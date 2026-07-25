"""Ticket #6 - toy world replay mode; extended by ticket #33 to three decision
types read from a recorder-written recording.

Assertions use the literal frozen attribute names from docs/conventions.md
section 9, on emitted telemetry only - same discipline as the library tests.
The committed recording (recordings/replay-v1.jsonl) is, as of this PR, a
PLACEHOLDER written by the recorder against a trivial always-correct oracle
client (NOT a real model) - see the PR description and toy-world/README.md.
These tests pin the mechanism (grading, cost, trace shape, difficulty), not a
particular win/loss split, since the placeholder is a clean sweep by
construction.
"""

import json

import pytest

from toyworld.replay import load_recording
from toyworld.replay import replay as run_replay
from toyworld.world import QUERIES_BY_ID


def _run(world, recording_path, world_metrics=None):
    world_provider, world_exporter = world
    summary = run_replay(
        recording_path,
        world_provider=world_provider,
        world_meter_provider=world_metrics[0] if world_metrics else None,
    )
    return summary, world_exporter


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


def test_committed_recording_has_roughly_180_decisions(recording_path):
    entries = load_recording(recording_path)
    assert 170 <= len(entries) <= 190


def test_every_decision_is_recorded_and_math_graded(world, recording_path):
    summary, world_exporter = _run(world, recording_path)

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


def test_difficulty_attribute_is_set_on_every_decision_span(world, recording_path):
    _, world_exporter = _run(world, recording_path)
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
    world, recording_path
):
    """The recording never stores a `correct` field - `replay.py` must look it
    up fresh from `world.QUERIES_BY_ID` by query_id (spec: "never hand-author
    the recording's answers")."""
    raw_lines = [json.loads(line) for line in recording_path.read_text().splitlines() if line]
    assert all("correct" not in entry for entry in raw_lines)

    _, world_exporter = _run(world, recording_path)
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


def test_decision_events_sit_under_a_per_model_trace_waterfall(world, recording_path):
    _, world_exporter = _run(world, recording_path)
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


def test_replay_is_deterministic(world, recording_path):
    summary_a, world_a = _run(world, recording_path)

    from conftest import _pair

    world2 = _pair()
    summary_b, world_b = _run(world2, recording_path)

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
    world, recording_path, world_metrics
):
    """Ticket #7: the metrics ride the same replay call as the events, so the
    counter's total matches summary.decisions exactly - no separate code path
    to drift out of sync."""
    summary, _ = _run(world, recording_path, world_metrics)

    _, world_reader = world_metrics

    world_points = _metrics_by_name(world_reader)["gradebook.decisions.graded"].data.data_points
    assert sum(p.value for p in world_points) == summary.decisions

    cost_points = _metrics_by_name(world_reader)["gradebook.decision.cost.usd"].data.data_points
    assert sum(p.sum for p in cost_points) == pytest.approx(summary.total_cost_usd)


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


def test_by_model_type_breakdown_covers_every_decision_type(world, recording_path):
    summary, _ = _run(world, recording_path)
    decision_types = {dt for (_, dt) in summary.by_model_type}
    assert decision_types == {"route_choice", "eta_estimate", "next_hop"}


def test_cost_per_correct_is_the_headline_division(world, recording_path):
    summary, _ = _run(world, recording_path)
    assert summary.cost_per_correct_usd == pytest.approx(
        summary.total_cost_usd / summary.correct
    )
    assert set(summary.by_model) == {
        "anthropic/claude-haiku-4.5",
        "anthropic/claude-sonnet-4.6",
        "google/gemini-2.5-flash-lite",
    }
