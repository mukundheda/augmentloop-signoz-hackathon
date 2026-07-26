# Gradebook Complete Hackathon Film Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an exactly three-minute, professional Gradebook hackathon product film that teaches integration and deployment, proves the contract through ToyWorld and CleanCut, and records the resulting observability in SigNoz.

**Architecture:** Add a separate `gradebook-complete` production path beside the existing 60-second and world-first paths. A validated 5,400-frame cue sheet and evidence manifest drive deterministic browser graphics, real application captures, narration, audio mixing, FFmpeg assembly, and a machine-readable verification report. Source adapters for ToyWorld, CleanCut, SigNoz, and repository tutorial visuals produce normalized 1920x1080/30 fps clips so the final assembly can use actual UI when available and verified evidence when it is not.

**Tech Stack:** Node.js ESM, Playwright with Microsoft Edge, FFmpeg/FFprobe, Kokoro-82M WASM, HTML/CSS/SVG, Python 3.10+, pytest, Foundry, Docker Compose, OpenTelemetry, SigNoz.

## Global Constraints

- Final duration is exactly 180.000 seconds and 5,400 frames at 30 fps.
- Delivery is 1920x1080 H.264 High Profile, YUV 4:2:0, AAC stereo at 48 kHz.
- Integrated loudness must be between -15 and -12.5 LUFS; true peak must not exceed -1 dBFS.
- No designed narration gap may exceed 1.2 seconds.
- Actual SigNoz UI is the preferred source; verified screenshots and committed JSON are the explicit fallback.
- Do not fabricate live UI, product behavior, telemetry, costs, outcomes, or model calls.
- Every displayed claim must map to committed evidence or an actual captured UI state.
- ToyWorld headline values are 420 decisions, 268 correct, 140 reality outcomes, $0.403804 total cost, and $0.001507 cost per correct decision.
- CleanCut visuals use committed synthetic samples or approved non-identifying local inputs only.
- No client-identifying CleanCut data may enter the repository, film, logs, or generated metadata.
- Use Evidence Noir: near-black/navy, white, teal math/telemetry, amber reality, and red failures.
- Preserve the existing `world:*`, 60-second, ToyWorld, Gradebook, and CleanCut pipelines.

---

## File structure

Create these focused units:

- `video-studio/timeline/gradebook-complete-cues.json`: the only frame-addressed editorial timeline.
- `video-studio/config/gradebook-complete-evidence.json`: claim-to-evidence mappings and source preferences.
- `video-studio/src/complete-cues.mjs`: cue/evidence loading and validation.
- `video-studio/src/complete-sources.mjs`: source selection, fallback rules, and normalized clip descriptors.
- `video-studio/src/complete-visuals.mjs`: deterministic scene state and Evidence Noir motion values.
- `video-studio/src/complete-video-graph.mjs`: normalized FFmpeg segment and assembly graph generation.
- `video-studio/src/complete-delivery.mjs`: delivery, claim, privacy, and source-coverage validation.
- `video-studio/public/gradebook-complete.html`: code, architecture, CleanCut, transition, and closing graphics only; never mock product UI.
- `video-studio/scripts/gradebook-complete-graphics.mjs`: frame renderer for approved graphics scenes.
- `video-studio/scripts/gradebook-complete-toyworld.mjs`: real ToyWorld excerpt preparation.
- `video-studio/scripts/gradebook-complete-signoz.mjs`: actual SigNoz capture with verified fallback.
- `video-studio/scripts/gradebook-complete-narrate.mjs`: continuous local narration.
- `video-studio/scripts/gradebook-complete-mix.mjs`: mastered music, effects, and narration.
- `video-studio/scripts/gradebook-complete-master.mjs`: final source normalization, assembly, and encode.
- `video-studio/scripts/gradebook-complete-verify.mjs`: media and evidence acceptance gate.
- Corresponding focused tests under `video-studio/test/`.

## Task 1: Lock the 5,400-frame editorial and evidence contract

**Files:**
- Create: `video-studio/timeline/gradebook-complete-cues.json`
- Create: `video-studio/config/gradebook-complete-evidence.json`
- Create: `video-studio/src/complete-cues.mjs`
- Create: `video-studio/test/complete-cues.test.mjs`

**Interfaces:**
- Produces: `loadCompleteCues(url?) -> Promise<CompleteCues>`
- Produces: `validateCompleteCues(cues, evidence) -> CompleteCues`
- Produces: cue fields `fps`, `totalFrames`, `width`, `height`, `chapters`, `narration`, `visualSegments`, `overlays`, `effects`, `claims`.
- Consumes: committed ToyWorld results, CleanCut sample paths, dashboard JSON, saved-view JSON, and approved design timings.

- [ ] **Step 1: Write failing timeline and evidence tests**

```js
test("complete film is exactly three minutes and covers every frame", async () => {
  const cues = await loadCompleteCues();
  assert.equal(cues.fps, 30);
  assert.equal(cues.totalFrames, 5400);
  assert.equal(cues.chapters[0].startFrame, 0);
  assert.equal(cues.chapters.at(-1).endFrame, 5400);
});

test("every displayed claim has committed evidence", async () => {
  const cues = await loadCompleteCues();
  assert.deepEqual(
    cues.claims.map(({id}) => id).sort(),
    ["cleancut-reality", "otel-event", "signoz-assets", "toyworld-result"].sort(),
  );
});
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="complete film|displayed claim"`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `src/complete-cues.mjs`.

- [ ] **Step 3: Implement the loader and strict validator**

```js
export function validateCompleteCues(cues, evidence) {
  if (cues.fps !== 30 || cues.totalFrames !== 5400) {
    throw new Error("complete film must be 5,400 frames at 30 fps");
  }
  assertContiguous(cues.chapters, cues.totalFrames, "chapters");
  assertContiguous(cues.visualSegments, cues.totalFrames, "visualSegments");
  assertNarrationGaps(cues.narration, 36);
  const evidenceIds = new Set(evidence.claims.map(({id}) => id));
  for (const claim of cues.claims) {
    if (!evidenceIds.has(claim.id)) throw new Error(`missing evidence for ${claim.id}`);
  }
  return cues;
}
```

The chapter boundaries are exactly `0`, `750`, `1500`, `2550`, `3450`, `4800`, and `5400`. Populate narration and visual segments for all six approved chapters. Use ASCII punctuation in machine-read timeline strings.

- [ ] **Step 4: Add real evidence mappings**

Map claims to:

```json
{
  "id": "toyworld-result",
  "paths": [
    "../toy-world/recordings/replay-v2.jsonl",
    "../viewer/public/data/run.json"
  ],
  "values": {
    "decisions": 420,
    "correct": 268,
    "realityOutcomes": 140,
    "totalCostUsd": 0.4038042399999995
  }
}
```

Also map `otel-event` to `reference-library/src/gradebook/recorder.py`, `cleancut-reality` to `cleancut-proof/src/cleancutproof/runner.py`, and `signoz-assets` to all ten files indexed by `dashboards/README.md`.

- [ ] **Step 5: Run focused and full video-studio tests**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="complete film|displayed claim"`

Expected: PASS.

Run: `cd video-studio && npm.cmd test`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add video-studio/timeline/gradebook-complete-cues.json video-studio/config/gradebook-complete-evidence.json video-studio/src/complete-cues.mjs video-studio/test/complete-cues.test.mjs
git commit -m "feat: define complete Gradebook film timeline"
```

## Task 2: Build deterministic Evidence Noir graphics

**Files:**
- Create: `video-studio/src/complete-visuals.mjs`
- Create: `video-studio/test/complete-visuals.test.mjs`
- Create: `video-studio/public/gradebook-complete.html`
- Create: `video-studio/scripts/gradebook-complete-graphics.mjs`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: `CompleteCues.visualSegments` from Task 1.
- Produces: `visualStateAtFrame(frame, segments) -> {segment, progress, enter, exit}`.
- Produces: `output/gradebook-complete/graphics/graphics.mp4`, 1920x1080, 30 fps, 5,400 frames, without audio.
- Browser interface: `window.renderFrame(frame: number): void`.

- [ ] **Step 1: Write failing deterministic state tests**

```js
test("complete visual state resolves exact boundaries", () => {
  const segments = [
    {id: "gap", startFrame: 0, endFrame: 750},
    {id: "instrument", startFrame: 750, endFrame: 1500},
  ];
  assert.equal(visualStateAtFrame(749, segments).segment.id, "gap");
  assert.equal(visualStateAtFrame(750, segments).segment.id, "instrument");
  assert.equal(visualStateAtFrame(750, segments).progress, 0);
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="complete visual state"`

Expected: FAIL because `complete-visuals.mjs` does not exist.

- [ ] **Step 3: Implement frame-derived state**

```js
export function visualStateAtFrame(frame, segments) {
  const segment = segments.find(({startFrame, endFrame}) => frame >= startFrame && frame < endFrame);
  if (!segment) throw new Error(`frame ${frame} is outside complete timeline`);
  const progress = (frame - segment.startFrame) / (segment.endFrame - segment.startFrame);
  return {
    segment,
    progress,
    enter: easeOutCubic(Math.min(1, progress * 7)),
    exit: easeOutCubic(Math.min(1, (1 - progress) * 8)),
  };
}
```

- [ ] **Step 4: Implement the graphics page**

Create only these scene classes:

- `gap`: latency/token cards fade away while “Was the decision correct?” remains.
- `instrument`: actual, syntax-highlighted `record_decision(...)` excerpt and OTel event attributes.
- `architecture`: app → Gradebook → OTLP → SigNoz → agent proposal → human approval.
- `cleancut-fillers`: synthetic transcript words with provable fillers highlighted.
- `cleancut-quote`: verbatim quote comparison; paraphrase resolves red.
- `cleancut-reality`: clip decision node links to later editor outcome in amber.
- `right-sizing`: real model-by-decision-type values and a human approval diff.
- `identity`: Gradebook and “Performance becomes evidence.”

Do not draw dashboard chrome, fake SigNoz panels, fake ToyWorld, or fake CleanCut product UI.

- [ ] **Step 5: Render a five-frame smoke set**

Add `--frames 0,900,2700,3300,5250` to the graphics renderer. Run:

`cd video-studio && node scripts/gradebook-complete-graphics.mjs --frames 0,900,2700,3300,5250`

Expected: five 1920x1080 PNGs under `output/gradebook-complete/review/graphics/`.

- [ ] **Step 6: Inspect all five PNGs at original resolution**

Confirm no clipping, mojibake, mock product UI, low-contrast captions, or elements inside a 48-pixel delivery-safe edge.

- [ ] **Step 7: Render the graphics source and verify media**

Run: `cd video-studio && npm.cmd run complete:graphics`

Run: `ffprobe -v error -count_frames -show_entries stream=width,height,r_frame_rate,nb_read_frames -of json video-studio/output/gradebook-complete/graphics/graphics.mp4`

Expected: 1920x1080, `30/1`, and `5400` frames.

- [ ] **Step 8: Commit**

```powershell
git add video-studio/src/complete-visuals.mjs video-studio/test/complete-visuals.test.mjs video-studio/public/gradebook-complete.html video-studio/scripts/gradebook-complete-graphics.mjs video-studio/package.json
git commit -m "feat: add Evidence Noir film graphics"
```

## Task 3: Prepare the real ToyWorld source

**Files:**
- Create: `video-studio/src/complete-toyworld.mjs`
- Create: `video-studio/test/complete-toyworld.test.mjs`
- Create: `video-studio/scripts/gradebook-complete-toyworld.mjs`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: `output/world-first/footage/toyworld-live.webm` and its `recording.json`.
- Produces: `buildToyWorldExcerptPlan(cues, recording) -> Array<{sourceStart, duration, destinationStart, camera}>`.
- Produces: `output/gradebook-complete/sources/toyworld.mp4`, exactly 35 seconds and 1,050 frames.

- [ ] **Step 1: Write failing excerpt-plan tests**

```js
test("ToyWorld excerpt contains motion, one followed decision, and completed evidence", () => {
  const plan = buildToyWorldExcerptPlan(cues, recording);
  assert.deepEqual(plan.map(({camera}) => camera), ["orbit", "follow", "overview"]);
  assert.equal(plan.reduce((sum, shot) => sum + shot.durationFrames, 0), 1050);
  assert.equal(recording.finalStatus.state, "COMPLETE");
});
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="ToyWorld excerpt"`

Expected: FAIL because `complete-toyworld.mjs` is missing.

- [ ] **Step 3: Implement the excerpt plan and source check**

Reject any recording whose final status is not `COMPLETE` or whose values are
not 420 decisions and 268 correct. Select an opening orbit, a close follow shot
that shows a real route and HUD decision evidence, and the completed overview.

- [ ] **Step 4: Build the normalized excerpt**

Use FFmpeg trim/setpts blocks, `xfade=transition=fade:duration=0.4`, and a final
`fps=30,scale=1920:1080:flags=lanczos,format=yuv420p`. Do not use the previous
film's narration, titles, or audio.

- [ ] **Step 5: Verify and visually inspect**

Run: `cd video-studio && npm.cmd run complete:toyworld`

Expected: 1,050 frames, 35.000 seconds, no audio.

Extract frames at 2, 15, and 32 seconds and inspect at original resolution.

- [ ] **Step 6: Commit**

```powershell
git add video-studio/src/complete-toyworld.mjs video-studio/test/complete-toyworld.test.mjs video-studio/scripts/gradebook-complete-toyworld.mjs video-studio/package.json
git commit -m "feat: prepare real ToyWorld film source"
```

## Task 4: Build the privacy-safe CleanCut proof source

**Files:**
- Create: `video-studio/src/complete-cleancut.mjs`
- Create: `video-studio/test/complete-cleancut.test.mjs`
- Modify: `video-studio/public/gradebook-complete.html`
- Modify: `video-studio/scripts/gradebook-complete-graphics.mjs`
- Modify: `video-studio/config/gradebook-complete-evidence.json`

**Interfaces:**
- Consumes: `cleancut-proof/samples/sample_transcript.txt`, `cleancut-proof/samples/sample_clips.csv`, reusable checker behavior, and tests.
- Produces: `buildCleanCutProof({transcript, clips}) -> {fillers, verbatimQuote, clipOutcomes, clipCorrect}`.
- Produces: source metadata containing only the basename `sample_transcript.txt`, aggregate counts, and checker names.

- [ ] **Step 1: Write failing proof and privacy tests**

```js
test("CleanCut source derives only provable synthetic evidence", async () => {
  const proof = await loadCleanCutProof();
  assert.deepEqual(proof.fillers, ["um", "uh", "uh", "um", "hmm"]);
  assert.equal(proof.clipOutcomes, 6);
  assert.equal(proof.clipCorrect, 4);
});

test("CleanCut metadata never includes transcript or CSV row content", () => {
  const metadata = publicCleanCutMetadata(proof);
  assert.equal(JSON.stringify(metadata).includes(proof.transcript), false);
  assert.deepEqual(Object.keys(metadata).sort(), ["clipCorrect", "clipOutcomes", "sourceLabel"]);
});
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="CleanCut source|CleanCut metadata"`

Expected: FAIL because `complete-cleancut.mjs` is missing.

- [ ] **Step 3: Implement the evidence adapter**

Parse the committed samples; derive fillers with the same pure-filler token set,
verify the selected quote is a normalized verbatim substring, and compute clip
correctness as `(predicted_viral_score >= 0.45) === kept`.

- [ ] **Step 4: Drive CleanCut graphics from derived evidence**

Render 30 seconds across filler detection, quote extraction, and the late
keep/discard outcome. Use teal for math and amber for the cross-trace reality
link. Show `cleancut-proof` and `cleancut-outcomes` service names once.

- [ ] **Step 5: Run CleanCut and graphics tests**

Run: `python -m pytest cleancut-proof/tests -q`

Expected: all CleanCut tests pass.

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="CleanCut"`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add video-studio/src/complete-cleancut.mjs video-studio/test/complete-cleancut.test.mjs video-studio/public/gradebook-complete.html video-studio/scripts/gradebook-complete-graphics.mjs video-studio/config/gradebook-complete-evidence.json
git commit -m "feat: add privacy-safe CleanCut proof visuals"
```

## Task 5: Rebuild, populate, and record the actual SigNoz UI with a verified fallback

**Files:**
- Create: `video-studio/src/complete-sources.mjs`
- Create: `video-studio/test/complete-sources.test.mjs`
- Create: `video-studio/scripts/gradebook-complete-signoz.mjs`
- Create: `video-studio/config/signoz-shot-plan.json`
- Modify: `video-studio/package.json`

**Interfaces:**
- Produces: `resolveSource({actualPath, fallbackPaths, expectedKind}) -> SourceDescriptor`.
- Source descriptor: `{kind: "actual-ui"|"verified-evidence", files: string[], label: string, reason?: string}`.
- Produces: `output/gradebook-complete/sources/signoz.mp4`, exactly 45 seconds, or a manifest of verified screenshots for assembly.
- Consumes optional environment variables `SIGNOZ_URL`, `SIGNOZ_EMAIL`, `SIGNOZ_PASSWORD`, and `SIGNOZ_API_KEY`; never stores their values.

- [ ] **Step 1: Write failing source-policy tests**

```js
test("SigNoz prefers actual UI and labels fallback evidence", () => {
  assert.equal(resolveSource({actualPath: "capture.mp4", fallbackPaths: []}).kind, "actual-ui");
  assert.deepEqual(
    resolveSource({actualPath: null, fallbackPaths: ["dashboard-headline.png"]}),
    {
      kind: "verified-evidence",
      files: ["dashboard-headline.png"],
      label: "RECORDED DEPLOYMENT",
      reason: "actual SigNoz capture unavailable",
    },
  );
});
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="SigNoz prefers"`

Expected: FAIL because `complete-sources.mjs` is missing.

- [ ] **Step 3: Implement source selection and shot-plan validation**

The required shots are:

1. Services: `toy-world`, `toy-world-outcomes`, and CleanCut services when available.
2. A model-run trace and one `gen_ai.evaluation.result` span.
3. Grade-source attributes and decision cost.
4. Cost-per-correct dashboard.
5. Right-sizing grid.
6. Failure logs.
7. Alert rules.
8. Dashboard index showing both cost-per-correct and meta-build-fleet dashboards.

Actual capture metadata must record URL origin, capture timestamp, shot IDs, and
visible service names, but never credentials.

- [ ] **Step 4: Attempt the local deployment**

Check `SIGNOZ_URL` or `http://localhost:8080`. If unavailable and Docker is
running, execute:

```powershell
foundry_windows_amd64/bin/foundryctl.exe cast -f casting.yaml
```

Wait for the HTTP endpoint. If onboarding is required, use the supplied
`SIGNOZ_EMAIL` and `SIGNOZ_PASSWORD`. If either is absent, record a structured
fallback reason and continue; do not invent credentials or pause the build.

- [ ] **Step 5: Populate telemetry and import observability assets**

Run the deterministic ToyWorld replay against `http://localhost:4318`. Import
the two dashboard JSON files, five alert-rule JSON files, and three saved views
using the documented UI/API flows. Use `SIGNOZ_API_KEY` only in process memory.
Run the synthetic CleanCut proof only if its required model credential is
available; otherwise show its committed proof through graphics and do not
fabricate CleanCut services in SigNoz.

- [ ] **Step 6: Record the actual UI**

Use Playwright with 1920x1080 viewport. Hide or smooth the cursor between
intentional interactions. Capture each shot in `signoz-shot-plan.json`; avoid
loading pauses by waiting for selectors before beginning each shot. Normalize
the result to 45 seconds and 1,350 frames.

- [ ] **Step 7: Implement and exercise the fallback**

Fallback files are:

- `docs/screenshots/dashboard-headline.png`
- `docs/screenshots/right-sizing-grid.png`
- `docs/visuals/span-link.png`
- `dashboards/view-decision-traces.json`
- `dashboards/view-failure-events.json`
- `dashboards/view-judge-run-health.json`

Generate Evidence Noir crops and pans with the visible label
`RECORDED DEPLOYMENT`. Never draw fake browser chrome or imply live clicking.

- [ ] **Step 8: Verify source metadata and inspect representative frames**

Run: `cd video-studio && npm.cmd run complete:signoz`

Expected: either `kind: "actual-ui"` with a 1,350-frame source, or
`kind: "verified-evidence"` with all six fallback files present.

- [ ] **Step 9: Commit**

```powershell
git add video-studio/src/complete-sources.mjs video-studio/test/complete-sources.test.mjs video-studio/scripts/gradebook-complete-signoz.mjs video-studio/config/signoz-shot-plan.json video-studio/package.json
git commit -m "feat: capture Gradebook observability in SigNoz"
```

## Task 6: Generate continuous three-minute narration

**Files:**
- Create: `video-studio/src/complete-narration.mjs`
- Create: `video-studio/test/complete-narration.test.mjs`
- Create: `video-studio/scripts/gradebook-complete-narrate.mjs`
- Modify: `video-studio/timeline/gradebook-complete-cues.json`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: narration cues and `af_heart`.
- Produces: `output/gradebook-complete/audio/narration/<cue>.wav`.
- Produces: `output/gradebook-complete/audio/narration.json`.
- Produces: `output/gradebook-complete/audio/narration-preview.wav`, exactly 180 seconds.

- [ ] **Step 1: Write failing narration-density and fit tests**

```js
test("complete narration stays continuous and inside each chapter", async () => {
  const cues = await loadCompleteCues();
  for (let i = 1; i < cues.narration.length; i += 1) {
    assert.ok(cues.narration[i].startFrame - cues.narration[i - 1].endFrame <= 36);
  }
  assert.equal(cues.narration.at(-1).endFrame <= 5400, true);
});
```

- [ ] **Step 2: Run the focused test**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="complete narration"`

Expected: FAIL until measured narration frames are committed.

- [ ] **Step 3: Write and generate the complete narration**

Use concise spoken language. Explicitly say:

- Gradebook measures correctness, cost, and grade authority.
- Math, reality, and AI-judge sources are not interchangeable.
- ToyWorld is the controlled experiment.
- CleanCut is the real-product proof.
- SigNoz receives traces, metrics, logs, dashboards, and alerts.
- The finding is to right-size per decision type with human approval.

Generate with Kokoro `af_heart`, resample to 48 kHz mono, and store actual
duration frames.

- [ ] **Step 4: Revise timing until every segment fits naturally**

Do not speed speech outside the existing natural range. Shorten copy if a cue
overruns. Keep frame gaps at or below 36 frames.

- [ ] **Step 5: Verify preview duration and silence density**

Run:

```powershell
ffprobe -v error -show_entries format=duration -of default=nw=1 video-studio/output/gradebook-complete/audio/narration-preview.wav
ffmpeg -hide_banner -i video-studio/output/gradebook-complete/audio/narration-preview.wav -af silencedetect=noise=-45dB:d=1.2 -f null NUL
```

Expected: `180.000000` and no internal detected silence longer than 1.2 seconds.

- [ ] **Step 6: Commit**

```powershell
git add video-studio/src/complete-narration.mjs video-studio/test/complete-narration.test.mjs video-studio/scripts/gradebook-complete-narrate.mjs video-studio/timeline/gradebook-complete-cues.json video-studio/package.json
git commit -m "feat: generate complete Gradebook narration"
```

## Task 7: Mix and master the long-form audio

**Files:**
- Modify: `video-studio/src/audio-graph.mjs`
- Create: `video-studio/test/complete-audio.test.mjs`
- Create: `video-studio/scripts/gradebook-complete-mix.mjs`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: narration metadata, licensed audio manifest, timeline effects.
- Produces: `output/gradebook-complete/audio/master.wav`, 180 seconds, 48 kHz stereo PCM24.

- [ ] **Step 1: Write failing 180-second graph tests**

```js
test("complete audio graph derives its three-minute boundary from frames", () => {
  const graph = buildAudioGraph({fps: 30, totalFrames: 5400, narration: [], effects: []});
  assert.match(graph, /apad=whole_dur=180/);
  assert.match(graph, /atrim=duration=180/);
  assert.match(graph, /sidechaincompress/);
});
```

- [ ] **Step 2: Run the focused test and confirm failure if graph assumptions remain**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="complete audio graph"`

Expected: FAIL if any remaining 60/120-second constant exists.

- [ ] **Step 3: Implement the complete mix**

Loop the licensed music bed, apply narration-driven sidechain compression, and
place only approved transition, trace, confirmation, and closing effects from
`assets/audio/manifest.json`. Effects remain at least 18 dB below full scale
before mastering.

- [ ] **Step 4: Master and measure**

Use `loudnorm` followed by a true-peak limiter. Iterate target input until the
measured WAV is between -15 and -12.5 LUFS with true peak at or below -2 dBFS,
leaving AAC headroom.

- [ ] **Step 5: Run tests and probe the WAV**

Expected: 180.000 seconds, PCM24, 48 kHz, stereo.

- [ ] **Step 6: Commit**

```powershell
git add video-studio/src/audio-graph.mjs video-studio/test/complete-audio.test.mjs video-studio/scripts/gradebook-complete-mix.mjs video-studio/package.json
git commit -m "feat: master three-minute Gradebook audio"
```

## Task 8: Assemble the professional source-driven master

**Files:**
- Create: `video-studio/src/complete-video-graph.mjs`
- Create: `video-studio/test/complete-video-graph.test.mjs`
- Create: `video-studio/scripts/gradebook-complete-master.mjs`
- Modify: `video-studio/package.json`

**Interfaces:**
- Consumes: graphics, ToyWorld, SigNoz actual/fallback, audio master, cue sheet, and capture metadata.
- Produces: `buildCompleteVideoGraph({segments, fps, width, height}) -> string`.
- Produces: `output/gradebook-complete/gradebook-hackathon-3m.mp4`.

- [ ] **Step 1: Write failing graph tests**

```js
test("complete video graph covers 5,400 frames with normalized sources", () => {
  const graph = buildCompleteVideoGraph({segments, fps: 30, width: 1920, height: 1080});
  assert.match(graph, /fps=30/);
  assert.match(graph, /scale=1920:1080/);
  assert.match(graph, /concat=n=6:v=1:a=0/);
  assert.match(graph, /trim=duration=180/);
});
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="complete video graph"`

Expected: FAIL because `complete-video-graph.mjs` is missing.

- [ ] **Step 3: Implement normalized segment assembly**

Normalize every source with:

`fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1`

Trim and reset timestamps per cue. Use the graphics source for the problem,
integration, CleanCut, and closing portions; use real ToyWorld and actual or
verified SigNoz sources in their approved intervals. Apply only short eased
fades or route/trace match transitions specified by the cue sheet.

- [ ] **Step 4: Add restrained real-UI annotations**

Generate ASS overlays for chapter names, tutorial step labels, and verified
fallback labeling. Keep overlays outside important UI panels. Do not cover
ToyWorld's HUD or SigNoz query results.

- [ ] **Step 5: Encode the master**

Use H.264 High Profile, CRF 18, `yuv420p`, AAC 256 kbps, 48 kHz stereo,
`+faststart`, and exactly `-frames:v 5400`.

- [ ] **Step 6: Extract and inspect review frames**

Extract at 5, 30, 60, 95, 125, 155, and 175 seconds. Inspect every frame at
original resolution for visual hierarchy, clean motion state, factual labels,
privacy, and UI obstruction.

- [ ] **Step 7: Commit**

```powershell
git add video-studio/src/complete-video-graph.mjs video-studio/test/complete-video-graph.test.mjs video-studio/scripts/gradebook-complete-master.mjs video-studio/package.json
git commit -m "feat: assemble complete Gradebook hackathon film"
```

## Task 9: Add the final acceptance gate and reproducible build

**Files:**
- Create: `video-studio/src/complete-delivery.mjs`
- Create: `video-studio/test/complete-delivery.test.mjs`
- Create: `video-studio/scripts/gradebook-complete-verify.mjs`
- Modify: `video-studio/package.json`
- Modify: `video-studio/README.md`

**Interfaces:**
- Consumes: final FFprobe JSON, cue sheet, evidence manifest, capture metadata, narration metadata, and source descriptors.
- Produces: `validateCompleteDelivery(input) -> CompleteDeliveryReport`.
- Produces: `output/gradebook-complete/verification.json`.

- [ ] **Step 1: Write failing exact-delivery tests**

```js
test("complete delivery accepts exact synchronized media and evidence", () => {
  const report = validateCompleteDelivery(validInput);
  assert.equal(report.frames, 5400);
  assert.equal(report.durationSeconds, 180);
  assert.deepEqual(report.requiredProofs.sort(), ["cleancut", "signoz", "toyworld"]);
});

test("complete delivery rejects private CleanCut content", () => {
  assert.throws(
    () => validateCompleteDelivery({...validInput, generatedText: "private client transcript"}),
    /CleanCut privacy/,
  );
});
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd video-studio && npm.cmd test -- --test-name-pattern="complete delivery"`

Expected: FAIL because `complete-delivery.mjs` is missing.

- [ ] **Step 3: Implement delivery validation**

Validate:

- H.264 High, 1920x1080, 30/1, 5,400 frames.
- AAC, 48 kHz, stereo.
- Both streams begin at zero and last 180 seconds.
- Loudness and true peak.
- Narration silence density.
- Chapter and source coverage.
- Actual SigNoz UI or explicitly labeled verified fallback.
- ToyWorld numeric reconciliation.
- CleanCut privacy metadata.
- Evidence paths exist.
- Required reviewed-frame files exist.

- [ ] **Step 4: Add complete build scripts**

Add:

```json
{
  "complete:graphics": "node scripts/gradebook-complete-graphics.mjs",
  "complete:toyworld": "node scripts/gradebook-complete-toyworld.mjs",
  "complete:signoz": "node scripts/gradebook-complete-signoz.mjs",
  "complete:narrate": "node scripts/gradebook-complete-narrate.mjs",
  "complete:mix": "node scripts/gradebook-complete-mix.mjs",
  "complete:master": "node scripts/gradebook-complete-master.mjs",
  "complete:verify": "node scripts/gradebook-complete-verify.mjs",
  "complete:build": "npm run complete:graphics && npm run complete:toyworld && npm run complete:signoz && npm run complete:narrate && npm run complete:mix && npm run complete:master && npm run complete:verify"
}
```

- [ ] **Step 5: Run every relevant test suite**

```powershell
cd video-studio
npm.cmd test
npm.cmd run check
npm.cmd run complete:verify
cd ../viewer
npm.cmd test
npm.cmd run build
cd ../reference-library
python -m pytest tests -q
cd ../toy-world
python -m pytest tests -q
cd ../cleancut-proof
python -m pytest tests -q
```

Expected: all suites pass. If a Python environment lacks an optional runtime
extra, install only the extras declared by that package before repeating its
documented test command.

- [ ] **Step 6: Perform final media verification**

Run:

```powershell
ffprobe -v error -count_frames -show_entries format=duration:stream=codec_type,codec_name,profile,width,height,r_frame_rate,sample_rate,channels,nb_read_frames,start_time,duration -of json video-studio/output/gradebook-complete/gradebook-hackathon-3m.mp4
ffmpeg -hide_banner -i video-studio/output/gradebook-complete/gradebook-hackathon-3m.mp4 -af ebur128=peak=true -f null NUL
```

Expected: 5,400 frames, 180.000 seconds, matching zero start times, -15 to
-12.5 LUFS, and true peak no higher than -1 dBFS.

- [ ] **Step 7: Update the README**

Document setup, optional SigNoz credentials, actual-UI/fallback behavior,
individual stages, one-command build, output locations, and verification
targets. Explicitly state that private CleanCut inputs must remain local.

- [ ] **Step 8: Commit**

```powershell
git add video-studio/src/complete-delivery.mjs video-studio/test/complete-delivery.test.mjs video-studio/scripts/gradebook-complete-verify.mjs video-studio/package.json video-studio/README.md
git commit -m "test: verify complete Gradebook hackathon film"
```

## Task 10: Final review and branch handoff

**Files:**
- Review: `video-studio/output/gradebook-complete/gradebook-hackathon-3m.mp4`
- Review: `video-studio/output/gradebook-complete/verification.json`
- Review: `video-studio/output/gradebook-complete/review/`

**Interfaces:**
- Consumes: all completed tasks.
- Produces: a verified local delivery and a user integration choice.

- [ ] **Step 1: Run the complete build from the documented command**

Run: `cd video-studio && npm.cmd run complete:build`

Expected: exits zero and writes the final MP4 plus verification report.

- [ ] **Step 2: Watch the complete film with headphones**

Check narration intelligibility, music ducking, pronunciation, synchronization,
cursor pacing, transition restraint, chapter comprehension, privacy, and the
accuracy of every on-screen value. Any problem returns to the owning task and
requires a fresh full build.

- [ ] **Step 3: Run fresh final tests and verification**

Repeat Task 9 Steps 5 and 6 after the last content change.

- [ ] **Step 4: Inspect version-control scope**

Run: `git status --short`, `git diff --check`, and `git log --oneline main..HEAD`.
Do not add unrelated pre-existing untracked files or generated media excluded
by `.gitignore`.

- [ ] **Step 5: Use the branch-finishing workflow**

Invoke `superpowers:verification-before-completion`, then
`superpowers:finishing-a-development-branch`. Present the required merge,
push/PR, or keep-branch choices without choosing on the user's behalf.
