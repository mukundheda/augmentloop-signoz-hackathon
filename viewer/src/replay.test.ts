import { describe, expect, it } from "vitest";
import { buildTimeline, parseRaceData, resolveOutcomeTargets } from "./replay";

const fixture = {
  schema_version: 1,
  generated_from: "fixture",
  drivers: [
    {
      id: "driver-3",
      model: "google/gemini",
      color: "#fff",
      decisions: [
        { junction: "J1", stage_index: 0, chosen: "B", true_fastest: "A", correct: false, travel_time_min: 9, input_tokens: 1, output_tokens: 1, cost_usd: 0.1, response_id: "d3-j1" }
      ]
    },
    {
      id: "driver-4",
      model: "anthropic/haiku",
      color: "#0ff",
      decisions: [
        { junction: "J2", stage_index: 1, chosen: "E", true_fastest: "D", correct: false, travel_time_min: 8, input_tokens: 1, output_tokens: 1, cost_usd: 0.2, response_id: "d4-j2" }
      ]
    }
  ],
  outcomes: [
    { driver: "driver-3", on_time: false, graded_response_id: "d3-j1" },
    { driver: "driver-4", on_time: false, graded_response_id: "d4-j2" }
  ],
  totals: { decisions: 2, correct: 0, total_cost_usd: 0.3, outcomes: 2, cost_per_correct_usd: null }
};

describe("replay domain", () => {
  it("targets late outcomes at the linked decisions", () => {
    const run = parseRaceData(fixture);
    const targets = resolveOutcomeTargets(run);
    expect(targets.get("driver-3")?.junction).toBe("J1");
    expect(targets.get("driver-4")?.junction).toBe("J2");
  });

  it("uses exported headline totals in the complete event", () => {
    const run = parseRaceData(fixture);
    const complete = buildTimeline(run).at(-1);
    expect(complete?.kind).toBe("complete");
    expect(complete?.totals.costPerCorrectUsd).toBeNull();
  });

  it("rejects an outcome that points to an unknown response", () => {
    const broken = structuredClone(fixture);
    broken.outcomes[0].graded_response_id = "missing";
    expect(() => parseRaceData(broken)).toThrow(/unknown response/);
  });
});
