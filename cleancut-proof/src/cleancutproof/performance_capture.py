"""Run and record the CleanCut performance prediction reality grade.

The transcript corpus stays local. The committed JSONL recording contains only
model replies, usage, response ids, and a hash of each prompt.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .direct import direct_caller
from .runner import (
    PERFORMANCE_GATE,
    ProofSummary,
    load_ground_truth,
    recording_caller,
    run_performance_prediction,
)

DEFAULT_ROSTER = (
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "google/gemini-2.5-flash-lite",
)


def _providers(service: str, endpoint: str) -> tuple[TracerProvider, MeterProvider]:
    resource = Resource.create({"service.name": service})
    traces = TracerProvider(resource=resource)
    traces.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    metrics = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
                export_interval_millis=1_000,
            )
        ],
    )
    return traces, metrics


def _transcripts(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for item_id, value in raw.items():
        if isinstance(value, str):
            text = value
        elif isinstance(value, dict):
            text = value.get("full") or value.get("text") or value.get("hook_90s") or ""
        else:
            text = ""
        if isinstance(text, str) and text.strip():
            result[item_id] = text
    return result


def _score(text: str) -> float:
    match = re.search(r"[01]?\.?\d+", text)
    if not match:
        return -1.0
    try:
        return float(match.group(0))
    except ValueError:
        return -1.0


def _dump_checkpoint(
    path: Path,
    *,
    started_at: str,
    completed_at: str | None,
    processed_items: int,
    total_items: int,
    summary: ProofSummary,
    confusion: dict[str, dict[str, int]],
) -> None:
    payload = {
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "processed_items": processed_items,
        "total_items": total_items,
        "decisions": summary.decisions,
        "correct": summary.correct,
        "cost_usd": round(summary.total_cost_usd, 8),
        "by_model": summary.by_model,
        "by_model_type": {
            f"{model}|{decision_type}": row
            for (model, decision_type), row in summary.by_model_type.items()
        },
        "confusion_by_model": confusion,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    corpus_path = Path(os.environ["CLEANCUT_PERFORMANCE_CORPUS"])
    truth_path = Path(os.environ["CLEANCUT_PERFORMANCE_GROUND_TRUTH"])
    recording_path = Path(
        os.environ.get(
            "CLEANCUT_PERFORMANCE_RECORDING",
            "cleancut-proof/recordings/cleancut-performance.jsonl",
        )
    )
    summary_path = Path(
        os.environ.get(
            "CLEANCUT_PERFORMANCE_SUMMARY",
            "cleancut-proof/recordings/cleancut-performance-summary.json",
        )
    )
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    budget = float(os.environ.get("PROOF_BUDGET_USD", "3.00"))
    roster_env = os.environ.get("PROOF_ROSTER")
    roster = (
        tuple(model.strip() for model in roster_env.split(",") if model.strip())
        if roster_env
        else DEFAULT_ROSTER
    )

    corpus = _transcripts(corpus_path)
    truth = load_ground_truth(truth_path)
    missing = sorted(set(truth) - set(corpus))
    if missing:
        raise RuntimeError(f"ground-truth ids missing transcripts: {', '.join(missing)}")

    recording_path.parent.mkdir(parents=True, exist_ok=True)
    live = direct_caller(budget_usd=budget)
    record_live = recording_caller(recording_path, record_from=live)
    replay = (
        recording_caller(recording_path)
        if recording_path.exists() and recording_path.stat().st_size
        else None
    )
    live_calls = 0

    def caller(model: str, prompt: str):  # type: ignore[no-untyped-def]
        """Replay completed calls and append only responses still missing."""
        nonlocal live_calls
        if replay is not None:
            try:
                return replay(model, prompt)
            except KeyError:
                pass
        live_calls += 1
        return record_live(model, prompt)

    throttle = float(os.environ.get("PROOF_THROTTLE", "6"))
    rate_limit_sleep = float(os.environ.get("PROOF_RATE_LIMIT_SLEEP", "65"))
    proof_traces, proof_metrics = _providers("cleancut-proof", endpoint)
    outcome_traces, outcome_metrics = _providers("cleancut-outcomes", endpoint)

    started_at = datetime.now(timezone.utc).isoformat()
    summary = ProofSummary()
    confusion: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    )
    total = len(truth)
    processed = 0

    print(f"START_UTC={started_at}", flush=True)
    print(f"items={total} roster={','.join(roster)} endpoint={endpoint}", flush=True)

    try:
        for item_id in sorted(truth):
            replies: dict[str, str] = {}
            live_calls_before = live_calls

            def capture(model: str, prompt: str):  # type: ignore[no-untyped-def]
                for attempt in range(3):
                    try:
                        reply = caller(model, prompt)
                        break
                    except urllib.error.HTTPError as error:
                        if error.code != 429 or attempt == 2:
                            raise
                        print(
                            f"rate_limit model={model} "
                            f"sleep={rate_limit_sleep:.0f}s",
                            flush=True,
                        )
                        time.sleep(rate_limit_sleep)
                replies[model] = reply.text
                return reply

            run_performance_prediction(
                corpus[item_id],
                caller=capture,
                item_id=item_id,
                ground_truth=truth,
                models=roster,
                tracer_provider=proof_traces,
                outcomes_provider=outcome_traces,
                meter_provider=outcome_metrics,
                summary=summary,
            )
            actual = truth[item_id]
            for model, text in replies.items():
                predicted = _score(text) >= PERFORMANCE_GATE
                bucket = (
                    "tp"
                    if predicted and actual
                    else "tn"
                    if not predicted and not actual
                    else "fp"
                    if predicted
                    else "fn"
                )
                confusion[model][bucket] += 1

            processed += 1
            _dump_checkpoint(
                summary_path,
                started_at=started_at,
                completed_at=None,
                processed_items=processed,
                total_items=total,
                summary=summary,
                confusion=confusion,
            )
            print(
                f"checkpoint items={processed}/{total} decisions={summary.decisions} "
                f"correct={summary.correct} cost=${summary.total_cost_usd:.6f}",
                flush=True,
            )
            if live_calls > live_calls_before and throttle:
                time.sleep(throttle)
    finally:
        for provider in (
            proof_traces,
            outcome_traces,
            proof_metrics,
            outcome_metrics,
        ):
            provider.force_flush()
            provider.shutdown()

    completed_at = datetime.now(timezone.utc).isoformat()
    _dump_checkpoint(
        summary_path,
        started_at=started_at,
        completed_at=completed_at,
        processed_items=processed,
        total_items=total,
        summary=summary,
        confusion=confusion,
    )
    print(f"END_UTC={completed_at}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
