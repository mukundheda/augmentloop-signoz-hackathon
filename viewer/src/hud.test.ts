import { describe, expect, it } from "vitest";
import { createHud } from "./hud";
import type { RaceRun } from "./domain";

const run = {
  schema_version: 2,
  generated_from: "fixture",
  agents: [],
  outcomes: [],
  totals: {
    decisions: 180,
    correct: 120,
    total_cost_usd: 0.3,
    outcomes: 60,
    cost_per_correct_usd: 0.0025,
    by_type: { route_choice: 60, eta_estimate: 60, next_hop: 60 },
    by_model: { model: 180 }
  }
} satisfies RaceRun;

describe("schema-v2 HUD", () => {
  it("shows all three decision type totals", () => {
    const root = document.createElement("div");
    const hud = createHud(root, run);
    expect(hud.element.querySelector("[data-type=route_choice]")).not.toBeNull();
    expect(hud.element.querySelector("[data-type=eta_estimate]")).not.toBeNull();
    expect(hud.element.querySelector("[data-type=next_hop]")).not.toBeNull();
  });
});
