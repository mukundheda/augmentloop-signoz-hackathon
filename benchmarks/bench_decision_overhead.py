"""Microbenchmark: per-decision overhead of gradebook's OTel instrumentation.

Times `record_decision` (reference-library/src/gradebook/recorder.py) - the
decision+grade emission path that turns one AI decision into a standard
`gen_ai.evaluation.result` OTel span plus two OTel metrics
(reference-library/src/gradebook/metrics.py) - under three telemetry wiring
configurations:

  1. noop          OTel API no-op providers (`trace.NoOpTracerProvider` +
                    `metrics.NoOpMeterProvider`). The exact same
                    `record_decision()` code path runs (math grading, pricing
                    lookup, `set_attribute` calls, counter/histogram calls) but
                    every OTel API call is a no-op with no SDK behind it. This
                    is "instrumentation disabled": it isolates
                    `record_decision`'s own Python-level cost (grading +
                    pricing + attribute plumbing) from any OTel SDK cost.

  2. sdk-inmemory  A real OTel SDK `TracerProvider` + `MeterProvider`, wired to
                   an in-memory exporter/reader (`SimpleSpanProcessor` +
                   `InMemorySpanExporter`, `InMemoryMetricReader`) - the exact
                   fixture pattern reference-library/tests/conftest.py uses.
                   This is the fair "instrumentation ON" number: real SDK
                   span/attribute/metric machinery runs synchronously on the
                   hot path, with zero network or serialization cost, so it
                   isolates SDK overhead from export/network overhead.

  3. sdk-otlp-batch  Real OTel SDK wired to the actual OTLP/HTTP exporter
                     pointed at a live SigNoz collector (`BatchSpanProcessor` +
                     `PeriodicExportingMetricReader`), i.e. the same wiring as
                     reference-library/examples/emit_one_decision.py. Export
                     happens off a background thread, so this measures whether
                     batching keeps network cost off the hot decision path.
                     SKIPPED with a clear message if the endpoint is
                     unreachable (no fake numbers).

Each configuration is measured independently: fresh providers per
configuration, a warmup phase discarded before timing, then N timed
iterations of a single `record_decision()` call, using `time.perf_counter_ns()`
around each individual call (not just the whole loop), so the reported
percentiles reflect per-call latency, not amortized throughput.

Usage (from repo root, must use the repo's own venv - gradebook is only
importable there):

    .venv/bin/python3 benchmarks/bench_decision_overhead.py
    .venv/bin/python3 benchmarks/bench_decision_overhead.py --iterations 20000
    .venv/bin/python3 benchmarks/bench_decision_overhead.py --otlp-endpoint http://localhost:4318

Does not touch dashboards/ or README.md. Writes only to stdout.
"""

from __future__ import annotations

import argparse
import gc
import platform
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from opentelemetry import metrics as otel_metrics
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

sys.path.insert(0, "reference-library/src")  # works even if not pip-installed
from gradebook import record_decision  # noqa: E402

MODEL = "anthropic/claude-haiku-4.5"  # a real entry in gradebook.pricing.PRICES
WARMUP_ITERATIONS = 200


@dataclass
class Timing:
    label: str
    n: int
    median_us: float
    p95_us: float
    p99_us: float
    mean_us: float
    min_us: float
    max_us: float

    def render(self) -> str:
        return (
            f"{self.label:<18} n={self.n:<7} "
            f"median={self.median_us:8.2f}us  p95={self.p95_us:8.2f}us  "
            f"p99={self.p99_us:8.2f}us  mean={self.mean_us:8.2f}us  "
            f"min={self.min_us:6.2f}us  max={self.max_us:9.2f}us"
        )


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted list (no numpy dep)."""
    if not sorted_values:
        return float("nan")
    k = max(0, min(len(sorted_values) - 1, int(round(pct / 100 * (len(sorted_values) - 1)))))
    return sorted_values[k]


def _time_calls(fn: Callable[[int], None], n: int) -> list[float]:
    """Time n individual calls to fn(i), returning per-call durations in microseconds."""
    durations_us = []
    for i in range(n):
        start = time.perf_counter_ns()
        fn(i)
        end = time.perf_counter_ns()
        durations_us.append((end - start) / 1_000)
    return durations_us


def _run_config(
    label: str,
    tracer_provider,
    meter_provider,
    iterations: int,
) -> Timing:
    def one_call(i: int) -> None:
        record_decision(
            name="route.fastest",
            model=MODEL,
            chosen="B" if i % 2 == 0 else "A",
            correct="A",
            input_tokens=180,
            output_tokens=12,
            decision_type="route_choice",
            response_id=f"bench-resp-{i:07d}",
            explanation="benchmark decision, not a real grading judgment",
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )

    # Warmup: pays for one-time costs (import caches, instrument creation on
    # first counter/histogram use, JIT-ish CPython dict/attr caches) so the
    # timed loop reflects steady-state per-call cost, not first-call cost.
    for i in range(WARMUP_ITERATIONS):
        one_call(i)

    gc.collect()
    gc.disable()
    try:
        durations_us = _time_calls(one_call, iterations)
    finally:
        gc.enable()

    durations_us.sort()
    return Timing(
        label=label,
        n=iterations,
        median_us=statistics.median(durations_us),
        p95_us=_percentile(durations_us, 95),
        p99_us=_percentile(durations_us, 99),
        mean_us=statistics.mean(durations_us),
        min_us=durations_us[0],
        max_us=durations_us[-1],
    )


def bench_noop(iterations: int) -> Timing:
    """'Instrumentation disabled': pure OTel API no-ops, no SDK at all."""
    tracer_provider = otel_trace.NoOpTracerProvider()
    meter_provider = otel_metrics.NoOpMeterProvider()
    return _run_config("noop", tracer_provider, meter_provider, iterations)


def bench_sdk_inmemory(iterations: int) -> Timing:
    """'Instrumentation enabled', no network: real SDK, in-memory exporter."""
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))

    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])

    try:
        return _run_config("sdk-inmemory", tracer_provider, meter_provider, iterations)
    finally:
        tracer_provider.shutdown()
        meter_provider.shutdown()


def _otlp_endpoint_reachable(endpoint: str) -> bool:
    try:
        req = urllib.request.Request(f"{endpoint}/v1/traces", method="POST", data=b"")
        urllib.request.urlopen(req, timeout=1.5)
        return True
    except urllib.error.HTTPError:
        # Any HTTP response (even 400/415 for an empty body) means something is
        # listening and speaking HTTP at that path.
        return True
    except Exception:
        return False


def bench_sdk_otlp_batch(iterations: int, endpoint: str) -> Optional[Timing]:
    """'Instrumentation enabled', real export: SDK + OTLP/HTTP to a live collector.

    Uses BatchSpanProcessor / PeriodicExportingMetricReader (async, background
    thread), matching reference-library/examples/emit_one_decision.py, so the
    timed loop measures whether batching keeps network I/O off the hot path -
    NOT a full network round-trip per call.
    """
    if not _otlp_endpoint_reachable(endpoint):
        print(
            f"  [skip] sdk-otlp-batch: no OTLP/HTTP endpoint reachable at "
            f"{endpoint} - not faking a network number."
        )
        return None

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": "gradebook-bench"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"),
            # Default max_queue_size (2048) drops spans under a fast timed
            # loop with a 5s export interval ("Queue full, dropping Span.").
            # Size generously above the iteration count so every span is
            # actually exported and the benchmark also validates end-to-end
            # delivery, not just enqueue speed.
            max_queue_size=max(iterations + WARMUP_ITERATIONS + 1_000, 2_048),
            max_export_batch_size=2_048,
        )
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
                export_interval_millis=5_000,
            )
        ],
    )

    try:
        return _run_config("sdk-otlp-batch", tracer_provider, meter_provider, iterations)
    finally:
        tracer_provider.force_flush()
        tracer_provider.shutdown()
        meter_provider.force_flush()
        meter_provider.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iterations",
        type=int,
        default=10_000,
        help="Timed iterations per configuration (default: 10000)",
    )
    parser.add_argument(
        "--otlp-endpoint",
        default="http://localhost:4318",
        help="OTLP/HTTP endpoint for the real-export benchmark (default: http://localhost:4318)",
    )
    parser.add_argument(
        "--skip-otlp",
        action="store_true",
        help="Skip the real-OTLP-export configuration entirely",
    )
    args = parser.parse_args()

    print(f"Python: {platform.python_version()} ({sys.executable})")
    print(f"Platform: {platform.platform()}")
    print(f"Model: {platform.machine()}")
    print(f"Iterations per config: {args.iterations} (+{WARMUP_ITERATIONS} warmup, discarded)")
    print()

    results = []
    results.append(bench_noop(args.iterations))
    results.append(bench_sdk_inmemory(args.iterations))
    if not args.skip_otlp:
        otlp_result = bench_sdk_otlp_batch(args.iterations, args.otlp_endpoint)
        if otlp_result is not None:
            results.append(otlp_result)

    print()
    print("Results (per single record_decision() call):")
    for r in results:
        print("  " + r.render())

    if len(results) >= 2:
        noop, sdk = results[0], results[1]
        print()
        print(
            f"SDK overhead over no-op (median): "
            f"{sdk.median_us - noop.median_us:.2f}us "
            f"({sdk.median_us / noop.median_us:.2f}x)"
        )
        print(
            f"SDK overhead over no-op (p95): "
            f"{sdk.p95_us - noop.p95_us:.2f}us "
            f"({sdk.p95_us / noop.p95_us:.2f}x)"
        )


if __name__ == "__main__":
    main()
