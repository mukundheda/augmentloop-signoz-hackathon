"""The public recording seam: `record_decision`.

Applies the conventions doc's contract for one math-graded decision: grade it,
and emit one standard `gen_ai.evaluation.result` event carrying the standard
score slots plus Gradebook's mandatory grade-source extension. The emitted
telemetry - not this signature - is the contract.
"""

from __future__ import annotations

import operator
from typing import Any, Callable, Optional

from opentelemetry import trace

from . import conventions as conv
from . import pricing
from .grading import math_grade


def record_decision(
    *,
    name: str,
    model: str,
    chosen: Any,
    correct: Any,
    input_tokens: int,
    output_tokens: int,
    decision_type: Optional[str] = None,
    response_id: Optional[str] = None,
    explanation: Optional[str] = None,
    checker: Callable[[Any, Any], bool] = operator.eq,
    tracer_provider: Optional[trace.TracerProvider] = None,
) -> None:
    """Record one math-graded decision as a `gen_ai.evaluation.result` event.

    Args:
        name: What was graded - the low-cardinality metric id
            (`gen_ai.evaluation.name`), e.g. "route.fastest".
        model: The model that made the decision (`gen_ai.request.model`).
        chosen: The answer the AI chose.
        correct: The provably-correct answer; `checker` compares the two.
        input_tokens / output_tokens: Token counts for the model call, used to
            price the decision.
        decision_type: Optional kind of decision (`augmentloop.decision.type`).
        response_id: Optional id of the completion being graded
            (`gen_ai.response.id`); the correlation key back to the model call.
        explanation: Optional free-form reason (`gen_ai.evaluation.explanation`).
        checker: How to compare `chosen` and `correct`; equality by default.
        tracer_provider: SDK provider to emit through; defaults to the globally
            configured one. Injected by tests to capture the event in memory.
    """
    provider = tracer_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer("gradebook")

    grade = math_grade(chosen, correct, checker)
    cost_usd = pricing.price(model, input_tokens, output_tokens)

    # A leaf event span. With no explicit context it auto-parents to the active
    # operation span (the model-call span) when recording happens in that flow -
    # conventions doc section 2 ("SHOULD be parented to the operation span").
    span = tracer.start_span(conv.EVENT_NAME)
    try:
        # Standard slots + our two mandatory extensions (always present).
        span.set_attribute(conv.EVAL_NAME, name)
        span.set_attribute(conv.SCORE_VALUE, grade.value)
        span.set_attribute(conv.SCORE_LABEL, grade.label)
        span.set_attribute(conv.GRADE_SOURCE, grade.source.value)
        span.set_attribute(conv.COST_USD, cost_usd)

        # Recommended (section 7): echo model + tokens so the observatory is a
        # single-table query with no join. Always available here.
        span.set_attribute(conv.REQUEST_MODEL, model)
        span.set_attribute(conv.INPUT_TOKENS, input_tokens)
        span.set_attribute(conv.OUTPUT_TOKENS, output_tokens)

        # Optional: set only when provided, so we never emit empty/None values.
        if response_id is not None:
            span.set_attribute(conv.RESPONSE_ID, response_id)
        if decision_type is not None:
            span.set_attribute(conv.DECISION_TYPE, decision_type)
        if explanation is not None:
            span.set_attribute(conv.EXPLANATION, explanation)
    finally:
        span.end()
