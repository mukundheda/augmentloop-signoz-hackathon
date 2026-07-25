"""One command for the judge: `python -m toyworld` (spec user story 12).

Replays the committed recording through the Gradebook library and exports the
resulting spans to the Foundry SigNoz stack over OTLP/HTTP. Two logical
services are emitted - `toy-world` (journeys + decisions) and
`toy-world-outcomes` (the late reality grades) - so both appear in SigNoz and
the deferred grade demonstrably crosses a service boundary.

`python -m toyworld --live` (ticket #9) instead runs every roster model over
the same junctions through real model calls, under a per-run budget cap
(`--budget`, default $0.50), to populate the model-vs-model comparison.
`--provider openrouter` (the default) needs `OPENROUTER_API_KEY`.
`--provider direct` is a TEMPORARY stopgap for while OpenRouter credits are
provisioned: it reaches Anthropic natively (`ANTHROPIC_API_KEY`) and Gemini via
its OpenAI-compatible endpoint (`GEMINI_API_KEY`) instead. Either way, live
mode needs the `[live]` extra; replay needs neither.

Endpoint defaults to http://localhost:4318; override with
OTEL_EXPORTER_OTLP_ENDPOINT. The run also prints a summary so the numbers can
be eyeballed against the dashboards.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .replay import replay

if TYPE_CHECKING:
    from .direct import DirectClient
    from .openrouter import OpenRouterClient

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
RECORDING = Path(__file__).resolve().parents[2] / "recordings" / "replay-v1.jsonl"


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


def _print_per_model(by_model: dict) -> None:
    print("per model:")
    for model, row in by_model.items():
        print(
            f"  {model}: {row['correct']:.0f}/{row['decisions']:.0f} correct, "
            f"${row['cost_usd']:.6f}"
        )


def _run_replay() -> None:
    world_resource = Resource.create({"service.name": "toy-world"})
    outcomes_resource = Resource.create({"service.name": "toy-world-outcomes"})

    world = _tracer_provider(world_resource)
    outcomes = _tracer_provider(outcomes_resource)
    world_meters = _meter_provider(world_resource)
    outcomes_meters = _meter_provider(outcomes_resource)

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

    print(f"Replayed {RECORDING.name} -> {ENDPOINT}")
    print(
        f"decisions={summary.decisions}  correct={summary.correct}  "
        f"reality_outcomes={summary.outcomes}  "
        f"total_cost=${summary.total_cost_usd:.6f}"
    )
    if summary.cost_per_correct_usd is not None:
        print(f"cost per correct decision: ${summary.cost_per_correct_usd:.6f}")
    _print_per_model(summary.by_model)
    print("Open SigNoz -> Traces: filter service.name=toy-world for the journey")
    print("waterfalls; the late journey.on_time grades under toy-world-outcomes")
    print("span-link back to the decisions they judge.")


def _make_client(provider: str) -> "OpenRouterClient | DirectClient":
    # Imported here so replay never needs the [live] extra, an API key, or
    # either provider SDK.
    if provider == "direct":
        from .direct import DirectClient

        return DirectClient()
    from .openrouter import OpenRouterClient

    return OpenRouterClient()


def _run_live(budget_usd: float, provider: str) -> None:
    from .live import run_live

    world_resource = Resource.create({"service.name": "toy-world"})
    world = _tracer_provider(world_resource)
    world_meters = _meter_provider(world_resource)

    summary = run_live(
        _make_client(provider),
        budget_usd=budget_usd,
        world_provider=world,
        world_meter_provider=world_meters,
    )

    for telemetry_provider in (world, world_meters):
        telemetry_provider.force_flush()
        telemetry_provider.shutdown()

    print(f"Live run (budget ${budget_usd:.2f}) -> {ENDPOINT}")
    print(
        f"decisions={summary.decisions}  correct={summary.correct}  "
        f"total_cost=${summary.total_cost_usd:.6f}"
        + ("  [BUDGET CAP HIT]" if summary.budget_exhausted else "")
    )
    if summary.cost_per_correct_usd is not None:
        print(f"cost per correct decision: ${summary.cost_per_correct_usd:.6f}")
    _print_per_model(summary.by_model)
    print("Open SigNoz -> Traces: filter service.name=toy-world; each model is one")
    print("trace. The cost-per-correct-by-model panel is the right-sizing evidence.")


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
    args = parser.parse_args()

    if args.live:
        _run_live(args.budget, args.provider)
    else:
        _run_replay()


if __name__ == "__main__":
    main()
