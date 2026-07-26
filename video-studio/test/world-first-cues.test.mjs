import assert from "node:assert/strict";
import test from "node:test";
import {loadWorldFirstCues, validateWorldFirstCues} from "../src/world-first-cues.mjs";

test("world-first film contains every required real-viewer shot", async () => {
  const cues = await loadWorldFirstCues();
  const cameras = new Set(
    cues.cameraActions
      .filter((action) => action.operation === "camera")
      .map((action) => action.camera),
  );
  for (const required of ["orbit", "top", "chase", "follow", "overview"]) {
    assert.ok(cameras.has(required), `missing ${required}`);
  }
});

test("world-first narration has no designed gap longer than 1.4 seconds", async () => {
  const cues = await loadWorldFirstCues();
  for (let index = 1; index < cues.narration.length; index += 1) {
    const before = cues.narration[index - 1];
    const current = cues.narration[index];
    assert.ok(
      current.startFrame - before.endFrame <= Math.round(cues.fps * 1.4),
      `gap after ${before.id} is too long`,
    );
  }
});

test("world-first claims match the committed ToyWorld run", async () => {
  const cues = await loadWorldFirstCues();
  assert.deepEqual(cues.results, {
    junctions: 20,
    models: 7,
    decisions: 420,
    correct: 268,
    outcomes: 140,
    totalCostUsd: 0.4038042399999995,
    costPerCorrectUsd: 0.0015067322388059683,
  });
  assert.doesNotThrow(() => validateWorldFirstCues(cues));
});
