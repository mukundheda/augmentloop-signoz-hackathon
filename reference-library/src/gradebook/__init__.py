"""Gradebook reference library (walking skeleton).

Records one math-graded AI decision as the standard OpenTelemetry
`gen_ai.evaluation.result` event, with the two mandatory Gradebook extension
attributes (`augmentloop.grade.source`, `augmentloop.cost.usd`).

The public seam is `record_decision`. See `docs/conventions.md` for the contract
this library applies; the emitted telemetry - not this API - is the contract.
"""

from .grading import Grade, GradeSource
from .recorder import (
    DecisionRef,
    capture_decision,
    record_decision,
    record_reality_grade,
)

__all__ = [
    "record_decision",
    "capture_decision",
    "record_reality_grade",
    "DecisionRef",
    "Grade",
    "GradeSource",
]
