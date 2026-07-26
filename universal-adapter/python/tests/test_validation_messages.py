"""Validation behaviour that the corpus cannot express: the SHAPE of the errors.

The parity test proves the verdicts are right. These prove the errors are worth
reading, which is a separate acceptance criterion and the one an integrator
actually experiences.
"""

from __future__ import annotations

from typing import Any

import pytest

from gradebook_adapter.validation import (
    UnknownRecordTypeError,
    validate_decision_evidence_bundle,
    validate_evaluation_manifest,
    validate_record,
    validate_usage_record,
)


def _minimal_bundle() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "decision": {
            "decision_type": "task_completion",
            "evaluation_name": "repository.tests_pass",
            "chosen": {"kind": "absent", "reason": "not_captured"},
        },
        "subject": {"harness": "hermes", "run_id": "run-42"},
        "evidence": [],
    }


def test_a_valid_minimal_bundle_produces_no_errors() -> None:
    assert validate_decision_evidence_bundle(_minimal_bundle()) == []


def test_validation_never_raises_on_garbage() -> None:
    for garbage in (None, 7, "a string", [], {"schema_version": "9.9"}):
        errors = validate_decision_evidence_bundle(garbage)
        assert errors, f"{garbage!r} should have been rejected"


def test_an_unknown_schema_version_is_rejected_rather_than_guessed() -> None:
    record = _minimal_bundle()
    record["schema_version"] = "2.0"
    errors = validate_decision_evidence_bundle(record)
    assert any(e.path == "/schema_version" for e in errors)
    assert any("reject a version it does not implement" in e.expected for e in errors)


def test_a_typo_is_caught_and_points_at_ext() -> None:
    """ADR 0003: closed objects catch typos, and ext is where extras belong."""
    record = _minimal_bundle()
    record["decision"]["decision_typ"] = "task_completion"
    errors = validate_decision_evidence_bundle(record)
    assert [e.path for e in errors] == ["/decision/decision_typ"]
    assert "ext" in errors[0].expected


def test_an_unknown_discriminator_reports_one_error_not_seven() -> None:
    """Rule: dispatch on `kind` first, and never dump every arm's failures."""
    record = _minimal_bundle()
    record["evidence"] = [{"evidence_id": "e-1", "kind": "screenshot"}]
    errors = validate_decision_evidence_bundle(record)
    assert len(errors) == 1
    assert errors[0].path == "/evidence/0/kind"
    assert "command_result" in errors[0].expected


def test_a_missing_discriminator_names_the_discriminator() -> None:
    record = _minimal_bundle()
    record["decision"]["chosen"] = {"value": "x"}
    errors = validate_decision_evidence_bundle(record)
    assert len(errors) == 1
    assert "'kind' is missing" in errors[0].message


def test_once_kind_selects_an_arm_only_that_arm_is_reported() -> None:
    record = _minimal_bundle()
    record["evidence"] = [{"evidence_id": "e-1", "kind": "test_report", "passed": -1}]
    errors = validate_decision_evidence_bundle(record)
    paths = {e.path for e in errors}
    assert "/evidence/0/passed" in paths
    # A missing required field is reported against the object that should have
    # carried it, which is where a reader would go to add it.
    assert any("'failed' is missing" in e.message for e in errors)
    assert all(p.startswith("/evidence/0") for p in paths)


def test_a_callback_missing_determinism_under_math_says_the_specific_thing() -> None:
    """Most specific wins when two rules fire at one path."""
    manifest = {
        "schema_version": "1.0",
        "task_id": "repair-auth-017",
        "decision_type": "task_completion",
        "evaluation_name": "repository.tests_pass",
        "authority": "math",
        "evaluator": {"kind": "callback", "name": "tests_pass"},
    }
    errors = validate_evaluation_manifest(manifest)
    at_evaluator = [e for e in errors if e.path == "/evaluator"]
    assert len(at_evaluator) == 1
    assert "determinism" in at_evaluator[0].message
    assert "'deterministic' when authority is 'math'" in at_evaluator[0].expected


def test_a_model_assisted_callback_cannot_claim_math() -> None:
    manifest = {
        "schema_version": "1.0",
        "task_id": "t",
        "decision_type": "task_completion",
        "evaluation_name": "e",
        "authority": "math",
        "evaluator": {
            "kind": "callback", "name": "llm_pairwise_judge",
            "determinism": "model_assisted",
        },
    }
    errors = validate_evaluation_manifest(manifest)
    assert any(e.path == "/evaluator/determinism" for e in errors)


def test_a_deterministic_callback_may_claim_less_authority() -> None:
    """Downgrades are safe. Only upgrades are policed."""
    manifest = {
        "schema_version": "1.0",
        "task_id": "t",
        "decision_type": "task_completion",
        "evaluation_name": "e",
        "authority": "ai_judge",
        "evaluator": {
            "kind": "callback", "name": "tests_pass", "determinism": "deterministic",
        },
    }
    assert validate_evaluation_manifest(manifest) == []


def test_a_token_estimate_must_name_the_rates_behind_it() -> None:
    record = {
        "schema_version": "1.0", "usage_id": "usage-1", "scope": "model_invocation",
        "run_id": "run-42", "cost_provenance": "provider_token_estimate",
        "input_tokens": 10, "output_tokens": 5,
    }
    errors = validate_usage_record(record)
    assert any("pricing_table_id" in e.message for e in errors)


def test_unknown_record_type_is_a_caller_bug_and_raises() -> None:
    with pytest.raises(UnknownRecordTypeError):
        validate_record({}, "not-a-record-type")
