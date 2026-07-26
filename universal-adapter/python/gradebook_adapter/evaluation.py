"""The seven evaluator kinds, and the wall between evidence and authority.

Gradebook's whole claim is that it decides correctness independently of the
thing being graded. This module is where that claim is either kept or lost, so
it is built around one asymmetry: an evaluator may CONCLUDE, and a harness may
only supply material. Concretely, an evaluator grades what the MANIFEST declares
(the expected value, the command, the digest, the schema, the checker name), and
evidence only supplies the observation the manifest asked for. The harness never
gets to choose the question.

Three mechanisms hold the wall up, in order of strength.

1. Type level. `HarnessClaimEvidence` is not a member of `GradeableEvidence`, so
   a function that grades cannot be handed one without mypy objecting. There is
   no code path from a harness claim to a math grade to review, because the type
   says there is no such path to write.
2. Guard clause. `require_gradeable` raises on a harness claim, for the dynamic
   callers that types cannot reach (a JSONL importer holding `Any`).
3. Manifest structure. Math authority is refused for any evaluator that is not
   deterministic, re-checking what the schema already enforces. Defence in depth
   is warranted here because the schema is data and data can be edited.

The callback evaluator is the one arm whose determinism the schema cannot see: a
name in a registry could resolve to something that calls a model. So the registry
demands a determinism declaration at REGISTRATION time, from the application that
owns the code. When the manifest overstates the checker, the checker still runs
and the result is graded `ai_judge` with the downgrade recorded, which keeps the
opinion visible instead of throwing it away, and keeps it out of the headline
metric where it does not belong.

Collection and evaluation stay separate: nothing here runs as a side effect of
ingesting evidence, and nothing that ingests evidence calls into this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from gradebook.checkers import CheckResult, ReasonCode
from gradebook.grading import GradeSource

from .models import (
    AbsentValue,
    ArtifactReference,
    Authority,
    CallbackEvaluator,
    CommandExitCodeEvaluator,
    CommandResultEvidence,
    DecisionEvidenceBundle,
    Determinism,
    DigestValue,
    EvaluationManifest,
    Evaluator,
    EvidenceItem,
    ExactEqualityEvaluator,
    FileDigestEvaluator,
    FileStateEvidence,
    GradeableEvidence,
    HarnessClaimEvidence,
    InlineValue,
    JsonEqualityEvaluator,
    JsonSchemaEvaluator,
    OutcomeEvaluator,
    Scalar,
    StructuredOutputEvidence,
    Value,
    resolve_decision_identity,
)


class EvaluationError(Exception):
    """Base class for the conditions this module refuses to paper over."""


class ManifestMismatchError(EvaluationError):
    """The manifest does not describe the decision it was handed.

    Comparing decisions of different types is the decision-boundary risk in
    issue #101, and it starts here, with a manifest applied to the wrong unit.
    """


class InvalidManifestError(EvaluationError):
    """The manifest's authority and evaluator contradict each other."""


class HarnessClaimIsNotAuthorityError(EvaluationError):
    """A harness claim was offered as grading input.

    post-task(success=true) is a fact about what the harness believes, not about
    the world. It may trigger evaluation; it may never conclude it.
    """


class UnknownCheckerError(EvaluationError):
    """A callback manifest named a checker the application never registered."""


Checker = Callable[[Value, Mapping[str, Scalar]], Union[bool, CheckResult]]


@dataclass(frozen=True)
class RegisteredChecker:
    checker: Checker
    determinism: Determinism


class CheckerRegistry:
    """Named checkers the application owns, each with a determinism claim.

    Registration demands `determinism` with no default. That is the point of the
    registry: the application, which can see the implementation, states whether
    the checker computes a verdict or asks a model for one, and that statement is
    what the evaluator trusts when a manifest disagrees.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RegisteredChecker] = {}

    def register(self, name: str, checker: Checker, *,
                 determinism: Determinism) -> None:
        if name in self._entries:
            # Silent replacement would let a later import swap a deterministic
            # checker for a model-assisted one under the same name.
            raise EvaluationError(
                f"checker {name!r} is already registered; unregister it "
                "explicitly if replacing it is intended"
            )
        self._entries[name] = RegisteredChecker(checker=checker,
                                                determinism=determinism)

    def unregister(self, name: str) -> None:
        self._entries.pop(name, None)

    def resolve(self, name: str) -> RegisteredChecker:
        try:
            return self._entries[name]
        except KeyError:
            known = ", ".join(sorted(self._entries)) or "none"
            raise UnknownCheckerError(
                f"no checker named {name!r} is registered; registered checkers "
                f"are: {known}. A manifest names a checker, it never imports one, "
                "so the application must register it first."
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self._entries


@dataclass
class EvaluationContext:
    """Everything an evaluator may reach outside the records themselves.

    Just the checker registry. Deliberately not a process runner or a file
    system: every other evaluator grades the manifest's declaration against the
    evidence it was given, so this package never executes anything on its own.
    """

    checkers: CheckerRegistry = field(default_factory=CheckerRegistry)


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationResult:
    """One evaluator's verdict on one decision.

    Three flags that are easy to conflate and must not be:

    - `graded`: an evaluator reached a machine-checked verdict at all.
    - `passed`: that verdict was pass.
    - `counts_as_correct`: it may enter the headline metric, which additionally
      requires math or reality authority. An `ai_judge` pass is a real result and
      is never a verified correct decision.
    """

    decision_id: str
    decision_type: str
    evaluation_name: str
    evaluator_kind: str
    graded: bool
    passed: bool
    authority: Optional[GradeSource]
    reason: ReasonCode
    detail: str
    deferred: bool = False
    authority_downgraded_from: Optional[GradeSource] = None

    @property
    def counts_as_correct(self) -> bool:
        return (
            self.graded
            and self.passed
            and self.authority in (GradeSource.MATH, GradeSource.REALITY)
        )


# --------------------------------------------------------------------------
# The wall: which evidence may be looked at by a grader
# --------------------------------------------------------------------------


def require_gradeable(item: EvidenceItem) -> GradeableEvidence:
    """Guard-clause half of "harness success is not authority"."""
    if isinstance(item, HarnessClaimEvidence):
        raise HarnessClaimIsNotAuthorityError(
            f"evidence {item.evidence_id!r} is a harness_claim. A harness "
            "asserting its own success is evidence that something finished, not "
            "evidence that it was right. Supply an evaluation manifest with an "
            "independent evaluator instead."
        )
    return item


def gradeable_evidence(
    bundle: DecisionEvidenceBundle,
) -> tuple[GradeableEvidence, ...]:
    """The evidence a grader is allowed to see. Harness claims are not in it."""
    return tuple(
        item for item in bundle.evidence
        if not isinstance(item, HarnessClaimEvidence)
    )


@dataclass(frozen=True)
class _Resolved:
    ok: bool
    value: Any
    reason: ReasonCode
    detail: str


def _resolve_value(bundle: DecisionEvidenceBundle) -> _Resolved:
    """Get the concrete value a value-comparing evaluator should grade.

    Preference order: the decision's own `chosen`, then a structured_output
    evidence item. A digest or an artifact reference is deliberately NOT resolved
    here; this package does not fetch artifacts, and comparing a hash to an
    expected plaintext would be a false negative dressed as a verdict.
    """
    chosen = bundle.decision.chosen
    if isinstance(chosen, InlineValue):
        if _is_empty(chosen.value):
            # Nothing to compare is not the same as the wrong answer. Reporting
            # it as a mismatch would blame the agent for a gap in the capture.
            return _Resolved(False, None, ReasonCode.EMPTY_ANSWER,
                             "decision.chosen is an empty inline value")
        return _Resolved(True, chosen.value, ReasonCode.MATCH, "decision.chosen")

    for item in gradeable_evidence(bundle):
        if isinstance(item, StructuredOutputEvidence) and isinstance(
            item.output, InlineValue
        ):
            if _is_empty(item.output.value):
                return _Resolved(False, None, ReasonCode.EMPTY_ANSWER,
                                 f"evidence {item.evidence_id} carries an empty "
                                 "inline value")
            return _Resolved(True, item.output.value, ReasonCode.MATCH,
                             f"evidence {item.evidence_id}")

    if isinstance(chosen, AbsentValue):
        return _Resolved(
            False, None, ReasonCode.EMPTY_ANSWER,
            f"chosen is absent (reason: {chosen.reason}) and no structured_output "
            "evidence carries an inline value",
        )
    if isinstance(chosen, (DigestValue, ArtifactReference)):
        return _Resolved(
            False, None, ReasonCode.AMBIGUOUS,
            f"chosen is carried as {chosen.KIND}; this package does not fetch "
            "artifacts, so the value cannot be compared here",
        )
    return _Resolved(False, None, ReasonCode.AMBIGUOUS, "chosen is unresolvable")


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def evaluate(
    bundle: DecisionEvidenceBundle,
    manifest: EvaluationManifest,
    *,
    context: Optional[EvaluationContext] = None,
) -> EvaluationResult:
    """Grade one decision against its manifest. Never trusts the bundle."""
    ctx = context or EvaluationContext()
    identity = resolve_decision_identity(bundle)

    if manifest.decision_type != bundle.decision.decision_type:
        raise ManifestMismatchError(
            f"manifest grades decision_type {manifest.decision_type!r} but the "
            f"bundle is {bundle.decision.decision_type!r}. Only decisions of the "
            "same type may be compared, because harnesses draw decision "
            "boundaries differently."
        )
    if manifest.evaluation_name != bundle.decision.evaluation_name:
        raise ManifestMismatchError(
            f"manifest grades {manifest.evaluation_name!r} but the bundle names "
            f"{bundle.decision.evaluation_name!r}"
        )

    evaluator = manifest.evaluator
    _check_authority_shape(manifest, evaluator)

    downgraded_from: Optional[GradeSource] = None
    authority = manifest.authority

    if isinstance(evaluator, OutcomeEvaluator):
        return _build(
            identity.decision_id, bundle, evaluator.KIND,
            CheckResult(False, ReasonCode.NO_GROUND_TRUTH), authority,
            detail=(
                f"awaiting a {evaluator.outcome_type!r} outcome record; reality "
                "authority is conferred by what happens later, not by a checker"
            ),
            deferred=True,
        )

    if isinstance(evaluator, ExactEqualityEvaluator):
        check, detail = _exact_equality(bundle, evaluator)
    elif isinstance(evaluator, JsonEqualityEvaluator):
        check, detail = _json_equality(bundle, evaluator)
    elif isinstance(evaluator, JsonSchemaEvaluator):
        check, detail = _json_schema(bundle, evaluator)
    elif isinstance(evaluator, CommandExitCodeEvaluator):
        check, detail = _command_exit_code(bundle, evaluator)
    elif isinstance(evaluator, FileDigestEvaluator):
        check, detail = _file_digest(bundle, evaluator)
    elif isinstance(evaluator, CallbackEvaluator):
        check, detail, authority, downgraded_from = _callback(
            bundle, evaluator, ctx, manifest
        )
    else:  # pragma: no cover - the union above is exhaustive
        raise InvalidManifestError(f"unsupported evaluator {evaluator!r}")

    return _build(identity.decision_id, bundle, evaluator.KIND, check, authority,
                  detail=detail, downgraded_from=downgraded_from)


def _check_authority_shape(manifest: EvaluationManifest,
                           evaluator: Evaluator) -> None:
    """Re-check what the schema enforces. Schemas are data, and data gets edited."""
    if manifest.authority is Authority.MATH and isinstance(evaluator, OutcomeEvaluator):
        raise InvalidManifestError(
            "math authority cannot come from an outcome evaluator; an outcome is "
            "reality authority and arrives later"
        )
    if manifest.authority is Authority.REALITY and not isinstance(
        evaluator, OutcomeEvaluator
    ):
        raise InvalidManifestError(
            f"reality authority requires the outcome evaluator, not "
            f"{evaluator.KIND!r}; reality is conferred by a later result, never by "
            "running a checker at decision time"
        )


def _build(decision_id: str, bundle: DecisionEvidenceBundle, evaluator_kind: str,
           check: CheckResult, authority: Authority, *, detail: str,
           deferred: bool = False,
           downgraded_from: Optional[GradeSource] = None) -> EvaluationResult:
    graded = check.reason.is_machine_checked
    source: Optional[GradeSource] = None
    if graded:
        source = (
            GradeSource.MATH if authority is Authority.MATH else GradeSource.AI_JUDGE
        )
    return EvaluationResult(
        decision_id=decision_id,
        decision_type=bundle.decision.decision_type,
        evaluation_name=bundle.decision.evaluation_name,
        evaluator_kind=evaluator_kind,
        graded=graded,
        passed=check.passed and graded,
        authority=source,
        reason=check.reason,
        detail=detail,
        deferred=deferred,
        authority_downgraded_from=downgraded_from,
    )


# --------------------------------------------------------------------------
# The evaluators
# --------------------------------------------------------------------------


def _exact_equality(bundle: DecisionEvidenceBundle,
                    evaluator: ExactEqualityEvaluator) -> tuple[CheckResult, str]:
    resolved = _resolve_value(bundle)
    if not resolved.ok:
        return CheckResult(False, resolved.reason), resolved.detail

    chosen = resolved.value
    expected = evaluator.expected
    if isinstance(chosen, str) and isinstance(expected, str):
        if evaluator.trim_whitespace:
            chosen, expected = chosen.strip(), expected.strip()
        if not evaluator.case_sensitive:
            chosen, expected = chosen.casefold(), expected.casefold()
    # No cross-type coercion: "1" is not 1. A harness that reports the right
    # answer in the wrong type has a real bug, and hiding it here would hide it
    # everywhere downstream too.
    return (
        CheckResult.decided(_json_equal(chosen, expected)),
        f"compared {resolved.detail} against the manifest's expected value",
    )


def _json_equality(bundle: DecisionEvidenceBundle,
                   evaluator: JsonEqualityEvaluator) -> tuple[CheckResult, str]:
    resolved = _resolve_value(bundle)
    if not resolved.ok:
        return CheckResult(False, resolved.reason), resolved.detail
    return (
        CheckResult.decided(_json_equal(resolved.value, evaluator.expected)),
        f"structural JSON comparison of {resolved.detail}",
    )


def _json_schema(bundle: DecisionEvidenceBundle,
                 evaluator: JsonSchemaEvaluator) -> tuple[CheckResult, str]:
    resolved = _resolve_value(bundle)
    if not resolved.ok:
        return CheckResult(False, resolved.reason), resolved.detail
    failure = _schema_failure(resolved.value, evaluator.schema, "")
    if failure is not None:
        return (
            CheckResult.decided(False),
            f"{resolved.detail} does not satisfy the manifest schema: {failure}",
        )
    # Shape, not truth. A weaker authority than an oracle, still deterministic.
    return CheckResult.decided(True), f"{resolved.detail} satisfies the manifest schema"


def _command_exit_code(bundle: DecisionEvidenceBundle,
                       evaluator: CommandExitCodeEvaluator
                       ) -> tuple[CheckResult, str]:
    """Grade a command's exit status, which the MANIFEST named and the evidence
    merely reports.

    Matching is BY NAME ONLY: command_name equal to argv joined by single spaces,
    or equal to argv[0]. There is deliberately no fallback to "whatever
    command_result happens to be in the bundle". The manifest declares the command
    precisely so the graded process cannot choose its own grader, and a fallback
    that accepts any command result hands that choice straight back to the
    harness: emit one command_result with an unrelated name and a zero exit code,
    and it becomes the verdict for a test that never ran. That is the callback
    determinism hole one layer down, and it is closed the same way.

    Zero matches cannot be graded, and more than one is ambiguous, because picking
    between two exit codes would be picking the answer.
    """
    joined = " ".join(evaluator.command)
    head = evaluator.command[0] if evaluator.command else ""
    candidates = [
        item for item in gradeable_evidence(bundle)
        if isinstance(item, CommandResultEvidence)
        and item.command_name in (joined, head)
    ]

    if not candidates:
        return (
            CheckResult(False, ReasonCode.NO_GROUND_TRUTH),
            f"no command_result evidence names {joined!r} or {head!r}; an "
            "unrelated command result is not a substitute, because the manifest "
            "names the command so the graded process cannot pick its own grader",
        )
    if len(candidates) > 1:
        return (
            CheckResult(False, ReasonCode.AMBIGUOUS),
            f"{len(candidates)} command_result items could be {joined!r}: "
            + ", ".join(item.evidence_id for item in candidates),
        )
    actual = candidates[0].exit_code
    return (
        CheckResult.decided(actual == evaluator.expected_exit_code),
        f"{candidates[0].evidence_id} reports exit {actual}, manifest expects "
        f"{evaluator.expected_exit_code}",
    )


def _file_digest(bundle: DecisionEvidenceBundle, evaluator: FileDigestEvaluator
                 ) -> tuple[CheckResult, str]:
    """Compare a file's reported digest to the digest the manifest expects.

    Identical rule to the command evaluator, for the identical reason: match
    file_state evidence by EXACT path, zero is no_ground_truth, more than one is
    ambiguous, and there is no fallback to some other file that happens to be in
    the bundle. The manifest names the path and the expected hash; the evidence
    only reports what was observed. Accepting a different file's digest would let
    the graded process choose which file gets graded.

    A digest is content-addressed, so within that rule a harness cannot fake a
    match without producing the matching content.
    """
    candidates = [
        item for item in gradeable_evidence(bundle)
        if isinstance(item, FileStateEvidence) and item.path == evaluator.path
    ]
    if not candidates:
        return (
            CheckResult(False, ReasonCode.NO_GROUND_TRUTH),
            f"no file_state evidence reports {evaluator.path!r}",
        )
    if len(candidates) > 1:
        return (
            CheckResult(False, ReasonCode.AMBIGUOUS),
            f"{len(candidates)} file_state items report {evaluator.path!r}",
        )
    actual = candidates[0].artifact_digest.digest
    return (
        CheckResult.decided(actual == evaluator.expected.digest),
        f"{evaluator.path} digest {actual[:12]}..., manifest expects "
        f"{evaluator.expected.digest[:12]}...",
    )


def _callback(bundle: DecisionEvidenceBundle, evaluator: CallbackEvaluator,
              ctx: EvaluationContext, manifest: EvaluationManifest,
              ) -> tuple[CheckResult, str, Authority, Optional[GradeSource]]:
    """Run an application checker, with the registry as the determinism authority.

    One directional. A manifest may always claim LESS than its checker could
    support, because a downgrade cannot inflate the headline metric. The direction
    that is policed is the manifest OVERSTATING the checker: declaring
    'deterministic' for something the application itself registered as
    model-assisted. That case still RUNS, because the opinion is worth having, but
    it is graded ai_judge and the downgrade is recorded, so nobody has to
    reconstruct later why a math grade did not appear.
    """
    entry = ctx.checkers.resolve(evaluator.name)

    authority = manifest.authority
    downgraded_from: Optional[GradeSource] = None
    overstated = (
        evaluator.determinism is Determinism.DETERMINISTIC
        and entry.determinism is Determinism.MODEL_ASSISTED
    )
    if entry.determinism is Determinism.MODEL_ASSISTED and authority is Authority.MATH:
        downgraded_from = GradeSource.MATH
        authority = Authority.AI_JUDGE
    elif entry.determinism is Determinism.MODEL_ASSISTED and authority is Authority.REALITY:
        authority = Authority.AI_JUDGE

    outcome = entry.checker(bundle.decision.chosen, evaluator.options)
    check = outcome if isinstance(outcome, CheckResult) else CheckResult.decided(
        bool(outcome)
    )
    note = (
        " (manifest declared it deterministic; the registry is closer to the code "
        "and wins)" if overstated else ""
    )
    return (
        check,
        f"checker {evaluator.name!r} ({entry.determinism.value}) returned "
        f"{check.reason.value}{note}",
        authority,
        downgraded_from,
    )


# --------------------------------------------------------------------------
# JSON equality and the documented JSON Schema keyword subset
# --------------------------------------------------------------------------


def _json_equal(left: Any, right: Any) -> bool:
    """JSON equality, where true is not 1.

    Python's `==` says True == 1. JSON says a boolean and a number are different
    types. Grading is exactly the place where that difference matters, so the
    types are compared before the values.
    """
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return False
        return all(_json_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        # Arrays are order sensitive, objects are not. That is the JSON contract.
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, Mapping) != isinstance(right, Mapping):
        return False
    if isinstance(left, list) != isinstance(right, list):
        return False
    return bool(left == right)


# The keyword subset the json_schema evaluator implements. Anything else in a
# manifest schema is IGNORED rather than half-honoured, and the list is published
# here so an author knows exactly what their schema will and will not enforce.
# A partial implementation that pretended to be complete would produce confident
# passes on constraints nobody checked.
JSON_SCHEMA_KEYWORDS: tuple[str, ...] = (
    "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "minItems", "maxItems", "minimum", "maximum", "minLength",
    "maxLength", "pattern",
)


def _schema_failure(value: Any, schema: Mapping[str, Any], path: str) -> Optional[str]:
    """First failure of the supported keywords, or None. Depth-first, stable."""
    where = path or "the value"

    if "type" in schema:
        types = schema["type"]
        allowed = [types] if isinstance(types, str) else list(types)
        if not any(_is_json_type(value, name) for name in allowed):
            return f"{where} is not of type {'/'.join(allowed)}"
    if "const" in schema and not _json_equal(value, schema["const"]):
        return f"{where} does not equal the required const"
    if "enum" in schema and not any(
        _json_equal(value, option) for option in schema["enum"]
    ):
        return f"{where} is not one of the enumerated values"

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            return f"{where} is shorter than {schema['minLength']}"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{where} is longer than {schema['maxLength']}"
        # Known non-conformance, recorded rather than silently lived with: this
        # runs a manifest author's pattern through Python's `re`, whose `$` also
        # matches before a trailing newline, while JSON Schema specifies ECMA-262
        # where it does not. The patterns this package owns use `\Z` for that
        # reason (see validation.py), but a pattern that arrives inside a manifest
        # cannot be rewritten safely, so an author who anchors with `$` will get
        # slightly different verdicts in the two languages.
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return f"{where} does not match {schema['pattern']}"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{where} is below the minimum {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{where} is above the maximum {schema['maximum']}"

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            return f"{where} has fewer than {schema['minItems']} items"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{where} has more than {schema['maxItems']} items"
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                failure = _schema_failure(item, item_schema, f"{path}[{index}]")
                if failure is not None:
                    return failure

    if isinstance(value, Mapping):
        for name in schema.get("required", ()):
            if name not in value:
                return f"{where} is missing required property {name!r}"
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            for name, subschema in properties.items():
                if name in value and isinstance(subschema, Mapping):
                    failure = _schema_failure(value[name], subschema,
                                              f"{path}.{name}" if path else name)
                    if failure is not None:
                        return failure
            # Only the boolean form is supported, which is what the subset says.
            if schema.get("additionalProperties") is False:
                extra = sorted(set(value) - set(properties))
                if extra:
                    return f"{where} has unexpected properties: {', '.join(extra)}"
    return None


def _is_json_type(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (
            isinstance(value, float) and value.is_integer()
        )
    if name == "number":
        return not isinstance(value, bool) and isinstance(value, (int, float))
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, Mapping)
    return False


def evidence_of_kind(bundle: DecisionEvidenceBundle,
                     kind: str) -> Sequence[GradeableEvidence]:
    """Gradeable evidence of one kind. Harness claims are unreachable here."""
    return [item for item in gradeable_evidence(bundle) if item.KIND == kind]
