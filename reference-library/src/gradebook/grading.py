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
from typing import Any, Callable

CORRECT = "correct"
INCORRECT = "incorrect"


class GradeSource(str, Enum):
    """Where a grade's authority comes from (conventions doc section 3.1)."""

    MATH = "math"          # a checker computes the provably-correct answer
    REALITY = "reality"    # the real world proves it, usually later
    AI_JUDGE = "ai_judge"  # another model scored it - an opinion, not a fact


@dataclass(frozen=True)
class Grade:
    """One verdict on one decision."""

    source: GradeSource
    value: float
    label: str


def math_grade(
    chosen: Any,
    correct: Any,
    checker: Callable[[Any, Any], bool] = operator.eq,
) -> Grade:
    """Grade a decision against a provably-correct answer.

    The caller supplies `correct`; `checker` compares it to `chosen` (equality by
    default). A binary correctness grade always applies, so value and label are
    always set (1.0/"correct" or 0.0/"incorrect").
    """
    is_correct = checker(chosen, correct)
    return Grade(
        source=GradeSource.MATH,
        value=1.0 if is_correct else 0.0,
        label=CORRECT if is_correct else INCORRECT,
    )
