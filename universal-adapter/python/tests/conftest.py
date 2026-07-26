"""Test seam: real telemetry, real fixtures, no reaching inside the library.

Two things are wired here.

1. The same in-memory OpenTelemetry SDK the reference library's tests use, so
   emission tests assert on the EMITTED event, which is the contract, rather
   than on this package's internals.
2. The shared fixture corpus at `universal-adapter/fixtures/`, which is authored
   separately and is the same corpus the TypeScript implementation reads. The
   corpus is loaded lazily and its absence skips rather than fails, so this
   suite stays green whether or not the corpus is present.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

# The package under test lives beside this directory and is normally installed
# with `pip install -e universal-adapter/python[test]`. Adding it to the path
# keeps the suite runnable straight from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # pragma: no cover - import guard, exercised only when misinstalled
    import gradebook  # noqa: F401
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "gradebook is this repo's reference library, not the unrelated PyPI "
        "project of the same name. Install both in one invocation:\n"
        "  pip install -e reference-library -e universal-adapter/python[test]"
    ) from exc

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "universal-adapter" / "schemas"
FIXTURE_DIR = REPO_ROOT / "universal-adapter" / "fixtures"
FIXTURE_INDEX = FIXTURE_DIR / "index.json"

SCHEMA_FILES = {
    "decision-evidence-bundle": "decision-evidence-bundle.schema.json",
    "usage-record": "usage-record.schema.json",
    "evaluation-manifest": "evaluation-manifest.schema.json",
    "outcome-record": "outcome-record.schema.json",
}


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


# --------------------------------------------------------------------------
# The shared fixture corpus
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureCase:
    """One corpus entry, already read off disk."""

    name: str
    schema: Optional[str]
    expect: str
    documents: tuple[Any, ...]
    note: str

    @property
    def should_validate(self) -> bool:
        """`not_validated` cases are raw harness input, not protocol records."""
        return self.expect in ("valid", "invalid") and self.schema is not None

    @property
    def expects_valid(self) -> bool:
        return self.expect == "valid"


def load_fixture_cases() -> list[FixtureCase]:
    """Read `fixtures/index.json`, or return an empty list if it is not there."""
    if not FIXTURE_INDEX.exists():
        return []
    index = json.loads(FIXTURE_INDEX.read_text(encoding="utf-8"))
    cases: list[FixtureCase] = []
    for entry in index["cases"]:
        path = FIXTURE_DIR / entry["file"]
        if not path.exists():
            # An index row whose file is missing is a corpus bug, and a silent
            # skip would hide it behind a green suite.
            raise AssertionError(
                f"fixture index lists {entry['file']!r} but the file does not "
                f"exist at {path}"
            )
        document = json.loads(path.read_text(encoding="utf-8"))
        container = entry.get("container", "single")
        if container == "array":
            if not isinstance(document, list):
                raise AssertionError(
                    f"fixture {entry['file']!r} is indexed as container 'array' "
                    f"but holds a {type(document).__name__}"
                )
            documents = tuple(document)
        elif container == "single":
            documents = (document,)
        else:
            raise AssertionError(
                f"fixture {entry['file']!r} declares unknown container "
                f"{container!r}; this test knows 'single' and 'array'"
            )
        cases.append(FixtureCase(
            name=entry["file"],
            schema=entry.get("schema"),
            expect=entry.get("expect", "valid"),
            documents=documents,
            note=entry.get("note", ""),
        ))
    return cases


def require_fixture_cases() -> list[FixtureCase]:
    """Corpus cases, or a clean skip explaining exactly what is missing."""
    cases = load_fixture_cases()
    if not cases:
        pytest.skip(
            f"fixture corpus not present yet ({FIXTURE_INDEX} is missing); the "
            "corpus is authored separately and shared with the TypeScript "
            "implementation"
        )
    return cases


def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / SCHEMA_FILES[name]
    return json.loads(path.read_text(encoding="utf-8"))
