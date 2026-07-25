import { describe, expect, it } from "vitest";
import type { AgentDecision, AgentLog, AgentSpan } from "./domain";
import { parseRaceData } from "./replay";
import {
  buildSigNozLinks,
  filterLogs,
  observabilityCoverage,
  parseSigNozConfig,
  spanTree
} from "./observability";

const traceId = "a".repeat(32);
const spanId = "b".repeat(16);
const childSpanId = "c".repeat(16);

const span = (overrides: Partial<AgentSpan> = {}): AgentSpan => ({
  span_id: spanId,
  parent_span_id: undefined,
  trace_id: traceId,
  name: "gen_ai.evaluation.result",
  service_name: "toy-world",
  start_time_unix_nano: "1785001000000000000",
  duration_ms: 2,
  status: "ok",
  source: "signoz",
  attributes: { "gen_ai.response.id": "response-1" },
  linked_span_ids: [],
  ...overrides
});

const log = (overrides: Partial<AgentLog> = {}): AgentLog => ({
  timestamp_unix_nano: "1785001001000000000",
  severity: "INFO",
  body: "grade resolved",
  source: "signoz",
  trace_id: traceId,
  span_id: spanId,
  attributes: { "service.name": "toy-world" },
  ...overrides
});

const agent = (mode: "signoz" | "replay" = "signoz"): AgentDecision => ({
  agent_id: "agent-1",
  response_id: "response-1",
  model: "anthropic/claude-haiku-4.5",
  color: "#55d7ff",
  decision_type: "route_choice",
  difficulty: "medium",
  query_id: "query-1",
  start: "J1",
  destination: "J5",
  chosen: "A",
  correct_answer: "A",
  is_correct: true,
  chosen_path: ["J1", "J5"],
  correct_path: ["J1", "J5"],
  chosen_polyline: [[73.84, 18.52]],
  correct_polyline: [[73.84, 18.52]],
  cost_usd: 0.001,
  input_tokens: 10,
  output_tokens: 2,
  outcome: null,
  observability: mode === "signoz"
    ? {
        mode,
        response_id: "response-1",
        service_name: "toy-world",
        trace_id: traceId,
        evaluation_span_id: spanId,
        synchronized_at: "2026-07-26T12:00:00Z",
        spans: [span()],
        logs: [log()],
        links: { dashboard: "" }
      }
    : {
        mode,
        response_id: "response-1",
        service_name: "toy-world",
        spans: [span({ trace_id: undefined, source: "replay" })],
        logs: [log({ trace_id: undefined, source: "replay" })],
        links: { dashboard: "" }
      }
});

describe("schema-v3 observability", () => {
  it("keeps Unix nanoseconds as strings", () => {
    const run = parseRaceData({
      schema_version: 3,
      generated_from: "fixture",
      agents: [agent()],
      outcomes: [],
      totals: {
        decisions: 1,
        correct: 1,
        total_cost_usd: 0.001,
        outcomes: 0,
        cost_per_correct_usd: 0.001,
        by_type: { route_choice: 1, eta_estimate: 0, next_hop: 0 },
        by_model: { "anthropic/claude-haiku-4.5": 1 }
      },
      observability_coverage: { kind: "connected", matched: 1, total: 1 }
    });

    expect(run.agents[0].observability.spans[0].start_time_unix_nano)
      .toBe("1785001000000000000");
  });

  it("rejects live evidence that does not belong to its agent", () => {
    const raw = agent();
    raw.observability.response_id = "response-2";
    expect(() => parseRaceData({
      schema_version: 3,
      generated_from: "fixture",
      agents: [raw],
      outcomes: [],
      totals: {
        decisions: 1, correct: 1, total_cost_usd: 0.001, outcomes: 0,
        cost_per_correct_usd: 0.001,
        by_type: { route_choice: 1, eta_estimate: 0, next_hop: 0 },
        by_model: { "anthropic/claude-haiku-4.5": 1 }
      }
    })).toThrow(/response id/);
  });

  it("rejects replay evidence that exposes a trace ID", () => {
    const raw = agent("replay");
    raw.observability.trace_id = traceId;
    expect(() => parseRaceData({
      schema_version: 3,
      generated_from: "fixture",
      agents: [raw],
      outcomes: [],
      totals: {
        decisions: 1, correct: 1, total_cost_usd: 0.001, outcomes: 0,
        cost_per_correct_usd: 0.001,
        by_type: { route_choice: 1, eta_estimate: 0, next_hop: 0 },
        by_model: { "anthropic/claude-haiku-4.5": 1 }
      }
    })).toThrow(/replay.*trace/i);
  });
});

describe("SigNoz navigation", () => {
  const config = parseSigNozConfig({
    signoz_origin: "https://signoz.example/base/",
    dashboard_path: "/dashboard/gradebook",
    service_names: ["toy-world"]
  });

  it("builds exact trace, logs, and dashboard URLs only for synchronized evidence", () => {
    const links = buildSigNozLinks(config, agent());
    expect(links.trace).toBe(`https://signoz.example/base/trace/${traceId}`);
    expect(links.logs).toBe(`https://signoz.example/base/logs?traceId=${traceId}`);
    expect(links.dashboard).toBe("https://signoz.example/base/dashboard/gradebook");

    const replayLinks = buildSigNozLinks(config, agent("replay"));
    expect(replayLinks.trace).toBeUndefined();
    expect(decodeURIComponent(replayLinks.traceSearch!)).toContain("gen_ai.response.id");
    expect(decodeURIComponent(replayLinks.traceSearch!)).toContain("response-1");
  });

  it("rejects javascript and credential-bearing origins", () => {
    expect(() => parseSigNozConfig({ signoz_origin: "javascript:alert(1)" }))
      .toThrow(/http or https/);
    expect(() => parseSigNozConfig({ signoz_origin: "http://user:pass@localhost:8080" }))
      .toThrow(/credentials/);
  });
});

describe("observability utilities", () => {
  it("reports only validated live evidence as coverage", () => {
    const invalid = agent();
    invalid.observability.trace_id = "not-a-trace";
    expect(observabilityCoverage([agent(), agent("replay"), invalid])).toEqual({
      kind: "partial", matched: 1, total: 3
    });
  });

  it("orders span roots and siblings by nanosecond time", () => {
    const nodes = spanTree([
      span({ span_id: childSpanId, parent_span_id: spanId, start_time_unix_nano: "30" }),
      span({ span_id: spanId, start_time_unix_nano: "20" }),
      span({ span_id: "d".repeat(16), start_time_unix_nano: "10" })
    ]);
    expect(nodes.map((node) => node.span.span_id)).toEqual(["d".repeat(16), spanId]);
    expect(nodes[1].children.map((node) => node.span.span_id)).toEqual([childSpanId]);
  });

  it("filters warning/error logs and selected-span logs", () => {
    const logs = [
      log({ severity: "INFO" }),
      log({ severity: "WARN", span_id: childSpanId }),
      log({ severity: "ERROR", span_id: childSpanId })
    ];
    expect(filterLogs(logs, "warnings-errors").map((entry) => entry.severity))
      .toEqual(["WARN", "ERROR"]);
    expect(filterLogs(logs, "selected-span", childSpanId)).toHaveLength(2);
  });
});
