"""Reality grades from a signal that is not ours: the OS process exit code.

An agent decides a shell command; whether that command *worked* is a real-world
outcome the OS already reports as an exit code - `subprocess.run(...).returncode
== 0`. No ground truth, no comparison, **no checker**: the exit code is the
verdict. This is the ticket #43 rebuttal made concrete against a pre-existing,
external signal (Python's stdlib `subprocess`), not one invented for the demo.

The whole Gradebook integration is the three `# gradebook` lines below - a
decorator, an `observe` call, and the provider wiring. `run_command` is an
ordinary command runner that already returns whether the command succeeded;
Gradebook records a reality grade from that existing boolean.

Run (SigNoz stack up):
    pip install -e reference-library[live]   # only for the OTLP exporter
    python reference-library/examples/reality_from_exit_code.py
Then find the `gen_ai.evaluation.result` events (service `agent-shell`) in
SigNoz Traces - grade.source=reality, one per command, no checker in this file.
"""

from __future__ import annotations

import os
import subprocess

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from gradebook import RealitySignal

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

signal = RealitySignal("command.succeeded", decision_type="shell_command")  # gradebook


@signal.on_outcome                                                          # gradebook
def run_command(step_id: str, command: str) -> bool:
    """An existing command runner that already returns whether it worked."""
    return subprocess.run(command, shell=True).returncode == 0


def main() -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": "agent-shell"}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces"))
    )
    signal.use_providers(tracer_provider=provider)  # tests inject their own

    tracer = provider.get_tracer("agent-shell")
    plan = [
        ("step-1", "python --version"),   # the agent's chosen commands
        ("step-2", "definitely-not-a-real-command --nope"),
    ]
    for step_id, command in plan:
        with tracer.start_as_current_span(f"agent decides: {command}"):
            signal.observe(step_id, response_id=step_id)                    # gradebook
        run_command(step_id, command)  # the existing call site, unchanged

    provider.force_flush()
    provider.shutdown()
    print(f"Recorded reality grades for {len(plan)} commands -> {ENDPOINT} "
          "(service agent-shell). No checker was written.")


if __name__ == "__main__":
    main()
