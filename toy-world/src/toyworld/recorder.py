"""The recorder (ticket #33, `--live --record`): writes a replay file FROM a
real run.

The committed recording judges run cold (`python -m toyworld`, no API key) has
to come from somewhere honest. Before this ticket, `replay.py` only read a
hand-authored file - there was no path from a real live run into a replay
recording. This module closes that gap: it runs `live.run_live` exactly as
`--live` does (real model calls, real grading, real telemetry), and on top of
that ALSO captures each decision's raw fields, so the run can be replayed
later byte-for-byte from what the models actually said.

For every route_choice decision it also computes and writes a deferred
"reality" outcome row (`journey_on_time` in `world.py`): did the journey the
model's chosen route produces actually arrive on time? This is the mechanism
`replay.py` later reads to emit the late, span-linked reality grade through
the separate `toy-world-outcomes` service (docs/conventions.md section 6) -
restored here rather than dropped, now keyed by decision (`response_id`)
instead of by driver/journey, since a route_choice query already IS one whole
point-to-point journey. Only route_choice decisions get an outcome row:
eta_estimate and next_hop have no journey to arrive anywhere.

Nothing here invents an answer. Every recorded `chosen` is whatever
`ModelClient.decide` returned for a real call; the correct answer key is never
written to the file at all (see `load_recording` in `replay.py`) - it is
recomputed from `world.QUERIES_BY_ID` at replay time, the same computation
that produced the prompt in the first place. The `on_time` outcome is the same
discipline extended one step further: a pure function of the graph's own
travel times, computed here and re-derivable from the same inputs, never
hand-picked. That is the mechanism that keeps "never hand-author the
recording's answers" true even for the file this module writes.

Tested (see `tests/test_recorder.py`) against the same kind of deterministic,
duck-typed `ModelClient` fake `test_live.py` uses - no key, no spend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from opentelemetry import metrics, trace

from .live import (
    DEFAULT_ROSTER,
    LiveSummary,
    ModelClient,
    ModelDecision,
    default_pairs,
    run_live,
)
from .world import ALL_QUERIES, DECISION_TYPE_ROUTE_CHOICE, Query, journey_on_time


@dataclass(frozen=True)
class RecordedDecision:
    """One line of the written recording - everything `replay.py` needs to
    reproduce this decision without re-deriving the correct answer from
    anything other than `world.QUERIES_BY_ID` (looked up by `query_id`)."""

    decision_type: str
    query_id: str
    model: str
    chosen: object
    input_tokens: int
    output_tokens: int
    response_id: str

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "type": "decision",
                "decision_type": self.decision_type,
                "query_id": self.query_id,
                "model": self.model,
                "chosen": self.chosen,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "response_id": self.response_id,
            }
        )


@dataclass(frozen=True)
class RecordedOutcome:
    """One line of the written recording's DEFERRED reality grade - the
    journey a route_choice decision's chosen route produces, judged after the
    fact (docs/conventions.md section 6). `replay.py` reads this back by
    `graded_response_id` to span-link the late grade to the decision span it
    judges. `on_time` is computed once, here, from `journey_on_time` - never
    re-derived differently in two places."""

    graded_response_id: str
    on_time: bool
    model: str

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "type": "outcome",
                "graded_response_id": self.graded_response_id,
                "on_time": self.on_time,
                "model": self.model,
            }
        )


def record_live(
    client: ModelClient,
    *,
    budget_usd: float,
    pairs: Optional[Sequence[tuple[str, Query]]] = None,
    roster: Sequence[str] = DEFAULT_ROSTER,
    queries: Sequence[Query] = ALL_QUERIES,
    output_path: Path,
    world_provider: Optional[trace.TracerProvider] = None,
    world_meter_provider: Optional[metrics.MeterProvider] = None,
) -> LiveSummary:
    """Run live mode and write every decision to `output_path` as it happens.

    Reuses `run_live` verbatim (same grading, pricing, budget guard, telemetry)
    via its `on_decision` hook, so a recording run populates the dashboards
    exactly like an ordinary `--live` run AND leaves a replay file behind - one
    code path, not two that could drift apart. Every route_choice decision
    additionally gets a deferred reality outcome row (`RecordedOutcome`),
    computed from the same query the decision answered.
    """
    recorded: list[RecordedDecision] = []
    outcomes: list[RecordedOutcome] = []

    def _capture(
        model: str, query: Query, decision: ModelDecision, is_correct: bool, cost_usd: float
    ) -> None:
        recorded.append(
            RecordedDecision(
                decision_type=query.decision_type,
                query_id=query.query_id,
                model=model,
                chosen=decision.chosen,
                input_tokens=decision.input_tokens,
                output_tokens=decision.output_tokens,
                response_id=decision.response_id,
            )
        )
        if query.decision_type == DECISION_TYPE_ROUTE_CHOICE and query.route_options:
            chosen_time = query.route_options.get(str(decision.chosen), float("inf"))
            best_time = query.route_options[query.correct]
            outcomes.append(
                RecordedOutcome(
                    graded_response_id=decision.response_id,
                    on_time=journey_on_time(chosen_time, best_time),
                    model=model,
                )
            )

    run_pairs = pairs if pairs is not None else default_pairs(roster, queries)

    summary = run_live(
        client,
        budget_usd=budget_usd,
        pairs=run_pairs,
        world_provider=world_provider,
        world_meter_provider=world_meter_provider,
        on_decision=_capture,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        for entry in recorded:
            f.write(entry.to_json_line())
            f.write("\n")
        for outcome in outcomes:
            f.write(outcome.to_json_line())
            f.write("\n")

    return summary
