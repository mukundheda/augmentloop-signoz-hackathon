import assert from "node:assert/strict";
import test from "node:test";
import {buildRecordingPlan} from "../src/recording-plan.mjs";

const sampleCues = {
  fps: 30,
  totalFrames: 3600,
  cameraActions: [
    {startFrame: 0, operation: "camera", camera: "orbit"},
    {startFrame: 0, operation: "speed", value: 4},
    {startFrame: 600, operation: "selectAgent"},
    {startFrame: 615, operation: "camera", camera: "follow"},
    {startFrame: 3590, operation: "completeRun"},
  ],
};

test("recording plan begins with a real orbit and ends on completed results", () => {
  const plan = buildRecordingPlan(sampleCues);
  assert.deepEqual(plan[0], {atFrame: 0, atMs: 0, operation: "camera", value: "orbit"});
  assert.equal(plan.at(-1).operation, "completeRun");
});

test("recording plan selects an agent before the follow camera", () => {
  const plan = buildRecordingPlan(sampleCues);
  const select = plan.findIndex((action) => action.operation === "selectAgent");
  const follow = plan.findIndex((action) => action.value === "follow");
  assert.ok(select >= 0 && select < follow);
});

test("recording actions use frame-derived wall-clock time", () => {
  const plan = buildRecordingPlan(sampleCues);
  assert.equal(plan.find((action) => action.atFrame === 600).atMs, 20000);
});
