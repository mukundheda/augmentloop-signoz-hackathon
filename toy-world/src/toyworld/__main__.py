"""One command for the judge: `python -m toyworld` (spec user story 12).

Replays the committed recording through the Gradebook library and exports the
resulting spans to the Foundry SigNoz stack over OTLP/HTTP. Two logical
services are emitted - `toy-world` (the decisions) and `toy-world-outcomes`
(the late, route_choice-only reality grades) - so both appear in SigNoz and
the deferred grade demonstrably crosses a service boundary. Three decision
types run (ticket #33: route_choice, eta_estimate, next_hop) over the
20-junction graph in `world.py`.

`python -m toyworld --live` (ticket #9) instead runs every roster model over
every query through real model calls, under a per-run budget cap (`--budget`,
default $0.50), to populate the model-vs-model comparison. `--provider
openrouter` (the default) needs `OPENROUTER_API_KEY`. `--provider direct` is a
TEMPORARY stopgap for while OpenRouter credits are provisioned: it reaches
Anthropic natively (`ANTHROPIC_API_KEY`) and Gemini via its OpenAI-compatible
endpoint (`GEMINI_API_KEY`) instead. Either way, live mode needs the `[live]`
extra; replay needs neither.

`python -m toyworld --live --record` (ticket #33) additionally writes every
decision to a replay file (`--output`, default `recordings/replay-v2.jsonl`)
as it happens - the mechanism that lets a real run become the next committed
recording, instead of a hand-authored one. See `recorder.py`'s docstring.

Endpoint defaults to http://localhost:4318; override with
OTEL_EXPORTER_OTLP_ENDPOINT. The run also prints a summary - overall, by
model, and by (model, decision type) - so the numbers can be eyeballed against
the dashboards.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from gradebook.logs import LOGGER_NAME
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .replay import replay
from .routing import DEFAULT_ROUTING_PATH

if TYPE_CHECKING:
    from .direct import DirectClient
    from .openrouter import OpenRouterClient

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
RECORDING = Path(__file__).resolve().parents[2] / "recordings" / "replay-v2.jsonl"


def _tracer_provider(resource: Resource) -> TracerProvider:
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces"))
    )
    return provider


def _meter_provider(resource: Resource) -> MeterProvider:
    # Short export interval: a one-shot replay needs its data points to leave
    # the process on force_flush, not wait out the default 60s period.
    return MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{ENDPOINT}/v1/metrics"),
                export_interval_millis=1_000,
            )
        ],
    )


def _logger_provider(resource: Resource) -> LoggerProvider:
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{ENDPOINT}/v1/logs"))
    )
    return provider


def _install_log_bridge(provider: LoggerProvider) -> LoggingHandler:
    """Route gradebook's failure logs (conventions §13) to SigNoz over OTLP.

    Attaches the SDK LoggingHandler to the "gradebook" logger, so a failure log
    emitted while a decision span is current carries that span's trace/span id
    automatically - click the log in SigNoz, land on the decision span.
    """
    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    logging.getLogger(LOGGER_NAME).addHandler(handler)
    return handler


def _remove_log_bridge(provider: LoggerProvider, handler: LoggingHandler) -> None:
    logging.getLogger(LOGGER_NAME).removeHandler(handler)
    provider.force_flush()
    provider.shutdown()


def _print_per_model(by_model: dict) -> None:
    print("per model:")
    for model, row in by_model.items():
        print(
            f"  {model}: {row['correct']:.0f}/{row['decisions']:.0f} correct, "
            f"${row['cost_usd']:.6f}"
        )


def _print_per_model_type(by_model_type: dict) -> None:
    print("per model x decision type:")
    for (model, decision_type), row in sorted(by_model_type.items()):
        print(
            f"  {model} / {decision_type}: "
            f"{row['correct']:.0f}/{row['decisions']:.0f} correct, "
            f"${row['cost_usd']:.6f}"
        )


def _run_replay() -> None:
    world_resource = Resource.create({"service.name": "toy-world"})
    outcomes_resource = Resource.create({"service.name": "toy-world-outcomes"})

    world = _tracer_provider(world_resource)
    outcomes = _tracer_provider(outcomes_resource)
    world_meters = _meter_provider(world_resource)
    outcomes_meters = _meter_provider(outcomes_resource)
    world_logs = _logger_provider(world_resource)
    log_handler = _install_log_bridge(world_logs)

    summary = replay(
        RECORDING,
        world_provider=world,
        outcomes_provider=outcomes,
        world_meter_provider=world_meters,
        outcomes_meter_provider=outcomes_meters,
    )

    for provider in (world, outcomes, world_meters, outcomes_meters):
        provider.force_flush()
        provider.shutdown()
    _remove_log_bridge(world_logs, log_handler)

    print(f"Replayed {RECORDING.name} -> {ENDPOINT}")
    print(
        f"decisions={summary.decisions}  correct={summary.correct}  "
        f"reality_outcomes={summary.outcomes}  "
        f"total_cost=${summary.total_cost_usd:.6f}"
    )
    if summary.cost_per_correct_usd is not None:
        print(f"cost per correct decision: ${summary.cost_per_correct_usd:.6f}")
    _print_per_model(summary.by_model)
    _print_per_model_type(summary.by_model_type)
    print("Open SigNoz -> Traces: filter service.name=toy-world; each model is one")
    print("trace, each query one span carrying augmentloop.decision.type and")
    print("augmentloop.decision.difficulty. The late journey.on_time grades under")
    print("service.name=toy-world-outcomes span-link back to the route_choice")
    print("decisions they judge.")


def _make_client(provider: str) -> "OpenRouterClient | DirectClient":
    # Imported here so replay never needs the [live] extra, an API key, or
    # either provider SDK.
    if provider == "direct":
        from .direct import DirectClient

        return DirectClient()
    from .openrouter import OpenRouterClient

    return OpenRouterClient()


def _production_pairs(routing_path: Path):
    """Every query, routed to whichever model the committed table currently
    assigns to ITS decision type (ticket #33: three types can each be routed
    independently, not one model for the whole run)."""
    from .routing import load_routing, routed_model
    from .world import ALL_QUERIES

    routing = load_routing(routing_path)
    pairs = [(routed_model(routing, q.decision_type), q) for q in ALL_QUERIES]
    for decision_type, model in sorted(routing.items()):
        print(f"Production routing ({routing_path.name}): {decision_type} -> {model}")
    return pairs


def _run_live(
    budget_usd: float,
    provider: str,
    routing_path: Optional[Path],
    record: bool,
    output_path: Path,
) -> None:
    from .live import run_live
    from .recorder import record_live

    resource = Resource.create({"service.name": "toy-world"})
    world = _tracer_provider(resource)
    world_meters = _meter_provider(resource)
    world_logs = _logger_provider(resource)
    log_handler = _install_log_bridge(world_logs)

    # Comparison mode (pairs=None -> the full roster x query cross-product) is
    # what produces the cost-per-correct-by-model-by-type evidence the
    # right-sizing proposal reads. Production mode (ticket #10, extended by
    # #33) instead runs only the model the committed routing table currently
    # assigns to EACH decision type, so a run before and a run after an
    # approved reroute are directly comparable.
    pairs = _production_pairs(routing_path) if routing_path is not None else None

    if record:
        summary = record_live(
            _make_client(provider),
            budget_usd=budget_usd,
            pairs=pairs,
            output_path=output_path,
            world_provider=world,
            world_meter_provider=world_meters,
        )
    else:
        summary = run_live(
            _make_client(provider),
            budget_usd=budget_usd,
            pairs=pairs,
            world_provider=world,
            world_meter_provider=world_meters,
        )

    for telemetry_provider in (world, world_meters):
        telemetry_provider.force_flush()
        telemetry_provider.shutdown()
    _remove_log_bridge(world_logs, log_handler)

    print(f"Live run (budget ${budget_usd:.2f}) -> {ENDPOINT}")
    print(
        f"decisions={summary.decisions}  correct={summary.correct}  "
        f"total_cost=${summary.total_cost_usd:.6f}"
        + ("  [BUDGET CAP HIT]" if summary.budget_exhausted else "")
    )
    if summary.cost_per_correct_usd is not None:
        print(f"cost per correct decision: ${summary.cost_per_correct_usd:.6f}")
    _print_per_model(summary.by_model)
    _print_per_model_type(summary.by_model_type)
    if record:
        print(f"Recorded {summary.decisions} decisions -> {output_path}")
    print("Open SigNoz -> Traces: filter service.name=toy-world; each model is one")
    print("trace. The cost-per-correct-by-model-by-type panel is the right-sizing")
    print("evidence.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="toyworld")
    parser.add_argument(
        "--live",
        action="store_true",
        help="run real OpenRouter model calls (needs OPENROUTER_API_KEY) instead "
        "of the deterministic committed replay",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=0.50,
        help="per-run budget cap in USD for --live (default: 0.50)",
    )
    parser.add_argument(
        "--provider",
        choices=("openrouter", "direct"),
        default="openrouter",
        help="live-mode model client (default: openrouter, needs "
        "OPENROUTER_API_KEY). 'direct' is a TEMPORARY stopgap while OpenRouter "
        "credits are provisioned: native Anthropic (ANTHROPIC_API_KEY) + "
        "Gemini's OpenAI-compatible endpoint (GEMINI_API_KEY)",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="run only the models the committed routing table assigns to each "
        "decision type, instead of the whole comparison roster (ticket #10). "
        "Use this for the before/after either side of an approved reroute",
    )
    parser.add_argument(
        "--routing",
        type=Path,
        default=DEFAULT_ROUTING_PATH,
        metavar="PATH",
        help=f"routing table for --production (default: {DEFAULT_ROUTING_PATH.name} "
        "beside the package, which is the committed table the approval step edits)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="write every --live decision to --output as a replay recording "
        "(ticket #33). Needs --live; the recording is what a future "
        "`python -m toyworld` (no flags) replays",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RECORDING,
        metavar="PATH",
        help=f"where --record writes the recording (default: {RECORDING})",
    )
    args = parser.parse_args()

    if args.production and not args.live:
        parser.error(
            "--production selects WHICH model serves real traffic, so it needs "
            "--live. Replay has no routing to apply: it re-prices a recording "
            "whose models are already fixed."
        )

    if args.record and not args.live:
        parser.error(
            "--record captures a real run into a replay file, so it needs "
            "--live. Replay has nothing new to capture: it already reads a "
            "recording."
        )

    if args.live:
        _run_live(
            args.budget,
            args.provider,
            routing_path=args.routing if args.production else None,
            record=args.record,
            output_path=args.output,
        )
    else:
        _run_replay()


if __name__ == "__main__":
    main()
