import { describe, expect, it } from "vitest";
import { AgentDotGeometry, roadSegmentGeometry } from "./scene";

describe("stable scene geometry", () => {
  it("builds independent road quads so sharp bends cannot cross-crack", () => {
    const geometry = roadSegmentGeometry([
      [73.8525, 18.5125],
      [73.8530, 18.5125],
      [73.8530, 18.5130]
    ], 0.2);

    expect(geometry.getAttribute("position").count).toBe(8);
    expect(geometry.getIndex()?.count).toBe(12);
  });

  it("uses a sphere for agent dots", () => {
    const geometry = new AgentDotGeometry();
    expect(geometry.type).toBe("SphereGeometry");
  });
});
