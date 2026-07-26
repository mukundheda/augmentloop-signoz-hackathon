# Gradebook and ToyWorld Synced Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and render a professional 60-second Gradebook and ToyWorld product demo with local Kokoro narration, licensed music and effects, and frame-accurate audiovisual synchronization.

**Architecture:** A JSON cue sheet is the sole timing authority for the 1,800-frame timeline. Small Node.js modules validate cues, generate sentence-level narration through Kokoro.js WebAssembly, drive deterministic browser visuals, and emit an FFmpeg filter graph for music ducking, effects, mastering, and exact-duration muxing.

**Tech Stack:** Node.js 24, `kokoro-js`, WebAssembly, Playwright with Microsoft Edge, HTML/CSS/JavaScript, FFmpeg 8.1, Node test runner, Mixkit-licensed audio assets.

## Global Constraints

- Timeline is exactly 1,800 frames at 30 fps and 1920×1080.
- Final audio is 48 kHz stereo; final video is H.264 High Profile with AAC audio.
- All timing originates as integer frames; seconds are derived as `frame / 30`.
- Narration uses a warm, confident female Kokoro voice selected from auditions.
- Music is minimal premium technology and stays subordinate to narration.
- Sound design is limited to an opening texture, two UI interactions, one transition, one insight accent, and one closing chime.
- Every downloaded audio asset records title, creator, source URL, download date, and license URL.
- Final muxing must not use `-shortest`.
- Final master targets approximately −14 LUFS integrated and at most −1 dBTP.
- Do not weaken Windows Application Control or require unsigned native helpers.

---

## File Structure

- `video-studio/timeline/cues.json`: the complete 1,800-frame story, narration, caption, music, and SFX schedule.
- `video-studio/src/cues.mjs`: cue parsing, frame conversion, and validation.
- `video-studio/src/kokoro.mjs`: WebAssembly model loading and sentence-level WAV generation.
- `video-studio/src/audio-graph.mjs`: deterministic FFmpeg input and filter-graph construction.
- `video-studio/scripts/audition.mjs`: generate voice candidates from a fixed Gradebook line.
- `video-studio/scripts/narrate.mjs`: generate all selected narration segments and measured-duration metadata.
- `video-studio/scripts/render.mjs`: render cue-driven deterministic visual frames.
- `video-studio/scripts/mix.mjs`: mix narration, licensed music, and SFX into the exact 60-second master.
- `video-studio/public/frame.html`: render the appropriate visual scene for a requested frame.
- `video-studio/assets/audio/manifest.json`: licensing metadata and local filenames for selected music and effects.
- `video-studio/assets/audio/source/`: immutable downloaded source audio.
- `video-studio/output/audio/`: generated narration and processed audio.
- `video-studio/test/*.test.mjs`: timing, cue, generation, filter graph, and final-media tests.

### Task 1: Install and Prove Kokoro WebAssembly

**Files:**
- Modify: `video-studio/package.json`
- Modify: `video-studio/package-lock.json`
- Create: `video-studio/src/kokoro.mjs`
- Create: `video-studio/scripts/audition.mjs`
- Create: `video-studio/test/kokoro.test.mjs`

**Interfaces:**
- Produces: `loadKokoro({dtype?: "q8", device?: "wasm"}): Promise<KokoroTTS>`
- Produces: `generateWav({tts, text, voice, outputPath, speed?}): Promise<string>`

- [ ] **Step 1: Write the failing module contract test**

```js
// test/kokoro.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {generateWav} from '../src/kokoro.mjs';

test('generateWav rejects blank narration', async () => {
  await assert.rejects(
    generateWav({tts: {}, text: '   ', voice: 'af_heart', outputPath: 'x.wav'}),
    /Narration text cannot be blank/,
  );
});
```

- [ ] **Step 2: Run the test and verify the missing module failure**

Run: `node --test test/kokoro.test.mjs`

Expected: FAIL because `src/kokoro.mjs` does not exist.

- [ ] **Step 3: Install the JavaScript WebAssembly runtime**

Run: `npm.cmd install kokoro-js@1.2.1`

Expected: `kokoro-js` appears in `dependencies`; `npm audit` reports no high-severity vulnerability.

- [ ] **Step 4: Implement the Kokoro adapter**

```js
// src/kokoro.mjs
import path from 'node:path';
import {mkdir} from 'node:fs/promises';
import {KokoroTTS} from 'kokoro-js';

export const loadKokoro = () =>
  KokoroTTS.from_pretrained('onnx-community/Kokoro-82M-v1.0-ONNX', {
    dtype: 'q8',
    device: 'wasm',
  });

export const generateWav = async ({tts, text, voice, outputPath, speed = 1}) => {
  if (!text.trim()) throw new Error('Narration text cannot be blank');
  await mkdir(path.dirname(outputPath), {recursive: true});
  const audio = await tts.generate(text, {voice, speed});
  audio.save(outputPath);
  return outputPath;
};
```

- [ ] **Step 5: Generate four auditions**

Use this fixed line:

> ToyWorld captures every meaningful learning moment. Gradebook turns those moments into clear, actionable insight.

Generate `af_heart`, `af_bella`, `af_nicole`, and `af_sarah` into `output/audio/auditions/`.

Run: `node scripts/audition.mjs`

Expected: four non-empty WAV files readable by `ffprobe`.

- [ ] **Step 6: Verify and commit**

Run: `node --test test/kokoro.test.mjs && npm.cmd audit --audit-level=high`

Commit: `feat: add local Kokoro WASM narration`

### Task 2: Establish the Frame-Accurate Cue Sheet

**Files:**
- Create: `video-studio/timeline/cues.json`
- Create: `video-studio/src/cues.mjs`
- Create: `video-studio/test/cues.test.mjs`

**Interfaces:**
- Produces: `loadCues(path): Promise<Timeline>`
- Produces: `validateTimeline(timeline): void`
- Produces: `frameToSeconds(frame, fps = 30): number`

- [ ] **Step 1: Write timing validation tests**

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import {frameToSeconds, validateTimeline} from '../src/cues.mjs';

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
```

- [ ] **Step 2: Confirm the tests fail**

Run: `node --test test/cues.test.mjs`

Expected: FAIL because the cue module does not exist.

- [ ] **Step 3: Implement strict cue validation**

Validate `fps === 30`, `totalFrames === 1800`, integer frame values, ordered
scene ranges, in-range narration/SFX cues, non-empty captions, and unique IDs.
Return seconds only through `frameToSeconds`.

- [ ] **Step 4: Create the six-scene cue sheet**

Use scene boundaries `0`, `180`, `540`, `1020`, `1440`, `1680`, and `1800`.
Store narration text per scene, but leave measured `durationFrames` absent until
Task 3 writes the derived narration metadata.

- [ ] **Step 5: Verify and commit**

Run: `node --test test/cues.test.mjs`

Commit: `feat: add frame-accurate audiovisual cue sheet`

### Task 3: Generate and Measure Final Narration

**Files:**
- Create: `video-studio/scripts/narrate.mjs`
- Create: `video-studio/output/audio/narration.json`
- Modify: `video-studio/timeline/cues.json`
- Create: `video-studio/test/narration.test.mjs`

**Interfaces:**
- Consumes: `loadKokoro`, `generateWav`, and `loadCues`
- Produces: `narration.json` entries shaped as `{id, file, startFrame, durationFrames, text}`

- [ ] **Step 1: Write the narration metadata test**

Assert every spoken scene has a WAV file, positive measured duration, a start
frame within its scene, and an end frame no later than the next scene boundary.

- [ ] **Step 2: Confirm the test fails without generated metadata**

Run: `node --test test/narration.test.mjs`

Expected: FAIL because `output/audio/narration.json` does not exist.

- [ ] **Step 3: Select the warmest consistent audition**

Listen to all four auditions at the same normalized playback level. Choose the
voice that is clearest on “ToyWorld,” “Gradebook,” and “actionable.” Record the
chosen voice ID in `timeline/cues.json`.

- [ ] **Step 4: Generate sentence-level WAV files**

For every narration cue, generate a WAV with the selected voice. Measure duration
using:

```powershell
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 <file.wav>
```

Convert each duration to frames with `Math.ceil(seconds * 30)`. Fail if any
sentence crosses its scene boundary; adjust punctuation or speed between 0.94
and 1.06 and regenerate instead of truncating speech.

- [ ] **Step 5: Verify and commit**

Run: `node --test test/narration.test.mjs`

Commit: `feat: generate timed Gradebook narration`

### Task 4: Acquire and Document Licensed Music and Effects

**Files:**
- Create: `video-studio/assets/audio/manifest.json`
- Create: `video-studio/assets/audio/source/*`
- Create: `video-studio/test/assets.test.mjs`

**Interfaces:**
- Produces: manifest entries shaped as `{id, role, title, creator, sourceUrl, licenseUrl, downloadedAt, file}`

- [ ] **Step 1: Write manifest validation tests**

Require exactly one `music` entry and no more than six `sfx` entries. Require
HTTPS source/license URLs, ISO download dates, unique IDs, and existing files.

- [ ] **Step 2: Select assets**

Search Mixkit for a restrained technology/corporate instrumental without vocals,
trailer drums, or dense lead melodies. Select quiet UI, whoosh, insight, and
closing sounds under the Mixkit Free License. Prefer a single creator/library
style where practical.

- [ ] **Step 3: Download through the official asset pages**

Save originals under `assets/audio/source/`. Record each final asset page URL,
creator, displayed title, download date, and `https://mixkit.co/license/` in the
manifest. Do not scrape or use a third-party mirror.

- [ ] **Step 4: Verify and commit**

Run: `node --test test/assets.test.mjs`

Commit: `chore: add licensed product demo audio assets`

### Task 5: Make Visual Rendering Cue-Driven

**Files:**
- Modify: `video-studio/public/frame.html`
- Modify: `video-studio/scripts/render.mjs`
- Create: `video-studio/test/render-contract.test.mjs`

**Interfaces:**
- Consumes: serialized timeline data and requested `frame`
- Produces: `output/gradebook-toyworld-silent.mp4`

- [ ] **Step 1: Write the scene-selection contract test**

Test boundary frames `0`, `179`, `180`, `539`, `540`, `1019`, `1020`, `1439`,
`1440`, `1679`, `1680`, and `1799`. Each must map to exactly one scene.

- [ ] **Step 2: Implement scene selection and frame state**

Expose `sceneForFrame(timeline, frame)` from `src/cues.mjs`. Pass the timeline
to the browser page and render scene-local progress as:

```js
const localProgress =
  (frame - scene.startFrame) / (scene.endFrame - scene.startFrame);
```

- [ ] **Step 3: Build the six visual scenes**

Render ToyWorld establishment, interaction activity, Gradebook signal
transformation, teacher insights, product payoff, and closing identity. Show
captions only during their cue ranges and keep title-safe margins.

- [ ] **Step 4: Render and verify the silent master**

Run: `npm.cmd run render`

Expected: H.264, 1920×1080, 30 fps, exactly 1,800 frames and 60 seconds.

- [ ] **Step 5: Commit**

Commit: `feat: render cue-driven 60-second product demo`

### Task 6: Build the Deterministic Audio Mix

**Files:**
- Create: `video-studio/src/audio-graph.mjs`
- Create: `video-studio/scripts/mix.mjs`
- Create: `video-studio/test/audio-graph.test.mjs`
- Remove: `video-studio/scripts/master.ps1`
- Remove: `video-studio/scripts/narrate.ps1`

**Interfaces:**
- Consumes: timeline, narration metadata, asset manifest
- Produces: `buildAudioGraph({timeline, narration, assets}): {inputs, filterComplex, maps}`
- Produces: `output/gradebook-toyworld-final.mp4`

- [ ] **Step 1: Write filter-graph tests**

Assert the graph uses frame-derived start times, `adelay` for every timed element,
stereo conversion, narration-aware music ducking, `amix`, `aresample=48000`,
and final `loudnorm`. Assert the final FFmpeg arguments do not contain
`-shortest`.

- [ ] **Step 2: Implement narration and effect placement**

For cue frame `F`, generate delay milliseconds as:

```js
const delayMs = Math.round((F / 30) * 1000);
const delay = `adelay=${delayMs}|${delayMs}`;
```

Normalize each narration segment before placement. Use cue gains for effects and
short fades to avoid clicks.

- [ ] **Step 3: Implement music shaping and ducking**

Trim or loop music to exactly 60 seconds. Use a narration bus as the sidechain
input to `sidechaincompress`, with smooth attack/release, then mix the ducked
music, narration bus, and SFX bus.

- [ ] **Step 4: Implement final two-pass loudness normalization**

Measure the complete mix with `loudnorm=I=-14:TP=-1:LRA=7:print_format=json`,
parse the reported values, then render with those measurements in the second
pass. Resample the final mix to 48 kHz stereo.

- [ ] **Step 5: Mux without truncation**

Map the silent video and mastered audio, copy the H.264 stream, encode AAC at
192 kbps, set output duration explicitly to `60`, and add `+faststart`.

- [ ] **Step 6: Verify and commit**

Run: `node --test test/audio-graph.test.mjs && node scripts/mix.mjs`

Commit: `feat: add synchronized production audio mix`

### Task 7: End-to-End Synchronization and Quality Gate

**Files:**
- Create: `video-studio/scripts/verify.mjs`
- Create: `video-studio/test/final-media.test.mjs`
- Modify: `video-studio/package.json`
- Modify: `video-studio/README.md`

**Interfaces:**
- Produces: `npm run production`
- Produces: `npm run verify`

- [ ] **Step 1: Add final media assertions**

Use `ffprobe` JSON to assert H.264 video, AAC audio, 1920×1080, 30 fps, exactly
1,800 video frames, 48 kHz stereo, start times within one audio sample of zero,
and duration within one video frame of 60 seconds.

- [ ] **Step 2: Add cue-boundary review frames**

Extract PNGs at frames `0`, `180`, `540`, `1020`, `1440`, and `1680` into
`output/review/`. Name each file with its scene ID.

- [ ] **Step 3: Add production scripts**

```json
{
  "scripts": {
    "audition": "node scripts/audition.mjs",
    "narrate": "node scripts/narrate.mjs",
    "render": "node scripts/render.mjs",
    "mix": "node scripts/mix.mjs",
    "verify": "node scripts/verify.mjs",
    "production": "npm run narrate && npm run render && npm run mix && npm run verify",
    "test": "node --test test/*.test.mjs"
  }
}
```

- [ ] **Step 4: Run the complete production gate**

Run: `npm.cmd test && npm.cmd run production && npm.cmd audit --audit-level=high`

Expected: all tests pass, final MP4 passes every stream/timing assertion, and npm
reports no high-severity vulnerability.

- [ ] **Step 5: Perform playback review**

Watch the entire final video with headphones and speakers. Confirm speech remains
intelligible, music ducking is smooth, effects reinforce visible actions, no cue
feels early or late, and the final chime resolves before frame 1,800.

- [ ] **Step 6: Commit**

Commit: `feat: complete synced Gradebook product demo`
