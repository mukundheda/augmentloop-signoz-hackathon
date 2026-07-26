/**
 * Types mirroring the four frozen JSON Schemas in universal-adapter/schemas.
 *
 * The schemas are the contract; these types are a convenience for TypeScript
 * callers and are deliberately structural, so a record parsed from JSON can be
 * used directly once validate() has passed. Field names stay snake_case to
 * match the wire format exactly: a camelCase mirror would need a translation
 * layer and every translation layer is somewhere for a field to go missing.
 *
 * Every object type here is CLOSED (design decision D1). The single `ext`
 * object per record is the only place unknown fields are legal, which is why
 * `ext` is the only index-signature property in this file.
 */

export const SCHEMA_VERSION = "1.0";
export type SchemaVersion = typeof SCHEMA_VERSION;

/** Forward-compatibility namespace: the only place unknown fields are legal. */
export type Ext = Record<string, unknown>;

export interface Sha256Digest {
  algorithm: "sha256";
  digest: string;
  byte_length?: number;
}

/**
 * The tagged value union (design decision D2). A value may be carried inline,
 * by digest, by reference to an artifact, or explicitly declared absent. The
 * `absent` arm is not the same as an empty inline value: an empty answer is a
 * real answer of zero length, and conflating the two hides a captured failure.
 */
export type ValueAbsentReason = "redacted" | "not_captured" | "too_large" | "unknown";

export type InlineValue = { kind: "inline"; value: unknown };
export type DigestValue = {
  kind: "digest";
  algorithm: "sha256";
  digest: string;
  byte_length?: number;
};
export type ArtifactReferenceValue = {
  kind: "artifact_reference";
  value: string;
  digest?: Sha256Digest;
};
export type AbsentValue = { kind: "absent"; reason: ValueAbsentReason };

export type ProtocolValue = InlineValue | DigestValue | ArtifactReferenceValue | AbsentValue;

export type ValueKind = ProtocolValue["kind"];

// --- evidence ---------------------------------------------------------------

export interface CommandResultEvidence {
  evidence_id: string;
  kind: "command_result";
  command_name: string;
  exit_code: number;
  duration_ms?: number;
  artifact_digest?: Sha256Digest;
}

export interface FileStateEvidence {
  evidence_id: string;
  kind: "file_state";
  path: string;
  artifact_digest: Sha256Digest;
}

export interface TestReportEvidence {
  evidence_id: string;
  kind: "test_report";
  passed: number;
  failed: number;
  skipped?: number;
  artifact_digest?: Sha256Digest;
}

export interface StructuredOutputEvidence {
  evidence_id: string;
  kind: "structured_output";
  output: ProtocolValue;
}

export interface OtelSpanEvidence {
  evidence_id: string;
  kind: "otel_span";
  trace_id: string;
  span_id: string;
}

export interface LogReferenceEvidence {
  evidence_id: string;
  kind: "log_reference";
  ref: string;
  artifact_digest?: Sha256Digest;
}

/**
 * The harness asserting something about its own run. Its own kind so that no
 * evaluator can mistake it for a verdict; see MathAdmissibleEvidence below,
 * which excludes it at the type level.
 */
export interface HarnessClaimEvidence {
  evidence_id: string;
  kind: "harness_claim";
  claim: Record<string, string | number | boolean | null>;
}

export type EvidenceItem =
  | CommandResultEvidence
  | FileStateEvidence
  | TestReportEvidence
  | StructuredOutputEvidence
  | OtelSpanEvidence
  | LogReferenceEvidence
  | HarnessClaimEvidence;

export type EvidenceKind = EvidenceItem["kind"];

/**
 * Evidence a deterministic evaluator is allowed to look at. HarnessClaimEvidence
 * is removed by the type system, not by a runtime `if`, so a future evaluator
 * that tries to read `claim` fails to compile rather than failing in production.
 */
export type MathAdmissibleEvidence = Exclude<EvidenceItem, HarnessClaimEvidence>;

// --- decision evidence bundle ----------------------------------------------

export interface DecisionEvidenceBundleDecision {
  decision_id?: string;
  decision_type: string;
  evaluation_name: string;
  chosen: ProtocolValue;
}

export interface DecisionEvidenceBundleSubject {
  harness: string;
  harness_version?: string | null;
  run_id: string;
  session_id?: string | null;
  agent_id?: string | null;
  parent_agent_id?: string | null;
  model?: string | null;
}

export interface DecisionEvidenceBundleCorrelation {
  provider_response_id?: string | null;
  trace_id?: string | null;
  span_id?: string | null;
  task_id?: string | null;
}

export type MetadataValue = string | number | boolean | null;

export interface DecisionEvidenceBundle {
  schema_version: SchemaVersion;
  decision: DecisionEvidenceBundleDecision;
  subject: DecisionEvidenceBundleSubject;
  correlation?: DecisionEvidenceBundleCorrelation;
  evidence: EvidenceItem[];
  usage_refs?: string[];
  metadata?: Record<string, MetadataValue>;
  ext?: Ext;
}

// --- usage record -----------------------------------------------------------

export type UsageScope = "model_invocation" | "decision" | "agent" | "run";

/** Strongest first. The array order IS the precedence order (see costing.ts). */
export const COST_PROVENANCE_PRECEDENCE = [
  "provider_reported",
  "provider_token_estimate",
  "harness_token_estimate",
  "run_aggregate",
  "unknown",
] as const;

export type CostProvenance = (typeof COST_PROVENANCE_PRECEDENCE)[number];

export interface UsageRecord {
  schema_version: SchemaVersion;
  usage_id: string;
  scope: UsageScope;
  run_id: string;
  agent_id?: string | null;
  parent_agent_id?: string | null;
  contains_usage_ids?: string[];
  decision_ids?: string[];
  provider_response_id?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_input_tokens?: number | null;
  provider_cost_usd?: number | null;
  cost_provenance: CostProvenance;
  pricing_table_id?: string | null;
  ext?: Ext;
}

// --- evaluation manifest ----------------------------------------------------

export type GradeAuthority = "math" | "reality" | "ai_judge";

export interface ExactEqualityEvaluator {
  kind: "exact_equality";
  expected: unknown;
  case_sensitive?: boolean;
  trim_whitespace?: boolean;
}

export interface JsonEqualityEvaluator {
  kind: "json_equality";
  expected: unknown;
}

export interface CommandExitCodeEvaluator {
  kind: "command_exit_code";
  command: string[];
  expected_exit_code: number;
  timeout_seconds?: number;
  working_directory?: string;
}

export interface FileDigestEvaluator {
  kind: "file_digest";
  path: string;
  expected: Sha256Digest;
}

export interface JsonSchemaEvaluator {
  kind: "json_schema";
  schema: Record<string, unknown>;
}

/**
 * Whether a checker computes its verdict or asks a model for one. Required on
 * the manifest and again at registration, with no default anywhere: a defaulted
 * value would be a guess about the one property that decides whether a result
 * can reach the headline metric.
 */
export type CallbackDeterminism = "deterministic" | "model_assisted";

export interface CallbackEvaluator {
  kind: "callback";
  name: string;
  determinism: CallbackDeterminism;
  options?: Record<string, MetadataValue>;
}

export interface OutcomeEvaluator {
  kind: "outcome";
  outcome_type: string;
  observation_window_seconds?: number;
}

export type Evaluator =
  | ExactEqualityEvaluator
  | JsonEqualityEvaluator
  | CommandExitCodeEvaluator
  | FileDigestEvaluator
  | JsonSchemaEvaluator
  | CallbackEvaluator
  | OutcomeEvaluator;

export type EvaluatorKind = Evaluator["kind"];

/** The six deterministic kinds. `outcome` is excluded: it confers reality. */
export type DeterministicEvaluator = Exclude<Evaluator, OutcomeEvaluator>;

export interface EvaluationManifest {
  schema_version: SchemaVersion;
  task_id: string;
  decision_type: string;
  evaluation_name: string;
  authority: GradeAuthority;
  evaluator: Evaluator;
  description?: string;
  ext?: Ext;
}

// --- outcome record ---------------------------------------------------------

export interface OutcomeRecord {
  schema_version: SchemaVersion;
  outcome_id: string;
  decision_id: string;
  provider_response_id?: string | null;
  outcome_type: string;
  correct: boolean;
  observed_at: string;
  evidence_ref?: string | null;
  explanation?: string | null;
  ext?: Ext;
}

// --- pricing ----------------------------------------------------------------

export interface PricingTableEntry {
  input_per_1m_usd: number;
  output_per_1m_usd: number;
}

/**
 * A rate card. Its identity (pricing_table_id) is a digest over its canonical
 * serialization, so a cost figure can always be traced to the exact rates that
 * produced it even if the table is later edited in place.
 *
 * There is deliberately NO version field (ADR 0008). The digest IS the version.
 * A hand-maintained version string inside the hashed object would let two
 * genuinely different rate tables share one identifier whenever somebody edits
 * a rate and forgets to bump the string, which is the precise failure the
 * content digest exists to eliminate. It would also be unreproducible from the
 * Python side, whose gradebook.pricing.PRICES carries no version.
 */
export interface PricingTable {
  currency: "usd";
  models: Record<string, PricingTableEntry>;
}

// --- the adapter interface the issue specifies ------------------------------

export interface HarnessEvidenceAdapter<TSource> {
  normalizeRun(source: TSource): Iterable<DecisionEvidenceBundle>;
  normalizeUsage(source: TSource): Iterable<UsageRecord>;
}

/** Every record kind in the protocol, keyed the way fixtures name them. */
export type RecordKind =
  | "decision_evidence_bundle"
  | "usage_record"
  | "evaluation_manifest"
  | "outcome_record";

export function isHarnessClaim(item: EvidenceItem): item is HarnessClaimEvidence {
  return item.kind === "harness_claim";
}

/**
 * Drop harness self-assertions before any deterministic evaluation. The return
 * type is what makes "a harness_claim cannot yield a math grade" structural:
 * downstream code literally cannot receive one.
 */
export function mathAdmissibleEvidence(items: readonly EvidenceItem[]): MathAdmissibleEvidence[] {
  return items.filter((item): item is MathAdmissibleEvidence => !isHarnessClaim(item));
}
