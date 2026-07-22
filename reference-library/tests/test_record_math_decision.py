"""Ticket #5 - record one math-graded decision.

Assertions use the *literal* frozen attribute names from the conventions doc
(docs/conventions.md section 9), not the library's own constants. The conventions
doc is the independent source of truth; asserting the library's constants against
themselves would be tautological.
"""

import pytest


def test_correct_math_decision_emits_standard_event(tracer_provider, exporter):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="A",
        correct="A",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
    )

    spans = exporter.get_finished_spans()
    assert len(spans) == 1, "exactly one gen_ai.evaluation.result event per decision"
    span = spans[0]

    # The standard OpenTelemetry event and its standard slots
    assert span.name == "gen_ai.evaluation.result"
    assert span.attributes["gen_ai.evaluation.name"] == "route.fastest"
    assert span.attributes["gen_ai.evaluation.score.value"] == 1.0
    assert span.attributes["gen_ai.evaluation.score.label"] == "correct"

    # Our mandatory extension: grade source is stamped on every event
    assert span.attributes["augmentloop.grade.source"] == "math"


def test_incorrect_math_decision_scores_zero(tracer_provider, exporter):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="B",          # the AI picked B...
        correct="A",         # ...but A was the provably-fastest route
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
    )

    span = exporter.get_finished_spans()[0]
    assert span.attributes["gen_ai.evaluation.score.value"] == 0.0
    assert span.attributes["gen_ai.evaluation.score.label"] == "incorrect"
    assert span.attributes["augmentloop.grade.source"] == "math"


def test_cost_is_priced_from_the_table_and_attached(tracer_provider, exporter):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="A",
        correct="A",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
    )

    span = exporter.get_finished_spans()[0]
    # Claude Haiku 3.5 list price: $0.80 / 1M input, $4.00 / 1M output.
    # 1000 in x $0.80/1e6 + 1000 out x $4.00/1e6 = 0.0008 + 0.0040 = 0.0048.
    assert span.attributes["augmentloop.cost.usd"] == pytest.approx(0.0048)


def test_unknown_model_fails_loud_and_emits_no_partial_event(tracer_provider, exporter):
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
        )

    # Pricing runs before the event is created, so a pricing failure never leaks
    # a half-populated event with a missing cost.
    assert exporter.get_finished_spans() == ()


def test_negative_tokens_fail_loud_and_emit_no_event(tracer_provider, exporter):
    from gradebook import record_decision
    from gradebook.pricing import InvalidTokenCountError

    # A malformed (negative) token count would otherwise produce a wrong-signed
    # cost and silently corrupt the headline "cost per correct" - fail loud
    # instead, consistent with the unknown-model path.
    with pytest.raises(InvalidTokenCountError):
        record_decision(
            name="route.fastest",
            model="anthropic/claude-3.5-haiku",
            chosen="A",
            correct="A",
            input_tokens=-1,
            output_tokens=10,
            tracer_provider=tracer_provider,
        )

    assert exporter.get_finished_spans() == ()


def test_recommended_and_optional_attributes_carried_when_provided(tracer_provider, exporter):
    from gradebook import record_decision

    record_decision(
        name="quote.verbatim",
        model="anthropic/claude-3.5-haiku",
        chosen="hello world",
        correct="hello world",
        input_tokens=250,
        output_tokens=8,
        decision_type="quote_extraction",
        response_id="resp_abc123",
        explanation="chose the verbatim substring",
        tracer_provider=tracer_provider,
    )

    attrs = exporter.get_finished_spans()[0].attributes
    # Recommended: model + token counts echoed for join-free dashboards (section 7)
    assert attrs["gen_ai.request.model"] == "anthropic/claude-3.5-haiku"
    assert attrs["gen_ai.usage.input_tokens"] == 250
    assert attrs["gen_ai.usage.output_tokens"] == 8
    # Correlation + optional context
    assert attrs["gen_ai.response.id"] == "resp_abc123"
    assert attrs["augmentloop.decision.type"] == "quote_extraction"
    assert attrs["gen_ai.evaluation.explanation"] == "chose the verbatim substring"


def test_optional_attributes_absent_when_not_provided(tracer_provider, exporter):
    from gradebook import record_decision

    record_decision(
        name="route.fastest",
        model="anthropic/claude-3.5-haiku",
        chosen="A",
        correct="A",
        input_tokens=1,
        output_tokens=1,
        tracer_provider=tracer_provider,
    )

    attrs = exporter.get_finished_spans()[0].attributes
    # We omit optional attributes rather than emit empty/None values.
    assert "gen_ai.response.id" not in attrs
    assert "augmentloop.decision.type" not in attrs
    assert "gen_ai.evaluation.explanation" not in attrs


def test_custom_checker_decides_the_math_grade(tracer_provider, exporter):
    from gradebook import record_decision

    # "Hello" != "hello" under the default equality checker (would grade
    # incorrect); a case-insensitive checker must grade it correct - proving the
    # grader is pluggable, not hardwired to equality.
    record_decision(
        name="quote.verbatim",
        model="anthropic/claude-3.5-haiku",
        chosen="Hello",
        correct="hello",
        input_tokens=10,
        output_tokens=10,
        checker=lambda chosen, correct: chosen.lower() == correct.lower(),
        tracer_provider=tracer_provider,
    )

    span = exporter.get_finished_spans()[0]
    assert span.attributes["gen_ai.evaluation.score.value"] == 1.0
    assert span.attributes["gen_ai.evaluation.score.label"] == "correct"


def test_cost_is_looked_up_per_model(tracer_provider, exporter):
    from gradebook import record_decision

    # A different pricing-table row must yield a different cost, proving the
    # price is keyed per-model, not coincidentally correct for one row.
    record_decision(
        name="route.fastest",
        model="google/gemini-2.0-flash",
        chosen="A",
        correct="A",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
    )

    span = exporter.get_finished_spans()[0]
    # Gemini 2.0 Flash table rate: $0.10 / 1M input, $0.40 / 1M output.
    # 1000 in x $0.10/1e6 + 1000 out x $0.40/1e6 = 0.0001 + 0.0004 = 0.0005.
    assert span.attributes["augmentloop.cost.usd"] == pytest.approx(0.0005)
