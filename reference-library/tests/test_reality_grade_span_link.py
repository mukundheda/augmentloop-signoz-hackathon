"""Ticket #8 - reality grade source + span-link Role 1.

A decision is recorded now; the real world proves it right or wrong later. The
late grade emits the same standard event, stamped `reality`, and MUST both
span-link back to the decision span and carry `gen_ai.response.id`
(conventions doc section 6).

As in test_record_math_decision.py, assertions use the literal frozen attribute
names from docs/conventions.md section 9, never the library's own constants.
"""

import pytest
from opentelemetry import trace


def _capture_ref_during_decision(tracer_provider, response_id="resp_decision_1"):
    """Simulate a decision happening inside a model-call span and capture it."""
    from gradebook import capture_decision

    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("chat anthropic/claude-3.5-haiku") as span:
        ref = capture_decision(response_id=response_id)
        decision_ctx = span.get_span_context()
    return ref, decision_ctx


def test_late_reality_grade_links_back_to_the_decision_span(tracer_provider, exporter):
    from gradebook import record_reality_grade

    ref, decision_ctx = _capture_ref_during_decision(tracer_provider)
    exporter.clear()  # the decision span itself is not under test

    # ...time passes; the clip is kept / the appointment lands...
    record_reality_grade(
        ref,
        name="clip.kept",
        correct=True,
        tracer_provider=tracer_provider,
    )

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    grade_span = spans[0]

    assert grade_span.name == "gen_ai.evaluation.result"
    assert grade_span.attributes["augmentloop.grade.source"] == "reality"

    # Span-link Role 1: the late grade is one hop from the decision it judges.
    assert len(grade_span.links) == 1
    link_ctx = grade_span.links[0].context
    assert link_ctx.trace_id == decision_ctx.trace_id
    assert link_ctx.span_id == decision_ctx.span_id


def test_reality_grade_carries_the_mandatory_response_id(tracer_provider, exporter):
    from gradebook import record_reality_grade

    ref, _ = _capture_ref_during_decision(tracer_provider, response_id="resp_abc")
    exporter.clear()

    record_reality_grade(
        ref, name="clip.kept", correct=True, tracer_provider=tracer_provider
    )

    attrs = exporter.get_finished_spans()[0].attributes
    # Section 6: deferred grades MUST set gen_ai.response.id as the
    # always-present correlation fallback.
    assert attrs["gen_ai.response.id"] == "resp_abc"


def test_capture_without_response_id_fails_loud():
    from gradebook import capture_decision
    from gradebook.recorder import MissingResponseIdError

    # A deferred grade with no response id would violate the section 6 MUST and
    # leave the grade unlinkable across process/time boundaries - fail at
    # capture time, when the caller can still fix it, not at grading time.
    with pytest.raises(MissingResponseIdError):
        capture_decision(response_id=None)


def test_correct_and_incorrect_outcomes_encode_like_math_grades(
    tracer_provider, exporter
):
    from gradebook import record_reality_grade

    ref, _ = _capture_ref_during_decision(tracer_provider)
    exporter.clear()

    record_reality_grade(
        ref, name="clip.kept", correct=False, tracer_provider=tracer_provider
    )

    attrs = exporter.get_finished_spans()[0].attributes
    assert attrs["gen_ai.evaluation.score.value"] == 0.0
    assert attrs["gen_ai.evaluation.score.label"] == "incorrect"
    assert attrs["augmentloop.grade.source"] == "reality"


def test_cost_attached_only_when_tokens_are_known(tracer_provider, exporter):
    from gradebook import record_reality_grade

    ref, _ = _capture_ref_during_decision(tracer_provider)
    exporter.clear()

    # With model + tokens: cost priced from the same single pricing table.
    record_reality_grade(
        ref,
        name="clip.kept",
        correct=True,
        model="anthropic/claude-3.5-haiku",
        input_tokens=1000,
        output_tokens=1000,
        tracer_provider=tracer_provider,
    )
    # Without them: no cost attribute at all (cost is "on decisions where cost
    # is known", never a fabricated zero).
    record_reality_grade(
        ref, name="clip.kept", correct=True, tracer_provider=tracer_provider
    )

    priced, unpriced = exporter.get_finished_spans()
    assert priced.attributes["augmentloop.cost.usd"] == pytest.approx(0.0048)
    assert "augmentloop.cost.usd" not in unpriced.attributes


def test_ref_survives_a_process_boundary_via_ids(tracer_provider, exporter):
    from gradebook import DecisionRef, record_reality_grade

    _, decision_ctx = _capture_ref_during_decision(tracer_provider)
    exporter.clear()

    # A reality outcome usually arrives in another process (a webhook, a cron
    # sweep). Rebuild the ref from persisted primitive ids and grade there.
    rebuilt = DecisionRef.from_ids(
        trace_id=decision_ctx.trace_id,
        span_id=decision_ctx.span_id,
        response_id="resp_decision_1",
    )
    record_reality_grade(
        rebuilt, name="clip.kept", correct=True, tracer_provider=tracer_provider
    )

    grade_span = exporter.get_finished_spans()[0]
    link_ctx = grade_span.links[0].context
    assert link_ctx.trace_id == decision_ctx.trace_id
    assert link_ctx.span_id == decision_ctx.span_id
    assert grade_span.attributes["gen_ai.response.id"] == "resp_decision_1"


def test_optional_context_attributes_carried_when_provided(tracer_provider, exporter):
    from gradebook import record_reality_grade

    ref, _ = _capture_ref_during_decision(tracer_provider)
    exporter.clear()

    record_reality_grade(
        ref,
        name="clip.kept",
        correct=True,
        decision_type="clip_scoring",
        explanation="clip was kept by the editor",
        tracer_provider=tracer_provider,
    )

    attrs = exporter.get_finished_spans()[0].attributes
    assert attrs["augmentloop.decision.type"] == "clip_scoring"
    assert attrs["gen_ai.evaluation.explanation"] == "clip was kept by the editor"
