"""Ticket #6 - toy world replay mode.

Assertions use the literal frozen attribute names from docs/conventions.md
section 9, on emitted telemetry only - same discipline as the library tests.
"""

import pytest

from toyworld import replay


def _run(world, outcomes, recording_path):
    world_provider, world_exporter = world
    outcomes_provider, outcomes_exporter = outcomes
    summary = replay(
        recording_path,
        world_provider=world_provider,
        outcomes_provider=outcomes_provider,
    )
    return summary, world_exporter, outcomes_exporter


def test_every_decision_is_recorded_and_math_graded(world, outcomes, recording_path):
    summary, world_exporter, _ = _run(world, outcomes, recording_path)

    events = [
        s
        for s in world_exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    ]
    # 4 drivers x 3 junctions in the committed recording.
    assert summary.decisions == 12
    assert len(events) == 12
    for e in events:
        assert e.attributes["augmentloop.grade.source"] == "math"
        assert e.attributes["gen_ai.evaluation.name"] == "route.fastest"
        assert e.attributes["augmentloop.decision.type"] == "route_choice"
        assert e.attributes["augmentloop.cost.usd"] > 0


def test_grades_match_the_engines_known_truth(world, outcomes, recording_path):
    summary, world_exporter, _ = _run(world, outcomes, recording_path)

    # From the committed recording: d1 misses J3 (G over F), d3 misses J1 and
    # J2, d4 misses J2 -> 8 of 12 correct.
    assert summary.correct == 8
    labels = [
        s.attributes["gen_ai.evaluation.score.label"]
        for s in world_exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    ]
    assert labels.count("correct") == 8
    assert labels.count("incorrect") == 4


def test_decision_events_sit_inside_a_journey_trace_waterfall(
    world, outcomes, recording_path
):
    _, world_exporter, _ = _run(world, outcomes, recording_path)
    spans = world_exporter.get_finished_spans()

    journeys = [s for s in spans if s.name.startswith("journey ")]
    junctions = [s for s in spans if s.name.startswith("junction ")]
    events = [s for s in spans if s.name == "gen_ai.evaluation.result"]

    assert len(journeys) == 4
    assert len(junctions) == 12
    # Real waterfall: event under junction span, junction under journey root,
    # all three sharing one trace per driver.
    junction_ids = {s.context.span_id: s for s in junctions}
    journey_ids = {s.context.span_id: s for s in journeys}
    for e in events:
        parent_junction = junction_ids[e.parent.span_id]
        assert parent_junction.parent.span_id in journey_ids
        assert e.context.trace_id == parent_junction.context.trace_id


def test_reality_outcomes_span_link_back_across_the_service_boundary(
    world, outcomes, recording_path
):
    summary, world_exporter, outcomes_exporter = _run(world, outcomes, recording_path)

    assert summary.outcomes == 4
    late_grades = outcomes_exporter.get_finished_spans()
    assert len(late_grades) == 4

    decision_events = {
        s.attributes["gen_ai.response.id"]: s
        for s in world_exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    }
    for grade in late_grades:
        assert grade.attributes["augmentloop.grade.source"] == "reality"
        assert grade.attributes["gen_ai.evaluation.name"] == "journey.on_time"
        # The link target is the junction decision span the outcome judges -
        # resolve it via the graded response id's decision event parent.
        graded = decision_events[grade.attributes["gen_ai.response.id"]]
        assert len(grade.links) == 1
        assert grade.links[0].context.trace_id == graded.context.trace_id
        assert grade.links[0].context.span_id == graded.parent.span_id


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


def test_cost_per_correct_is_the_headline_division(world, outcomes, recording_path):
    summary, _, _ = _run(world, outcomes, recording_path)
    assert summary.cost_per_correct_usd == pytest.approx(
        summary.total_cost_usd / summary.correct
    )
    # Three roster models present -> the model-vs-model panel has rows to show.
    assert set(summary.by_model) == {
        "anthropic/claude-3.5-haiku",
        "anthropic/claude-sonnet-4",
        "google/gemini-2.0-flash",
    }
