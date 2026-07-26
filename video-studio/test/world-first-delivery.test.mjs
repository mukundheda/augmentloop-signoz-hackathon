import test from "node:test";
import assert from "node:assert/strict";
import {validateWorldFirstDelivery} from "../src/world-first-delivery.mjs";

const cues = {
  fps: 30,
  totalFrames: 3600,
  width: 1920,
  height: 1080,
  narration: [{id: "world", text: "Real narration"}],
};
const probe = {
  format: {duration: "120.000000"},
  streams: [
    {
      codec_type: "video", codec_name: "h264", profile: "High",
      width: 1920, height: 1080, r_frame_rate: "30/1",
      start_time: "0.000000", duration: "120.000000", nb_read_frames: "3600",
    },
    {
      codec_type: "audio", codec_name: "aac", sample_rate: "48000",
      channels: 2, start_time: "0.000000", duration: "120.000000",
    },
  ],
};
const recording = {
  actions: ["orbit", "top", "chase", "follow", "overview"].map((value) => ({
    operation: "camera", value,
  })),
  finalStatus: {decisions: 420, correct: 268, state: "COMPLETE"},
};
const narration = [{id: "world", text: "Real narration"}];

test("world-first delivery validates exact synchronized media and real viewer actions", () => {
  const result = validateWorldFirstDelivery({probe, cues, recording, narration});
  assert.equal(result.durationSeconds, 120);
  assert.equal(result.frames, 3600);
  assert.deepEqual(result.cameraModes, ["chase", "follow", "orbit", "overview", "top"]);
});

test("world-first delivery rejects a frame-short master", () => {
  const shortProbe = structuredClone(probe);
  shortProbe.streams[0].nb_read_frames = "3594";
  assert.throws(
    () => validateWorldFirstDelivery({probe: shortProbe, cues, recording, narration}),
    /expected 3600 video frames/,
  );
});
