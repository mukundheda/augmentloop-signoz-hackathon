"""Live mode (ticket #9): the same toy world, real model calls.

Replay reads a recorded choice; live mode asks each roster model to choose the
fastest route at each junction, prices the real token counts, and math-grades
the choice against the world's known truth - all through the same Gradebook
library call replay uses, so the emitted telemetry (and therefore the
dashboards) is identical in shape. Running every roster model over the same
junctions is what gives the model-vs-model comparison panel its rows.

The model call is behind an injected `ModelClient`, so the whole grading/pricing/
budget path is tested with a deterministic fake (no key, no spend). The real
OpenRouter client lives in `openrouter.py` and is only imported when a live run
actually needs it.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Optional, Protocol, Sequence

from opentelemetry import metrics, trace

from gradebook import record_decision
from gradebook.pricing import price

from .world import WORLD, Junction

TRACER_NAME = "toyworld"

# The comparison roster (CONTEXT.md): two Claude price tiers for the right-sizing
# story plus a cross-provider contrast. Every model must exist in the Gradebook
# pricing table, or pricing fails loud before any span is emitted.
DEFAULT_ROSTER: tuple[str, ...] = (
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.0-flash",
)

# Conservative token counts used only to pre-estimate a call's cost ceiling for
# the budget guard. Real cost is always computed from the actual response.
_EST_INPUT_TOKENS = 256


@dataclass(frozen=True)
class ModelDecision:
    """One model's route choice at one junction, with its real token usage."""

    chosen: str
    input_tokens: int
    output_tokens: int
    response_id: str


class ModelClient(Protocol):
    """The one thing live mode needs from a model: choose a route at a junction."""

    def decide(self, *, model: str, junction: Junction) -> ModelDecision: ...


@dataclass
class LiveSummary:
    """What one live run produced - printed for the operator, asserted in tests."""

    decisions: int = 0
    correct: int = 0
    total_cost_usd: float = 0.0
    budget_exhausted: bool = False
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def cost_per_correct_usd(self) -> Optional[float]:
        """The headline number, or None when nothing was correct (never a fake 0)."""
        return self.total_cost_usd / self.correct if self.correct else None


def run_live(
    client: ModelClient,
    *,
    budget_usd: float,
    roster: Sequence[str] = DEFAULT_ROSTER,
    world: Sequence[Junction] = WORLD,
    max_output_tokens: int = 64,
    world_provider: Optional[trace.TracerProvider] = None,
    world_meter_provider: Optional[metrics.MeterProvider] = None,
) -> LiveSummary:
    """Run every roster model over the whole world, under a hard budget cap.

    Each model gets one trace (`model-run <model>`) with a child span per
    junction, mirroring replay's per-journey waterfall. The budget guard is a
    *pre-call* check against a conservative cost ceiling, so a run stops before
    it can push total spend past `budget_usd` - it never overshoots and errors
    after the fact, it simply doesn't place a call it cannot afford.
    """
    provider = world_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer(TRACER_NAME)
    summary = LiveSummary()

    for model in roster:
        ceiling = price(model, _EST_INPUT_TOKENS, max_output_tokens)
        with tracer.start_as_current_span(f"model-run {model}"):
            for junction in world:
                if summary.total_cost_usd + ceiling > budget_usd:
                    summary.budget_exhausted = True
                    return summary
                with tracer.start_as_current_span(f"junction {junction.name} decision"):
                    decision = client.decide(model=model, junction=junction)
                    correct = junction.true_fastest
                    record_decision(
                        name="route.fastest",
                        model=model,
                        chosen=decision.chosen,
                        correct=correct,
                        input_tokens=decision.input_tokens,
                        output_tokens=decision.output_tokens,
                        decision_type="route_choice",
                        response_id=decision.response_id,
                        explanation=(
                            f"chose {decision.chosen} "
                            f"({junction.options.get(decision.chosen, '?')}m); "
                            f"true fastest {correct} ({junction.options[correct]}m)"
                        ),
                        tracer_provider=provider,
                        meter_provider=world_meter_provider,
                    )
                    cost = price(model, decision.input_tokens, decision.output_tokens)
                    is_correct = operator.eq(decision.chosen, correct)
                    summary.decisions += 1
                    summary.correct += int(is_correct)
                    summary.total_cost_usd += cost
                    row = summary.by_model.setdefault(
                        model, {"decisions": 0, "correct": 0, "cost_usd": 0.0}
                    )
                    row["decisions"] += 1
                    row["correct"] += int(is_correct)
                    row["cost_usd"] += cost

    return summary
