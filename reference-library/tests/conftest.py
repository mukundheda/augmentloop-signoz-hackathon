"""Test seam: capture the telemetry Gradebook emits, without reaching inside it.

Every test asserts on the *emitted event* (the contract), never on library
internals. We wire a fresh SDK `TracerProvider` with an in-memory exporter and
inject it into `record_decision`, so each test observes exactly the spans that
would go to SigNoz.
"""

import logging

import pytest
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from gradebook.logs import LOGGER_NAME


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def tracer_provider(exporter: InMemorySpanExporter) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


@pytest.fixture
def metric_reader() -> InMemoryMetricReader:
    return InMemoryMetricReader()


@pytest.fixture
def meter_provider(metric_reader: InMemoryMetricReader) -> MeterProvider:
    return MeterProvider(metric_readers=[metric_reader])


@pytest.fixture
def gradebook_log_bridge():
    """Capture gradebook's failure logs, exactly as the application routes them.

    Attaches the SDK LoggingHandler to the "gradebook" logger against an
    in-memory exporter - the same bridge `python -m toyworld` installs against
    OTLP - so tests assert on the *emitted log record* (its failure class, its
    structured attributes, and the trace/span id the bridge stamps from the
    current span), never on library internals. Yields the exporter.
    """
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    try:
        yield exporter
    finally:
        logger.removeHandler(handler)
        provider.shutdown()
