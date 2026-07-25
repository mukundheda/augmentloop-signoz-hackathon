import type {
  AgentDecision,
  Coordinate,
  DecisionType,
  Difficulty,
  RaceRun
} from "./domain";

export interface ReplayWave {
  index: number;
  agents: AgentDecision[];
}

const asRecord = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
};

const asString = (value: unknown, label: string): string => {
  if (typeof value !== "string" || !value) throw new Error(`${label} must be a string`);
  return value;
};

const asNumber = (value: unknown, label: string): number => {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} must be finite`);
  return value;
};

const asCoordinate = (value: unknown, label: string): Coordinate => {
  if (!Array.isArray(value) || value.length !== 2) throw new Error(`${label} must be [lon,lat]`);
  return [asNumber(value[0], label), asNumber(value[1], label)];
};

const DECISION_TYPES = new Set(["route_choice", "eta_estimate", "next_hop"]);
const DIFFICULTIES = new Set(["easy", "medium", "hard"]);

export function parseRaceData(value: unknown): RaceRun {
  const root = asRecord(value, "run");
  if (root.schema_version !== 2) throw new Error("unsupported schema version");
  if (!Array.isArray(root.agents) || !Array.isArray(root.outcomes)) {
    throw new Error("agents and outcomes must be arrays");
  }
  const seen = new Set<string>();
  const agents = root.agents.map((rawAgent, index): AgentDecision => {
    const agent = asRecord(rawAgent, `agent ${index}`);
    const responseId = asString(agent.response_id, "response id");
    if (seen.has(responseId)) throw new Error(`duplicate response ${responseId}`);
    seen.add(responseId);
    const decisionType = asString(agent.decision_type, "decision type");
    const difficulty = asString(agent.difficulty, "difficulty");
    if (!DECISION_TYPES.has(decisionType)) throw new Error(`unknown decision type ${decisionType}`);
    if (!DIFFICULTIES.has(difficulty)) throw new Error(`unknown difficulty ${difficulty}`);
    if (!Array.isArray(agent.chosen_polyline) || agent.chosen_polyline.length < 1) {
      throw new Error("chosen polyline must not be empty");
    }
    if (!Array.isArray(agent.correct_polyline) || agent.correct_polyline.length < 1) {
      throw new Error("correct polyline must not be empty");
    }
    return {
      agent_id: asString(agent.agent_id, "agent id"),
      response_id: responseId,
      model: asString(agent.model, "model"),
      color: asString(agent.color, "color"),
      decision_type: decisionType as DecisionType,
      difficulty: difficulty as Difficulty,
      query_id: asString(agent.query_id, "query id"),
      start: asString(agent.start, "start"),
      destination: asString(agent.destination, "destination"),
      chosen: agent.chosen as string | number,
      correct_answer: agent.correct_answer as string | number,
      is_correct: Boolean(agent.is_correct),
      chosen_path: (agent.chosen_path as unknown[]).map((item) => asString(item, "chosen path node")),
      correct_path: (agent.correct_path as unknown[]).map((item) => asString(item, "correct path node")),
      chosen_polyline: agent.chosen_polyline.map((item, point) => asCoordinate(item, `chosen point ${point}`)),
      correct_polyline: agent.correct_polyline.map((item, point) => asCoordinate(item, `correct point ${point}`)),
      cost_usd: asNumber(agent.cost_usd, "cost"),
      input_tokens: asNumber(agent.input_tokens, "input tokens"),
      output_tokens: asNumber(agent.output_tokens, "output tokens"),
      outcome: agent.outcome as AgentDecision["outcome"]
    };
  });
  const totals = asRecord(root.totals, "totals");
  const byType = asRecord(totals.by_type, "by type") as RaceRun["totals"]["by_type"];
  const byModel = asRecord(totals.by_model, "by model") as Record<string, number>;
  return {
    schema_version: 2,
    generated_from: asString(root.generated_from, "generated from"),
    agents,
    outcomes: root.outcomes as RaceRun["outcomes"],
    totals: {
      decisions: asNumber(totals.decisions, "decisions"),
      correct: asNumber(totals.correct, "correct"),
      total_cost_usd: asNumber(totals.total_cost_usd, "total cost"),
      outcomes: asNumber(totals.outcomes, "outcomes"),
      cost_per_correct_usd: totals.cost_per_correct_usd === null
        ? null
        : asNumber(totals.cost_per_correct_usd, "cost per correct"),
      by_type: byType,
      by_model: byModel
    }
  };
}

export function buildWaves(run: RaceRun, size = 24): ReplayWave[] {
  if (!Number.isInteger(size) || size < 1) throw new Error("wave size must be positive");
  const waves: ReplayWave[] = [];
  for (let offset = 0; offset < run.agents.length; offset += size) {
    waves.push({ index: waves.length, agents: run.agents.slice(offset, offset + size) });
  }
  return waves;
}

export function samplePolyline(points: Coordinate[], progress: number): Coordinate {
  if (points.length === 0) throw new Error("cannot sample an empty polyline");
  if (points.length === 1) return [...points[0]];
  const clamped = Math.max(0, Math.min(1, progress));
  const lengths = points.slice(1).map((point, index) =>
    Math.hypot(point[0] - points[index][0], point[1] - points[index][1])
  );
  const total = lengths.reduce((sum, length) => sum + length, 0);
  if (total === 0) return [...points[0]];
  let target = clamped * total;
  for (let index = 0; index < lengths.length; index += 1) {
    if (target <= lengths[index] || index === lengths.length - 1) {
      const ratio = lengths[index] === 0 ? 0 : target / lengths[index];
      return [
        points[index][0] + (points[index + 1][0] - points[index][0]) * ratio,
        points[index][1] + (points[index + 1][1] - points[index][1]) * ratio
      ];
    }
    target -= lengths[index];
  }
  return [...points.at(-1)!];
}

export function filterAgents(
  run: RaceRun,
  filters: { model?: string; decisionType?: DecisionType; difficulty?: Difficulty; result?: "correct" | "wrong" }
): AgentDecision[] {
  return run.agents.filter((agent) =>
    (!filters.model || agent.model === filters.model)
    && (!filters.decisionType || agent.decision_type === filters.decisionType)
    && (!filters.difficulty || agent.difficulty === filters.difficulty)
    && (!filters.result || (filters.result === "correct") === agent.is_correct)
  );
}
