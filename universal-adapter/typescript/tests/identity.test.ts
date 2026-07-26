/**
 * Decision identity, replay and conflict. These are the reliability criteria:
 * replaying the same evidence must be idempotent, and two different decisions
 * must never be allowed to share one id.
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { DecisionRegistry, decisionIdentity, deriveDecisionId } from "../src/identity.ts";
import { canonicalize, canonicalNumber } from "../src/canonical.ts";
import type { DecisionEvidenceBundle } from "../src/models.ts";

function bundle(overrides: Partial<DecisionEvidenceBundle> = {}): DecisionEvidenceBundle {
  return {
    schema_version: "1.0",
    decision: {
      decision_type: "task_completion",
      evaluation_name: "repository.tests_pass",
      chosen: { kind: "artifact_reference", value: "workspace-after-agent" },
    },
    subject: { harness: "hermes", run_id: "run-42", agent_id: "coder-1" },
    correlation: { task_id: "repair-auth-017" },
    evidence: [],
    ...overrides,
  };
}

describe("decision id derivation", () => {
  test("is deterministic and stable across identical bundles", () => {
    assert.equal(deriveDecisionId(bundle()), deriveDecisionId(bundle()));
    assert.match(deriveDecisionId(bundle()), /^decision-[0-9a-f]{32}$/);
  });

  test("ignores fields that can change without the decision changing", () => {
    const base = deriveDecisionId(bundle());
    const withMoreEvidence = deriveDecisionId(
      bundle({ evidence: [{ evidence_id: "e1", kind: "harness_claim", claim: { success: true } }] }),
    );
    const withUsage = deriveDecisionId(bundle({ usage_refs: ["usage-1"] }));
    assert.equal(withMoreEvidence, base, "attaching evidence does not make it a different decision");
    assert.equal(withUsage, base);
  });

  test("changes when an identity field changes", () => {
    const base = deriveDecisionId(bundle());
    assert.notEqual(base, deriveDecisionId(bundle({ subject: { harness: "ruflo", run_id: "run-42", agent_id: "coder-1" } })));
    assert.notEqual(
      base,
      deriveDecisionId(
        bundle({
          decision: {
            decision_type: "task_completion",
            evaluation_name: "repository.tests_pass",
            chosen: { kind: "artifact_reference", value: "some-other-workspace" },
          },
        }),
      ),
    );
  });

  test("records whether the id was supplied or derived", () => {
    const supplied = decisionIdentity(
      bundle({
        decision: {
          decision_id: "decision-017",
          decision_type: "task_completion",
          evaluation_name: "repository.tests_pass",
          chosen: { kind: "artifact_reference", value: "workspace-after-agent" },
        },
      }),
    );
    assert.equal(supplied.decisionId, "decision-017");
    assert.equal(supplied.source, "adapter_supplied");
    assert.equal(decisionIdentity(bundle()).source, "derived");
  });
});

describe("replay and conflict", () => {
  test("replaying the same bundle is idempotent", () => {
    const registry = new DecisionRegistry();
    const first = registry.register(bundle());
    const second = registry.register(bundle());
    assert.equal(first.status, "new");
    assert.equal(second.status, "replay");
    assert.ok(second.accepted);
    assert.equal(registry.size, 1);
    assert.equal(first.identity.decisionId, second.identity.decisionId);
  });

  test("a duplicate id whose content differs is rejected", () => {
    const registry = new DecisionRegistry();
    const withId = (chosenValue: string): DecisionEvidenceBundle =>
      bundle({
        decision: {
          decision_id: "decision-017",
          decision_type: "task_completion",
          evaluation_name: "repository.tests_pass",
          chosen: { kind: "inline", value: chosenValue },
        },
      });
    assert.ok(registry.register(withId("answer-a")).accepted);
    const conflict = registry.register(withId("answer-b"));
    assert.equal(conflict.accepted, false);
    assert.equal(conflict.status, "conflict");
    assert.ok(!conflict.accepted && conflict.message.includes("different content digest"));
  });

  test("a supplied id replayed with identical content is still a replay", () => {
    const registry = new DecisionRegistry();
    const supplied = bundle({
      decision: {
        decision_id: "decision-017",
        decision_type: "task_completion",
        evaluation_name: "repository.tests_pass",
        chosen: { kind: "inline", value: "answer-a" },
      },
    });
    registry.register(supplied);
    assert.equal(registry.register(supplied).status, "replay");
  });
});

describe("canonical serialization", () => {
  test("object key order does not change the bytes", () => {
    assert.equal(canonicalize({ b: 1, a: 2 }), canonicalize({ a: 2, b: 1 }));
    assert.equal(canonicalize({ b: 1, a: 2 }), '{"a":2,"b":1}');
  });

  test("array order does change the bytes", () => {
    assert.notEqual(canonicalize([1, 2]), canonicalize([2, 1]));
  });

  test("numbers use the pinned decimal form, never an exponent", () => {
    assert.equal(canonicalNumber(2), "2");
    assert.equal(canonicalNumber(2.0), "2");
    assert.equal(canonicalNumber(0.000003), "0.000003");
    assert.equal(canonicalNumber(-0), "0");
    assert.equal(canonicalNumber(1.5), "1.5");
  });

  test("non-ASCII is escaped the way Python's ensure_ascii writes it", () => {
    assert.equal(canonicalize({ "k": "café" }), '{"k":"caf\\u00e9"}');
  });

  test("null and absent are not interchangeable", () => {
    assert.equal(canonicalize({ a: null }), '{"a":null}');
    assert.equal(canonicalize({ a: undefined }), "{}");
  });
});
