"""Typed records mirroring the four frozen JSON Schemas, plus record identity.

Why a hand written model layer at all, when the schemas already exist: the
schemas define what is *legal on the wire*, and this module defines what the
rest of the package is allowed to *assume in memory*. Once a dict has been
through `from_dict` there are no optional-but-actually-required fields left to
re-check, so the evaluator and the costing layer never re-implement validation
by accident.

Two rules shape everything here.

1. Closed records, one `ext` namespace (ADR 0003). Every object rejects unknown
   fields; `ext` is the single place a harness may carry something we did not
   anticipate. Nothing in `ext` is ever read by the evaluator or the costing
   layer, and nothing in it reaches telemetry.

2. Missing stays missing (issue #101, invariant 4). `None` means "not reported"
   and is never normalized to zero, to an empty string, or to a guessed value.
   That is why token counts and costs are `Optional` rather than defaulted, and
   why `AbsentValue` is a real member of the value union rather than an absent
   key.

`from_dict` here is deliberately strict and DOES raise: the documented order is
validate first (which never raises and returns actionable errors), then decode.
A decode error therefore means a caller skipped validation, which is a bug in
the caller and not a data problem.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Literal, Mapping, Optional, Union

SCHEMA_VERSION = "1.0"

# JSON scalar as it may appear in the low-cardinality label maps (metadata,
# harness claims). Deliberately not `Any`: these maps are the ones most likely
# to be handed a payload, and the type is the first line of that defence.
Scalar = Union[str, float, int, bool, None]


class RecordDecodeError(ValueError):
    """A record could not be decoded into its typed form.

    Raised rather than returned because reaching here means validation was
    skipped. Fail loud at the seam where the caller can still fix the order of
    operations, instead of producing a half-populated record that corrupts a
    grade or a cost much later.
    """


# --------------------------------------------------------------------------
# Canonical serialization and digests
# --------------------------------------------------------------------------


class CanonicalizationError(ValueError):
    """A value cannot be canonically serialized, so it cannot be hashed."""


def canonical_json(value: Any) -> str:
    """Serialize `value` the one way EVERY implementation must serialize it.

    This is a wire format for hashing, so the bytes matter: if the TypeScript
    implementation produces different bytes it produces different decision ids
    for the same decision, and the two sides silently stop agreeing about which
    decisions exist.

    Sorted keys by Unicode code point, no whitespace, arrays in order, and
    ensure_ascii escaping so no encoding question can arise. Numbers are the one
    place neither language's default is usable: Python writes 3e-06 where
    JavaScript writes 0.000003. So numbers are formatted explicitly instead, and
    the format is part of the contract rather than a property of the runtime.

    An absent key is omitted and a null is written. They are not interchangeable.
    """
    return _canonical(value)


def _canonical(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, Mapping):
        # sorted() on str compares by code point, which is the rule.
        parts = []
        for key in sorted(value):
            if not isinstance(key, str):
                raise CanonicalizationError(
                    f"object keys must be strings, got {type(key).__name__}"
                )
            parts.append(f"{json.dumps(key, ensure_ascii=True)}:{_canonical(value[key])}")
        return "{" + ",".join(parts) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    raise CanonicalizationError(
        f"{type(value).__name__} has no JSON representation, so it cannot be "
        "part of a digest"
    )


# Beyond this magnitude the two languages stop agreeing about what an integer
# even is, so the value is refused rather than hashed into a divergence.
_CANONICAL_NUMBER_LIMIT = 1e15


def _canonical_number(value: Union[int, float]) -> str:
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalizationError(
                f"{value!r} is not a JSON number and cannot be hashed"
            )
    if abs(value) >= _CANONICAL_NUMBER_LIMIT:
        raise CanonicalizationError(
            f"{value!r} is at or beyond 1e15, where integer representation stops "
            "being identical across languages"
        )
    if isinstance(value, int):
        return str(value)
    if value.is_integer():
        # 2.0 is written 2, and -0.0 is written 0: a negative zero would be one
        # more way for two implementations to disagree about the same number.
        return str(int(value) + 0)
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0", "-") else "0"


def sha256_hex(text: str) -> str:
    """sha256 of `text` as lowercase hex, over its UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, kw_only=True)
class Digest:
    """A content hash. `byte_length` is optional and never inferred."""

    algorithm: Literal["sha256"] = "sha256"
    digest: str
    byte_length: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Digest":
        _require_mapping(data, "digest")
        try:
            algorithm = data["algorithm"]
            digest = data["digest"]
        except KeyError as exc:
            raise RecordDecodeError(f"digest is missing {exc.args[0]!r}") from None
        if algorithm != "sha256":
            raise RecordDecodeError(
                f"digest algorithm {algorithm!r} is not supported, expected 'sha256'"
            )
        return cls(
            algorithm="sha256",
            digest=str(digest),
            byte_length=_opt_int(data.get("byte_length")),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"algorithm": self.algorithm, "digest": self.digest}
        if self.byte_length is not None:
            out["byte_length"] = self.byte_length
        return out


# --------------------------------------------------------------------------
# The value tagged union (decision.chosen, structured_output.output)
# --------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class InlineValue:
    """The real payload, carried inline. The privacy-expensive option."""

    KIND: ClassVar[str] = "inline"
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.KIND, "value": self.value}


@dataclass(frozen=True, kw_only=True)
class DigestValue:
    """The payload's hash instead of the payload. Comparable, not readable."""

    KIND: ClassVar[str] = "digest"
    algorithm: Literal["sha256"] = "sha256"
    digest: str
    byte_length: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.KIND,
            "algorithm": self.algorithm,
            "digest": self.digest,
        }
        if self.byte_length is not None:
            out["byte_length"] = self.byte_length
        return out


@dataclass(frozen=True, kw_only=True)
class ArtifactReference:
    """A pointer to the payload, held somewhere the grader can reach."""

    KIND: ClassVar[str] = "artifact_reference"
    value: str
    digest: Optional[Digest] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.KIND, "value": self.value}
        if self.digest is not None:
            out["digest"] = self.digest.to_dict()
        return out


@dataclass(frozen=True, kw_only=True)
class AbsentValue:
    """Explicitly withheld or unavailable, with the reason why.

    Distinct from an empty inline value on purpose: an empty string is an answer
    of length zero, and this is the absence of an answer.
    """

    KIND: ClassVar[str] = "absent"
    reason: Literal["redacted", "not_captured", "too_large", "unknown"]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.KIND, "reason": self.reason}


Value = Union[InlineValue, DigestValue, ArtifactReference, AbsentValue]


def value_from_dict(data: Mapping[str, Any]) -> Value:
    """Decode the tagged value union by its `kind` tag."""
    _require_mapping(data, "value")
    kind = data.get("kind")
    if kind == InlineValue.KIND:
        if "value" not in data:
            raise RecordDecodeError("inline value is missing 'value'")
        return InlineValue(value=data["value"])
    if kind == DigestValue.KIND:
        try:
            return DigestValue(
                algorithm="sha256",
                digest=str(data["digest"]),
                byte_length=_opt_int(data.get("byte_length")),
            )
        except KeyError as exc:
            raise RecordDecodeError(f"digest value is missing {exc.args[0]!r}") from None
    if kind == ArtifactReference.KIND:
        try:
            raw_digest = data.get("digest")
            return ArtifactReference(
                value=str(data["value"]),
                digest=Digest.from_dict(raw_digest) if raw_digest is not None else None,
            )
        except KeyError as exc:
            raise RecordDecodeError(
                f"artifact_reference value is missing {exc.args[0]!r}"
            ) from None
    if kind == AbsentValue.KIND:
        reason = data.get("reason")
        if reason not in ("redacted", "not_captured", "too_large", "unknown"):
            raise RecordDecodeError(f"absent value has unsupported reason {reason!r}")
        return AbsentValue(reason=reason)
    raise RecordDecodeError(f"value has unknown kind {kind!r}")


def value_to_dict(value: Value) -> dict[str, Any]:
    return value.to_dict()


# --------------------------------------------------------------------------
# Evidence items
# --------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CommandResultEvidence:
    KIND: ClassVar[str] = "command_result"
    evidence_id: str
    command_name: str
    exit_code: int
    duration_ms: Optional[int] = None
    artifact_digest: Optional[Digest] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "kind": self.KIND,
            "command_name": self.command_name,
            "exit_code": self.exit_code,
        }
        if self.duration_ms is not None:
            out["duration_ms"] = self.duration_ms
        if self.artifact_digest is not None:
            out["artifact_digest"] = self.artifact_digest.to_dict()
        return out


@dataclass(frozen=True, kw_only=True)
class FileStateEvidence:
    KIND: ClassVar[str] = "file_state"
    evidence_id: str
    path: str
    artifact_digest: Digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.KIND,
            "path": self.path,
            "artifact_digest": self.artifact_digest.to_dict(),
        }


@dataclass(frozen=True, kw_only=True)
class TestReportEvidence:
    KIND: ClassVar[str] = "test_report"
    evidence_id: str
    passed: int
    failed: int
    skipped: Optional[int] = None
    artifact_digest: Optional[Digest] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "kind": self.KIND,
            "passed": self.passed,
            "failed": self.failed,
        }
        if self.skipped is not None:
            out["skipped"] = self.skipped
        if self.artifact_digest is not None:
            out["artifact_digest"] = self.artifact_digest.to_dict()
        return out


@dataclass(frozen=True, kw_only=True)
class StructuredOutputEvidence:
    KIND: ClassVar[str] = "structured_output"
    evidence_id: str
    output: Value

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.KIND,
            "output": self.output.to_dict(),
        }


@dataclass(frozen=True, kw_only=True)
class OtelSpanEvidence:
    KIND: ClassVar[str] = "otel_span"
    evidence_id: str
    trace_id: str
    span_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.KIND,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }


@dataclass(frozen=True, kw_only=True)
class LogReferenceEvidence:
    KIND: ClassVar[str] = "log_reference"
    evidence_id: str
    ref: str
    artifact_digest: Optional[Digest] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "kind": self.KIND,
            "ref": self.ref,
        }
        if self.artifact_digest is not None:
            out["artifact_digest"] = self.artifact_digest.to_dict()
        return out


@dataclass(frozen=True, kw_only=True)
class HarnessClaimEvidence:
    """The harness asserting something about its own run, e.g. success=true.

    Its own type on purpose. `GradeableEvidence` below excludes it, so a
    function that grades cannot even be *handed* one without mypy objecting.
    That is the type-level half of "harness success is not authority"; the
    guard-clause half lives in evaluation.require_gradeable.
    """

    KIND: ClassVar[str] = "harness_claim"
    evidence_id: str
    claim: Mapping[str, Scalar]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.KIND,
            "claim": dict(self.claim),
        }


# Everything a grader may look at. HarnessClaimEvidence is absent by design.
GradeableEvidence = Union[
    CommandResultEvidence,
    FileStateEvidence,
    TestReportEvidence,
    StructuredOutputEvidence,
    OtelSpanEvidence,
    LogReferenceEvidence,
]

EvidenceItem = Union[GradeableEvidence, HarnessClaimEvidence]


def evidence_from_dict(data: Mapping[str, Any]) -> EvidenceItem:
    _require_mapping(data, "evidence item")
    kind = data.get("kind")
    try:
        evidence_id = str(data["evidence_id"])
        if kind == CommandResultEvidence.KIND:
            return CommandResultEvidence(
                evidence_id=evidence_id,
                command_name=str(data["command_name"]),
                exit_code=_int(data["exit_code"], "exit_code"),
                duration_ms=_opt_int(data.get("duration_ms")),
                artifact_digest=_opt_digest(data.get("artifact_digest")),
            )
        if kind == FileStateEvidence.KIND:
            return FileStateEvidence(
                evidence_id=evidence_id,
                path=str(data["path"]),
                artifact_digest=Digest.from_dict(data["artifact_digest"]),
            )
        if kind == TestReportEvidence.KIND:
            return TestReportEvidence(
                evidence_id=evidence_id,
                passed=_int(data["passed"], "passed"),
                failed=_int(data["failed"], "failed"),
                skipped=_opt_int(data.get("skipped")),
                artifact_digest=_opt_digest(data.get("artifact_digest")),
            )
        if kind == StructuredOutputEvidence.KIND:
            return StructuredOutputEvidence(
                evidence_id=evidence_id,
                output=value_from_dict(data["output"]),
            )
        if kind == OtelSpanEvidence.KIND:
            return OtelSpanEvidence(
                evidence_id=evidence_id,
                trace_id=str(data["trace_id"]),
                span_id=str(data["span_id"]),
            )
        if kind == LogReferenceEvidence.KIND:
            return LogReferenceEvidence(
                evidence_id=evidence_id,
                ref=str(data["ref"]),
                artifact_digest=_opt_digest(data.get("artifact_digest")),
            )
        if kind == HarnessClaimEvidence.KIND:
            claim = data["claim"]
            _require_mapping(claim, "harness claim")
            return HarnessClaimEvidence(
                evidence_id=evidence_id, claim=dict(claim)
            )
    except KeyError as exc:
        raise RecordDecodeError(
            f"evidence item of kind {kind!r} is missing {exc.args[0]!r}"
        ) from None
    raise RecordDecodeError(f"evidence item has unknown kind {kind!r}")


# --------------------------------------------------------------------------
# DecisionEvidenceBundle
# --------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Decision:
    decision_type: str
    evaluation_name: str
    chosen: Value
    decision_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "decision_type": self.decision_type,
            "evaluation_name": self.evaluation_name,
            "chosen": self.chosen.to_dict(),
        }
        if self.decision_id is not None:
            out["decision_id"] = self.decision_id
        return out


@dataclass(frozen=True, kw_only=True)
class Subject:
    harness: str
    run_id: str
    harness_version: Optional[str] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    parent_agent_id: Optional[str] = None
    model: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"harness": self.harness, "run_id": self.run_id}
        for key in ("harness_version", "session_id", "agent_id", "parent_agent_id", "model"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True, kw_only=True)
class Correlation:
    provider_response_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    task_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in ("provider_response_id", "trace_id", "span_id", "task_id"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True, kw_only=True)
class DecisionEvidenceBundle:
    """Evidence about ONE decision. Never states whether it was correct."""

    decision: Decision
    subject: Subject
    evidence: tuple[EvidenceItem, ...] = ()
    correlation: Optional[Correlation] = None
    usage_refs: tuple[str, ...] = ()
    metadata: Optional[Mapping[str, Scalar]] = None
    ext: Optional[Mapping[str, Any]] = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DecisionEvidenceBundle":
        _require_mapping(data, "decision evidence bundle")
        _require_schema_version(data)
        try:
            decision_raw = data["decision"]
            subject_raw = data["subject"]
            evidence_raw = data["evidence"]
        except KeyError as exc:
            raise RecordDecodeError(
                f"decision evidence bundle is missing {exc.args[0]!r}"
            ) from None
        _require_mapping(decision_raw, "decision")
        _require_mapping(subject_raw, "subject")
        if not isinstance(evidence_raw, list):
            raise RecordDecodeError("evidence must be an array")
        correlation_raw = data.get("correlation")
        return cls(
            decision=Decision(
                decision_type=str(decision_raw["decision_type"]),
                evaluation_name=str(decision_raw["evaluation_name"]),
                chosen=value_from_dict(decision_raw["chosen"]),
                decision_id=_opt_str(decision_raw.get("decision_id")),
            ),
            subject=Subject(
                harness=str(subject_raw["harness"]),
                run_id=str(subject_raw["run_id"]),
                harness_version=_opt_str(subject_raw.get("harness_version")),
                session_id=_opt_str(subject_raw.get("session_id")),
                agent_id=_opt_str(subject_raw.get("agent_id")),
                parent_agent_id=_opt_str(subject_raw.get("parent_agent_id")),
                model=_opt_str(subject_raw.get("model")),
            ),
            correlation=(
                Correlation(
                    provider_response_id=_opt_str(correlation_raw.get("provider_response_id")),
                    trace_id=_opt_str(correlation_raw.get("trace_id")),
                    span_id=_opt_str(correlation_raw.get("span_id")),
                    task_id=_opt_str(correlation_raw.get("task_id")),
                )
                if isinstance(correlation_raw, Mapping)
                else None
            ),
            evidence=tuple(evidence_from_dict(item) for item in evidence_raw),
            usage_refs=tuple(str(ref) for ref in data.get("usage_refs", ())),
            metadata=dict(data["metadata"]) if "metadata" in data else None,
            ext=dict(data["ext"]) if "ext" in data else None,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "decision": self.decision.to_dict(),
            "subject": self.subject.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
        }
        if self.correlation is not None:
            out["correlation"] = self.correlation.to_dict()
        if self.usage_refs:
            out["usage_refs"] = list(self.usage_refs)
        if self.metadata is not None:
            out["metadata"] = dict(self.metadata)
        if self.ext is not None:
            out["ext"] = dict(self.ext)
        return out


# --------------------------------------------------------------------------
# UsageRecord
# --------------------------------------------------------------------------


class UsageScope(str, Enum):
    """What a usage record measures, ordered narrow to broad."""

    MODEL_INVOCATION = "model_invocation"
    DECISION = "decision"
    AGENT = "agent"
    RUN = "run"


class CostProvenance(str, Enum):
    """Where a money figure's authority comes from, strongest first.

    The order of the members IS the precedence order (see `strength`). An
    estimate is never presented as a measurement, which is the same honesty rule
    Gradebook applies to grades, applied to cost.
    """

    PROVIDER_REPORTED = "provider_reported"
    PROVIDER_TOKEN_ESTIMATE = "provider_token_estimate"
    HARNESS_TOKEN_ESTIMATE = "harness_token_estimate"
    RUN_AGGREGATE = "run_aggregate"
    UNKNOWN = "unknown"

    @property
    def strength(self) -> int:
        """Lower is stronger. Used to pick the weakest link of a summed cost."""
        return _COST_PRECEDENCE.index(self)


_COST_PRECEDENCE: tuple[CostProvenance, ...] = (
    CostProvenance.PROVIDER_REPORTED,
    CostProvenance.PROVIDER_TOKEN_ESTIMATE,
    CostProvenance.HARNESS_TOKEN_ESTIMATE,
    CostProvenance.RUN_AGGREGATE,
    CostProvenance.UNKNOWN,
)


@dataclass(frozen=True, kw_only=True)
class UsageRecord:
    """One unit of resource consumption, deduplicated by `usage_id`."""

    usage_id: str
    scope: UsageScope
    run_id: str
    cost_provenance: CostProvenance
    agent_id: Optional[str] = None
    parent_agent_id: Optional[str] = None
    contains_usage_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    provider_response_id: Optional[str] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    provider_cost_usd: Optional[float] = None
    pricing_table_id: Optional[str] = None
    ext: Optional[Mapping[str, Any]] = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UsageRecord":
        _require_mapping(data, "usage record")
        _require_schema_version(data)
        try:
            return cls(
                usage_id=str(data["usage_id"]),
                scope=_enum(UsageScope, data["scope"], "scope"),
                run_id=str(data["run_id"]),
                cost_provenance=_enum(
                    CostProvenance, data["cost_provenance"], "cost_provenance"
                ),
                agent_id=_opt_str(data.get("agent_id")),
                parent_agent_id=_opt_str(data.get("parent_agent_id")),
                contains_usage_ids=tuple(
                    str(x) for x in data.get("contains_usage_ids", ())
                ),
                decision_ids=tuple(str(x) for x in data.get("decision_ids", ())),
                provider_response_id=_opt_str(data.get("provider_response_id")),
                model=_opt_str(data.get("model")),
                input_tokens=_opt_int(data.get("input_tokens")),
                output_tokens=_opt_int(data.get("output_tokens")),
                cached_input_tokens=_opt_int(data.get("cached_input_tokens")),
                provider_cost_usd=_opt_float(data.get("provider_cost_usd")),
                pricing_table_id=_opt_str(data.get("pricing_table_id")),
                ext=dict(data["ext"]) if "ext" in data else None,
            )
        except KeyError as exc:
            raise RecordDecodeError(
                f"usage record is missing {exc.args[0]!r}"
            ) from None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "usage_id": self.usage_id,
            "scope": self.scope.value,
            "run_id": self.run_id,
            "cost_provenance": self.cost_provenance.value,
        }
        for key in (
            "agent_id",
            "parent_agent_id",
            "provider_response_id",
            "model",
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "provider_cost_usd",
            "pricing_table_id",
        ):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.contains_usage_ids:
            out["contains_usage_ids"] = list(self.contains_usage_ids)
        if self.decision_ids:
            out["decision_ids"] = list(self.decision_ids)
        if self.ext is not None:
            out["ext"] = dict(self.ext)
        return out


# --------------------------------------------------------------------------
# EvaluationManifest
# --------------------------------------------------------------------------


class Authority(str, Enum):
    MATH = "math"
    REALITY = "reality"
    AI_JUDGE = "ai_judge"


class Determinism(str, Enum):
    """Whether a callback computes its verdict or asks a model for one."""

    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"


@dataclass(frozen=True, kw_only=True)
class ExactEqualityEvaluator:
    KIND: ClassVar[str] = "exact_equality"
    expected: Any
    case_sensitive: bool = True
    trim_whitespace: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.KIND,
            "expected": self.expected,
            "case_sensitive": self.case_sensitive,
            "trim_whitespace": self.trim_whitespace,
        }


@dataclass(frozen=True, kw_only=True)
class JsonEqualityEvaluator:
    KIND: ClassVar[str] = "json_equality"
    expected: Any

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.KIND, "expected": self.expected}


@dataclass(frozen=True, kw_only=True)
class CommandExitCodeEvaluator:
    KIND: ClassVar[str] = "command_exit_code"
    command: tuple[str, ...]
    expected_exit_code: int
    timeout_seconds: float = 120.0
    working_directory: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.KIND,
            "command": list(self.command),
            "expected_exit_code": self.expected_exit_code,
            "timeout_seconds": self.timeout_seconds,
        }
        if self.working_directory is not None:
            out["working_directory"] = self.working_directory
        return out


@dataclass(frozen=True, kw_only=True)
class FileDigestEvaluator:
    KIND: ClassVar[str] = "file_digest"
    path: str
    expected: Digest

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.KIND, "path": self.path, "expected": self.expected.to_dict()}


@dataclass(frozen=True, kw_only=True)
class JsonSchemaEvaluator:
    KIND: ClassVar[str] = "json_schema"
    schema: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.KIND, "schema": dict(self.schema)}


@dataclass(frozen=True, kw_only=True)
class CallbackEvaluator:
    """A checker resolved BY NAME from a registry the application owns.

    The name is a lookup key and never an import path, so a manifest arriving
    from outside cannot cause arbitrary code to load.

    `determinism` has no default. A callback is the one evaluator whose
    determinism is invisible in its shape, and defaulting it would let a
    model-assisted checker reach the headline metric by omission. Declaring it
    here is a claim, not proof: the registry in evaluation.py holds the second,
    stronger declaration and wins if the two disagree.
    """

    KIND: ClassVar[str] = "callback"
    name: str
    determinism: Determinism
    options: Mapping[str, Scalar] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.KIND,
            "name": self.name,
            "determinism": self.determinism.value,
        }
        if self.options:
            out["options"] = dict(self.options)
        return out


@dataclass(frozen=True, kw_only=True)
class OutcomeEvaluator:
    KIND: ClassVar[str] = "outcome"
    outcome_type: str
    observation_window_seconds: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.KIND, "outcome_type": self.outcome_type}
        if self.observation_window_seconds is not None:
            out["observation_window_seconds"] = self.observation_window_seconds
        return out


# Evaluators whose verdict is computable from their own output alone. Only these
# may carry math authority, enforced by the schema and re-checked in evaluation.
DeterministicEvaluator = Union[
    ExactEqualityEvaluator,
    JsonEqualityEvaluator,
    CommandExitCodeEvaluator,
    FileDigestEvaluator,
    JsonSchemaEvaluator,
    CallbackEvaluator,
]

Evaluator = Union[DeterministicEvaluator, OutcomeEvaluator]

DETERMINISTIC_EVALUATOR_KINDS: frozenset[str] = frozenset(
    {
        ExactEqualityEvaluator.KIND,
        JsonEqualityEvaluator.KIND,
        CommandExitCodeEvaluator.KIND,
        FileDigestEvaluator.KIND,
        JsonSchemaEvaluator.KIND,
        CallbackEvaluator.KIND,
    }
)


def evaluator_from_dict(data: Mapping[str, Any]) -> Evaluator:
    _require_mapping(data, "evaluator")
    kind = data.get("kind")
    try:
        if kind == ExactEqualityEvaluator.KIND:
            return ExactEqualityEvaluator(
                expected=data["expected"],
                case_sensitive=_bool(data.get("case_sensitive", True), "case_sensitive"),
                trim_whitespace=_bool(data.get("trim_whitespace", True), "trim_whitespace"),
            )
        if kind == JsonEqualityEvaluator.KIND:
            return JsonEqualityEvaluator(expected=data["expected"])
        if kind == CommandExitCodeEvaluator.KIND:
            return CommandExitCodeEvaluator(
                command=tuple(str(part) for part in data["command"]),
                expected_exit_code=_int(data["expected_exit_code"], "expected_exit_code"),
                timeout_seconds=float(data.get("timeout_seconds", 120)),
                working_directory=_opt_str(data.get("working_directory")),
            )
        if kind == FileDigestEvaluator.KIND:
            return FileDigestEvaluator(
                path=str(data["path"]), expected=Digest.from_dict(data["expected"])
            )
        if kind == JsonSchemaEvaluator.KIND:
            schema = data["schema"]
            _require_mapping(schema, "json_schema evaluator schema")
            return JsonSchemaEvaluator(schema=dict(schema))
        if kind == CallbackEvaluator.KIND:
            options = data.get("options") or {}
            _require_mapping(options, "callback options")
            return CallbackEvaluator(
                name=str(data["name"]),
                determinism=_enum(Determinism, data["determinism"], "determinism"),
                options=dict(options),
            )
        if kind == OutcomeEvaluator.KIND:
            window = data.get("observation_window_seconds")
            return OutcomeEvaluator(
                outcome_type=str(data["outcome_type"]),
                observation_window_seconds=None if window is None else float(window),
            )
    except KeyError as exc:
        raise RecordDecodeError(
            f"evaluator of kind {kind!r} is missing {exc.args[0]!r}"
        ) from None
    raise RecordDecodeError(f"evaluator has unknown kind {kind!r}")


@dataclass(frozen=True, kw_only=True)
class EvaluationManifest:
    """The independent source of truth for one task."""

    task_id: str
    decision_type: str
    evaluation_name: str
    authority: Authority
    evaluator: Evaluator
    description: Optional[str] = None
    ext: Optional[Mapping[str, Any]] = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvaluationManifest":
        _require_mapping(data, "evaluation manifest")
        _require_schema_version(data)
        try:
            return cls(
                task_id=str(data["task_id"]),
                decision_type=str(data["decision_type"]),
                evaluation_name=str(data["evaluation_name"]),
                authority=_enum(Authority, data["authority"], "authority"),
                evaluator=evaluator_from_dict(data["evaluator"]),
                description=_opt_str(data.get("description")),
                ext=dict(data["ext"]) if "ext" in data else None,
            )
        except KeyError as exc:
            raise RecordDecodeError(
                f"evaluation manifest is missing {exc.args[0]!r}"
            ) from None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "decision_type": self.decision_type,
            "evaluation_name": self.evaluation_name,
            "authority": self.authority.value,
            "evaluator": self.evaluator.to_dict(),
        }
        if self.description is not None:
            out["description"] = self.description
        if self.ext is not None:
            out["ext"] = dict(self.ext)
        return out


# --------------------------------------------------------------------------
# OutcomeRecord
# --------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class OutcomeRecord:
    """A real-world result that arrives after the decision it judges."""

    outcome_id: str
    decision_id: str
    outcome_type: str
    correct: bool
    observed_at: str
    provider_response_id: Optional[str] = None
    evidence_ref: Optional[str] = None
    explanation: Optional[str] = None
    ext: Optional[Mapping[str, Any]] = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OutcomeRecord":
        _require_mapping(data, "outcome record")
        _require_schema_version(data)
        try:
            correct = data["correct"]
            if not isinstance(correct, bool):
                # A truthy 1 silently becoming a passing grade is a known way to
                # corrupt a headline metric, so this is never coerced.
                raise RecordDecodeError(
                    f"outcome 'correct' must be a boolean, got {type(correct).__name__}"
                )
            return cls(
                outcome_id=str(data["outcome_id"]),
                decision_id=str(data["decision_id"]),
                outcome_type=str(data["outcome_type"]),
                correct=correct,
                observed_at=str(data["observed_at"]),
                provider_response_id=_opt_str(data.get("provider_response_id")),
                evidence_ref=_opt_str(data.get("evidence_ref")),
                explanation=_opt_str(data.get("explanation")),
                ext=dict(data["ext"]) if "ext" in data else None,
            )
        except KeyError as exc:
            raise RecordDecodeError(
                f"outcome record is missing {exc.args[0]!r}"
            ) from None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "outcome_id": self.outcome_id,
            "decision_id": self.decision_id,
            "outcome_type": self.outcome_type,
            "correct": self.correct,
            "observed_at": self.observed_at,
        }
        for key in ("provider_response_id", "evidence_ref", "explanation"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.ext is not None:
            out["ext"] = dict(self.ext)
        return out


# --------------------------------------------------------------------------
# Decision identity (ADR 0004)
# --------------------------------------------------------------------------

DecisionIdOrigin = Literal["derived", "adapter_supplied"]

# The eight identity fields, cross-language binding. `chosen` IS one of them,
# which corrects the first draft of ADR 0004: without it, two attempts at the
# same task in the same run derive the SAME id, so the second is rejected as a
# conflicting duplicate and the failed attempt vanishes from the cost-per-correct
# numerator that issue #101 explicitly requires it to stay in. `chosen` is fixed
# at the moment the decision is made, so including it does not make identity
# mutable the way evidence, usage or a late outcome would.
#
# Excluded on purpose: model, evidence, usage_refs, metadata, trace and span ids,
# harness_version, provider_response_id.
_IDENTITY_FIELDS: tuple[str, ...] = (
    "agent_id",
    "chosen",
    "decision_type",
    "evaluation_name",
    "harness",
    "run_id",
    "session_id",
    "task_id",
)

DECISION_ID_PREFIX = "decision-"
_DECISION_ID_HEX = 32


@dataclass(frozen=True, kw_only=True)
class DecisionIdentity:
    """A decision's id plus the provenance of that id.

    Recording which of the two happened is not bookkeeping for its own sake: an
    id whose provenance is unknown is an id nobody can reason about later.
    """

    decision_id: str
    origin: DecisionIdOrigin
    content_digest: str


def identity_payload(bundle: DecisionEvidenceBundle) -> dict[str, Any]:
    """The exact field map that gets canonically serialized and hashed."""
    correlation = bundle.correlation or Correlation()
    values: dict[str, Any] = {
        "agent_id": bundle.subject.agent_id,
        "chosen": bundle.decision.chosen.to_dict(),
        "decision_type": bundle.decision.decision_type,
        "evaluation_name": bundle.decision.evaluation_name,
        "harness": bundle.subject.harness,
        "run_id": bundle.subject.run_id,
        "session_id": bundle.subject.session_id,
        "task_id": correlation.task_id,
    }
    # Nulls are written explicitly rather than omitted, so "field absent" and
    # "field present and null" cannot hash to two different decisions.
    return {name: values[name] for name in _IDENTITY_FIELDS}


def derive_decision_id(bundle: DecisionEvidenceBundle) -> str:
    """Deterministic id from the eight identity fields, and nothing else."""
    digest = sha256_hex(canonical_json(identity_payload(bundle)))
    return DECISION_ID_PREFIX + digest[:_DECISION_ID_HEX]


def bundle_content_digest(bundle: DecisionEvidenceBundle) -> str:
    """Digest of everything the bundle says, ignoring the id itself.

    Ignoring `decision_id` is what makes replay idempotent across the two id
    provenances: a bundle that omits the id and the same bundle carrying its
    derived id are the same content, not a conflict.
    """
    payload = bundle.to_dict()
    payload["decision"].pop("decision_id", None)
    return sha256_hex(canonical_json(payload))


def resolve_decision_identity(bundle: DecisionEvidenceBundle) -> DecisionIdentity:
    """Use the supplied id as-is, or derive one, and say which happened."""
    supplied = bundle.decision.decision_id
    if supplied is not None:
        return DecisionIdentity(
            decision_id=supplied,
            origin="adapter_supplied",
            content_digest=bundle_content_digest(bundle),
        )
    return DecisionIdentity(
        decision_id=derive_decision_id(bundle),
        origin="derived",
        content_digest=bundle_content_digest(bundle),
    )


# --------------------------------------------------------------------------
# Small decode helpers. Strict on purpose: see the module docstring.
# --------------------------------------------------------------------------


def _require_mapping(data: Any, what: str) -> None:
    if not isinstance(data, Mapping):
        raise RecordDecodeError(f"{what} must be an object, got {type(data).__name__}")


def _require_schema_version(data: Mapping[str, Any]) -> None:
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise RecordDecodeError(
            f"unsupported schema_version {version!r}, this implementation "
            f"understands only {SCHEMA_VERSION!r}"
        )


def _opt_str(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def _int(value: Any, what: str) -> int:
    # bool is a subclass of int in Python but not in JSON, so it is refused.
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecordDecodeError(f"{what} must be an integer, got {value!r}")
    return value


def _opt_int(value: Any) -> Optional[int]:
    return None if value is None else _int(value, "integer field")


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecordDecodeError(f"number field must be a number, got {value!r}")
    return float(value)


def _bool(value: Any, what: str) -> bool:
    if not isinstance(value, bool):
        raise RecordDecodeError(f"{what} must be a boolean, got {value!r}")
    return value


def _opt_digest(value: Any) -> Optional[Digest]:
    return None if value is None else Digest.from_dict(value)


def _enum(enum_cls: Any, value: Any, what: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_cls)
        raise RecordDecodeError(
            f"{what} must be one of [{allowed}], got {value!r}"
        ) from None
