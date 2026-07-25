# Pune Race View Design

## Status

Approved on 2026-07-25.

## Goal

Add an optional, judge-independent Three.js view layer that replays the toy
world's four recorded AI drivers racing from A to B through multiple route
choices on a recognizable central Pune backdrop.

The viewer makes Gradebook's evidence spatial: choices are colored by their
math grade, model cost accumulates while drivers move, and late reality grades
return to the earlier decisions they judge.

## Scope and safety boundary

The viewer is a side exploration on its own branch. It is not part of the
Foundry cast or the judge-facing one-command path.

All product files are additive under `viewer/` except for the design and plan
documents under `docs/superpowers/`. The change must not modify:

- `README.md`
- `casting.yaml`
- `casting.yaml.lock`
- CI configuration
- Existing `toy-world/` production source
- Existing `reference-library/` production source

Unrelated untracked workspace artifacts must remain untouched.

## Chosen approach

Build a standalone Vite and TypeScript application using Three.js. Reuse only
the small, framework-independent path-rendering primitives needed from
`GoogleCloudPlatform/race-condition`; do not vendor its Angular application,
Go gateway, WebSocket protocol, agent services, or cloud infrastructure.

The first version is a deterministic replay of
`toy-world/recordings/replay-v1.jsonl`. It does not launch live LLM agents from
the browser. Its data contract is ordered-event-friendly so a later SSE or
WebSocket adapter can supply the same decisions and outcomes incrementally.

## Pune geography

The scene depicts a recognizable central Pune corridor from Shivajinagar
through Deccan toward Swargate.

OpenStreetMap geometry is downloaded once during development, reduced to a
small local GeoJSON asset, and committed under `viewer/public/data/`. The
runtime performs no network requests and needs no API key.

The geographic layer is presentation, not ground truth:

- Pune streets, simplified buildings, water, green areas, and place labels
  establish location.
- The three toy-world junction stages are projected onto suitable nearby
  corridors.
- Toy route names, travel times, correct answers, grades, and costs remain
  authoritative and unchanged.
- Copy must not imply that the toy travel times represent live or historical
  Pune traffic.

The viewer must display `© OpenStreetMap contributors` and link to
`https://www.openstreetmap.org/copyright`. The local extract's source bounds,
retrieval date, and transformation steps are recorded in `viewer/VENDOR.md`.

## Architecture

```text
toyworld.world.WORLD
toy-world/recordings/replay-v1.jsonl
gradebook.pricing.price
             |
       viewer/export.py
             |
  world.geojson + run.json
             |
   Vite + TypeScript + Three.js
             |
 Pune scene + routes + drivers + HUD
```

`viewer/export.py` temporarily adds `toy-world/src` and
`reference-library/src` to its import path when run from the repository root.
It imports only existing public seams:

- `toyworld.world.WORLD`
- `toyworld.replay.load_recording`
- `toyworld.replay.replay`
- `gradebook.pricing.price`

The exporter writes deterministic JSON with stable feature and driver order.
Committed generated files let `npm run dev` work without Python setup.

## Data contracts

### `world.geojson`

The file is a GeoJSON `FeatureCollection`. It includes the locally reduced
Pune context plus exactly one simulation `LineString` feature per route option
in `WORLD`.

Each simulation route has:

- `kind: "simulation-route"`
- `junction`
- `route`
- `travel_time_min`
- `is_fastest`
- `stage_index`

Start, junction, merge, and finish points are represented as point features
with `kind` values that distinguish them from Pune place labels.

Route coordinates form three consecutive stages. Alternative choices separate
visually and rejoin before the next stage. Longer travel times produce larger
curvature and slower traversal, without changing their recorded numeric value.

### `run.json`

The run document has:

- `schema_version`
- `generated_from`
- `drivers`
- `outcomes`
- `totals`

Every driver record has an ID, model, display color, and ordered decisions.
Every decision includes:

- `junction`
- `stage_index`
- `chosen`
- `true_fastest`
- `correct`
- `travel_time_min`
- `input_tokens`
- `output_tokens`
- `cost_usd`
- `response_id`

Every outcome includes `driver`, `on_time`, and `graded_response_id`.

Totals include `decisions`, `correct`, `total_cost_usd`, `outcomes`, and
`cost_per_correct_usd`. These values must reconcile with `ReplaySummary`; the
exporter must not implement a competing headline-metric formula.

## Viewer behavior

### Scene

The scene uses a dark, presentation-friendly 3D style inspired by
`race-condition`:

- Orthographic or perspective camera at an oblique city angle
- Simplified extruded Pune building footprints
- Muted road and land-use context
- Luminous route paths
- Screen-space labels that remain readable while the camera moves
- Start and finish gates

The application supports orbit/pan/zoom but opens on a composed camera view
that contains the entire corridor.

### Replay

Four drivers begin together. Each driver follows its recorded route at each
stage. Progress duration is proportional to the selected route's travel time,
scaled to keep the full replay short.

At a decision:

- The selected path illuminates.
- A correct choice resolves to green.
- An incorrect choice resolves to red.
- For an incorrect choice, the fastest alternative appears as a subdued ghost
  line.
- The driver's accumulated cost and correctness counters update.

Drivers are labeled by model. Drivers sharing a model remain distinguishable
by driver ID and marker color.

### Late outcomes

After every driver reaches the finish, outcomes arrive in a separate closing
phase. The viewer resolves each `graded_response_id` to the original decision:

- On-time outcomes add a positive reality-grade treatment.
- Late outcomes pulse or tint the responsible earlier junction red.
- Driver 3 resolves to J1.
- Driver 4 resolves to J2.

The treatment must target the linked decision, not the last junction.

### HUD and controls

The HUD shows:

- Replay state
- Drivers finished
- Decisions graded
- Correct decisions
- Total cost
- Cost per correct decision
- A compact row for each driver with model, progress, correctness, and cost

Controls include play/pause, restart, speed, and a camera-reset action.
Animation respects `prefers-reduced-motion`: reduced-motion mode advances in
discrete steps and disables decorative camera movement and pulsing.

## Upstream reuse and attribution

Only framework-independent Three.js primitives may be copied from
`GoogleCloudPlatform/race-condition`, expected to include path abstractions,
gradient path rendering, Catmull-Rom adaptation, and label overlay behavior.

Copied files retain their Google copyright and Apache-2.0 headers.
`viewer/NOTICE` and `viewer/VENDOR.md` record:

- Upstream repository URL
- Exact upstream commit SHA
- Original file paths
- Local file paths
- Changes made, including removal of marathon-specific types
- Apache-2.0 license reference
- OpenStreetMap attribution and extract metadata

The viewer's original code must not claim Google authorship or endorsement.

## Error handling

- Fetch failures replace the canvas with a readable error panel naming the
  missing asset.
- Invalid or unsupported schema versions fail before scene construction.
- Outcomes with unknown `graded_response_id` fail export and viewer
  validation.
- Unknown route names fail export.
- Unknown pricing models retain Gradebook's existing fail-loud behavior.
- A zero-correct run represents cost per correct as `null`, never zero.

## Testing

### Python exporter tests

Tests run without an OTLP endpoint and verify:

- One simulation route feature exists per option in `WORLD`.
- `is_fastest` matches `Junction.true_fastest`.
- Driver and decision ordering matches the recording.
- Decision costs come from `gradebook.pricing.price`.
- Exported totals equal a locally executed `ReplaySummary`.
- Every outcome resolves to an exported decision.
- Unknown outcome links fail loudly.

### TypeScript tests

Pure modules are tested with Vitest:

- Schema validation
- Route lookup
- Replay timeline construction
- Cost and correctness accumulation
- Late-outcome targeting
- Reduced-motion timeline behavior

Three.js rendering itself is kept thin and verified through the production
build and a browser smoke test.

### Build and visual verification

- `npm test`
- `npm run build`
- `python -m pytest viewer/tests -v`
- Browser smoke test confirms four labeled drivers, three decision stages,
  green/red path states, ghost paths, matching HUD totals, Pune attribution,
  and correct late-grade targeting.

## Out of scope

- Live LLM calls initiated by the browser
- WebSockets, SSE, A2A, or a Go gateway
- Google Maps APIs
- Real Pune travel-time claims
- SigNoz trace deep links
- Editing toy-world decisions from the viewer
- Autonomous remediation
- Adding the viewer to Foundry, CI, or the submission README
