"""ai_judge grader (SIDE EXPERIMENT - not part of the headline metric).

`GradeSource.AI_JUDGE` (reference-library/src/gradebook/grading.py) has never
actually been emitted anywhere in this repo's committed runs - it exists only
as an enum value and an accepted string in conformance/check_conformance.py.
ADR 0001 (docs/adr/0001-*) excludes ai_judge from the headline "cost per
correct decision" on purpose, citing published self-preference/verbosity/
position bias in LLM judges.

This module builds the grader that ADR 0001 argues against trusting, so this
project can show its work: run it once, and quantify what trusting it would
have cost. See experiments/ai-judge/README.md for the full rationale and
experiments/ai-judge/WRITEUP.md for the results.

Reuses `toyworld.openrouter.OpenRouterClient` for the actual OpenRouter call
(key handling, base URL, and the transient-error retry/backoff loop) rather
than writing a second HTTP client. `_create_with_retry` is "private" (a
leading underscore) but takes only `model=` and an object with a `.prompt`
attribute - `_JudgePrompt` below duck-types exactly that, so the judge's very
different prompt (no answer key, a request for the judge's own reasoning)
reuses the client's retry behaviour without needing `query.parse` or any of
`world.Query`'s other fields, which don't apply to a judge call anyway.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from toyworld.openrouter import OpenRouterClient

# Observed empirically (see WRITEUP.md "what did not work"): OpenRouter
# sometimes routes qwen/qwen-2.5-72b-instruct to an upstream that returns a
# 200 response body shaped `{"error": {"code": 400, "message": "... does not
# support endpoint: completions"}}` with `choices=None`, rather than an HTTP
# error status - so OpenRouterClient's own retry loop (which only catches
# RateLimitError/APIStatusError) never sees it. Measured ~1 in 5 calls on a
# 10-call sequential probe. Retried here as its own transient class, same
# backoff shape as the client's real retries, since it is not a bad
# prompt/key/slug - the identical prompt succeeds on retry.
_TRANSIENT_ENDPOINT_RETRY_DELAYS_S: tuple[float, ...] = (1.0, 3.0, 6.0)

# The judge is asked to solve the problem itself before grading - it is
# explicitly NOT given the answer key (world.Query.correct never appears in
# this prompt). Response format is deliberately rigid (two labeled lines) so
# parsing is a single regex, not free-form extraction.
JUDGE_PROMPT_TEMPLATE = (
    "You are a strict, independent grader for an AI agent's answer to a "
    "route-planning problem over a road network.\n\n"
    "You will be given the EXACT problem text the agent saw, including the "
    "full road map, and the agent's final answer. You are NOT given any "
    "answer key. Work out the correct answer yourself, from the map, by "
    "actual computation, BEFORE judging the agent's answer. Do not assume "
    "the agent is right because it sounds confident, and do not assume it "
    "is wrong because the answer looks unusual - check the arithmetic "
    "yourself.\n\n"
    "Reply in EXACTLY this two-line format, nothing else:\n"
    "VERDICT: correct\n"
    "REASONING: <one or two sentences showing your own computation and why "
    "the agent's answer does or doesn't match it>\n"
    "(use VERDICT: incorrect if the agent's answer is wrong)\n\n"
    "--- PROBLEM GIVEN TO THE AGENT ---\n"
    "{problem_prompt}\n"
    "--- END OF PROBLEM ---\n\n"
    "The agent's final answer was: {chosen!r}\n\n"
    "Is the agent's answer correct?"
)

_VERDICT_RE = re.compile(r"verdict\s*:\s*(correct|incorrect)", re.IGNORECASE)
_REASONING_RE = re.compile(r"reasoning\s*:\s*(.*)", re.IGNORECASE | re.DOTALL)


def parse_verdict(text: str) -> str:
    """Extract the judge's correct/incorrect call from its raw reply.

    Falls back to a loose prefix match, then to "unparseable" - a bad judge
    reply is recorded as data (a data point about judge reliability), never
    silently coerced into "incorrect" or dropped.
    """
    match = _VERDICT_RE.search(text)
    if match:
        return match.group(1).lower()
    lowered = text.strip().lower()
    if lowered.startswith("correct"):
        return "correct"
    if lowered.startswith("incorrect"):
        return "incorrect"
    return "unparseable"


def parse_reasoning(text: str) -> str:
    """Pull the REASONING line(s) out of the judge's reply, for verbatim
    quoting; falls back to the whole reply when the format wasn't followed."""
    match = _REASONING_RE.search(text)
    return match.group(1).strip() if match else text.strip()


@dataclass(frozen=True)
class _JudgePrompt:
    """Duck-types `world.Query` just far enough to reuse
    `OpenRouterClient._create_with_retry`, which reads only `.prompt`."""

    prompt: str


@dataclass(frozen=True)
class JudgeVerdict:
    """One ai_judge grade: the label, the judge's own verbatim text (for
    on-camera quoting of disagreements), and the token/cost accounting for
    THIS judge call - kept separate from the headline recompute, which prices
    the original candidate models from gradebook.pricing, never the judge."""

    label: str  # "correct" | "incorrect" | "unparseable"
    raw_text: str
    reasoning: str
    input_tokens: int
    output_tokens: int
    reported_cost_usd: Optional[float]


class AiJudgeGrader:
    """Grades one recorded decision as correct/incorrect by asking a real LLM,
    without the answer key. This is the grader ADR 0001 argues should never
    feed the headline metric; it exists to run that argument's one supporting
    experiment (see README.md in this directory).
    """

    def __init__(self, *, judge_model: str, client: Optional[OpenRouterClient] = None):
        self._judge_model = judge_model
        self._client = client or OpenRouterClient()

    def _call_with_endpoint_retry(self, prompt: str):
        """`_create_with_retry` (see module docstring) already retries real
        HTTP-level failures; this wraps it once more for the embedded-error
        response body described above, which never raises."""
        last_response = None
        for attempt in range(len(_TRANSIENT_ENDPOINT_RETRY_DELAYS_S) + 1):
            response = self._client._create_with_retry(  # noqa: SLF001
                model=self._judge_model, query=_JudgePrompt(prompt=prompt)
            )
            if response.choices is not None:
                return response
            last_response = response
            if attempt < len(_TRANSIENT_ENDPOINT_RETRY_DELAYS_S):
                time.sleep(_TRANSIENT_ENDPOINT_RETRY_DELAYS_S[attempt])
        raise RuntimeError(
            f"judge model {self._judge_model!r} returned no choices after "
            f"{len(_TRANSIENT_ENDPOINT_RETRY_DELAYS_S) + 1} attempts; "
            f"last response.error={getattr(last_response, 'error', None)!r}"
        )

    def judge(self, *, problem_prompt: str, chosen: Any) -> JudgeVerdict:
        prompt = JUDGE_PROMPT_TEMPLATE.format(problem_prompt=problem_prompt, chosen=chosen)
        response = self._call_with_endpoint_retry(prompt)
        content = response.choices[0].message.content or ""
        usage = response.usage
        reported_cost = getattr(usage, "cost", None) if usage is not None else None
        return JudgeVerdict(
            label=parse_verdict(content),
            raw_text=content.strip(),
            reasoning=parse_reasoning(content),
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            reported_cost_usd=reported_cost,
        )
