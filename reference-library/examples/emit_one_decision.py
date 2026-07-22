"""Emit one real graded decision to the live SigNoz stack.

The walking skeleton's end-to-end proof and the wiring the toy world reuses:
configure an OpenTelemetry SDK provider with the OTLP/HTTP exporter, point it at
the Foundry SigNoz stack, and record one math-graded decision. Then find it in
SigNoz by the trace id this prints.

Run (stack must be up, from reference-library/):
    pip install -e ".[live]"
    python examples/emit_one_decision.py

Endpoint defaults to http://localhost:4318 (Foundry SigNoz OTLP/HTTP); override
with OTEL_EXPORTER_OTLP_ENDPOINT.
"""

import os

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from gradebook import record_decision

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")


def main() -> None:
    provider = TracerProvider(
        resource=Resource.create({"service.name": "gradebook-example"})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces"))
    )

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="B",
        correct="A",
        input_tokens=180,
        output_tokens=12,
        decision_type="route_choice",
        response_id="example-resp-0001",
        explanation="chose route B; the true fastest was A",
        tracer_provider=provider,
    )

    # Flush before exit so the batch actually leaves the process.
    provider.force_flush()
    provider.shutdown()
    print(f"Emitted one gen_ai.evaluation.result to {ENDPOINT} "
          f"(service.name=gradebook-example). Find it in SigNoz Traces.")


if __name__ == "__main__":
    main()
