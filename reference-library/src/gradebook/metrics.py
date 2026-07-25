"""Aggregate OTel metrics alongside the per-decision event (ticket #7).

Docs/conventions.md section 10 is the contract this module applies: two
instruments, emitted from the same call that emits the `gen_ai.evaluation.result`
event, using the exact same attribute names as that event (no separate
vocabulary for spans vs metrics). `record()` must be called while the event's
span is current - that is what lets the SDK's default `TraceBasedExemplarFilter`
attach an exemplar (trace id + span id) to each data point.
"""

from __future__ import annotations

from typing import Optional

from opentelemetry import metrics

from . import conventions as conv

METER_NAME = "gradebook"


def record(
    *,
    grade_source: str,
    grade_label: str,
    cost_usd: Optional[float],
    model: Optional[str] = None,
    decision_type: Optional[str] = None,
    grade_reason: Optional[str] = None,
    meter_provider: Optional[metrics.MeterProvider] = None,
) -> None:
    """Increment the decisions-graded counter and record cost, if known.

    Call this while the decision's `gen_ai.evaluation.result` span is current
    (conventions doc section 10) so metric data points carry an exemplar
    pointing back at that exact span.
    """
    provider = meter_provider or metrics.get_meter_provider()
    meter = provider.get_meter(METER_NAME)

    attributes = {conv.GRADE_SOURCE: grade_source, conv.SCORE_LABEL: grade_label}
    if model is not None:
        attributes[conv.REQUEST_MODEL] = model
    if decision_type is not None:
        attributes[conv.DECISION_TYPE] = decision_type
    # Reason as a metric dimension so the dashboard can break grades down by it.
    if grade_reason is not None:
        attributes[conv.GRADE_REASON] = grade_reason

    meter.create_counter(
        conv.METRIC_DECISIONS_GRADED,
        unit="1",
        description="Count of graded AI decisions, by grade source and label",
    ).add(1, attributes)

    if cost_usd is not None:
        meter.create_histogram(
            conv.METRIC_DECISION_COST_USD,
            unit="usd",
            description="Cost in USD of a graded AI decision",
        ).record(cost_usd, attributes)
