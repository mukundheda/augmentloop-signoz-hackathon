import { describe, expect, it } from "vitest";
import { createHud } from "./hud";
import type { CoverageState, RaceRun, SigNozConfig } from "./domain";

const run = {
  schema_version: 3,
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

  it.each([
    [{ kind: "connected", matched: 180, total: 180 }, "SIGNOZ CONNECTED · 180/180"],
    [{ kind: "partial", matched: 142, total: 180 }, "SIGNOZ PARTIAL · 142/180"],
    [{ kind: "offline", matched: 0, total: 180 }, "REPLAY MODE · SIGNOZ OFFLINE"]
  ])("renders explicit observability coverage", (coverage, expected) => {
    const root = document.createElement("div");
    const config: SigNozConfig = {
      signoz_origin: "https://signoz.example.test",
      dashboard_path: "/dashboard/gradebook",
      service_names: ["toy-world"]
    };
    const hud = createHud(root, run, config);
    hud.setCoverage(coverage as CoverageState);

    expect(root.textContent).toContain(expected);
  });
});
