"""Ticket #9 - toy world live mode; extended by ticket #33 to three decision
types over the 20-junction graph.

Live mode runs the SAME queries replay uses, but the answer comes from a real
model call instead of a recording. These tests drive it through an injected
fake client (deterministic, no API key, no spend) and assert on emitted
telemetry only - same discipline as test_replay.py.
"""

import pytest

from toyworld.live import DEFAULT_ROSTER, ModelDecision, default_pairs, run_live
from toyworld.world import ALL_QUERIES, ETA_ESTIMATE_QUERIES, ROUTE_CHOICE_QUERIES


class FakeClient:
    """A stand-in model: `chooser(model, query)` decides the answer.

    Deterministic and free, so cross-model correctness/cost differences in the
    tests come from the chooser we hand it, not from a live model's whims.
    """

    def __init__(self, chooser, tokens=(150, 6)):
        self._chooser = chooser
        self._in, self._out = tokens
        self._n = 0

    def decide(self, *, model, query):
        self._n += 1
        return ModelDecision(
            chosen=self._chooser(model, query),
            input_tokens=self._in,
            output_tokens=self._out,
            response_id=f"live-{model.split('/')[-1]}-{query.query_id}-{self._n}",
        )


def _perfect(model, query):
    return query.correct


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


def test_runs_the_full_roster_over_every_query(world, world_metrics):
    provider, exporter = world
    summary = run_live(
        FakeClient(_perfect),
        budget_usd=10.0,
        world_provider=provider,
        world_meter_provider=world_metrics[0],
    )
    expected_decisions = len(DEFAULT_ROSTER) * len(ALL_QUERIES)
    assert summary.decisions == expected_decisions
    assert not summary.budget_exhausted
    assert set(summary.by_model) == set(DEFAULT_ROSTER)
    for model in DEFAULT_ROSTER:
        assert summary.by_model[model]["decisions"] == len(ALL_QUERIES)

    events = _events(exporter)
    assert len(events) == expected_decisions
    for e in events:
        assert e.attributes["augmentloop.grade.source"] == "math"
        assert e.attributes["augmentloop.decision.type"] in (
            "route_choice",
            "eta_estimate",
            "next_hop",
        )
        assert e.attributes["augmentloop.cost.usd"] > 0


def test_difficulty_attribute_is_set_on_every_decision_span(world):
    provider, exporter = world
    run_live(FakeClient(_perfect), budget_usd=10.0, world_provider=provider)

    decision_spans = [
        s
        for s in exporter.get_finished_spans()
        if s.name != "gen_ai.evaluation.result" and not s.name.startswith("model-run")
    ]
    assert len(decision_spans) == len(DEFAULT_ROSTER) * len(ALL_QUERIES)
    for s in decision_spans:
        assert s.attributes["augmentloop.decision.difficulty"] in (
            "easy",
            "medium",
            "hard",
        )


def test_grades_differ_by_decision_type_when_a_model_is_only_good_at_easy_ones(world):
    """The right-sizing story needs real differentiation: a cheap model that
    nails one-step next_hop decisions but falls apart on multi-hop
    route_choice - a split, not a clean sweep (spec ticket #33)."""

    def chooser(model, query):
        if model == "anthropic/claude-sonnet-4.6":
            return query.correct  # premium model: always right
        if query.decision_type == "next_hop":
            return query.correct  # even the cheap tier nails the easy, one-step case
        # both cheaper models miss every multi-hop decision
        if query.decision_type == "route_choice":
            return "A" if query.correct == "B" else "B"
        return query.correct * 3  # eta_estimate: wildly outside tolerance

    provider, exporter = world
    summary = run_live(FakeClient(chooser), budget_usd=10.0, world_provider=provider)

    sonnet = summary.by_model_type[("anthropic/claude-sonnet-4.6", "route_choice")]
    haiku_next_hop = summary.by_model_type[("anthropic/claude-haiku-4.5", "next_hop")]
    haiku_route = summary.by_model_type[("anthropic/claude-haiku-4.5", "route_choice")]

    assert sonnet["correct"] == 20
    assert haiku_next_hop["correct"] == 20  # perfect on the easy type
    assert haiku_route["correct"] == 0  # zero on the hard type - the split


def test_cost_is_priced_per_model_from_real_token_counts(world):
    from gradebook.pricing import price

    provider, _ = world
    client = FakeClient(_perfect, tokens=(300, 20))
    summary = run_live(client, budget_usd=10.0, world_provider=provider)

    for model in DEFAULT_ROSTER:
        expected = price(model, 300, 20) * len(ALL_QUERIES)
        assert summary.by_model[model]["cost_usd"] == pytest.approx(expected)


def test_budget_cap_prevents_exceeding_the_cap(world):
    provider, _ = world
    summary = run_live(FakeClient(_perfect), budget_usd=0.0, world_provider=provider)
    assert summary.decisions == 0
    assert summary.budget_exhausted
    assert summary.total_cost_usd == 0.0


def test_budget_cap_stops_partway_without_overspending(world):
    provider, _ = world
    summary = run_live(
        FakeClient(_perfect, tokens=(300, 20)),
        budget_usd=0.01,
        world_provider=provider,
    )
    assert summary.budget_exhausted
    assert 0 < summary.decisions < len(DEFAULT_ROSTER) * len(ALL_QUERIES)
    assert summary.total_cost_usd <= 0.01


def test_generous_budget_runs_everything(world):
    provider, _ = world
    summary = run_live(FakeClient(_perfect), budget_usd=100.0, world_provider=provider)
    assert summary.decisions == len(DEFAULT_ROSTER) * len(ALL_QUERIES)
    assert not summary.budget_exhausted


def test_live_emits_aggregate_metrics_matching_the_summary(world, world_metrics):
    provider, _ = world
    reader = world_metrics[1]
    summary = run_live(
        FakeClient(_perfect),
        budget_usd=10.0,
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
    run_live(FakeClient(_perfect), budget_usd=10.0, world_provider=provider)
    spans = exporter.get_finished_spans()

    model_runs = [s for s in spans if s.name.startswith("model-run ")]
    events = _events(exporter)
    decision_spans = [
        s for s in spans if s not in model_runs and s not in events
    ]

    assert len(model_runs) == len(DEFAULT_ROSTER)
    assert len(decision_spans) == len(DEFAULT_ROSTER) * len(ALL_QUERIES)
    run_ids = {s.context.span_id for s in model_runs}
    decision_ids = {s.context.span_id: s for s in decision_spans}
    for e in events:
        parent_decision = decision_ids[e.parent.span_id]
        assert parent_decision.parent.span_id in run_ids
        assert e.context.trace_id == parent_decision.context.trace_id


def test_cost_per_correct_is_none_when_nothing_is_correct(world):
    provider, _ = world

    def always_wrong(model, query):
        if query.decision_type == "eta_estimate":
            return query.correct * 100  # far outside tolerance
        # next_hop / route_choice: return a value that is never correct
        return "definitely-not-it"

    summary = run_live(FakeClient(always_wrong), budget_usd=10.0, world_provider=provider)
    assert summary.correct == 0
    assert summary.cost_per_correct_usd is None
    assert summary.total_cost_usd > 0


def test_default_pairs_is_the_full_roster_by_query_cross_product():
    pairs = default_pairs()
    assert len(pairs) == len(DEFAULT_ROSTER) * len(ALL_QUERIES)
    assert pairs[0] == (DEFAULT_ROSTER[0], ALL_QUERIES[0])


def test_run_live_respects_an_explicit_pairs_override(world):
    """Production mode (routing.py) passes pairs directly, bypassing the
    roster x query cross product - only those exact (model, query) pairs run."""
    provider, _ = world
    one_query = ROUTE_CHOICE_QUERIES[0]
    pairs = [("google/gemini-2.5-flash-lite", one_query)]

    summary = run_live(
        FakeClient(_perfect), budget_usd=10.0, pairs=pairs, world_provider=provider
    )

    assert summary.decisions == 1
    assert set(summary.by_model) == {"google/gemini-2.5-flash-lite"}


def test_eta_estimate_grades_within_tolerance_not_exact_match(world):
    from toyworld.world import ETA_TOLERANCE_FRACTION

    provider, exporter = world
    query = ETA_ESTIMATE_QUERIES[0]

    def slightly_off(model, q):
        return q.correct * (1 + ETA_TOLERANCE_FRACTION / 2) if q is query else q.correct

    summary = run_live(
        FakeClient(slightly_off),
        budget_usd=10.0,
        pairs=[("anthropic/claude-sonnet-4.6", query)],
        world_provider=provider,
    )
    assert summary.correct == 1  # within tolerance, not an exact match
