/**
 * The seven evaluator kinds, and the invariant the whole protocol exists for:
 * a harness saying it succeeded is evidence, never a verdict.
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { CheckerRegistry, evaluate, isVerifiedCorrect } from "../src/evaluation.ts";
import type { EvaluationResult } from "../src/evaluation.ts";
import type {
  DecisionEvidenceBundle,
  EvaluationManifest,
  EvidenceItem,
  Evaluator,
  GradeAuthority,
  OutcomeRecord,
  ProtocolValue,
} from "../src/models.ts";

const DIGEST_A = "a".repeat(64);
const DIGEST_B = "b".repeat(64);

function bundle(chosen: ProtocolValue, evidence: EvidenceItem[] = []): DecisionEvidenceBundle {
  return {
    schema_version: "1.0",
    decision: { decision_id: "decision-017", decision_type: "task_completion", evaluation_name: "repository.tests_pass", chosen },
    subject: { harness: "hermes", run_id: "run-42" },
    correlation: { task_id: "repair-auth-017" },
    evidence,
  };
}

function manifest(evaluator: Evaluator, authority: GradeAuthority = "math"): EvaluationManifest {
  return {
    schema_version: "1.0",
    task_id: "repair-auth-017",
    decision_type: "task_completion",
    evaluation_name: "repository.tests_pass",
    authority,
    evaluator,
  };
}

function assertGraded(result: EvaluationResult, correct: boolean, authority: GradeAuthority): void {
  assert.ok(result.graded, `expected a grade, got: ${JSON.stringify(result)}`);
  assert.equal(result.correct, correct);
  assert.equal(result.authority, authority);
  assert.equal(result.reason, correct ? "match" : "mismatch");
}

describe("exact_equality", () => {
  const evaluator = { kind: "exact_equality", expected: "42" } as const;

  test("grades a match and a mismatch", () => {
    assertGraded(evaluate({ bundle: bundle({ kind: "inline", value: "42" }), manifest: manifest(evaluator) }), true, "math");
    assertGraded(evaluate({ bundle: bundle({ kind: "inline", value: "43" }), manifest: manifest(evaluator) }), false, "math");
  });

  test("honours case sensitivity and whitespace trimming", () => {
    const loose = { kind: "exact_equality", expected: "Yes", case_sensitive: false, trim_whitespace: true } as const;
    assertGraded(evaluate({ bundle: bundle({ kind: "inline", value: "  yes " }), manifest: manifest(loose) }), true, "math");
    const strict = { kind: "exact_equality", expected: "Yes", case_sensitive: true, trim_whitespace: false } as const;
    assertGraded(evaluate({ bundle: bundle({ kind: "inline", value: "  yes " }), manifest: manifest(strict) }), false, "math");
  });

  test("an empty answer is not gradeable, and is not a wrong answer either", () => {
    const result = evaluate({ bundle: bundle({ kind: "inline", value: "" }), manifest: manifest(evaluator) });
    assert.equal(result.graded, false);
    assert.ok(!result.graded && result.reason === "empty_answer");
  });

  test("a value carried by digest cannot be compared, and says so", () => {
    const result = evaluate({
      bundle: bundle({ kind: "digest", algorithm: "sha256", digest: DIGEST_A }),
      manifest: manifest(evaluator),
    });
    assert.equal(result.graded, false);
    assert.ok(!result.graded && result.reason === "ambiguous");
  });
});

describe("json_equality", () => {
  const evaluator = { kind: "json_equality", expected: { b: [1, 2], a: "x" } } as const;

  test("is order insensitive for object keys and order sensitive for arrays", () => {
    assertGraded(
      evaluate({ bundle: bundle({ kind: "inline", value: { a: "x", b: [1, 2] } }), manifest: manifest(evaluator) }),
      true,
      "math",
    );
    assertGraded(
      evaluate({ bundle: bundle({ kind: "inline", value: { a: "x", b: [2, 1] } }), manifest: manifest(evaluator) }),
      false,
      "math",
    );
  });
});

describe("command_exit_code", () => {
  const evaluator: Evaluator = { kind: "command_exit_code", command: ["npm", "test"], expected_exit_code: 0 };
  const commandEvidence = (exitCode: number, name = "npm test"): EvidenceItem => ({
    evidence_id: "evidence-tests-1",
    kind: "command_result",
    command_name: name,
    exit_code: exitCode,
  });

  test("the exit status in the evidence is the verdict", () => {
    const pass = evaluate({ bundle: bundle({ kind: "absent", reason: "not_captured" }, [commandEvidence(0)]), manifest: manifest(evaluator) });
    assertGraded(pass, true, "math");
    assert.ok(pass.graded && pass.evidenceIds.includes("evidence-tests-1"));
    assertGraded(
      evaluate({ bundle: bundle({ kind: "absent", reason: "not_captured" }, [commandEvidence(1)]), manifest: manifest(evaluator) }),
      false,
      "math",
    );
  });

  test("an injected independent run outranks reported evidence", () => {
    const result = evaluate({
      bundle: bundle({ kind: "absent", reason: "not_captured" }, [commandEvidence(0)]),
      manifest: manifest(evaluator),
      runCommand: () => 1,
    });
    assertGraded(result, false, "math");
  });

  test("with no command evidence there is no ground truth", () => {
    const result = evaluate({ bundle: bundle({ kind: "absent", reason: "not_captured" }), manifest: manifest(evaluator) });
    assert.ok(!result.graded && result.reason === "no_ground_truth");
  });

  test("two candidate command results are ambiguous rather than arbitrarily picked", () => {
    const result = evaluate({
      bundle: bundle({ kind: "absent", reason: "not_captured" }, [
        { ...commandEvidence(0), evidence_id: "e1" },
        { ...commandEvidence(1), evidence_id: "e2" },
      ]),
      manifest: manifest(evaluator),
    });
    assert.ok(!result.graded && result.reason === "ambiguous");
  });
});

describe("file_digest", () => {
  const evaluator = { kind: "file_digest", path: "src/app.ts", expected: { algorithm: "sha256", digest: DIGEST_A } } as const;
  const fileEvidence = (digest: string): EvidenceItem => ({
    evidence_id: "evidence-file-1",
    kind: "file_state",
    path: "src/app.ts",
    artifact_digest: { algorithm: "sha256", digest },
  });

  test("compares the observed digest with the expected one", () => {
    assertGraded(
      evaluate({ bundle: bundle({ kind: "absent", reason: "not_captured" }, [fileEvidence(DIGEST_A)]), manifest: manifest(evaluator) }),
      true,
      "math",
    );
    assertGraded(
      evaluate({ bundle: bundle({ kind: "absent", reason: "not_captured" }, [fileEvidence(DIGEST_B)]), manifest: manifest(evaluator) }),
      false,
      "math",
    );
  });

  test("a different path is not evidence about this file", () => {
    const other: EvidenceItem = { ...fileEvidence(DIGEST_A), path: "src/other.ts" } as EvidenceItem;
    const result = evaluate({ bundle: bundle({ kind: "absent", reason: "not_captured" }, [other]), manifest: manifest(evaluator) });
    assert.ok(!result.graded && result.reason === "no_ground_truth");
  });
});

describe("json_schema", () => {
  const evaluator = {
    kind: "json_schema",
    schema: {
      type: "object",
      required: ["answer"],
      properties: { answer: { type: "string", minLength: 1 }, score: { type: "number", minimum: 0 } },
      additionalProperties: false,
    },
  } as const;

  test("passes a conforming payload and fails a non-conforming one", () => {
    assertGraded(
      evaluate({ bundle: bundle({ kind: "inline", value: { answer: "yes", score: 1 } }), manifest: manifest(evaluator) }),
      true,
      "math",
    );
    const failing = evaluate({ bundle: bundle({ kind: "inline", value: { score: -1 } }), manifest: manifest(evaluator) });
    assertGraded(failing, false, "math");
    assert.ok(failing.graded && failing.explanation && failing.explanation.includes("required"));
  });

  test("falls back to a single structured_output evidence item", () => {
    const result = evaluate({
      bundle: bundle({ kind: "absent", reason: "too_large" }, [
        { evidence_id: "e1", kind: "structured_output", output: { kind: "inline", value: { answer: "yes" } } },
      ]),
      manifest: manifest(evaluator),
    });
    assertGraded(result, true, "math");
    assert.ok(result.graded && result.evidenceIds.includes("e1"));
  });
});

describe("callback", () => {
  test("resolves the checker by name from the application's registry", () => {
    const checkers = new CheckerRegistry().register(
      "answer_is_long_enough",
      ({ chosen }) => ({ passed: chosen.kind === "inline" && String(chosen.value).length > 3 }),
      "deterministic",
    );
    const evaluator = { kind: "callback", name: "answer_is_long_enough", determinism: "deterministic" } as const;
    assertGraded(evaluate({ bundle: bundle({ kind: "inline", value: "long enough" }), manifest: manifest(evaluator), checkers }), true, "math");
    assertGraded(evaluate({ bundle: bundle({ kind: "inline", value: "no" }), manifest: manifest(evaluator), checkers }), false, "math");
  });

  test("an unregistered name yields no ground truth, because a manifest carries a key and not code", () => {
    const result = evaluate({
      bundle: bundle({ kind: "inline", value: "x" }),
      manifest: manifest({ kind: "callback", name: "nowhere", determinism: "deterministic" }),
      checkers: new CheckerRegistry(),
    });
    assert.ok(!result.graded && result.reason === "no_ground_truth");
  });

  test("registration requires an explicit determinism declaration", () => {
    const registry = new CheckerRegistry();
    assert.throws(
      // The declaration is required by the type system; this is the runtime
      // guard for callers arriving from plain JavaScript.
      () => registry.register("x", () => ({ passed: true }), "probably_fine" as never),
      /must declare determinism/,
    );
  });

  test("a manifest claiming deterministic over a model-assisted registration is refused math authority", () => {
    const checkers = new CheckerRegistry().register("llm_pairwise_judge", () => ({ passed: true }), "model_assisted");
    const result = evaluate({
      bundle: bundle({ kind: "inline", value: "x" }),
      // The manifest lies. The registry sits next to the real function, so it wins.
      manifest: manifest({ kind: "callback", name: "llm_pairwise_judge", determinism: "deterministic" }, "math"),
      checkers,
    });
    assertGraded(result, true, "ai_judge");
    assert.ok(result.graded && result.authorityDowngradedFrom === "math");
    assert.ok(result.graded && result.explanation?.includes("registry wins"));
    assert.equal(isVerifiedCorrect(result), false, "a downgraded grade must not reach the headline metric");
  });

  test("claiming less authority than the code supports is left alone", () => {
    const checkers = new CheckerRegistry().register("house_style", () => ({ passed: true }), "deterministic");
    const result = evaluate({
      bundle: bundle({ kind: "inline", value: "x" }),
      manifest: manifest({ kind: "callback", name: "house_style", determinism: "deterministic" }, "ai_judge"),
      checkers,
    });
    assertGraded(result, true, "ai_judge");
    assert.ok(result.graded && result.authorityDowngradedFrom === undefined);
  });

  test("a checker that throws does not take the evaluator down with it", () => {
    const checkers = new CheckerRegistry().register(
      "explodes",
      () => {
        throw new Error("boom");
      },
      "deterministic",
    );
    const result = evaluate({
      bundle: bundle({ kind: "inline", value: "x" }),
      manifest: manifest({ kind: "callback", name: "explodes", determinism: "deterministic" }),
      checkers,
    });
    assert.ok(!result.graded && result.reason === "ambiguous");
  });
});

describe("outcome", () => {
  const evaluator = { kind: "outcome", outcome_type: "pull_request_merged" } as const;
  const outcome = (correct: boolean, overrides: Partial<OutcomeRecord> = {}): OutcomeRecord => ({
    schema_version: "1.0",
    outcome_id: "outcome-88",
    decision_id: "decision-017",
    outcome_type: "pull_request_merged",
    correct,
    observed_at: "2026-07-27T10:00:00Z",
    ...overrides,
  });

  test("a later real-world result carries reality authority", () => {
    const result = evaluate({
      bundle: bundle({ kind: "artifact_reference", value: "workspace" }),
      manifest: manifest(evaluator, "reality"),
      outcomes: [outcome(true)],
    });
    assertGraded(result, true, "reality");
    assert.ok(result.graded && result.evidenceIds.includes("outcome-88"));
    assert.ok(isVerifiedCorrect(result));
  });

  test("no outcome yet means no grade yet, not a failure", () => {
    const result = evaluate({
      bundle: bundle({ kind: "artifact_reference", value: "workspace" }),
      manifest: manifest(evaluator, "reality"),
      outcomes: [],
    });
    assert.ok(!result.graded && result.reason === "no_ground_truth");
  });

  test("an outcome for another decision is not this decision's evidence", () => {
    const result = evaluate({
      bundle: bundle({ kind: "artifact_reference", value: "workspace" }),
      manifest: manifest(evaluator, "reality"),
      outcomes: [outcome(true, { decision_id: "decision-999" })],
    });
    assert.ok(!result.graded && result.reason === "no_ground_truth");
  });

  test("a later observation overturns an earlier one", () => {
    const result = evaluate({
      bundle: bundle({ kind: "artifact_reference", value: "workspace" }),
      manifest: manifest(evaluator, "reality"),
      outcomes: [
        outcome(true),
        outcome(false, { outcome_id: "outcome-89", observed_at: "2026-07-28T10:00:00Z" }),
      ],
    });
    assertGraded(result, false, "reality");
  });
});

describe("harness success is not authority", () => {
  const claim: EvidenceItem = { evidence_id: "e-claim", kind: "harness_claim", claim: { task_id: "42", success: true } };

  test("a harness claim of success cannot produce a math grade", () => {
    const result = evaluate({
      bundle: bundle({ kind: "absent", reason: "not_captured" }, [claim]),
      manifest: manifest({ kind: "command_exit_code", command: ["npm", "test"], expected_exit_code: 0 }),
    });
    assert.equal(result.graded, false);
    assert.ok(!result.graded && result.reason === "no_ground_truth");
    assert.ok(!result.graded && result.detail.includes("harness claim"));
  });

  test("a claim alongside real evidence changes nothing about the verdict", () => {
    const withClaim = evaluate({
      bundle: bundle({ kind: "absent", reason: "not_captured" }, [
        claim,
        { evidence_id: "e1", kind: "command_result", command_name: "npm test", exit_code: 1 },
      ]),
      manifest: manifest({ kind: "command_exit_code", command: ["npm", "test"], expected_exit_code: 0 }),
    });
    // The harness said success. The exit code said otherwise. The exit code wins.
    assertGraded(withClaim, false, "math");
  });

  test("a claim is not counted as a candidate command result", () => {
    const result = evaluate({
      bundle: bundle({ kind: "absent", reason: "not_captured" }, [
        claim,
        { evidence_id: "e1", kind: "command_result", command_name: "npm test", exit_code: 0 },
      ]),
      manifest: manifest({ kind: "command_exit_code", command: ["npm", "test"], expected_exit_code: 0 }),
    });
    assertGraded(result, true, "math");
  });
});

describe("scope guards", () => {
  test("a manifest for a different decision type does not grade this decision", () => {
    const result = evaluate({
      bundle: bundle({ kind: "inline", value: "42" }),
      manifest: { ...manifest({ kind: "exact_equality", expected: "42" }), decision_type: "tool_choice" },
    });
    assert.ok(!result.graded && result.reason === "ambiguous");
  });

  test("a manifest for a different task does not grade this decision", () => {
    const result = evaluate({
      bundle: bundle({ kind: "inline", value: "42" }),
      manifest: { ...manifest({ kind: "exact_equality", expected: "42" }), task_id: "some-other-task" },
    });
    assert.ok(!result.graded && result.reason === "ambiguous");
  });

  test("only math and reality grades count as verified correct", () => {
    const aiJudge = evaluate({
      bundle: bundle({ kind: "inline", value: "42" }),
      manifest: manifest({ kind: "exact_equality", expected: "42" }, "ai_judge"),
    });
    assertGraded(aiJudge, true, "ai_judge");
    assert.equal(isVerifiedCorrect(aiJudge), false);
  });
});
