"""Test seam, mirroring reference-library/tests: assert on emitted telemetry.

Ticket #33 dropped the separate `toy-world-outcomes` service (the journey/
reality-grade demo was scoped out of this ticket - see the PR description) so
there is now one provider+exporter pair, `world`, matching what `replay.py`
and `live.py` both emit through.
"""

from pathlib import Path

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

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
def world_metrics():
    return _metric_pair()


@pytest.fixture
def recording_path() -> Path:
    return RECORDING
