# Pune Race View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a deterministic Three.js replay of the toy world's four AI drivers racing across a locally bundled central Pune map.

**Architecture:** A Python exporter converts the existing canonical world, replay recording, and Gradebook prices into validated static JSON. A standalone Vite/TypeScript/Three.js app loads those files, constructs a replay timeline, and renders Pune context, alternative routes, animated drivers, grades, late-outcome links, and headline metrics.

**Tech Stack:** Python 3.10+, pytest, TypeScript 5, Vite, Three.js, Vitest, OpenStreetMap-derived GeoJSON.

## Global Constraints

- Keep the viewer additive under `viewer/`; do not modify existing toy-world or Gradebook production source.
- Do not modify `README.md`, `casting.yaml`, `casting.yaml.lock`, or CI.
- The runtime must be offline and require no API key.
- Preserve unrelated untracked files.
- Use the existing Gradebook price function and replay summary as the only headline-metric authorities.
- Display OpenStreetMap attribution and retain/document Apache-2.0 attribution for copied upstream code.
- The first version replays committed decisions; it does not launch live LLM agents.

---

### Task 1: Export deterministic race data

**Files:**
- Create: `viewer/export.py`
- Create: `viewer/tests/conftest.py`
- Create: `viewer/tests/test_export.py`
- Create: `viewer/public/data/world.geojson`
- Create: `viewer/public/data/run.json`

**Interfaces:**
- Consumes: `toyworld.world.WORLD`, `toyworld.replay.load_recording`, `toyworld.replay.replay`, `gradebook.pricing.price`.
- Produces: `build_world_feature_collection() -> dict`, `build_run_document() -> dict`, and `export_data(output_dir: Path) -> None`.

- [ ] **Step 1: Write failing exporter tests**

```python
def test_exports_one_simulation_route_per_world_option():
    world = build_world_feature_collection()
    routes = [f for f in world["features"] if f["properties"]["kind"] == "simulation-route"]
    assert len(routes) == sum(len(j.options) for j in WORLD)


def test_run_totals_reconcile_with_replay_summary():
    document = build_run_document(RECORDING)
    summary = replay(RECORDING, world_provider=TracerProvider())
    assert document["totals"]["decisions"] == summary.decisions
    assert document["totals"]["correct"] == summary.correct
    assert document["totals"]["total_cost_usd"] == pytest.approx(summary.total_cost_usd)
    assert document["totals"]["cost_per_correct_usd"] == pytest.approx(
        summary.cost_per_correct_usd
    )


def test_every_outcome_targets_an_exported_decision():
    document = build_run_document(RECORDING)
    response_ids = {
        decision["response_id"]
        for driver in document["drivers"]
        for decision in driver["decisions"]
    }
    assert all(o["graded_response_id"] in response_ids for o in document["outcomes"])
```

- [ ] **Step 2: Verify exporter tests fail because `viewer/export.py` does not exist**

Run: `python -m pytest viewer/tests/test_export.py -v`

Expected: collection failure for missing `export`.

- [ ] **Step 3: Implement deterministic export**

Implement:

```python
def build_run_document(recording_path: Path = RECORDING) -> dict:
    decisions, outcomes = load_recording(recording_path)
    drivers = []
    for driver_id in _drivers_in_order(decisions):
        driver_decisions = [d for d in decisions if d.driver == driver_id]
        drivers.append({
            "id": driver_id,
            "model": driver_decisions[0].model,
            "decisions": [{
                "junction": d.junction,
                "stage_index": _stage_index(d.junction),
                "chosen": d.chosen,
                "true_fastest": d.true_fastest,
                "correct": d.chosen == d.true_fastest,
                "travel_time_min": d.options[d.chosen],
                "input_tokens": d.input_tokens,
                "output_tokens": d.output_tokens,
                "cost_usd": price(d.model, d.input_tokens, d.output_tokens),
                "response_id": d.response_id,
            } for d in driver_decisions],
        })
    summary = replay(recording_path, world_provider=TracerProvider())
    return {
        "schema_version": 1,
        "generated_from": str(recording_path.as_posix()),
        "drivers": drivers,
        "outcomes": [asdict(outcome) for outcome in outcomes],
        "totals": {
            "decisions": summary.decisions,
            "correct": summary.correct,
            "total_cost_usd": summary.total_cost_usd,
            "outcomes": summary.outcomes,
            "cost_per_correct_usd": summary.cost_per_correct_usd,
        },
    }
```

Construct three consecutive simulation stages over the approved Pune corridor,
with one GeoJSON `LineString` per `WORLD` option and stable route ordering.

- [ ] **Step 4: Run exporter tests and generate committed data**

Run:

```powershell
python -m pytest viewer/tests/test_export.py -v
python viewer/export.py
```

Expected: tests pass and both JSON assets are written.

- [ ] **Step 5: Commit exporter slice**

```powershell
git add viewer/export.py viewer/tests viewer/public/data/world.geojson viewer/public/data/run.json
git commit -m "feat(viewer): export deterministic race data"
```

### Task 2: Add validated replay domain

**Files:**
- Create: `viewer/package.json`
- Create: `viewer/tsconfig.json`
- Create: `viewer/vite.config.ts`
- Create: `viewer/index.html`
- Create: `viewer/src/domain.ts`
- Create: `viewer/src/replay.ts`
- Create: `viewer/src/replay.test.ts`

**Interfaces:**
- Produces: `parseRaceData(value: unknown): RaceRun`, `buildTimeline(run: RaceRun): ReplayEvent[]`, and `resolveOutcomeTargets(run: RaceRun): Map<string, Decision>`.

- [ ] **Step 1: Write failing TypeScript tests**

```typescript
it("targets late outcomes at their graded response IDs", () => {
  const targets = resolveOutcomeTargets(runFixture);
  expect(targets.get("driver-3")?.junction).toBe("J1");
  expect(targets.get("driver-4")?.junction).toBe("J2");
});

it("accumulates the exported headline totals without recomputing pricing", () => {
  const final = buildTimeline(runFixture).at(-1);
  expect(final?.totals.costPerCorrectUsd).toBe(runFixture.totals.cost_per_correct_usd);
});
```

- [ ] **Step 2: Install dependencies and verify tests fail**

Run:

```powershell
cd viewer
npm install
npm test -- --run
```

Expected: failure because replay modules are missing.

- [ ] **Step 3: Implement strict domain parsing and timeline construction**

Define typed schema guards for schema version 1. Reject duplicate response IDs,
unknown outcome links, empty decision lists, and non-finite costs. Build a
timeline with `start`, `decision-start`, `decision-resolved`, `driver-finished`,
`outcome`, and `complete` events.

- [ ] **Step 4: Verify domain tests pass**

Run: `npm test -- --run`

Expected: all domain tests pass.

- [ ] **Step 5: Commit domain slice**

```powershell
git add viewer/package.json viewer/package-lock.json viewer/tsconfig.json viewer/vite.config.ts viewer/index.html viewer/src
git commit -m "feat(viewer): add validated replay timeline"
```

### Task 3: Render the Pune race

**Files:**
- Create: `viewer/src/main.ts`
- Create: `viewer/src/scene.ts`
- Create: `viewer/src/paths.ts`
- Create: `viewer/src/labels.ts`
- Create: `viewer/src/styles.css`
- Create: `viewer/src/types/three-addons.d.ts` if required by TypeScript.

**Interfaces:**
- Consumes: parsed world/run data and replay events.
- Produces: `createRaceScene(container, world, run) -> RaceScene` with `apply(event)`, `resize()`, `resetCamera()`, and `dispose()`.

- [ ] **Step 1: Add a failing smoke-level DOM test**

```typescript
it("creates one accessible driver row for each replay driver", () => {
  const root = document.createElement("div");
  renderHud(root, runFixture);
  expect(root.querySelectorAll("[data-driver-id]")).toHaveLength(4);
});
```

- [ ] **Step 2: Verify the smoke test fails because the HUD does not exist**

Run: `npm test -- --run`

- [ ] **Step 3: Implement scene, paths, labels, drivers, and HUD**

Render:

- Dark ground plane and simplified Pune building blocks
- Three alternative-route stages with Catmull-Rom curves
- Start/finish gates and junction labels
- Four colored driver markers with model labels
- Correct/incorrect/ghost path states
- Live exported totals and driver progress
- Play/pause, restart, speed, and reset-camera controls
- Persistent OpenStreetMap attribution

Honor `prefers-reduced-motion` by stepping decisions and suppressing pulses.

- [ ] **Step 4: Verify tests and production build**

Run:

```powershell
npm test -- --run
npm run build
```

Expected: tests and TypeScript/Vite build pass without warnings.

- [ ] **Step 5: Commit render slice**

```powershell
git add viewer/src viewer/index.html
git commit -m "feat(viewer): render animated Pune race"
```

### Task 4: Add Pune context and legal attribution

**Files:**
- Create: `viewer/public/data/pune-context.geojson`
- Create: `viewer/NOTICE`
- Create: `viewer/VENDOR.md`

**Interfaces:**
- Consumes: a bounded Shivajinagar–Deccan–Swargate OpenStreetMap extract.
- Produces: a reduced runtime asset containing only required geometry and labels.

- [ ] **Step 1: Add a failing asset validation test**

```python
def test_pune_context_has_osm_attribution_and_bounded_geometry():
    context = json.loads(PUNE_CONTEXT.read_text())
    assert context["metadata"]["attribution"] == "© OpenStreetMap contributors"
    assert context["metadata"]["corridor"] == "Shivajinagar–Deccan–Swargate"
    assert len(context["features"]) > 0
```

- [ ] **Step 2: Verify the validation test fails because the asset is absent**

Run: `python -m pytest viewer/tests -v`

- [ ] **Step 3: Fetch and reduce OpenStreetMap context**

Use an Overpass query bounded around the corridor to collect major roads,
building footprints, water, green areas, and the three place labels. Store the
retrieval date and bounds in asset metadata. Simplify coordinates enough to
keep the asset practical for a demo.

- [ ] **Step 4: Add attribution documents and verify**

Document upstream `race-condition` source/commit/file provenance if code was
copied, plus OpenStreetMap license/attribution details. Run:

```powershell
python -m pytest viewer/tests -v
npm run build
```

- [ ] **Step 5: Commit attribution slice**

```powershell
git add viewer/public/data/pune-context.geojson viewer/NOTICE viewer/VENDOR.md viewer/tests
git commit -m "feat(viewer): add offline Pune map context"
```

### Task 5: End-to-end verification and local handoff

**Files:**
- Create: `viewer/README.md`
- Modify only viewer files if verification reveals defects.

**Interfaces:**
- Produces: a reproducible local command and verified URL.

- [ ] **Step 1: Run all relevant Python tests**

Run:

```powershell
python -m pytest reference-library/tests toy-world/tests viewer/tests -v
```

Expected: all pass.

- [ ] **Step 2: Run all viewer checks**

Run:

```powershell
cd viewer
npm test -- --run
npm run build
```

Expected: all pass with no TypeScript errors.

- [ ] **Step 3: Start the development server**

Run: `npm run dev -- --host 127.0.0.1`

Expected: Vite reports a local URL, normally `http://127.0.0.1:5173/`.

- [ ] **Step 4: Perform browser smoke verification**

Confirm the page shows:

- A Pune-labeled city scene and attribution
- Four labeled drivers
- Three multiple-route stages
- Green and red graded choices
- Ghost fastest routes on wrong choices
- HUD totals matching `run.json`
- Driver 3 late grade targeting J1
- Driver 4 late grade targeting J2

- [ ] **Step 5: Document and commit the runnable handoff**

```powershell
git add viewer/README.md
git commit -m "docs(viewer): add local run instructions"
```
