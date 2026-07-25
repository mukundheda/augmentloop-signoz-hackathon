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

# `gradebook` is also a real, unrelated project on PyPI. Installing toy-world
# without `-e reference-library` in the SAME pip invocation resolves against
# that stranger's package, and every test module then dies at collection with
# `ImportError: cannot import name 'DecisionRef' from 'gradebook'` - four
# opaque tracebacks that read like our code is broken. Name the real fix
# instead (ticket #30).
_WRONG_GRADEBOOK_HINT = (
    "The installed `gradebook` is not this repo's reference library - "
    "`gradebook` is also an unrelated project on PyPI, and installing "
    "toy-world on its own resolves to that one.\n"
    "Fix, from the repo root:\n"
    "    pip uninstall -y gradebook\n"
    "    pip install -e reference-library -e 'toy-world[test]'\n"
    "Both packages must be named in the SAME pip invocation."
)


def pytest_collection(session):
    try:
        import gradebook
    except ImportError as exc:
        raise pytest.UsageError(
            f"`gradebook` is not installed.\n{_WRONG_GRADEBOOK_HINT}"
        ) from exc

    if not hasattr(gradebook, "record_decision"):
        where = getattr(gradebook, "__file__", None) or "an unknown location"
        raise pytest.UsageError(
            f"`gradebook` imported from {where} but has no `record_decision`.\n"
            f"{_WRONG_GRADEBOOK_HINT}"
        )


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
