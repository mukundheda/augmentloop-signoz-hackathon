/**
 * Emission, checked against the repository's existing language-neutral
 * conformance checker rather than against our own idea of the contract. The
 * checker was written to judge an emitter it did not write, which is exactly
 * the property being used here.
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { buildEvaluationEvent, buildOtlpTracePayload, toConformanceJson, EVENT_NAME } from "../src/emission.ts";
import { evaluate } from "../src/evaluation.ts";
import type { DecisionEvidenceBundle, EvaluationManifest } from "../src/models.ts";

const CHECKER = resolve(import.meta.dirname, "..", "..", "..", "conformance", "check_conformance.py");

const bundle: DecisionEvidenceBundle = {
  schema_version: "1.0",
  decision: {
    decision_id: "decision-017",
    decision_type: "task_completion",
    evaluation_name: "repository.tests_pass",
    chosen: { kind: "artifact_reference", value: "workspace-after-agent" },
  },
  subject: { harness: "hermes", run_id: "run-42", model: "anthropic/claude-sonnet-4.6" },
  correlation: { provider_response_id: "response-abc", task_id: "repair-auth-017" },
  evidence: [{ evidence_id: "evidence-tests-1", kind: "command_result", command_name: "npm test", exit_code: 0 }],
};

const manifest: EvaluationManifest = {
  schema_version: "1.0",
  task_id: "repair-auth-017",
  decision_type: "task_completion",
  evaluation_name: "repository.tests_pass",
  authority: "math",
  evaluator: { kind: "command_exit_code", command: ["npm", "test"], expected_exit_code: 0 },
};

function gradeOf(input: DecisionEvidenceBundle = bundle) {
  const result = evaluate({ bundle: input, manifest });
  assert.ok(result.graded);
  return result;
}

/** The interpreter that runs the checker, or undefined if there is none. */
function pythonCommand(): string | undefined {
  for (const candidate of ["python", "python3", "py"]) {
    const probe = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    if (probe.status === 0) return candidate;
  }
  return undefined;
}

describe("evaluation event", () => {
  test("carries the standard fields and the two mandatory extensions", () => {
    const event = buildEvaluationEvent({ bundle, result: gradeOf(), costUsd: 0.00021 });
    assert.equal(event.name, EVENT_NAME);
    assert.equal(event.attributes["gen_ai.evaluation.name"], "repository.tests_pass");
    assert.equal(event.attributes["gen_ai.evaluation.score.value"], 1);
    assert.equal(event.attributes["gen_ai.evaluation.score.label"], "correct");
    assert.equal(event.attributes["augmentloop.grade.source"], "math");
    assert.equal(event.attributes["augmentloop.cost.usd"], 0.00021);
    assert.equal(event.attributes["gen_ai.response.id"], "response-abc");
    assert.equal(event.attributes["augmentloop.decision.type"], "task_completion");
    assert.equal(event.attributes["augmentloop.grade.reason"], "match");
  });

  test("omits cost entirely when it is unknown, rather than emitting zero", () => {
    const event = buildEvaluationEvent({ bundle, result: gradeOf() });
    assert.equal("augmentloop.cost.usd" in event.attributes, false);
  });

  test("an incorrect grade is encoded as 0.0 and incorrect", () => {
    const failing: DecisionEvidenceBundle = {
      ...bundle,
      evidence: [{ evidence_id: "evidence-tests-1", kind: "command_result", command_name: "npm test", exit_code: 1 }],
    };
    const event = buildEvaluationEvent({ bundle: failing, result: gradeOf(failing) });
    assert.equal(event.attributes["gen_ai.evaluation.score.value"], 0);
    assert.equal(event.attributes["gen_ai.evaluation.score.label"], "incorrect");
  });

  test("carries no payload out of the bundle, only identifiers and the verdict", () => {
    const sensitive: DecisionEvidenceBundle = {
      ...bundle,
      decision: { ...bundle.decision, chosen: { kind: "inline", value: "PATCH WITH A SECRET INSIDE" } },
      metadata: { environment: "benchmark", ticket: "high-cardinality-value" },
    };
    const event = buildEvaluationEvent({ bundle: sensitive, result: gradeOf() });
    const serialized = JSON.stringify(event);
    assert.ok(!serialized.includes("SECRET"), "the chosen payload must not reach telemetry");
    assert.ok(!serialized.includes("high-cardinality-value"), "metadata must not be copied into attributes");
  });

  test("builds the OTLP/HTTP JSON body in the shape the collector accepts", () => {
    const payload = buildOtlpTracePayload(buildEvaluationEvent({ bundle, result: gradeOf() }), {
      traceId: "0".repeat(32),
      spanId: "0".repeat(16),
      timestampMs: 1_700_000_000_000,
    }) as Record<string, [Record<string, [Record<string, [Record<string, unknown>]>]>]>;
    const span = payload["resourceSpans"]![0]!["scopeSpans"]![0]!["spans"]![0]!;
    assert.equal(span["name"], EVENT_NAME);
    assert.equal(span["startTimeUnixNano"], "1700000000000000000");
    const attributes = span["attributes"] as { key: string; value: Record<string, unknown> }[];
    const source = attributes.find((a) => a.key === "augmentloop.grade.source");
    assert.deepEqual(source?.value, { stringValue: "math" });
  });
});

describe("the repository's conformance checker", () => {
  const python = pythonCommand();
  const skip = !python
    ? "no python interpreter on PATH"
    : !existsSync(CHECKER)
      ? `checker not found at ${CHECKER}`
      : false;

  test("accepts our emitted event", { skip }, () => {
    const event = buildEvaluationEvent({ bundle, result: gradeOf(), costUsd: 0.00021 });
    const run = spawnSync(python as string, [CHECKER, "-"], {
      input: toConformanceJson(event) + "\n",
      encoding: "utf8",
    });
    assert.equal(run.status, 0, `checker rejected the event:\n${run.stderr}`);
    assert.match(run.stderr, /CONFORMS/);
  });

  test("accepts a reality grade too", { skip }, () => {
    const realityBundle: DecisionEvidenceBundle = { ...bundle, evidence: [] };
    const result = evaluate({
      bundle: realityBundle,
      manifest: { ...manifest, authority: "reality", evaluator: { kind: "outcome", outcome_type: "pull_request_merged" } },
      outcomes: [
        {
          schema_version: "1.0",
          outcome_id: "outcome-88",
          decision_id: "decision-017",
          outcome_type: "pull_request_merged",
          correct: true,
          observed_at: "2026-07-27T10:00:00Z",
        },
      ],
    });
    assert.ok(result.graded);
    const run = spawnSync(python as string, [CHECKER, "-"], {
      input: toConformanceJson(buildEvaluationEvent({ bundle: realityBundle, result })) + "\n",
      encoding: "utf8",
    });
    assert.equal(run.status, 0, `checker rejected the reality grade:\n${run.stderr}`);
  });
});
