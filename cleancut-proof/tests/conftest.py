"""Test seam, mirroring the other packages: assert on emitted telemetry only."""

from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _pair() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


@pytest.fixture
def proof():
    return _pair()


@pytest.fixture
def outcomes():
    return _pair()


@pytest.fixture
def sample_transcript() -> str:
    return (SAMPLES / "sample_transcript.txt").read_text(encoding="utf-8")


@pytest.fixture
def sample_clips_csv() -> Path:
    return SAMPLES / "sample_clips.csv"
