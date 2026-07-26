# Gradebook Complete Hackathon Film Design

## Objective

Create an exactly three-minute professional hackathon product-demo film that
explains Gradebook, demonstrates its complete repository-backed feature set,
shows how it is deployed with Foundry and observed in SigNoz, and proves the
contract across two applications:

- ToyWorld, a controlled and visually legible 420-decision experiment.
- CleanCut, a privacy-safe proof on real product workflows.

The film must help judges understand both the product and the implementation.
It is a tutorial-shaped product reveal: instrument, deploy, run, observe, and
act.

## Audience and success criteria

The primary audience is the Agents of SigNoz hackathon judging panel. A
successful film lets a judge answer these questions after one viewing:

1. What problem does Gradebook solve?
2. What is integrated into an application?
3. What does Gradebook emit through OpenTelemetry?
4. What can SigNoz observe and alert on?
5. Why are math, reality, and AI-judge provenance kept distinct?
6. What did ToyWorld and CleanCut prove?
7. What decision can a team make from the evidence?

The film must feel like a polished technical product reveal, not an unedited
screen recording or a slide deck.

## Narrative

The argument is:

> AI observability usually shows that a request happened. Gradebook records
> whether the decision was correct, what that correctness cost, and where the
> verdict's authority came from. It emits standard OpenTelemetry evidence that
> SigNoz can trace, measure, search, dashboard, and alert on. ToyWorld makes the
> mechanism visible; CleanCut proves it applies to real product work.

The main phrase is **Performance becomes evidence.**

## Exact three-minute structure

| Time | Duration | Chapter | Purpose |
| --- | ---: | --- | --- |
| 00:00-00:25 | 25 s | The gap | Contrast conventional latency/token observability with correctness and value. Introduce Gradebook. |
| 00:25-00:50 | 25 s | Instrument and deploy | Show `record_decision(...)`, reusable checkers, the OTel contract, `casting.yaml`, Foundry, and the SigNoz data path. |
| 00:50-01:25 | 35 s | ToyWorld | Show the real 3D Pune road environment, its machine-computed truth, seven models, three decision types, and the completed 420-decision run. |
| 01:25-01:55 | 30 s | CleanCut | Show privacy-safe filler detection, verbatim quote checking, and editor keep/discard reality outcomes. |
| 01:55-02:40 | 45 s | Observe in SigNoz | Show the actual SigNoz deployment where possible: services, traces, evaluation events, metrics, logs, dashboards, saved views, and alert rules. |
| 02:40-03:00 | 20 s | Act on evidence | Show cost per correct decision, per-decision-type right-sizing, MCP-assisted analysis, the human approval gate, and the closing identity. |

The total is 180 seconds and 5,400 frames at 30 fps.

## Feature coverage

The film should cover the repository's material Gradebook capabilities without
turning each one into a separate chapter:

- One-call `record_decision(...)` integration.
- The standard `gen_ai.evaluation.result` OpenTelemetry event.
- Mandatory grade provenance through `augmentloop.grade.source`.
- Math grades from deterministic checkers.
- Reality grades from later application outcomes with span links.
- AI-judge grades labeled as opinion and excluded from the headline metric.
- Cost calculation and cost-per-correct decision.
- Reusable checkers and closed, queryable reason codes.
- `gradebook.decisions.graded` and `gradebook.decision.cost.usd` metrics.
- Trace/span-stamped failure logs.
- Budget guard and spend failure signal.
- Per-model and per-decision-type analysis.
- Human-approved routing changes rather than autonomous writes.
- Foundry-declared SigNoz deployment with MCP enabled.
- Two dashboards, five alert rules, and three saved views.
- Replayable, deterministic evidence with optional live model execution.

## Application proofs

### ToyWorld

ToyWorld is the controlled visual experiment. It uses a real OpenStreetMap road
network in Pune with 20 weighted junctions. The graph computes its own answer
keys. Seven models each face route-choice, ETA-estimation, and next-hop tasks.
The committed run contains:

- 420 decisions.
- 268 math-correct decisions.
- 140 later reality outcomes.
- 43 cases where reality overturns the immediate math interpretation.
- $0.403804 total decision cost.
- $0.001507 per correct decision.

The film uses the real 3D viewer and shows orbit, overview, top, chase, and
follow perspectives. Correct routes resolve in green, incorrect routes in red,
and the optimal alternative appears as a yellow ghost.

### CleanCut

CleanCut is the real-product proof. The film uses only committed synthetic
samples or approved local non-identifying inputs.

- Filler detection is math-graded against a lexical scan of pure hesitation
  sounds.
- Quote extraction passes only if the selected quote is a verbatim transcript
  substring.
- Clip scoring is reality-graded by the editor's later keep/discard outcome.
- The later grade span-links back to the original decision.
- Unknown historical token counts do not produce fabricated cost attributes.

The SigNoz services are `cleancut-proof` and `cleancut-outcomes`.
Client-identifying transcript or clip data must never enter the repository,
film, logs, or generated metadata.

## SigNoz and tutorial flow

The tutorial steps are visible but concise:

1. Wrap the existing AI decision with Gradebook.
2. Deploy SigNoz with `foundryctl cast -f casting.yaml`.
3. Create the SigNoz organization and configure the OTLP endpoint.
4. Replay ToyWorld and, where credentials permit, run the CleanCut proof.
5. Import the committed dashboards, alert rules, and saved views.
6. Inspect a decision trace and its evaluation event.
7. Compare grade-source metrics, cost, correctness, and failure logs.
8. Read the right-sizing result and propose a routing change.
9. Require a human to approve the configuration diff.

The preferred visual source is a rebuilt local SigNoz deployment recorded from
the actual UI. The pipeline should attempt to deploy, populate, import, and
record it.

If a reliable local deployment cannot be rebuilt within the production
environment, use the repository's verified SigNoz screenshots, committed
dashboard JSON, and saved-view JSON. Such material must be labeled as a
recorded deployment or repository evidence. The film must never simulate a
live SigNoz session or present fabricated UI as captured product footage.

## Visual language

The approved direction is **Evidence Noir**:

- Near-black and navy backgrounds.
- White primary typography with muted blue-gray secondary text.
- Teal for Gradebook, deterministic evidence, and active telemetry.
- Amber for later reality outcomes.
- Red only for failures or incorrect decisions.
- AI-judge material appears muted and visually secondary.
- Restrained borders, grids, trace lines, and subtle glow.
- Clear sans-serif display typography with monospaced technical details.

Real product interfaces remain visually dominant. Motion graphics annotate and
connect evidence; they do not replace the product.

## Motion grammar

- Use smooth eased camera motion, match cuts, and purposeful focus shifts.
- Remove cursor hesitation, loading pauses, repeated clicks, and dead time.
- Use thin telemetry lines and expanding trace nodes for chapter transitions.
- Animate real UI crops with subtle pans and zooms.
- Use focus masks only to direct attention to a real element.
- Count metrics up only to values present in the captured evidence.
- Reuse ToyWorld route geometry as a match transition into SigNoz trace lines.
- Resolve CleanCut transcript fragments into math-grade events, then connect a
  clip decision to its later reality outcome.
- Use compact branded lower thirds and short chapter cards.
- Avoid fake dashboards, decorative charts without data, excessive particles,
  aggressive glitches, large obstructive captions, and constant motion.

All animation uses deterministic frame-derived timing at 30 fps.

## Audio

- Generate continuous local narration with the approved Kokoro `af_heart`
  voice unless a superior installed local voice passes audition.
- Write narration for spoken clarity, not as README text.
- Do not design any narration gap longer than 1.2 seconds.
- Use a soft licensed technology music bed.
- Duck music beneath narration with sidechain compression.
- Use subtle transition, trace, confirmation, and closing effects.
- Avoid effects that imitate product notifications unless the product creates
  that notification in the shot.
- Target approximately -14 LUFS integrated and no more than -1 dBFS true peak
  after final AAC encoding.

## Production architecture

The film remains a deterministic local pipeline:

1. A single 5,400-frame cue sheet defines narration, source clips, overlays,
   tutorial steps, transitions, effects, and expected claims.
2. Narration is generated per cue and measured before final timing is locked.
3. Playwright records actual browser applications with scheduled actions.
4. Static repository visuals are rendered at source resolution when used.
5. FFmpeg composes real footage, motion graphics, narration, music, and effects.
6. A verifier probes the final master and validates streams, frames, duration,
   loudness, silence density, source coverage, and factual claims.

Each source adapter—ToyWorld, CleanCut, SigNoz, code/tutorial, and
motion-overlay—must be independently replaceable without rewriting the whole
timeline.

## Source and claim policy

Every displayed claim must map to one of:

- A committed run or recording.
- A committed source/configuration file.
- A generated report computed from committed data.
- An actual captured UI state.
- A verified repository screenshot or imported JSON view.

The cue sheet stores the claim and its evidence path. The verification script
fails if required evidence is absent or if headline numbers differ from the
committed ToyWorld run.

Known SigNoz limitations are not hidden or overstated. Exemplars are emitted
but not claimed as a working click-through in the recorded SigNoz build. A
cross-trace span link is not presented as a service-map edge.

## Failure and fallback behavior

- If the Foundry/SigNoz deployment fails, capture diagnostics and switch to the
  verified screenshot/JSON path.
- If dashboard import fails, record the actual saved views that are available
  and use committed dashboard renders for missing panels.
- If the CleanCut live roster cannot run because credentials are unavailable,
  use its deterministic tests and synthetic sample proof; do not fabricate
  model calls or real client data.
- If a browser capture is shorter than its cue, hold an appropriate completed
  state rather than inserting black frames.
- If generated narration overruns a chapter, revise copy or delivery speed;
  never time-stretch speech beyond a natural range.
- If any assertion cannot be verified, remove or soften the assertion before
  mastering.

## Verification and acceptance

The final master must satisfy:

- Exactly 180.000 seconds.
- Exactly 5,400 video frames at 30 fps.
- 1920x1080 H.264 High Profile, YUV 4:2:0.
- AAC stereo at 48 kHz.
- Video and audio both start at zero and end at 180 seconds.
- Integrated loudness between -15 and -12.5 LUFS.
- True peak no higher than -1 dBFS.
- No designed narration gap longer than 1.2 seconds.
- All required chapters and both application proofs appear.
- Actual SigNoz UI appears, or the explicit verified-evidence fallback is used.
- All headline numbers reconcile with the committed run.
- No private CleanCut client material appears.
- No fake product UI or unsupported product behavior appears.
- Viewer, video-studio, Gradebook, ToyWorld, and CleanCut relevant tests pass.
- Representative frames from every chapter pass visual review at full
  resolution.

## Deliverables

- `video-studio/output/gradebook-complete/gradebook-hackathon-3m.mp4`
- Narration preview and mastered audio.
- Source-capture metadata.
- Contact sheet and representative review frames.
- Machine-readable delivery verification report.
- Reproducible build and verification commands documented in the video-studio
  README.
