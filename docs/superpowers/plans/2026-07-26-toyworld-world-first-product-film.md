# ToyWorld World-First Product Film Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a 100–120 second hackathon film whose primary footage is a real recording of the ToyWorld Three.js website, with continuous narration explaining the environment, problem, experiment, Gradebook mechanism, results, and broader applicability.

**Architecture:** Extend the real viewer with a narrow deterministic demo-control interface, then use Playwright to record a scheduled sequence of real website camera passes and interactions. A frame-addressed production cue sheet drives both recording actions and a continuous Kokoro narration mix; FFmpeg trims, overlays, masters, and muxes the recorded footage without replacing it with simulated UI.

**Tech Stack:** Three.js 0.179, TypeScript 5.9, Vite 7, Playwright 1.62, Kokoro.js 1.2 WASM, Node.js 24, FFmpeg 8.1, Vitest 3.2.

## Global Constraints

- Target duration is 100–120 seconds; clarity determines the exact duration.
- The real `viewer` application must occupy approximately 85–90% of the film.
- Capture and deliver at 1920×1080.
- Required views: slow orbit, top-down, street, follow-selected-agent, HUD metrics, and completed result.
- Narration must explain the environment, problem, purpose, experiment, Gradebook mechanism, result, and broader applicability.
- Narration continues across camera changes; no unintended long narration gaps.
- Use only restrained chapter titles, metric callouts, crops, and identity graphics.
- Final audio target is approximately −14 LUFS integrated and no more than −1 dBTP.
- Final delivery is H.264 High Profile with 48 kHz stereo AAC.
- Do not invent results not present in the committed run.

---

## File Structure

- `viewer/src/scene.ts`: owns Three.js camera behavior and exposes deterministic orbit and agent-selection controls.
- `viewer/src/main.ts`: publishes the narrow `window.toyWorldDemo` recording interface after the actual app boots.
- `viewer/src/demo-api.ts`: typed interface for recorder-safe playback, camera, and result controls.
- `viewer/src/demo-api.test.ts`: contract tests for demo actions and camera names.
- `video-studio/timeline/world-first-cues.json`: single frame-addressed source of truth for chapters, narration, camera actions, and overlays.
- `video-studio/src/world-first-cues.mjs`: validation and time/frame conversion.
- `video-studio/test/world-first-cues.test.mjs`: duration, coverage, narrative-density, and required-shot tests.
- `video-studio/scripts/world-first-narrate.mjs`: paragraph-level Kokoro generation and narration metadata.
- `video-studio/src/silence.mjs`: FFmpeg silence-detection parsing and narration-gap validation.
- `video-studio/test/silence.test.mjs`: silence-policy tests.
- `video-studio/scripts/record-toyworld.mjs`: starts the real viewer and records scheduled camera passes through Playwright.
- `video-studio/src/recording-plan.mjs`: converts cue actions into deterministic recorder operations.
- `video-studio/test/recording-plan.test.mjs`: recording order and required-view tests.
- `video-studio/scripts/world-first-mix.mjs`: continuous narration, music ducking, effects, and loudness master.
- `video-studio/scripts/world-first-master.mjs`: trims real footage, applies restrained overlays, muxes mastered audio, and verifies delivery streams.
- `video-studio/scripts/world-first-verify.mjs`: machine-readable final timing, frame, audio, and real-footage checks.
- `video-studio/README.md`: revised production commands and final artifact location.

---

### Task 1: Deterministic Demo Controls in the Real Viewer

**Files:**
- Create: `viewer/src/demo-api.ts`
- Create: `viewer/src/demo-api.test.ts`
- Modify: `viewer/src/scene.ts`
- Modify: `viewer/src/main.ts`

**Interfaces:**
- Produces: `ToyWorldDemoApi` with `setCamera(preset)`, `setOrbit(enabled)`, `setSpeed(speed)`, `restart()`, `completeRun()`, and `getStatus()`.
- Produces: `RaceScene.setOrbit(enabled: boolean)` and `RaceScene.selectFirstActiveAgent(): boolean`.
- Consumes: existing `RaceScene`, `createHud`, playback callbacks, and real committed run data.

- [ ] **Step 1: Write the failing demo-interface test**

```ts
import { describe, expect, it } from "vitest";
import { CAMERA_PRESETS, isDemoSpeed } from "./demo-api";

describe("ToyWorld demo API", () => {
  it("contains every camera view required by the film", () => {
    expect(CAMERA_PRESETS).toEqual(["overview", "orbit", "top", "chase", "follow"]);
  });

  it("allows only viewer-supported replay speeds", () => {
    expect(isDemoSpeed(4)).toBe(true);
    expect(isDemoSpeed(3)).toBe(false);
  });
});
```

- [ ] **Step 2: Run the targeted test and verify red**

Run: `npm.cmd test -- --run src/demo-api.test.ts` from `viewer/`

Expected: FAIL because `demo-api.ts` does not exist.

- [ ] **Step 3: Implement the typed demo contract**

```ts
export const CAMERA_PRESETS = ["overview", "orbit", "top", "chase", "follow"] as const;
export type DemoCamera = typeof CAMERA_PRESETS[number];
export type DemoSpeed = 0.5 | 1 | 2 | 4;

export const isDemoSpeed = (value: number): value is DemoSpeed =>
  value === 0.5 || value === 1 || value === 2 || value === 4;

export interface ToyWorldDemoApi {
  setCamera(camera: DemoCamera): void;
  setOrbit(enabled: boolean): void;
  setSpeed(speed: DemoSpeed): void;
  restart(): void;
  completeRun(): void;
  getStatus(): { decisions: number; correct: number; cost: number; state: string };
}
```

- [ ] **Step 4: Add real-scene orbit and selection controls**

In `RaceScene`, add:

```ts
setOrbit(enabled: boolean) {
  this.controls.autoRotate = enabled;
  this.controls.autoRotateSpeed = 0.55;
}

selectFirstActiveAgent(): boolean {
  const candidate = this.active.find((record) => !record.completed);
  if (!candidate) return false;
  this.selected = candidate;
  this.setCameraPreset("follow");
  return true;
}
```

Extend `setCameraPreset` so `"orbit"` returns to the overview position and enables auto-rotation; all other presets disable auto-rotation.

- [ ] **Step 5: Publish the recording API only after successful boot**

In `main.ts`, retain the current real viewer behavior and assign
`window.toyWorldDemo` to methods backed by the existing `play`, `scene`, `hud`,
and `progress`. `completeRun()` must update the HUD with `run.totals`; it must not
fabricate values.

- [ ] **Step 6: Verify the actual viewer**

Run:

```powershell
npm.cmd test -- --run
npm.cmd run build
```

Expected: all Vitest tests pass and Vite production build succeeds.

- [ ] **Step 7: Commit**

```powershell
git add viewer/src/demo-api.ts viewer/src/demo-api.test.ts viewer/src/scene.ts viewer/src/main.ts
git commit -m "feat: add deterministic ToyWorld demo controls"
```

---

### Task 2: World-First Cue Sheet and Continuous Script

**Files:**
- Create: `video-studio/timeline/world-first-cues.json`
- Create: `video-studio/src/world-first-cues.mjs`
- Create: `video-studio/test/world-first-cues.test.mjs`

**Interfaces:**
- Produces: `validateWorldFirstCues(cues)` and `frameToSeconds(frame, fps)`.
- Produces: cue fields `chapters`, `narration`, `cameraActions`, `overlays`, `music`, and `effects`.
- Consumes: committed run facts: 20 junctions, 7 models, 420 decisions, and the three decision types.

- [ ] **Step 1: Write failing cue-sheet tests**

```js
test("world-first film contains every required real-viewer shot", async () => {
  const cues = await loadWorldFirstCues();
  const cameras = new Set(cues.cameraActions.map((action) => action.camera));
  for (const required of ["orbit", "top", "chase", "follow", "overview"]) {
    assert.ok(cameras.has(required), `missing ${required}`);
  }
});

test("narration has no unexplained gap longer than 1.4 seconds", async () => {
  const cues = await loadWorldFirstCues();
  for (let index = 1; index < cues.narration.length; index += 1) {
    const before = cues.narration[index - 1];
    const current = cues.narration[index];
    assert.ok(current.startFrame - before.endFrame <= Math.round(cues.fps * 1.4));
  }
});
```

- [ ] **Step 2: Run the tests and verify red**

Run: `npm.cmd test -- --test-name-pattern="world-first"` from `video-studio/`

Expected: FAIL because the cue loader and JSON do not exist.

- [ ] **Step 3: Implement cue validation**

Validate:

- 30 fps;
- total duration between 3,000 and 3,600 frames;
- ordered, non-overlapping chapters;
- required camera views;
- all narration segments have nonblank text and frame bounds;
- no designed narration gap over 42 frames;
- all result claims are copied from `viewer/public/data/run.json`;
- final chapter ends exactly at `totalFrames`.

- [ ] **Step 4: Write the continuous narration and shot schedule**

Use eight connected paragraphs:

1. world introduction;
2. observability problem;
3. controlled experiment;
4. live visual language;
5. one agent’s machine-checkable choice;
6. Gradebook mechanism;
7. completed results;
8. broader applicability.

Schedule narration to begin by frame 24 and continue through the closing chapter.
Keep paragraph gaps between 12 and 30 frames. Schedule camera actions under the
sentences they illustrate, not between paragraphs.

- [ ] **Step 5: Run the targeted and full studio tests**

Run:

```powershell
npm.cmd test -- --test-name-pattern="world-first"
npm.cmd test
```

Expected: targeted tests and the full suite pass.

- [ ] **Step 6: Commit**

```powershell
git add video-studio/timeline/world-first-cues.json video-studio/src/world-first-cues.mjs video-studio/test/world-first-cues.test.mjs
git commit -m "feat: add continuous world-first demo timeline"
```

---

### Task 3: Continuous Kokoro Narration and Silence Policy

**Files:**
- Create: `video-studio/scripts/world-first-narrate.mjs`
- Create: `video-studio/src/silence.mjs`
- Create: `video-studio/test/silence.test.mjs`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: `world-first-cues.json` narration segments and existing `generateVoiceJobs`.
- Produces: `output/world-first/audio/narration/*.wav`.
- Produces: `output/world-first/audio/narration.json` with measured `durationFrames` and `endFrame`.
- Produces: `output/world-first/audio/narration-preview.wav`, with all paragraphs placed at their cue frames.
- Produces: `parseSilenceDetect(stderr)` and `assertNarrationDensity(events, maxGapSeconds)`.

- [ ] **Step 1: Write failing silence-parser tests**

```js
test("silence parser identifies an unintended two-second gap", () => {
  const events = parseSilenceDetect(
    "[silencedetect] silence_start: 4.2\n[silencedetect] silence_end: 6.4 | silence_duration: 2.2",
  );
  assert.deepEqual(events, [{start: 4.2, end: 6.4, duration: 2.2}]);
  assert.throws(() => assertNarrationDensity(events, 1.4), /2.2 second silence/);
});
```

- [ ] **Step 2: Verify the silence test fails**

Run: `npm.cmd test -- --test-name-pattern="silence parser"`

Expected: FAIL because `silence.mjs` does not exist.

- [ ] **Step 3: Implement silence parsing and density validation**

Parse paired `silence_start` and `silence_end` lines. Ignore leading silence
before narration and trailing silence after the last word; reject internal
silence longer than 1.4 seconds unless the cue sheet explicitly marks it as a
dramatic pause.

- [ ] **Step 4: Generate paragraph-level narration**

Use `af_heart` and the existing browser WASM generator. Generate each narrative
paragraph as one WAV so clause boundaries remain natural. Probe every output
with `ffprobe`, write measured metadata, and fail if a segment cannot fit before
the next scheduled paragraph with at least a 12-frame crossfade allowance.
Create `narration-preview.wav` by placing each paragraph at its cue-derived
timestamp and trimming the result to `totalFrames / fps`.

- [ ] **Step 5: Add the command**

Add:

```json
"world:narrate": "node scripts/world-first-narrate.mjs"
```

- [ ] **Step 6: Generate and verify narration**

Run:

```powershell
npm.cmd run world:narrate
ffmpeg -i output/world-first/audio/narration-preview.wav -af silencedetect=n=-42dB:d=1.4 -f null NUL
npm.cmd test
```

Expected: all paragraph files exist; no unintended internal silence exceeds 1.4 seconds; tests pass.

- [ ] **Step 7: Commit**

```powershell
git add video-studio/scripts/world-first-narrate.mjs video-studio/src/silence.mjs video-studio/test/silence.test.mjs video-studio/package.json
git commit -m "feat: generate continuous world-first narration"
```

---

### Task 4: Real ToyWorld Website Recording

**Files:**
- Create: `video-studio/src/recording-plan.mjs`
- Create: `video-studio/test/recording-plan.test.mjs`
- Create: `video-studio/scripts/record-toyworld.mjs`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: `cameraActions` from `world-first-cues.json`.
- Consumes: `window.toyWorldDemo` from Task 1.
- Produces: ordered `{atFrame, operation, value}` recording actions.
- Produces: `output/world-first/footage/toyworld-live.webm`.
- Produces: `output/world-first/footage/recording.json` with viewport, duration, action log, and source URL.

- [ ] **Step 1: Write failing recording-plan tests**

```js
test("recording plan begins with a real orbit and ends on completed results", () => {
  const plan = buildRecordingPlan(sampleCues);
  assert.deepEqual(plan[0], {atFrame: 0, operation: "camera", value: "orbit"});
  assert.equal(plan.at(-1).operation, "completeRun");
});

test("recording plan includes follow-agent selection before follow camera", () => {
  const plan = buildRecordingPlan(sampleCues);
  const select = plan.findIndex((action) => action.operation === "selectAgent");
  const follow = plan.findIndex((action) => action.value === "follow");
  assert.ok(select >= 0 && select < follow);
});
```

- [ ] **Step 2: Run and verify red**

Run: `npm.cmd test -- --test-name-pattern="recording plan"`

Expected: FAIL because the recording-plan module does not exist.

- [ ] **Step 3: Implement deterministic recording actions**

Convert frame times to milliseconds using `Math.round(frame * 1000 / fps)`.
Allow only:

- `camera`;
- `orbit`;
- `speed`;
- `restart`;
- `selectAgent`;
- `completeRun`.

Reject unordered actions and unsupported camera values.

- [ ] **Step 4: Implement the real-site recorder**

The script must:

1. start `npm.cmd run dev -- --host 127.0.0.1` in `viewer/`;
2. wait for the printed Vite URL;
3. launch Edge through Playwright with a 1920×1080 video context;
4. navigate to the actual viewer;
5. verify `window.toyWorldDemo` exists;
6. set replay speed to 4×;
7. execute cue actions against the real API at frame-derived wall-clock times;
8. preserve the visible HUD, controls, map attribution, routes, and Three.js canvas;
9. save the context video as `toyworld-live.webm`;
10. write the action log and terminate only the Vite process it started.

- [ ] **Step 5: Add the command**

Add:

```json
"world:record": "node scripts/record-toyworld.mjs"
```

- [ ] **Step 6: Record and prove the footage is real**

Run:

```powershell
npm.cmd run world:record
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of json output/world-first/footage/toyworld-live.webm
```

Expected: a 1920×1080 browser-recorded WebM whose duration matches the cue sheet within one frame.

Extract review frames at orbit, top, street, follow, HUD, and completed-result
timestamps. Visually verify that each image contains the real viewer canvas or
HUD and the required state.

- [ ] **Step 7: Commit**

```powershell
git add video-studio/src/recording-plan.mjs video-studio/test/recording-plan.test.mjs video-studio/scripts/record-toyworld.mjs video-studio/package.json
git commit -m "feat: record scheduled real ToyWorld footage"
```

---

### Task 5: Continuous Audio Mix

**Files:**
- Create: `video-studio/scripts/world-first-mix.mjs`
- Modify: `video-studio/src/audio-graph.mjs`
- Modify: `video-studio/test/audio-graph.test.mjs`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: paragraph WAVs, world-first cue sheet, and licensed asset manifest.
- Produces: `output/world-first/audio/master.wav`.
- Produces: exact-duration 48 kHz stereo audio with music sidechain ducking.

- [ ] **Step 1: Add a failing long-form graph test**

```js
test("long-form mix pads and trims to the cue-sheet duration", () => {
  const graph = buildAudioGraph({
    fps: 30,
    totalFrames: 3360,
    narration,
    effects,
  });
  assert.match(graph, /apad=whole_dur=112/);
  assert.match(graph, /atrim=duration=112/);
  assert.match(graph, /sidechaincompress/);
});
```

- [ ] **Step 2: Run and verify red**

Run: `npm.cmd test -- --test-name-pattern="long-form mix"`

Expected: FAIL because the existing graph is hard-coded to 60 seconds.

- [ ] **Step 3: Generalize the audio graph**

Accept `totalFrames`, derive `durationSeconds = totalFrames / fps`, and use it
for music trim, fades, voice-bus padding, and final trim. Preserve 48 kHz
resampling and narration-led sidechain compression.

- [ ] **Step 4: Implement the world-first mix**

Mix the new paragraph narration, the documented Mixkit music bed, and only the
effects present in the new cue sheet. Apply final loudness processing with
`level=false` limiter behavior so AAC encoding remains below −1 dBTP.

- [ ] **Step 5: Add the command**

Add:

```json
"world:mix": "node scripts/world-first-mix.mjs"
```

- [ ] **Step 6: Verify duration, channels, silence, and loudness**

Run:

```powershell
npm.cmd run world:mix
ffprobe -v error -show_entries format=duration:stream=sample_rate,channels -of json output/world-first/audio/master.wav
ffmpeg -i output/world-first/audio/master.wav -af silencedetect=n=-42dB:d=1.4 -f null NUL
ffmpeg -i output/world-first/audio/master.wav -filter_complex ebur128=peak=true -f null NUL
```

Expected: exact cue duration, 48 kHz stereo, no unintended internal narration
gap over 1.4 seconds, approximately −14 LUFS, and true peak no higher than
−1 dBTP.

- [ ] **Step 7: Commit**

```powershell
git add video-studio/scripts/world-first-mix.mjs video-studio/src/audio-graph.mjs video-studio/test/audio-graph.test.mjs video-studio/package.json
git commit -m "feat: master continuous world-first audio"
```

---

### Task 6: Master the Real Footage with Restrained Overlays

**Files:**
- Create: `video-studio/scripts/world-first-master.mjs`
- Create: `video-studio/src/overlay-plan.mjs`
- Create: `video-studio/test/overlay-plan.test.mjs`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: real WebM footage, master WAV, and `overlays` from the cue sheet.
- Produces: `output/world-first/gradebook-toyworld-world-first.mp4`.
- Produces: `buildOverlayFilters(overlays, fps)` with frame-derived enable expressions.

- [ ] **Step 1: Write failing restrained-overlay tests**

```js
test("overlay plan contains only approved graphic types", () => {
  const filters = buildOverlayFilters([
    {kind: "chapter", text: "A controlled world", startFrame: 30, endFrame: 150},
    {kind: "metric", text: "420 checkable decisions", startFrame: 900, endFrame: 1080},
  ], 30);
  assert.equal(filters.length, 2);
});

test("overlay plan rejects unsupported full-screen mock UI", () => {
  assert.throws(
    () => buildOverlayFilters([{kind: "mock-ui", startFrame: 0, endFrame: 30}], 30),
    /unsupported overlay kind/,
  );
});
```

- [ ] **Step 2: Run and verify red**

Run: `npm.cmd test -- --test-name-pattern="overlay plan"`

Expected: FAIL because `overlay-plan.mjs` does not exist.

- [ ] **Step 3: Implement overlay filters**

Support only `chapter`, `metric`, and `identity`. Derive `enable` start/end
seconds from integer frames. Use dark translucent backing, white text, and the
existing teal accent. Keep overlays inside safe margins and away from the
viewer’s side HUD.

- [ ] **Step 4: Implement the final master**

Use the real recording as the sole video input. Trim to the cue duration, apply
the approved overlays, and mux the mastered audio. Do not use `-shortest`.
Encode H.264 High Profile, `yuv420p`, 30 fps, AAC 256 kb/s, 48 kHz stereo, and
`+faststart`.

- [ ] **Step 5: Add the command**

Add:

```json
"world:master": "node scripts/world-first-master.mjs"
```

- [ ] **Step 6: Render and visually review**

Run `npm.cmd run world:master`.

Extract frames at every chapter and camera boundary. Confirm the real Three.js
world is visible for at least 85% of sampled story frames and no overlay hides
the decision drawer or hero metrics.

- [ ] **Step 7: Commit**

```powershell
git add video-studio/scripts/world-first-master.mjs video-studio/src/overlay-plan.mjs video-studio/test/overlay-plan.test.mjs video-studio/package.json
git commit -m "feat: master real ToyWorld product film"
```

---

### Task 7: End-to-End Verification and Handoff

**Files:**
- Create: `video-studio/scripts/world-first-verify.mjs`
- Create: `video-studio/test/world-first-verify.test.mjs`
- Modify: `video-studio/README.md`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: final MP4, cue sheet, narration metadata, recording action log.
- Produces: `output/world-first/verification.json`.
- Produces: a nonzero exit code for frame, timing, audio, narration-density, or required-shot failures.

- [ ] **Step 1: Write failing verification tests**

```js
test("delivery validation rejects audio/video drift", () => {
  assert.throws(
    () => validateDelivery({
      expectedFrames: 3360,
      videoFrames: 3360,
      videoStart: 0,
      audioStart: 0.04,
      videoDuration: 112,
      audioDuration: 112,
    }),
    /start-time drift/,
  );
});
```

- [ ] **Step 2: Run and verify red**

Run: `npm.cmd test -- --test-name-pattern="delivery validation"`

Expected: FAIL because the verification module does not exist.

- [ ] **Step 3: Implement final verification**

Verify:

- H.264 High Profile;
- 1920×1080;
- 30 fps;
- exact expected frame count;
- audio and video start at 0;
- audio and video duration equal the cue duration;
- 48 kHz stereo AAC;
- all required camera actions appear in `recording.json`;
- silence report passes;
- caption text equals narration text;
- source footage path and URL identify the real viewer.

- [ ] **Step 4: Update commands and documentation**

Add:

```json
"world:verify": "node scripts/world-first-verify.mjs",
"world:build": "npm run world:narrate && npm run world:record && npm run world:mix && npm run world:master && npm run world:verify"
```

Document prerequisites, all individual commands, the one-command build, review
frames, license manifest, and final artifact path.

- [ ] **Step 5: Run fresh full verification**

Run:

```powershell
npm.cmd test
npm.cmd run check
npm.cmd run world:verify
```

Also run from `viewer/`:

```powershell
npm.cmd test -- --run
npm.cmd run build
```

Expected: all suites pass, viewer builds, and `verification.json` records every
delivery requirement as passed.

- [ ] **Step 6: Perform full playback review**

Watch the final film from beginning to end. Confirm:

- narration is continuous and intelligible;
- each spoken topic matches the visible camera pass;
- orbit motion is smooth;
- the environment remains the visual centerpiece;
- the completed metrics are legible;
- the ending states the broader Gradebook result.

- [ ] **Step 7: Commit**

```powershell
git add video-studio/scripts/world-first-verify.mjs video-studio/test/world-first-verify.test.mjs video-studio/README.md video-studio/package.json
git commit -m "test: verify world-first product film delivery"
```
