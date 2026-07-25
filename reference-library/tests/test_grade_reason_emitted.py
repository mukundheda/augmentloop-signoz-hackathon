"""Ticket #42 - the reason sub-code reaches the wire.

Asserts on emitted telemetry (the literal `augmentloop.grade.reason` attribute),
never on library internals - same discipline as the other recorder tests.
"""


def test_bool_checker_emits_match_reason(tracer_provider, exporter):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="A",
        correct="A",
        input_tokens=10,
        output_tokens=10,
        tracer_provider=tracer_provider,
    )
    span = exporter.get_finished_spans()[0]
    # A plain-bool checker (the default operator.eq) still yields a reason code.
    assert span.attributes["augmentloop.grade.reason"] == "match"
    assert span.attributes["gen_ai.evaluation.score.label"] == "correct"


def test_reusable_checker_emits_its_reason(tracer_provider, exporter):
    from gradebook import record_decision, verbatim_substring

    record_decision(
        name="quote.verbatim",
        model="anthropic/claude-3.5-haiku",
        chosen="not in the text",
        correct="a totally different reference string",
        input_tokens=10,
        output_tokens=10,
        checker=verbatim_substring,
        tracer_provider=tracer_provider,
    )
    span = exporter.get_finished_spans()[0]
    assert span.attributes["augmentloop.grade.reason"] == "mismatch"
    assert span.attributes["gen_ai.evaluation.score.label"] == "incorrect"


def test_empty_answer_reason_survives_to_the_wire(tracer_provider, exporter):
    from gradebook import record_decision, verbatim_substring

    record_decision(
        name="quote.verbatim",
        model="anthropic/claude-3.5-haiku",
        chosen="   ",  # model produced nothing checkable
        correct="a reference the quote should have come from",
        input_tokens=10,
        output_tokens=10,
        checker=verbatim_substring,
        tracer_provider=tracer_provider,
    )
    span = exporter.get_finished_spans()[0]
    # "not machine-checkable" is a specific, queryable reason, not a generic fail.
    assert span.attributes["augmentloop.grade.reason"] == "empty_answer"
    assert span.attributes["gen_ai.evaluation.score.label"] == "incorrect"


def test_reason_is_a_metric_dimension(tracer_provider, metric_reader, meter_provider):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="A",
        correct="B",
        input_tokens=10,
        output_tokens=10,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    data = metric_reader.get_metrics_data()
    points = [
        p
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "gradebook.decisions.graded"
        for p in m.data.data_points
    ]
    assert points, "counter should have a data point"
    assert points[0].attributes["augmentloop.grade.reason"] == "mismatch"
