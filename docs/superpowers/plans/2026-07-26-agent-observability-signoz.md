# Agent Observability and SigNoz Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every animated Pune ToyWorld agent expose a correlated trace, structured logs, Gradebook evidence, and safe navigation to its SigNoz trace, logs explorer, and dashboard.

**Architecture:** A Python synchronization boundary queries SigNoz's authenticated `POST /api/v5/query_range` endpoint for raw traces and logs, sanitizes and correlates results by `gen_ai.response.id`, and writes a browser-safe sidecar. The existing exporter merges synchronized evidence where available and otherwise generates a deterministic replay projection. The TypeScript viewer consumes one schema and renders Details, Trace, and Logs in the existing right-side inspector.

**Tech Stack:** Python 3.11 standard library, SigNoz Query Builder v5 API, OpenTelemetry/Gradebook field conventions, TypeScript 5.9, Three.js, Vitest/jsdom, Vite.

## Global Constraints

- Branch is stacked on `codex/race-view-pune` / PR #91.
- SigNoz is authoritative when synchronized evidence exists.
- Static replay must remain deterministic and require no SigNoz instance.
- Browser code and committed assets must never contain `SIGNOZ_API_KEY`.
- All SigNoz access is read-only.
- Correlation uses `gen_ai.response.id`; exact navigation uses validated trace IDs.
- Per-decision identifiers are never added as metric dimensions.
- Replay projections are visibly labelled and never presented as live telemetry.
- SigNoz origin must be `http` or `https`; all filter values must be encoded.
- Unix nanosecond timestamps remain decimal strings.

---

## File Structure

### New files

- `viewer/observability.py` — replay projections, sidecar validation, merge, coverage, and secret scanning.
- `viewer/signoz_client.py` — authenticated Query Builder v5 trace/log reads and response normalization.
- `viewer/sync_signoz.py` — CLI, time-range parsing, atomic sidecar write, and coverage output.
- `viewer/tests/test_observability.py` — projection and sidecar contract tests.
- `viewer/tests/test_signoz_client.py` — exact v5 request and normalization tests.
- `viewer/public/data/signoz-config.json` — public navigation configuration only.
- `viewer/src/observability.ts` — coverage, URL generation, span tree, and log filtering.
- `viewer/src/observability.test.ts` — TypeScript contract and URL tests.
- `viewer/src/inspector.ts` — Details/Trace/Logs inspector rendering and tab behavior.
- `viewer/src/inspector.test.ts` — jsdom rendering and interaction tests.

### Modified files

- `viewer/export.py` — merge synchronized evidence or replay projection into every agent.
- `viewer/tests/test_export.py` — require observability coverage for all 180 agents.
- `viewer/src/domain.ts` — add observability types and public SigNoz config.
- `viewer/src/replay.ts` — validate observability envelopes.
- `viewer/src/replay.test.ts` — validate live/replay and unsafe-data cases.
- `viewer/src/hud.ts` — delegate selected-agent rendering to the inspector.
- `viewer/src/hud.test.ts` — update selection expectations.
- `viewer/src/main.ts` — load navigation config and show global SigNoz coverage state.
- `viewer/src/styles.css` — inspector, tabs, span waterfall, logs, and connection badge styles.
- `viewer/README.md` — offline and SigNoz-connected workflows.
- `viewer/VENDOR.md` — record SigNoz API documentation references.

---

### Task 1: Deterministic Replay Observability Projection

**Files:**
- Create: `viewer/observability.py`
- Create: `viewer/tests/test_observability.py`

**Interfaces:**
- Produces: `build_replay_observability(agent: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `stable_hex_id(response_id: str, label: str, length: int) -> str`
- Produces: `coverage_for(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]`
- Consumes: the exporter agent dictionary after route, grade, cost, and outcome fields exist.

- [ ] **Step 1: Write failing projection tests**

```python
def test_replay_projection_is_deterministic_and_labelled():
    first = build_replay_observability(AGENT)
    second = build_replay_observability(AGENT)
    assert first == second
    assert first["mode"] == "replay"
    assert first["trace_id"] is None
    assert [span["name"] for span in first["spans"]] == [
        "gen_ai.model.request",
        "toyworld.route.decision",
        "gen_ai.evaluation.result",
        "toyworld.reality.outcome",
    ]
    assert {span["source"] for span in first["spans"]} == {"replay"}


def test_replay_projection_has_no_outcome_span_without_outcome():
    agent = {**AGENT, "outcome": None}
    result = build_replay_observability(agent)
    assert "toyworld.reality.outcome" not in {
        span["name"] for span in result["spans"]
    }
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_observability.py" -v
```

Expected: import failure because `viewer.observability` does not exist.

- [ ] **Step 3: Implement stable IDs and projection**

Use `hashlib.sha256(f"{response_id}:{label}".encode()).hexdigest()` and slice to
16 hex characters for span IDs. Use fixed relative nanosecond timestamps
`"0"`, `"1000000"`, `"2000000"`, and `"3000000"` so committed replay output is
stable. Set `trace_id` to `None`; projected IDs must not be eligible for exact
SigNoz navigation.

Each projected span must include:

```python
{
    "span_id": stable_hex_id(response_id, "grade", 16),
    "parent_span_id": stable_hex_id(response_id, "decision", 16),
    "trace_id": None,
    "name": "gen_ai.evaluation.result",
    "service_name": "toy-world",
    "start_time_unix_nano": "2000000",
    "duration_ms": 0.0,
    "status": "ok",
    "source": "replay",
    "attributes": {
        "gen_ai.response.id": response_id,
        "gen_ai.request.model": agent["model"],
        "gen_ai.evaluation.score.label":
            "correct" if agent["is_correct"] else "incorrect",
        "augmentloop.grade.source": "math",
        "augmentloop.cost.usd": agent["cost_usd"],
    },
    "linked_span_ids": [],
}
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_observability.py" -v
```

Expected: all projection tests pass.

- [ ] **Step 5: Commit**

```powershell
git add viewer/observability.py viewer/tests/test_observability.py
git commit -m "feat: add replay observability projections"
```

---

### Task 2: SigNoz Query Builder v5 Read Client

**Files:**
- Create: `viewer/signoz_client.py`
- Create: `viewer/tests/test_signoz_client.py`

**Interfaces:**
- Produces: `SigNozClient(origin: str, api_key: str, transport: Transport | None = None)`
- Produces: `query_evaluation_spans(start_ms: int, end_ms: int) -> list[dict[str, Any]]`
- Produces: `query_trace_spans(trace_ids: Sequence[str], start_ms: int, end_ms: int) -> list[dict[str, Any]]`
- Produces: `query_logs(trace_ids: Sequence[str], start_ms: int, end_ms: int) -> list[dict[str, Any]]`
- Produces: `normalize_raw_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]`
- Dependency: official SigNoz `POST /api/v5/query_range`, `requestType: "raw"`.

- [ ] **Step 1: Write failing request-shape tests**

```python
def test_evaluation_query_uses_v5_raw_trace_api():
    transport = RecordingTransport({"data": {"result": []}})
    client = SigNozClient("http://localhost:8080", "secret", transport)
    client.query_evaluation_spans(1000, 2000)
    request = transport.requests[0]
    assert request.url == "http://localhost:8080/api/v5/query_range"
    assert request.headers["SIGNOZ-API-KEY"] == "secret"
    assert request.body["requestType"] == "raw"
    spec = request.body["compositeQuery"]["queries"][0]["spec"]
    assert spec["signal"] == "traces"
    assert "name = 'gen_ai.evaluation.result'" in spec["filter"]["expression"]
    assert "service.name IN ('toy-world','toy-world-outcomes')" in spec["filter"]["expression"]


def test_log_query_filters_by_trace_ids():
    transport = RecordingTransport({"data": {"result": []}})
    client = SigNozClient("http://localhost:8080", "secret", transport)
    client.query_logs(["a" * 32, "b" * 32], 1000, 2000)
    spec = transport.requests[0].body["compositeQuery"]["queries"][0]["spec"]
    assert spec["signal"] == "logs"
    assert "trace_id IN ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')" == spec["filter"]["expression"]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_signoz_client.py" -v
```

Expected: import failure because `viewer.signoz_client` does not exist.

- [ ] **Step 3: Implement the authenticated transport and payload builders**

Use `urllib.request.Request` and `urllib.request.urlopen` with:

```python
headers = {
    "Content-Type": "application/json",
    "SIGNOZ-API-KEY": api_key,
}
```

The trace query selects:

```python
TRACE_FIELDS = [
    "trace_id", "span_id", "parent_span_id", "name", "timestamp",
    "duration_nano", "status_code", "service.name",
    "gen_ai.response.id", "gen_ai.request.model",
    "gen_ai.evaluation.score.label", "augmentloop.grade.source",
    "augmentloop.grade.reason", "augmentloop.cost.usd",
]
```

The log query selects:

```python
LOG_FIELDS = [
    "timestamp", "severity_text", "body", "trace_id", "span_id",
    "service.name", "augmentloop.failure.class",
]
```

Implement response normalization behind one function so response-shape changes
remain isolated from correlation logic. Accept `data.result`, `data.results.A`,
and `data.newResult.data.result` only; otherwise raise `SigNozResponseError`
containing no headers or API-key value.

- [ ] **Step 4: Add normalization and secret-redaction tests**

```python
def test_unknown_response_shape_does_not_echo_api_key():
    client = SigNozClient(
        "http://localhost:8080",
        "super-secret",
        RecordingTransport({"unexpected": True}),
    )
    with self.assertRaises(SigNozResponseError) as error:
        client.query_evaluation_spans(1000, 2000)
    self.assertNotIn("super-secret", str(error.exception))
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_signoz_client.py" -v
```

Expected: all client tests pass.

- [ ] **Step 6: Commit**

```powershell
git add viewer/signoz_client.py viewer/tests/test_signoz_client.py
git commit -m "feat: add read-only SigNoz query client"
```

---

### Task 3: Synchronization, Correlation, and Atomic Sidecar

**Files:**
- Modify: `viewer/observability.py`
- Create: `viewer/sync_signoz.py`
- Modify: `viewer/tests/test_observability.py`
- Modify: `viewer/tests/test_signoz_client.py`

**Interfaces:**
- Produces: `correlate_signoz(spans, trace_spans, logs, response_ids, config) -> dict[str, Any]`
- Produces: `load_sidecar(path: Path) -> dict[str, Any]`
- Produces: CLI `python viewer/sync_signoz.py --lookback-minutes 30`
- Writes: `.scratch/viewer-signoz-observability.json` via temporary file plus `Path.replace`.

- [ ] **Step 1: Write failing correlation tests**

```python
def test_correlation_joins_by_response_id_and_attaches_logs():
    sidecar = correlate_signoz(
        spans=[evaluation_span("resp-1", trace_id="a" * 32, span_id="b" * 16)],
        trace_spans=[operation_span(trace_id="a" * 32, span_id="c" * 16)],
        logs=[log_row(trace_id="a" * 32, span_id="b" * 16)],
        response_ids={"resp-1", "resp-2"},
        config=CONFIG,
    )
    assert sidecar["entries"]["resp-1"]["mode"] == "signoz"
    assert sidecar["entries"]["resp-1"]["trace_id"] == "a" * 32
    assert len(sidecar["entries"]["resp-1"]["logs"]) == 1
    assert sidecar["coverage"] == {"matched": 1, "total": 2}


def test_duplicate_math_evaluation_is_rejected():
    duplicated = evaluation_span("resp-1"), evaluation_span("resp-1")
    with self.assertRaisesRegex(CorrelationError, "duplicate math evaluation"):
        correlate_signoz(duplicated, [], [], {"resp-1"}, CONFIG)
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_observability.py" -v
```

Expected: failure because `correlate_signoz` is missing.

- [ ] **Step 3: Implement correlation and strict identifier validation**

Validate trace IDs with `re.fullmatch(r"[0-9a-fA-F]{32}", value)` and span IDs
with `re.fullmatch(r"[0-9a-fA-F]{16}", value)`. Normalize them to lowercase.
Join the evaluation span to all same-trace spans and logs, sort by timestamp,
and set exact navigation links only after validation.

- [ ] **Step 4: Implement the CLI and atomic write**

CLI arguments:

```text
--lookback-minutes INTEGER     default 30
--from RFC3339                optional; must be paired with --to
--to RFC3339                  optional; must be paired with --from
--output PATH                 default .scratch/viewer-signoz-observability.json
--dashboard-path PATH         optional
```

Read `SIGNOZ_URL` and `SIGNOZ_API_KEY`. Load response IDs from the committed
recording. Query evaluation spans, then all spans and logs for discovered trace
IDs. Serialize to a sibling `.tmp` file, flush, close, and call `Path.replace`
only after secret scanning succeeds.

- [ ] **Step 5: Test failed synchronization preserves a valid sidecar**

Use a temporary directory containing `{"schema_version":1,"entries":{}}`.
Inject a transport error and assert the original bytes remain unchanged.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_*.py" -v
```

Expected: all synchronization and correlation tests pass.

- [ ] **Step 7: Commit**

```powershell
git add viewer/observability.py viewer/signoz_client.py viewer/sync_signoz.py viewer/tests/test_observability.py viewer/tests/test_signoz_client.py
git commit -m "feat: correlate Gradebook agents with SigNoz"
```

---

### Task 4: Export Schema v3 With Live/Replay Evidence

**Files:**
- Modify: `viewer/export.py:268`
- Modify: `viewer/tests/test_export.py`
- Modify: `viewer/public/data/run.json`
- Create: `viewer/public/data/signoz-config.json`

**Interfaces:**
- Consumes: `.scratch/viewer-signoz-observability.json` when present.
- Produces: `run.json` schema version 3 with `observability` on every agent.
- Produces: top-level `observability_coverage`.

- [ ] **Step 1: Write failing exporter tests**

```python
def test_every_agent_has_observability(self):
    run = export.build_run_document()
    self.assertEqual(run["schema_version"], 3)
    self.assertEqual(len(run["agents"]), 180)
    self.assertTrue(all("observability" in agent for agent in run["agents"]))
    self.assertEqual(
        {agent["observability"]["mode"] for agent in run["agents"]},
        {"replay"},
    )


def test_sidecar_entry_replaces_projection(self):
    run = export.build_run_document(sidecar_path=self.sidecar_path)
    matched = next(a for a in run["agents"] if a["response_id"] == "resp-1")
    self.assertEqual(matched["observability"]["mode"], "signoz")
    self.assertEqual(matched["observability"]["trace_id"], "a" * 32)
```

- [ ] **Step 2: Run exporter tests and verify RED**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_export.py" -v
```

Expected: schema version remains 2 and agents lack `observability`.

- [ ] **Step 3: Merge evidence in `build_run_document`**

Add:

```python
def build_run_document(
    recording_path: Path = RECORDING,
    sidecar_path: Path = SIGNOZ_SIDECAR,
) -> dict[str, Any]:
```

Build the agent first, then choose:

```python
agent["observability"] = synchronized.get(
    agent["response_id"],
    build_replay_observability(agent),
)
```

Compute top-level coverage from the final agents, not from sidecar metadata.

- [ ] **Step 4: Generate and inspect deterministic committed assets**

Run:

```powershell
python viewer/export.py
```

Expected: 180 agents, all replay mode when no local sidecar is present, with no
changes to Pune road geometry.

- [ ] **Step 5: Run exporter tests and verify GREEN**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_export.py" -v
```

Expected: all exporter tests pass.

- [ ] **Step 6: Commit**

```powershell
git add viewer/export.py viewer/observability.py viewer/tests/test_export.py viewer/public/data/run.json viewer/public/data/signoz-config.json
git commit -m "feat: export per-agent observability evidence"
```

---

### Task 5: TypeScript Contract, Coverage, and Safe SigNoz URLs

**Files:**
- Modify: `viewer/src/domain.ts:5`
- Modify: `viewer/src/replay.ts`
- Modify: `viewer/src/replay.test.ts`
- Create: `viewer/src/observability.ts`
- Create: `viewer/src/observability.test.ts`

**Interfaces:**
- Produces: `observabilityCoverage(agents: AgentDecision[]): CoverageState`
- Produces: `buildSigNozLinks(config: SigNozConfig, agent: AgentDecision): SigNozLinks`
- Produces: `spanTree(spans: AgentSpan[]): SpanTreeNode[]`
- Produces: `filterLogs(logs: AgentLog[], mode: LogFilter, spanId?: string): AgentLog[]`

- [ ] **Step 1: Write failing schema and URL tests**

```typescript
it("keeps Unix nanoseconds as strings", () => {
  const run = parseRaceData(fixtureWithObservability);
  expect(run.agents[0].observability.spans[0].start_time_unix_nano)
    .toBe("1785001000000000000");
});

it("builds an exact trace URL only for synchronized evidence", () => {
  const links = buildSigNozLinks(config, synchronizedAgent);
  expect(links.trace).toContain("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
  expect(buildSigNozLinks(config, replayAgent).trace).toBeUndefined();
});

it("rejects javascript and credential-bearing origins", () => {
  expect(() => parseSigNozConfig({ signoz_origin: "javascript:alert(1)" }))
    .toThrow(/http or https/);
  expect(() => parseSigNozConfig({ signoz_origin: "http://user:pass@localhost:8080" }))
    .toThrow(/credentials/);
});
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
npm.cmd --prefix viewer test -- --run src/observability.test.ts src/replay.test.ts
```

Expected: missing observability types and functions.

- [ ] **Step 3: Add strict schema parsing**

Require:

- `mode` is `signoz` or `replay`;
- `response_id` matches the containing agent;
- live trace IDs are 32 lowercase hex characters;
- span IDs are 16 lowercase hex characters;
- nanosecond timestamps are digit strings;
- attributes contain only string, finite number, or boolean values;
- replay entries have no exact trace ID.

- [ ] **Step 4: Add URL builder and coverage logic**

Return:

```typescript
type CoverageState =
  | { kind: "connected"; matched: number; total: number }
  | { kind: "partial"; matched: number; total: number }
  | { kind: "offline"; matched: 0; total: number };
```

Use `new URL()` against the validated origin. Put query expressions in
`URLSearchParams`; never concatenate raw response IDs.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
npm.cmd --prefix viewer test -- --run src/observability.test.ts src/replay.test.ts
```

Expected: all schema, coverage, tree, filter, and URL tests pass.

- [ ] **Step 6: Commit**

```powershell
git add viewer/src/domain.ts viewer/src/replay.ts viewer/src/replay.test.ts viewer/src/observability.ts viewer/src/observability.test.ts
git commit -m "feat: add viewer observability contract"
```

---

### Task 6: Right-Side Details, Trace, and Logs Inspector

**Files:**
- Create: `viewer/src/inspector.ts`
- Create: `viewer/src/inspector.test.ts`
- Modify: `viewer/src/hud.ts:26`
- Modify: `viewer/src/hud.test.ts`
- Modify: `viewer/src/styles.css`

**Interfaces:**
- Produces: `createInspector(host: HTMLElement, config: SigNozConfig): AgentInspector`
- Produces: `AgentInspector.show(agent: AgentDecision): void`
- Produces: `AgentInspector.selectTab(tab: "details" | "trace" | "logs"): void`
- Produces: `AgentInspector.destroy(): void`
- Consumes: safe links from `buildSigNozLinks`.

- [ ] **Step 1: Write failing inspector tests**

```typescript
it("renders replay evidence without an exact trace action", () => {
  const inspector = createInspector(host, config);
  inspector.show(replayAgent);
  expect(host.textContent).toContain("REPLAY EVIDENCE");
  expect(host.textContent).toContain("Find by response ID in SigNoz");
  expect(host.textContent).not.toContain("Open trace in SigNoz");
});

it("renders a synchronized span waterfall and correlated logs", () => {
  const inspector = createInspector(host, config);
  inspector.show(synchronizedAgent);
  inspector.selectTab("trace");
  expect(host.textContent).toContain("gen_ai.evaluation.result");
  inspector.selectTab("logs");
  expect(host.textContent).toContain("grade resolved incorrect");
});
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
npm.cmd --prefix viewer test -- --run src/inspector.test.ts
```

Expected: import failure because `inspector.ts` does not exist.

- [ ] **Step 3: Implement semantic tab and action markup**

Use native buttons with `role="tab"`, `aria-selected`, and associated
`role="tabpanel"`. External navigation uses `<a target="_blank"
rel="noreferrer">`. Copy actions use `navigator.clipboard.writeText` only after
an explicit click and expose a short success/error status in an `aria-live`
region.

- [ ] **Step 4: Implement trace waterfall and log filters**

Trace rows display:

- indentation from parent depth;
- source badge;
- status;
- duration;
- linked reality-grade marker.

Log filters are `all`, `warnings-errors`, and `selected-span`. Empty live logs
render `No trace-correlated logs returned by SigNoz`; replay logs remain
labelled.

- [ ] **Step 5: Integrate inspector into the HUD**

Keep summary totals and model/type panels in `hud.ts`. Replace the old
hand-built selected-agent block with `inspector.show(agent)`.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
npm.cmd --prefix viewer test -- --run src/inspector.test.ts src/hud.test.ts
```

Expected: all inspector and HUD tests pass.

- [ ] **Step 7: Commit**

```powershell
git add viewer/src/inspector.ts viewer/src/inspector.test.ts viewer/src/hud.ts viewer/src/hud.test.ts viewer/src/styles.css
git commit -m "feat: add agent trace and logs inspector"
```

---

### Task 7: Global SigNoz State and Viewer Integration

**Files:**
- Modify: `viewer/src/main.ts:13`
- Modify: `viewer/src/hud.ts`
- Modify: `viewer/src/hud.test.ts`
- Modify: `viewer/src/styles.css`

**Interfaces:**
- Consumes: `/data/signoz-config.json`
- Consumes: top-level `observability_coverage`
- Produces: global connection badge and dashboard navigation.

- [ ] **Step 1: Write failing coverage badge tests**

```typescript
it.each([
  [{ kind: "connected", matched: 180, total: 180 }, "SIGNOZ CONNECTED · 180/180"],
  [{ kind: "partial", matched: 142, total: 180 }, "SIGNOZ PARTIAL · 142/180"],
  [{ kind: "offline", matched: 0, total: 180 }, "REPLAY MODE · SIGNOZ OFFLINE"],
])("renders explicit observability coverage", (coverage, expected) => {
  const hud = createHud(host, run, config);
  hud.setCoverage(coverage as CoverageState);
  expect(host.textContent).toContain(expected);
});
```

- [ ] **Step 2: Run focused test and verify RED**

Run:

```powershell
npm.cmd --prefix viewer test -- --run src/hud.test.ts
```

Expected: `setCoverage` does not exist.

- [ ] **Step 3: Load public config and wire inspector**

Load config beside run/map/roads. If config parsing fails, use:

```typescript
{
  signoz_origin: null,
  dashboard_path: null,
  service_names: ["toy-world", "toy-world-outcomes"]
}
```

The map and replay must still boot. Disable only SigNoz navigation actions.

- [ ] **Step 4: Render the global state badge**

Derive coverage from parsed agents rather than trusting JSON totals. Use
high-contrast green for connected, amber for partial, and muted blue for
offline.

- [ ] **Step 5: Run focused and complete TypeScript tests**

Run:

```powershell
npm.cmd --prefix viewer test -- --run
```

Expected: all TypeScript tests pass.

- [ ] **Step 6: Commit**

```powershell
git add viewer/src/main.ts viewer/src/hud.ts viewer/src/hud.test.ts viewer/src/styles.css
git commit -m "feat: surface SigNoz connection coverage"
```

---

### Task 8: Documentation, Full Verification, and Browser QA

**Files:**
- Modify: `viewer/README.md`
- Modify: `viewer/VENDOR.md`

**Interfaces:**
- Documents: offline export, SigNoz synchronization, safe configuration, and troubleshooting.

- [ ] **Step 1: Update usage documentation**

Document these exact flows:

```powershell
# Deterministic replay
python viewer/export.py
npm.cmd --prefix viewer run dev

# Synchronize a recent local SigNoz run
$env:SIGNOZ_URL = "http://localhost:8080"
python viewer/sync_signoz.py --lookback-minutes 30
python viewer/export.py
npm.cmd --prefix viewer run dev
```

State that `SIGNOZ_API_KEY` must already exist in the environment and never
belongs in `signoz-config.json`.

- [ ] **Step 2: Run complete Python verification**

Run:

```powershell
python -m unittest discover -s viewer/tests -p "test_*.py" -v
```

Expected: zero failures.

- [ ] **Step 3: Run complete frontend verification**

Run:

```powershell
npm.cmd --prefix viewer test -- --run
npm.cmd --prefix viewer run build
```

Expected: zero test failures and successful TypeScript/Vite build.

- [ ] **Step 4: Verify generated output contains no secret**

With a test-only key in the environment, run the fixture synchronizer and:

```powershell
rg -n "test-only-signoz-secret|SIGNOZ-API-KEY|authorization" viewer/public/data .scratch/viewer-signoz-observability.json
```

Expected: no matches.

- [ ] **Step 5: Perform browser QA**

Verify:

1. Pune renders with road-constrained moving dots.
2. Header shows offline mode without a sidecar.
3. Selecting an agent exposes Details, Trace, and Logs.
4. Replay evidence is labelled.
5. Response-ID search and dashboard links use the configured SigNoz origin.
6. Loading a synchronized fixture changes coverage to partial/connected.
7. Exact trace and logs actions appear only for synchronized agents.
8. No browser errors or warnings appear.

- [ ] **Step 6: Commit documentation**

```powershell
git add viewer/README.md viewer/VENDOR.md
git commit -m "docs: explain SigNoz-connected viewer workflow"
```

- [ ] **Step 7: Inspect final branch scope**

Run:

```powershell
git status -sb
git diff --stat codex/race-view-pune...HEAD
git log --oneline codex/race-view-pune..HEAD
```

Expected: only the approved design, plan, observability implementation,
generated viewer data, tests, and documentation appear.

---

## Final Acceptance Checklist

- [ ] Every one of 180 agents has an observability envelope.
- [ ] Offline replay produces deterministic projected spans and logs.
- [ ] SigNoz v5 queries authenticate only in Python.
- [ ] Live evidence is matched by `gen_ai.response.id`.
- [ ] Duplicate and contradictory correlations fail safely.
- [ ] Connection coverage is explicit and derived from agent data.
- [ ] Inspector exposes Details, Trace, and Logs.
- [ ] Exact trace/log navigation requires validated live identifiers.
- [ ] Dashboard navigation is configurable.
- [ ] No API key appears in browser assets or error text.
- [ ] Python tests, TypeScript tests, production build, and browser QA pass.
