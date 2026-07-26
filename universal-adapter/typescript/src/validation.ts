/**
 * Record validation.
 *
 * Hand written rather than driven by a JSON Schema library, for the same reason
 * conformance/check_conformance.py depends on nothing but the standard library:
 * the project's claim is that the contract is checkable with nothing installed.
 * The rules below are transcribed from universal-adapter/schemas, which remain
 * the contract; if the two ever disagree the schema wins.
 *
 * Two properties matter more than completeness here:
 *   - validate() NEVER throws on hostile input. It returns errors. A validator
 *     that throws turns a bad record into a crashed ingest.
 *   - every error is ACTIONABLE: where (a JSON Pointer), what was wrong, and
 *     what was expected instead.
 *
 * Unions are DISCRIMINATED: every arm pins `kind` to a distinct const and
 * `kind` is required, so no value can match two arms. Validation therefore
 * dispatches on `kind` first and reports one actionable error naming a missing
 * or unknown discriminator, instead of trying every arm and returning a pile of
 * oneOf failures that says nothing about what the author meant.
 *
 * On timestamps: outcome_record's observed_at carries both "format": "date-time"
 * and an RFC 3339 "pattern". Only the PATTERN is checked here. JSON Schema
 * treats format as an annotation unless a validator opts in, so asserting it
 * would make the cross-language verdict depend on validator configuration. The
 * pattern does not catch an impossible date such as month 13, and this
 * implementation deliberately does NOT parse the value to reject one, because a
 * stricter check on one side is a parity break in the other direction.
 */

import type { RecordKind } from "./models.ts";

export interface ValidationError {
  /** RFC 6901 JSON Pointer to the offending location, "" for the record root. */
  path: string;
  /** What is wrong, in terms of the value that was actually supplied. */
  message: string;
  /** What would have been accepted instead. */
  expected: string;
}

const TRACE_ID_RE = /^[0-9a-f]{32}$/;
const SPAN_ID_RE = /^[0-9a-f]{16}$/;
const SHA256_RE = /^[0-9a-f]{64}$/;
const RFC3339_RE =
  /^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$/;

const SCHEMA_VERSION = "1.0";

const VALUE_KINDS = ["inline", "digest", "artifact_reference", "absent"] as const;
const ABSENT_REASONS = ["redacted", "not_captured", "too_large", "unknown"] as const;
const EVIDENCE_KINDS = [
  "command_result",
  "file_state",
  "test_report",
  "structured_output",
  "otel_span",
  "log_reference",
  "harness_claim",
] as const;
const USAGE_SCOPES = ["model_invocation", "decision", "agent", "run"] as const;
const COST_PROVENANCES = [
  "provider_reported",
  "provider_token_estimate",
  "harness_token_estimate",
  "run_aggregate",
  "unknown",
] as const;
const AUTHORITIES = ["math", "reality", "ai_judge"] as const;
const EVALUATOR_KINDS = [
  "exact_equality",
  "json_equality",
  "command_exit_code",
  "file_digest",
  "json_schema",
  "callback",
  "outcome",
] as const;
/** Which evaluator kinds may carry math authority (manifest schema, allOf #1). */
const DETERMINISTIC_EVALUATOR_KINDS = EVALUATOR_KINDS.filter((k) => k !== "outcome");
const CALLBACK_DETERMINISM = ["deterministic", "model_assisted"] as const;

// --- primitives -------------------------------------------------------------

type Errors = ValidationError[];

function pointer(base: string, key: string | number): string {
  const token = String(key).replace(/~/g, "~0").replace(/\//g, "~1");
  return `${base}/${token}`;
}

function add(errors: Errors, path: string, message: string, expected: string): void {
  errors.push({ path, message, expected });
}

function describe(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "an array";
  const type = typeof value;
  if (type === "object") return "an object";
  if (type === "string") return `the string ${JSON.stringify(value)}`;
  if (type === "undefined") return "nothing (field absent)";
  return `${type} ${String(value)}`;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Enforce a CLOSED object: required keys present, no unknown keys. Returns the
 * object when the value is one at all, so callers can stop instead of piling
 * confusing follow-on errors onto a value of the wrong type.
 */
function closedObject(
  errors: Errors,
  value: unknown,
  path: string,
  allowed: readonly string[],
  required: readonly string[],
  what: string,
): Record<string, unknown> | undefined {
  if (!isPlainObject(value)) {
    add(errors, path, `${what} is ${describe(value)}`, "an object");
    return undefined;
  }
  for (const key of required) {
    if (!(key in value) || value[key] === undefined) {
      add(errors, path, `required field "${key}" is missing`, `"${key}" to be present`);
    }
  }
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) {
      add(
        errors,
        pointer(path, key),
        `unknown field "${key}"; objects in this protocol are closed and "ext" is the only place unknown fields are legal`,
        `one of: ${allowed.join(", ")}`,
      );
    }
  }
  return value;
}

function checkString(
  errors: Errors,
  value: unknown,
  path: string,
  opts: { nullable?: boolean; minLength?: number; maxLength?: number; pattern?: RegExp; patternLabel?: string },
): void {
  if (value === undefined) return;
  if (value === null) {
    if (!opts.nullable) add(errors, path, "value is null", "a string");
    return;
  }
  if (typeof value !== "string") {
    add(errors, path, `value is ${describe(value)}`, opts.nullable ? "a string or null" : "a string");
    return;
  }
  if (opts.minLength !== undefined && value.length < opts.minLength) {
    add(errors, path, `string has length ${value.length}`, `length >= ${opts.minLength}`);
  }
  if (opts.maxLength !== undefined && value.length > opts.maxLength) {
    add(errors, path, `string has length ${value.length}`, `length <= ${opts.maxLength}`);
  }
  if (opts.pattern && !opts.pattern.test(value)) {
    add(errors, path, `string ${JSON.stringify(value)} does not match the required form`, opts.patternLabel ?? String(opts.pattern));
  }
}

function checkIdentifier(errors: Errors, value: unknown, path: string, nullable = false): void {
  checkString(errors, value, path, { nullable, minLength: 1, maxLength: 512 });
}

function checkNullableString(errors: Errors, value: unknown, path: string): void {
  checkString(errors, value, path, { nullable: true, maxLength: 2048 });
}

function checkInteger(
  errors: Errors,
  value: unknown,
  path: string,
  opts: { nullable?: boolean; minimum?: number } = {},
): void {
  if (value === undefined) return;
  if (value === null) {
    if (!opts.nullable) add(errors, path, "value is null", "an integer");
    return;
  }
  // typeof true === "boolean" so booleans are already excluded; that matters,
  // because a JSON true silently counted as 1 is a known way to corrupt totals.
  if (typeof value !== "number" || !Number.isInteger(value)) {
    add(errors, path, `value is ${describe(value)}`, opts.nullable ? "an integer or null" : "an integer");
    return;
  }
  if (opts.minimum !== undefined && value < opts.minimum) {
    add(errors, path, `value is ${value}`, `an integer >= ${opts.minimum}`);
  }
}

function checkNumber(
  errors: Errors,
  value: unknown,
  path: string,
  opts: { nullable?: boolean; minimum?: number; exclusiveMinimum?: number } = {},
): void {
  if (value === undefined) return;
  if (value === null) {
    if (!opts.nullable) add(errors, path, "value is null", "a number");
    return;
  }
  if (typeof value !== "number" || !Number.isFinite(value)) {
    add(errors, path, `value is ${describe(value)}`, opts.nullable ? "a number or null" : "a number");
    return;
  }
  if (opts.minimum !== undefined && value < opts.minimum) {
    add(errors, path, `value is ${value}`, `a number >= ${opts.minimum}`);
  }
  if (opts.exclusiveMinimum !== undefined && value <= opts.exclusiveMinimum) {
    add(errors, path, `value is ${value}`, `a number > ${opts.exclusiveMinimum}`);
  }
}

function checkEnum(
  errors: Errors,
  value: unknown,
  path: string,
  allowed: readonly string[],
  what: string,
): boolean {
  if (typeof value !== "string" || !allowed.includes(value)) {
    add(errors, path, `${what} is ${describe(value)}`, `one of: ${allowed.join(", ")}`);
    return false;
  }
  return true;
}

function checkIdentifierArray(
  errors: Errors,
  value: unknown,
  path: string,
  what: string,
): void {
  if (value === undefined) return;
  if (!Array.isArray(value)) {
    add(errors, path, `${what} is ${describe(value)}`, "an array of identifiers");
    return;
  }
  const seen = new Set<string>();
  value.forEach((item, index) => {
    const itemPath = pointer(path, index);
    checkIdentifier(errors, item, itemPath);
    if (typeof item === "string") {
      if (seen.has(item)) {
        add(errors, itemPath, `duplicate entry ${JSON.stringify(item)}`, "unique items");
      }
      seen.add(item);
    }
  });
}

function checkExt(errors: Errors, value: unknown, path: string): void {
  if (value === undefined) return;
  if (!isPlainObject(value)) {
    add(errors, path, `ext is ${describe(value)}`, "an object");
  }
}

function checkSchemaVersion(errors: Errors, value: unknown, path: string): void {
  if (value !== SCHEMA_VERSION) {
    add(
      errors,
      path,
      `unknown schema_version ${describe(value)}; a consumer must reject a version it does not implement rather than guess`,
      `the string "${SCHEMA_VERSION}"`,
    );
  }
}

function checkDigestObject(errors: Errors, value: unknown, path: string): void {
  const obj = closedObject(errors, value, path, ["algorithm", "digest", "byte_length"], ["algorithm", "digest"], "digest");
  if (!obj) return;
  checkEnum(errors, obj["algorithm"], pointer(path, "algorithm"), ["sha256"], "algorithm");
  checkString(errors, obj["digest"], pointer(path, "digest"), {
    pattern: SHA256_RE,
    patternLabel: "64 lowercase hex characters",
  });
  checkInteger(errors, obj["byte_length"], pointer(path, "byte_length"), { minimum: 0 });
}

/** The tagged value union (D2). */
function checkValue(errors: Errors, value: unknown, path: string): void {
  if (!isPlainObject(value)) {
    add(errors, path, `value is ${describe(value)}`, "a tagged value object with a \"kind\" field");
    return;
  }
  if (!checkEnum(errors, value["kind"], pointer(path, "kind"), VALUE_KINDS, "kind")) return;
  switch (value["kind"]) {
    case "inline": {
      closedObject(errors, value, path, ["kind", "value"], ["kind", "value"], "inline value");
      return;
    }
    case "digest": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["kind", "algorithm", "digest", "byte_length"],
        ["kind", "algorithm", "digest"],
        "digest value",
      );
      if (!obj) return;
      checkEnum(errors, obj["algorithm"], pointer(path, "algorithm"), ["sha256"], "algorithm");
      checkString(errors, obj["digest"], pointer(path, "digest"), {
        pattern: SHA256_RE,
        patternLabel: "64 lowercase hex characters",
      });
      checkInteger(errors, obj["byte_length"], pointer(path, "byte_length"), { minimum: 0 });
      return;
    }
    case "artifact_reference": {
      const obj = closedObject(errors, value, path, ["kind", "value", "digest"], ["kind", "value"], "artifact reference");
      if (!obj) return;
      checkString(errors, obj["value"], pointer(path, "value"), { minLength: 1, maxLength: 2048 });
      if (obj["digest"] !== undefined) checkDigestObject(errors, obj["digest"], pointer(path, "digest"));
      return;
    }
    case "absent": {
      const obj = closedObject(errors, value, path, ["kind", "reason"], ["kind", "reason"], "absent value");
      if (!obj) return;
      checkEnum(errors, obj["reason"], pointer(path, "reason"), ABSENT_REASONS, "reason");
      return;
    }
    default:
      return;
  }
}

function checkScalarMap(errors: Errors, value: unknown, path: string, what: string): void {
  if (value === undefined) return;
  if (!isPlainObject(value)) {
    add(errors, path, `${what} is ${describe(value)}`, "an object of scalar values");
    return;
  }
  for (const [key, item] of Object.entries(value)) {
    const type = typeof item;
    if (item !== null && type !== "string" && type !== "number" && type !== "boolean") {
      add(
        errors,
        pointer(path, key),
        `value is ${describe(item)}; this object must not carry payloads`,
        "a string, number, boolean or null",
      );
    }
  }
}

// --- evidence ---------------------------------------------------------------

function checkEvidenceItem(errors: Errors, value: unknown, path: string): void {
  if (!isPlainObject(value)) {
    add(errors, path, `evidence item is ${describe(value)}`, "an object");
    return;
  }
  checkIdentifier(errors, value["evidence_id"], pointer(path, "evidence_id"));
  if (!("evidence_id" in value)) {
    add(errors, path, 'required field "evidence_id" is missing', '"evidence_id" to be present');
  }
  if (!checkEnum(errors, value["kind"], pointer(path, "kind"), EVIDENCE_KINDS, "evidence kind")) return;

  switch (value["kind"]) {
    case "command_result": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["evidence_id", "kind", "command_name", "exit_code", "duration_ms", "artifact_digest"],
        ["evidence_id", "kind", "command_name", "exit_code"],
        "command_result evidence",
      );
      if (!obj) return;
      checkIdentifier(errors, obj["command_name"], pointer(path, "command_name"));
      checkInteger(errors, obj["exit_code"], pointer(path, "exit_code"));
      checkInteger(errors, obj["duration_ms"], pointer(path, "duration_ms"), { minimum: 0 });
      if (obj["artifact_digest"] !== undefined) {
        checkDigestObject(errors, obj["artifact_digest"], pointer(path, "artifact_digest"));
      }
      return;
    }
    case "file_state": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["evidence_id", "kind", "path", "artifact_digest"],
        ["evidence_id", "kind", "path", "artifact_digest"],
        "file_state evidence",
      );
      if (!obj) return;
      checkString(errors, obj["path"], pointer(path, "path"), { minLength: 1, maxLength: 2048 });
      if (obj["artifact_digest"] !== undefined) {
        checkDigestObject(errors, obj["artifact_digest"], pointer(path, "artifact_digest"));
      }
      return;
    }
    case "test_report": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["evidence_id", "kind", "passed", "failed", "skipped", "artifact_digest"],
        ["evidence_id", "kind", "passed", "failed"],
        "test_report evidence",
      );
      if (!obj) return;
      checkInteger(errors, obj["passed"], pointer(path, "passed"), { minimum: 0 });
      checkInteger(errors, obj["failed"], pointer(path, "failed"), { minimum: 0 });
      checkInteger(errors, obj["skipped"], pointer(path, "skipped"), { minimum: 0 });
      if (obj["artifact_digest"] !== undefined) {
        checkDigestObject(errors, obj["artifact_digest"], pointer(path, "artifact_digest"));
      }
      return;
    }
    case "structured_output": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["evidence_id", "kind", "output"],
        ["evidence_id", "kind", "output"],
        "structured_output evidence",
      );
      if (!obj) return;
      if (obj["output"] !== undefined) checkValue(errors, obj["output"], pointer(path, "output"));
      return;
    }
    case "otel_span": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["evidence_id", "kind", "trace_id", "span_id"],
        ["evidence_id", "kind", "trace_id", "span_id"],
        "otel_span evidence",
      );
      if (!obj) return;
      checkString(errors, obj["trace_id"], pointer(path, "trace_id"), {
        pattern: TRACE_ID_RE,
        patternLabel: "32 lowercase hex characters (W3C trace id)",
      });
      checkString(errors, obj["span_id"], pointer(path, "span_id"), {
        pattern: SPAN_ID_RE,
        patternLabel: "16 lowercase hex characters (W3C span id)",
      });
      return;
    }
    case "log_reference": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["evidence_id", "kind", "ref", "artifact_digest"],
        ["evidence_id", "kind", "ref"],
        "log_reference evidence",
      );
      if (!obj) return;
      checkString(errors, obj["ref"], pointer(path, "ref"), { minLength: 1, maxLength: 2048 });
      if (obj["artifact_digest"] !== undefined) {
        checkDigestObject(errors, obj["artifact_digest"], pointer(path, "artifact_digest"));
      }
      return;
    }
    case "harness_claim": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["evidence_id", "kind", "claim"],
        ["evidence_id", "kind", "claim"],
        "harness_claim evidence",
      );
      if (!obj) return;
      if (obj["claim"] !== undefined) {
        if (!isPlainObject(obj["claim"])) {
          add(errors, pointer(path, "claim"), `claim is ${describe(obj["claim"])}`, "an object of scalar values");
        } else {
          checkScalarMap(errors, obj["claim"], pointer(path, "claim"), "claim");
        }
      }
      return;
    }
    default:
      return;
  }
}

// --- records ----------------------------------------------------------------

function validateBundle(value: unknown): ValidationError[] {
  const errors: Errors = [];
  const root = closedObject(
    errors,
    value,
    "",
    ["schema_version", "decision", "subject", "correlation", "evidence", "usage_refs", "metadata", "ext"],
    ["schema_version", "decision", "subject", "evidence"],
    "DecisionEvidenceBundle",
  );
  if (!root) return errors;
  checkSchemaVersion(errors, root["schema_version"], "/schema_version");

  if (root["decision"] !== undefined) {
    const decision = closedObject(
      errors,
      root["decision"],
      "/decision",
      ["decision_id", "decision_type", "evaluation_name", "chosen"],
      ["decision_type", "evaluation_name", "chosen"],
      "decision",
    );
    if (decision) {
      if (decision["decision_id"] !== undefined) {
        checkIdentifier(errors, decision["decision_id"], "/decision/decision_id");
      }
      checkIdentifier(errors, decision["decision_type"], "/decision/decision_type");
      checkIdentifier(errors, decision["evaluation_name"], "/decision/evaluation_name");
      if (decision["chosen"] !== undefined) checkValue(errors, decision["chosen"], "/decision/chosen");
    }
  }

  if (root["subject"] !== undefined) {
    const subject = closedObject(
      errors,
      root["subject"],
      "/subject",
      ["harness", "harness_version", "run_id", "session_id", "agent_id", "parent_agent_id", "model"],
      ["harness", "run_id"],
      "subject",
    );
    if (subject) {
      checkIdentifier(errors, subject["harness"], "/subject/harness");
      checkNullableString(errors, subject["harness_version"], "/subject/harness_version");
      checkIdentifier(errors, subject["run_id"], "/subject/run_id");
      checkIdentifier(errors, subject["session_id"], "/subject/session_id", true);
      checkIdentifier(errors, subject["agent_id"], "/subject/agent_id", true);
      checkIdentifier(errors, subject["parent_agent_id"], "/subject/parent_agent_id", true);
      checkNullableString(errors, subject["model"], "/subject/model");
    }
  }

  if (root["correlation"] !== undefined) {
    const correlation = closedObject(
      errors,
      root["correlation"],
      "/correlation",
      ["provider_response_id", "trace_id", "span_id", "task_id"],
      [],
      "correlation",
    );
    if (correlation) {
      checkNullableString(errors, correlation["provider_response_id"], "/correlation/provider_response_id");
      checkString(errors, correlation["trace_id"], "/correlation/trace_id", {
        nullable: true,
        pattern: TRACE_ID_RE,
        patternLabel: "32 lowercase hex characters (W3C trace id) or null",
      });
      checkString(errors, correlation["span_id"], "/correlation/span_id", {
        nullable: true,
        pattern: SPAN_ID_RE,
        patternLabel: "16 lowercase hex characters (W3C span id) or null",
      });
      checkIdentifier(errors, correlation["task_id"], "/correlation/task_id", true);
    }
  }

  if (root["evidence"] !== undefined) {
    if (!Array.isArray(root["evidence"])) {
      add(errors, "/evidence", `evidence is ${describe(root["evidence"])}`, "an array (an empty array is legal)");
    } else {
      root["evidence"].forEach((item, index) => checkEvidenceItem(errors, item, pointer("/evidence", index)));
    }
  }

  checkIdentifierArray(errors, root["usage_refs"], "/usage_refs", "usage_refs");
  checkScalarMap(errors, root["metadata"], "/metadata", "metadata");
  checkExt(errors, root["ext"], "/ext");
  return errors;
}

function validateUsage(value: unknown): ValidationError[] {
  const errors: Errors = [];
  const root = closedObject(
    errors,
    value,
    "",
    [
      "schema_version",
      "usage_id",
      "scope",
      "run_id",
      "agent_id",
      "parent_agent_id",
      "contains_usage_ids",
      "decision_ids",
      "provider_response_id",
      "model",
      "input_tokens",
      "output_tokens",
      "cached_input_tokens",
      "provider_cost_usd",
      "cost_provenance",
      "pricing_table_id",
      "ext",
    ],
    ["schema_version", "usage_id", "scope", "run_id", "cost_provenance"],
    "UsageRecord",
  );
  if (!root) return errors;
  checkSchemaVersion(errors, root["schema_version"], "/schema_version");
  checkIdentifier(errors, root["usage_id"], "/usage_id");
  const scopeOk = root["scope"] === undefined
    ? false
    : checkEnum(errors, root["scope"], "/scope", USAGE_SCOPES, "scope");
  checkIdentifier(errors, root["run_id"], "/run_id");
  checkIdentifier(errors, root["agent_id"], "/agent_id", true);
  checkIdentifier(errors, root["parent_agent_id"], "/parent_agent_id", true);
  checkIdentifierArray(errors, root["contains_usage_ids"], "/contains_usage_ids", "contains_usage_ids");
  checkIdentifierArray(errors, root["decision_ids"], "/decision_ids", "decision_ids");
  checkNullableString(errors, root["provider_response_id"], "/provider_response_id");
  checkNullableString(errors, root["model"], "/model");
  checkInteger(errors, root["input_tokens"], "/input_tokens", { nullable: true, minimum: 0 });
  checkInteger(errors, root["output_tokens"], "/output_tokens", { nullable: true, minimum: 0 });
  checkInteger(errors, root["cached_input_tokens"], "/cached_input_tokens", { nullable: true, minimum: 0 });
  checkNumber(errors, root["provider_cost_usd"], "/provider_cost_usd", { nullable: true, minimum: 0 });
  const provenanceOk =
    root["cost_provenance"] === undefined
      ? false
      : checkEnum(errors, root["cost_provenance"], "/cost_provenance", COST_PROVENANCES, "cost_provenance");
  checkNullableString(errors, root["pricing_table_id"], "/pricing_table_id");
  checkExt(errors, root["ext"], "/ext");

  if (!provenanceOk) return errors;
  const provenance = root["cost_provenance"] as string;

  // A token-estimated figure without its rate card is untraceable, which is the
  // precise dishonesty pricing_table_id exists to prevent.
  if (provenance === "provider_token_estimate" || provenance === "harness_token_estimate") {
    const table = root["pricing_table_id"];
    if (typeof table !== "string" || table.length === 0) {
      add(
        errors,
        "/pricing_table_id",
        `cost_provenance is "${provenance}" but pricing_table_id is ${describe(table)}`,
        "a non-empty pricing table id, mandatory for token-estimated cost",
      );
    }
  }
  if (provenance === "provider_reported") {
    const cost = root["provider_cost_usd"];
    if (typeof cost !== "number" || !Number.isFinite(cost) || cost < 0) {
      add(
        errors,
        "/provider_cost_usd",
        `cost_provenance is "provider_reported" but provider_cost_usd is ${describe(cost)}`,
        "a number >= 0",
      );
    }
  }
  if (provenance === "run_aggregate" && scopeOk && root["scope"] !== "run") {
    add(
      errors,
      "/scope",
      `cost_provenance is "run_aggregate" but scope is ${describe(root["scope"])}; a run aggregate covers a whole run and cannot also be scoped to one call or agent`,
      'scope "run"',
    );
  }
  return errors;
}

function checkEvaluator(errors: Errors, value: unknown, path: string): void {
  if (!isPlainObject(value)) {
    add(errors, path, `evaluator is ${describe(value)}`, "an object with a \"kind\" field");
    return;
  }
  if (!checkEnum(errors, value["kind"], pointer(path, "kind"), EVALUATOR_KINDS, "evaluator kind")) return;
  switch (value["kind"]) {
    case "exact_equality": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["kind", "expected", "case_sensitive", "trim_whitespace"],
        ["kind", "expected"],
        "exact_equality evaluator",
      );
      if (!obj) return;
      for (const key of ["case_sensitive", "trim_whitespace"]) {
        if (obj[key] !== undefined && typeof obj[key] !== "boolean") {
          add(errors, pointer(path, key), `value is ${describe(obj[key])}`, "a boolean");
        }
      }
      return;
    }
    case "json_equality": {
      closedObject(errors, value, path, ["kind", "expected"], ["kind", "expected"], "json_equality evaluator");
      return;
    }
    case "command_exit_code": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["kind", "command", "expected_exit_code", "timeout_seconds", "working_directory"],
        ["kind", "command", "expected_exit_code"],
        "command_exit_code evaluator",
      );
      if (!obj) return;
      const command = obj["command"];
      if (command !== undefined) {
        if (!Array.isArray(command) || command.length < 1) {
          add(errors, pointer(path, "command"), `command is ${describe(command)}`, "a non-empty array of argv strings");
        } else {
          command.forEach((arg, index) => {
            if (typeof arg !== "string") {
              add(errors, pointer(pointer(path, "command"), index), `argv element is ${describe(arg)}`, "a string");
            }
          });
        }
      }
      checkInteger(errors, obj["expected_exit_code"], pointer(path, "expected_exit_code"));
      checkNumber(errors, obj["timeout_seconds"], pointer(path, "timeout_seconds"), { exclusiveMinimum: 0 });
      checkString(errors, obj["working_directory"], pointer(path, "working_directory"), { maxLength: 2048 });
      return;
    }
    case "file_digest": {
      const obj = closedObject(errors, value, path, ["kind", "path", "expected"], ["kind", "path", "expected"], "file_digest evaluator");
      if (!obj) return;
      checkString(errors, obj["path"], pointer(path, "path"), { minLength: 1, maxLength: 2048 });
      if (obj["expected"] !== undefined) checkDigestObject(errors, obj["expected"], pointer(path, "expected"));
      return;
    }
    case "json_schema": {
      const obj = closedObject(errors, value, path, ["kind", "schema"], ["kind", "schema"], "json_schema evaluator");
      if (!obj) return;
      if (obj["schema"] !== undefined && !isPlainObject(obj["schema"])) {
        add(errors, pointer(path, "schema"), `schema is ${describe(obj["schema"])}`, "an object");
      }
      return;
    }
    case "callback": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["kind", "name", "determinism", "options"],
        ["kind", "name", "determinism"],
        "callback evaluator",
      );
      if (!obj) return;
      checkIdentifier(errors, obj["name"], pointer(path, "name"));
      // Required with no default: a defaulted determinism is a guess about the
      // one property that decides whether a verdict can reach the headline.
      if (obj["determinism"] !== undefined) {
        checkEnum(errors, obj["determinism"], pointer(path, "determinism"), CALLBACK_DETERMINISM, "determinism");
      }
      checkScalarMap(errors, obj["options"], pointer(path, "options"), "options");
      return;
    }
    case "outcome": {
      const obj = closedObject(
        errors,
        value,
        path,
        ["kind", "outcome_type", "observation_window_seconds"],
        ["kind", "outcome_type"],
        "outcome evaluator",
      );
      if (!obj) return;
      checkIdentifier(errors, obj["outcome_type"], pointer(path, "outcome_type"));
      checkNumber(errors, obj["observation_window_seconds"], pointer(path, "observation_window_seconds"), {
        exclusiveMinimum: 0,
      });
      return;
    }
    default:
      return;
  }
}

function validateManifest(value: unknown): ValidationError[] {
  const errors: Errors = [];
  const root = closedObject(
    errors,
    value,
    "",
    ["schema_version", "task_id", "decision_type", "evaluation_name", "authority", "evaluator", "description", "ext"],
    ["schema_version", "task_id", "decision_type", "evaluation_name", "authority", "evaluator"],
    "EvaluationManifest",
  );
  if (!root) return errors;
  checkSchemaVersion(errors, root["schema_version"], "/schema_version");
  checkIdentifier(errors, root["task_id"], "/task_id");
  checkIdentifier(errors, root["decision_type"], "/decision_type");
  checkIdentifier(errors, root["evaluation_name"], "/evaluation_name");
  const authorityOk =
    root["authority"] === undefined
      ? false
      : checkEnum(errors, root["authority"], "/authority", AUTHORITIES, "authority");
  if (root["evaluator"] !== undefined) checkEvaluator(errors, root["evaluator"], "/evaluator");
  checkString(errors, root["description"], "/description", { maxLength: 2048 });
  checkExt(errors, root["ext"], "/ext");

  if (!authorityOk || !isPlainObject(root["evaluator"])) return errors;
  const evaluatorKind = (root["evaluator"] as Record<string, unknown>)["kind"];
  if (typeof evaluatorKind !== "string" || !(EVALUATOR_KINDS as readonly string[]).includes(evaluatorKind)) return errors;

  // The protocol's most important rule, enforced structurally: an opinion
  // cannot be relabelled as arithmetic by editing one field of a manifest.
  if (root["authority"] === "math" && !(DETERMINISTIC_EVALUATOR_KINDS as readonly string[]).includes(evaluatorKind)) {
    add(
      errors,
      "/evaluator/kind",
      `authority is "math" but the evaluator kind is "${evaluatorKind}", which is not deterministic`,
      `one of: ${DETERMINISTIC_EVALUATOR_KINDS.join(", ")}`,
    );
  }
  // callback is the one arm whose determinism is invisible in its shape. Under
  // math authority it must have said so out loud, so a model-assisted checker
  // cannot reach the headline metric by omission. The registry enforces the
  // same rule a second time, against the code rather than the declaration.
  if (root["authority"] === "math" && evaluatorKind === "callback") {
    const determinism = (root["evaluator"] as Record<string, unknown>)["determinism"];
    if (determinism !== "deterministic") {
      add(
        errors,
        "/evaluator/determinism",
        `authority is "math" but the callback declares determinism ${describe(determinism)}; a checker that may ask a model for its verdict cannot carry math authority`,
        'determinism "deterministic"',
      );
    }
  }
  if (root["authority"] === "reality" && evaluatorKind !== "outcome") {
    add(
      errors,
      "/evaluator/kind",
      `authority is "reality" but the evaluator kind is "${evaluatorKind}"; reality authority is conferred by an outcome that arrives later, not by running a checker at decision time`,
      'the evaluator kind "outcome"',
    );
  }
  return errors;
}

function validateOutcome(value: unknown): ValidationError[] {
  const errors: Errors = [];
  const root = closedObject(
    errors,
    value,
    "",
    [
      "schema_version",
      "outcome_id",
      "decision_id",
      "provider_response_id",
      "outcome_type",
      "correct",
      "observed_at",
      "evidence_ref",
      "explanation",
      "ext",
    ],
    ["schema_version", "outcome_id", "decision_id", "outcome_type", "correct", "observed_at"],
    "OutcomeRecord",
  );
  if (!root) return errors;
  checkSchemaVersion(errors, root["schema_version"], "/schema_version");
  checkIdentifier(errors, root["outcome_id"], "/outcome_id");
  checkIdentifier(errors, root["decision_id"], "/decision_id");
  checkNullableString(errors, root["provider_response_id"], "/provider_response_id");
  checkIdentifier(errors, root["outcome_type"], "/outcome_type");

  // Strictly boolean. A truthy 1 quietly becoming a passing grade is a known
  // way to corrupt a headline metric, so it is rejected rather than coerced.
  if (root["correct"] !== undefined && typeof root["correct"] !== "boolean") {
    add(
      errors,
      "/correct",
      `correct is ${describe(root["correct"])}; a truthy value must not be coerced into a passing grade`,
      "true or false",
    );
  }

  const observedAt = root["observed_at"];
  if (observedAt !== undefined) {
    if (typeof observedAt !== "string") {
      add(errors, "/observed_at", `observed_at is ${describe(observedAt)}`, "an RFC 3339 date-time string");
    } else if (!RFC3339_RE.test(observedAt)) {
      add(
        errors,
        "/observed_at",
        `observed_at ${JSON.stringify(observedAt)} does not match the RFC 3339 pattern`,
        'an RFC 3339 date-time, e.g. "2026-07-27T10:00:00Z"',
      );
    }
  }

  checkNullableString(errors, root["evidence_ref"], "/evidence_ref");
  checkString(errors, root["explanation"], "/explanation", { nullable: true, maxLength: 2048 });
  checkExt(errors, root["ext"], "/ext");
  return errors;
}

// --- public entry point -----------------------------------------------------

const VALIDATORS: Record<RecordKind, (value: unknown) => ValidationError[]> = {
  decision_evidence_bundle: validateBundle,
  usage_record: validateUsage,
  evaluation_manifest: validateManifest,
  outcome_record: validateOutcome,
};

/**
 * Accept the spellings a fixture corpus might reasonably use for a record kind,
 * so an external parity runner does not have to guess ours.
 */
export function normalizeRecordKind(name: string): RecordKind | undefined {
  const key = name.trim().toLowerCase().replace(/[-\s.]/g, "_").replace(/_schema_json$/, "").replace(/_json$/, "");
  const aliases: Record<string, RecordKind> = {
    decision_evidence_bundle: "decision_evidence_bundle",
    decisionevidencebundle: "decision_evidence_bundle",
    bundle: "decision_evidence_bundle",
    decision: "decision_evidence_bundle",
    usage_record: "usage_record",
    usagerecord: "usage_record",
    usage: "usage_record",
    evaluation_manifest: "evaluation_manifest",
    evaluationmanifest: "evaluation_manifest",
    manifest: "evaluation_manifest",
    outcome_record: "outcome_record",
    outcomerecord: "outcome_record",
    outcome: "outcome_record",
  };
  return aliases[key];
}

/**
 * Validate one record. Returns an empty array when the record conforms, and
 * never throws: hostile input is a data problem, not a control-flow event.
 *
 * This is the stable signature an external parity runner drives.
 */
export function validate(kind: RecordKind | string, value: unknown): ValidationError[] {
  const resolved = typeof kind === "string" ? normalizeRecordKind(kind) : undefined;
  if (!resolved) {
    return [
      {
        path: "",
        message: `unknown record kind ${JSON.stringify(kind)}`,
        expected: `one of: ${Object.keys(VALIDATORS).join(", ")}`,
      },
    ];
  }
  try {
    return VALIDATORS[resolved](value);
  } catch (error) {
    // Belt and braces. A validator bug must still surface as a finding rather
    // than as an exception crossing an ingest boundary.
    return [
      {
        path: "",
        message: `validator failed unexpectedly: ${String(error)}`,
        expected: "a validatable record",
      },
    ];
  }
}

export function isValid(kind: RecordKind | string, value: unknown): boolean {
  return validate(kind, value).length === 0;
}

/** Render errors as one actionable line each, for logs and test failures. */
export function formatErrors(errors: readonly ValidationError[]): string {
  return errors.map((e) => `${e.path || "<root>"}: ${e.message} (expected ${e.expected})`).join("\n");
}
