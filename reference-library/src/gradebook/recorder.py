"""The public recording seams: `record_decision` and the deferred-grade pair
`capture_decision` / `record_reality_grade`.

Applies the conventions doc's contract: grade a decision, and emit one standard
`gen_ai.evaluation.result` event carrying the standard score slots plus
Gradebook's mandatory grade-source extension. A reality grade arrives later
than its decision, so it additionally span-links back to the decision span and
always carries `gen_ai.response.id` (conventions doc section 6, span-link
Role 1). The emitted telemetry - not these signatures - is the contract.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Callable, Optional

from opentelemetry import trace
from opentelemetry.metrics import MeterProvider

from . import conventions as conv
from . import logs as gb_logs
from . import metrics as gb_metrics
from . import pricing
from .grading import CORRECT, INCORRECT, CheckerResult, GradeSource, math_grade


class MissingResponseIdError(ValueError):
    """Raised when a decision is captured for deferred grading with no response id.

    Section 6 of the conventions doc: a deferred grade MUST set
    `gen_ai.response.id` as the always-present correlation fallback. Fail at
    capture time, when the caller can still supply it, not at grading time when
    the decision context is long gone.
    """


@dataclass(frozen=True)
class DecisionRef:
    """A durable handle to a decision awaiting a real-world verdict.

    Captures exactly what section 6 requires the late grade to carry: the
    decision span's context (for the span link) and the completion id (for
    `gen_ai.response.id`). Both fields are primitives-or-serializable so a ref
    can cross a process boundary (webhook, cron sweep) via `from_ids`.
    """

    span_context: trace.SpanContext
    response_id: str

    @classmethod
    def from_ids(cls, *, trace_id: int, span_id: int, response_id: str) -> "DecisionRef":
        """Rebuild a ref from persisted primitive ids in another process."""
        return cls(
            span_context=trace.SpanContext(
                trace_id=trace_id,
                span_id=span_id,
                is_remote=True,
                trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
            ),
            response_id=response_id,
        )


def capture_decision(*, response_id: Optional[str]) -> DecisionRef:
    """Capture the currently-active decision span for later reality grading.

    Call this inside the decision's flow (while the model-call span is the
    active span). The returned ref is everything `record_reality_grade` needs,
    now or in another process.
    """
    if response_id is None:
        # Log while the decision span is still current, then fail loud: the log
        # links to the exact span that was about to become ungradable (§13).
        gb_logs.missing_response_id()
        raise MissingResponseIdError(
            "a deferred grade MUST carry gen_ai.response.id (conventions "
            "section 6); supply the completion id at capture time"
        )
    return DecisionRef(
        span_context=trace.get_current_span().get_span_context(),
        response_id=response_id,
    )


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
    checker: Callable[[Any, Any], CheckerResult] = operator.eq,
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
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
        meter_provider: SDK provider for the aggregate metrics (conventions doc
            section 10); defaults to the globally configured one. Injected by
            tests to capture data points in memory.
    """
    provider = tracer_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer("gradebook")

    grade = math_grade(chosen, correct, checker)
    try:
        cost_usd = pricing.price(model, input_tokens, output_tokens)
    except pricing.UnknownModelError:
        # The caller's decision span is current here, so the log links to the
        # decision that could not be priced; then fail loud as before (§13). A
        # silently missing cost would corrupt the headline cost-per-correct.
        gb_logs.unknown_model_pricing_miss(model=model)
        raise

    # A leaf event span. With no explicit context it auto-parents to the active
    # operation span (the model-call span) when recording happens in that flow -
    # conventions doc section 2 ("SHOULD be parented to the operation span").
    # `start_as_current_span` also makes it the current span for the metrics
    # recorded below, so the default TraceBasedExemplarFilter can attach an
    # exemplar pointing back at it (section 10).
    with tracer.start_as_current_span(conv.EVENT_NAME) as span:
        # Standard slots + our two mandatory extensions (always present).
        span.set_attribute(conv.EVAL_NAME, name)
        span.set_attribute(conv.SCORE_VALUE, grade.value)
        span.set_attribute(conv.SCORE_LABEL, grade.label)
        span.set_attribute(conv.GRADE_SOURCE, grade.source.value)
        span.set_attribute(conv.COST_USD, cost_usd)
        # The reason sub-code (§12): why this grade got its label, queryable.
        if grade.reason is not None:
            span.set_attribute(conv.GRADE_REASON, grade.reason.value)

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

        gb_metrics.record(
            grade_source=grade.source.value,
            grade_label=grade.label,
            cost_usd=cost_usd,
            model=model,
            decision_type=decision_type,
            grade_reason=grade.reason.value if grade.reason is not None else None,
            meter_provider=meter_provider,
        )


def record_reality_grade(
    ref: DecisionRef,
    *,
    name: str,
    correct: bool,
    model: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    decision_type: Optional[str] = None,
    explanation: Optional[str] = None,
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
) -> None:
    """Grade a previously-captured decision by its real-world outcome.

    Emits the same standard `gen_ai.evaluation.result` event as
    `record_decision`, stamped `augmentloop.grade.source = "reality"`, with the
    two section-6 mandatory correlations: a span link back to the decision span
    and the decision's `gen_ai.response.id`.

    Args:
        ref: The handle captured at decision time (`capture_decision`) or
            rebuilt across a process boundary (`DecisionRef.from_ids`).
        name: What was graded (`gen_ai.evaluation.name`), e.g. "clip.kept".
        correct: The real-world verdict; a reality grade is binary.
        model / input_tokens / output_tokens: Optional; when all are known and
            `cost_usd` is not given, the decision is priced from the same
            single pricing table. When none of the three is known, no cost
            attribute is emitted (cost is only attached "where cost is known" -
            never a fabricated zero).
        cost_usd: Optional pre-computed dollar figure, for callers who already
            have an authoritative cost from the same underlying token data
            (e.g. a model provider's own billing telemetry) and want to attach
            it directly rather than re-deriving an approximation through
            gradebook's own pricing table. Takes priority over model/token
            pricing when provided; `model`/`input_tokens`/`output_tokens` may
            still be passed alongside it purely for the recommended
            `gen_ai.request.model` / `gen_ai.usage.*_tokens` fields (section 7).
        decision_type: Optional kind of decision (`augmentloop.decision.type`).
        explanation: Optional free-form reason (`gen_ai.evaluation.explanation`).
        tracer_provider: SDK provider to emit through; defaults to the globally
            configured one. Injected by tests to capture the event in memory.
        meter_provider: SDK provider for the aggregate metrics (conventions doc
            section 10); defaults to the globally configured one. Injected by
            tests to capture data points in memory.
    """
    provider = tracer_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer("gradebook")

    if cost_usd is None and (
        model is not None and input_tokens is not None and output_tokens is not None
    ):
        cost_usd = pricing.price(model, input_tokens, output_tokens)

    grade_label = CORRECT if correct else INCORRECT

    # Span-link Role 1 (section 6): the late grade links to the decision span
    # it judges. Links must be supplied at span creation in OTel.
    # `start_as_current_span` makes this span current for the metrics recorded
    # below, so the default TraceBasedExemplarFilter can exemplar-link back to
    # it (section 10) - a second, independent hop from the section-6 link.
    with tracer.start_as_current_span(
        conv.EVENT_NAME, links=[trace.Link(ref.span_context)]
    ) as span:
        span.set_attribute(conv.EVAL_NAME, name)
        span.set_attribute(conv.SCORE_VALUE, 1.0 if correct else 0.0)
        span.set_attribute(conv.SCORE_LABEL, grade_label)
        span.set_attribute(conv.GRADE_SOURCE, GradeSource.REALITY.value)
        # Section 6 MUST: the always-present correlation fallback.
        span.set_attribute(conv.RESPONSE_ID, ref.response_id)

        if cost_usd is not None:
            span.set_attribute(conv.COST_USD, cost_usd)
        if model is not None:
            span.set_attribute(conv.REQUEST_MODEL, model)
        if input_tokens is not None:
            span.set_attribute(conv.INPUT_TOKENS, input_tokens)
        if output_tokens is not None:
            span.set_attribute(conv.OUTPUT_TOKENS, output_tokens)
        if decision_type is not None:
            span.set_attribute(conv.DECISION_TYPE, decision_type)
        if explanation is not None:
            span.set_attribute(conv.EXPLANATION, explanation)

        gb_metrics.record(
            grade_source=GradeSource.REALITY.value,
            grade_label=grade_label,
            cost_usd=cost_usd,
            model=model,
            decision_type=decision_type,
            meter_provider=meter_provider,
        )
