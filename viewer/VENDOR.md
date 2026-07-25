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

`public/data/pune-context.geojson` is a compact visualization context using
OpenStreetMap place and road geography. Runtime rendering is entirely local and
does not call an external map service.

The route alternatives and travel-time values are synthetic toy-world data.
They are not Pune routing or traffic claims.

