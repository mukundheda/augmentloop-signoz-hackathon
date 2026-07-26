"""Python reference implementation of the Universal Agent Evidence Protocol.

A harness submits EVIDENCE. Gradebook decides CORRECTNESS. This package is the
translation layer between those two sentences, and its job is to keep them from
merging: nothing a harness says about its own success can become a grade here.

The four record types are defined by the JSON Schemas in
`universal-adapter/schemas/`, which are the language-neutral contract. This
package mirrors them; it does not extend them.

Layout, in the order evidence moves through it:

- `models`      typed records, plus deterministic decision identity
- `validation`  actionable errors, never raised, checked against the schemas
- `costing`     the ledger, deduplication, attribution and cost coverage
- `evaluation`  the seven evaluators and the authority rules
- `emission`    conversion into gradebook's existing record_decision contract

Collection and evaluation are separate concerns. Ingesting evidence never runs
an evaluator and never emits telemetry.
"""

from .costing import (
    PRICING_TABLE_ID,
    ConflictingDecisionIdError,
    CostCoverage,
    CostPerCorrect,
    CostReport,
    DecisionCost,
    EvidenceLedger,
    InsufficientCoverageError,
    UnpriceableUsageError,
    attribute_costs,
    compare_cost_per_correct,
    cost_per_correct,
)
from .emission import (
    AuthorityNotEmittableError,
    CostNotRepresentableError,
    NotGradedError,
    capture_pending_decision,
    emit_graded_decision,
    emit_reality_outcome,
    redact,
)
from .evaluation import (
    CheckerRegistry,
    EvaluationContext,
    EvaluationResult,
    HarnessClaimIsNotAuthorityError,
    UnknownCheckerError,
    evaluate,
    gradeable_evidence,
    require_gradeable,
)
from .models import (
    SCHEMA_VERSION,
    Authority,
    CostProvenance,
    DecisionEvidenceBundle,
    DecisionIdentity,
    Determinism,
    EvaluationManifest,
    GradeableEvidence,
    HarnessClaimEvidence,
    OutcomeRecord,
    UsageRecord,
    UsageScope,
    derive_decision_id,
    resolve_decision_identity,
)
from .validation import (
    ValidationError,
    format_errors,
    infer_record_type,
    validate_decision_evidence_bundle,
    validate_evaluation_manifest,
    validate_outcome_record,
    validate_record,
    validate_usage_record,
)

__all__ = [
    "SCHEMA_VERSION",
    # models
    "Authority",
    "CostProvenance",
    "DecisionEvidenceBundle",
    "DecisionIdentity",
    "Determinism",
    "EvaluationManifest",
    "GradeableEvidence",
    "HarnessClaimEvidence",
    "OutcomeRecord",
    "UsageRecord",
    "UsageScope",
    "derive_decision_id",
    "resolve_decision_identity",
    # validation
    "ValidationError",
    "format_errors",
    "infer_record_type",
    "validate_record",
    "validate_decision_evidence_bundle",
    "validate_usage_record",
    "validate_evaluation_manifest",
    "validate_outcome_record",
    # evaluation
    "CheckerRegistry",
    "EvaluationContext",
    "EvaluationResult",
    "evaluate",
    "gradeable_evidence",
    "require_gradeable",
    "HarnessClaimIsNotAuthorityError",
    "UnknownCheckerError",
    # costing
    "PRICING_TABLE_ID",
    "CostCoverage",
    "CostPerCorrect",
    "CostReport",
    "DecisionCost",
    "EvidenceLedger",
    "attribute_costs",
    "compare_cost_per_correct",
    "cost_per_correct",
    "ConflictingDecisionIdError",
    "InsufficientCoverageError",
    "UnpriceableUsageError",
    # emission
    "capture_pending_decision",
    "emit_graded_decision",
    "emit_reality_outcome",
    "redact",
    "AuthorityNotEmittableError",
    "CostNotRepresentableError",
    "NotGradedError",
]
