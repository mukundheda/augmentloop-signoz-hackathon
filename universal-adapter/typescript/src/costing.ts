/**
 * Usage attribution and cost.
 *
 * The rule the whole module exists to protect: a missing cost stays missing.
 * Never zero. Zero is a measurement, absence is an admission, and a fabricated
 * zero in the numerator of "cost per correct decision" makes the headline
 * number look better the less it knows, which is the exact failure mode this
 * protocol is meant to make impossible.
 *
 * The second rule: the same consumption is charged exactly once. Multi-agent
 * runs report the same model calls at several levels (per call, per agent, per
 * run), and adding those levels together inflates cost silently. Deduplication
 * here is deterministic and, wherever the data allows, EXPLICIT: a record that
 * declares contains_usage_ids removes the guesswork entirely.
 *
 * Cost coverage is REPORTED, never thresholded (design decision D3). Deciding
 * that 80 percent coverage is good enough to compare two harnesses is a policy
 * question belonging to whoever is doing the comparing, so the only helper that
 * applies a threshold takes it as an explicit argument with no default.
 */

import { canonicalize, sha256Hex } from "./canonical.ts";
import { COST_PROVENANCE_PRECEDENCE } from "./models.ts";
import type { CostProvenance, PricingTable, UsageRecord } from "./models.ts";

/**
 * Identity of a pricing table (ADR 0008).
 *
 * Format: "gradebook.pricing@" + the first 12 hex characters of the sha256 over
 * the table's canonical serialization (see canonical.ts for the exact form).
 * Twelve characters is enough to distinguish rate cards while staying readable
 * inside a telemetry attribute, and hashing the CONTENT rather than trusting a
 * hand-written version string means a table edited in place cannot keep
 * claiming to be the table that produced yesterday's figures.
 *
 * The hashed object is exactly, with no version field anywhere in it:
 *
 *   {"currency":"usd","models":{"<slug>":{"input_per_1m_usd":<n>,"output_per_1m_usd":<n>}}}
 *
 * The digest is the version. Anything hand-maintained inside the hash would
 * reintroduce the stale-identifier failure the digest was chosen to remove, and
 * could not be reproduced from Python's gradebook.pricing.PRICES, which carries
 * no version of its own.
 */
export function pricingTableId(table: PricingTable): string {
  assertAsciiOnly(table);
  return "gradebook.pricing@" + sha256Hex(canonicalize(table)).slice(0, 12);
}

/**
 * Non-ASCII would force a choice about escaping that the two languages spell
 * differently by default, so it is rejected outright rather than risking two
 * implementations deriving two different ids for the same table.
 */
function assertAsciiOnly(table: PricingTable): void {
  const scan = (value: unknown, path: string): void => {
    if (typeof value === "string") {
      if (/[^\x20-\x7e]/.test(value)) {
        throw new Error(`pricing table ${path} contains non-ASCII characters, which are not permitted in a table id`);
      }
      return;
    }
    if (value && typeof value === "object") {
      for (const [key, sub] of Object.entries(value as Record<string, unknown>)) {
        scan(key, `${path}.${key}`);
        scan(sub, `${path}.${key}`);
      }
    }
  };
  scan(table, "table");
}

export function precedenceRank(provenance: CostProvenance): number {
  return COST_PROVENANCE_PRECEDENCE.indexOf(provenance);
}

export interface CostingOptions {
  pricingTable?: PricingTable;
  /** Decision ids that received a grade. Coverage is measured over these. */
  gradedDecisionIds?: readonly string[];
  /**
   * Where a run-level aggregate is attached when it is the only cost available.
   * When omitted, the LAST entry of gradedDecisionIds is used, on the
   * convention that a caller lists decisions in run order and the terminal task
   * decision is therefore last.
   */
  terminalDecisionId?: string;
}

export interface ChargedUsage {
  usageId: string;
  /** Undefined means unknown. It is never silently turned into 0. */
  costUsd?: number;
  provenance: CostProvenance;
  decisionIds: string[];
  note?: string;
}

export interface SuppressedUsage {
  usageId: string;
  reason: string;
}

export interface CostCoverage {
  gradedDecisions: number;
  gradedDecisionsWithCost: number;
  /** Undefined when there are no graded decisions: 0/0 is not 0 percent. */
  coverage?: number;
}

export interface CostAttribution {
  charged: ChargedUsage[];
  suppressed: SuppressedUsage[];
  /** usage_ids seen more than once with differing content. */
  duplicateConflicts: { usageId: string; message: string }[];
  /** Sum of the KNOWN charged costs. Records with unknown cost are excluded. */
  totalKnownCostUsd: number;
  /** usage_ids whose cost could not be determined. */
  unknownCostUsageIds: string[];
  costByDecisionId: Map<string, number>;
  coverage: CostCoverage;
}

function costOf(
  record: UsageRecord,
  pricingTable: PricingTable | undefined,
  pricingId: string | undefined,
): { costUsd?: number; note?: string } {
  const provider = record.provider_cost_usd;
  if (record.cost_provenance === "provider_reported") {
    return typeof provider === "number"
      ? { costUsd: provider }
      : { note: "provider_reported provenance without a provider figure" };
  }
  if (record.cost_provenance === "unknown") {
    return { note: "cost_provenance is unknown" };
  }
  if (record.cost_provenance === "run_aggregate") {
    if (typeof provider === "number") return { costUsd: provider };
    return estimateFromTokens(record, pricingTable, pricingId);
  }
  // Token estimates. A provider figure, if one somehow arrived alongside, still
  // outranks the estimate: it is the only source reflecting the real contract.
  if (typeof provider === "number") {
    return { costUsd: provider, note: "provider figure used in preference to the token estimate" };
  }
  return estimateFromTokens(record, pricingTable, pricingId);
}

function estimateFromTokens(
  record: UsageRecord,
  pricingTable: PricingTable | undefined,
  pricingId: string | undefined,
): { costUsd?: number; note?: string } {
  if (!pricingTable) return { note: "no pricing table supplied, so a token estimate cannot be priced" };
  if (record.pricing_table_id && pricingId && record.pricing_table_id !== pricingId) {
    return {
      note: `record was priced with ${record.pricing_table_id} but ${pricingId} was supplied; rates from a different table must not be applied`,
    };
  }
  const model = record.model;
  if (!model) return { note: "model is unknown, so no rate applies" };
  const entry = pricingTable.models[model];
  if (!entry) return { note: `model ${model} is not in the pricing table` };
  const input = record.input_tokens;
  const output = record.output_tokens;
  if (typeof input !== "number" || typeof output !== "number") {
    // One reported count and one null is not a partial cost, it is no cost.
    return { note: "token counts are incomplete, so the cost stays unknown rather than becoming partial" };
  }
  const cost = (input / 1_000_000) * entry.input_per_1m_usd + (output / 1_000_000) * entry.output_per_1m_usd;
  return { costUsd: cost };
}

/**
 * Deduplicate, suppress overlapping aggregates, price what can be priced and
 * attribute the result to decisions.
 */
export function attributeUsage(
  records: readonly UsageRecord[],
  options: CostingOptions = {},
): CostAttribution {
  const pricingId = options.pricingTable ? pricingTableId(options.pricingTable) : undefined;
  const suppressed: SuppressedUsage[] = [];
  const duplicateConflicts: { usageId: string; message: string }[] = [];

  // 1. The same usage_id is the SAME consumption. First occurrence wins; a
  //    later one that disagrees is reported rather than quietly overwriting.
  const deduped = new Map<string, UsageRecord>();
  for (const record of records) {
    const existing = deduped.get(record.usage_id);
    if (!existing) {
      deduped.set(record.usage_id, record);
      continue;
    }
    suppressed.push({ usageId: record.usage_id, reason: "duplicate usage_id, already charged once" });
    if (canonicalize(existing) !== canonicalize(record)) {
      duplicateConflicts.push({
        usageId: record.usage_id,
        message: `usage_id ${JSON.stringify(record.usage_id)} was seen twice with different content; the first occurrence was charged`,
      });
    }
  }

  const suppressedIds = new Set<string>();
  const suppress = (usageId: string, reason: string): void => {
    if (suppressedIds.has(usageId)) return;
    suppressedIds.add(usageId);
    suppressed.push({ usageId, reason });
  };

  // 2. Explicit containment. A record that declares it already includes others
  //    is charged, and the ones it names are not. No guesswork.
  for (const record of deduped.values()) {
    for (const contained of record.contains_usage_ids ?? []) {
      if (deduped.has(contained)) {
        suppress(contained, `already included in the totals of ${record.usage_id}`);
      }
    }
  }

  const priced = new Map<string, { costUsd?: number; note?: string }>();
  for (const record of deduped.values()) {
    priced.set(record.usage_id, costOf(record, options.pricingTable, pricingId));
  }
  const hasKnownCost = (record: UsageRecord): boolean =>
    !suppressedIds.has(record.usage_id) && priced.get(record.usage_id)?.costUsd !== undefined;

  const live = (): UsageRecord[] => [...deduped.values()].filter((r) => !suppressedIds.has(r.usage_id));

  // 3. An agent aggregate that overlaps narrower records from the same agent,
  //    or a parent aggregate that overlaps its children, is dropped in favour
  //    of the narrower figures. The narrower records are the more precise
  //    measurement, so keeping the aggregate as well would double count.
  for (const record of live()) {
    if (record.scope !== "agent") continue;
    const agent = record.agent_id;
    if (!agent) continue;
    const overlapping = live().some(
      (other) =>
        other.usage_id !== record.usage_id &&
        other.run_id === record.run_id &&
        (other.scope === "model_invocation" || other.scope === "decision") &&
        (other.agent_id === agent || other.parent_agent_id === agent) &&
        hasKnownCost(other),
    );
    if (overlapping) {
      suppress(
        record.usage_id,
        `agent-scoped aggregate for ${agent} overlaps narrower records from the same agent or its children`,
      );
    }
  }

  // 4. A run aggregate covers everything inside it. It is charged ONLY when
  //    nothing narrower carries a cost; otherwise it would be added on top of
  //    the calls it already contains.
  for (const record of live()) {
    if (record.scope !== "run") continue;
    const narrower = live().some(
      (other) => other.usage_id !== record.usage_id && other.run_id === record.run_id && other.scope !== "run" && hasKnownCost(other),
    );
    if (narrower) {
      suppress(
        record.usage_id,
        `run-scoped aggregate for ${record.run_id} already contains the narrower records that carry cost`,
      );
    }
  }

  // 5. Provider precedence. Several records may describe one provider response
  //    at different confidence levels; the strongest provenance wins and the
  //    rest are dropped rather than summed.
  const byResponse = new Map<string, UsageRecord[]>();
  for (const record of live()) {
    const responseId = record.provider_response_id;
    if (!responseId) continue;
    // A NUL separator so a run_id containing the delimiter cannot collide.
    const key = `${record.run_id}\u0000${responseId}`;
    const group = byResponse.get(key);
    if (group) group.push(record);
    else byResponse.set(key, [record]);
  }
  for (const group of byResponse.values()) {
    if (group.length < 2) continue;
    const sorted = [...group].sort((a, b) => {
      const rank = precedenceRank(a.cost_provenance) - precedenceRank(b.cost_provenance);
      return rank !== 0 ? rank : a.usage_id.localeCompare(b.usage_id);
    });
    const winner = sorted[0] as UsageRecord;
    for (const loser of sorted.slice(1)) {
      suppress(
        loser.usage_id,
        `same provider response as ${winner.usage_id}, whose ${winner.cost_provenance} cost outranks ${loser.cost_provenance}`,
      );
    }
  }

  // 6. Charge what survived, and attribute it.
  const charged: ChargedUsage[] = [];
  const unknownCostUsageIds: string[] = [];
  const costByDecisionId = new Map<string, number>();
  let totalKnownCostUsd = 0;
  let runAggregateAssigned = false;

  const gradedIds = options.gradedDecisionIds ?? [];
  const terminalDecisionId =
    options.terminalDecisionId ?? (gradedIds.length > 0 ? gradedIds[gradedIds.length - 1] : undefined);

  const addToDecision = (decisionId: string, amount: number): void => {
    costByDecisionId.set(decisionId, (costByDecisionId.get(decisionId) ?? 0) + amount);
  };

  for (const record of live()) {
    const pricing = priced.get(record.usage_id) ?? {};
    const decisionIds = record.decision_ids ?? [];
    charged.push({
      usageId: record.usage_id,
      ...(pricing.costUsd === undefined ? {} : { costUsd: pricing.costUsd }),
      provenance: record.cost_provenance,
      decisionIds,
      ...(pricing.note === undefined ? {} : { note: pricing.note }),
    });
    if (pricing.costUsd === undefined) {
      unknownCostUsageIds.push(record.usage_id);
      continue;
    }
    totalKnownCostUsd += pricing.costUsd;

    if (record.scope === "run") {
      // Assigned once, to one terminal decision, never copied across the run.
      if (runAggregateAssigned) continue;
      const target = decisionIds.length === 1 ? decisionIds[0] : terminalDecisionId;
      if (target) {
        addToDecision(target, pricing.costUsd);
        runAggregateAssigned = true;
      }
      continue;
    }

    if (decisionIds.length === 0) continue; // real cost, not yet attributable
    // A call referenced by several decisions is split evenly. Splitting keeps
    // the per-decision figures from summing to more than was actually spent.
    const share = pricing.costUsd / decisionIds.length;
    for (const decisionId of decisionIds) addToDecision(decisionId, share);
  }

  const withCost = gradedIds.filter((id) => costByDecisionId.has(id)).length;
  const coverage: CostCoverage = {
    gradedDecisions: gradedIds.length,
    gradedDecisionsWithCost: withCost,
    ...(gradedIds.length === 0 ? {} : { coverage: withCost / gradedIds.length }),
  };

  return {
    charged,
    suppressed,
    duplicateConflicts,
    totalKnownCostUsd,
    unknownCostUsageIds,
    costByDecisionId,
    coverage,
  };
}

/**
 * Cost per verified correct decision.
 *
 * The numerator is the attributable cost of ALL evaluated attempts, including
 * the ones that were wrong: an agent that gets there on the fourth try spent
 * four tries. Undefined when nothing was verified correct, because dividing by
 * zero correct decisions produces a number that reads as "free".
 */
export function costPerCorrect(
  totalAttributableCostUsd: number,
  verifiedCorrectCount: number,
): number | undefined {
  if (verifiedCorrectCount <= 0) return undefined;
  return totalAttributableCostUsd / verifiedCorrectCount;
}

export interface ComparabilityVerdict {
  comparable: boolean;
  reason: string;
}

/**
 * Whether two cost figures may honestly be compared.
 *
 * minCoverage is REQUIRED and has no default (design decision D3). The library
 * reports coverage; it does not decide how much of it is enough. Baking in a
 * default would silently make that policy call on every caller's behalf.
 */
export function comparableAtCoverage(
  left: CostCoverage,
  right: CostCoverage,
  minCoverage: number,
): ComparabilityVerdict {
  if (!Number.isFinite(minCoverage) || minCoverage < 0 || minCoverage > 1) {
    return { comparable: false, reason: `minCoverage must be a fraction between 0 and 1, got ${minCoverage}` };
  }
  for (const [label, side] of [["left", left], ["right", right]] as const) {
    if (side.coverage === undefined) {
      return { comparable: false, reason: `${label} cohort has no graded decisions, so its coverage is undefined` };
    }
    if (side.coverage < minCoverage) {
      return {
        comparable: false,
        reason: `${label} cohort coverage ${side.coverage.toFixed(4)} is below the caller's minimum ${minCoverage}`,
      };
    }
  }
  return { comparable: true, reason: `both cohorts meet the caller's minimum coverage of ${minCoverage}` };
}
