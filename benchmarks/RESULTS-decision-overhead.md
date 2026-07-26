# Per-decision OTel instrumentation overhead

Measured, not assumed. This is the actual per-call cost of `record_decision`
(`reference-library/src/gradebook/recorder.py`) - the decision+grade emission
path that produces one `gen_ai.evaluation.result` span plus two OTel metrics
(`reference-library/src/gradebook/metrics.py`) - under three telemetry
configurations. Script: `benchmarks/bench_decision_overhead.py`.

## Machine / environment

- Apple M4 Pro (arm64), macOS 26.3.1
- Python 3.12.13, repo venv (`.venv/`)
- `opentelemetry-api` / `opentelemetry-sdk` 1.44.0 (see `reference-library/pyproject.toml`)
- Local SigNoz stack already running via Docker (`signoz-ingester-1` OTel collector on `localhost:4318`) for the real-export configuration

## Reproduce

```bash
cd /Users/mukundheda/Desktop/AugmentLoop/projects/augmentloop-signoz-hackathon
.venv/bin/python3 benchmarks/bench_decision_overhead.py --iterations 20000
```

Flags: `--iterations N` (default 10000), `--otlp-endpoint URL` (default
`http://localhost:4318`), `--skip-otlp` to skip the real-export configuration
(e.g. no SigNoz stack running).

## Method

Three configurations, each with its own fresh `TracerProvider`/`MeterProvider`,
200 discarded warmup calls, then N timed calls to `record_decision()`. Each
call is timed individually with `time.perf_counter_ns()` (not just the whole
loop), so the reported numbers are per-call latency, not amortized
throughput. GC is disabled during the timed loop to avoid a collection
landing inside one call's timing window.

1. **`noop`** - "instrumentation disabled." `opentelemetry.trace.NoOpTracerProvider`
   + `opentelemetry.metrics.NoOpMeterProvider`. The exact same
   `record_decision()` code runs - math grading, pricing lookup, every
   `set_attribute` call, the counter/histogram calls in `gradebook/metrics.py`
   - but every OTel API call is a no-op with no SDK behind it. This isolates
   `record_decision`'s own Python-level cost (grading + pricing + attribute
   plumbing) from OTel SDK cost.
2. **`sdk-inmemory`** - "instrumentation enabled, no network." A real OTel SDK
   `TracerProvider` + `MeterProvider`, wired to `SimpleSpanProcessor` +
   `InMemorySpanExporter` / `InMemoryMetricReader` - the same fixture pattern
   `reference-library/tests/conftest.py` uses for tests. Real SDK span,
   attribute, and metric machinery runs synchronously on the hot path, with
   zero network or serialization cost. This is the fair "on" number for
   in-process SDK overhead.
3. **`sdk-otlp-batch`** - "instrumentation enabled, real export." Real OTel SDK
   wired to the actual OTLP/HTTP exporter pointed at the live SigNoz collector
   at `localhost:4318` - the same wiring as
   `reference-library/examples/emit_one_decision.py`
   (`BatchSpanProcessor` + `PeriodicExportingMetricReader`, async/background
   thread). Spans and metrics are genuinely delivered to SigNoz, not faked;
   this configuration is skipped with an explicit message (not a fabricated
   number) if the endpoint is unreachable.

## Results (20,000 iterations, one run; see "Run-to-run stability" below)

| Config | median | p95 | p99 | mean | min | max |
|---|---:|---:|---:|---:|---:|---:|
| `noop` (disabled) | 5.71us | 6.42us | 7.67us | 5.81us | 4.83us | 88.96us |
| `sdk-inmemory` (on, no network) | 30.62us | 40.29us | 112.67us | 35.07us | 25.38us | 6923.83us |
| `sdk-otlp-batch` (on, real export) | 30.33us | 40.38us | 115.00us | 45.56us | 24.88us | 11119.46us |

**Headline number: the OTel SDK adds ~25us median / ~34us p95 per decision
(~5.4x median, ~6.3x p95) over the no-op baseline, whether or not spans are
actually exported to a real collector.** At the scale this system runs at
(AI agent decisions - at most low hundreds per second even in a busy
demo), 25-40 microseconds per decision is not something a caller would
notice; it is roughly two orders of magnitude below a single LLM API round
trip (typically 100ms-several seconds).

The near-identical `sdk-inmemory` vs `sdk-otlp-batch` numbers show the
`BatchSpanProcessor`/`PeriodicExportingMetricReader` wiring is doing its job:
network I/O to the collector happens on a background thread, off the
per-decision hot path. The `sdk-otlp-batch` mean is higher than its median
(45.56us vs 30.33us median) because of a heavier right tail (occasional
multi-millisecond spikes, max 11.1ms) - almost certainly background-thread
scheduling/GIL contention from the concurrent batch exporter, not per-call
network cost (a real network round trip to a local Docker container would
show up as a rightward-shifted *median*, which it does not).

## Run-to-run stability

Three back-to-back runs at 10,000 iterations (same machine, same process
each time) before the 20,000-iteration run above:

| Run | noop median | sdk-inmemory median | sdk-otlp-batch median | overhead (median) |
|---|---:|---:|---:|---:|
| 1 | 5.79us | 29.46us | 30.08us | 23.67us (5.09x) |
| 2 | 5.83us | 29.88us | 29.25us | 24.04us (5.12x) |
| 3 | 5.88us | 30.62us | 29.50us | 24.75us (5.21x) |
| 20k (final) | 5.71us | 30.62us | 30.33us | 24.92us (5.37x) |

Medians are stable within about 1us run to run; the overhead figure is
consistently in the 23-25us / ~5x range.

## Caveats (read before quoting this number)

- This measures **one process, single-threaded, back-to-back calls with no
  other work happening** - it isolates instrumentation cost but does not
  model a busy multi-threaded agent runtime with other spans/exports
  contending for the same background export thread.
- `record_decision`'s hot path re-calls `meter.create_counter(...)` /
  `meter.create_histogram(...)` on every single invocation
  (`reference-library/src/gradebook/metrics.py`) rather than caching the
  instrument handles. The OTel SDK meter de-duplicates repeat
  `create_counter`/`create_histogram` calls by name internally, so this does
  not re-register a new instrument each time, but it is still a Python-level
  dict lookup + function call on every decision that a cached instrument
  handle would avoid. Not fixed here (out of scope for a benchmark task) but
  worth flagging as the most obvious next micro-optimization if this ever
  needs to go faster.
- The `sdk-otlp-batch` configuration requires `docker ps` to show the SigNoz
  OTel collector (`signoz-ingester-1`) reachable at `localhost:4318`; if it
  is not running, the script prints `[skip] sdk-otlp-batch: ...` and reports
  only `noop` and `sdk-inmemory` - it never fabricates a real-export number.
- Numbers are wall-clock on one developer laptop, not a controlled
  benchmarking rig (no CPU pinning, no thermal control). Treat the ~5x
  ratio and the ~25-40us absolute magnitude as the defensible claims, not
  the last decimal digit.
