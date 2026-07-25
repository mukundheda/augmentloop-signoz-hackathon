import type {
  AgentDecision,
  AgentLog,
  AgentSpan,
  CoverageState,
  SigNozConfig,
  SigNozLinks
} from "./domain";

export type LogFilter = "all" | "warnings-errors" | "selected-span";

export interface SpanTreeNode {
  span: AgentSpan;
  children: SpanTreeNode[];
  linked: AgentSpan[];
}

const TRACE_ID = /^[0-9a-f]{32}$/;
const SPAN_ID = /^[0-9a-f]{16}$/;

const asRecord = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
};

const normalizeOrigin = (value: string | null): string | undefined => {
  if (value === null) return undefined;
  if (typeof value !== "string" || value.trim() === "") throw new Error("SigNoz origin must be a URL");
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("SigNoz origin must be a URL");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("SigNoz origin must use http or https");
  }
  if (url.username || url.password) throw new Error("SigNoz origin must not include credentials");
  if (url.search || url.hash) throw new Error("SigNoz origin must not include a query or fragment");
  return `${url.origin}${url.pathname.replace(/\/+$/, "")}`;
};

const dashboardPath = (value: string | null): string | undefined => {
  if (value === null) return undefined;
  if (typeof value !== "string" || value.trim() === "") throw new Error("dashboard path must be a non-empty string or null");
  if (value.startsWith("//") || /[?#]/.test(value) || /^[a-z][a-z0-9+.-]*:/i.test(value)) {
    throw new Error("dashboard path must be a relative path");
  }
  return value.replace(/^\/+/, "");
};

export function parseSigNozConfig(value: unknown): SigNozConfig {
  const config = asRecord(value, "SigNoz config");
  const rawOrigin = config.signoz_origin ?? null;
  if (rawOrigin !== null && typeof rawOrigin !== "string") {
    throw new Error("SigNoz origin must be a string or null");
  }
  normalizeOrigin(rawOrigin as string | null);
  const rawDashboard = config.dashboard_path ?? null;
  if (rawDashboard !== null && typeof rawDashboard !== "string") {
    throw new Error("dashboard path must be a string or null");
  }
  dashboardPath(rawDashboard as string | null);
  const serviceNames = config.service_names ?? [];
  if (!Array.isArray(serviceNames) || serviceNames.some((name) => typeof name !== "string" || name === "")) {
    throw new Error("service names must be an array of strings");
  }
  return {
    signoz_origin: rawOrigin as string | null,
    dashboard_path: rawDashboard as string | null,
    service_names: [...serviceNames] as string[]
  };
}

const joinPath = (origin: string, path: string): URL => {
  const url = new URL(origin);
  const base = url.pathname.replace(/\/+$/, "");
  url.pathname = `${base}/${path.replace(/^\/+/, "")}`;
  return url;
};

const validLiveEvidence = (agent: AgentDecision): boolean =>
  agent.observability.mode === "signoz"
  && typeof agent.observability.trace_id === "string"
  && TRACE_ID.test(agent.observability.trace_id)
  && typeof agent.observability.evaluation_span_id === "string"
  && SPAN_ID.test(agent.observability.evaluation_span_id);

export function observabilityCoverage(agents: AgentDecision[]): CoverageState {
  const total = agents.length;
  const matched = agents.filter(validLiveEvidence).length;
  if (matched === 0) return { kind: "offline", matched: 0, total };
  if (matched === total) return { kind: "connected", matched, total };
  return { kind: "partial", matched, total };
}

export function buildSigNozLinks(config: SigNozConfig, agent: AgentDecision): SigNozLinks {
  let origin: string | undefined;
  let configuredDashboard: string | undefined;
  try {
    origin = normalizeOrigin(config.signoz_origin);
    configuredDashboard = dashboardPath(config.dashboard_path);
  } catch {
    return {};
  }
  if (!origin) return {};

  const links: SigNozLinks = {};
  if (configuredDashboard) links.dashboard = joinPath(origin, configuredDashboard).toString();
  if (validLiveEvidence(agent)) {
    links.trace = joinPath(origin, `trace/${agent.observability.trace_id}`).toString();
    const logs = joinPath(origin, "logs");
    logs.searchParams.set("traceId", agent.observability.trace_id!);
    links.logs = logs.toString();
  } else if (agent.observability.mode === "replay") {
    const search = joinPath(origin, "traces");
    search.searchParams.set("filter", `gen_ai.response.id = \"${agent.response_id}\"`);
    links.traceSearch = search.toString();
  }
  return links;
}

const compareNanoseconds = (left: string, right: string): number => {
  const leftValue = BigInt(left);
  const rightValue = BigInt(right);
  return leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0;
};

const sortNodes = (nodes: SpanTreeNode[]): SpanTreeNode[] => nodes.sort((left, right) => {
  const timestampOrder = compareNanoseconds(left.span.start_time_unix_nano, right.span.start_time_unix_nano);
  return timestampOrder || left.span.span_id.localeCompare(right.span.span_id);
});

const wouldCreateCycle = (childId: string, parentId: string, byId: Map<string, AgentSpan>): boolean => {
  const visited = new Set<string>();
  let current: string | undefined = parentId;
  while (current && !visited.has(current)) {
    if (current === childId) return true;
    visited.add(current);
    current = byId.get(current)?.parent_span_id;
  }
  return false;
};

export function spanTree(spans: AgentSpan[]): SpanTreeNode[] {
  const byId = new Map<string, AgentSpan>();
  for (const span of spans) {
    if (!byId.has(span.span_id)) byId.set(span.span_id, span);
  }
  const nodes = new Map<string, SpanTreeNode>(
    [...byId.values()].map((span) => [span.span_id, { span, children: [], linked: [] }])
  );
  const roots: SpanTreeNode[] = [];
  for (const span of byId.values()) {
    const node = nodes.get(span.span_id)!;
    const parentId = span.parent_span_id;
    const parent = parentId ? nodes.get(parentId) : undefined;
    if (parent && !wouldCreateCycle(span.span_id, parentId!, byId)) parent.children.push(node);
    else roots.push(node);
    node.linked = span.linked_span_ids
      .map((id) => byId.get(id))
      .filter((linked): linked is AgentSpan => linked !== undefined)
      .sort((left, right) => compareNanoseconds(left.start_time_unix_nano, right.start_time_unix_nano));
  }
  const order = (entries: SpanTreeNode[]): SpanTreeNode[] => {
    for (const node of entries) order(node.children);
    return sortNodes(entries);
  };
  return order(roots);
}

export function filterLogs(logs: AgentLog[], mode: LogFilter, spanId?: string): AgentLog[] {
  switch (mode) {
    case "all":
      return logs;
    case "warnings-errors":
      return logs.filter((log) => log.severity === "WARN" || log.severity === "ERROR" || log.severity === "FATAL");
    case "selected-span":
      return spanId === undefined ? [] : logs.filter((log) => log.span_id === spanId);
  }
}
