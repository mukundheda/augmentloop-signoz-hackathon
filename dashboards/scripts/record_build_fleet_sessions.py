"""Ticket #13 (T10): grade our own build agents.

The third proof surface. Same Gradebook methodology the toy-world dashboard
(#7) applies to simulated model decisions - applied instead to *our own*
Claude Code build-agent sessions in this repo. One decision = one ticket's
Claude Code session (per team convention, one ticket = one branch = one PR).
The reality grade is: did it ship correctly, per this repo's own definition of
done (CLAUDE.md: "A ticket is done when /spec-review passes both axes and the
full test suite is green")? A merged PR is a fact that gate was cleared;
`correct=True` records that fact, not a re-derivation of it.

Uses the existing reference-library recorder (`capture_decision` +
`record_reality_grade`), the existing `gen_ai.evaluation.result` event and
`augmentloop.grade.source`/`augmentloop.cost.usd` extensions, and the existing
`gradebook.decisions.graded` / `gradebook.decision.cost.usd` metrics (T4,
ticket #7). No new schema.

## Honest scope (read before extending this list)

This repo has four humans (Mukund, Vedant, Rutik, Anish) plus their agent
sessions. As of this ticket, only Mukund's own Claude Code sessions are
landing `claude_code.*` telemetry in the live SigNoz stack - Rutik's tunnel
died 2026-07-19 with nothing since, and Vedant/Anish have zero samples, never
connected. This script's real, honest scope is Mukund's own build-agent
telemetry. It is NOT a genuine "team fleet" view yet - a known, accepted
limitation, not something this ticket set out to solve.

## Why historical tickets carry no cost figure (verified, not an oversight)

`claude_code.*` metrics carry no repository, workspace, or cwd attribute
anywhere in their labels (verified against the live schema: `attrs`,
`scope_attrs`, and `resource_attrs` on `claude_code.cost.usage` /
`claude_code.token.usage` in `signoz_metrics.time_series_v4` - exhaustively
listed, no such key). Claude Code telemetry is per-account, not per-project:
a day's `claude_code.cost.usage` sum for Mukund's account blends every
project he worked on that day (this hackathon plus other unrelated work),
with no way to separate them from the metric alone.
Attributing a historical PR's cost from wall-clock windows around its commits
was tried and rejected: this repo's PRs are frequently on stacked branches
worked concurrently (see PR #21's body: "Stacked on `6-toy-world`"), so
commit-time windows for different tickets overlap and a window-based split
would silently double-count or misattribute real dollars. Rather than
fabricate a number dressed as precise, historical tickets below are recorded
correct (a verifiable fact: they merged, which this repo's process gates on
spec-review + green tests) with NO cost attribute - exactly the "never
emit a fabricated cost" discipline the conventions doc already requires
(Section 3.2), just applied to a gap this ticket found rather than one #7
already knew about.

The one exception is the current ticket's own session (#13, this file's
authoring session): its `session.id` is directly knowable (it is the session
running this work), so its real cost is queryable from
`claude_code.cost.usage` filtered to that exact `session.id` - genuinely
attributable, not window-guessed. See `--current-session-id` /
`--current-session-cost` below.

## Running this

From `dashboards/scripts/`, against a running Foundry SigNoz stack (OTLP/HTTP
on `localhost:4318` by default; override with `OTEL_EXPORTER_OTLP_ENDPOINT`):

    pip install -e ../../reference-library[live]
    python record_build_fleet_sessions.py
    python record_build_fleet_sessions.py \\
        --current-session-id 08499cc0-07e5-46c1-be37-dbd5394bb355 \\
        --current-session-cost 1.2345 \\
        --current-session-model claude-sonnet-5

Re-running re-emits the same historical batch (idempotent in effect, not in
telemetry - each run adds another identical batch, same caveat toy-world's
replay carries).
"""

from __future__ import annotations

import argparse
import os

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from gradebook import capture_decision, record_reality_grade

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
EVAL_NAME = "build_agent.ticket_shipped"
DECISION_TYPE = "build_session"

# Every merged PR in this repo as of ticket #13 (2026-07-25). Each is one
# ticket's Claude Code build-agent session, graded correct because it cleared
# this repo's own definition of done (CLAUDE.md: /spec-review both axes +
# full green test suite) before merge. No cost attribute - see module
# docstring "Why historical tickets carry no cost figure".
HISTORICAL_MERGED_TICKETS = [
    {"number": 17, "issue": 4, "title": "docs: gradebook conventions - the recording contract"},
    {"number": 18, "issue": 5, "title": "feat(reference-library): record one math-graded decision"},
    {"number": 19, "issue": 8, "title": "feat(reference-library): reality grade source + span-link Role 1"},
    {"number": 20, "issue": 6, "title": "feat(toy-world): replay-mode demo harness"},
    {"number": 21, "issue": 7, "title": "T4: Cost-per-correct dashboard + spend-spike + grade-quality alerts"},
    {"number": 22, "issue": 12, "title": "T9: Windows reproducibility + judge-run packaging"},
    {"number": 24, "issue": 9, "title": "feat(toy-world): live mode - real model calls under a budget cap"},
    {"number": 25, "issue": None, "title": "fix: apply #22's 3 owner-decision findings"},
    {"number": 23, "issue": 11, "title": "feat(cleancut-proof): CleanCut real-substrate proof harness"},
]


def _build_providers() -> tuple[TracerProvider, MeterProvider]:
    resource = Resource.create({"service.name": "build-fleet-gradebook"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces"))
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{ENDPOINT}/v1/metrics"),
                export_interval_millis=1_000,
            )
        ],
    )
    return tracer_provider, meter_provider


def _record_ticket(
    *,
    tracer_provider: TracerProvider,
    meter_provider: MeterProvider,
    response_id: str,
    explanation: str,
    cost_usd: float | None = None,
    model: str | None = None,
) -> None:
    tracer = tracer_provider.get_tracer("build-fleet-gradebook")
    # The decision span: the ticket's Claude Code build-agent session. There is
    # no single model-call span to parent to (a ticket's session is many turns
    # and often many model calls) - this span IS the decision, matching the
    # ticket framing literally ("each ticket's Claude Code session is a
    # decision").
    with tracer.start_as_current_span("build_agent.session"):
        ref = capture_decision(response_id=response_id)

    record_reality_grade(
        ref,
        name=EVAL_NAME,
        correct=True,
        decision_type=DECISION_TYPE,
        explanation=explanation,
        cost_usd=cost_usd,
        model=model,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--current-session-id",
        default=None,
        help="This ticket's own Claude Code session.id (real cost is directly "
        "queryable for this one, unlike the historical backfill).",
    )
    parser.add_argument(
        "--current-session-cost",
        type=float,
        default=None,
        help="Real dollar figure for --current-session-id, from "
        "claude_code.cost.usage filtered to that exact session.id.",
    )
    parser.add_argument(
        "--current-session-model",
        default="claude-sonnet-5",
        help="Primary model for the current session (recommended field only).",
    )
    args = parser.parse_args()

    tracer_provider, meter_provider = _build_providers()

    for ticket in HISTORICAL_MERGED_TICKETS:
        issue_ref = f"#{ticket['issue']}" if ticket["issue"] is not None else "no linked issue"
        _record_ticket(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            response_id=f"pr-{ticket['number']}",
            explanation=(
                f"PR #{ticket['number']} ({issue_ref}): {ticket['title']} - merged, "
                "meaning this repo's process gate (spec-review both axes + green "
                "test suite, CLAUDE.md) already passed. No cost attribute: "
                "claude_code.* telemetry carries no repo/project scope, so a "
                "per-ticket dollar figure here would be a guess dressed as "
                "precision, not a fact (see module docstring)."
            ),
        )

    if args.current_session_id is not None:
        if args.current_session_cost is None:
            parser.error("--current-session-cost is required with --current-session-id")
        _record_ticket(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            response_id=f"session-{args.current_session_id}",
            explanation=(
                "T10 (#13): this ticket's own Claude Code session. Correct "
                "because it shipped a reviewed, green-tests PR (this repo's "
                "definition of done) - the first genuinely session-attributed "
                f"cost in this dataset: claude_code.cost.usage summed for "
                f"session.id={args.current_session_id} directly, not a "
                "window guess."
            ),
            cost_usd=args.current_session_cost,
            model=args.current_session_model,
        )

    tracer_provider.force_flush()
    tracer_provider.shutdown()
    meter_provider.force_flush()
    meter_provider.shutdown()

    n = len(HISTORICAL_MERGED_TICKETS) + (1 if args.current_session_id else 0)
    print(
        f"Emitted {n} build-agent decision(s) + reality grade(s) to {ENDPOINT} "
        f"(service.name=build-fleet-gradebook). "
        f"{len(HISTORICAL_MERGED_TICKETS)} historical (no cost - see docstring)"
        + (", 1 current-session (real cost)." if args.current_session_id else ".")
    )


if __name__ == "__main__":
    main()
