"""Ticket C6 (#51) - structured logs for the genuine failure classes.

conventions.md §13. Like the event tests, these assert on the *emitted log* (the
contract): its failure class, its structured attributes, and that it carries the
current decision span's trace/span id automatically via the SDK LoggingHandler
bridge - the click-a-log-then-jump-to-the-decision-span payoff. They never assert
on library internals. Two of the three failure classes originate in this library
(pricing miss, missing response id); the budget-guard trip lives in the toy-world
run loop and is covered there.
"""

import pytest


def _only_record(log_exporter):
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1, "exactly one failure log per failure"
    return logs[0].log_record


def test_missing_response_id_logs_and_links_to_the_decision_span(
    tracer_provider, gradebook_log_bridge
):
    from gradebook import capture_decision
    from gradebook.recorder import MissingResponseIdError

    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("chat anthropic/claude-haiku-4.5") as span:
        decision_ctx = span.get_span_context()
        with pytest.raises(MissingResponseIdError):
            capture_decision(response_id=None)

    record = _only_record(gradebook_log_bridge)
    assert record.attributes["augmentloop.failure.class"] == "missing_response_id"
    # Carries the decision span's ids automatically - no trace-parser processor.
    assert record.trace_id == decision_ctx.trace_id
    assert record.span_id == decision_ctx.span_id


def test_unknown_model_pricing_miss_logs_and_links_to_the_decision_span(
    tracer_provider, gradebook_log_bridge
):
    from gradebook import record_decision
    from gradebook.pricing import UnknownModelError

    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("junction J1 decision") as span:
        decision_ctx = span.get_span_context()
        with pytest.raises(UnknownModelError):
            record_decision(
                name="route.fastest",
                model="totally/unpriced-model",
                chosen="A",
                correct="A",
                input_tokens=10,
                output_tokens=10,
                tracer_provider=tracer_provider,
            )

    record = _only_record(gradebook_log_bridge)
    assert record.attributes["augmentloop.failure.class"] == "unknown_model_pricing_miss"
    # The unpriced slug is on the log so a judge can see WHICH model missed.
    assert record.attributes["gen_ai.request.model"] == "totally/unpriced-model"
    assert record.trace_id == decision_ctx.trace_id
    assert record.span_id == decision_ctx.span_id


def test_negative_tokens_are_not_mislabelled_as_a_pricing_miss(
    tracer_provider, gradebook_log_bridge
):
    """A malformed token count is a different failure (InvalidTokenCountError);
    it must not be logged as an unknown-model pricing miss."""
    from gradebook import record_decision
    from gradebook.pricing import InvalidTokenCountError

    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("junction J1 decision"):
        with pytest.raises(InvalidTokenCountError):
            record_decision(
                name="route.fastest",
                model="anthropic/claude-haiku-4.5",
                chosen="A",
                correct="A",
                input_tokens=-1,
                output_tokens=10,
                tracer_provider=tracer_provider,
            )

    assert len(gradebook_log_bridge.get_finished_logs()) == 0


def test_a_graded_decision_emits_no_failure_log(tracer_provider, gradebook_log_bridge):
    """The failure logs are for failures only. A happy-path decision must NOT
    emit a log that just repeats its span attributes - that padding version is
    the gimmick §13 warns against."""
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-haiku-4.5",
        chosen="A",
        correct="A",
        input_tokens=10,
        output_tokens=10,
        tracer_provider=tracer_provider,
    )

    assert len(gradebook_log_bridge.get_finished_logs()) == 0
