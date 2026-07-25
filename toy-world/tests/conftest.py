"""Test seam, mirroring reference-library/tests: assert on emitted telemetry.

Two independent provider+exporter pairs so tests can tell the decision spans
(`toy-world`) apart from the late reality grades (`toy-world-outcomes`),
exactly as `python -m toyworld` wires them.
"""

import logging
from pathlib import Path

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

RECORDING = Path(__file__).resolve().parents[1] / "recordings" / "replay-v1.jsonl"


def _pair() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _metric_pair() -> tuple[MeterProvider, InMemoryMetricReader]:
    reader = InMemoryMetricReader()
    return MeterProvider(metric_readers=[reader]), reader


@pytest.fixture
def world():
    return _pair()


@pytest.fixture
def outcomes():
    return _pair()


@pytest.fixture
def world_metrics():
    return _metric_pair()


@pytest.fixture
def outcomes_metrics():
    return _metric_pair()


@pytest.fixture
def recording_path() -> Path:
    return RECORDING


@pytest.fixture
def gradebook_log_bridge():
    """Capture gradebook's failure logs, as `python -m toyworld` routes them.

    Mirrors reference-library/tests: the SDK LoggingHandler on the "gradebook"
    logger against an in-memory exporter, so a budget-guard trip (conventions
    §13) can be asserted on as an emitted log record with the model-run span's
    trace/span id stamped automatically. Yields the exporter.
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
