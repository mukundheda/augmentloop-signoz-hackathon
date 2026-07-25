"""Conformance checker for the Gradebook recording contract (ticket #44).

ADR 0002's whole moat is that Gradebook extends a *cross-language* OpenTelemetry
standard. That was proven in exactly one language (the Python reference
library). This checker turns "our contract is language-agnostic" from a claim
into something **executable against an implementation we did not write**: hand
it a `gen_ai.evaluation.result` event emitted by any language, and it validates
that event against the frozen field table in `docs/conventions.md` §9.

It depends on nothing but the standard library, precisely so it can judge a
non-Python emitter without importing the Python library it is checking.

Input is one event as language-neutral JSON:

    {"name": "gen_ai.evaluation.result",
     "attributes": {"gen_ai.evaluation.name": "quote.verbatim",
                    "augmentloop.grade.source": "math", ...}}

Run:
    python conformance/check_conformance.py <event.json>     # or "-" for stdin

Exit code 0 = conforms (warnings allowed), 1 = one or more errors, 2 = bad input.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Optional

# --- the frozen contract (docs/conventions.md §9, semconv v1.43.0) -----------

EVENT_NAME = "gen_ai.evaluation.result"
GRADE_SOURCES = {"math", "reality", "ai_judge"}
SCORE_LABELS = {"correct", "incorrect"}
MACHINE_SOURCES = {"math", "reality"}  # §4: these set score.value/label as 1/0

# attribute keys (§9)
EVAL_NAME = "gen_ai.evaluation.name"
SCORE_VALUE = "gen_ai.evaluation.score.value"
SCORE_LABEL = "gen_ai.evaluation.score.label"
RESPONSE_ID = "gen_ai.response.id"
GRADE_SOURCE = "augmentloop.grade.source"
COST_USD = "augmentloop.cost.usd"


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_event(event: dict) -> list[Finding]:
    """Validate one event against the frozen field table. Errors fail, warnings don't."""
    findings: list[Finding] = []
    attrs = event.get("attributes")
    if not isinstance(attrs, dict):
        return [Finding("error", "event has no `attributes` object")]

    # The standard event itself.
    if event.get("name") != EVENT_NAME:
        findings.append(
            Finding("error", f"event name must be {EVENT_NAME!r}, got {event.get('name')!r}")
        )

    # Required standard field: the evaluation name (§9, semconv `required`).
    name = attrs.get(EVAL_NAME)
    if not isinstance(name, str) or not name.strip():
        findings.append(Finding("error", f"{EVAL_NAME} is required and must be a non-empty string"))

    # Mandatory extension: grade source, closed enum (§3, ADR 0001).
    source = attrs.get(GRADE_SOURCE)
    if source is None:
        findings.append(Finding("error", f"{GRADE_SOURCE} is mandatory on every grade"))
    elif source not in GRADE_SOURCES:
        findings.append(
            Finding("error", f"{GRADE_SOURCE} must be one of {sorted(GRADE_SOURCES)}, got {source!r}")
        )

    # Correctness encoding (§4). math/reality grades set both slots as 1.0/0.0
    # and correct/incorrect; ai_judge may carry a raw score, so only type-check it.
    value = attrs.get(SCORE_VALUE)
    label = attrs.get(SCORE_LABEL)
    if source in MACHINE_SOURCES:
        # `_is_number` first: Python's `True == 1`, so a bare membership test
        # accepts a JSON `true` here. That matters more in this checker than
        # almost anywhere else, because its whole job is judging emitters
        # written in other languages, where `true` is a native literal and
        # `score.value: isCorrect` is one keystroke from `isCorrect ? 1 : 0`.
        if not _is_number(value) or value not in (0.0, 1.0):
            findings.append(
                Finding("error", f"{SCORE_VALUE} must be 0.0 or 1.0 for a {source} grade, got {value!r}")
            )
        if label not in SCORE_LABELS:
            findings.append(
                Finding("error", f"{SCORE_LABEL} must be one of {sorted(SCORE_LABELS)} for a {source} grade, got {label!r}")
            )
    else:
        if value is not None and not _is_number(value):
            findings.append(Finding("error", f"{SCORE_VALUE}, if present, must be a number"))
        if label is not None and not isinstance(label, str):
            findings.append(Finding("error", f"{SCORE_LABEL}, if present, must be a string"))

    # Cost extension: optional, but if present must be a non-negative number (§3.2).
    cost = attrs.get(COST_USD)
    if cost is not None and (not _is_number(cost) or cost < 0):
        findings.append(Finding("error", f"{COST_USD}, if present, must be a number >= 0, got {cost!r}"))

    # Recommended (§7 / §9): the correlation key. Missing is a warning, not a fail.
    if not attrs.get(RESPONSE_ID):
        findings.append(Finding("warning", f"{RESPONSE_ID} is recommended (correlation to the model call) but absent"))

    return findings


def conforms(event: dict) -> bool:
    """True if the event has no error-level findings (warnings are allowed)."""
    return not any(f.level == "error" for f in check_event(event))


def _load(arg: str) -> dict:
    text = sys.stdin.read() if arg == "-" else open(arg, encoding="utf-8").read()
    return json.loads(text)


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: check_conformance.py <event.json | ->", file=sys.stderr)
        return 2
    try:
        event = _load(argv[0])
    except (OSError, json.JSONDecodeError) as e:
        print(f"[error] could not read event: {e}", file=sys.stderr)
        return 2

    findings = check_event(event)
    for f in findings:
        print(f, file=sys.stderr)
    if any(f.level == "error" for f in findings):
        print("NONCONFORMING", file=sys.stderr)
        return 1
    print("CONFORMS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
