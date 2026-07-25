import type { Decision, RaceRun } from "./domain";

type TotalsView = {
  decisions: number;
  correct: number;
  totalCostUsd: number;
  costPerCorrectUsd: number | null;
};

export type ReplayEvent =
  | { kind: "start"; at: number; totals: TotalsView }
  | { kind: "decision"; at: number; driverId: string; decision: Decision; totals: TotalsView }
  | { kind: "driver-finished"; at: number; driverId: string; totals: TotalsView }
  | { kind: "outcome"; at: number; driverId: string; decision: Decision; onTime: boolean; totals: TotalsView }
  | { kind: "complete"; at: number; totals: TotalsView };

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, label: string): string {
  if (typeof value !== "string" || !value) throw new Error(`${label} must be a non-empty string`);
  return value;
}

function number(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} must be finite`);
  return value;
}

export function parseRaceData(value: unknown): RaceRun {
  const root = record(value, "run");
  if (root.schema_version !== 1) throw new Error("unsupported schema version");
  if (!Array.isArray(root.drivers) || !Array.isArray(root.outcomes)) throw new Error("drivers and outcomes must be arrays");

  const responseIds = new Set<string>();
  const drivers = root.drivers.map((rawDriver, driverIndex) => {
    const driver = record(rawDriver, `driver ${driverIndex}`);
    if (!Array.isArray(driver.decisions) || driver.decisions.length === 0) throw new Error("driver decisions must not be empty");
    return {
      id: string(driver.id, "driver id"),
      model: string(driver.model, "driver model"),
      color: string(driver.color, "driver color"),
      decisions: driver.decisions.map((rawDecision, decisionIndex) => {
        const decision = record(rawDecision, `decision ${decisionIndex}`);
        const response_id = string(decision.response_id, "response id");
        if (responseIds.has(response_id)) throw new Error(`duplicate response ${response_id}`);
        responseIds.add(response_id);
        return {
          junction: string(decision.junction, "junction"),
          stage_index: number(decision.stage_index, "stage index"),
          chosen: string(decision.chosen, "chosen route"),
          true_fastest: string(decision.true_fastest, "true fastest route"),
          correct: Boolean(decision.correct),
          travel_time_min: number(decision.travel_time_min, "travel time"),
          input_tokens: number(decision.input_tokens, "input tokens"),
          output_tokens: number(decision.output_tokens, "output tokens"),
          cost_usd: number(decision.cost_usd, "cost"),
          response_id
        };
      })
    };
  });

  const outcomes = root.outcomes.map((rawOutcome, outcomeIndex) => {
    const outcome = record(rawOutcome, `outcome ${outcomeIndex}`);
    const graded_response_id = string(outcome.graded_response_id, "graded response id");
    if (!responseIds.has(graded_response_id)) throw new Error(`outcome targets unknown response ${graded_response_id}`);
    return {
      driver: string(outcome.driver, "outcome driver"),
      on_time: Boolean(outcome.on_time),
      graded_response_id
    };
  });

  const totals = record(root.totals, "totals");
  const costPerCorrect = totals.cost_per_correct_usd;
  if (costPerCorrect !== null) number(costPerCorrect, "cost per correct");
  return {
    schema_version: 1,
    generated_from: string(root.generated_from, "generated from"),
    drivers,
    outcomes,
    totals: {
      decisions: number(totals.decisions, "total decisions"),
      correct: number(totals.correct, "total correct"),
      total_cost_usd: number(totals.total_cost_usd, "total cost"),
      outcomes: number(totals.outcomes, "total outcomes"),
      cost_per_correct_usd: costPerCorrect as number | null
    }
  };
}

export function resolveOutcomeTargets(run: RaceRun): Map<string, Decision> {
  const byResponse = new Map(run.drivers.flatMap((driver) => driver.decisions.map((decision) => [decision.response_id, decision] as const)));
  return new Map(run.outcomes.map((outcome) => [outcome.driver, byResponse.get(outcome.graded_response_id)!]));
}

function totals(run: RaceRun, decisions: number, correct: number, cost: number): TotalsView {
  return {
    decisions,
    correct,
    totalCostUsd: cost,
    costPerCorrectUsd: correct ? cost / correct : null
  };
}

export function buildTimeline(run: RaceRun): ReplayEvent[] {
  const events: ReplayEvent[] = [{ kind: "start", at: 0, totals: totals(run, 0, 0, 0) }];
  let at = 600;
  let decisionCount = 0;
  let correctCount = 0;
  let cost = 0;
  const maxStages = Math.max(...run.drivers.map((driver) => driver.decisions.length));
  for (let stage = 0; stage < maxStages; stage += 1) {
    for (const driver of run.drivers) {
      const decision = driver.decisions[stage];
      if (!decision) continue;
      decisionCount += 1;
      correctCount += Number(decision.correct);
      cost += decision.cost_usd;
      events.push({ kind: "decision", at, driverId: driver.id, decision, totals: totals(run, decisionCount, correctCount, cost) });
    }
    at += 2500;
  }
  for (const driver of run.drivers) {
    events.push({ kind: "driver-finished", at, driverId: driver.id, totals: totals(run, decisionCount, correctCount, cost) });
  }
  at += 1000;
  const targets = resolveOutcomeTargets(run);
  for (const outcome of run.outcomes) {
    events.push({ kind: "outcome", at, driverId: outcome.driver, decision: targets.get(outcome.driver)!, onTime: outcome.on_time, totals: totals(run, decisionCount, correctCount, cost) });
    at += 450;
  }
  events.push({
    kind: "complete",
    at,
    totals: {
      decisions: run.totals.decisions,
      correct: run.totals.correct,
      totalCostUsd: run.totals.total_cost_usd,
      costPerCorrectUsd: run.totals.cost_per_correct_usd
    }
  });
  return events;
}
