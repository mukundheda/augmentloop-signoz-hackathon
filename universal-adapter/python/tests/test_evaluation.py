"""The seven evaluators, and the wall between evidence and authority.

The tests that matter most here are not the happy paths. They are the ones that
prove a harness cannot talk its way to a math grade: harness_claim carries no
authority, an outcome evaluator defers instead of deciding, and a checker that
the application registered as model-assisted cannot be promoted by editing a
manifest.
"""

from __future__ import annotations

import pytest
from support import bundle, inline

from gradebook.checkers import CheckResult, ReasonCode
from gradebook.grading import GradeSource
from gradebook_adapter.evaluation import (
    CheckerRegistry,
    EvaluationContext,
    HarnessClaimIsNotAuthorityError,
    InvalidManifestError,
    ManifestMismatchError,
    UnknownCheckerError,
    evaluate,
    gradeable_evidence,
    require_gradeable,
)
from gradebook_adapter.models import (
    Authority,
    CallbackEvaluator,
    CommandExitCodeEvaluator,
    CommandResultEvidence,
    Determinism,
    Digest,
    EvaluationManifest,
    ExactEqualityEvaluator,
    FileDigestEvaluator,
    FileStateEvidence,
    HarnessClaimEvidence,
    JsonEqualityEvaluator,
    JsonSchemaEvaluator,
    OutcomeEvaluator,
    StructuredOutputEvidence,
)

SHA = "a" * 64


def manifest(evaluator: object, *, authority: Authority = Authority.MATH,
             evaluation_name: str = "repository.tests_pass",
             decision_type: str = "task_completion") -> EvaluationManifest:
    return EvaluationManifest(
        task_id="repair-auth-017",
        decision_type=decision_type,
        evaluation_name=evaluation_name,
        authority=authority,
        evaluator=evaluator,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------
# Deterministic evaluators
# --------------------------------------------------------------------------


def test_exact_equality_grades_a_match_and_a_mismatch() -> None:
    good = evaluate(bundle(chosen=inline("search_database")),
                    manifest(ExactEqualityEvaluator(expected="search_database")))
    assert good.graded and good.passed
    assert good.authority is GradeSource.MATH
    assert good.reason is ReasonCode.MATCH

    bad = evaluate(bundle(chosen=inline("search_web")),
                   manifest(ExactEqualityEvaluator(expected="search_database")))
    assert bad.graded and not bad.passed
    assert bad.reason is ReasonCode.MISMATCH


def test_exact_equality_honours_its_normalization_options() -> None:
    evaluator = ExactEqualityEvaluator(expected="  Search_Database ",
                                       case_sensitive=False, trim_whitespace=True)
    assert evaluate(bundle(chosen=inline("search_database")),
                    manifest(evaluator)).passed


def test_exact_equality_does_not_coerce_across_json_types() -> None:
    result = evaluate(bundle(chosen=inline("1")),
                      manifest(ExactEqualityEvaluator(expected=1)))
    assert result.graded and not result.passed


def test_json_equality_is_key_order_insensitive_and_array_order_sensitive() -> None:
    expected = {"tools": ["a", "b"], "n": 1}
    assert evaluate(bundle(chosen=inline({"n": 1, "tools": ["a", "b"]})),
                    manifest(JsonEqualityEvaluator(expected=expected))).passed
    assert not evaluate(bundle(chosen=inline({"n": 1, "tools": ["b", "a"]})),
                        manifest(JsonEqualityEvaluator(expected=expected))).passed


def test_json_equality_treats_true_and_one_as_different() -> None:
    assert not evaluate(bundle(chosen=inline(1)),
                        manifest(JsonEqualityEvaluator(expected=True))).passed


def test_json_schema_evaluator_proves_shape() -> None:
    schema = {"type": "object", "required": ["ticket"],
              "properties": {"ticket": {"type": "string"}}}
    assert evaluate(bundle(chosen=inline({"ticket": "T-1"})),
                    manifest(JsonSchemaEvaluator(schema=schema))).passed
    failed = evaluate(bundle(chosen=inline({"ticket": 7})),
                      manifest(JsonSchemaEvaluator(schema=schema)))
    assert failed.graded and not failed.passed


def test_command_exit_code_grades_the_command_the_manifest_named() -> None:
    evidence = (CommandResultEvidence(evidence_id="e-1", command_name="npm test",
                                      exit_code=0),)
    evaluator = CommandExitCodeEvaluator(command=("npm", "test"), expected_exit_code=0)
    result = evaluate(bundle(evidence=evidence), manifest(evaluator))
    assert result.passed and result.authority is GradeSource.MATH

    failing = (CommandResultEvidence(evidence_id="e-1", command_name="npm test",
                                     exit_code=1),)
    beaten = evaluate(bundle(evidence=failing), manifest(evaluator))
    assert beaten.graded and not beaten.passed


def test_command_exit_code_matches_on_argv_head_too() -> None:
    evidence = (CommandResultEvidence(evidence_id="e-1", command_name="npm",
                                      exit_code=0),)
    evaluator = CommandExitCodeEvaluator(command=("npm", "test"), expected_exit_code=0)
    assert evaluate(bundle(evidence=evidence), manifest(evaluator)).passed


def test_command_exit_code_falls_back_to_the_only_command_result() -> None:
    evidence = (CommandResultEvidence(evidence_id="e-1",
                                      command_name="project-test-suite",
                                      exit_code=0),)
    evaluator = CommandExitCodeEvaluator(command=("npm", "test"), expected_exit_code=0)
    assert evaluate(bundle(evidence=evidence), manifest(evaluator)).passed


def test_command_exit_code_cannot_decide_with_no_evidence_or_with_two() -> None:
    evaluator = CommandExitCodeEvaluator(command=("npm", "test"), expected_exit_code=0)

    none_at_all = evaluate(bundle(), manifest(evaluator))
    assert not none_at_all.graded
    assert none_at_all.reason is ReasonCode.NO_GROUND_TRUTH

    two = (
        CommandResultEvidence(evidence_id="e-1", command_name="lint", exit_code=0),
        CommandResultEvidence(evidence_id="e-2", command_name="build", exit_code=1),
    )
    # Choosing between two exit codes would be choosing the answer.
    ambiguous = evaluate(bundle(evidence=two), manifest(evaluator))
    assert not ambiguous.graded
    assert ambiguous.reason is ReasonCode.AMBIGUOUS


def test_a_harness_claim_is_invisible_to_the_command_evaluator() -> None:
    claim = HarnessClaimEvidence(evidence_id="e-claim", claim={"exit_code": 0})
    evaluator = CommandExitCodeEvaluator(command=("npm", "test"), expected_exit_code=0)
    result = evaluate(bundle(evidence=(claim,)), manifest(evaluator))
    assert not result.graded
    assert result.reason is ReasonCode.NO_GROUND_TRUTH


def test_file_digest_compares_the_manifest_hash_to_reported_state() -> None:
    evaluator = FileDigestEvaluator(path="dist/app.js", expected=Digest(digest=SHA))
    matching = (FileStateEvidence(evidence_id="e-1", path="dist/app.js",
                                  artifact_digest=Digest(digest=SHA)),)
    assert evaluate(bundle(evidence=matching), manifest(evaluator)).passed

    other = (FileStateEvidence(evidence_id="e-1", path="dist/app.js",
                               artifact_digest=Digest(digest="b" * 64)),)
    beaten = evaluate(bundle(evidence=other), manifest(evaluator))
    assert beaten.graded and not beaten.passed

    unreported = evaluate(bundle(), manifest(evaluator))
    assert not unreported.graded
    assert unreported.reason is ReasonCode.NO_GROUND_TRUTH


def test_callback_runs_an_application_checker_by_name() -> None:
    registry = CheckerRegistry()
    registry.register("answer_is_42", lambda value, options: True,
                      determinism=Determinism.DETERMINISTIC)
    evaluator = CallbackEvaluator(name="answer_is_42",
                                  determinism=Determinism.DETERMINISTIC)
    result = evaluate(bundle(chosen=inline(42)), manifest(evaluator),
                      context=EvaluationContext(checkers=registry))
    assert result.passed and result.authority is GradeSource.MATH
    assert result.counts_as_correct is True


def test_an_unregistered_checker_fails_loud() -> None:
    evaluator = CallbackEvaluator(name="never_registered",
                                  determinism=Determinism.DETERMINISTIC)
    with pytest.raises(UnknownCheckerError):
        evaluate(bundle(), manifest(evaluator), context=EvaluationContext())


def test_outcome_evaluator_defers_instead_of_deciding() -> None:
    result = evaluate(bundle(),
                      manifest(OutcomeEvaluator(outcome_type="pull_request_merged"),
                               authority=Authority.REALITY))
    assert result.deferred
    assert not result.graded
    assert result.authority is None


# --------------------------------------------------------------------------
# Authority
# --------------------------------------------------------------------------


def test_harness_success_is_not_authority() -> None:
    """The flagship invariant: success=true grades nothing."""
    claim = HarnessClaimEvidence(evidence_id="e-1", claim={"success": True})
    subject = bundle(evidence=(claim,))

    # 1. It is not even visible to a grader.
    assert gradeable_evidence(subject) == ()

    # 2. Offering it to one is an error, not a grade.
    with pytest.raises(HarnessClaimIsNotAuthorityError):
        require_gradeable(claim)

    # 3. And a decision whose only evidence is a claim stays ungraded.
    result = evaluate(subject, manifest(ExactEqualityEvaluator(expected=True)))
    assert not result.graded
    assert result.authority is None
    assert result.reason is ReasonCode.EMPTY_ANSWER


def test_structured_output_evidence_can_be_graded_but_a_claim_cannot() -> None:
    claim = HarnessClaimEvidence(evidence_id="e-claim", claim={"success": True})
    output = StructuredOutputEvidence(evidence_id="e-out", output=inline("done"))
    result = evaluate(bundle(evidence=(claim, output)),
                      manifest(ExactEqualityEvaluator(expected="done")))
    assert result.passed
    assert result.detail.startswith("compared evidence e-out")


def test_math_authority_is_refused_for_an_outcome_evaluator() -> None:
    with pytest.raises(InvalidManifestError):
        evaluate(bundle(), manifest(OutcomeEvaluator(outcome_type="merged"),
                                    authority=Authority.MATH))


def test_reality_authority_is_refused_for_a_checker_that_runs_now() -> None:
    with pytest.raises(InvalidManifestError):
        evaluate(bundle(), manifest(ExactEqualityEvaluator(expected="x"),
                                    authority=Authority.REALITY))


def test_a_manifest_for_another_decision_type_is_refused() -> None:
    with pytest.raises(ManifestMismatchError):
        evaluate(bundle(decision_type="tool_choice"),
                 manifest(ExactEqualityEvaluator(expected="x")))


def test_a_manifest_for_another_evaluation_name_is_refused() -> None:
    with pytest.raises(ManifestMismatchError):
        evaluate(bundle(), manifest(ExactEqualityEvaluator(expected="x"),
                                    evaluation_name="repository.builds"))


# --------------------------------------------------------------------------
# Callback determinism: manifest versus registry
# --------------------------------------------------------------------------


def test_registration_demands_a_determinism_declaration() -> None:
    registry = CheckerRegistry()
    with pytest.raises(TypeError):
        registry.register("x", lambda value, options: True)  # type: ignore[call-arg]


def test_a_manifest_cannot_promote_a_model_assisted_checker() -> None:
    """The disagreement case: the path a careless integrator actually takes.

    The checker still runs, because its opinion is worth having. What it does not
    get is math authority, and the downgrade is recorded rather than inferred.
    """
    registry = CheckerRegistry()
    registry.register("llm_pairwise_judge", lambda value, options: True,
                      determinism=Determinism.MODEL_ASSISTED)
    lying = CallbackEvaluator(name="llm_pairwise_judge",
                              determinism=Determinism.DETERMINISTIC)

    result = evaluate(bundle(chosen=inline("x")),
                      manifest(lying, authority=Authority.MATH),
                      context=EvaluationContext(checkers=registry))

    assert result.graded and result.passed
    assert result.authority is GradeSource.AI_JUDGE
    assert result.authority_downgraded_from is GradeSource.MATH
    # The one that matters: it never enters the headline metric.
    assert result.counts_as_correct is False
    assert "registry is closer to the code" in result.detail


def test_a_model_assisted_checker_still_runs_and_is_graded_ai_judge() -> None:
    registry = CheckerRegistry()
    registry.register("llm_pairwise_judge",
                      lambda value, options: CheckResult.decided(True),
                      determinism=Determinism.MODEL_ASSISTED)
    honest = CallbackEvaluator(name="llm_pairwise_judge",
                               determinism=Determinism.MODEL_ASSISTED)
    result = evaluate(bundle(chosen=inline("x")),
                      manifest(honest, authority=Authority.AI_JUDGE),
                      context=EvaluationContext(checkers=registry))
    assert result.graded and result.passed
    assert result.authority is GradeSource.AI_JUDGE


def test_a_deterministic_checker_may_be_declared_less_than_it_is() -> None:
    """Downgrades are safe, so this is allowed and lands on ai_judge."""
    registry = CheckerRegistry()
    registry.register("tests_pass", lambda value, options: True,
                      determinism=Determinism.DETERMINISTIC)
    modest = CallbackEvaluator(name="tests_pass",
                               determinism=Determinism.MODEL_ASSISTED)
    result = evaluate(bundle(chosen=inline("x")),
                      manifest(modest, authority=Authority.AI_JUDGE),
                      context=EvaluationContext(checkers=registry))
    assert result.graded
    assert result.authority is GradeSource.AI_JUDGE
    assert result.authority_downgraded_from is None


def test_registering_the_same_name_twice_is_refused() -> None:
    registry = CheckerRegistry()
    registry.register("x", lambda value, options: True,
                      determinism=Determinism.DETERMINISTIC)
    with pytest.raises(Exception):
        registry.register("x", lambda value, options: True,
                          determinism=Determinism.MODEL_ASSISTED)


def test_an_empty_inline_answer_is_not_a_wrong_answer() -> None:
    """An empty string or null is a gap in the capture, not a wrong choice."""
    for empty in ("", None):
        result = evaluate(bundle(chosen=inline(empty)),
                          manifest(ExactEqualityEvaluator(expected="x")))
        assert not result.graded
        assert result.reason is ReasonCode.EMPTY_ANSWER


def test_a_digest_chosen_value_is_not_guessed_at() -> None:
    from gradebook_adapter.models import DigestValue

    result = evaluate(bundle(chosen=DigestValue(digest=SHA)),
                      manifest(ExactEqualityEvaluator(expected="x")))
    assert not result.graded
    assert result.reason is ReasonCode.AMBIGUOUS


def test_json_schema_evaluator_ignores_unsupported_keywords() -> None:
    """The subset is documented, so an author knows what is NOT enforced."""
    from gradebook_adapter.evaluation import JSON_SCHEMA_KEYWORDS

    assert "allOf" not in JSON_SCHEMA_KEYWORDS
    schema = {"type": "object", "allOf": [{"required": ["never"]}]}
    assert evaluate(bundle(chosen=inline({"a": 1})),
                    manifest(JsonSchemaEvaluator(schema=schema))).passed
