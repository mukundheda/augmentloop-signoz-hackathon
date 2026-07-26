import assert from "node:assert/strict";
import test from "node:test";
import {assertNarrationDensity, parseSilenceDetect} from "../src/silence.mjs";

test("silence parser identifies an unintended two-second gap", () => {
  const events = parseSilenceDetect(
    "[silencedetect] silence_start: 4.2\n" +
      "[silencedetect] silence_end: 6.4 | silence_duration: 2.2",
  );
  assert.deepEqual(events, [{start: 4.2, end: 6.4, duration: 2.2}]);
  assert.throws(() => assertNarrationDensity(events, 1.4), /2.2 second silence/);
});

test("silence policy permits natural sentence breaths", () => {
  assert.doesNotThrow(() =>
    assertNarrationDensity([{start: 4.2, end: 5.1, duration: 0.9}], 1.4),
  );
});
