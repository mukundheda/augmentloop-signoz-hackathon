/**
 * Cost attribution. Every test here is really the same test asked in a
 * different way: is the money charged once, and does an unknown stay unknown.
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  attributeUsage,
  comparableAtCoverage,
  costPerCorrect,
  precedenceRank,
  pricingTableId,
} from "../src/costing.ts";
import { canonicalize } from "../src/canonical.ts";
import type { PricingTable, UsageRecord } from "../src/models.ts";

const PRICING: PricingTable = {
  currency: "usd",
  models: {
    "anthropic/claude-haiku-4.5": { input_per_1m_usd: 1, output_per_1m_usd: 5 },
    "anthropic/claude-sonnet-4.6": { input_per_1m_usd: 3, output_per_1m_usd: 15 },
  },
};

const TABLE_ID = pricingTableId(PRICING);

function usage(overrides: Partial<UsageRecord> & Pick<UsageRecord, "usage_id">): UsageRecord {
  return {
    schema_version: "1.0",
    scope: "model_invocation",
    run_id: "run-42",
    cost_provenance: "unknown",
    ...overrides,
  } as UsageRecord;
}

function tokenUsage(id: string, overrides: Partial<UsageRecord> = {}): UsageRecord {
  return usage({
    usage_id: id,
    model: "anthropic/claude-haiku-4.5",
    input_tokens: 1_000_000,
    output_tokens: 1_000_000,
    cost_provenance: "provider_token_estimate",
    pricing_table_id: TABLE_ID,
    decision_ids: ["decision-017"],
    ...overrides,
  });
}

describe("pricing table identity", () => {
  test("has the documented shape", () => {
    assert.match(TABLE_ID, /^gradebook\.pricing@[0-9a-f]{12}$/);
  });

  test("is a function of content, not of key order", () => {
    const reordered: PricingTable = {
      models: {
        "anthropic/claude-sonnet-4.6": { output_per_1m_usd: 15, input_per_1m_usd: 3 },
        "anthropic/claude-haiku-4.5": { output_per_1m_usd: 5, input_per_1m_usd: 1 },
      },
      currency: "usd",
    };
    assert.equal(pricingTableId(reordered), TABLE_ID);
  });

  test("the hashed object carries no version field, because the digest is the version", () => {
    // ADR 0008. A hand-maintained string in here could go stale and let two
    // different rate tables share one id, and Python's PRICES has no version
    // to reproduce it from.
    assert.equal(Object.keys(PRICING).sort().join(","), "currency,models");
  });

  test("changes when a rate changes, so a figure can be traced to its rates", () => {
    const edited: PricingTable = {
      ...PRICING,
      models: { ...PRICING.models, "anthropic/claude-haiku-4.5": { input_per_1m_usd: 2, output_per_1m_usd: 5 } },
    };
    assert.notEqual(pricingTableId(edited), TABLE_ID);
  });

  test("the canonical form of the table is the pinned one", () => {
    // Spelled out so the Python implementation has something exact to match.
    assert.equal(
      canonicalize({ currency: "usd", models: { m: { input_per_1m_usd: 0.000003, output_per_1m_usd: 2 } } }),
      '{"currency":"usd","models":{"m":{"input_per_1m_usd":0.000003,"output_per_1m_usd":2}}}',
    );
  });

  test("rejects a table containing non-ASCII, which the two languages would escape differently", () => {
    assert.throws(
      () => pricingTableId({ ...PRICING, models: { ...PRICING.models, "vendor/modèle": { input_per_1m_usd: 1, output_per_1m_usd: 1 } } }),
      /non-ASCII/,
    );
  });
});

describe("token pricing", () => {
  test("prices a token estimate from the table", () => {
    const result = attributeUsage([tokenUsage("usage-1")], { pricingTable: PRICING, gradedDecisionIds: ["decision-017"] });
    assert.equal(result.charged[0]!.costUsd, 6);
    assert.equal(result.totalKnownCostUsd, 6);
  });

  test("an unpriced model leaves the cost unknown rather than zero", () => {
    const result = attributeUsage([tokenUsage("usage-1", { model: "someone/unknown-model" })], { pricingTable: PRICING });
    assert.equal(result.charged[0]!.costUsd, undefined);
    assert.deepEqual(result.unknownCostUsageIds, ["usage-1"]);
    assert.equal(result.totalKnownCostUsd, 0, "the total of nothing is 0, but no record was charged 0");
    assert.match(result.charged[0]!.note ?? "", /not in the pricing table/);
  });

  test("half the token counts is not half a cost", () => {
    const result = attributeUsage([tokenUsage("usage-1", { output_tokens: null })], { pricingTable: PRICING });
    assert.equal(result.charged[0]!.costUsd, undefined);
  });

  test("rates from a different table are refused", () => {
    const result = attributeUsage([tokenUsage("usage-1", { pricing_table_id: "gradebook.pricing@000000000000" })], {
      pricingTable: PRICING,
    });
    assert.equal(result.charged[0]!.costUsd, undefined);
    assert.match(result.charged[0]!.note ?? "", /different table/);
  });
});

describe("unknown cost stays unknown", () => {
  test("an unknown provenance produces no figure at all", () => {
    const result = attributeUsage([usage({ usage_id: "usage-1", cost_provenance: "unknown", decision_ids: ["decision-017"] })], {
      pricingTable: PRICING,
      gradedDecisionIds: ["decision-017"],
    });
    assert.equal(result.charged[0]!.costUsd, undefined);
    assert.equal(result.costByDecisionId.has("decision-017"), false);
    assert.equal(result.coverage.coverage, 0);
  });
});

describe("deduplication", () => {
  test("the same usage_id is charged once", () => {
    const record = tokenUsage("usage-1");
    const result = attributeUsage([record, record], { pricingTable: PRICING });
    assert.equal(result.charged.length, 1);
    assert.equal(result.totalKnownCostUsd, 6);
    assert.equal(result.suppressed.length, 1);
    assert.equal(result.duplicateConflicts.length, 0, "identical replays are not conflicts");
  });

  test("a duplicate id with different content is reported, and the first still wins", () => {
    const result = attributeUsage([tokenUsage("usage-1"), tokenUsage("usage-1", { input_tokens: 9_000_000 })], {
      pricingTable: PRICING,
    });
    assert.equal(result.totalKnownCostUsd, 6);
    assert.equal(result.duplicateConflicts.length, 1);
  });

  test("an explicit container is charged and the records it contains are not", () => {
    const parent = tokenUsage("usage-parent", {
      scope: "agent",
      agent_id: "lead",
      contains_usage_ids: ["usage-child-1", "usage-child-2"],
      input_tokens: 2_000_000,
      output_tokens: 2_000_000,
    });
    const children = [
      tokenUsage("usage-child-1", { agent_id: "worker-1", parent_agent_id: "lead" }),
      tokenUsage("usage-child-2", { agent_id: "worker-2", parent_agent_id: "lead" }),
    ];
    const result = attributeUsage([parent, ...children], { pricingTable: PRICING });
    assert.equal(result.totalKnownCostUsd, 12, "the parent total, not the parent plus its children");
    assert.deepEqual(
      result.suppressed.map((s) => s.usageId).sort(),
      ["usage-child-1", "usage-child-2"],
    );
  });

  test("an agent aggregate that overlaps its own calls is dropped in favour of the calls", () => {
    const aggregate = tokenUsage("usage-agent", { scope: "agent", agent_id: "coder-1" });
    const calls = [
      tokenUsage("usage-call-1", { agent_id: "coder-1", input_tokens: 500_000, output_tokens: 0 }),
      tokenUsage("usage-call-2", { agent_id: "coder-1", input_tokens: 500_000, output_tokens: 0 }),
    ];
    const result = attributeUsage([aggregate, ...calls], { pricingTable: PRICING });
    assert.equal(result.totalKnownCostUsd, 1);
    assert.ok(result.suppressed.some((s) => s.usageId === "usage-agent"));
  });

  test("a parent aggregate that overlaps a child's calls is dropped too", () => {
    const parent = tokenUsage("usage-parent", { scope: "agent", agent_id: "lead" });
    const child = tokenUsage("usage-child", { agent_id: "worker", parent_agent_id: "lead", input_tokens: 0, output_tokens: 200_000 });
    const result = attributeUsage([parent, child], { pricingTable: PRICING });
    assert.equal(result.totalKnownCostUsd, 1);
    assert.ok(result.suppressed.some((s) => s.usageId === "usage-parent"));
  });
});

describe("provider cost precedence", () => {
  test("a provider figure wins over a token estimate of the same call", () => {
    const estimate = tokenUsage("usage-estimate", { provider_response_id: "response-abc" });
    const reported = usage({
      usage_id: "usage-reported",
      provider_response_id: "response-abc",
      provider_cost_usd: 4.2,
      cost_provenance: "provider_reported",
      decision_ids: ["decision-017"],
    });
    const result = attributeUsage([estimate, reported], { pricingTable: PRICING, gradedDecisionIds: ["decision-017"] });
    assert.equal(result.totalKnownCostUsd, 4.2);
    assert.ok(result.suppressed.some((s) => s.usageId === "usage-estimate"));
  });

  test("the precedence order is the documented one, strongest first", () => {
    assert.deepEqual(
      (["unknown", "provider_reported", "run_aggregate", "harness_token_estimate", "provider_token_estimate"] as const)
        .slice()
        .sort((a, b) => precedenceRank(a) - precedenceRank(b)),
      ["provider_reported", "provider_token_estimate", "harness_token_estimate", "run_aggregate", "unknown"],
    );
  });

  test("a harness estimate loses to a provider estimate of the same response", () => {
    const provider = tokenUsage("usage-provider", { provider_response_id: "response-abc" });
    const harness = tokenUsage("usage-harness", {
      provider_response_id: "response-abc",
      cost_provenance: "harness_token_estimate",
      input_tokens: 9_000_000,
      output_tokens: 9_000_000,
    });
    const result = attributeUsage([harness, provider], { pricingTable: PRICING });
    assert.equal(result.totalKnownCostUsd, 6);
  });
});

describe("run level cost", () => {
  const runAggregate = usage({
    usage_id: "usage-run",
    scope: "run",
    cost_provenance: "run_aggregate",
    provider_cost_usd: 9,
  });

  test("is attached once, to the terminal decision, when it is all there is", () => {
    const result = attributeUsage([runAggregate], {
      pricingTable: PRICING,
      gradedDecisionIds: ["decision-001", "decision-terminal"],
    });
    assert.equal(result.totalKnownCostUsd, 9);
    assert.deepEqual([...result.costByDecisionId.entries()], [["decision-terminal", 9]]);
  });

  test("is not copied onto every decision", () => {
    const result = attributeUsage([runAggregate], {
      pricingTable: PRICING,
      gradedDecisionIds: ["a", "b", "c"],
      terminalDecisionId: "c",
    });
    assert.equal(result.costByDecisionId.size, 1);
    assert.equal(result.coverage.gradedDecisionsWithCost, 1);
  });

  test("is dropped when narrower records already carry the cost", () => {
    const result = attributeUsage([runAggregate, tokenUsage("usage-call")], {
      pricingTable: PRICING,
      gradedDecisionIds: ["decision-017"],
    });
    assert.equal(result.totalKnownCostUsd, 6, "the calls, not the calls plus the run total");
    assert.ok(result.suppressed.some((s) => s.usageId === "usage-run"));
  });

  test("survives when the narrower records exist but have no cost at all", () => {
    const unpriced = usage({ usage_id: "usage-call", cost_provenance: "unknown", decision_ids: ["decision-017"] });
    const result = attributeUsage([runAggregate, unpriced], {
      pricingTable: PRICING,
      gradedDecisionIds: ["decision-017"],
    });
    assert.equal(result.totalKnownCostUsd, 9, "suppressing it would discard the only figure available");
  });
});

describe("cost coverage", () => {
  test("is the graded decisions with cost over all graded decisions", () => {
    const result = attributeUsage([tokenUsage("usage-1", { decision_ids: ["decision-a"] })], {
      pricingTable: PRICING,
      gradedDecisionIds: ["decision-a", "decision-b", "decision-c", "decision-d"],
    });
    assert.equal(result.coverage.gradedDecisions, 4);
    assert.equal(result.coverage.gradedDecisionsWithCost, 1);
    assert.equal(result.coverage.coverage, 0.25);
  });

  test("is undefined rather than zero when nothing was graded", () => {
    const result = attributeUsage([tokenUsage("usage-1")], { pricingTable: PRICING });
    assert.equal(result.coverage.coverage, undefined);
  });

  test("usage attributable to no decision lowers coverage instead of vanishing", () => {
    const result = attributeUsage([tokenUsage("usage-1", { decision_ids: [] })], {
      pricingTable: PRICING,
      gradedDecisionIds: ["decision-a"],
    });
    assert.equal(result.totalKnownCostUsd, 6, "the money was still spent");
    assert.equal(result.coverage.coverage, 0);
  });

  test("a call shared by two decisions is split, so per-decision costs do not exceed what was spent", () => {
    const result = attributeUsage([tokenUsage("usage-1", { decision_ids: ["decision-a", "decision-b"] })], {
      pricingTable: PRICING,
      gradedDecisionIds: ["decision-a", "decision-b"],
    });
    assert.equal(result.costByDecisionId.get("decision-a"), 3);
    assert.equal(result.costByDecisionId.get("decision-b"), 3);
    assert.equal(result.coverage.coverage, 1);
  });

  test("comparison requires an explicit minimum coverage, with no default", () => {
    const good = { gradedDecisions: 10, gradedDecisionsWithCost: 9, coverage: 0.9 };
    const poor = { gradedDecisions: 10, gradedDecisionsWithCost: 3, coverage: 0.3 };
    assert.equal(comparableAtCoverage(good, good, 0.8).comparable, true);
    assert.equal(comparableAtCoverage(good, poor, 0.8).comparable, false);
    assert.match(comparableAtCoverage(good, poor, 0.8).reason, /below the caller's minimum/);
    // The same pair is comparable at a minimum the caller is willing to accept.
    assert.equal(comparableAtCoverage(good, poor, 0.25).comparable, true);
    assert.equal(comparableAtCoverage(good, { gradedDecisions: 0, gradedDecisionsWithCost: 0 }, 0).comparable, false);
  });
});

describe("cost per correct", () => {
  test("keeps failed attempts in the numerator", () => {
    // Three attempts, one of them verified correct. The wrong tries were paid for.
    const attempts = ["a", "b", "c"].map((suffix) => tokenUsage(`usage-${suffix}`, { decision_ids: [`decision-${suffix}`] }));
    const result = attributeUsage(attempts, {
      pricingTable: PRICING,
      gradedDecisionIds: ["decision-a", "decision-b", "decision-c"],
    });
    assert.equal(result.totalKnownCostUsd, 18);
    assert.equal(costPerCorrect(result.totalKnownCostUsd, 1), 18);
  });

  test("is undefined when nothing was verified correct, never a number that reads as free", () => {
    assert.equal(costPerCorrect(18, 0), undefined);
  });
});
