import test from 'node:test';
import assert from 'node:assert/strict';
import {
  frameToSeconds,
  loadCues,
  sceneForFrame,
  validateTimeline,
} from '../src/cues.mjs';

test('frame conversion is exact at scene boundaries', () => {
  assert.equal(frameToSeconds(180), 6);
  assert.equal(frameToSeconds(1800), 60);
});

test('timeline must end at frame 1800', () => {
  assert.throws(
    () => validateTimeline({fps: 30, totalFrames: 1799, scenes: []}),
    /exactly 1800 frames/,
  );
});

test('approved cue sheet covers every frame with exactly one scene', async () => {
  const timeline = await loadCues('timeline/cues.json');
  const boundaries = [0, 179, 180, 539, 540, 1019, 1020, 1439, 1440, 1679, 1680, 1799];
  const expected = [
    'opening',
    'opening',
    'toyworld',
    'toyworld',
    'signals',
    'signals',
    'insights',
    'insights',
    'payoff',
    'payoff',
    'identity',
    'identity',
  ];
  assert.deepEqual(
    boundaries.map((frame) => sceneForFrame(timeline, frame).id),
    expected,
  );
});
