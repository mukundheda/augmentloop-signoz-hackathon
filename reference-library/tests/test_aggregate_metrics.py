"""Ticket #7 - aggregate OTel metrics alongside the per-decision event.

Docs/conventions.md section 10 is the doc contract for these two instruments -
as in test_record_math_decision.py, assertions use literal names from that doc,
never the library's own constants (anti-tautology).
"""

import pytest


def _metrics_by_name(metric_reader) -> dict:
    """Collect emitted metrics keyed by instrument name."""
    data = metric_reader.get_metrics_data()
    out = {}
    if data is None:
        return out
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                out[metric.name] = metric
    return out


def test_math_decision_increments_the_decisions_graded_counter(
    tracer_provider, meter_provider, metric_reader
):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="A",
        correct="A",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    point = _metrics_by_name(metric_reader)["gradebook.decisions.graded"].data.data_points[0]
    assert point.value == 1
    assert point.attributes["augmentloop.grade.source"] == "math"
    assert point.attributes["gen_ai.evaluation.score.label"] == "correct"
    assert point.attributes["gen_ai.request.model"] == "anthropic/claude-3.5-haiku"


def test_math_decision_records_the_cost_histogram(
    tracer_provider, meter_provider, metric_reader
):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="A",
        correct="A",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    point = _metrics_by_name(metric_reader)["gradebook.decision.cost.usd"].data.data_points[0]
    # Same Haiku rate as test_cost_is_priced_from_the_table_and_attached.
    assert point.sum == pytest.approx(0.0048)
    assert point.count == 1


def test_incorrect_decision_still_counted_with_incorrect_label(
    tracer_provider, meter_provider, metric_reader
):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="B",
        correct="A",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    point = _metrics_by_name(metric_reader)["gradebook.decisions.graded"].data.data_points[0]
    assert point.value == 1
    assert point.attributes["gen_ai.evaluation.score.label"] == "incorrect"


def test_decisions_graded_counter_carries_decision_type_when_known(
    tracer_provider, meter_provider, metric_reader
):
    from gradebook import record_decision

    record_decision(
        name="quote.verbatim",
        model="anthropic/claude-3.5-haiku",
        chosen="hi",
        correct="hi",
        input_tokens=10,
        output_tokens=10,
        decision_type="quote_extraction",
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    point = _metrics_by_name(metric_reader)["gradebook.decisions.graded"].data.data_points[0]
    assert point.attributes["augmentloop.decision.type"] == "quote_extraction"


def test_reality_grade_without_cost_still_counted_but_no_histogram_point(
    tracer_provider, meter_provider, metric_reader
):
    from gradebook import capture_decision, record_reality_grade

    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("chat anthropic/claude-3.5-haiku"):
        ref = capture_decision(response_id="resp_1")

    record_reality_grade(
        ref,
        name="clip.kept",
        correct=True,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    metrics = _metrics_by_name(metric_reader)
    assert metrics["gradebook.decisions.graded"].data.data_points[0].value == 1
    assert metrics["gradebook.decisions.graded"].data.data_points[0].attributes[
        "augmentloop.grade.source"
    ] == "reality"
    assert "gradebook.decision.cost.usd" not in metrics


def test_reality_grade_with_cost_records_the_histogram(
    tracer_provider, meter_provider, metric_reader
):
    from gradebook import capture_decision, record_reality_grade

    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("chat anthropic/claude-3.5-haiku"):
        ref = capture_decision(response_id="resp_1")

    record_reality_grade(
        ref,
        name="clip.kept",
        correct=True,
        model="anthropic/claude-3.5-haiku",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    point = _metrics_by_name(metric_reader)["gradebook.decision.cost.usd"].data.data_points[0]
    assert point.sum == pytest.approx(0.0048)


def test_cost_histogram_point_carries_an_exemplar_pointing_at_the_eval_span(
    tracer_provider, exporter, meter_provider, metric_reader
):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="A",
        correct="A",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    eval_span = exporter.get_finished_spans()[0]
    point = _metrics_by_name(metric_reader)["gradebook.decision.cost.usd"].data.data_points[0]

    # The default TraceBasedExemplarFilter attaches an exemplar because the
    # metric is recorded while the eval-result span is current (docs/
    # conventions.md section 10) - it must point at that exact span.
    assert len(point.exemplars) == 1
    exemplar = point.exemplars[0]
    assert exemplar.span_id == eval_span.context.span_id
    assert exemplar.trace_id == eval_span.context.trace_id


def test_no_metrics_emitted_when_pricing_fails_loud(
    tracer_provider, meter_provider, metric_reader
):
    from gradebook import record_decision
    from gradebook.pricing import UnknownModelError

    with pytest.raises(UnknownModelError):
        record_decision(
            name="route.fastest",
            model="totally/unpriced-model",
            chosen="A",
            correct="A",
            input_tokens=10,
            output_tokens=10,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )

    assert _metrics_by_name(metric_reader) == {}
