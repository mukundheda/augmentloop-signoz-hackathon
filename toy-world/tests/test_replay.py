"""Ticket #6 - toy world replay mode; extended by ticket #33 to three decision
types read from a recorder-written recording, including the deferred
route_choice reality grade restored after a prior #33 revision dropped it.

Assertions use the literal frozen attribute names from docs/conventions.md
section 9, on emitted telemetry only - same discipline as the library tests.
"""

import collections
import json

import pytest

from toyworld.replay import load_recording
from toyworld.replay import replay as run_replay
from toyworld.world import QUERIES_BY_ID


def _run(world, outcomes, recording_path, world_metrics=None, outcomes_metrics=None):
    world_provider, world_exporter = world
    outcomes_provider, outcomes_exporter = outcomes
    summary = run_replay(
        recording_path,
        world_provider=world_provider,
        outcomes_provider=outcomes_provider,
        world_meter_provider=world_metrics[0] if world_metrics else None,
        outcomes_meter_provider=outcomes_metrics[0] if outcomes_metrics else None,
    )
    return summary, world_exporter, outcomes_exporter


def _metrics_by_name(metric_reader) -> dict:
    data = metric_reader.get_metrics_data()
    out = {}
    if data is None:
        return out
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                out[metric.name] = metric
    return out


def test_committed_recording_covers_a_complete_balanced_grid(recording_path):
    """The recording must be the full roster crossed with every decision type,
    20 queries in each cell.

    This replaces an assertion on a literal decision count, which only held for
    one roster size and said nothing about shape. Balance is the property that
    actually matters: an unbalanced grid would let one model's easy cell inflate
    a per-model total, and the right-sizing comparison reads down the columns.
    """
    decisions, _ = load_recording(recording_path)
    models = {d.model for d in decisions}
    types = {d.decision_type for d in decisions}
    assert types == {"route_choice", "eta_estimate", "next_hop"}
    assert len(models) >= 3

    per_cell = collections.Counter((d.model, d.decision_type) for d in decisions)
    assert len(per_cell) == len(models) * len(types), "grid has a missing cell"
    assert set(per_cell.values()) == {20}, f"unbalanced grid: {per_cell}"
    assert len(decisions) == len(models) * len(types) * 20


def test_committed_recording_has_one_outcome_per_route_choice_decision(recording_path):
    decisions, outcomes = load_recording(recording_path)
    route_choice_decisions = [d for d in decisions if d.decision_type == "route_choice"]
    assert len(outcomes) == len(route_choice_decisions) > 0


def test_every_decision_is_recorded_and_math_graded(world, outcomes, recording_path):
    summary, world_exporter, _ = _run(world, outcomes, recording_path)

    events = [
        s
        for s in world_exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    ]
    assert summary.decisions == len(events) > 0
    for e in events:
        assert e.attributes["augmentloop.grade.source"] == "math"
        assert e.attributes["augmentloop.decision.type"] in (
            "route_choice",
            "eta_estimate",
            "next_hop",
        )
        assert e.attributes["augmentloop.cost.usd"] > 0


def test_difficulty_attribute_is_set_on_every_decision_span(world, outcomes, recording_path):
    _, world_exporter, _ = _run(world, outcomes, recording_path)
    spans = world_exporter.get_finished_spans()

    events = {s for s in spans if s.name == "gen_ai.evaluation.result"}
    model_runs = {s for s in spans if s.name.startswith("model-run ")}
    decision_spans = [s for s in spans if s not in events and s not in model_runs]

    assert len(decision_spans) > 0
    for s in decision_spans:
        assert s.attributes["augmentloop.decision.difficulty"] in (
            "easy",
            "medium",
            "hard",
        )


def test_grades_recompute_the_correct_answer_from_the_graph_not_the_file(
    world, outcomes, recording_path
):
    """The recording never stores a `correct` field - `replay.py` must look it
    up fresh from `world.QUERIES_BY_ID` by query_id (spec: "never hand-author
    the recording's answers")."""
    raw_lines = [json.loads(line) for line in recording_path.read_text().splitlines() if line]
    assert all("correct" not in entry for entry in raw_lines)

    _, world_exporter, _ = _run(world, outcomes, recording_path)
    events = [
        s
        for s in world_exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    ]
    # Every emitted decision type is one this build's graph actually has -
    # the cheapest cross-check available from the public telemetry surface
    # that grading came from a fresh QUERIES_BY_ID lookup, not the file.
    known_types = {q.decision_type for q in QUERIES_BY_ID.values()}
    for e in events:
        assert e.attributes["augmentloop.decision.type"] in known_types


def test_decision_events_sit_under_a_per_model_trace_waterfall(world, outcomes, recording_path):
    _, world_exporter, _ = _run(world, outcomes, recording_path)
    spans = world_exporter.get_finished_spans()

    model_runs = [s for s in spans if s.name.startswith("model-run ")]
    events = [s for s in spans if s.name == "gen_ai.evaluation.result"]
    decision_spans = [
        s for s in spans if s not in model_runs and s not in events
    ]

    run_ids = {s.context.span_id for s in model_runs}
    decision_ids = {s.context.span_id: s for s in decision_spans}
    for e in events:
        parent_decision = decision_ids[e.parent.span_id]
        assert parent_decision.parent.span_id in run_ids
        assert e.context.trace_id == parent_decision.context.trace_id


def test_reality_outcomes_span_link_back_across_the_service_boundary(
    world, outcomes, recording_path
):
    """docs/conventions.md section 6, span-link Role 1 (restored after a prior
    #33 revision dropped this path entirely): every route_choice decision's
    deferred `journey.on_time` grade lands in the separate `outcomes`
    provider/service and carries a span link back to the exact decision span
    it judges."""
    summary, world_exporter, outcomes_exporter = _run(world, outcomes, recording_path)

    decisions, recorded_outcomes = load_recording(recording_path)
    assert summary.outcomes == len(recorded_outcomes) > 0

    late_grades = outcomes_exporter.get_finished_spans()
    assert len(late_grades) == summary.outcomes

    decision_events = {
        s.attributes["gen_ai.response.id"]: s
        for s in world_exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    }
    for grade in late_grades:
        assert grade.attributes["augmentloop.grade.source"] == "reality"
        assert grade.attributes["gen_ai.evaluation.name"] == "journey.on_time"
        assert grade.attributes["augmentloop.decision.type"] == "route_choice"
        # The link target is the decision span the outcome judges - resolve it
        # via the graded response id's decision event parent.
        graded = decision_events[grade.attributes["gen_ai.response.id"]]
        assert len(grade.links) == 1
        assert grade.links[0].context.trace_id == graded.context.trace_id
        assert grade.links[0].context.span_id == graded.parent.span_id

    # The late grades never land in the `toy-world` service's exporter - the
    # whole point of the separate `outcomes` provider.
    world_events = [
        s
        for s in world_exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    ]
    assert all(e.attributes["augmentloop.grade.source"] == "math" for e in world_events)


def test_replay_is_deterministic(world, outcomes, recording_path):
    summary_a, world_a, _ = _run(world, outcomes, recording_path)

    from conftest import _pair

    world2, outcomes2 = _pair(), _pair()
    summary_b, world_b, _ = _run(world2, outcomes2, recording_path)

    assert summary_a.decisions == summary_b.decisions
    assert summary_a.correct == summary_b.correct
    assert summary_a.total_cost_usd == pytest.approx(summary_b.total_cost_usd)

    def fingerprint(exporter):
        return [
            (
                s.name,
                s.attributes.get("gen_ai.response.id"),
                s.attributes.get("gen_ai.evaluation.score.label"),
                s.attributes.get("augmentloop.cost.usd"),
            )
            for s in exporter.get_finished_spans()
        ]

    assert fingerprint(world_a) == fingerprint(world_b)


def test_replay_emits_aggregate_metrics_matching_the_summary(
    world, outcomes, recording_path, world_metrics, outcomes_metrics
):
    """Ticket #7: the metrics ride the same replay call as the events, so the
    counter's total matches summary.decisions exactly - no separate code path
    to drift out of sync."""
    summary, _, _ = _run(world, outcomes, recording_path, world_metrics, outcomes_metrics)

    _, world_reader = world_metrics
    _, outcomes_reader = outcomes_metrics

    world_points = _metrics_by_name(world_reader)["gradebook.decisions.graded"].data.data_points
    assert sum(p.value for p in world_points) == summary.decisions

    cost_points = _metrics_by_name(world_reader)["gradebook.decision.cost.usd"].data.data_points
    assert sum(p.sum for p in cost_points) == pytest.approx(summary.total_cost_usd)

    outcomes_points = _metrics_by_name(outcomes_reader)["gradebook.decisions.graded"].data.data_points
    assert sum(p.value for p in outcomes_points) == summary.outcomes
    assert all(p.attributes["augmentloop.grade.source"] == "reality" for p in outcomes_points)


def test_unknown_query_id_fails_loud(world, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps(
            {
                "type": "decision",
                "decision_type": "next_hop",
                "query_id": "next_hop-J999",
                "model": "anthropic/claude-sonnet-4.6",
                "chosen": "J1",
                "input_tokens": 100,
                "output_tokens": 5,
                "response_id": "bad-1",
            }
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="next_hop-J999"):
        load_recording(bad)


def test_unknown_graded_response_id_fails_loud(world, outcomes, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps(
            {
                "type": "outcome",
                "graded_response_id": "no-such-decision",
                "on_time": True,
                "model": "anthropic/claude-sonnet-4.6",
            }
        )
        + "\n"
    )
    world_provider, _ = world
    outcomes_provider, _ = outcomes
    with pytest.raises(ValueError, match="no-such-decision"):
        run_replay(bad, world_provider=world_provider, outcomes_provider=outcomes_provider)


def test_by_model_type_breakdown_covers_every_decision_type(world, outcomes, recording_path):
    summary, _, _ = _run(world, outcomes, recording_path)
    decision_types = {dt for (_, dt) in summary.by_model_type}
    assert decision_types == {"route_choice", "eta_estimate", "next_hop"}


def test_cost_per_correct_is_the_headline_division(world, outcomes, recording_path):
    summary, _, _ = _run(world, outcomes, recording_path)
    assert summary.cost_per_correct_usd == pytest.approx(
        summary.total_cost_usd / summary.correct
    )


def test_summary_reports_every_model_in_the_recording(world, outcomes, recording_path):
    """Named as a property, not as a hardcoded roster.

    This used to assert one literal set of three model slugs, which meant it
    only ever confirmed that the roster had not changed. What matters is that
    the breakdown loses nobody: a model present in the recording but missing
    from `by_model` would silently drop out of the right-sizing comparison
    while every total still added up.
    """
    summary, _, _ = _run(world, outcomes, recording_path)
    decisions, _ = load_recording(recording_path)
    assert set(summary.by_model) == {d.model for d in decisions}
    assert sum(row["decisions"] for row in summary.by_model.values()) == len(decisions)
    assert sum(row["correct"] for row in summary.by_model.values()) == summary.correct
