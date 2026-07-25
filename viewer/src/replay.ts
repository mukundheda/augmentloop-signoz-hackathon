import type {
  AgentLog,
  AgentObservability,
  AgentSpan,
  AgentDecision,
  AttributeValue,
  Coordinate,
  CoverageState,
  DecisionType,
  Difficulty,
  EvidenceSource,
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

const asOptionalString = (value: unknown, label: string): string | undefined => {
  if (value === undefined || value === null) return undefined;
  return asString(value, label);
};

const asOptionalText = (value: unknown, label: string): string | undefined => {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string") throw new Error(`${label} must be a string`);
  return value;
};

const asStringArray = (value: unknown, label: string): string[] => {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value.map((item, index) => asString(item, `${label} ${index}`));
};

const asCoordinate = (value: unknown, label: string): Coordinate => {
  if (!Array.isArray(value) || value.length !== 2) throw new Error(`${label} must be [lon,lat]`);
  return [asNumber(value[0], label), asNumber(value[1], label)];
};

const DECISION_TYPES = new Set(["route_choice", "eta_estimate", "next_hop"]);
const DIFFICULTIES = new Set(["easy", "medium", "hard"]);
const HEX_32 = /^[0-9a-f]{32}$/;
const HEX_16 = /^[0-9a-f]{16}$/;
const NANOSECONDS = /^\d+$/;
const SPAN_STATUSES = new Set(["unset", "ok", "error"]);
const EVIDENCE_SOURCES = new Set(["signoz", "replay"]);
const LOG_SEVERITIES = new Set(["TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"]);

const asCanonicalId = (value: unknown, label: string, pattern: RegExp): string => {
  const identifier = asString(value, label);
  if (!pattern.test(identifier)) throw new Error(`${label} must be canonical lowercase hexadecimal`);
  return identifier;
};

const asOptionalCanonicalId = (value: unknown, label: string, pattern: RegExp): string | undefined => {
  if (value === undefined || value === null) return undefined;
  return asCanonicalId(value, label, pattern);
};

const asNanoseconds = (value: unknown, label: string): string => {
  const timestamp = asString(value, label);
  if (!NANOSECONDS.test(timestamp)) throw new Error(`${label} must be a decimal-string nanosecond timestamp`);
  return timestamp;
};

const asAttributes = (value: unknown, label: string): Record<string, AttributeValue> => {
  const record = asRecord(value, label);
  const attributes: Record<string, AttributeValue> = {};
  for (const [key, attribute] of Object.entries(record)) {
    if (typeof attribute === "string" || typeof attribute === "boolean") {
      attributes[key] = attribute;
    } else if (typeof attribute === "number" && Number.isFinite(attribute)) {
      attributes[key] = attribute;
    } else {
      throw new Error(`${label}.${key} must be a primitive finite value`);
    }
  }
  return attributes;
};

const parseSpan = (value: unknown, index: number, mode: EvidenceSource): AgentSpan => {
  const span = asRecord(value, `span ${index}`);
  const source = asString(span.source, `span ${index} source`);
  if (!EVIDENCE_SOURCES.has(source) || source !== mode) throw new Error(`span ${index} source does not match observability mode`);
  const traceId = asOptionalCanonicalId(span.trace_id, `span ${index} trace id`, HEX_32);
  if (mode === "replay" && traceId !== undefined) throw new Error("replay spans must not expose a trace ID");
  const status = asString(span.status, `span ${index} status`);
  if (!SPAN_STATUSES.has(status)) throw new Error(`span ${index} has an unknown status`);
  return {
    span_id: asCanonicalId(span.span_id, `span ${index} id`, HEX_16),
    parent_span_id: asOptionalCanonicalId(span.parent_span_id, `span ${index} parent span id`, HEX_16),
    trace_id: traceId,
    name: asString(span.name, `span ${index} name`),
    service_name: asString(span.service_name, `span ${index} service name`),
    start_time_unix_nano: asNanoseconds(span.start_time_unix_nano, `span ${index} timestamp`),
    duration_ms: asNumber(span.duration_ms, `span ${index} duration`),
    status: status as AgentSpan["status"],
    source: source as EvidenceSource,
    attributes: asAttributes(span.attributes, `span ${index} attributes`),
    linked_span_ids: asStringArray(span.linked_span_ids, `span ${index} linked span ids`).map((id, linkedIndex) =>
      asCanonicalId(id, `span ${index} linked span ${linkedIndex}`, HEX_16)
    )
  };
};

const parseLog = (value: unknown, index: number, mode: EvidenceSource): AgentLog => {
  const log = asRecord(value, `log ${index}`);
  const source = asString(log.source, `log ${index} source`);
  if (!EVIDENCE_SOURCES.has(source) || source !== mode) throw new Error(`log ${index} source does not match observability mode`);
  const traceId = asOptionalCanonicalId(log.trace_id, `log ${index} trace id`, HEX_32);
  if (mode === "replay" && traceId !== undefined) throw new Error("replay logs must not expose a trace ID");
  const severity = asString(log.severity, `log ${index} severity`);
  if (!LOG_SEVERITIES.has(severity)) throw new Error(`log ${index} has an unknown severity`);
  return {
    timestamp_unix_nano: asNanoseconds(log.timestamp_unix_nano, `log ${index} timestamp`),
    severity: severity as AgentLog["severity"],
    body: asString(log.body, `log ${index} body`),
    source: source as EvidenceSource,
    trace_id: traceId,
    span_id: asOptionalCanonicalId(log.span_id, `log ${index} span id`, HEX_16),
    attributes: asAttributes(log.attributes, `log ${index} attributes`)
  };
};

const parseLinks = (value: unknown): AgentObservability["links"] => {
  const links = asRecord(value, "observability links");
  return {
    trace: asOptionalText(links.trace, "trace link"),
    logs: asOptionalText(links.logs, "logs link"),
    dashboard: asOptionalText(links.dashboard, "dashboard link"),
    traceSearch: asOptionalText(links.traceSearch, "trace search link")
  };
};

const parseObservability = (value: unknown, responseId: string): AgentObservability => {
  const observation = asRecord(value, "observability");
  const mode = asString(observation.mode, "observability mode");
  if (mode !== "signoz" && mode !== "replay") throw new Error("observability mode must be signoz or replay");
  if (asString(observation.response_id, "observability response id") !== responseId) {
    throw new Error("observability response id must match agent response id");
  }
  const traceId = asOptionalCanonicalId(observation.trace_id, "observability trace id", HEX_32);
  const evaluationSpanId = asOptionalCanonicalId(observation.evaluation_span_id, "observability evaluation span id", HEX_16);
  if (mode === "signoz" && (traceId === undefined || evaluationSpanId === undefined)) {
    throw new Error("signoz observability requires trace and evaluation span IDs");
  }
  if (mode === "replay" && traceId !== undefined) throw new Error("replay observability must not expose a trace ID");
  if (!Array.isArray(observation.spans) || !Array.isArray(observation.logs)) {
    throw new Error("observability spans and logs must be arrays");
  }
  const spans = observation.spans.map((span, index) => parseSpan(span, index, mode));
  const spanIds = new Set<string>();
  for (const span of spans) {
    if (spanIds.has(span.span_id)) throw new Error(`duplicate observability span ${span.span_id}`);
    spanIds.add(span.span_id);
  }
  return {
    mode,
    response_id: responseId,
    service_name: asString(observation.service_name, "observability service name"),
    trace_id: traceId,
    evaluation_span_id: evaluationSpanId,
    synchronized_at: asOptionalString(observation.synchronized_at, "observability synchronized at"),
    spans,
    logs: observation.logs.map((log, index) => parseLog(log, index, mode)),
    links: parseLinks(observation.links)
  };
};

export function parseRaceData(value: unknown): RaceRun {
  const root = asRecord(value, "run");
  if (root.schema_version !== 3) throw new Error("unsupported schema version");
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
      outcome: agent.outcome as AgentDecision["outcome"],
      observability: parseObservability(agent.observability, responseId)
    };
  });
  const matchedEvidence = agents.filter((agent) =>
    agent.observability.mode === "signoz"
    && agent.observability.trace_id !== undefined
    && HEX_32.test(agent.observability.trace_id)
    && agent.observability.evaluation_span_id !== undefined
    && HEX_16.test(agent.observability.evaluation_span_id)
  ).length;
  const derivedCoverage: CoverageState = matchedEvidence === 0
    ? { kind: "offline" as const, matched: 0, total: agents.length }
    : matchedEvidence === agents.length
      ? { kind: "connected" as const, matched: matchedEvidence, total: agents.length }
      : { kind: "partial" as const, matched: matchedEvidence, total: agents.length };
  const coverage = asRecord(root.observability_coverage, "observability coverage");
  const coverageKind = asString(coverage.kind, "observability coverage kind");
  const coverageMatched = asNumber(coverage.matched, "observability coverage matched");
  const coverageTotal = asNumber(coverage.total, "observability coverage total");
  if (
    coverageKind !== derivedCoverage.kind
    || coverageMatched !== derivedCoverage.matched
    || coverageTotal !== derivedCoverage.total
  ) {
    throw new Error("observability coverage must match agent evidence");
  }
  const totals = asRecord(root.totals, "totals");
  const byType = asRecord(totals.by_type, "by type") as RaceRun["totals"]["by_type"];
  const byModel = asRecord(totals.by_model, "by model") as Record<string, number>;
  return {
    schema_version: 3,
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
    },
    observability_coverage: derivedCoverage
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
