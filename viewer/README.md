# Gradebook Pune Toy-World View

A standalone Three.js replay of the current 20-junction toy world. Every one
of the committed recording's 420 decisions becomes an animated agent moving
along locally bundled OpenStreetMap roads in central Pune, one colour per
roster model.

The viewer supports all three decision types:

- `route_choice`: the selected full candidate path
- `eta_estimate`: the shortest journey whose time the model estimated
- `next_hop`: the chosen outgoing road segment

Agents replay in waves of 24, so the seven-model run is 18 waves and takes a
little over ninety seconds at 1x. Use the speed control to shorten it. Model
colors remain visible while math-correct routes resolve green, wrong routes
red, and the optimal alternative appears as a yellow ghost. Deferred reality
outcomes pulse their linked route after the last wave.

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
