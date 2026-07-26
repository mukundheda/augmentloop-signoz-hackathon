"""Rules that exist ONLY to keep Python and TypeScript producing identical bytes.

Every assertion in this file is arbitrary in isolation. That is the point: an
arbitrary choice is only worth anything if both implementations made the same
one, so each is pinned here rather than left to whichever default the runtime
happens to have. A future contributor who "fixes" one of these breaks the
cross-language claim, and this file is what tells them so.
"""

from __future__ import annotations

import pytest

import json

from gradebook_adapter.costing import PRICING_TABLE_ID
from gradebook_adapter.models import (
    CanonicalizationError,
    DecisionEvidenceBundle,
    bundle_content_digest,
    canonical_json,
)
from gradebook_adapter.validation import (
    validate_decision_evidence_bundle,
    validate_outcome_record,
)


def test_an_exact_integer_never_grows_a_point_or_an_exponent() -> None:
    assert canonical_json(2) == "2"
    assert canonical_json(2.0) == "2"
    assert canonical_json(-0.0) == "0"
    assert canonical_json(1000000) == "1000000"


def test_a_fraction_is_six_decimal_places_with_the_zeros_stripped() -> None:
    # Python writes 3e-06 here and JavaScript writes 0.000003. Neither default
    # is usable, so the format is stated instead of inherited.
    assert canonical_json(0.000003) == "0.000003"
    assert canonical_json(0.5) == "0.5"
    assert canonical_json(1.250000) == "1.25"


def test_numbers_that_stop_agreeing_across_languages_are_refused() -> None:
    for value in (1e15, -1e15, float("nan"), float("inf")):
        with pytest.raises(CanonicalizationError):
            canonical_json(value)


def test_non_ascii_is_escaped_and_astral_characters_use_surrogate_pairs() -> None:
    assert canonical_json("é") == '"\\u00e9"'
    assert canonical_json("😀") == '"\\ud83d\\ude00"'


def test_keys_sort_by_code_point_and_no_whitespace_survives() -> None:
    assert canonical_json({"b": 1, "A": 2, "a": 3}) == '{"A":2,"a":3,"b":1}'


def test_a_null_is_written_and_an_absent_key_is_omitted() -> None:
    assert canonical_json({"a": None}) == '{"a":null}'
    assert canonical_json({}) == "{}"


def test_the_pricing_table_id_has_the_agreed_shape() -> None:
    prefix, _, digest = PRICING_TABLE_ID.partition("@")
    assert prefix == "gradebook.pricing"
    assert len(digest) == 12
    assert all(char in "0123456789abcdef" for char in digest)


def test_an_impossible_date_is_ACCEPTED_on_purpose() -> None:
    """Pinning test. Do not "fix" this.

    The schema asserts an RFC 3339 pattern and nothing more, and both language
    implementations assert exactly that. A stricter Python check would mean the
    two implementations rejecting different documents, which is a worse failure
    than accepting a month 13 that no clock can produce. If a real calendar check
    is wanted, it belongs in the schema, in the same commit, in both languages.
    """
    record = {
        "schema_version": "1.0",
        "outcome_id": "outcome-88",
        "decision_id": "decision-017",
        "outcome_type": "pull_request_merged",
        "correct": True,
        "observed_at": "2026-13-45T99:00:00Z",
    }
    assert validate_outcome_record(record) == []

    record["observed_at"] = "not-a-date"
    assert validate_outcome_record(record) != []


# --------------------------------------------------------------------------
# Anchoring. Python's `$` is not ECMAScript's `$`.
# --------------------------------------------------------------------------


def _bundle_with(correlation: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "decision": {
            "decision_type": "task_completion",
            "evaluation_name": "repository.tests_pass",
            "chosen": {"kind": "absent", "reason": "not_captured"},
        },
        "subject": {"harness": "hermes", "run_id": "run-42"},
        "correlation": correlation,
        "evidence": [],
    }


def test_a_trailing_newline_is_rejected_in_a_trace_id() -> None:
    r"""Python's `re` matches `$` before a trailing newline and ECMA-262 does not.

    JSON Schema specifies ECMA-262, so Python is the non-conformant one, and
    every pattern in validation.py anchors with `\Z` for that reason.

    These four tests exist because tests/test_schema_parity.py structurally
    CANNOT catch this: the `jsonschema` package uses Python's `re` too, so both
    sides of that check share the same wrong semantics and agree. Only the
    cross-language parity runner sees it. Do not delete these when they look
    redundant with the corpus.
    """
    good = validate_decision_evidence_bundle(_bundle_with({"trace_id": "0" * 32}))
    assert good == []
    errors = validate_decision_evidence_bundle(
        _bundle_with({"trace_id": "0" * 32 + "\n"})
    )
    assert any(e.path == "/correlation/trace_id" for e in errors)


def test_a_trailing_newline_is_rejected_in_a_span_id() -> None:
    errors = validate_decision_evidence_bundle(
        _bundle_with({"span_id": "0" * 16 + "\n"})
    )
    assert any(e.path == "/correlation/span_id" for e in errors)


def test_a_trailing_newline_is_rejected_in_a_sha256_digest() -> None:
    record = {
        "schema_version": "1.0",
        "decision": {
            "decision_type": "task_completion",
            "evaluation_name": "repository.tests_pass",
            "chosen": {"kind": "digest", "algorithm": "sha256",
                       "digest": "a" * 64 + "\n"},
        },
        "subject": {"harness": "hermes", "run_id": "run-42"},
        "evidence": [],
    }
    errors = validate_decision_evidence_bundle(record)
    assert any(e.path == "/decision/chosen/digest" for e in errors)


def test_a_trailing_newline_is_rejected_in_a_timestamp() -> None:
    record = {
        "schema_version": "1.0",
        "outcome_id": "outcome-88",
        "decision_id": "decision-017",
        "outcome_type": "pull_request_merged",
        "correct": True,
        "observed_at": "2026-07-27T10:00:00Z\n",
    }
    assert validate_outcome_record(record) != []


# --------------------------------------------------------------------------
# The content digest hashes the wire, not the model
# --------------------------------------------------------------------------


def test_an_explicit_null_and_an_omitted_key_digest_differently() -> None:
    """Absent and present-null are not interchangeable, digests included.

    The content digest is what separates an idempotent replay from a conflicting
    duplicate. If re-emitting the model dropped the null before hashing, the two
    documents below would collide, and a mixed-language ingest would disagree
    about whether a re-sent bundle is the same decision.
    """
    with_null = DecisionEvidenceBundle.from_dict(
        _bundle_with({"provider_response_id": None})
    )
    without_key = DecisionEvidenceBundle.from_dict(_bundle_with({}))

    assert bundle_content_digest(with_null) != bundle_content_digest(without_key)


def test_the_digest_is_stable_across_a_replay_of_the_same_wire_bytes() -> None:
    document = _bundle_with({"provider_response_id": None})
    first = DecisionEvidenceBundle.from_dict(document)
    second = DecisionEvidenceBundle.from_dict(json.loads(json.dumps(document)))
    assert bundle_content_digest(first) == bundle_content_digest(second)


def test_the_kept_source_does_not_change_what_a_record_means() -> None:
    """Provenance about the bytes, not part of the record's identity."""
    from_wire = DecisionEvidenceBundle.from_dict(_bundle_with({}))
    rebuilt = DecisionEvidenceBundle.from_dict(from_wire.to_dict())
    assert from_wire == rebuilt
