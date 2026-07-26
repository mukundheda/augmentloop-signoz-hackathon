import assert from "node:assert/strict";
import test from "node:test";
import {buildAudioGraph, frameToMilliseconds} from "../src/audio-graph.mjs";

test("audio placement is derived exactly from integer frames", () => {
  assert.equal(frameToMilliseconds(35, 30), 1167);
  assert.equal(frameToMilliseconds(1800, 30), 60000);
});

test("master graph ducks music, delays cues, and ends at sixty seconds", () => {
  const graph = buildAudioGraph({
    fps: 30,
    narration: [{startFrame: 35}],
    effects: [{startFrame: 548, gainDb: -18}],
  });
  assert.match(graph, /adelay=1167\|1167/);
  assert.match(graph, /adelay=18267\|18267/);
  assert.match(graph, /sidechaincompress/);
  assert.match(graph, /apad=whole_dur=60/);
  assert.match(graph, /atrim=duration=60/);
  assert.match(graph, /aresample=48000/);
});
