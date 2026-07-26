/**
 * Independent evaluation: the layer that decides whether a decision was correct
 * and, crucially, on whose authority.
 *
 * Two rules shape everything here.
 *
 * 1. A harness claim can never conclude a grade. This is enforced by the TYPE
 *    SYSTEM: every deterministic evaluator takes MathAdmissibleEvidence, which
 *    is Exclude<EvidenceItem, HarnessClaimEvidence>. Code that tries to read a
 *    harness claim to decide correctness does not compile. A runtime filter
 *    would be a rule someone can later delete by accident; a type is not.
 *
 * 2. Collection and evaluation are separate concerns (design decision D5). This
 *    module runs no processes and reads no files. A command's exit status and a
 *    file's digest arrive as EVIDENCE produced by a collector, or through an
 *    explicitly injected resolver. That keeps the evaluator deterministic and
 *    keeps the library from turning into a workflow engine.
 *
 * The manifest still declares the command and the expected digest, so the
 * process being graded cannot choose the test that grades it: evidence supplies
 * the observation, the manifest supplies the expectation.
 *
 * The one evaluator whose determinism is not visible in its shape is `callback`,
 * because it is resolved from an application registry that could wrap a model.
 * It is therefore checked twice: the manifest must declare determinism, and the
 * registry must declare it again at registration time. Where the two disagree
 * the registry wins, and a math authority the running code cannot justify is
 * downgraded to ai_judge rather than honoured.
 */

import { canonicalize } from "./canonical.ts";
import type {
  CallbackDeterminism,
  CommandExitCodeEvaluator,
  DecisionEvidenceBundle,
  EvaluationManifest,
  EvaluatorKind,
  FileDigestEvaluator,
  GradeAuthority,
  MathAdmissibleEvidence,
  MetadataValue,
  OutcomeRecord,
  ProtocolValue,
} from "./models.ts";
import { mathAdmissibleEvidence } from "./models.ts";

/** The closed reason enum from docs/conventions.md section 12.1. */
export type ReasonCode = "match" | "mismatch" | "no_ground_truth" | "empty_answer" | "ambiguous";

export interface GradedEvaluation {
  graded: true;
  correct: boolean;
  authority: GradeAuthority;
  reason: Extract<ReasonCode, "match" | "mismatch">;
  evaluatorKind: EvaluatorKind;
  /** Which evidence items (or outcome id) the verdict actually rests on. */
  evidenceIds: string[];
  explanation?: string;
  /**
   * Set when the manifest asked for a stronger authority than the running code
   * could justify, e.g. a manifest claiming a deterministic callback that the
   * registry knows to be model assisted. The grade still exists; it just lands
   * as ai_judge, and the downgrade is on the record rather than in a log line.
   */
  authorityDowngradedFrom?: GradeAuthority;
}

export interface UngradedEvaluation {
  graded: false;
  /** Why no authoritative grade could be produced. */
  reason: Exclude<ReasonCode, "match" | "mismatch">;
  evaluatorKind: EvaluatorKind | null;
  detail: string;
}

export type EvaluationResult = GradedEvaluation | UngradedEvaluation;

export interface CheckerResult {
  passed: boolean;
  /** Optional override; defaults to match/mismatch from `passed`. */
  reason?: ReasonCode;
  explanation?: string;
}

export interface CheckerContext {
  chosen: ProtocolValue;
  evidence: readonly MathAdmissibleEvidence[];
  options: Record<string, MetadataValue>;
}

/**
 * An application-provided checker, resolved BY NAME from a registry the
 * application owns. The manifest carries a lookup key, never an import path, so
 * a manifest can never cause arbitrary code to load.
 */
export type Checker = (context: CheckerContext) => CheckerResult;

export interface RegisteredChecker {
  checker: Checker;
  determinism: CallbackDeterminism;
}

/**
 * The application's checker registry, and the second enforcement point for the
 * determinism rule.
 *
 * The manifest declares whether a callback is deterministic, but a manifest is
 * a claim about code it does not contain. The registry sits next to the actual
 * function, so registration REQUIRES the declaration (no default), and when the
 * two disagree the registry wins: it is closer to what will really run.
 */
export class CheckerRegistry {
  readonly #entries = new Map<string, RegisteredChecker>();

  register(name: string, checker: Checker, determinism: CallbackDeterminism): this {
    if (determinism !== "deterministic" && determinism !== "model_assisted") {
      throw new TypeError(
        `checker ${JSON.stringify(name)} must declare determinism as "deterministic" or "model_assisted"`,
      );
    }
    this.#entries.set(name, { checker, determinism });
    return this;
  }

  get(name: string): RegisteredChecker | undefined {
    return this.#entries.get(name);
  }

  has(name: string): boolean {
    return this.#entries.has(name);
  }
}

export interface EvaluationInput {
  bundle: DecisionEvidenceBundle;
  manifest: EvaluationManifest;
  /** Outcomes known so far; only the `outcome` evaluator consults them. */
  outcomes?: readonly OutcomeRecord[];
  /** Resolved decision id, when the caller already computed it. */
  decisionId?: string;
  checkers?: CheckerRegistry;
  /**
   * Optional independent execution of the manifest's command. When supplied its
   * exit code outranks any command_result evidence, because it was run by the
   * grader rather than reported by the graded process. Injected, never spawned
   * here, so this module stays free of side effects.
   */
  runCommand?: (evaluator: CommandExitCodeEvaluator) => number | undefined;
  /** Optional independent read of a file digest, same reasoning as runCommand. */
  resolveFileDigest?: (evaluator: FileDigestEvaluator) => string | undefined;
}

function ungraded(
  reason: UngradedEvaluation["reason"],
  evaluatorKind: EvaluatorKind | null,
  detail: string,
): UngradedEvaluation {
  return { graded: false, reason, evaluatorKind, detail };
}

function graded(
  correct: boolean,
  authority: GradeAuthority,
  evaluatorKind: EvaluatorKind,
  evidenceIds: string[],
  explanation?: string,
): GradedEvaluation {
  return {
    graded: true,
    correct,
    authority,
    reason: correct ? "match" : "mismatch",
    evaluatorKind,
    evidenceIds,
    ...(explanation === undefined ? {} : { explanation }),
  };
}

/**
 * Pull the inline payload out of a tagged value, or explain why there is none.
 * A digest or artifact reference is not a failure of the harness; it just means
 * the value cannot be compared here, and saying so beats guessing.
 */
type InlineExtraction =
  | { ok: true; value: unknown }
  | { ok: false; reason: UngradedEvaluation["reason"]; detail: string };

function inlinePayload(chosen: ProtocolValue): InlineExtraction {
  switch (chosen.kind) {
    case "inline":
      if (chosen.value === null || chosen.value === "") {
        return { ok: false, reason: "empty_answer", detail: "the chosen value is inline but empty" };
      }
      return { ok: true, value: chosen.value };
    case "absent":
      return {
        ok: false,
        reason: "ambiguous",
        detail: `the chosen value is absent (reason: ${chosen.reason}), so it cannot be compared`,
      };
    case "digest":
      return {
        ok: false,
        reason: "ambiguous",
        detail: "the chosen value is carried by digest; a value evaluator needs the value itself",
      };
    case "artifact_reference":
      return {
        ok: false,
        reason: "ambiguous",
        detail: "the chosen value is an artifact reference; a value evaluator needs the value itself",
      };
  }
}

function normalizeForExactEquality(
  value: unknown,
  caseSensitive: boolean,
  trimWhitespace: boolean,
): unknown {
  if (typeof value !== "string") return value;
  let out = trimWhitespace ? value.trim() : value;
  if (!caseSensitive) out = out.toLowerCase();
  return out;
}

/** Structural equality: object key order irrelevant, array order significant. */
export function jsonEqual(left: unknown, right: unknown): boolean {
  return canonicalize(left) === canonicalize(right);
}

// --- a deliberately small JSON Schema subset --------------------------------

/**
 * Supported keywords: type, enum, const, required, properties,
 * additionalProperties (boolean form), items, minItems, maxItems, minimum,
 * maximum, minLength, maxLength, pattern.
 *
 * Anything else is IGNORED rather than treated as a failure. This is a grading
 * protocol, not a schema engine, and a half-implemented keyword that silently
 * fails a correct answer is worse than a keyword that is honestly not supported.
 * The Python side must restrict itself to the same subset for parity.
 */
export function validateAgainstSubsetSchema(value: unknown, schema: Record<string, unknown>): string[] {
  const failures: string[] = [];
  const check = (val: unknown, sch: Record<string, unknown>, path: string): void => {
    const type = sch["type"];
    if (typeof type === "string" && !matchesJsonType(val, type)) {
      failures.push(`${path || "value"} is not of type ${type}`);
      return;
    }
    if (Array.isArray(type) && !type.some((t) => typeof t === "string" && matchesJsonType(val, t))) {
      failures.push(`${path || "value"} is not one of the types ${type.join(", ")}`);
      return;
    }
    if (Array.isArray(sch["enum"]) && !sch["enum"].some((option) => jsonEqual(option, val))) {
      failures.push(`${path || "value"} is not one of the permitted enum values`);
    }
    if ("const" in sch && !jsonEqual(sch["const"], val)) {
      failures.push(`${path || "value"} does not equal the required const`);
    }
    if (typeof val === "number") {
      if (typeof sch["minimum"] === "number" && val < sch["minimum"]) {
        failures.push(`${path || "value"} is below minimum ${sch["minimum"]}`);
      }
      if (typeof sch["maximum"] === "number" && val > sch["maximum"]) {
        failures.push(`${path || "value"} is above maximum ${sch["maximum"]}`);
      }
    }
    if (typeof val === "string") {
      if (typeof sch["minLength"] === "number" && val.length < sch["minLength"]) {
        failures.push(`${path || "value"} is shorter than minLength ${sch["minLength"]}`);
      }
      if (typeof sch["maxLength"] === "number" && val.length > sch["maxLength"]) {
        failures.push(`${path || "value"} is longer than maxLength ${sch["maxLength"]}`);
      }
      if (typeof sch["pattern"] === "string" && !new RegExp(sch["pattern"]).test(val)) {
        failures.push(`${path || "value"} does not match pattern ${sch["pattern"]}`);
      }
    }
    if (Array.isArray(val)) {
      if (typeof sch["minItems"] === "number" && val.length < sch["minItems"]) {
        failures.push(`${path || "value"} has fewer than minItems ${sch["minItems"]}`);
      }
      if (typeof sch["maxItems"] === "number" && val.length > sch["maxItems"]) {
        failures.push(`${path || "value"} has more than maxItems ${sch["maxItems"]}`);
      }
      const items = sch["items"];
      if (items && typeof items === "object" && !Array.isArray(items)) {
        val.forEach((item, index) => check(item, items as Record<string, unknown>, `${path}[${index}]`));
      }
    }
    if (val !== null && typeof val === "object" && !Array.isArray(val)) {
      const record = val as Record<string, unknown>;
      const required = sch["required"];
      if (Array.isArray(required)) {
        for (const key of required) {
          if (typeof key === "string" && !(key in record)) {
            failures.push(`${path || "value"} is missing required property ${key}`);
          }
        }
      }
      const properties = sch["properties"];
      const known = new Set<string>();
      if (properties && typeof properties === "object" && !Array.isArray(properties)) {
        for (const [key, sub] of Object.entries(properties as Record<string, unknown>)) {
          known.add(key);
          if (key in record && sub && typeof sub === "object" && !Array.isArray(sub)) {
            check(record[key], sub as Record<string, unknown>, `${path}.${key}`);
          }
        }
      }
      if (sch["additionalProperties"] === false) {
        for (const key of Object.keys(record)) {
          if (!known.has(key)) failures.push(`${path || "value"} has unexpected property ${key}`);
        }
      }
    }
  };
  check(value, schema, "");
  return failures;
}

function matchesJsonType(value: unknown, type: string): boolean {
  switch (type) {
    case "object":
      return value !== null && typeof value === "object" && !Array.isArray(value);
    case "array":
      return Array.isArray(value);
    case "string":
      return typeof value === "string";
    case "number":
      return typeof value === "number" && Number.isFinite(value);
    case "integer":
      return typeof value === "number" && Number.isInteger(value);
    case "boolean":
      return typeof value === "boolean";
    case "null":
      return value === null;
    default:
      return true;
  }
}

// --- evidence selection -----------------------------------------------------

/**
 * The command_result item that answers the manifest's declared command.
 * Matching rule, pinned so both languages agree: an evidence item matches when
 * its command_name equals the argv joined by single spaces, or equals argv[0].
 * If no item matches, every command_result item is a candidate, so a collector
 * that names its command differently is still usable as long as it reported
 * exactly one command.
 */
function selectCommandResults(
  evidence: readonly MathAdmissibleEvidence[],
  evaluator: CommandExitCodeEvaluator,
): MathAdmissibleEvidence[] {
  const commandResults = evidence.filter((item) => item.kind === "command_result");
  const joined = evaluator.command.join(" ");
  const head = evaluator.command[0];
  const named = commandResults.filter(
    (item) => item.kind === "command_result" && (item.command_name === joined || item.command_name === head),
  );
  return named.length > 0 ? named : commandResults;
}

// --- the seven evaluator kinds ---------------------------------------------

export function evaluate(input: EvaluationInput): EvaluationResult {
  const { bundle, manifest } = input;
  const evaluator = manifest.evaluator;
  const authority = manifest.authority;

  // Only decisions of the same type and question may be graded by a manifest.
  // Harnesses draw decision boundaries differently, so a mismatch here means the
  // manifest is answering a different question, not that the agent was wrong.
  if (manifest.decision_type !== bundle.decision.decision_type) {
    return ungraded(
      "ambiguous",
      evaluator.kind,
      `manifest decision_type ${JSON.stringify(manifest.decision_type)} does not match the bundle's ${JSON.stringify(bundle.decision.decision_type)}`,
    );
  }
  if (manifest.evaluation_name !== bundle.decision.evaluation_name) {
    return ungraded(
      "ambiguous",
      evaluator.kind,
      `manifest evaluation_name ${JSON.stringify(manifest.evaluation_name)} does not match the bundle's ${JSON.stringify(bundle.decision.evaluation_name)}`,
    );
  }
  const taskId = bundle.correlation?.task_id;
  if (taskId != null && taskId !== manifest.task_id) {
    return ungraded(
      "ambiguous",
      evaluator.kind,
      `manifest task_id ${JSON.stringify(manifest.task_id)} does not match the bundle's ${JSON.stringify(taskId)}`,
    );
  }

  // The single point where harness self-assertions are dropped. Everything
  // below is typed to MathAdmissibleEvidence and cannot see them.
  const evidence = mathAdmissibleEvidence(bundle.evidence);
  const chosen = bundle.decision.chosen;

  switch (evaluator.kind) {
    case "exact_equality": {
      const payload = inlinePayload(chosen);
      if (!payload.ok) return ungraded(payload.reason, evaluator.kind, payload.detail);
      const caseSensitive = evaluator.case_sensitive ?? true;
      const trim = evaluator.trim_whitespace ?? true;
      const left = normalizeForExactEquality(payload.value, caseSensitive, trim);
      const right = normalizeForExactEquality(evaluator.expected, caseSensitive, trim);
      return graded(jsonEqual(left, right), authority, evaluator.kind, []);
    }

    case "json_equality": {
      const payload = inlinePayload(chosen);
      if (!payload.ok) return ungraded(payload.reason, evaluator.kind, payload.detail);
      return graded(jsonEqual(payload.value, evaluator.expected), authority, evaluator.kind, []);
    }

    case "command_exit_code": {
      const independent = input.runCommand?.(evaluator);
      if (independent !== undefined) {
        return graded(independent === evaluator.expected_exit_code, authority, evaluator.kind, []);
      }
      const candidates = selectCommandResults(evidence, evaluator);
      if (candidates.length === 0) {
        return ungraded(
          "no_ground_truth",
          evaluator.kind,
          `no command_result evidence for the declared command ${JSON.stringify(evaluator.command.join(" "))}; a harness claim of success is not a substitute`,
        );
      }
      if (candidates.length > 1) {
        return ungraded(
          "ambiguous",
          evaluator.kind,
          `${candidates.length} command_result items could answer the declared command; the verdict would depend on which one was picked`,
        );
      }
      const item = candidates[0] as Extract<MathAdmissibleEvidence, { kind: "command_result" }>;
      return graded(
        item.exit_code === evaluator.expected_exit_code,
        authority,
        evaluator.kind,
        [item.evidence_id],
      );
    }

    case "file_digest": {
      const independent = input.resolveFileDigest?.(evaluator);
      if (independent !== undefined) {
        return graded(independent === evaluator.expected.digest, authority, evaluator.kind, []);
      }
      const candidates = evidence.filter(
        (item) => item.kind === "file_state" && item.path === evaluator.path,
      );
      if (candidates.length === 0) {
        return ungraded(
          "no_ground_truth",
          evaluator.kind,
          `no file_state evidence for path ${JSON.stringify(evaluator.path)}`,
        );
      }
      if (candidates.length > 1) {
        return ungraded(
          "ambiguous",
          evaluator.kind,
          `${candidates.length} file_state items report path ${JSON.stringify(evaluator.path)}`,
        );
      }
      const item = candidates[0] as Extract<MathAdmissibleEvidence, { kind: "file_state" }>;
      const observed = item.artifact_digest;
      const correct =
        observed.algorithm === evaluator.expected.algorithm && observed.digest === evaluator.expected.digest;
      return graded(correct, authority, evaluator.kind, [item.evidence_id]);
    }

    case "json_schema": {
      // Prefer the chosen value; fall back to a single structured_output item,
      // which is how a harness reports a payload it did not put in `chosen`.
      let payloadValue: unknown;
      let evidenceIds: string[] = [];
      const payload = inlinePayload(chosen);
      if (payload.ok) {
        payloadValue = payload.value;
      } else {
        const structured = evidence.filter((item) => item.kind === "structured_output");
        if (structured.length !== 1) {
          return ungraded(payload.reason, evaluator.kind, payload.detail);
        }
        const item = structured[0] as Extract<MathAdmissibleEvidence, { kind: "structured_output" }>;
        const nested = inlinePayload(item.output);
        if (!nested.ok) return ungraded(nested.reason, evaluator.kind, nested.detail);
        payloadValue = nested.value;
        evidenceIds = [item.evidence_id];
      }
      const failures = validateAgainstSubsetSchema(payloadValue, evaluator.schema);
      return graded(
        failures.length === 0,
        authority,
        evaluator.kind,
        evidenceIds,
        failures.length === 0 ? undefined : failures.join("; "),
      );
    }

    case "callback": {
      const registered = input.checkers?.get(evaluator.name);
      if (!registered) {
        return ungraded(
          "no_ground_truth",
          evaluator.kind,
          `no checker named ${JSON.stringify(evaluator.name)} is registered; the manifest carries a lookup key, never code`,
        );
      }
      // The manifest's claim about determinism is checked against the registry,
      // which sits next to the real function. Where they disagree the registry
      // wins, and an over-claimed authority is refused rather than trusted.
      let effectiveAuthority = authority;
      let downgradedFrom: GradeAuthority | undefined;
      let disagreement: string | undefined;
      // One directional on purpose. Claiming LESS than the code could support
      // is always safe, so a deterministic checker used under a manifest that
      // only claims ai_judge is not a problem. The forbidden direction is a
      // model-assisted checker being presented as arithmetic.
      if (evaluator.determinism === "deterministic" && registered.determinism === "model_assisted") {
        disagreement =
          `manifest declares checker ${JSON.stringify(evaluator.name)} as deterministic ` +
          `but the registry registered it as model_assisted; the registry wins`;
      }
      if (registered.determinism === "model_assisted" && authority === "math") {
        effectiveAuthority = "ai_judge";
        downgradedFrom = "math";
      }
      let result: CheckerResult;
      try {
        result = registered.checker({ chosen, evidence, options: evaluator.options ?? {} });
      } catch (error) {
        return ungraded("ambiguous", evaluator.kind, `checker ${evaluator.name} threw: ${String(error)}`);
      }
      if (typeof result?.passed !== "boolean") {
        return ungraded(
          "ambiguous",
          evaluator.kind,
          `checker ${evaluator.name} did not return a boolean \`passed\``,
        );
      }
      if (result.reason === "no_ground_truth" || result.reason === "empty_answer" || result.reason === "ambiguous") {
        return ungraded(result.reason, evaluator.kind, result.explanation ?? `checker ${evaluator.name} declined to grade`);
      }
      const explanation = [disagreement, result.explanation].filter(Boolean).join("; ") || undefined;
      const verdict = graded(result.passed, effectiveAuthority, evaluator.kind, [], explanation);
      return downgradedFrom === undefined ? verdict : { ...verdict, authorityDowngradedFrom: downgradedFrom };
    }

    case "outcome": {
      // No checker runs. Reality arrives later, or it has not arrived yet.
      const decisionId = input.decisionId ?? bundle.decision.decision_id;
      if (!decisionId) {
        return ungraded(
          "ambiguous",
          evaluator.kind,
          "an outcome must be matched to a decision id, and none was supplied or derived",
        );
      }
      const matches = (input.outcomes ?? []).filter(
        (outcome) => outcome.decision_id === decisionId && outcome.outcome_type === evaluator.outcome_type,
      );
      if (matches.length === 0) {
        return ungraded(
          "no_ground_truth",
          evaluator.kind,
          `no ${JSON.stringify(evaluator.outcome_type)} outcome has been observed for ${JSON.stringify(decisionId)} yet`,
        );
      }
      // Latest observation wins; an outcome can overturn an earlier one, and a
      // stable tiebreak on outcome_id keeps replay deterministic.
      const chosenOutcome = [...matches].sort((a, b) => {
        const byTime = Date.parse(a.observed_at) - Date.parse(b.observed_at);
        return byTime !== 0 ? byTime : a.outcome_id.localeCompare(b.outcome_id);
      })[matches.length - 1] as OutcomeRecord;
      return graded(
        chosenOutcome.correct,
        authority,
        evaluator.kind,
        [chosenOutcome.outcome_id],
        chosenOutcome.explanation ?? undefined,
      );
    }
  }
}

/**
 * Convenience predicate for the headline metric: only math and reality grades
 * count as verified correct. An ai_judge opinion never enters the numerator.
 */
export function isVerifiedCorrect(result: EvaluationResult): boolean {
  return result.graded && result.correct && (result.authority === "math" || result.authority === "reality");
}
