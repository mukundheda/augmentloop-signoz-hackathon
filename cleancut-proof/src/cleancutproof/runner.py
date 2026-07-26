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
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from opentelemetry import metrics, trace

from gradebook import (
    CheckResult,
    capture_decision,
    record_decision,
    record_reality_grade,
    verbatim_substring,
)

from .checkers import filler_checker, lexical_fillers


def _passed(outcome) -> bool:
    """Normalize a checker return (bool or CheckResult) to a bool for the tally."""
    return outcome.passed if isinstance(outcome, CheckResult) else bool(outcome)


def _strip_none_sentinel(answer: str) -> str:
    """Drop the prompt's `NONE` sentinel wherever it appears in a filler answer.

    The prompt says "if there are none, reply NONE", and models sometimes append
    NONE *after* listing fillers rather than instead of a list (observed from
    gpt-4o on the real capture). Only stripping a whole-answer "NONE" left the
    sentinel as a stray token, which the multiset comparison then counted as a
    filler the transcript never contained - failing a model for how it framed
    its answer rather than for which fillers it found. This grade is supposed to
    measure filler detection, so the sentinel is removed either way; a genuinely
    wrong count still fails.
    """
    return re.sub(r"\bNONE\b", " ", answer, flags=re.IGNORECASE)

TRACER_NAME = "cleancutproof"

# Current roster, grounded against OpenRouter's public /models API in #9 and
# matched to toyworld.live.DEFAULT_ROSTER: cheap tier, premium tier, and a
# cross-provider cheap contrast. The pre-#24 slugs (claude-3.5-haiku,
# claude-sonnet-4, gemini-2.0-flash) are retired/delisted and 404 on a live run.
ROSTER = (
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-sonnet-4.6",
    "google/gemini-2.5-flash-lite",
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

# Performance prediction: will this piece beat the typical piece on its own
# channel. Graded `reality` against published performance, so unlike the clip
# gate (where 51 of 51 scored above threshold and nothing could come out wrong)
# roughly half of a median-split population fails by construction.
PERFORMANCE_PROMPT = (
    "Below is a video transcript. Predict whether this piece will outperform "
    "the typical piece on its own channel, judging only from the content "
    "itself. Reply with ONLY a number between 0 and 1, where 1 means certain "
    "to outperform and 0 means certain to underperform. No words, no "
    "explanation, just the number.\n\n"
    "TRANSCRIPT:\n{transcript}"
)
PERFORMANCE_GATE = 0.5  # >= this means the model predicted "will outperform"

# Anything that would tell the model the answer instead of making it predict.
# The toy world lost a whole run to leaked answers inside prompts, and the
# failure mode is silent: every model scores well and it reads as a finding.
_LEAK_PATTERNS = (
    r"\bviews?\b", r"\bview[_\s-]?count\b", r"\bwatch(ed|es|time)?\b",
    r"\blikes?\b", r"\bcomments?\b", r"\bsubscribers?\b", r"\bengagement\b",
    r"\bimpressions?\b", r"\bctr\b", r"\bpublish(ed)?[_\s-]?(date|on)\b",
    r"\bupload(ed)?[_\s-]?(date|on)\b", r"\bperformed\b", r"\boutperformed\b",
    r"\bmedian\b", r"\bper[_\s-]?day\b", r"\btrending\b", r"\bviral[_\s-]?score\b",
)


class PromptLeakError(RuntimeError):
    """Raised when a prompt carries the answer it is supposed to predict."""


def assert_no_performance_leak(prompt: str, transcript: str) -> None:
    """Fail loud if the scaffolding around a transcript leaks outcome data.

    Only the prompt's own wording is checked, never the transcript: a creator
    saying the word "views" on camera is content, not a leak, and rejecting that
    would make most real transcripts unusable. What must stay clean is anything
    we wrap around it.
    """
    scaffold = prompt.replace(transcript, " ")
    for pat in _LEAK_PATTERNS:
        m = re.search(pat, scaffold, flags=re.IGNORECASE)
        if m:
            raise PromptLeakError(
                f"performance prompt leaks outcome data: matched {pat!r} on "
                f"{m.group(0)!r}. The model must predict from the transcript "
                f"alone, never from how the piece actually did."
            )


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
    # (model, decision_type) -> counts. The two jobs fail very differently -
    # exhaustive filler enumeration is a much harder ask than pulling one
    # verbatim quote - so a single per-model number hides the real finding.
    by_model_type: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)

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
                _strip_none_sentinel(chosen), truth_fillers
            ),
            " ".join(truth_fillers) or "NONE",
        ),
        (
            "quote.verbatim",
            "quote_extraction",
            QUOTE_PROMPT,
            # The library's reusable verbatim-substring checker (ticket #42): it
            # returns a CheckResult, so the emitted grade carries the reason code
            # (MATCH / MISMATCH / EMPTY_ANSWER) rather than a bare true/false.
            verbatim_substring,
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
                    is_correct = _passed(checker(reply.text, correct))
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
                    trow = summary.by_model_type.setdefault(
                        (model, decision_type),
                        {"decisions": 0, "correct": 0, "cost_usd": 0.0},
                    )
                    trow["decisions"] += 1
                    trow["correct"] += int(is_correct)
                    trow["cost_usd"] += cost

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


def run_performance_prediction(
    transcript: str,
    *,
    caller: ModelCaller,
    item_id: str,
    ground_truth: dict[str, bool],
    models: tuple[str, ...] = ROSTER,
    tracer_provider: Optional[trace.TracerProvider] = None,
    outcomes_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[metrics.MeterProvider] = None,
    summary: Optional[ProofSummary] = None,
) -> ProofSummary:
    """Predict whether a piece outperforms its channel, graded by `reality`.

    The decision is made from the transcript alone; the verdict comes from
    published performance the model never saw. `ground_truth` is read ONLY
    here, after the answer exists, and is never threaded into the prompt path.

    Items with no ground-truth row are skipped rather than guessed at: a
    decision we cannot grade is not evidence, and inventing an outcome is the
    one thing that would sink this.
    """
    from gradebook.pricing import price

    provider = tracer_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer(TRACER_NAME)
    summary = summary or ProofSummary()

    if item_id not in ground_truth:
        return summary
    outperformed = ground_truth[item_id]

    prompt = PERFORMANCE_PROMPT.format(transcript=transcript)
    # Fail loud before spending, not after: a leaked prompt invalidates the run.
    assert_no_performance_leak(prompt, transcript)

    with tracer.start_as_current_span(f"performance {item_id}"):
        for model in models:
            with tracer.start_as_current_span(f"performance_prediction {model}"):
                reply = caller(model, prompt)
                ref = capture_decision(
                    response_id=f"perf-{item_id}-{reply.response_id}"
                )
                try:
                    score = float(re.search(r"[01]?\.?\d+", reply.text).group(0))
                except (AttributeError, ValueError):
                    score = -1.0  # unparseable answer counts as a wrong call
                predicted_out = score >= PERFORMANCE_GATE
                cost = price(model, reply.input_tokens, reply.output_tokens)

                record_reality_grade(
                    ref,
                    name="performance.outperformed",
                    correct=predicted_out == outperformed,
                    model=model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                    decision_type="performance_prediction",
                    explanation=(
                        f"predicted {score:.2f} vs gate {PERFORMANCE_GATE} -> "
                        f"{'outperform' if predicted_out else 'underperform'}; "
                        f"actually {'outperformed' if outperformed else 'underperformed'}"
                    ),
                    tracer_provider=outcomes_provider or provider,
                    meter_provider=meter_provider,
                )

                ok = predicted_out == outperformed
                summary.decisions += 1
                summary.correct += int(ok)
                summary.total_cost_usd += cost
                row = summary.by_model.setdefault(
                    model, {"decisions": 0, "correct": 0, "cost_usd": 0.0}
                )
                row["decisions"] += 1
                row["correct"] += int(ok)
                row["cost_usd"] += cost
                trow = summary.by_model_type.setdefault(
                    (model, "performance_prediction"),
                    {"decisions": 0, "correct": 0, "cost_usd": 0.0},
                )
                trow["decisions"] += 1
                trow["correct"] += int(ok)
                trow["cost_usd"] += cost

    return summary


def load_ground_truth(path: Path) -> dict[str, bool]:
    """Read item_id,outperformed. Read only by the reality replay, never the prompt."""
    truth: dict[str, bool] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            truth[row["item_id"].strip()] = (
                row["outperformed"].strip().lower() in {"1", "true", "yes"}
            )
    return truth


def recording_caller(path: Path, *, record_from: Optional[ModelCaller] = None) -> ModelCaller:
    """Record live replies to JSONL, or replay them so a judge needs no API key.

    This is what the toy world already has and CleanCut did not: with
    `record_from` set it wraps a live caller and appends every
    (model, prompt) -> reply; with it unset it serves stored replies and makes
    no network call at all.

    The recording stores only what the model SAID. Grades are always recomputed
    by the checkers at replay time, never read from the file, which is the
    property that keeps a replay honest instead of circular.
    """
    import hashlib

    def _key(model: str, prompt: str) -> str:
        return f"{model}|{hashlib.sha256(prompt.encode()).hexdigest()[:32]}"

    if record_from is not None:
        def record(model: str, prompt: str) -> ModelReply:
            reply = record_from(model, prompt)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "key": _key(model, prompt),
                    "model": model,
                    "text": reply.text,
                    "input_tokens": reply.input_tokens,
                    "output_tokens": reply.output_tokens,
                    "response_id": reply.response_id,
                }) + "\n")
            return reply
        return record

    store: dict[str, ModelReply] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            store[r["key"]] = ModelReply(
                text=r["text"],
                input_tokens=int(r["input_tokens"]),
                output_tokens=int(r["output_tokens"]),
                response_id=r["response_id"],
            )

    def replay(model: str, prompt: str) -> ModelReply:
        k = _key(model, prompt)
        if k not in store:
            raise KeyError(
                f"no recorded reply for {model}. The recording and the prompts "
                f"have drifted apart; re-record rather than guess."
            )
        return store[k]

    return replay
