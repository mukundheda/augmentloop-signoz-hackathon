# Vendor and data attribution

## GoogleCloudPlatform/race-condition

- Source: https://github.com/GoogleCloudPlatform/race-condition
- License: Apache-2.0
- Use: visual and interaction reference
- Copied files: none

The implementation uses original Three.js scene, path, animation, label, HUD,
and replay code. It deliberately does not vendor the upstream Angular
application, gateway, WebSocket protocol, or framework-independent primitives.

## OpenStreetMap

- Attribution: © OpenStreetMap contributors
- Copyright and license: https://www.openstreetmap.org/copyright
- Corridor: Shivajinagar–Deccan–Swargate, Pune
- Bounds: 73.835,18.480,73.865,18.535
- Prepared: 2026-07-25

`public/data/pune-map.geojson` is a reduced visualization extract containing
real road ways and up to 1,800 building footprints from the fixed bounds.
`public/data/toyworld-roads.json` records the deterministic assignment of
`J1`–`J20` to OSM road intersections and a Dijkstra-computed road polyline for
every directed toy-world edge.

The raw Overpass response is excluded from Git; the reduced committed assets
are sufficient at runtime and for regenerating `run.json`.

The route alternatives and travel-time values are synthetic toy-world data.
They are not Pune routing or traffic claims.

## SigNoz

- Use: optional, user-configured synchronization of trace and log evidence;
  no SigNoz source code, telemetry data, API key, or client library is
  vendored.
- API workflow: the Python-only `sync_signoz.py` client uses `SIGNOZ_URL` and
  `SIGNOZ_API_KEY` to query the Query Builder v5 `POST
  https://{URL}/api/v5/query_range` endpoint, then writes a sanitized local
  sidecar for the next export.
- Official trace API: https://signoz.io/docs/apm-and-distributed-tracing/traces-api/
- Official logs API: https://signoz.io/docs/logs-management/logs-api/overview/
- Query Builder v5 reference: https://signoz.io/docs/userguide/query-builder-v5/

The public viewer receives navigation configuration only, never the API key.
Its external origins are limited to credential-free `http`/`https` URLs and
dashboard paths must be relative. SigNoz connectivity has not been verified in
this repository; absent or unmatched live data is represented as deterministic
schema-v3 replay evidence instead.
