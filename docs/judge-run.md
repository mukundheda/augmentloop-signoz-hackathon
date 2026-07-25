# Judge run: cold machine, zero API keys

The full path from an empty machine to lit-up Gradebook dashboards. Every step
below was executed on a clean Windows 11 machine (no prior SigNoz, no
containers, no `foundryctl`) on 2026-07-23; the commands are copy-paste. The
same flow works on macOS/Linux with the obvious shell substitutions - only
step 1 differs meaningfully.

Prerequisites: Docker Desktop running, Python 3.10+ (3.13 verified), ~10
minutes, ~2 GB of image pulls. No API keys of any kind.

## 1. Install foundryctl

**Windows** (PowerShell; `tar` is built into Windows 10/11):

```powershell
Invoke-WebRequest -Uri "https://github.com/SigNoz/foundry/releases/latest/download/foundry_windows_amd64.tar.gz" -OutFile foundry.tar.gz -UseBasicParsing
tar -xzf foundry.tar.gz
mkdir "$HOME\.local\bin" -Force
Move-Item foundry_windows_amd64\bin\foundryctl.exe "$HOME\.local\bin\"
& "$HOME\.local\bin\foundryctl.exe" version   # add $HOME\.local\bin to PATH to drop the prefix
```

There is no install script for Windows (the `curl | bash` one-liner is
Unix-only); the release tarball ships a native `foundryctl.exe` and works
without WSL. Verified with v0.2.16.

**macOS/Linux:**

```bash
curl -fsSL https://signoz.io/foundry.sh | bash
```

## 2. Cast the stack

From the repo root:

```powershell
foundryctl cast -f casting.yaml
```

Pulls images and starts 8 containers (SigNoz, ClickHouse, keeper, Postgres,
ingest collector, MCP server, plus two one-shot init jobs that exit 0 - that
is normal). Wait until `docker ps` shows the long-running containers healthy:

```powershell
docker ps --format "{{.Names}}\t{{.Status}}"
```

Casting writes a `pours/` directory (the materialized compose files,
gitignored) and may reformat `casting.yaml.lock` - see the troubleshooting
table for when that lock change should and should not be committed.

## 3. Create the admin account - REQUIRED before any telemetry flows

Open http://localhost:8080 and create the admin account (any local
email/password).

This is not just a login step. A fresh SigNoz has no organization until the
first account exists, the ingest collector cannot register itself without one
(`cannot create agent without orgId` in the logs), and **the OTLP endpoint on
port 4318 refuses connections until ~30-60 s after the account is created.**
If you run the replay first, every span export fails with "connection
aborted" and nothing reaches SigNoz.

Readiness probe - ready when it returns `{"partialSuccess":{}}`:

```powershell
curl.exe -s -X POST http://localhost:4318/v1/traces -H "Content-Type: application/json" -d "{}"
```

## 4. Run the toy-world replay (no API keys)

From the repo root:

```powershell
python -m venv .venv
.venv\Scripts\pip install -e reference-library -e toy-world
.venv\Scripts\python -m toyworld
```

(macOS/Linux: `.venv/bin/pip` / `.venv/bin/python`.) Expected output:

```
Replayed replay-v1.jsonl -> http://localhost:4318
decisions=12  correct=8  reality_outcomes=4  total_cost=$0.003735
cost per correct decision: $0.000467
per model:
  anthropic/claude-3.5-haiku: 4/6 correct, $0.001274
  anthropic/claude-sonnet-4: 3/3 correct, $0.002382
  google/gemini-2.0-flash: 1/3 correct, $0.000079
```

In SigNoz you now have services `toy-world` and `toy-world-outcomes`, journey
trace waterfalls, and 16 `gen_ai.evaluation.result` events. The replay is
deterministic; re-running it just adds another identical batch.

## 5. Import the Gradebook dashboard

SigNoz UI -> Dashboards -> New Dashboard -> **Import JSON** -> upload
`dashboards/gradebook-cost-per-correct-decision.json` -> Import and Next.

The panels (cost per correct by model, correct-rate by model, cost over time
by grade source) light up from the replay batch on the default "Last 30
minutes" range. The AI-Estimated Quality panel reads 0 - correct, the replay
recording contains no `ai_judge` grades by design.

## 6. Import the two alert rules

Two one-time setup steps, then two API calls:

1. **Notification channel** - the committed alert rules route to a channel
   named `gradebook-alerts`, and SigNoz rejects a rule whose channel does not
   exist (and rejects rules with no channel at all). Create it: Settings ->
   Notification Channels -> New channel -> name `gradebook-alerts`, type
   Webhook, any URL (e.g. `http://localhost:9/noop`) -> Save.
2. **API key** - Settings -> **Service Accounts** (this is the "API Keys"
   screen; newer SigNoz renamed it) -> New Service Account -> open it and
   assign the `signoz-editor` role under Roles -> Save Changes -> Keys tab ->
   Add Key. Copy the key: it is shown once. A service account with **no role
   gets 403 forbidden** on every API call.

Then, from the repo root:

```powershell
curl.exe -s -X POST http://localhost:8080/api/v1/rules -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/alert-spend-spike.json"
curl.exe -s -X POST http://localhost:8080/api/v1/rules -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/alert-grade-quality-drop.json"
```

Both return `{"status":"success",...}`; the rules appear under Alerts.

The same key and header also drive the MCP server at
`http://localhost:8000/mcp` (see the repo README).

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Replay prints `Transient error ... connection aborted` then `Failed to export` | OTLP not ready: admin account not created yet, or created moments ago | Do step 3, wait for the readiness probe, re-run the replay |
| Alert import fails `channels ... do not exist: [gradebook-alerts]` | Fresh stack has no notification channels | Step 6.1 |
| API calls return `403 forbidden` despite a valid key | Service account has no role | Assign `signoz-editor` in step 6.2 |
| `casting.yaml.lock` shows as modified in git after casting | `foundryctl` regenerates the lock; formatting differs across versions | Expected; do not commit unless you changed `casting.yaml` |
| Dashboard panels empty | Time range does not cover the replay batch | Set the dashboard range to include when step 4 ran |
