# Agent Traceability and SigNoz Integration Design

**Date:** 2026-07-26  
**Branch:** `codex/agent-observability-signoz`  
**Base:** `codex/race-view-pune` / PR #91  
**Related issues:** #88, #89, #90

## Objective

Make every animated ToyWorld agent an observability entry point. Selecting an
agent in the Pune view must reveal the decision's trace, correlated logs, and
Gradebook evidence, and must provide direct navigation into SigNoz.

The feature uses a hybrid model:

- SigNoz is the authoritative observability source when correlation data has
  been synchronized.
- The committed replay remains a deterministic offline fallback.
- No SigNoz API key, session token, or privileged query is exposed to browser
  code or committed output.

## Scope

This increment delivers:

1. A versioned per-agent observability envelope in the viewer data contract.
2. A server-side synchronization/export command that correlates Gradebook
   decisions with SigNoz traces and logs.
3. A replay projection for agents that do not have synchronized SigNoz data.
4. A right-side inspector with Details, Trace, and Logs tabs.
5. Safe links to the exact SigNoz trace, correlated logs, and Gradebook
   dashboard.
6. Explicit connected, partial, and offline coverage states.
7. Automated contract, correlation, URL, rendering, and secret-leakage tests.

This increment does not:

- run SigNoz API queries directly from the browser;
- store SigNoz credentials in Vite environment variables;
- replace the existing Gradebook dashboards;
- turn the viewer into a general-purpose trace explorer;
- make write operations against SigNoz;
- claim that a replay projection is live telemetry.

## Architecture

```text
                         ┌──────────────────────────────┐
ToyWorld recording ─────►│ viewer/export.py             │
                         │ - decision and route export  │
                         │ - replay trace projection    │
                         └──────────────┬───────────────┘
                                        │
SigNoz API ──sync_signoz.py─────────────┤ merge by gen_ai.response.id
  traces                                  │
  span links                              ▼
  correlated logs              observability-enriched run.json
  dashboard identity                     │
                                        ▼
                              Three.js Pune viewer
                              - map and agent dots
                              - Details / Trace / Logs
                              - SigNoz navigation
```

The synchronization step is deliberately outside the browser. It reads a
SigNoz API key from the process environment, performs read-only queries, and
writes only sanitized observability evidence to a sidecar. The normal exporter
merges that sidecar into `run.json`.

The browser consumes one stable schema in both modes. It does not need to know
how the evidence was acquired.

## Data Contract

`AgentDecision` gains an `observability` property:

```ts
type ObservabilityMode = "signoz" | "replay";

interface AgentObservability {
  mode: ObservabilityMode;
  response_id: string;
  service_name: string;
  trace_id?: string;
  evaluation_span_id?: string;
  synchronized_at?: string;
  spans: AgentSpan[];
  logs: AgentLog[];
  links: SigNozLinks;
}

interface AgentSpan {
  span_id: string;
  parent_span_id?: string;
  trace_id?: string;
  name: string;
  service_name: string;
  start_time_unix_nano: string;
  duration_ms: number;
  status: "unset" | "ok" | "error";
  source: "signoz" | "replay";
  attributes: Record<string, string | number | boolean>;
  linked_span_ids: string[];
}

interface AgentLog {
  timestamp_unix_nano: string;
  severity: "TRACE" | "DEBUG" | "INFO" | "WARN" | "ERROR" | "FATAL";
  body: string;
  source: "signoz" | "replay";
  trace_id?: string;
  span_id?: string;
  attributes: Record<string, string | number | boolean>;
}

interface SigNozLinks {
  trace?: string;
  logs?: string;
  dashboard: string;
}
```

All nanosecond timestamps are decimal strings. JavaScript numbers cannot safely
represent current Unix nanosecond values.

Per-decision identifiers such as `response_id`, `trace_id`, and `span_id` are
used for correlation and navigation only. They must not become metric
dimensions or dashboard groupings.

## SigNoz Correlation

The synchronization command reads:

- `SIGNOZ_URL`, defaulting to `http://localhost:8080`;
- `SIGNOZ_API_KEY`, required for synchronization;
- an optional dashboard ID or path;
- a bounded time range covering the ToyWorld run.

It performs read-only SigNoz queries and selects
`gen_ai.evaluation.result` spans for:

- `service.name = toy-world`;
- `service.name = toy-world-outcomes`.

The primary join key is `gen_ai.response.id`.

For each response ID, the synchronizer resolves:

1. The Gradebook evaluation span.
2. Its containing trace and parent operation span when present.
3. Linked reality-grade spans.
4. Logs carrying the same trace ID or span ID.
5. All attributes needed by the inspector.

The command rejects:

- two math-evaluation spans claiming the same response ID within the selected
  run;
- a returned span whose trace ID is malformed;
- a reality grade whose response ID does not identify a decision;
- a log that claims a conflicting trace/span relationship.

Missing evidence is not fatal. It produces partial coverage and a warning.

The sanitized sidecar contains no request headers, API keys, cookies, or
authorization material. A test scans serialized output for common secret
field names and the configured API-key value.

## Replay Projection

When a response ID has no synchronized SigNoz entry, the exporter constructs a
deterministic projection from committed facts:

1. `gen_ai.model.request` — model, token counts, and response ID.
2. `toyworld.route.decision` — query, chosen answer, and road path.
3. `gen_ai.evaluation.result` — Gradebook score, source, cost, and reason.
4. `toyworld.reality.outcome` — only when a deferred outcome exists.

Projected span and log IDs are stable hashes scoped to the response ID. They
are explicitly marked `source = replay` and must never be used to construct an
exact SigNoz trace URL.

Replay logs are concise structured statements derived from recorded facts, for
example:

- decision requested for `route_choice`;
- model returned candidate `B`;
- math grade resolved `incorrect`;
- reality outcome arrived `on_time=false`.

The inspector labels the entire projection `REPLAY EVIDENCE`.

## Viewer Experience

The map remains the primary surface. Selecting an agent dot updates the
existing right panel rather than opening a second workspace.

### Global connection state

The header shows exactly one state:

- `SIGNOZ CONNECTED · 180/180`
- `SIGNOZ PARTIAL · 142/180`
- `REPLAY MODE · SIGNOZ OFFLINE`

Coverage counts only agents whose observability mode is `signoz` and whose
trace ID and evaluation span ID pass schema validation.

### Inspector tabs

**Details**

- agent and response ID;
- model and decision type;
- start, destination, and chosen path;
- selected and correct answer;
- correctness and grade source;
- input/output tokens and cost;
- service name, trace ID, and evaluation span ID;
- SigNoz or replay evidence badge.

**Trace**

- compact vertical waterfall ordered by start time;
- duration and status for each span;
- parent/child indentation;
- a separate linked-span treatment for deferred reality grades;
- selectable span rows;
- selected span attributes and links.

**Logs**

- timestamp, severity, body, service, and span association;
- severity styling;
- filter for all, warnings/errors, and the selected span;
- explicit empty state when SigNoz returned no correlated logs.

### Navigation

Actions appear above the tabs:

- `Open trace in SigNoz`;
- `Open logs in SigNoz`;
- `Open Gradebook dashboard`;
- `Copy trace ID`;
- `Copy response ID`.

Exact trace and log actions are enabled only for `mode = signoz`.

When exact trace identity is unavailable, the trace action becomes
`Find by response ID in SigNoz` and opens Trace Explorer with a filter on
`gen_ai.response.id`.

All URLs are produced by one URL builder. It accepts only:

- a configured `http` or `https` SigNoz origin;
- validated hexadecimal trace/span IDs;
- percent-encoded filter values;
- a configured dashboard path or identifier.

No raw server-returned URL is rendered directly.

## Configuration

Browser-safe configuration is served as static JSON:

```json
{
  "signoz_origin": "http://localhost:8080",
  "dashboard_path": null,
  "service_names": ["toy-world", "toy-world-outcomes"]
}
```

This file contains public navigation configuration only. It contains no API
key.

The synchronizer receives secrets exclusively through its environment.

## Error Handling

- Invalid observability data fails `parseRaceData` with an actionable path.
- A missing sidecar falls back to replay mode.
- An unreachable SigNoz instance causes the synchronization command to exit
  non-zero without replacing the last valid sidecar.
- Partial correlation writes a valid sidecar and prints unmatched response
  IDs plus coverage.
- Malformed SigNoz navigation configuration disables external actions while
  leaving the inspector usable.
- Popup blocking does not lose the link; actions remain normal anchors that
  users may open or copy.
- The UI never displays raw API errors containing request headers.

## Testing

### Python

- Replay projection contains the expected span sequence.
- Projection IDs are deterministic and remain labelled `replay`.
- Sidecar merge uses `gen_ai.response.id`.
- Duplicate or contradictory correlations fail.
- Missing entries produce partial coverage.
- A failed synchronization does not overwrite a valid sidecar.
- Serialized sidecar and run output contain no API key.

### TypeScript

- Schema parsing accepts valid SigNoz and replay envelopes.
- Nanosecond timestamps remain strings.
- Unsafe origins and malformed identifiers are rejected.
- Trace, logs, dashboard, and response-filter URLs are encoded safely.
- Connection coverage returns connected, partial, and offline states.
- Inspector tabs render correct live/replay badges and empty states.
- Exact trace actions are unavailable for replay projections.

### End-to-end browser verification

1. Start in replay mode and verify all 180 agents remain usable.
2. Select an agent and inspect Details, Trace, and Logs.
3. Verify replay evidence is labelled and exact-trace navigation is disabled.
4. Load a fixture sidecar with real trace identity.
5. Verify the header reports partial or full SigNoz coverage.
6. Select a correlated agent and verify exact trace/log/dashboard URLs.
7. Confirm the map replay, cameras, route coloring, and wave counts are
   unaffected.

## Operational Workflow

Offline:

```powershell
python viewer/export.py
npm.cmd --prefix viewer run dev
```

SigNoz-connected:

```powershell
$env:SIGNOZ_URL = "http://localhost:8080"
python viewer/sync_signoz.py --lookback-minutes 30
python viewer/export.py
npm.cmd --prefix viewer run dev
```

`SIGNOZ_API_KEY` must already be present in the environment. The implementation
will also accept explicit RFC 3339 `--from` and `--to` timestamps and document
the SigNoz API compatibility verified against the Foundry-pinned deployment.

## Delivery Boundary

This branch is stacked on PR #91. Its eventual PR targets
`codex/race-view-pune` until #91 merges; after that it can be retargeted to
`main`.

The work is complete when:

- offline mode remains deterministic;
- synchronized agents expose real trace and log evidence;
- SigNoz coverage is explicit;
- external navigation is safe and correct;
- no secret reaches browser assets;
- all Python, TypeScript, build, and browser checks pass.
