import test from "node:test";
import assert from "node:assert/strict";
import {buildOverlayPlan} from "../src/overlay-plan.mjs";

test("overlay plan converts approved cue kinds to exact timestamps", () => {
  const plan = buildOverlayPlan({
    fps: 30,
    overlays: [
      {kind: "chapter", text: "TOYWORLD / PUNE", startFrame: 24, endFrame: 180},
      {kind: "metric", text: "20 junctions", startFrame: 980, endFrame: 1260},
      {kind: "metric", text: "268 correct", startFrame: 2790, endFrame: 3070},
      {kind: "identity", text: "GRADEBOOK", startFrame: 3310, endFrame: 3580},
    ],
  });

  assert.equal(plan.length, 4);
  assert.deepEqual(plan[0], {
    kind: "chapter",
    text: "TOYWORLD / PUNE",
    startSeconds: 0.8,
    endSeconds: 6,
  });
});

test("overlay plan rejects mock product UI", () => {
  assert.throws(
    () => buildOverlayPlan({
      fps: 30,
      overlays: [{kind: "mock-ui", text: "fake dashboard", startFrame: 0, endFrame: 30}],
    }),
    /unsupported overlay kind/,
  );
});
