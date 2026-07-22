"""Test seam: capture the telemetry Gradebook emits, without reaching inside it.

Every test asserts on the *emitted event* (the contract), never on library
internals. We wire a fresh SDK `TracerProvider` with an in-memory exporter and
inject it into `record_decision`, so each test observes exactly the spans that
would go to SigNoz.
"""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def tracer_provider(exporter: InMemorySpanExporter) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider
