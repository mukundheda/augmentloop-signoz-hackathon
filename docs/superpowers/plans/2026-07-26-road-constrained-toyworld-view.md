# Road-Constrained Toy-World View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the viewer so every current toy-world recording decision animates along detailed, locally bundled Pune road geometry.

**Architecture:** A Python exporter loads `GRAPH`, `QUERIES_BY_ID`, and the recording directly from the canonical source files, maps all 20 toy nodes to a connected Pune-style road grid, and exports schema-v2 agent journeys. A typed Three.js client schedules all decisions in waves, renders road/building geometry, and moves directional agent markers only along exported road polylines.

**Tech Stack:** Python 3.10+ standard library and `unittest`; TypeScript 5; Three.js; Vite; Vitest.

## Global Constraints

- Derive all simulation semantics from `GRAPH`, `QUERIES_BY_ID`, `shortest_path`, the recording, and `gradebook.pricing.price`.
- Do not modify toy-world or Gradebook production source.
- Export every recording decision exactly once.
- Bundle map assets locally; runtime requires no API key or network.
- Agents must interpolate only along exported road polylines.
- Preserve OpenStreetMap attribution and state that toy weights are not Pune traffic data.
- Do not modify Foundry, CI, or the judge path.

---

### Task 1: Replace the obsolete exporter with schema v2

**Files:**
- Modify: `viewer/export.py`
- Replace: `viewer/tests/test_export.py`
- Replace: `viewer/public/data/run.json`
- Replace: `viewer/public/data/world.geojson`
- Create: `viewer/public/data/toyworld-roads.json`
- Create: `viewer/public/data/pune-map.geojson`

**Interfaces:**
- Produces: `build_road_mapping() -> dict`, `build_run_document() -> dict`, `polyline_for_path(path: tuple[str, ...]) -> list[list[float]]`.

- [ ] **Step 1: Write failing exporter tests**

```python
def test_maps_every_graph_node_to_a_distinct_road_intersection(self):
    mapping = build_road_mapping()
    self.assertEqual(set(mapping["nodes"]), set(GRAPH))
    self.assertEqual(len({tuple(v["coordinate"]) for v in mapping["nodes"].values()}), 20)

def test_exports_every_recorded_decision_once(self):
    run = build_run_document()
    self.assertEqual(len(run["agents"]), 180)
    self.assertEqual(len({a["response_id"] for a in run["agents"]}), 180)

def test_exports_all_three_decision_types(self):
    run = build_run_document()
    self.assertEqual(
        {a["decision_type"] for a in run["agents"]},
        {"route_choice", "eta_estimate", "next_hop"},
    )

def test_every_toy_edge_has_a_road_polyline(self):
    mapping = build_road_mapping()
    expected = {(start, edge.to) for start, node in GRAPH.items() for edge in node.edges}
    self.assertEqual(set(map(tuple, mapping["edges"])), expected)
    self.assertTrue(all(len(edge["polyline"]) >= 2 for edge in mapping["edges"].values()))
```

- [ ] **Step 2: Run the tests and verify they fail on removed `WORLD` assumptions**

Run: `python -m unittest discover -s viewer/tests -p "test_export.py" -v`

- [ ] **Step 3: Implement canonical query and recording export**

Load `world.py` and `pricing.py` with `importlib.util` to avoid importing
optional telemetry dependencies. Reconstruct route-choice candidate paths using
`shortest_path` and `second_best_path`, derive next-hop single edges, and use
the shortest path for ETA decisions. Evaluate `query.checker(chosen,
query.correct)` and merge outcomes by response ID.

- [ ] **Step 4: Build deterministic road geometry**

Map the five layers of four toy nodes onto five Pune corridor bands. Create a
connected road network with named primary and secondary roads, intersections,
blocks, building footprints, water, and landmark features. Route every toy
edge through the road network with Dijkstra and write stable polylines.

- [ ] **Step 5: Verify tests and regenerate assets**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_export.py" -v
python viewer/export.py
```

### Task 2: Upgrade the replay domain and scheduler

**Files:**
- Replace: `viewer/src/domain.ts`
- Replace: `viewer/src/replay.ts`
- Replace: `viewer/src/replay.test.ts`

**Interfaces:**
- Produces: `parseRaceData(value) -> RaceRunV2`, `buildWaves(run, 24) -> ReplayWave[]`, `samplePolyline(points, progress) -> Position`.

- [ ] **Step 1: Write failing schema-v2 tests**

```typescript
it("schedules every agent exactly once in waves of at most 24", () => {
  const waves = buildWaves(run, 24);
  expect(waves.every((wave) => wave.agents.length <= 24)).toBe(true);
  expect(new Set(waves.flatMap((wave) => wave.agents.map((a) => a.response_id))).size)
    .toBe(run.agents.length);
});

it("samples positions on the supplied road polyline", () => {
  expect(samplePolyline([[0, 0], [10, 0], [10, 10]], 0.75)).toEqual([10, 5]);
});
```

- [ ] **Step 2: Verify the tests fail against schema v1**

Run: `npm.cmd test -- --run`

- [ ] **Step 3: Implement validation, wave scheduling, and arc-length interpolation**

Validate schema version 2, unique response IDs, all three decision types,
non-empty route polylines, optional outcomes, and exported totals. Schedule
agents in deterministic 24-agent waves and interpolate by cumulative road
distance rather than point index.

- [ ] **Step 4: Run TypeScript tests**

Run: `npm.cmd test -- --run`

### Task 3: Render detailed roads, buildings, and road-following agents

**Files:**
- Replace: `viewer/src/scene.ts`
- Replace: `viewer/src/hud.ts`
- Replace: `viewer/src/hud.test.ts`
- Modify: `viewer/src/main.ts`
- Modify: `viewer/src/styles.css`

**Interfaces:**
- Consumes schema-v2 map/run data and replay waves.
- Produces a scene with `play()`, `pause()`, `restart()`, `setSpeed()`, `setCameraPreset()`, `selectAgent()`, and `setFilters()`.

- [ ] **Step 1: Write failing HUD/filter tests**

```typescript
it("shows all three decision type totals", () => {
  const hud = createHud(root, run);
  expect(hud.element.querySelector("[data-type=route_choice]")).not.toBeNull();
  expect(hud.element.querySelector("[data-type=eta_estimate]")).not.toBeNull();
  expect(hud.element.querySelector("[data-type=next_hop]")).not.toBeNull();
});
```

- [ ] **Step 2: Verify the test fails**

Run: `npm.cmd test -- --run`

- [ ] **Step 3: Implement the detailed city and road renderer**

Render road beds as flat strips sized by road class, lane-center lines,
extruded building polygons, water, green areas, 20 junction markers, and named
landmarks. Render each active agent as an arrow mesh oriented to the next
polyline sample. Keep labels limited to hovered/selected agents.

- [ ] **Step 4: Implement replay waves, route grades, and controls**

Animate up to 24 active agents with deterministic stagger. Color completed
paths green/red, show yellow optimal ghosts, and pulse deferred outcomes at
their linked response routes. Add overview, chase, top-down, and follow camera
presets plus model/type/difficulty/result filters.

- [ ] **Step 5: Run tests and build**

Run:

```powershell
npm.cmd test -- --run
npm.cmd run build
```

### Task 4: Verify and rerun

**Files:**
- Modify: `viewer/README.md`
- Modify: `viewer/VENDOR.md`

- [ ] **Step 1: Document schema v2 and road-map preparation**

Document the new 20-node mapping, 180-agent replay, offline assets, controls,
and attribution.

- [ ] **Step 2: Run fresh verification**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_*.py" -v
npm.cmd test -- --run
npm.cmd run build
git diff --check
```

- [ ] **Step 3: Start the preview**

Run: `npm.cmd run dev -- --host 127.0.0.1 --port 5173`

Confirm HTTP 200 and that the browser shows detailed roads, buildings, 20
junctions, road-following agents, all three decision types, and OSM
attribution.
