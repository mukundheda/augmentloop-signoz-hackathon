import { describe, expect, it } from "vitest";
import { buildWaves, parseRaceData, samplePolyline } from "./replay";

const agent = (index: number) => ({
  agent_id: `agent-${index}`,
  response_id: `response-${index}`,
  model: "anthropic/claude-haiku-4.5",
  color: "#55d7ff",
  decision_type: index % 3 === 0 ? "route_choice" : index % 3 === 1 ? "eta_estimate" : "next_hop",
  difficulty: "medium",
  query_id: `query-${index}`,
  start: "J1",
  destination: "J5",
  chosen: "A",
  correct_answer: "A",
  is_correct: true,
  chosen_path: ["J1", "J5"],
  correct_path: ["J1", "J5"],
  chosen_polyline: [[73.84, 18.52], [73.85, 18.51]],
  correct_polyline: [[73.84, 18.52], [73.85, 18.51]],
  cost_usd: 0.001,
  input_tokens: 10,
  output_tokens: 2,
  outcome: null
});

const fixture = {
  schema_version: 2,
  generated_from: "fixture",
  agents: Array.from({ length: 50 }, (_, index) => agent(index + 1)),
  outcomes: [],
  totals: {
    decisions: 50,
    correct: 50,
    total_cost_usd: 0.05,
    outcomes: 0,
    cost_per_correct_usd: 0.001,
    by_type: { route_choice: 16, eta_estimate: 17, next_hop: 17 },
    by_model: { "anthropic/claude-haiku-4.5": 50 }
  }
};

describe("schema-v2 replay", () => {
  it("schedules every agent exactly once in waves of at most 24", () => {
    const run = parseRaceData(fixture);
    const waves = buildWaves(run, 24);
    expect(waves.every((wave) => wave.agents.length <= 24)).toBe(true);
    expect(
      new Set(waves.flatMap((wave) => wave.agents.map((entry) => entry.response_id))).size
    ).toBe(50);
    expect(waves).toHaveLength(3);
  });

  it("samples by distance along the supplied road polyline", () => {
    expect(samplePolyline([[0, 0], [10, 0], [10, 10]], 0.75)).toEqual([10, 5]);
  });

  it("rejects duplicate response IDs", () => {
    const broken = structuredClone(fixture);
    broken.agents[1].response_id = broken.agents[0].response_id;
    expect(() => parseRaceData(broken)).toThrow(/duplicate response/);
  });
});
