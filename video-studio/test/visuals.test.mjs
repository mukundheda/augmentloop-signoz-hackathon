import assert from "node:assert/strict";
import test from "node:test";
import { visualStateAtFrame } from "../src/visuals.mjs";

const scenes = [
  { id: "opening", startFrame: 0, endFrame: 180 },
  { id: "toyworld", startFrame: 180, endFrame: 540 },
  { id: "signals", startFrame: 540, endFrame: 1020 },
];

test("visual state resolves the active scene from exact cue boundaries", () => {
  assert.equal(visualStateAtFrame(179, scenes).scene.id, "opening");
  assert.equal(visualStateAtFrame(180, scenes).scene.id, "toyworld");
  assert.equal(visualStateAtFrame(540, scenes).scene.id, "signals");
});

test("visual scene progress is clamped and deterministic", () => {
  assert.equal(visualStateAtFrame(180, scenes).progress, 0);
  assert.equal(visualStateAtFrame(360, scenes).progress, 0.5);
  assert.equal(visualStateAtFrame(539, scenes).progress, 359 / 360);
  assert.throws(() => visualStateAtFrame(1020, scenes), /outside the timeline/);
});
