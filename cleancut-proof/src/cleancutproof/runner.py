"""The CleanCut real-substrate proof runner (ticket #11).

Runs CleanCut's two math-gradeable jobs - filler detection and quote
extraction - across the model roster, grades every answer against the provable
truth, and records each decision through the Gradebook library. Then replays
CleanCut's historical clip-scoring decisions and grades them by **reality**
(the clip was kept or discarded), span-linking each late grade back to the
decision it judges.

Client-data rule (hard, per team contract + #11): this module never embeds or
commits transcript/clip content. Transcripts and the clips CSV are *local
inputs*; the only telemetry attributes derived from them are counts, grades,
costs, and synthetic ids.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from opentelemetry import metrics, trace

from gradebook import capture_decision, record_decision, record_reality_grade

from .checkers import filler_checker, lexical_fillers, quote_checker

TRACER_NAME = "cleancutproof"

ROSTER = (
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.0-flash",
)

FILLER_PROMPT = (
    "Below is a video transcript. List every pure filler-sound occurrence "
    "(hesitation sounds like: um, uh, er, ah, eh, hm, hmm, mm, mmm, umm, uhh, "
    "ahh, ehh). Reply with ONLY the filler words, space-separated, one entry "
    "per occurrence in transcript order. If there are none, reply NONE.\n\n"
    "TRANSCRIPT:\n{transcript}"
)

QUOTE_PROMPT = (
    "Below is a video transcript. Extract the single most quotable sentence "
    "for a social caption. It MUST be copied verbatim from the transcript - "
    "no paraphrasing, no added words. Reply with ONLY the quote itself.\n\n"
    "TRANSCRIPT:\n{transcript}"
)

CLIP_GATE = 0.45  # CleanCut's publish gate: viral_score >= 0.45 ships the clip


@dataclass(frozen=True)
class ModelReply:
    """One model call's answer plus the usage needed to price it."""

    text: str
    input_tokens: int
    output_tokens: int
    response_id: str


# A caller takes (model, prompt) and returns a ModelReply. Tests inject fakes;
# live runs use openrouter_caller.
ModelCaller = Callable[[str, str], ModelReply]


class BudgetExceededError(RuntimeError):
    """Raised when the per-run spend cap would be crossed (fail loud, stop calling)."""


def openrouter_caller(api_key: str, *, budget_usd: float = 0.50) -> ModelCaller:
    """Live caller via OpenRouter (one API for the whole roster).

    Enforces a per-run budget cap: before each call the spent-so-far total is
    checked against `budget_usd`, and the run aborts rather than overspends -
    same never-Max-plans discipline as #9.
    """
    from gradebook.pricing import price

    spent = {"usd": 0.0}

    def call(model: str, prompt: str) -> ModelReply:
        if spent["usd"] >= budget_usd:
            raise BudgetExceededError(
                f"per-run budget ${budget_usd:.2f} reached (spent ${spent['usd']:.4f})"
            )
        body = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.load(resp)
        usage = payload.get("usage") or {}
        reply = ModelReply(
            text=payload["choices"][0]["message"]["content"].strip(),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            response_id=str(payload.get("id", f"or-{model}")),
        )
        spent["usd"] += price(model, reply.input_tokens, reply.output_tokens)
        return reply

    return call


@dataclass
class ProofSummary:
    """What one proof run produced - printed for the blog, asserted in tests."""

    decisions: int = 0
    correct: int = 0
    total_cost_usd: float = 0.0
    clip_outcomes: int = 0
    clip_correct: int = 0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def cost_per_correct_usd(self) -> Optional[float]:
        return self.total_cost_usd / self.correct if self.correct else None


def run_detections(
    transcript: str,
    *,
    caller: ModelCaller,
    models: tuple[str, ...] = ROSTER,
    transcript_label: str = "transcript",
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[metrics.MeterProvider] = None,
) -> ProofSummary:
    """Run filler detection + quote extraction across the roster and grade both.

    `transcript_label` is a non-identifying handle (e.g. "sample-01") used in
    response ids - never a client name or title.
    """
    from gradebook.pricing import price

    provider = tracer_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer(TRACER_NAME)
    summary = ProofSummary()

    truth_fillers = lexical_fillers(transcript)

    jobs = (
        (
            "filler.pure_detected",
            "filler_detection",
            FILLER_PROMPT,
            # Compare the model's word list against the lexical ground truth.
            lambda chosen, _correct: filler_checker(
                "" if chosen.strip().upper() == "NONE" else chosen, truth_fillers
            ),
            " ".join(truth_fillers) or "NONE",
        ),
        (
            "quote.verbatim",
            "quote_extraction",
            QUOTE_PROMPT,
            # The transcript itself is the "correct" side for the substring check.
            lambda chosen, correct: quote_checker(chosen, correct),
            transcript,
        ),
    )

    with tracer.start_as_current_span(f"cleancut proof {transcript_label}"):
        for name, decision_type, prompt, checker, correct in jobs:
            for model in models:
                with tracer.start_as_current_span(f"{decision_type} {model}"):
                    reply = caller(model, prompt.format(transcript=transcript))
                    response_id = f"{transcript_label}-{decision_type}-{reply.response_id}"
                    record_decision(
                        name=name,
                        model=model,
                        chosen=reply.text,
                        correct=correct,
                        input_tokens=reply.input_tokens,
                        output_tokens=reply.output_tokens,
                        decision_type=decision_type,
                        response_id=response_id,
                        checker=checker,
                        tracer_provider=provider,
                        meter_provider=meter_provider,
                    )
                    is_correct = checker(reply.text, correct)
                    cost = price(model, reply.input_tokens, reply.output_tokens)
                    summary.decisions += 1
                    summary.correct += int(is_correct)
                    summary.total_cost_usd += cost
                    row = summary.by_model.setdefault(
                        model, {"decisions": 0, "correct": 0, "cost_usd": 0.0}
                    )
                    row["decisions"] += 1
                    row["correct"] += int(is_correct)
                    row["cost_usd"] += cost

    return summary


def replay_clip_outcomes(
    clips_csv: Path,
    *,
    tracer_provider: Optional[trace.TracerProvider] = None,
    outcomes_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[metrics.MeterProvider] = None,
    summary: Optional[ProofSummary] = None,
) -> ProofSummary:
    """Replay historical clip-scoring decisions and grade them by reality.

    CSV columns: `clip_id,predicted_viral_score,kept` (clip_id must already be
    a non-identifying handle). Each row is one historical decision - "publish"
    when the predicted score cleared CleanCut's gate - graded correct when the
    real outcome agreed (published clip kept / gated clip discarded). Honest
    proxy per the spec: kept-vs-discarded, no invented engagement numbers, and
    no cost attached (the historical calls' token counts are unknown - the
    library omits cost rather than fabricate one).
    """
    provider = tracer_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer(TRACER_NAME)
    summary = summary or ProofSummary()

    with tracer.start_as_current_span("cleancut clip outcomes replay"):
        with open(clips_csv, newline="") as f:
            for row in csv.DictReader(f):
                clip_id = row["clip_id"]
                predicted = float(row["predicted_viral_score"])
                kept = row["kept"].strip().lower() in {"1", "true", "yes"}
                published = predicted >= CLIP_GATE

                # The historical decision, replayed as its own span so the late
                # grade has a real link target (same pattern as the toy world).
                with tracer.start_as_current_span(f"clip decision {clip_id}"):
                    ref = capture_decision(response_id=f"clip-{clip_id}")

                record_reality_grade(
                    ref,
                    name="clip.publish_worthy",
                    correct=published == kept,
                    decision_type="clip_scoring",
                    explanation=(
                        f"predicted {predicted:.2f} vs gate {CLIP_GATE} -> "
                        f"{'publish' if published else 'hold'}; "
                        f"editor {'kept' if kept else 'discarded'} the clip"
                    ),
                    tracer_provider=outcomes_provider or provider,
                    meter_provider=meter_provider,
                )
                summary.clip_outcomes += 1
                summary.clip_correct += int(published == kept)

    return summary
