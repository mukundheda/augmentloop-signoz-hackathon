# Road-Constrained Toy-World View Design

## Status

Approved on 2026-07-26.

## Goal

Replace the obsolete three-stage race view with a road-constrained Three.js
visualization of the current toy world from `main`: its 20-junction weighted
graph, all three decision types, every recorded model decision, and all deferred
reality outcomes.

The intended presentation follows the visual language of Google Cloud's Race
Condition demonstrations: a dark miniature city, luminous road routes, many
simultaneous agents, a cinematic oblique camera, and a detail surface for
selected agents.

## Authority and scope

The visualization must derive its simulation from the current toy-world public
seams:

- `toyworld.world.GRAPH`
- `toyworld.world.QUERIES_BY_ID`
- `toyworld.world.shortest_path`
- `toy-world/recordings/replay-v1.jsonl`
- `gradebook.pricing.price`

It must not retain the removed `WORLD`, `Junction`, driver, or three-stage
assumptions.

Toy-world data remains authoritative:

- `J1` through `J20` and every directed edge come from `GRAPH`.
- Decision type, query, difficulty, answer key, and checker come from
  `QUERIES_BY_ID`.
- Chosen answer, model, tokens, and response ID come from the recording.
- Correctness is evaluated with each query's checker.
- Monetary cost comes from `gradebook.pricing.price`.
- Deferred outcomes target decisions by `graded_response_id`.

Pune geometry is the presentation substrate. It must never replace or alter
the toy-world graph weights, answer keys, or grades.

The work stays under `viewer/` except for this specification and its
implementation plan. It does not modify the Foundry cast or judge path.

## Chosen map approach

Bundle an offline OpenStreetMap-derived road graph for a central Pune area
covering Shivajinagar, Deccan, the old city, and Swargate.

The map preparation step will:

1. Download drivable road ways, building footprints, water, green areas, and
   named landmarks for a fixed bounding box.
2. Convert road ways into a connected node-edge graph.
3. Select 20 visually distributed, well-connected road intersections.
4. Assign `J1` through `J20` deterministically to those intersections in five
   geographic bands of four nodes, matching the toy graph's layered topology.
5. Compute a road-following polyline for every directed toy edge using
   Dijkstra over the extracted Pune road graph.
6. Store the result as committed GeoJSON so the runtime requires no API key or
   network.

If two toy edges share physical road segments, their neon overlays receive
small lane offsets so both remain visible. Agents always move along the stored
road polyline; no path may cut across blocks or float between intersections.

OpenStreetMap attribution remains permanently visible.

## Simulation mapping

Each recording decision is a replay agent. This intentionally creates a dense
swarm resembling the references rather than preserving the previous fictional
four-driver model.

### `next_hop`

- Start at the query's junction.
- The chosen answer identifies the destination junction.
- Animate over the corresponding toy edge's Pune road polyline.
- If the chosen junction is invalid, show a stationary rejected agent and a
  visible data-error event; do not invent a route.
- The cheapest correct edge is rendered as the ghost route when the answer is
  wrong.

### `route_choice`

- Use the query's two candidate paths.
- The recorded `chosen` label selects candidate A or B.
- Animate the entire selected multi-edge route across the mapped Pune graph.
- The faster candidate becomes the yellow ghost when the choice is wrong.
- A deferred journey outcome later re-highlights this exact decision by its
  response ID.

### `eta_estimate`

- Use the query start and destination.
- Animate the authoritative shortest path computed from the toy graph.
- The agent's answer is a time estimate, not a route, so spatial motion shows
  the journey it was estimating.
- Correctness is based on the existing 15% checker tolerance.
- The HUD shows chosen minutes, correct minutes, and percentage error.

## Replay scheduling

The recording has many decisions across multiple models. The runtime groups
them into waves so the map remains readable and performs reliably:

- Default wave size: 24 agents.
- Agents within a wave start with deterministic stagger offsets.
- Completed agents fade to a low-opacity trail before the next wave.
- Playback speed choices: 0.5×, 1×, 2×, and 4×.
- “All agents” mode retains every completed marker at reduced opacity.
- “Focus” mode follows one selected agent and hides unrelated labels.

Every recording entry still appears. Wave grouping changes only presentation
time, never counts or results.

## Visual system

### City

- Real road widths classified by OpenStreetMap highway type.
- Road beds rendered as dark meshes with brighter lane-center lines.
- Extruded building footprints with deterministic height variation when OSM
  height is absent.
- Water and green areas rendered as distinct flat surfaces.
- Labels for Shivajinagar, Deccan, Shaniwar Wada, Saras Baug, and Swargate.
- Subtle night fog, ambient lights, and emissive route materials.

### Agents

- Small runner/vehicle-like arrow markers oriented to the road tangent.
- Model family determines color.
- Decision type determines marker silhouette or halo.
- Difficulty affects halo size.
- Labels appear only for the hovered, selected, or currently graded agent.

### Routes and grades

- Neutral future path: dark blue.
- Active chosen route: model color.
- Math-correct completion: green.
- Incorrect completion: red.
- Correct alternative ghost: yellow.
- Deferred reality outcome: a delayed pulse traveling backward along the route
  to the linked decision marker.

### Camera

- Opening overview contains the complete mapped graph.
- Orbit, zoom, and pan remain available.
- Presets: overview, street-level chase, top-down graph, and selected-agent
  follow.
- Camera movement is disabled or shortened under `prefers-reduced-motion`.

## Information surfaces

The primary HUD shows:

- Completed decisions / total decisions
- Correct decisions and correct rate
- Total cost and cost per correct decision
- Active wave
- Counts by decision type
- Counts by model

The selected-agent drawer shows:

- Model and response ID
- Decision type and difficulty
- Query ID and start/destination
- Chosen and correct answer
- Grade source
- Cost and token counts
- Route duration and path
- Deferred outcome when present

Filters support model, decision type, difficulty, correctness, and reality
outcome.

## Exported data

### `pune-map.geojson`

Contains prepared map layers:

- Roads with `highway`, `name`, and display width
- Buildings with optional source height
- Water and green areas
- Landmarks and labels

### `toyworld-roads.json`

Contains:

- Mapping of every `J1`–`J20` to an OSM road node and coordinate
- Road-following polyline for every directed toy edge
- Toy edge minutes
- Source OSM node/way provenance

### `run.json`

Schema version 2 contains one agent record per decision:

- `agent_id`
- `response_id`
- `model`
- `decision_type`
- `difficulty`
- `query_id`
- `start`
- `destination`
- `chosen`
- `correct_answer`
- `is_correct`
- `chosen_path`
- `correct_path`
- `cost_usd`
- token counts
- optional deferred outcome

Totals are reconciled with `ReplaySummary` and grouped aggregates.

## Error handling

- Export fails if the 20 toy nodes cannot be mapped to 20 distinct road
  intersections.
- Export fails if any toy edge lacks a connected Pune road path.
- Export fails if a recording query ID is missing from `QUERIES_BY_ID`.
- Export fails if an outcome targets an unknown response ID.
- Runtime schema validation occurs before scene construction.
- Missing assets show an actionable error panel.
- Zero correct decisions yield a null cost-per-correct value.

## Testing

### Python

- Exactly 20 toy nodes are mapped once.
- Every directed edge in `GRAPH` has a non-empty road polyline whose endpoints
  match the mapped nodes.
- Every recording decision exports exactly once.
- All three decision types are present.
- Chosen/correct paths for each decision type match the query semantics.
- Correctness uses each query's checker.
- Costs use the shared Gradebook price function.
- Outcomes resolve to the correct response.
- Totals match a local `ReplaySummary`.

### TypeScript

- Schema version 2 validation.
- Wave scheduling contains every agent exactly once.
- Route traversal interpolation stays on its supplied polyline.
- Selected-agent filtering.
- Outcome targeting by response ID.
- HUD accumulation uses exported totals.

### Visual smoke test

- Real Pune road and building detail is visible.
- Twenty mapped junctions appear on road intersections.
- Agents remain on road surfaces during animation.
- All three decision types animate.
- Correct, incorrect, ghost, and reality-grade treatments appear.
- Camera presets and filters work.
- OpenStreetMap attribution remains visible.

## Attribution

The referenced videos are:

- “Explore a high-scale agentic AI-powered simulation sandbox with Gemini
  Enterprise Agent Platform,” Google for Developers.
- “How we built 1,000 AI agents that run a marathon,” Google Cloud Tech.

The visual system is inspired by those demonstrations and the Apache-2.0
`GoogleCloudPlatform/race-condition` repository. No source is copied unless
later documented file-by-file in `viewer/VENDOR.md`.

OpenStreetMap data is credited to © OpenStreetMap contributors with a link to
the copyright page.

## Out of scope

- Live LLM calls
- A2A, WebSocket, or cloud agent infrastructure
- Google Maps APIs
- Real Pune traffic claims
- Editing routing policies from the viewer
- Adding the viewer to Foundry or CI
