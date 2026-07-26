"""Decision identity: derived when omitted, honoured when supplied, never merged.

The headline metric has a decision count in its denominator, so an id that is
not stable inflates the number this project exists to defend, and an id that is
reused for two different decisions corrupts it silently. ADR 0004 fixes both,
and these tests are that ADR made executable.
"""

from __future__ import annotations

import pytest
from support import bundle, inline

from gradebook_adapter.costing import ConflictingDecisionIdError, EvidenceLedger
from gradebook_adapter.models import (
    DecisionEvidenceBundle,
    UsageRecord,
    derive_decision_id,
    resolve_decision_identity,
)


def test_a_derived_id_is_stable_across_equal_bundles() -> None:
    first = bundle()
    second = bundle()
    assert derive_decision_id(first) == derive_decision_id(second)


def test_derivation_ignores_evidence_usage_and_metadata() -> None:
    """A late outcome or a new usage reference must not change who a decision is."""
    plain = bundle(chosen=inline("same answer"))
    busy = bundle(chosen=inline("same answer"), usage_refs=("usage-9",),
                  metadata={"environment": "benchmark"},
                  model="anthropic/claude-sonnet-4.6")
    assert derive_decision_id(plain) == derive_decision_id(busy)


def test_derivation_includes_the_chosen_value() -> None:
    """Two attempts at one task in one run are two decisions, not a conflict.

    Excluding `chosen` would derive one id for both, so the second attempt would
    be rejected as a conflicting duplicate and the failed attempt would vanish
    from the cost-per-correct numerator it is required to stay in.
    """
    first = bundle(chosen=inline("wrong answer"))
    second = bundle(chosen=inline("right answer"))
    assert derive_decision_id(first) != derive_decision_id(second)


def test_a_derived_id_is_prefixed_and_half_length() -> None:
    derived = derive_decision_id(bundle())
    assert derived.startswith("decision-")
    assert len(derived) == len("decision-") + 32


def test_derivation_changes_when_identity_changes() -> None:
    assert derive_decision_id(bundle()) != derive_decision_id(bundle(run_id="run-43"))
    assert derive_decision_id(bundle()) != derive_decision_id(
        bundle(evaluation_name="repository.builds")
    )


def test_a_supplied_id_is_used_as_given_and_recorded_as_such() -> None:
    identity = resolve_decision_identity(bundle(decision_id="decision-017"))
    assert identity.decision_id == "decision-017"
    assert identity.origin == "adapter_supplied"

    derived = resolve_decision_identity(bundle())
    assert derived.origin == "derived"


def test_replaying_the_same_bundle_is_idempotent() -> None:
    ledger = EvidenceLedger()
    first = ledger.add_bundle(bundle(decision_id="decision-017"))
    second = ledger.add_bundle(bundle(decision_id="decision-017"))
    third = ledger.add_bundle(bundle(decision_id="decision-017"))

    assert first == second == third
    assert ledger.decision_ids == ("decision-017",)


def test_replay_is_idempotent_across_the_two_id_provenances() -> None:
    """Omitting the id and supplying the derived id are the same decision."""
    ledger = EvidenceLedger()
    without = bundle()
    ledger.add_bundle(without)
    ledger.add_bundle(bundle(decision_id=derive_decision_id(without)))
    assert len(ledger.decision_ids) == 1


def test_a_duplicate_id_with_different_content_is_rejected() -> None:
    ledger = EvidenceLedger()
    ledger.add_bundle(bundle(decision_id="decision-017", chosen=inline("first")))

    with pytest.raises(ConflictingDecisionIdError) as excinfo:
        ledger.add_bundle(bundle(decision_id="decision-017", chosen=inline("second")))

    message = str(excinfo.value)
    assert "decision-017" in message
    assert "rejected rather than overwritten" in message
    # The first record survives untouched: rejection, not overwrite.
    assert ledger.bundles["decision-017"].decision.chosen == inline("first")


def test_round_trip_through_dicts_preserves_the_record() -> None:
    original = bundle(decision_id="decision-017", chosen=inline({"answer": 42}),
                      usage_refs=("usage-1",), metadata={"environment": "benchmark"})
    assert DecisionEvidenceBundle.from_dict(original.to_dict()) == original


def test_usage_round_trip_preserves_unreported_versus_zero() -> None:
    from gradebook_adapter.models import CostProvenance, UsageScope

    unreported = UsageRecord(
        usage_id="usage-1", scope=UsageScope.RUN, run_id="run-42",
        cost_provenance=CostProvenance.UNKNOWN, input_tokens=None,
    )
    reported_zero = UsageRecord(
        usage_id="usage-2", scope=UsageScope.RUN, run_id="run-42",
        cost_provenance=CostProvenance.UNKNOWN, input_tokens=0,
    )
    assert "input_tokens" not in unreported.to_dict()
    assert reported_zero.to_dict()["input_tokens"] == 0
    assert UsageRecord.from_dict(reported_zero.to_dict()).input_tokens == 0
    assert UsageRecord.from_dict(unreported.to_dict()).input_tokens is None


def test_outcome_replay_records_nothing_new() -> None:
    from gradebook_adapter.models import OutcomeRecord

    outcome = OutcomeRecord(
        outcome_id="outcome-88", decision_id="decision-017",
        outcome_type="pull_request_merged", correct=True,
        observed_at="2026-07-27T10:00:00Z",
    )
    ledger = EvidenceLedger()
    assert ledger.add_outcome(outcome) is True
    assert ledger.add_outcome(outcome) is False
    assert len(ledger.outcomes) == 1
