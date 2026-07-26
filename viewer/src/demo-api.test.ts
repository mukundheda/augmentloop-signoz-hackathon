import {describe, expect, it} from "vitest";
import {CAMERA_PRESETS, isDemoSpeed} from "./demo-api";

describe("ToyWorld demo API", () => {
  it("contains every camera view required by the film", () => {
    expect(CAMERA_PRESETS).toEqual(["overview", "orbit", "top", "chase", "follow"]);
  });

  it("allows only viewer-supported replay speeds", () => {
    expect(isDemoSpeed(4)).toBe(true);
    expect(isDemoSpeed(3)).toBe(false);
  });
});
