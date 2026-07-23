"""Replay mode: deterministic, no API keys, judge-runnable (spec stories 12-13).

Reads a committed JSONL recording of driver decisions and journey outcomes and
replays them through the Gradebook library:

- each junction decision becomes a math-graded `gen_ai.evaluation.result`
  event, parented under the driver's journey trace (a real trace waterfall in
  SigNoz, per the T3 re-scope addendum);
- each journey outcome becomes a *reality* grade that span-links back to the
  decision span it judges (T5, span-link Role 1).

The decision spans are emitted by the `toy-world` service and the late reality
grades by the `toy-world-outcomes` service, mirroring how outcomes arrive from
a different process in real systems - both services appear in SigNoz.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from opentelemetry import metrics, trace

from gradebook import DecisionRef, capture_decision, record_decision, record_reality_grade

from .world import JourneyOutcome, JunctionDecision

TRACER_NAME = "toyworld"


def load_recording(path: Path) -> tuple[list[JunctionDecision], list[JourneyOutcome]]:
    """Parse the JSONL recording into decisions and outcomes, order preserved."""
    decisions: list[JunctionDecision] = []
    outcomes: list[JourneyOutcome] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        kind = entry.pop("type")
        if kind == "decision":
            decisions.append(JunctionDecision(**entry))
        elif kind == "outcome":
            outcomes.append(JourneyOutcome(**entry))
        else:
            raise ValueError(f"unknown recording entry type: {kind!r}")
    return decisions, outcomes


@dataclass
class ReplaySummary:
    """What one replay run produced - printed for the judge, asserted in tests."""

    decisions: int = 0
    correct: int = 0
    total_cost_usd: float = 0.0
    outcomes: int = 0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def cost_per_correct_usd(self) -> Optional[float]:
        """The headline number, or None when nothing was correct (never a fake 0)."""
        return self.total_cost_usd / self.correct if self.correct else None


def replay(
    recording_path: Path,
    *,
    world_provider: Optional[trace.TracerProvider] = None,
    outcomes_provider: Optional[trace.TracerProvider] = None,
    world_meter_provider: Optional[metrics.MeterProvider] = None,
    outcomes_meter_provider: Optional[metrics.MeterProvider] = None,
) -> ReplaySummary:
    """Replay one recording through the Gradebook library.

    Providers are injectable for tests (in-memory exporter/reader) and wired to
    OTLP by `__main__.py`. `world_provider`/`world_meter_provider` carry the
    journey/decision telemetry; `outcomes_provider`/`outcomes_meter_provider`
    carry the late reality grades (ticket #7: the aggregate metrics ride the
    same two services as the events they're recorded alongside).
    """
    provider = world_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer(TRACER_NAME)

    decisions, outcomes = load_recording(recording_path)
    summary = ReplaySummary()
    refs: dict[str, DecisionRef] = {}

    for driver in _drivers_in_order(decisions):
        driver_decisions = [d for d in decisions if d.driver == driver]
        # One journey = one trace: root span per driver, one child span per
        # junction (the model-call stand-in), the Gradebook event under it.
        with tracer.start_as_current_span(f"journey {driver}"):
            for d in driver_decisions:
                with tracer.start_as_current_span(f"junction {d.junction} decision"):
                    refs[d.response_id] = capture_decision(response_id=d.response_id)
                    correct_route = d.true_fastest
                    record_decision(
                        name="route.fastest",
                        model=d.model,
                        chosen=d.chosen,
                        correct=correct_route,
                        input_tokens=d.input_tokens,
                        output_tokens=d.output_tokens,
                        decision_type="route_choice",
                        response_id=d.response_id,
                        explanation=(
                            f"chose {d.chosen} ({d.options[d.chosen]}m); "
                            f"true fastest {correct_route} ({d.options[correct_route]}m)"
                        ),
                        tracer_provider=provider,
                        meter_provider=world_meter_provider,
                    )
                    summary.decisions += 1
                    is_correct = d.chosen == correct_route
                    summary.correct += int(is_correct)
                    cost = _cost(d)
                    summary.total_cost_usd += cost
                    per_model = summary.by_model.setdefault(
                        d.model, {"decisions": 0, "correct": 0, "cost_usd": 0.0}
                    )
                    per_model["decisions"] += 1
                    per_model["correct"] += int(is_correct)
                    per_model["cost_usd"] += cost

    # The outcomes "process": late reality grades, span-linked back (T5).
    for outcome in outcomes:
        ref = refs.get(outcome.graded_response_id)
        if ref is None:
            raise ValueError(
                f"outcome for {outcome.driver} references unknown decision "
                f"{outcome.graded_response_id!r}"
            )
        record_reality_grade(
            ref,
            name="journey.on_time",
            correct=outcome.on_time,
            decision_type="route_choice",
            explanation=f"{outcome.driver} arrived {'on time' if outcome.on_time else 'late'}",
            tracer_provider=outcomes_provider or provider,
            meter_provider=outcomes_meter_provider or world_meter_provider,
        )
        summary.outcomes += 1

    return summary


def _drivers_in_order(decisions: Iterable[JunctionDecision]) -> list[str]:
    seen: list[str] = []
    for d in decisions:
        if d.driver not in seen:
            seen.append(d.driver)
    return seen


def _cost(d: JunctionDecision) -> float:
    from gradebook.pricing import price

    return price(d.model, d.input_tokens, d.output_tokens)
