"""Ticket #9 - toy world live mode.

Live mode runs the SAME junctions replay uses, but the route choice comes from a
real model call instead of a recording. These tests drive it through an injected
fake client (deterministic, no API key, no spend) and assert on emitted
telemetry only - same discipline as test_replay.py. One real OpenRouter run
covers the "against real models" acceptance criterion outside the test suite.
"""

import operator

import pytest

from toyworld.live import (
    DEFAULT_ROSTER,
    ModelDecision,
    run_live,
)
from toyworld.world import WORLD


class FakeClient:
    """A stand-in model: `chooser(model, junction)` decides the route.

    Deterministic and free, so cross-model correctness/cost differences in the
    tests come from the chooser we hand it, not from a live model's whims.
    """

    def __init__(self, chooser, tokens=(200, 10)):
        self._chooser = chooser
        self._in, self._out = tokens
        self._n = 0

    def decide(self, *, model, junction):
        self._n += 1
        return ModelDecision(
            chosen=self._chooser(model, junction),
            input_tokens=self._in,
            output_tokens=self._out,
            response_id=f"live-{model.split('/')[-1]}-{junction.name}-{self._n}",
        )


def _perfect(model, junction):
    return junction.true_fastest


def _events(exporter):
    return [
        s
        for s in exporter.get_finished_spans()
        if s.name == "gen_ai.evaluation.result"
    ]


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


def test_runs_the_same_decision_across_the_full_roster(world, world_metrics):
    provider, exporter = world
    summary = run_live(
        FakeClient(_perfect),
        budget_usd=1.0,
        world_provider=provider,
        world_meter_provider=world_metrics[0],
    )
    # 3 roster models x 3 junctions in WORLD.
    assert summary.decisions == 9
    assert not summary.budget_exhausted
    assert set(summary.by_model) == set(DEFAULT_ROSTER)
    for model in DEFAULT_ROSTER:
        assert summary.by_model[model]["decisions"] == len(WORLD)

    events = _events(exporter)
    assert len(events) == 9
    for e in events:
        assert e.attributes["augmentloop.grade.source"] == "math"
        assert e.attributes["gen_ai.evaluation.name"] == "route.fastest"
        assert e.attributes["augmentloop.decision.type"] == "route_choice"
        assert e.attributes["augmentloop.cost.usd"] > 0


def test_grades_reflect_each_models_own_choices(world):
    """The model-vs-model story needs real differentiation: a stronger model
    gets more right. Chooser: sonnet perfect, haiku misses J3, flash misses
    J2 and J3."""

    def chooser(model, junction):
        if model == "anthropic/claude-sonnet-4":
            return junction.true_fastest
        if model == "anthropic/claude-3.5-haiku":
            return "G" if junction.name == "J3" else junction.true_fastest
        # gemini-flash: wrong at J2 and J3
        if junction.name == "J2":
            return "C"
        if junction.name == "J3":
            return "G"
        return junction.true_fastest

    provider, exporter = world
    summary = run_live(FakeClient(chooser), budget_usd=1.0, world_provider=provider)

    assert summary.by_model["anthropic/claude-sonnet-4"]["correct"] == 3
    assert summary.by_model["anthropic/claude-3.5-haiku"]["correct"] == 2
    assert summary.by_model["google/gemini-2.0-flash"]["correct"] == 1
    assert summary.correct == 6

    labels = [e.attributes["gen_ai.evaluation.score.label"] for e in _events(exporter)]
    assert labels.count("correct") == 6
    assert labels.count("incorrect") == 3


def test_cost_is_priced_per_model_from_real_token_counts(world):
    from gradebook.pricing import price

    provider, _ = world
    client = FakeClient(_perfect, tokens=(300, 20))
    summary = run_live(client, budget_usd=1.0, world_provider=provider)

    for model in DEFAULT_ROSTER:
        expected = price(model, 300, 20) * len(WORLD)
        assert summary.by_model[model]["cost_usd"] == pytest.approx(expected)


def test_budget_cap_prevents_exceeding_the_cap(world):
    provider, _ = world
    # A cap smaller than a single conservative call ceiling -> nothing runs.
    summary = run_live(FakeClient(_perfect), budget_usd=0.0, world_provider=provider)
    assert summary.decisions == 0
    assert summary.budget_exhausted
    assert summary.total_cost_usd == 0.0


def test_budget_cap_stops_partway_without_overspending(world):
    provider, _ = world
    # Enough for a few calls but not the whole roster.
    summary = run_live(
        FakeClient(_perfect, tokens=(300, 20)),
        budget_usd=0.002,
        world_provider=provider,
    )
    assert summary.budget_exhausted
    assert 0 < summary.decisions < 9
    assert summary.total_cost_usd <= 0.002


def test_generous_budget_runs_the_whole_roster(world):
    provider, _ = world
    summary = run_live(FakeClient(_perfect), budget_usd=100.0, world_provider=provider)
    assert summary.decisions == 9
    assert not summary.budget_exhausted


def test_live_emits_aggregate_metrics_matching_the_summary(world, world_metrics):
    provider, _ = world
    reader = world_metrics[1]
    summary = run_live(
        FakeClient(_perfect),
        budget_usd=1.0,
        world_provider=provider,
        world_meter_provider=world_metrics[0],
    )
    metrics = _metrics_by_name(reader)
    graded = metrics["gradebook.decisions.graded"].data.data_points
    assert sum(p.value for p in graded) == summary.decisions

    cost = metrics["gradebook.decision.cost.usd"].data.data_points
    assert sum(p.sum for p in cost) == pytest.approx(summary.total_cost_usd)


def test_live_traces_are_one_waterfall_per_model(world):
    provider, exporter = world
    run_live(FakeClient(_perfect), budget_usd=1.0, world_provider=provider)
    spans = exporter.get_finished_spans()

    model_runs = [s for s in spans if s.name.startswith("model-run ")]
    junctions = [s for s in spans if s.name.startswith("junction ")]
    events = _events(exporter)

    assert len(model_runs) == len(DEFAULT_ROSTER)
    assert len(junctions) == 9
    run_ids = {s.context.span_id for s in model_runs}
    junction_ids = {s.context.span_id: s for s in junctions}
    for e in events:
        parent_junction = junction_ids[e.parent.span_id]
        assert parent_junction.parent.span_id in run_ids
        assert e.context.trace_id == parent_junction.context.trace_id


def test_cost_per_correct_is_none_when_nothing_is_correct(world):
    provider, _ = world

    def always_wrong(model, junction):
        # Pick a route that is never the fastest at any junction.
        return next(r for r in sorted(junction.options) if r != junction.true_fastest)

    summary = run_live(FakeClient(always_wrong), budget_usd=1.0, world_provider=provider)
    assert summary.correct == 0
    assert summary.cost_per_correct_usd is None
    assert summary.total_cost_usd > 0
