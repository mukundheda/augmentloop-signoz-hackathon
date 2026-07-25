"""One command for the capture run: `python -m cleancutproof`.

Inputs are LOCAL files (never committed):
  CLEANCUT_TRANSCRIPT  path to a transcript .txt   (default: bundled synthetic sample)
  CLEANCUT_CLIPS_CSV   path to clip_id,predicted_viral_score,kept CSV
                       (default: bundled synthetic sample)
  OPENROUTER_API_KEY   required for the live roster run
  PROOF_BUDGET_USD     per-run spend cap (default 0.50)
  OTEL_EXPORTER_OTLP_ENDPOINT  (default http://localhost:4318)

Emits two services, mirroring the toy world: `cleancut-proof` (detections +
historical clip decisions) and `cleancut-outcomes` (the late reality grades).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .runner import ROSTER, openrouter_caller, replay_clip_outcomes, run_detections

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _tracer_provider(service: str) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces"))
    )
    return provider


def _meter_provider(service: str) -> MeterProvider:
    return MeterProvider(
        resource=Resource.create({"service.name": service}),
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{ENDPOINT}/v1/metrics"),
                export_interval_millis=1_000,
            )
        ],
    )


def main() -> None:
    # Two provider paths. `openrouter` is the original; `direct` is the stopgap
    # (mirroring toyworld.direct, #9) that runs on the keys CleanCut already
    # holds, so this capture is not blocked on OpenRouter credit. Chosen with
    # PROOF_PROVIDER, defaulting to whichever key is actually present.
    provider = os.environ.get("PROOF_PROVIDER")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not provider:
        provider = "openrouter" if api_key else "direct"

    if provider == "openrouter" and not api_key:
        sys.exit(
            "OPENROUTER_API_KEY is not set. Either set it, or use the direct "
            "provider (PROOF_PROVIDER=direct) which runs on OPENAI_API_KEY + "
            "GOOGLE_API_KEY. Tests need no key: pytest cleancut-proof/tests"
        )
    if provider == "direct" and not (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    ):
        sys.exit(
            "PROOF_PROVIDER=direct needs OPENAI_API_KEY and/or GOOGLE_API_KEY "
            "(GEMINI_API_KEY also accepted). Tests need no key."
        )

    transcript_path = Path(
        os.environ.get("CLEANCUT_TRANSCRIPT", SAMPLES / "sample_transcript.txt")
    )
    clips_csv = Path(os.environ.get("CLEANCUT_CLIPS_CSV", SAMPLES / "sample_clips.csv"))
    budget = float(os.environ.get("PROOF_BUDGET_USD", "0.50"))
    # Roster override, so a direct run can name the models its keys can reach.
    roster_env = os.environ.get("PROOF_ROSTER")
    roster = tuple(m.strip() for m in roster_env.split(",")) if roster_env else ROSTER

    transcript = transcript_path.read_text(encoding="utf-8")
    label = transcript_path.stem  # keep labels non-identifying by choosing the file name

    proof = _tracer_provider("cleancut-proof")
    outcomes = _tracer_provider("cleancut-outcomes")
    proof_meters = _meter_provider("cleancut-proof")
    outcomes_meters = _meter_provider("cleancut-outcomes")

    if provider == "direct":
        from .direct import direct_caller

        caller = direct_caller(budget_usd=budget)
    else:
        caller = openrouter_caller(api_key, budget_usd=budget)
    print(f"provider={provider}  roster={', '.join(roster)}")
    summary = run_detections(
        transcript,
        caller=caller,
        models=roster,
        transcript_label=label,
        tracer_provider=proof,
        meter_provider=proof_meters,
    )
    summary = replay_clip_outcomes(
        clips_csv,
        tracer_provider=proof,
        outcomes_provider=outcomes,
        meter_provider=outcomes_meters,
        summary=summary,
    )

    for provider in (proof, outcomes, proof_meters, outcomes_meters):
        provider.force_flush()
        provider.shutdown()

    print(f"CleanCut proof run ({label}) -> {ENDPOINT}")
    print(
        f"detections={summary.decisions}  correct={summary.correct}  "
        f"total_cost=${summary.total_cost_usd:.6f}"
    )
    if summary.cost_per_correct_usd is not None:
        print(f"cost per correct detection: ${summary.cost_per_correct_usd:.6f}")
    print("per model:")
    for model, row in summary.by_model.items():
        print(
            f"  {model}: {row['correct']:.0f}/{row['decisions']:.0f} correct, "
            f"${row['cost_usd']:.6f}"
        )
    print(
        f"clip reality grades: {summary.clip_correct}/{summary.clip_outcomes} "
        "historical publish decisions confirmed by kept/discarded"
    )
    print("Reminder: transcripts/CSVs are local-only; do not commit outputs.")


if __name__ == "__main__":
    main()
