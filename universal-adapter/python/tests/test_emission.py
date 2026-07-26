"""Emission: the existing gradebook contract, and nothing new invented.

Assertions here are on the EMITTED telemetry, using the literal attribute names
from docs/conventions.md rather than any constant, exactly as the reference
library's own tests do. If this package ever needed a new attribute name to
express itself, that would be the signal that it had stopped being an adapter.
"""

from __future__ import annotations

import pytest
from support import bundle, inline, usage

from gradebook.checkers import ReasonCode
from gradebook.grading import GradeSource
from gradebook_adapter.costing import DecisionCost
from gradebook_adapter.emission import (
    AuthorityNotEmittableError,
    CostNotRepresentableError,
    NotGradedError,
    capture_pending_decision,
    emit_graded_decision,
    emit_reality_outcome,
    redact,
)
from gradebook_adapter.evaluation import EvaluationResult
from gradebook_adapter.models import CostProvenance, OutcomeRecord

SECRET = "sk-live-abcdef0123456789"

# Metric attributes gradebook itself defines. Anything outside this set on a
# metric data point would be a cardinality leak introduced by this package.
ALLOWED_METRIC_KEYS = {
    "augmentloop.grade.source",
    "gen_ai.evaluation.score.label",
    "gen_ai.request.model",
    "augmentloop.decision.type",
    "augmentloop.grade.reason",
}


def result(*, passed: bool = True, graded: bool = True,
           authority: GradeSource = GradeSource.MATH,
           detail: str = "npm test exited 0") -> EvaluationResult:
    return EvaluationResult(
        decision_id="decision-017",
        decision_type="task_completion",
        evaluation_name="repository.tests_pass",
        evaluator_kind="command_exit_code",
        graded=graded,
        passed=passed and graded,
        authority=authority if graded else None,
        reason=(ReasonCode.MATCH if passed else ReasonCode.MISMATCH) if graded
        else ReasonCode.EMPTY_ANSWER,
        detail=detail,
    )


def test_a_graded_decision_emits_the_standard_event(tracer_provider, exporter,
                                                    meter_provider) -> None:
    emit_graded_decision(
        bundle(decision_id="decision-017", response_id="response-abc"),
        result(),
        usage=(usage("usage-1"),),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "gen_ai.evaluation.result"
    assert span.attributes["gen_ai.evaluation.name"] == "repository.tests_pass"
    assert span.attributes["gen_ai.evaluation.score.value"] == 1.0
    assert span.attributes["gen_ai.evaluation.score.label"] == "correct"
    assert span.attributes["augmentloop.grade.source"] == "math"
    assert span.attributes["augmentloop.decision.type"] == "task_completion"
    assert span.attributes["gen_ai.response.id"] == "response-abc"
    assert span.attributes["augmentloop.cost.usd"] > 0


def test_the_evaluator_verdict_is_replayed_and_never_re_graded(tracer_provider,
                                                               exporter) -> None:
    emit_graded_decision(
        bundle(decision_id="decision-017", chosen=inline("anything at all")),
        result(passed=False),
        usage=(usage("usage-1"),),
        tracer_provider=tracer_provider,
    )
    span = exporter.get_finished_spans()[0]
    assert span.attributes["gen_ai.evaluation.score.label"] == "incorrect"
    assert span.attributes["augmentloop.grade.reason"] == "mismatch"


def test_an_ungraded_decision_is_refused(tracer_provider, exporter) -> None:
    with pytest.raises(NotGradedError):
        emit_graded_decision(bundle(), result(graded=False),
                             usage=(usage("usage-1"),),
                             tracer_provider=tracer_provider)
    assert exporter.get_finished_spans() == ()


def test_an_ai_judge_verdict_never_goes_out_as_math(tracer_provider) -> None:
    """The single failure this whole protocol exists to prevent."""
    with pytest.raises(AuthorityNotEmittableError) as excinfo:
        emit_graded_decision(bundle(), result(authority=GradeSource.AI_JUDGE),
                             usage=(usage("usage-1"),),
                             tracer_provider=tracer_provider)
    assert "grade.source=math" in str(excinfo.value)


def test_missing_tokens_fail_loud_rather_than_becoming_zeros(tracer_provider) -> None:
    with pytest.raises(CostNotRepresentableError) as excinfo:
        emit_graded_decision(
            bundle(model=None), result(),
            usage=(usage("usage-1", model=None, input_tokens=None,
                         output_tokens=None),),
            tracer_provider=tracer_provider,
        )
    assert "Missing cost stays missing" in str(excinfo.value)


def test_a_provider_reported_cost_is_not_silently_re_estimated(tracer_provider,
                                                               exporter) -> None:
    """record_decision prices from tokens and takes no dollar figure, so the
    stronger source cannot be carried through it. Say so instead of lying."""
    cost = DecisionCost(decision_id="decision-017", cost_usd=0.42,
                        provenance=CostProvenance.PROVIDER_REPORTED,
                        usage_ids=("usage-1",))
    with pytest.raises(CostNotRepresentableError):
        emit_graded_decision(bundle(), result(), usage=(usage("usage-1"),),
                             cost=cost, tracer_provider=tracer_provider)

    emit_graded_decision(bundle(), result(), usage=(usage("usage-1"),), cost=cost,
                         tracer_provider=tracer_provider,
                         on_stronger_cost="reprice")
    assert len(exporter.get_finished_spans()) == 1


# --------------------------------------------------------------------------
# Reality outcomes
# --------------------------------------------------------------------------


def test_a_reality_outcome_links_back_to_its_decision(tracer_provider,
                                                      exporter) -> None:
    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("chat anthropic/claude-haiku-4.5") as span:
        ref = capture_pending_decision(bundle(response_id="response-abc"))
        decision_ctx = span.get_span_context()
    exporter.clear()

    outcome = OutcomeRecord(
        outcome_id="outcome-88", decision_id="decision-017",
        outcome_type="pull_request_merged", correct=True,
        observed_at="2026-07-27T10:00:00Z", explanation="merged by a human",
    )
    emit_reality_outcome(
        ref, outcome, evaluation_name="repository.tests_pass",
        decision_type="task_completion",
        cost=DecisionCost(decision_id="decision-017", cost_usd=0.42,
                          provenance=CostProvenance.PROVIDER_REPORTED,
                          usage_ids=("usage-1",)),
        tracer_provider=tracer_provider,
    )

    span = exporter.get_finished_spans()[0]
    assert span.attributes["augmentloop.grade.source"] == "reality"
    assert span.attributes["gen_ai.response.id"] == "response-abc"
    # The stronger cost survives here, because this seam accepts a figure.
    assert span.attributes["augmentloop.cost.usd"] == 0.42
    assert len(span.links) == 1
    assert span.links[0].context.span_id == decision_ctx.span_id


def test_a_reality_outcome_can_overturn_the_checker(tracer_provider,
                                                    exporter) -> None:
    tracer = tracer_provider.get_tracer("test-harness")
    with tracer.start_as_current_span("chat"):
        ref = capture_pending_decision(bundle(response_id="response-abc"))
    exporter.clear()

    emit_reality_outcome(
        ref,
        OutcomeRecord(outcome_id="o-1", decision_id="decision-017",
                      outcome_type="change_reverted", correct=False,
                      observed_at="2026-07-27T10:00:00Z"),
        evaluation_name="repository.tests_pass",
        tracer_provider=tracer_provider,
    )
    span = exporter.get_finished_spans()[0]
    assert span.attributes["gen_ai.evaluation.score.value"] == 0.0
    assert span.attributes["gen_ai.evaluation.score.label"] == "incorrect"


# --------------------------------------------------------------------------
# Privacy and redaction
# --------------------------------------------------------------------------


def test_redaction_removes_secret_shapes_and_keeps_the_rest() -> None:
    assert redact(f"failed with {SECRET}") == "failed with [redacted]"
    assert redact("Bearer abcdefghijklmnop") == "[redacted]"
    # Narrow on purpose: a greedy filter that ate model slugs would get disabled.
    assert redact("anthropic/claude-haiku-4.5") == "anthropic/claude-haiku-4.5"


def test_no_secret_reaches_a_span_attribute(tracer_provider, exporter,
                                            meter_provider) -> None:
    leaky = bundle(
        decision_id="decision-017",
        chosen=inline({"authorization": f"Bearer {SECRET}"}),
        metadata={"api_key": SECRET, "environment": "benchmark"},
        response_id=f"response-{SECRET}",
    )
    emit_graded_decision(
        leaky, result(detail=f"checker saw {SECRET}"),
        usage=(usage("usage-1"),),
        tracer_provider=tracer_provider, meter_provider=meter_provider,
    )

    span = exporter.get_finished_spans()[0]
    for key, value in span.attributes.items():
        assert SECRET not in str(value), f"{key} leaked a secret"
    # The payload itself never had a path to telemetry in the first place.
    assert not any("authorization" in str(v) for v in span.attributes.values())


def test_no_high_cardinality_value_reaches_a_metric_attribute(
    tracer_provider, meter_provider, metric_reader
) -> None:
    emit_graded_decision(
        bundle(decision_id="decision-017", run_id="run-42",
               metadata={"environment": "benchmark", "ticket": "PROJ-12345"}),
        result(),
        usage=(usage("usage-1"),),
        tracer_provider=tracer_provider, meter_provider=meter_provider,
    )

    points = []
    data = metric_reader.get_metrics_data()
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                points.extend(metric.data.data_points)
    assert points

    for point in points:
        attributes = dict(point.attributes or {})
        assert set(attributes) <= ALLOWED_METRIC_KEYS, (
            f"unexpected metric attribute(s): {set(attributes) - ALLOWED_METRIC_KEYS}"
        )
        joined = " ".join(str(v) for v in attributes.values())
        for high_cardinality in ("decision-017", "run-42", "PROJ-12345"):
            assert high_cardinality not in joined


def test_existing_gradebook_callers_are_unaffected(tracer_provider, exporter) -> None:
    """This package only calls the public seams; it never changes them."""
    from gradebook import record_decision

    record_decision(
        name="route.fastest", model="anthropic/claude-haiku-4.5",
        chosen="north", correct="north", input_tokens=10, output_tokens=5,
        tracer_provider=tracer_provider,
    )
    span = exporter.get_finished_spans()[0]
    assert span.attributes["augmentloop.grade.source"] == "math"
    assert span.attributes["gen_ai.evaluation.score.label"] == "correct"
