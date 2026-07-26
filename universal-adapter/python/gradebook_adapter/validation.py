"""Hand written validation that returns ACTIONABLE errors and never raises.

Why hand written when the JSON Schemas already exist: a schema library reports
"is not valid under any of the given schemas" for a mistyped evidence item,
which tells an integrator nothing about which of seven shapes they nearly hit.
The whole promise of this protocol is that an unknown future harness can
integrate without asking us, and that promise dies on unactionable errors. So
every error here carries three things: a JSON pointer to the exact spot, what
was wrong, and what was expected instead.

The cost of hand writing is drift: this file can quietly stop agreeing with the
frozen schemas. That risk is paid for by tests/test_schema_parity.py, which runs
the whole fixture corpus through BOTH this validator and a real JSON Schema
validation and fails if the two ever reach different verdicts. Treat that test
as part of this module.

Nothing here raises for invalid input. Invalid input is the expected case for a
validator, and a caller collecting errors from a JSONL stream must be able to
keep reading the stream (issue #101: partial ingestion must not silently corrupt
completed records).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

SCHEMA_VERSION = "1.0"

_IDENTIFIER_MAX = 512
_STRING_MAX = 2048

# `\Z` and NEVER `$`, in every pattern in this file.
#
# JSON Schema specifies ECMA-262 regex semantics, where `$` matches only at the
# very end of the string. Python's `re` also matches `$` just before a trailing
# newline, so "abc...\n" satisfies `^[0-9a-f]{64}$` in Python and fails the same
# pattern in JavaScript. Python is the non-conformant one here, so `\Z`, which
# means end-of-string and nothing else, is what actually implements the schema.
#
# This is invisible to tests/test_schema_parity.py, and that is the important
# part: the `jsonschema` package uses Python's `re` too, so both sides of the
# anti-drift check share the same wrong semantics and agree with each other. It
# was caught by the cross-language parity runner and can only be caught there.
# There is a targeted test per affected field type; do not "simplify" `\Z` back
# to `$`.
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}\Z")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}\Z")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}\Z")
# RFC 3339 shape. Calendar validity is checked separately below, because a
# regex happily accepts 2026-02-31.
# [0-9] and not \d: Python's \d matches Unicode digits such as U+0660, the
# schema's ECMA regex does not, and that difference alone would be a parity break.
_RFC3339_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(\.[0-9]+)?([Zz]|[+-][0-9]{2}:[0-9]{2})\Z"
)


@dataclass(frozen=True)
class ValidationError:
    """One problem, at one place, with the fix implied.

    `path` is an RFC 6901 JSON pointer into the record as submitted, so an error
    can be reported against a file and a location rather than against a concept.
    """

    path: str
    message: str
    expected: str

    def __str__(self) -> str:
        return f"{self.path or '/'}: {self.message}; expected {self.expected}"


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------


def validate_decision_evidence_bundle(data: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not _object(errors, "", data, "decision evidence bundle",
                   required=("schema_version", "decision", "subject", "evidence"),
                   allowed=("schema_version", "decision", "subject", "correlation",
                            "evidence", "usage_refs", "metadata", "ext")):
        return errors

    _schema_version(errors, data)

    if "decision" in data:
        _decision(errors, "/decision", data["decision"])
    if "subject" in data:
        _subject(errors, "/subject", data["subject"])
    if "correlation" in data:
        _correlation(errors, "/correlation", data["correlation"])
    if "evidence" in data:
        _evidence_array(errors, "/evidence", data["evidence"])
    if "usage_refs" in data:
        _identifier_array(errors, "/usage_refs", data["usage_refs"], "usage_refs")
    if "metadata" in data:
        _label_map(errors, "/metadata", data["metadata"], "metadata")
    if "ext" in data:
        _ext(errors, "/ext", data["ext"])
    return errors


def validate_usage_record(data: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not _object(errors, "", data, "usage record",
                   required=("schema_version", "usage_id", "scope", "run_id",
                             "cost_provenance"),
                   allowed=("schema_version", "usage_id", "scope", "run_id", "agent_id",
                            "parent_agent_id", "contains_usage_ids", "decision_ids",
                            "provider_response_id", "model", "input_tokens",
                            "output_tokens", "cached_input_tokens", "provider_cost_usd",
                            "cost_provenance", "pricing_table_id", "ext")):
        return errors

    _schema_version(errors, data)
    if "usage_id" in data:
        _identifier(errors, "/usage_id", data["usage_id"])
    if "run_id" in data:
        _identifier(errors, "/run_id", data["run_id"])
    if "scope" in data:
        _enum(errors, "/scope", data["scope"], USAGE_SCOPES)
    if "cost_provenance" in data:
        _enum(errors, "/cost_provenance", data["cost_provenance"], COST_PROVENANCES)
    for key in ("agent_id", "parent_agent_id"):
        if key in data:
            _nullable_identifier(errors, f"/{key}", data[key])
    for key in ("contains_usage_ids", "decision_ids"):
        if key in data:
            _identifier_array(errors, f"/{key}", data[key], key)
    for key in ("provider_response_id", "model", "pricing_table_id"):
        if key in data:
            _nullable_string(errors, f"/{key}", data[key])
    for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
        if key in data:
            _nullable_token_count(errors, f"/{key}", data[key])
    if "provider_cost_usd" in data:
        _nullable_number(errors, "/provider_cost_usd", data["provider_cost_usd"],
                         minimum=0)
    if "ext" in data:
        _ext(errors, "/ext", data["ext"])

    _usage_conditionals(errors, data)
    return errors


def validate_evaluation_manifest(data: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not _object(errors, "", data, "evaluation manifest",
                   required=("schema_version", "task_id", "decision_type",
                             "evaluation_name", "authority", "evaluator"),
                   allowed=("schema_version", "task_id", "decision_type",
                            "evaluation_name", "authority", "evaluator",
                            "description", "ext")):
        return errors

    _schema_version(errors, data)
    for key in ("task_id", "decision_type", "evaluation_name"):
        if key in data:
            _identifier(errors, f"/{key}", data[key])
    if "authority" in data:
        _enum(errors, "/authority", data["authority"], AUTHORITIES)
    if "evaluator" in data:
        _evaluator(errors, "/evaluator", data["evaluator"],
                   authority=data.get("authority"))
    if "description" in data:
        _string(errors, "/description", data["description"], max_length=_STRING_MAX)
    if "ext" in data:
        _ext(errors, "/ext", data["ext"])

    _manifest_conditionals(errors, data)
    return errors


def validate_outcome_record(data: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not _object(errors, "", data, "outcome record",
                   required=("schema_version", "outcome_id", "decision_id",
                             "outcome_type", "correct", "observed_at"),
                   allowed=("schema_version", "outcome_id", "decision_id",
                            "provider_response_id", "outcome_type", "correct",
                            "observed_at", "evidence_ref", "explanation", "ext")):
        return errors

    _schema_version(errors, data)
    for key in ("outcome_id", "decision_id", "outcome_type"):
        if key in data:
            _identifier(errors, f"/{key}", data[key])
    for key in ("provider_response_id", "evidence_ref"):
        if key in data:
            _nullable_string(errors, f"/{key}", data[key])
    if "explanation" in data:
        _nullable_string(errors, "/explanation", data["explanation"])
    if "correct" in data and not _is_boolean(data["correct"]):
        # The schema's own note: a truthy 1 silently becoming a passing grade is
        # a known way to corrupt a headline metric, so no coercion.
        errors.append(ValidationError(
            "/correct",
            f"reality verdict is {_describe(data['correct'])}",
            "a JSON boolean, true or false, never 1 or 0 or a string",
        ))
    if "observed_at" in data:
        _date_time(errors, "/observed_at", data["observed_at"])
    if "ext" in data:
        _ext(errors, "/ext", data["ext"])
    return errors


RECORD_VALIDATORS: Mapping[str, Callable[[Any], list[ValidationError]]] = {
    "decision-evidence-bundle": validate_decision_evidence_bundle,
    "usage-record": validate_usage_record,
    "evaluation-manifest": validate_evaluation_manifest,
    "outcome-record": validate_outcome_record,
}


class UnknownRecordTypeError(ValueError):
    """The caller asked for a record type this protocol does not define."""


def validate_record(data: Any, record_type: str) -> list[ValidationError]:
    """Validate `data` as `record_type`, e.g. 'usage-record'.

    Raises only for an unknown record type, which is a caller bug rather than a
    data problem. Bad data always comes back as a list of errors.
    """
    try:
        validator = RECORD_VALIDATORS[record_type]
    except KeyError:
        known = ", ".join(sorted(RECORD_VALIDATORS))
        raise UnknownRecordTypeError(
            f"unknown record type {record_type!r}; known types are {known}"
        ) from None
    return validator(data)


def infer_record_type(data: Any) -> Optional[str]:
    """Guess which of the four records `data` is, by its discriminating field.

    Used only where the caller genuinely does not know (a mixed JSONL stream, a
    fixture index that omits the type). Returns None rather than guessing when
    nothing discriminates, because validating a record as the wrong type would
    produce confidently wrong errors.
    """
    if not isinstance(data, Mapping):
        return None
    if "usage_id" in data:
        return "usage-record"
    if "outcome_id" in data:
        return "outcome-record"
    if "evaluator" in data or "authority" in data:
        return "evaluation-manifest"
    if "decision" in data or "subject" in data:
        return "decision-evidence-bundle"
    return None


# --------------------------------------------------------------------------
# Closed vocabularies, mirrored from the schemas
# --------------------------------------------------------------------------

USAGE_SCOPES: tuple[str, ...] = ("model_invocation", "decision", "agent", "run")
COST_PROVENANCES: tuple[str, ...] = (
    "provider_reported",
    "provider_token_estimate",
    "harness_token_estimate",
    "run_aggregate",
    "unknown",
)
AUTHORITIES: tuple[str, ...] = ("math", "reality", "ai_judge")
ABSENT_REASONS: tuple[str, ...] = ("redacted", "not_captured", "too_large", "unknown")
DETERMINISTIC_EVALUATOR_KINDS: tuple[str, ...] = (
    "exact_equality",
    "json_equality",
    "command_exit_code",
    "file_digest",
    "json_schema",
    "callback",
)
EVALUATOR_KINDS: tuple[str, ...] = DETERMINISTIC_EVALUATOR_KINDS + ("outcome",)
# A callback is the one evaluator arm whose determinism is invisible in its
# shape, so it has to say. No default: a defaulted value would be a guess about
# the one property that decides whether a result may reach the headline metric.
DETERMINISM_KINDS: tuple[str, ...] = ("deterministic", "model_assisted")
EVIDENCE_KINDS: tuple[str, ...] = (
    "command_result",
    "file_state",
    "test_report",
    "structured_output",
    "otel_span",
    "log_reference",
    "harness_claim",
)
VALUE_KINDS: tuple[str, ...] = ("inline", "digest", "artifact_reference", "absent")


# --------------------------------------------------------------------------
# Record parts
# --------------------------------------------------------------------------


def _schema_version(errors: list[ValidationError], data: Mapping[str, Any]) -> None:
    if "schema_version" not in data:
        return
    version = data["schema_version"]
    if version != SCHEMA_VERSION:
        errors.append(ValidationError(
            "/schema_version",
            f"unsupported protocol version {version!r}",
            f"the string {SCHEMA_VERSION!r}; a consumer must reject a version it "
            "does not implement rather than guess at it",
        ))


def _decision(errors: list[ValidationError], path: str, value: Any) -> None:
    if not _object(errors, path, value, "decision",
                   required=("decision_type", "evaluation_name", "chosen"),
                   allowed=("decision_id", "decision_type", "evaluation_name", "chosen")):
        return
    for key in ("decision_id", "decision_type", "evaluation_name"):
        if key in value:
            _identifier(errors, f"{path}/{key}", value[key])
    if "chosen" in value:
        _value(errors, f"{path}/chosen", value["chosen"])


def _subject(errors: list[ValidationError], path: str, value: Any) -> None:
    if not _object(errors, path, value, "subject",
                   required=("harness", "run_id"),
                   allowed=("harness", "harness_version", "run_id", "session_id",
                            "agent_id", "parent_agent_id", "model")):
        return
    for key in ("harness", "run_id"):
        if key in value:
            _identifier(errors, f"{path}/{key}", value[key])
    for key in ("harness_version", "model"):
        if key in value:
            _nullable_string(errors, f"{path}/{key}", value[key])
    for key in ("session_id", "agent_id", "parent_agent_id"):
        if key in value:
            _nullable_identifier(errors, f"{path}/{key}", value[key])


def _correlation(errors: list[ValidationError], path: str, value: Any) -> None:
    if not _object(errors, path, value, "correlation", required=(),
                   allowed=("provider_response_id", "trace_id", "span_id", "task_id")):
        return
    if "provider_response_id" in value:
        _nullable_string(errors, f"{path}/provider_response_id",
                         value["provider_response_id"])
    if "trace_id" in value:
        _nullable_pattern(errors, f"{path}/trace_id", value["trace_id"], _TRACE_ID_RE,
                          "32 lowercase hex characters, the W3C trace id, as a string")
    if "span_id" in value:
        _nullable_pattern(errors, f"{path}/span_id", value["span_id"], _SPAN_ID_RE,
                          "16 lowercase hex characters, the W3C span id, as a string")
    if "task_id" in value:
        _nullable_identifier(errors, f"{path}/task_id", value["task_id"])


def _evidence_array(errors: list[ValidationError], path: str, value: Any) -> None:
    if not _array(errors, path, value, "evidence"):
        return
    for index, item in enumerate(value):
        _evidence_item(errors, f"{path}/{index}", item)


def _evidence_item(errors: list[ValidationError], path: str, value: Any) -> None:
    if not isinstance(value, Mapping):
        errors.append(ValidationError(path, f"evidence item is {_describe(value)}",
                                      "an object"))
        return
    for key in ("evidence_id", "kind"):
        if key not in value:
            errors.append(ValidationError(path, f"required property {key!r} is missing",
                                          f"every evidence item to carry {key!r}"))
    if "evidence_id" in value:
        _identifier(errors, f"{path}/evidence_id", value["evidence_id"])
    kind = value.get("kind")
    if kind not in EVIDENCE_KINDS:
        if "kind" in value:
            errors.append(ValidationError(
                f"{path}/kind", f"unknown evidence kind {kind!r}",
                f"one of {', '.join(EVIDENCE_KINDS)}",
            ))
        return

    if kind == "command_result":
        _closed(errors, path, value, kind,
                required=("evidence_id", "kind", "command_name", "exit_code"),
                allowed=("evidence_id", "kind", "command_name", "exit_code",
                         "duration_ms", "artifact_digest"))
        if "command_name" in value:
            _identifier(errors, f"{path}/command_name", value["command_name"])
        if "exit_code" in value:
            _integer(errors, f"{path}/exit_code", value["exit_code"])
        if "duration_ms" in value:
            _integer(errors, f"{path}/duration_ms", value["duration_ms"], minimum=0)
        _optional_digest(errors, path, value, "artifact_digest")
    elif kind == "file_state":
        _closed(errors, path, value, kind,
                required=("evidence_id", "kind", "path", "artifact_digest"),
                allowed=("evidence_id", "kind", "path", "artifact_digest"))
        if "path" in value:
            _string(errors, f"{path}/path", value["path"], min_length=1,
                    max_length=_STRING_MAX)
        _optional_digest(errors, path, value, "artifact_digest")
    elif kind == "test_report":
        _closed(errors, path, value, kind,
                required=("evidence_id", "kind", "passed", "failed"),
                allowed=("evidence_id", "kind", "passed", "failed", "skipped",
                         "artifact_digest"))
        for key in ("passed", "failed", "skipped"):
            if key in value:
                _integer(errors, f"{path}/{key}", value[key], minimum=0)
        _optional_digest(errors, path, value, "artifact_digest")
    elif kind == "structured_output":
        _closed(errors, path, value, kind,
                required=("evidence_id", "kind", "output"),
                allowed=("evidence_id", "kind", "output"))
        if "output" in value:
            _value(errors, f"{path}/output", value["output"])
    elif kind == "otel_span":
        _closed(errors, path, value, kind,
                required=("evidence_id", "kind", "trace_id", "span_id"),
                allowed=("evidence_id", "kind", "trace_id", "span_id"))
        if "trace_id" in value:
            _pattern(errors, f"{path}/trace_id", value["trace_id"], _TRACE_ID_RE,
                     "32 lowercase hex characters")
        if "span_id" in value:
            _pattern(errors, f"{path}/span_id", value["span_id"], _SPAN_ID_RE,
                     "16 lowercase hex characters")
    elif kind == "log_reference":
        _closed(errors, path, value, kind,
                required=("evidence_id", "kind", "ref"),
                allowed=("evidence_id", "kind", "ref", "artifact_digest"))
        if "ref" in value:
            _string(errors, f"{path}/ref", value["ref"], min_length=1,
                    max_length=_STRING_MAX)
        _optional_digest(errors, path, value, "artifact_digest")
    elif kind == "harness_claim":
        _closed(errors, path, value, kind,
                required=("evidence_id", "kind", "claim"),
                allowed=("evidence_id", "kind", "claim"))
        if "claim" in value:
            _label_map(errors, f"{path}/claim", value["claim"], "harness claim")


def _value(errors: list[ValidationError], path: str, value: Any) -> None:
    """The tagged value union, dispatched on `kind`."""
    if not isinstance(value, Mapping):
        errors.append(ValidationError(path, f"value is {_describe(value)}",
                                      "an object tagged with a 'kind'"))
        return
    if "kind" not in value:
        errors.append(ValidationError(
            path, "required property 'kind' is missing",
            f"one of {', '.join(VALUE_KINDS)}; a value is a tagged union so that "
            "it can be carried by digest or by reference instead of inline",
        ))
        return
    kind = value.get("kind")
    if kind == "inline":
        _closed(errors, path, value, "inline value", required=("kind", "value"),
                allowed=("kind", "value"))
    elif kind == "digest":
        _closed(errors, path, value, "digest value",
                required=("kind", "algorithm", "digest"),
                allowed=("kind", "algorithm", "digest", "byte_length"))
        _digest_fields(errors, path, value)
    elif kind == "artifact_reference":
        _closed(errors, path, value, "artifact_reference value",
                required=("kind", "value"), allowed=("kind", "value", "digest"))
        if "value" in value:
            _string(errors, f"{path}/value", value["value"], min_length=1,
                    max_length=_STRING_MAX)
        if "digest" in value:
            _digest(errors, f"{path}/digest", value["digest"])
    elif kind == "absent":
        _closed(errors, path, value, "absent value", required=("kind", "reason"),
                allowed=("kind", "reason"))
        if "reason" in value:
            _enum(errors, f"{path}/reason", value["reason"], ABSENT_REASONS)
    else:
        errors.append(ValidationError(
            f"{path}/kind", f"unknown value kind {kind!r}",
            f"one of {', '.join(VALUE_KINDS)}",
        ))


def _evaluator(errors: list[ValidationError], path: str, value: Any, *,
               authority: Any = None) -> None:
    """Validate the evaluator union.

    `authority` is passed in so the callback arm can say the specific thing when
    `determinism` is missing under math authority. Two errors at one path, one
    generic and one specific, is worse than one specific error: the reader has to
    work out which of them to act on.
    """
    if not isinstance(value, Mapping):
        errors.append(ValidationError(path, f"evaluator is {_describe(value)}",
                                      "an object tagged with a 'kind'"))
        return
    if "kind" not in value:
        errors.append(ValidationError(
            path, "required property 'kind' is missing",
            f"one of {', '.join(EVALUATOR_KINDS)}",
        ))
        return
    kind = value.get("kind")
    if kind == "exact_equality":
        _closed(errors, path, value, kind, required=("kind", "expected"),
                allowed=("kind", "expected", "case_sensitive", "trim_whitespace"))
        for key in ("case_sensitive", "trim_whitespace"):
            if key in value and not _is_boolean(value[key]):
                errors.append(ValidationError(f"{path}/{key}",
                                              f"{key} is {_describe(value[key])}",
                                              "a boolean"))
    elif kind == "json_equality":
        _closed(errors, path, value, kind, required=("kind", "expected"),
                allowed=("kind", "expected"))
    elif kind == "command_exit_code":
        _closed(errors, path, value, kind,
                required=("kind", "command", "expected_exit_code"),
                allowed=("kind", "command", "expected_exit_code", "timeout_seconds",
                         "working_directory"))
        if "command" in value:
            if not _array(errors, f"{path}/command", value["command"], "command"):
                pass
            elif not value["command"]:
                errors.append(ValidationError(
                    f"{path}/command", "command is empty",
                    "at least one argv element; argv form is required so that "
                    "there is no shell to inject into",
                ))
            else:
                for index, part in enumerate(value["command"]):
                    _string(errors, f"{path}/command/{index}", part)
        if "expected_exit_code" in value:
            _integer(errors, f"{path}/expected_exit_code", value["expected_exit_code"])
        if "timeout_seconds" in value:
            _number(errors, f"{path}/timeout_seconds", value["timeout_seconds"],
                    exclusive_minimum=0)
        if "working_directory" in value:
            _string(errors, f"{path}/working_directory", value["working_directory"],
                    max_length=_STRING_MAX)
    elif kind == "file_digest":
        _closed(errors, path, value, kind, required=("kind", "path", "expected"),
                allowed=("kind", "path", "expected"))
        if "path" in value:
            _string(errors, f"{path}/path", value["path"], min_length=1,
                    max_length=_STRING_MAX)
        if "expected" in value:
            _digest(errors, f"{path}/expected", value["expected"])
    elif kind == "json_schema":
        _closed(errors, path, value, kind, required=("kind", "schema"),
                allowed=("kind", "schema"))
        if "schema" in value and not isinstance(value["schema"], Mapping):
            errors.append(ValidationError(f"{path}/schema",
                                          f"schema is {_describe(value['schema'])}",
                                          "an object"))
    elif kind == "callback":
        _closed(errors, path, value, kind, required=("kind", "name"),
                allowed=("kind", "name", "determinism", "options"))
        if "name" in value:
            _identifier(errors, f"{path}/name", value["name"])
        if "determinism" not in value:
            errors.append(ValidationError(
                path, "required property 'determinism' is missing",
                "'deterministic' when authority is 'math'; a callback is the one "
                "evaluator whose determinism the schema cannot inspect, so it "
                "must be declared and can never be defaulted"
                if authority == "math" else
                "one of " + ", ".join(DETERMINISM_KINDS)
                + "; a callback must declare whether it computes its verdict or "
                "asks a model for one",
            ))
        else:
            _enum(errors, f"{path}/determinism", value["determinism"], DETERMINISM_KINDS)
        if "options" in value:
            _label_map(errors, f"{path}/options", value["options"], "callback options")
    elif kind == "outcome":
        _closed(errors, path, value, kind, required=("kind", "outcome_type"),
                allowed=("kind", "outcome_type", "observation_window_seconds"))
        if "outcome_type" in value:
            _identifier(errors, f"{path}/outcome_type", value["outcome_type"])
        if "observation_window_seconds" in value:
            _number(errors, f"{path}/observation_window_seconds",
                    value["observation_window_seconds"], exclusive_minimum=0)
    else:
        errors.append(ValidationError(
            f"{path}/kind", f"unknown evaluator kind {kind!r}",
            f"one of {', '.join(EVALUATOR_KINDS)}",
        ))


def _manifest_conditionals(errors: list[ValidationError],
                           data: Mapping[str, Any]) -> None:
    """The two structural rules the manifest schema enforces with if/then.

    These are the protocol's most important rule made mechanical: a model's
    opinion cannot be laundered into the headline metric by editing one field.
    """
    authority = data.get("authority")
    evaluator = data.get("evaluator")
    if not isinstance(evaluator, Mapping):
        return
    kind = evaluator.get("kind")
    if authority == "math" and "kind" in evaluator:
        if kind not in DETERMINISTIC_EVALUATOR_KINDS:
            errors.append(ValidationError(
                "/evaluator/kind",
                f"evaluator kind {kind!r} cannot carry math authority",
                "one of " + ", ".join(DETERMINISTIC_EVALUATOR_KINDS)
                + "; math authority requires a deterministic, machine-verifiable "
                "evaluator",
            ))
        elif kind == "callback":
            # The schema cannot see what a named callback does, so it forces the
            # claim to be written down. This check only catches the honest half:
            # the dishonest half is caught at registration time in evaluation.py,
            # where the registry knows what the checker really is.
            # The missing case is reported by the arm itself, which already knows
            # the authority, so it says the specific thing once instead of twice.
            declared = evaluator.get("determinism")
            if "determinism" in evaluator and declared != "deterministic":
                errors.append(ValidationError(
                    "/evaluator/determinism",
                    f"callback declares determinism {declared!r} under math "
                    "authority",
                    "'deterministic'; a model-assisted checker is an opinion and "
                    "is graded ai_judge, never math",
                ))
    if authority == "reality" and "kind" in evaluator:
        if kind != "outcome":
            errors.append(ValidationError(
                "/evaluator/kind",
                f"evaluator kind {kind!r} cannot carry reality authority",
                "the 'outcome' evaluator; reality authority is conferred by a "
                "result that arrives later, not by running a checker now",
            ))


def _usage_conditionals(errors: list[ValidationError],
                        data: Mapping[str, Any]) -> None:
    """The three if/then rules that keep a cost figure honest about itself."""
    provenance = data.get("cost_provenance")

    if provenance in ("provider_token_estimate", "harness_token_estimate"):
        table = data.get("pricing_table_id")
        if "pricing_table_id" not in data:
            errors.append(ValidationError(
                "", "required property 'pricing_table_id' is missing",
                f"a pricing table id whenever cost_provenance is {provenance!r}; a "
                "token-estimated cost is meaningless without the rates behind it",
            ))
        elif not isinstance(table, str) or not table:
            errors.append(ValidationError(
                "/pricing_table_id",
                f"pricing_table_id is {_describe(table)}",
                "a non-empty string of the form gradebook.pricing@<12 hex>",
            ))

    if provenance == "provider_reported":
        cost = data.get("provider_cost_usd")
        if "provider_cost_usd" not in data:
            errors.append(ValidationError(
                "", "required property 'provider_cost_usd' is missing",
                "a provider figure whenever cost_provenance is 'provider_reported'; "
                "claiming that provenance without one is the exact dishonesty the "
                "field exists to prevent",
            ))
        elif not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
            errors.append(ValidationError(
                "/provider_cost_usd",
                f"provider-reported cost is {_describe(cost)}",
                "a number greater than or equal to 0",
            ))

    if provenance == "run_aggregate" and "scope" in data:
        if data.get("scope") != "run":
            errors.append(ValidationError(
                "/scope",
                f"scope {data.get('scope')!r} contradicts cost_provenance "
                "'run_aggregate'",
                "scope 'run'; a run aggregate covers a whole run and cannot also "
                "be scoped to a single call or agent",
            ))


# --------------------------------------------------------------------------
# Primitive checks
# --------------------------------------------------------------------------


def _object(errors: list[ValidationError], path: str, value: Any, what: str, *,
            required: Sequence[str], allowed: Sequence[str]) -> bool:
    if not isinstance(value, Mapping):
        errors.append(ValidationError(path, f"{what} is {_describe(value)}",
                                      "a JSON object"))
        return False
    _closed(errors, path, value, what, required=required, allowed=allowed)
    return True


def _closed(errors: list[ValidationError], path: str, value: Mapping[str, Any],
            what: str, *, required: Sequence[str], allowed: Sequence[str]) -> None:
    """Required fields present, and no unknown fields (ADR 0003)."""
    for key in required:
        if key not in value:
            errors.append(ValidationError(
                path, f"required property {key!r} is missing",
                f"{what} to carry {key!r}",
            ))
    allowed_set = set(allowed)
    for key in value:
        if key not in allowed_set:
            errors.append(ValidationError(
                _pointer(path, key), f"unknown property {key!r}",
                f"one of {', '.join(sorted(allowed_set))}; unknown fields belong "
                "under the record's 'ext' object, which is the one place they are "
                "legal",
            ))


def _array(errors: list[ValidationError], path: str, value: Any, what: str) -> bool:
    if not isinstance(value, list):
        errors.append(ValidationError(path, f"{what} is {_describe(value)}",
                                      "an array"))
        return False
    return True


def _identifier_array(errors: list[ValidationError], path: str, value: Any,
                      what: str) -> None:
    if not _array(errors, path, value, what):
        return
    for index, item in enumerate(value):
        _identifier(errors, f"{path}/{index}", item)
    seen: set[str] = set()
    for item in value:
        if isinstance(item, str):
            if item in seen:
                errors.append(ValidationError(
                    path, f"{what} repeats {item!r}",
                    "unique entries; a repeated reference is either a copy-paste "
                    "slip or an attempt to charge the same thing twice",
                ))
                break
            seen.add(item)


def _string(errors: list[ValidationError], path: str, value: Any, *,
            min_length: Optional[int] = None,
            max_length: Optional[int] = None) -> None:
    if not isinstance(value, str):
        errors.append(ValidationError(path, f"value is {_describe(value)}", "a string"))
        return
    _length(errors, path, value, min_length, max_length)


def _length(errors: list[ValidationError], path: str, value: str,
            min_length: Optional[int], max_length: Optional[int]) -> None:
    if min_length is not None and len(value) < min_length:
        errors.append(ValidationError(
            path, f"string is {len(value)} characters long",
            f"at least {min_length} character(s)",
        ))
    if max_length is not None and len(value) > max_length:
        errors.append(ValidationError(
            path, f"string is {len(value)} characters long",
            f"at most {max_length} characters",
        ))


def _identifier(errors: list[ValidationError], path: str, value: Any) -> None:
    _string(errors, path, value, min_length=1, max_length=_IDENTIFIER_MAX)


def _nullable_identifier(errors: list[ValidationError], path: str, value: Any) -> None:
    if value is None:
        return
    _identifier(errors, path, value)


def _nullable_string(errors: list[ValidationError], path: str, value: Any) -> None:
    if value is None:
        return
    _string(errors, path, value, max_length=_STRING_MAX)


def _pattern(errors: list[ValidationError], path: str, value: Any,
             regex: re.Pattern[str], expected: str) -> None:
    if not isinstance(value, str):
        errors.append(ValidationError(path, f"value is {_describe(value)}", expected))
        return
    if regex.search(value) is None:
        errors.append(ValidationError(path, f"{value!r} does not match "
                                            f"{regex.pattern}", expected))


def _nullable_pattern(errors: list[ValidationError], path: str, value: Any,
                      regex: re.Pattern[str], expected: str) -> None:
    if value is None:
        return
    _pattern(errors, path, value, regex, expected)


def _integer(errors: list[ValidationError], path: str, value: Any, *,
             minimum: Optional[int] = None) -> None:
    if not _is_integer(value):
        errors.append(ValidationError(path, f"value is {_describe(value)}",
                                      "an integer"))
        return
    if minimum is not None and float(value) < minimum:
        errors.append(ValidationError(path, f"value is {value}",
                                      f"an integer greater than or equal to {minimum}"))


def _nullable_token_count(errors: list[ValidationError], path: str, value: Any) -> None:
    """Null means not reported, zero means reported as zero, and the difference
    is load-bearing, so this refuses anything that blurs the two."""
    if value is None:
        return
    if not _is_integer(value):
        errors.append(ValidationError(
            path, f"token count is {_describe(value)}",
            "an integer, or null for not reported; zero is a measurement and "
            "null is an admission, and they are not interchangeable",
        ))
        return
    if float(value) < 0:
        errors.append(ValidationError(path, f"token count is {value}",
                                      "an integer greater than or equal to 0"))


def _number(errors: list[ValidationError], path: str, value: Any, *,
            minimum: Optional[float] = None,
            exclusive_minimum: Optional[float] = None) -> None:
    if not _is_number(value):
        errors.append(ValidationError(path, f"value is {_describe(value)}", "a number"))
        return
    if minimum is not None and float(value) < minimum:
        errors.append(ValidationError(path, f"value is {value}",
                                      f"a number greater than or equal to {minimum}"))
    if exclusive_minimum is not None and float(value) <= exclusive_minimum:
        errors.append(ValidationError(path, f"value is {value}",
                                      f"a number greater than {exclusive_minimum}"))


def _nullable_number(errors: list[ValidationError], path: str, value: Any, *,
                     minimum: Optional[float] = None) -> None:
    if value is None:
        return
    _number(errors, path, value, minimum=minimum)


def _digest(errors: list[ValidationError], path: str, value: Any) -> None:
    if not _object(errors, path, value, "digest", required=("algorithm", "digest"),
                   allowed=("algorithm", "digest", "byte_length")):
        return
    _digest_fields(errors, path, value)


def _digest_fields(errors: list[ValidationError], path: str,
                   value: Mapping[str, Any]) -> None:
    if "algorithm" in value:
        _enum(errors, f"{path}/algorithm", value["algorithm"], ("sha256",))
    if "digest" in value:
        _pattern(errors, f"{path}/digest", value["digest"], _SHA256_RE,
                 "64 lowercase hex characters, a sha256 digest")
    if "byte_length" in value:
        _integer(errors, f"{path}/byte_length", value["byte_length"], minimum=0)


def _optional_digest(errors: list[ValidationError], path: str,
                     value: Mapping[str, Any], key: str) -> None:
    if key in value:
        _digest(errors, f"{path}/{key}", value[key])


def _label_map(errors: list[ValidationError], path: str, value: Any,
               what: str) -> None:
    """A map of low-cardinality labels. Payloads are refused here, not later.

    Nothing in these maps is copied into metric attributes, and refusing nested
    structures at the schema boundary is what keeps that promise cheap to keep.
    """
    if not isinstance(value, Mapping):
        errors.append(ValidationError(path, f"{what} is {_describe(value)}",
                                      "an object of scalar labels"))
        return
    for key, item in value.items():
        if not (item is None or isinstance(item, (str, bool)) or _is_number(item)):
            errors.append(ValidationError(
                _pointer(path, key), f"{what} entry is {_describe(item)}",
                "a string, number, boolean or null; these labels must stay "
                "low-cardinality and must never carry a payload",
            ))


def _ext(errors: list[ValidationError], path: str, value: Any) -> None:
    """The one open namespace. Only its object-ness is checked."""
    if not isinstance(value, Mapping):
        errors.append(ValidationError(path, f"ext is {_describe(value)}",
                                      "an object; ext is the reserved namespace for "
                                      "fields this protocol does not define"))


def _enum(errors: list[ValidationError], path: str, value: Any,
          allowed: Sequence[str]) -> None:
    if value not in allowed:
        errors.append(ValidationError(path, f"value is {value!r}",
                                      f"one of {', '.join(allowed)}"))


def _date_time(errors: list[ValidationError], path: str, value: Any) -> None:
    if not isinstance(value, str):
        errors.append(ValidationError(path, f"timestamp is {_describe(value)}",
                                      "an RFC 3339 date-time string"))
        return
    if not is_rfc3339_datetime(value):
        errors.append(ValidationError(
            path, f"timestamp {value!r} is not a valid RFC 3339 date-time",
            "an RFC 3339 date-time with an explicit offset, e.g. "
            "2026-07-27T10:00:00Z; this is the OBSERVATION time, and the gap "
            "between it and the decision is the whole point of a deferred grade",
        ))


def is_rfc3339_datetime(value: str) -> bool:
    """RFC 3339 date-time SHAPE only. An impossible date is accepted.

    "2026-13-45T99:00:00Z" passes here, and that is deliberate rather than an
    oversight. The schema asserts the pattern and nothing more, both language
    implementations assert exactly that, and a stricter Python check would mean
    Python and TypeScript rejecting different documents. Cross-language parity on
    the same corpus is worth more than catching a month 13 that no clock can
    produce. There is a test pinning this so it cannot be "fixed" into a break.

    Exposed rather than private because the schema-parity test registers it as
    the `date-time` format checker when the installed jsonschema has no native
    one, so that both validators enforce the same keyword.
    """
    return _RFC3339_RE.match(value) is not None


# --------------------------------------------------------------------------
# Type predicates and formatting
# --------------------------------------------------------------------------


def _is_boolean(value: Any) -> bool:
    return isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    """JSON Schema 2020-12 integer: bool is not one, and 1.0 is.

    The float case looks wrong and is not: since draft 2019-09 a number with a
    zero fractional part IS an integer, and matching that exactly is what keeps
    this validator and the JSON Schemas from disagreeing on a fixture.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and value.is_integer()


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _describe(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"the boolean {str(value).lower()}"
    if isinstance(value, str):
        return f"the string {value!r}"
    if isinstance(value, (int, float)):
        return f"the number {value}"
    if isinstance(value, list):
        return "an array"
    if isinstance(value, Mapping):
        return "an object"
    return f"a {type(value).__name__}"


def _pointer(path: str, key: str) -> str:
    """RFC 6901 escaping: ~ becomes ~0 and / becomes ~1."""
    return f"{path}/{key.replace('~', '~0').replace('/', '~1')}"


def format_errors(errors: Iterable[ValidationError]) -> str:
    """One error per line, for a CLI or a test failure message."""
    return "\n".join(str(error) for error in errors)
