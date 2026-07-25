# Gradebook Pune Toy-World View

A standalone Three.js replay of the current 20-junction toy world. Every one
of the committed recording's 180 decisions becomes an animated agent moving
along locally bundled OpenStreetMap roads in central Pune.

The viewer supports all three decision types:

- `route_choice`: the selected full candidate path
- `eta_estimate`: the shortest journey whose time the model estimated
- `next_hop`: the chosen outgoing road segment

Agents replay in waves of 24. Model colors remain visible while math-correct
routes resolve green, wrong routes red, and the optimal alternative appears as
a yellow ghost. Deferred reality outcomes pulse their linked route after the
last wave.

## Observability evidence

The replay is deterministic and works entirely offline. `export.py` emits
schema-v3 `run.json` evidence for every decision, including a stable replay
span projection and its linked reality-grade outcome where present. This is
explicitly replay evidence, not a claim that a live trace was fetched. With no
synchronized sidecar, the HUD reports `REPLAY MODE · SIGNOZ OFFLINE` and every
agent remains inspectable.

Select an agent to use the **Details**, **Trace**, and **Logs** inspector tabs:

- **Details** identifies the response, decision, model, grade, and cost, and
  offers a response-ID search hint when an exact live trace is unavailable.
- **Trace** renders the projected or synchronized span waterfall, linked
  reality-grade spans, and copy/open actions when a validated trace ID exists.
- **Logs** displays trace-correlated entries with All, Warnings & errors, and
  Selected span filters.

Coverage is deliberately conservative: `SIGNOZ CONNECTED` means every decision
has validated synchronized evidence; `SIGNOZ PARTIAL` means only some do; and
the offline state means none do. A synchronized mode is not displayed merely
because an origin is configured.

### Optional SigNoz synchronization

Live synchronization is an optional, Python-only preparation step. Set
`SIGNOZ_URL` and `SIGNOZ_API_KEY` in the environment (the browser bundle never
receives the API key), then run:

```powershell
python viewer/sync_signoz.py --lookback-minutes 30
python viewer/export.py
```

The sync queries and correlates SigNoz evidence by the committed response IDs,
sanitizes it, and atomically writes `.scratch/viewer-signoz-observability.json`.
The following export merges only validated matches; unmatched decisions retain
their deterministic replay evidence. Do not commit the sidecar or credentials.

`public/data/signoz-config.json` contains navigation-only settings. The viewer
accepts only credential-free `http`/`https` origins and relative dashboard
paths; invalid configuration disables external links. It opens dashboard,
trace, log, or response-ID-search destinations in a new tab with `noreferrer`.
This repository has not verified connectivity to any live SigNoz instance.

## Run

```powershell
python export.py
npm install
npm run dev
```

Open the URL printed by Vite. No API key or map request is required after
dependencies have been installed. Use the camera control for overview,
top-down, street, and selected-agent follow views.

## Verify

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
npm test -- --run
npm run build
```

The committed `pune-map.geojson` and `toyworld-roads.json` are sufficient for
re-exporting the run on a clean clone. The raw Overpass response is intentionally
not committed.

The viewer is optional and does not change the Foundry cast or judge path.
