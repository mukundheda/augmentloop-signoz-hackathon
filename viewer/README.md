# Gradebook Pune Race View

A standalone Three.js replay of the toy world's four AI drivers. The route
choices, grades, costs, and late outcome links come from the committed
Gradebook replay; Pune supplies the visual setting.

## Run

```powershell
python export.py
npm install
npm run dev
```

Open the URL printed by Vite. No API key or network connection is required
after dependencies have been installed.

## Verify

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
npm test -- --run
npm run build
```

The viewer is optional and does not change the Foundry cast or judge path.
