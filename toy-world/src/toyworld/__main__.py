"""One command for the judge: `python -m toyworld` (spec user story 12).

Replays the committed recording through the Gradebook library and exports the
resulting spans to the Foundry SigNoz stack over OTLP/HTTP. Two logical
services are emitted - `toy-world` (journeys + decisions) and
`toy-world-outcomes` (the late reality grades) - so both appear in SigNoz and
the deferred grade demonstrably crosses a service boundary.

Endpoint defaults to http://localhost:4318; override with
OTEL_EXPORTER_OTLP_ENDPOINT. The run also prints a summary so the numbers can
be eyeballed against the dashboards.
"""

from __future__ import annotations

import os
from pathlib import Path

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .replay import replay

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
RECORDING = Path(__file__).resolve().parents[2] / "recordings" / "replay-v1.jsonl"


def _provider(service_name: str) -> TracerProvider:
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces"))
    )
    return provider


def main() -> None:
    world = _provider("toy-world")
    outcomes = _provider("toy-world-outcomes")

    summary = replay(RECORDING, world_provider=world, outcomes_provider=outcomes)

    for provider in (world, outcomes):
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
    print("per model:")
    for model, row in summary.by_model.items():
        print(
            f"  {model}: {row['correct']:.0f}/{row['decisions']:.0f} correct, "
            f"${row['cost_usd']:.6f}"
        )
    print("Open SigNoz -> Traces: filter service.name=toy-world for the journey")
    print("waterfalls; the late journey.on_time grades under toy-world-outcomes")
    print("span-link back to the decisions they judge.")


if __name__ == "__main__":
    main()
