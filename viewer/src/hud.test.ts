import { describe, expect, it } from "vitest";
import { createHud } from "./hud";
import { parseRaceData } from "./replay";

const fixture = {
  schema_version: 1,
  generated_from: "fixture",
  drivers: [1, 2, 3, 4].map((number) => ({
    id: `driver-${number}`,
    model: number === 3 ? "google/gemini-flash" : "anthropic/claude",
    color: "#69f0ae",
    decisions: [{
      junction: "J1", stage_index: 0, chosen: "A", true_fastest: "A", correct: true,
      travel_time_min: 7, input_tokens: 1, output_tokens: 1, cost_usd: 0.1,
      response_id: `d${number}-j1`
    }]
  })),
  outcomes: [1, 2, 3, 4].map((number) => ({
    driver: `driver-${number}`, on_time: true, graded_response_id: `d${number}-j1`
  })),
  totals: { decisions: 4, correct: 4, total_cost_usd: 0.4, outcomes: 4, cost_per_correct_usd: 0.1 }
};

describe("HUD", () => {
  it("renders one accessible row per driver", () => {
    const root = document.createElement("div");
    createHud(root, parseRaceData(fixture));
    expect(root.querySelectorAll("[data-driver-id]")).toHaveLength(4);
  });
});
