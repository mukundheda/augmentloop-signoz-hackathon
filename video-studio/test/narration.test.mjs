import test from 'node:test';
import assert from 'node:assert/strict';
import {validateNarrationMetadata, validateVoiceJobs} from '../src/narration.mjs';

test('voice jobs require unique ids and nonblank text', () => {
  assert.throws(
    () =>
      validateVoiceJobs([
        {id: 'opening', text: 'Hello'},
        {id: 'opening', text: '   '},
      ]),
    /unique ids|blank text/,
  );
});

test('narration metadata must fit inside its visual scene', () => {
  assert.throws(
    () =>
      validateNarrationMetadata(
        [{id: 'opening', startFrame: 35, durationFrames: 160}],
        [{id: 'opening', startFrame: 0, endFrame: 180}],
      ),
    /crosses scene boundary/,
  );
});
