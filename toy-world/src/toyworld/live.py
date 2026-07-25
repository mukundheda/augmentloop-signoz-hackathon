"""Live mode (ticket #9, extended by #33): the same toy world, real model calls.

Live mode asks each roster model to answer each `Query` (ticket #33: three
decision types - route_choice, eta_estimate, next_hop - over the 20-junction
graph in `world.py`), prices the real token counts, and grades the answer
against the query's own computed correct answer and checker - all through the
same Gradebook library call replay uses, so the emitted telemetry (and
therefore the dashboards) is identical in shape. Running every roster model
over every query is what gives the model-vs-model comparison panel its rows,
and running all three decision types is what lets a right-sizing proposal
target one decision type instead of "everything" (routing.py).

The model call is behind an injected `ModelClient`, so the whole grading/pricing/
budget path is tested with a deterministic fake (no key, no spend). The real
OpenRouter client lives in `openrouter.py` and is only imported when a live run
actually needs it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import Callable, Optional, Protocol, Sequence

from opentelemetry import metrics, trace

from gradebook import logs as gb_logs
from gradebook import record_decision
from gradebook.pricing import UnknownModelError, price

from .world import ALL_QUERIES, Query

TRACER_NAME = "toyworld"

# Decision-type strings live in world.py (DECISION_TYPES, ticket #33) - this
# module held the single DECISION_TYPE constant before #33; routing.py and
# __main__.py now import the three-type versions straight from world.py.

# The comparison roster (CONTEXT.md): two Claude price tiers for the right-sizing
# story plus a cross-provider contrast. Every model must exist in the Gradebook
# pricing table, or pricing fails loud before any span is emitted.
#
# Refreshed 2026-07-24 (ticket #9) to current models, grounded against
# OpenRouter's public /models API: the prior slugs were stale (claude-3.5-haiku
# retired by Anthropic 2026-02-19; claude-sonnet-4 past its announced
# retirement). Old slugs stay in gradebook.pricing.PRICES so the committed
# replay recording still prices - see that module's comment.
DEFAULT_ROSTER: tuple[str, ...] = (
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-sonnet-4.6",
    "google/gemini-2.5-flash-lite",
)

# Conservative token counts used only to pre-estimate a call's cost ceiling for
# the budget guard. Real cost is always computed from the actual response.
_EST_INPUT_TOKENS = 256


@dataclass(frozen=True)
class ModelDecision:
    """One model's answer to one query, with its real token usage."""

    chosen: object
    input_tokens: int
    output_tokens: int
    response_id: str


class ModelClient(Protocol):
    """The one thing live mode needs from a model: answer one query."""

    def decide(self, *, model: str, query: Query) -> ModelDecision: ...


@dataclass
class LiveSummary:
    """What one live run produced - printed for the operator, asserted in tests."""

    decisions: int = 0
    correct: int = 0
    total_cost_usd: float = 0.0
    budget_exhausted: bool = False
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)
    # (model, decision_type) -> {"decisions", "correct", "cost_usd"} - the
    # breakdown the right-sizing story and the PR's result table both read
    # from (per-model, per-decision-type correctness and cost).
    by_model_type: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)
    # (model, decision_type, difficulty) -> same shape, one level finer.
    by_model_type_difficulty: dict[tuple[str, str, str], dict[str, float]] = field(
        default_factory=dict
    )

    @property
    def cost_per_correct_usd(self) -> Optional[float]:
        """The headline number, or None when nothing was correct (never a fake 0)."""
        return self.total_cost_usd / self.correct if self.correct else None


def default_pairs(
    roster: Sequence[str] = DEFAULT_ROSTER, queries: Sequence[Query] = ALL_QUERIES
) -> tuple[tuple[str, Query], ...]:
    """The comparison-mode run: every roster model over every query (spec
    ticket #33: 3 decision types x 3 roster models x 20 queries = 180)."""
    return tuple((model, query) for model in roster for query in queries)


def run_live(
    client: ModelClient,
    *,
    budget_usd: float,
    pairs: Optional[Sequence[tuple[str, Query]]] = None,
    roster: Sequence[str] = DEFAULT_ROSTER,
    queries: Sequence[Query] = ALL_QUERIES,
    max_output_tokens: int = 64,
    world_provider: Optional[trace.TracerProvider] = None,
    world_meter_provider: Optional[metrics.MeterProvider] = None,
    on_decision: Optional[Callable[[str, Query, ModelDecision, bool, float], None]] = None,
) -> LiveSummary:
    """Run a set of (model, query) pairs under a hard budget cap.

    `pairs` defaults to the full comparison cross-product (`roster x queries`)
    - the data the model-vs-model comparison panel and the right-sizing
    proposal both read from. `--production` (routing.py / __main__.py) instead
    passes an explicit `pairs` that routes each decision type to only the one
    model currently assigned to it, so a before/after reroute pair is directly
    comparable (no roster model leaks into the "after" run's spend).

    Each model gets one trace (`model-run <model>`), with one child span per
    query (named after the query's decision type and id) carrying the
    `augmentloop.decision.difficulty` attribute (ticket #33). The budget guard
    is a *pre-call* check against a conservative cost ceiling, so a run stops
    before it can push total spend past `budget_usd` - it never overshoots and
    errors after the fact, it simply doesn't place a call it cannot afford.

    `on_decision`, if given, is called after every successfully-graded
    decision with `(model, query, ModelDecision, is_correct, cost_usd)` - the
    seam the recorder (`recorder.py`) uses to capture each real answer into a
    replay file, without duplicating this loop.
    """
    provider = world_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer(TRACER_NAME)
    summary = LiveSummary()

    run_pairs = pairs if pairs is not None else default_pairs(roster, queries)

    # Grouped by model so consecutive pairs for the same model share one
    # `model-run <model>` trace (mirrors the pre-#33 per-model waterfall);
    # `default_pairs` and `--production`'s per-decision-type pairs are both
    # already model-major/type-contiguous, so groupby needs no sort.
    for model, model_pairs in groupby(run_pairs, key=lambda pair: pair[0]):
        with tracer.start_as_current_span(f"model-run {model}"):
            # Priced INSIDE the model-run span on purpose: an unknown-model
            # pricing miss (§13) has no decision to link to, so the model-run
            # span is the only thing that can carry it.
            try:
                ceiling = price(model, _EST_INPUT_TOKENS, max_output_tokens)
            except UnknownModelError:
                # A stale roster/routing slug. Log while the model-run span is
                # current - there is no decision to link, the whole model is
                # unpriced - then fail loud as before (conventions §13).
                gb_logs.unknown_model_pricing_miss(model=model)
                raise
            for _, query in model_pairs:
                if summary.total_cost_usd + ceiling > budget_usd:
                    # The run stopped before it could overspend. Log while the
                    # model-run span is current so the failure links to the run
                    # that hit the cap (conventions §13).
                    gb_logs.budget_guard_tripped(
                        budget_usd=budget_usd,
                        spend_usd=summary.total_cost_usd,
                        model=model,
                        decision_type=query.decision_type,
                    )
                    summary.budget_exhausted = True
                    return summary

                with tracer.start_as_current_span(
                    f"{query.decision_type} {query.query_id} decision"
                ) as span:
                    span.set_attribute(
                        "augmentloop.decision.difficulty", query.difficulty
                    )
                    decision = client.decide(model=model, query=query)
                    record_decision(
                        name=query.eval_name,
                        model=model,
                        chosen=decision.chosen,
                        correct=query.correct,
                        input_tokens=decision.input_tokens,
                        output_tokens=decision.output_tokens,
                        decision_type=query.decision_type,
                        response_id=decision.response_id,
                        explanation=query.explain(decision.chosen),
                        checker=query.checker,
                        tracer_provider=provider,
                        meter_provider=world_meter_provider,
                    )
                    cost = price(model, decision.input_tokens, decision.output_tokens)
                    is_correct = bool(query.checker(decision.chosen, query.correct))

                    summary.decisions += 1
                    summary.correct += int(is_correct)
                    summary.total_cost_usd += cost

                    row = summary.by_model.setdefault(
                        model, {"decisions": 0, "correct": 0, "cost_usd": 0.0}
                    )
                    row["decisions"] += 1
                    row["correct"] += int(is_correct)
                    row["cost_usd"] += cost

                    type_row = summary.by_model_type.setdefault(
                        (model, query.decision_type),
                        {"decisions": 0, "correct": 0, "cost_usd": 0.0},
                    )
                    type_row["decisions"] += 1
                    type_row["correct"] += int(is_correct)
                    type_row["cost_usd"] += cost

                    diff_row = summary.by_model_type_difficulty.setdefault(
                        (model, query.decision_type, query.difficulty),
                        {"decisions": 0, "correct": 0, "cost_usd": 0.0},
                    )
                    diff_row["decisions"] += 1
                    diff_row["correct"] += int(is_correct)
                    diff_row["cost_usd"] += cost

                    if on_decision is not None:
                        on_decision(model, query, decision, is_correct, cost)

    return summary
