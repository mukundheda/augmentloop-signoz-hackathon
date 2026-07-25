import { beforeEach, describe, expect, it } from "vitest";
import { createInspector } from "./inspector";
import type { AgentDecision, SigNozConfig } from "./domain";

const config: SigNozConfig = {
  signoz_origin: "https://signoz.example.test",
  dashboard_path: "/dashboard/gradebook",
  service_names: ["toy-world", "toy-world-outcomes"]
};

const replayAgent = {
  agent_id: "route-agent",
  response_id: "response-replay",
  model: "openai/gpt-5",
  color: "#55d7ff",
  decision_type: "route_choice",
  difficulty: "medium",
  query_id: "query-1",
  start: "J1",
  destination: "J5",
  chosen: "B",
  correct_answer: "A",
  is_correct: false,
  chosen_path: ["J1", "J3", "J5"],
  correct_path: ["J1", "J2", "J5"],
  chosen_polyline: [[73.84, 18.52]],
  correct_polyline: [[73.84, 18.52]],
  cost_usd: 0.001,
  input_tokens: 10,
  output_tokens: 2,
  outcome: null,
  observability: {
    mode: "replay",
    response_id: "response-replay",
    service_name: "toy-world",
    links: {},
    evaluation_span_id: "0000000000000001",
    spans: [{
      span_id: "0000000000000001",
      service_name: "toy-world",
      name: "gen_ai.evaluation.result",
      start_time_unix_nano: "1785001000000000000",
      duration_ms: 1,
      status: "ok",
      source: "replay",
      attributes: {},
      linked_span_ids: []
    }],
    logs: [{
      timestamp_unix_nano: "1785001000000000000",
      severity: "INFO",
      body: "decision replayed",
      span_id: "0000000000000001",
      source: "replay",
      attributes: {}
    }]
  }
} as AgentDecision;

const synchronizedAgent = {
  ...replayAgent,
  response_id: "response-live",
  observability: {
    ...replayAgent.observability,
    mode: "signoz",
    response_id: "response-live",
    trace_id: "a".repeat(32),
    spans: [
      {
      ...replayAgent.observability.spans[0],
        span_id: "0000000000000002",
        trace_id: "a".repeat(32),
        name: "model.run",
        linked_span_ids: []
      },
      {
        ...replayAgent.observability.spans[0],
        trace_id: "a".repeat(32),
        parent_span_id: "0000000000000002",
        linked_span_ids: ["0000000000000002"]
      }
    ],
    logs: [{
      ...replayAgent.observability.logs[0],
      severity: "WARN",
      body: "grade resolved incorrect",
      trace_id: "a".repeat(32),
      span_id: "0000000000000001",
      source: "signoz"
    }]
  }
} as AgentDecision;

describe("agent inspector", () => {
  let host: HTMLElement;

  beforeEach(() => {
    host = document.createElement("div");
  });

  it("renders replay evidence with response-ID fallback but no exact trace action", () => {
    const inspector = createInspector(host, config);
    inspector.show(replayAgent);

    expect(host.textContent).toContain("REPLAY EVIDENCE");
    expect(host.textContent).toContain("Find by response ID in SigNoz");
    expect(host.textContent).not.toContain("Open trace in SigNoz");
    expect(host.querySelector("[data-copy-response-id]")).not.toBeNull();
  });

  it("renders accessible trace and logs tabs with span links and severity filters", () => {
    const inspector = createInspector(host, config);
    inspector.show(synchronizedAgent);
    inspector.selectTab("trace");

    const traceTab = host.querySelector<HTMLButtonElement>("[role=tab][data-tab=trace]");
    expect(traceTab?.getAttribute("aria-selected")).toBe("true");
    expect(host.textContent).toContain("gen_ai.evaluation.result");
    expect(host.textContent).toContain("REALITY GRADE LINK");
    expect(host.textContent).toContain("Open trace in SigNoz");

    inspector.selectTab("logs");
    expect(host.textContent).toContain("grade resolved incorrect");
    expect(host.textContent).toContain("WARN");
    expect(host.querySelector("[data-log-filter=warnings-errors]")).not.toBeNull();
  });

  it("labels an empty synchronized log result clearly", () => {
    const inspector = createInspector(host, config);
    inspector.show({
      ...synchronizedAgent,
      observability: { ...synchronizedAgent.observability, logs: [] }
    } as AgentDecision);
    inspector.selectTab("logs");

    expect(host.textContent).toContain("No trace-correlated logs returned by SigNoz");
  });
});
