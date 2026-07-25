"""Grades and grade sources.

A grade is the verdict on one decision, stamped with where its authority comes
from (conventions doc section 3). This walking skeleton implements the `math`
source; `reality` and `ai_judge` slot in behind the same `Grade` shape in later
tickets.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Union

from .checkers import CheckResult, ReasonCode

CORRECT = "correct"
INCORRECT = "incorrect"

# A checker may return a bare bool (back-compat, e.g. operator.eq) or a richer
# CheckResult carrying a reason code (the ticket #42 reusable checkers).
CheckerResult = Union[bool, CheckResult]


class GradeSource(str, Enum):
    """Where a grade's authority comes from (conventions doc section 3.1)."""

    MATH = "math"          # a checker computes the provably-correct answer
    REALITY = "reality"    # the real world proves it, usually later
    AI_JUDGE = "ai_judge"  # another model scored it - an opinion, not a fact


@dataclass(frozen=True)
class Grade:
    """One verdict on one decision.

    `reason` is the closed-enum sub-code for *why* the grade got its label
    (conventions §12); it is emitted as `augmentloop.grade.reason` so grades are
    queryable by reason, not just by pass/fail.
    """

    source: GradeSource
    value: float
    label: str
    reason: Optional[ReasonCode] = None


def _as_result(outcome: CheckerResult) -> CheckResult:
    """Normalize a checker's return (bool or CheckResult) to a CheckResult."""
    if isinstance(outcome, CheckResult):
        return outcome
    return CheckResult.decided(bool(outcome))


def math_grade(
    chosen: Any,
    correct: Any,
    checker: Callable[[Any, Any], CheckerResult] = operator.eq,
) -> Grade:
    """Grade a decision against a provably-correct answer.

    The caller supplies `correct`; `checker` compares it to `chosen` (equality by
    default). The checker may return a bare bool or a `CheckResult`; either way
    the grade carries the reason code (MATCH/MISMATCH for a plain bool, or the
    checker's own reason such as NO_GROUND_TRUTH). A binary correctness grade
    always applies, so value and label are always set.
    """
    result = _as_result(checker(chosen, correct))
    return Grade(
        source=GradeSource.MATH,
        value=1.0 if result.passed else 0.0,
        label=CORRECT if result.passed else INCORRECT,
        reason=result.reason,
    )
