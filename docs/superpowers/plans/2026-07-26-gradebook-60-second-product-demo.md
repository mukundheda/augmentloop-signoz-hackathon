# Gradebook 60-Second Product Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a polished, narrated 1080p MP4 that explains Gradebook through the Pune ToyWorld in 58–62 seconds.

**Architecture:** A deterministic Node-based renderer will generate the composited visual frames from actual repository assets and captured ToyWorld footage. PowerShell speech synthesis will create the narration WAV, and FFmpeg will combine narration, captions, subtle generated music, and frames into the final MP4. Automated probes will verify duration, dimensions, streams, captions, and factual copy.

**Tech Stack:** TypeScript/Vite/Three.js viewer, Node.js, Playwright, Sharp, PowerShell `System.Speech`, FFmpeg 8.1, FFprobe

## Global Constraints

- Runtime must be between 58 and 62 seconds.
- Frame must be 16:9 at 1920×1080.
- Delivery must be MP4 with professional English narration, burned-in captions, and subtle electronic background music.
- Existing project visuals and actual product footage take priority over decorative imagery.
- Displayed metrics must match the committed run: 420 decisions, 268 correct, $0.403804 spent, and $0.001507 per correct decision.
- Math is blue, reality is amber, correct is green, wrong is red, and the optimal ghost route is yellow.
- AI-judge opinions must be visibly separated and excluded from the headline metric.
- Captions must remain within title-safe margins, and important meaning must not depend on color alone.

---

## File map

- Create `video/script.json`: canonical narration, captions, scene timing, and data callouts.
- Create `video/render.mjs`: deterministic frame compositor and timeline renderer.
- Create `video/capture-viewer.mjs`: Playwright capture of actual ToyWorld animation.
- Create `video/synthesize-narration.ps1`: Windows narration generation.
- Create `video/build.ps1`: reproducible end-to-end production command.
- Create `video/tests/validate-script.mjs`: copy, timing, and metric validation.
- Create `video/tests/validate-output.ps1`: FFprobe-based media validation.
- Create `video/assets/`: generated captures and intermediate audio.
- Create `video/output/gradebook-60s-demo.mp4`: final deliverable.
- Modify `viewer/src/main.ts`: expose a capture-only deterministic playback hook without changing normal viewer behavior.
- Modify `viewer/src/replay.ts`: expose deterministic timeline seeking used by browser capture.
- Modify `viewer/src/replay.test.ts`: cover deterministic seeking.
- Modify `.gitignore`: ignore generated frames and intermediate audio while retaining the final MP4.

### Task 1: Lock the production timeline and factual copy

**Files:**
- Create: `video/script.json`
- Create: `video/tests/validate-script.mjs`

**Interfaces:**
- Produces: JSON object `{ durationSeconds: 60, scenes: Scene[] }`
- `Scene` fields: `{ id, start, end, narration, caption, visual, callouts }`
- Consumed by: `render.mjs`, `synthesize-narration.ps1`, and validation scripts

- [ ] **Step 1: Write the failing script validator**

Validate that scene IDs are unique, timings begin at zero, scenes are contiguous, the final scene ends at 60, every narration line has a caption, and the four committed metrics appear literally.

```js
const required = ["420 decisions", "268 correct", "$0.403804", "$0.001507"];
if (script.durationSeconds !== 60) throw new Error("durationSeconds must equal 60");
for (const value of required) {
  if (!JSON.stringify(script).includes(value)) throw new Error(`missing ${value}`);
}
```

- [ ] **Step 2: Run the validator and confirm it fails**

Run: `node video/tests/validate-script.mjs`

Expected: failure because `video/script.json` does not exist.

- [ ] **Step 3: Create the seven-scene canonical script**

Use the approved intervals `0–6`, `6–16`, `16–29`, `29–40`, `40–51`, `51–57`, and `57–60`. Preserve the approved narration and callouts from the design spec, with the numeric narration written for natural speech while the exact values remain in on-screen callouts.

- [ ] **Step 4: Run the validator**

Run: `node video/tests/validate-script.mjs`

Expected: `script valid: 7 scenes, 60 seconds`.

- [ ] **Step 5: Commit**

```powershell
git add video/script.json video/tests/validate-script.mjs
git commit -m "feat(video): lock 60-second demo timeline"
```

### Task 2: Add deterministic ToyWorld capture

**Files:**
- Modify: `viewer/src/replay.ts`
- Modify: `viewer/src/main.ts`
- Modify: `viewer/src/replay.test.ts`
- Create: `video/capture-viewer.mjs`

**Interfaces:**
- Produces browser global: `window.__GRADEBOOK_CAPTURE__.seek(seconds: number): void`
- Produces browser global: `window.__GRADEBOOK_CAPTURE__.ready: boolean`
- Produces: `video/assets/toyworld/frame-%05d.png`

- [ ] **Step 1: Add a failing replay seek test**

Test that seeking to the same timestamp twice returns the same agent positions and outcome state, and that seeking backward clears state created after the requested timestamp.

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `cd viewer; npm test -- --run src/replay.test.ts`

Expected: failure because deterministic seek is not exported.

- [ ] **Step 3: Implement deterministic seeking**

Add a replay method that derives state exclusively from the requested time and immutable run data. In capture mode, expose readiness and seeking on `window.__GRADEBOOK_CAPTURE__`; leave the existing interactive playback path unchanged.

- [ ] **Step 4: Capture the approved ToyWorld ranges**

Start Vite on `127.0.0.1:4173`, launch Chromium through the bundled Playwright runtime at a 1920×1080 viewport, wait for `ready`, seek once per output frame, and save PNGs for the `6–16`, `16–29`, `29–40`, and `51–57` scenes.

- [ ] **Step 5: Verify viewer and capture**

Run:

```powershell
cd viewer
npm test -- --run
npm run build
cd ..
node video/capture-viewer.mjs
```

Expected: all viewer tests pass, build succeeds, and the capture script reports the expected frame count with no blank frames.

- [ ] **Step 6: Commit**

```powershell
git add viewer/src/replay.ts viewer/src/main.ts viewer/src/replay.test.ts video/capture-viewer.mjs
git commit -m "feat(video): add deterministic ToyWorld capture"
```

### Task 3: Build the professional visual compositor

**Files:**
- Create: `video/render.mjs`
- Create: `video/tests/validate-frames.mjs`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `video/script.json`, ToyWorld captures, `docs/visuals/genome-strip.png`, `docs/visuals/span-link.png`, and verified SigNoz screenshots in the repository
- Produces: `video/assets/final-frames/frame-%05d.png`

- [ ] **Step 1: Write failing frame validation**

Validate frame count, 1920×1080 dimensions, non-empty pixel variance, and the presence of first and final frames.

- [ ] **Step 2: Run it and confirm it fails**

Run: `node video/tests/validate-frames.mjs`

Expected: failure because final frames are absent.

- [ ] **Step 3: Implement reusable composition primitives**

Implement functions for the dark background, title-safe captions, blue/amber provenance pills, numeric callouts, source-image fitting, cross-fades, restrained zooms, and end-card layout. Render at 30 fps.

- [ ] **Step 4: Compose all seven scenes**

Use actual ToyWorld frames for motion, the provenance strip and span-link artwork for grading, and verified SigNoz product imagery for observability. Add textual labels wherever color conveys provenance or correctness.

- [ ] **Step 5: Render and validate**

Run:

```powershell
node video/render.mjs
node video/tests/validate-frames.mjs
```

Expected: `1800 valid frames at 1920x1080`.

- [ ] **Step 6: Commit**

```powershell
git add .gitignore video/render.mjs video/tests/validate-frames.mjs
git commit -m "feat(video): compose Gradebook demo visuals"
```

### Task 4: Generate narration, captions, and soundtrack

**Files:**
- Create: `video/synthesize-narration.ps1`
- Create: `video/assets/captions.ass`
- Create: `video/assets/music.wav`

**Interfaces:**
- Consumes: `video/script.json`
- Produces: `video/assets/narration.wav`, `video/assets/captions.ass`, and `video/assets/music.wav`

- [ ] **Step 1: Implement narration generation**

Use `System.Speech.Synthesis.SpeechSynthesizer` with the best installed English voice, a measured rate, and per-scene silence padding. Generate a 48 kHz mono WAV aligned to the 60-second timeline.

- [ ] **Step 2: Generate title-safe captions**

Write ASS captions with a modern sans-serif face, white text, subtle shadow, maximum two lines, and bottom margin inside the title-safe region. Timings come directly from `script.json`.

- [ ] **Step 3: Generate subtle music**

Use FFmpeg audio sources to create a restrained 60-second electronic bed with no vocals, then high-pass/low-pass and normalize it. Keep its mix at least 18 dB below narration.

- [ ] **Step 4: Verify audio artifacts**

Run `ffprobe` on narration and music.

Expected: both are 48 kHz audio; narration is mono, music is stereo, and both cover the complete timeline.

- [ ] **Step 5: Commit**

```powershell
git add video/synthesize-narration.ps1
git commit -m "feat(video): add narration and caption pipeline"
```

### Task 5: Encode and verify the final MP4

**Files:**
- Create: `video/build.ps1`
- Create: `video/tests/validate-output.ps1`
- Create: `video/output/gradebook-60s-demo.mp4`

**Interfaces:**
- Consumes: final PNG frames, narration WAV, music WAV, and ASS captions
- Produces: H.264/AAC MP4 at `video/output/gradebook-60s-demo.mp4`

- [ ] **Step 1: Write the failing output validator**

Use FFprobe JSON to assert an H.264 video stream, AAC audio stream, 1920×1080 dimensions, 30 fps, and duration between 58 and 62 seconds.

- [ ] **Step 2: Confirm the validator fails**

Run: `powershell -ExecutionPolicy Bypass -File video/tests/validate-output.ps1`

Expected: failure because the MP4 is absent.

- [ ] **Step 3: Implement the reproducible build command**

Run script validation, ToyWorld capture, frame composition, narration generation, music generation, and FFmpeg encoding. Use `libx264`, `-pix_fmt yuv420p`, AAC audio, burned-in ASS captions, and `-movflags +faststart`.

- [ ] **Step 4: Build the video**

Run: `powershell -ExecutionPolicy Bypass -File video/build.ps1`

Expected: the final MP4 is created without dropped frames or FFmpeg errors.

- [ ] **Step 5: Run automated verification**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File video/tests/validate-output.ps1
```

Expected: `valid 1080p H.264/AAC video, duration 60 seconds`.

- [ ] **Step 6: Perform visual and audio QA**

Inspect frames near every scene boundary and play the complete MP4. Confirm captions are legible, narration is synchronized, music remains subordinate, product imagery is readable, facts match the committed run, and no scene contains blank or stale footage.

- [ ] **Step 7: Commit**

```powershell
git add video/build.ps1 video/tests/validate-output.ps1 video/output/gradebook-60s-demo.mp4
git commit -m "feat(video): deliver 60-second Gradebook demo"
```

