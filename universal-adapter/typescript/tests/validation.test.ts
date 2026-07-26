/**
 * Validation: one accept and several rejects per schema, plus the properties
 * the acceptance criteria call out. Fixture parity lives in corpus.test.ts;
 * these are the unit-level rules, including the ones no fixture can express
 * (never throwing, error shape, discriminator-first dispatch).
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { validate, isValid, normalizeRecordKind } from "../src/validation.ts";
import type { ValidationError } from "../src/validation.ts";

const DIGEST = "a".repeat(64);

function bundle(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: "1.0",
    decision: {
      decision_type: "task_completion",
      evaluation_name: "repository.tests_pass",
      chosen: { kind: "artifact_reference", value: "workspace-after-agent" },
    },
    subject: { harness: "hermes", run_id: "run-42" },
    evidence: [],
    ...overrides,
  };
}

function usage(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: "1.0",
    usage_id: "usage-101",
    scope: "model_invocation",
    run_id: "run-42",
    cost_provenance: "unknown",
    ...overrides,
  };
}

function manifest(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: "1.0",
    task_id: "repair-auth-017",
    decision_type: "task_completion",
    evaluation_name: "repository.tests_pass",
    authority: "math",
    evaluator: { kind: "command_exit_code", command: ["npm", "test"], expected_exit_code: 0 },
    ...overrides,
  };
}

function outcome(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: "1.0",
    outcome_id: "outcome-88",
    decision_id: "decision-017",
    outcome_type: "pull_request_merged",
    correct: true,
    observed_at: "2026-07-27T10:00:00Z",
    ...overrides,
  };
}

function paths(errors: readonly ValidationError[]): string[] {
  return errors.map((e) => e.path);
}

describe("decision evidence bundle", () => {
  test("accepts a minimal bundle", () => {
    assert.deepEqual(validate("decision_evidence_bundle", bundle()), []);
  });

  test("rejects an unknown schema version rather than guessing", () => {
    const errors = validate("decision_evidence_bundle", bundle({ schema_version: "2.0" }));
    assert.ok(paths(errors).includes("/schema_version"));
    assert.match(errors[0]!.message, /unknown schema_version/);
  });

  test("rejects unknown top-level fields, since objects are closed", () => {
    const errors = validate("decision_evidence_bundle", bundle({ surprise: 1 }));
    assert.ok(paths(errors).includes("/surprise"));
    assert.match(errors[0]!.expected, /one of:/);
  });

  test("accepts unknown fields inside ext, the one place they are legal", () => {
    assert.ok(isValid("decision_evidence_bundle", bundle({ ext: { anything: { nested: true } } })));
  });

  test("rejects a trace id that is not 32 lowercase hex characters", () => {
    const errors = validate("decision_evidence_bundle", bundle({ correlation: { trace_id: "NOTHEX" } }));
    assert.ok(paths(errors).includes("/correlation/trace_id"));
  });

  test("an empty evidence array is legal and honest", () => {
    assert.ok(isValid("decision_evidence_bundle", bundle({ evidence: [] })));
  });

  test("metadata must not carry payloads", () => {
    const errors = validate("decision_evidence_bundle", bundle({ metadata: { nested: { a: 1 } } }));
    assert.ok(paths(errors).includes("/metadata/nested"));
  });
});

describe("the tagged value union", () => {
  const chosen = (value: unknown) => bundle({
    decision: {
      decision_type: "tool_choice",
      evaluation_name: "tool.correct",
      chosen: value,
    },
  });

  test("accepts all four arms", () => {
    for (const value of [
      { kind: "inline", value: { any: "json" } },
      { kind: "digest", algorithm: "sha256", digest: DIGEST, byte_length: 12 },
      { kind: "artifact_reference", value: "s3://bucket/key", digest: { algorithm: "sha256", digest: DIGEST } },
      { kind: "absent", reason: "redacted" },
    ]) {
      assert.deepEqual(validate("decision_evidence_bundle", chosen(value)), [], JSON.stringify(value));
    }
  });

  test("an inline empty string is a real answer, not an absent one", () => {
    assert.ok(isValid("decision_evidence_bundle", chosen({ kind: "inline", value: "" })));
  });

  test("a missing discriminator produces one actionable error, not a pile of arm failures", () => {
    const errors = validate("decision_evidence_bundle", chosen({ value: "no kind here" }));
    assert.equal(errors.length, 1);
    assert.equal(errors[0]!.path, "/decision/chosen/kind");
    assert.match(errors[0]!.expected, /inline, digest, artifact_reference, absent/);
  });

  test("an unknown discriminator names the legal values", () => {
    const errors = validate("decision_evidence_bundle", chosen({ kind: "pointer", value: "x" }));
    assert.equal(errors.length, 1);
    assert.match(errors[0]!.expected, /one of: inline/);
  });

  test("once kind selects an arm, only that arm's rules apply", () => {
    // `value` belongs to the inline arm; on the absent arm it is an unknown field.
    const errors = validate("decision_evidence_bundle", chosen({ kind: "absent", reason: "unknown", value: 1 }));
    assert.ok(paths(errors).includes("/decision/chosen/value"));
    assert.ok(errors.every((e) => !e.message.includes("oneOf")));
  });

  test("rejects an absent reason outside the closed enum", () => {
    const errors = validate("decision_evidence_bundle", chosen({ kind: "absent", reason: "because" }));
    assert.ok(paths(errors).includes("/decision/chosen/reason"));
  });
});

describe("evidence items", () => {
  const withEvidence = (item: unknown) => bundle({ evidence: [item] });

  test("accepts every evidence kind", () => {
    const items = [
      { evidence_id: "e1", kind: "command_result", command_name: "project-test-suite", exit_code: 0 },
      { evidence_id: "e2", kind: "file_state", path: "src/app.ts", artifact_digest: { algorithm: "sha256", digest: DIGEST } },
      { evidence_id: "e3", kind: "test_report", passed: 10, failed: 0, skipped: 1 },
      { evidence_id: "e4", kind: "structured_output", output: { kind: "inline", value: [1, 2] } },
      { evidence_id: "e5", kind: "otel_span", trace_id: "0".repeat(32), span_id: "0".repeat(16) },
      { evidence_id: "e6", kind: "log_reference", ref: "s3://logs/run-42" },
      { evidence_id: "e7", kind: "harness_claim", claim: { success: true } },
    ];
    assert.deepEqual(validate("decision_evidence_bundle", bundle({ evidence: items })), []);
  });

  test("a harness claim may not smuggle a payload into its claim object", () => {
    const errors = validate(
      "decision_evidence_bundle",
      withEvidence({ evidence_id: "e1", kind: "harness_claim", claim: { detail: { patch: "..." } } }),
    );
    assert.ok(paths(errors).includes("/evidence/0/claim/detail"));
  });

  test("rejects an unknown evidence kind by naming the legal kinds", () => {
    const errors = validate("decision_evidence_bundle", withEvidence({ evidence_id: "e1", kind: "vibes" }));
    assert.equal(errors.length, 1);
    assert.match(errors[0]!.expected, /command_result/);
  });
});

describe("usage record", () => {
  test("accepts a minimal record", () => {
    assert.deepEqual(validate("usage_record", usage()), []);
  });

  test("null tokens and zero tokens are different things and both validate", () => {
    assert.ok(isValid("usage_record", usage({ input_tokens: null, output_tokens: 0 })));
  });

  test("rejects a token estimate with no pricing table identity", () => {
    const errors = validate("usage_record", usage({ cost_provenance: "provider_token_estimate" }));
    assert.ok(paths(errors).includes("/pricing_table_id"));
  });

  test("rejects provider_reported provenance with no provider figure", () => {
    const errors = validate("usage_record", usage({ cost_provenance: "provider_reported" }));
    assert.ok(paths(errors).includes("/provider_cost_usd"));
  });

  test("rejects a run aggregate that is not run scoped", () => {
    const errors = validate(
      "usage_record",
      usage({ cost_provenance: "run_aggregate", scope: "agent", provider_cost_usd: 1 }),
    );
    assert.ok(paths(errors).includes("/scope"));
  });

  test("rejects a negative provider cost", () => {
    const errors = validate("usage_record", usage({ provider_cost_usd: -0.01 }));
    assert.ok(paths(errors).includes("/provider_cost_usd"));
  });
});

describe("evaluation manifest", () => {
  test("accepts a math manifest with a deterministic evaluator", () => {
    assert.deepEqual(validate("evaluation_manifest", manifest()), []);
  });

  test("rejects math authority carried by an outcome evaluator", () => {
    const errors = validate(
      "evaluation_manifest",
      manifest({ evaluator: { kind: "outcome", outcome_type: "pull_request_merged" } }),
    );
    assert.ok(paths(errors).includes("/evaluator/kind"));
  });

  test("rejects reality authority carried by a checker that runs at decision time", () => {
    const errors = validate("evaluation_manifest", manifest({ authority: "reality" }));
    assert.ok(paths(errors).includes("/evaluator/kind"));
  });

  test("a callback must declare its determinism", () => {
    const errors = validate(
      "evaluation_manifest",
      manifest({ authority: "ai_judge", evaluator: { kind: "callback", name: "house_style" } }),
    );
    assert.ok(paths(errors).includes("/evaluator"));
    assert.ok(errors.some((e) => e.message.includes("determinism")));
  });

  test("a model-assisted callback cannot carry math authority", () => {
    const errors = validate(
      "evaluation_manifest",
      manifest({ evaluator: { kind: "callback", name: "llm_pairwise_judge", determinism: "model_assisted" } }),
    );
    assert.ok(paths(errors).includes("/evaluator/determinism"));
  });

  test("a math callback that omits determinism is rejected and says why at the determinism path", () => {
    const errors = validate(
      "evaluation_manifest",
      manifest({ evaluator: { kind: "callback", name: "house_style" } }),
    );
    // Rule 2: one authored mistake may legitimately produce several errors. The
    // assertion is rejection plus the presence of the useful path, not a count.
    assert.ok(errors.length > 0);
    assert.ok(paths(errors).includes("/evaluator/determinism"));
    assert.ok(errors.some((e) => e.expected.includes("deterministic")));
  });

  test("claiming LESS authority than the evaluator could support is legal", () => {
    assert.deepEqual(
      validate(
        "evaluation_manifest",
        manifest({ authority: "ai_judge", evaluator: { kind: "callback", name: "house_style", determinism: "deterministic" } }),
      ),
      [],
    );
    assert.deepEqual(validate("evaluation_manifest", manifest({ authority: "ai_judge" })), []);
  });
});

describe("outcome record", () => {
  test("accepts a well formed outcome", () => {
    assert.deepEqual(validate("outcome_record", outcome()), []);
  });

  test("rejects a truthy 1 in place of a boolean", () => {
    const errors = validate("outcome_record", outcome({ correct: 1 }));
    assert.ok(paths(errors).includes("/correct"));
    assert.match(errors[0]!.message, /must not be coerced/);
  });

  test("rejects a timestamp that does not match the RFC 3339 pattern", () => {
    for (const bad of ["not-a-date", "2026-07-27 10:00:00Z", "2026-07-27T10:00:00"]) {
      const errors = validate("outcome_record", outcome({ observed_at: bad }));
      assert.ok(paths(errors).includes("/observed_at"), bad);
    }
  });

  test("accepts the offset and fractional forms the pattern allows", () => {
    for (const good of ["2026-07-27T10:00:00Z", "2026-07-27T10:00:00.123456+05:30", "2026-07-27t10:00:00z"]) {
      assert.deepEqual(validate("outcome_record", outcome({ observed_at: good })), [], good);
    }
  });

  test("an impossible date passes, because only the pattern is asserted", () => {
    // Recorded deliberately: a stricter semantic check on one side only would
    // be a parity break in the other direction.
    assert.deepEqual(validate("outcome_record", outcome({ observed_at: "2026-13-45T99:00:00Z" })), []);
  });

  test("an unlinked outcome is rejected", () => {
    const { decision_id: _dropped, ...withoutDecision } = outcome();
    const errors = validate("outcome_record", withoutDecision);
    assert.ok(paths(errors).includes(""));
  });
});

describe("the validator's own contract", () => {
  test("never throws, whatever it is handed", () => {
    for (const hostile of [null, undefined, 42, "string", [], { a: { b: { c: [] } } }, new Map()]) {
      for (const kind of ["decision_evidence_bundle", "usage_record", "evaluation_manifest", "outcome_record"]) {
        assert.ok(Array.isArray(validate(kind, hostile)));
      }
    }
  });

  test("every error is actionable: it has a path, a cause and an expectation", () => {
    const errors = validate("decision_evidence_bundle", { schema_version: "1.0" });
    assert.ok(errors.length > 0);
    for (const error of errors) {
      assert.equal(typeof error.path, "string");
      assert.ok(error.message.length > 0);
      assert.ok(error.expected.length > 0);
    }
  });

  test("an unknown record kind is reported rather than thrown", () => {
    const errors = validate("not_a_record_kind", {});
    assert.equal(errors.length, 1);
    assert.match(errors[0]!.message, /unknown record kind/);
  });

  test("record kind names are accepted in the corpus's spelling too", () => {
    assert.equal(normalizeRecordKind("decision-evidence-bundle"), "decision_evidence_bundle");
    assert.equal(normalizeRecordKind("usage-record"), "usage_record");
    assert.equal(normalizeRecordKind("evaluation-manifest"), "evaluation_manifest");
    assert.equal(normalizeRecordKind("outcome-record"), "outcome_record");
  });
});
