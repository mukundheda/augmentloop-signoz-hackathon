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
Replayed replay-v2.jsonl -> http://localhost:4318
decisions=420  correct=268  reality_outcomes=140  total_cost=$0.403804
cost per correct decision: $0.001507
per model:
  mistralai/mistral-small-24b-instruct-2501: 40/60 correct, $0.003264
  google/gemini-2.5-flash-lite: 32/60 correct, $0.003335
  meta-llama/llama-3.3-70b-instruct: 28/60 correct, $0.004057
  openai/gpt-4o-mini: 33/60 correct, $0.004606
  deepseek/deepseek-chat: 40/60 correct, $0.010634
  anthropic/claude-haiku-4.5: 43/60 correct, $0.096187
  anthropic/claude-sonnet-4.6: 52/60 correct, $0.281721
per model x decision type:
  ... 21 rows, one per model and decision type. The three that matter most:
  deepseek/deepseek-chat / next_hop: 20/20 correct, $0.002012
  openai/gpt-4o-mini / next_hop: 20/20 correct, $0.001520
  anthropic/claude-sonnet-4.6 / next_hop: 19/20 correct, $0.031380
```

(The per model x decision type section is elided above only for length; the
command prints all 21 rows, plus a trailing "Open SigNoz -> Traces" hint.)

Read those last three lines against each other. Two of the cheapest models in
the roster each score a perfect 20 on `next_hop` and beat the most expensive
one, which drops a point, while costing roughly a twentieth as much on that
decision type. Then look at `eta_estimate`, where `gpt-4o-mini`,
`llama-3.3-70b-instruct` and `gemini-2.5-flash-lite` all score 0 out of 20 and
`claude-sonnet-4.6` scores 19. No ranking of these seven models survives both
columns, which is the entire argument for routing per decision type.

In SigNoz you now have services `toy-world` and `toy-world-outcomes`, one trace
per model, and 560 `gen_ai.evaluation.result` events - 420 math grades plus the
140 late `journey.on_time` reality grades that span-link back to the
`route_choice` decisions they judge. Of those 140, 43 overturn the math grade,
every one in the same direction: the checker called the route wrong because it
was not the shortest, and the journey still arrived inside tolerance. The
replay is deterministic; re-running it just adds another identical batch.

## 5. Import the Gradebook dashboard

SigNoz UI -> Dashboards -> New Dashboard -> **Import JSON** -> upload
`dashboards/gradebook-cost-per-correct-decision.json` -> Import and Next.

Eleven panels across five panel types (timeseries, bar, value, table and list)
light up from the replay batch on the default "Last 30 minutes" range. The
AI-Estimated Quality panel reads 0 - correct, the replay recording contains no
`ai_judge` grades by design. The panel worth opening first is the
**Right-Sizing Grid**, which is the finding this project exists to show: every
decision type crossed with every model, with the three cheapest models sitting
at 20 out of 20 on `next_hop` above `claude-sonnet-4.6`'s 19.

Two deliberate absences, so neither reads as an oversight. There is no
single-number "value" panel for the headline, and no histogram panel despite
this build emitting a real OpenTelemetry histogram instrument for cost. Both
come from the same limitation, found by looking at the rendered dashboard
rather than at query responses: **this SigNoz version does not evaluate builder
formulas on the scalar query path** that a value panel and a table column use.
The headline's `(A/B)*1000` returns 1.507 as a timeseries and empty as a
scalar, and with `nullZeroValues` set to zero a value panel renders that
emptiness as a confident `0`. The headline is therefore a timeseries, the
table shows raw counts instead of ratio columns, and the bucket panel was cut
rather than shipped reading "No Data".

**Keep the time range on your own replay run.** The reconciliation panels are
pinned to the demo services (`toy-world` and `toy-world-outcomes`), because
Gradebook is a portable layer and any stack running a second emitter through
the same contract would otherwise blend it into the headline. The
**Services Emitting Through the Contract** panel shows that full set on
purpose. Scoping fixes the service axis but not the time axis: a dashboard
aggregates every run inside the selected window, so if you run the replay more
than once, widen or narrow the range deliberately. On a range covering exactly
one replay, the headline reconciles with what `python -m toyworld` printed:
268 correct, and $0.403804 to within a rounding residue in the fifth decimal
that comes from histogram sum storage.

## 6. Import the alert rules

Two one-time setup steps, then four API calls.

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

**Use `/api/v2/rules`, not `/api/v1/rules`.** The v1 endpoint accepts the
request and returns success, but the rule then never evaluates (SigNoz issue
#10823) - confirmed the hard way in this project. Never trust the 200; poll
the rule's `state` (via `GET /api/v2/rules/{id}`) across two evaluation
cycles before believing it's wired up.

From the repo root:

```powershell
curl.exe -s -X POST http://localhost:8080/api/v2/rules -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/alert-spend-spike.json"
curl.exe -s -X POST http://localhost:8080/api/v2/rules -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/alert-grade-quality-drop.json"
curl.exe -s -X POST http://localhost:8080/api/v2/rules -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/alert-grade-quality-anomaly.json"
curl.exe -s -X POST http://localhost:8080/api/v2/rules -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/alert-grading-pipeline-silent.json"
curl.exe -s -X POST http://localhost:8080/api/v2/rules -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/alert-budget-guard-trips.json"
```

Five rules ship for this build, spanning all three of SigNoz's rule types
(threshold, anomaly, and log-based): `alert-grade-quality-drop.json` (static 50%
floor, kept intentionally alongside the anomaly rule - see its description
for why), `alert-spend-spike.json`, `alert-grade-quality-anomaly.json`
(seasonal anomaly on correct-decision volume, #49 - the primary
grade-quality detector), `alert-grading-pipeline-silent.json` (fires when no
decisions of any kind have been graded for 10 minutes, #50), and
`alert-budget-guard-trips.json` (log-based: fires when the budget guard
trips 3 or more times within a rolling 5-minute window - a discrete
failure-event stream, which is what logs and log-based alerts express
cleanly and a metrics counter cannot). Every rule's `description` field
carries the reasoning behind its design choices and any deployment-specific
gotchas discovered while building it - read it before changing the query or
thresholds.

**Verified live on 2026-07-25.** Both new rules were confirmed evaluating on
the running stack, not merely accepted by the API: the ruler logs an `Eval`
cycle for each rule id every 60 seconds, and `Gradebook Grading Pipeline
Silent` has recorded real state transitions in
`signoz_analytics.distributed_rule_state_history_v0` (it sits in `firing`
whenever nothing has been graded for 10 minutes, which is its job).

One honest caveat on the anomaly rule. It evaluates every cycle and issues
all five seasonal queries, but on a stack with no seasonal history it cannot
fire at all. With every past season empty the ruler computes
`anomaly_std_dev: 0`, and a z score over a zero standard deviation comes back
as `-Inf` for every point, so `alert.count` is always 0. This is not a
misconfiguration and it is not a rule that will start working after a few
more hours; it needs genuine multi day history before any score is finite.
That is the concrete reason the static 50% floor in
`alert-grade-quality-drop.json` stays wired up alongside it rather than being
replaced by it.

## 7. Open the judge-run saved views

`dashboards/view-judge-run-health.json` is a saved Explorer view (Metrics ->
graph of `gradebook.decisions.graded`, grouped by `augmentloop.grade.source`
and `gen_ai.evaluation.score.label`) that answers "is this run healthy?" at a
glance - the live version of this doc's troubleshooting table. Create it via
the API (there is no import-JSON button for saved views in the UI):

```powershell
curl.exe -s -X POST http://localhost:8080/api/v1/explorer/views -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/view-judge-run-health.json"
curl.exe -s -X POST http://localhost:8080/api/v1/explorer/views -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/view-decision-traces.json"
curl.exe -s -X POST http://localhost:8080/api/v1/explorer/views -H "SIGNOZ-API-KEY: <your-key>" -H "Content-Type: application/json" --data-binary "@dashboards/view-failure-events.json"
```

That is one saved view per signal. Besides the metrics view described below,
**Traces Explorer -> Saved Views -> "Judge Run: Decision Traces and Their Late
Grades"** scopes to `toy-world` and `toy-world-outcomes` together, which is the
only place the deferred reality grade is visible: open any
`toy-world-outcomes` span and follow its link back to the `route_choice`
decision it judges, recorded earlier and on a separate trace. **Logs Explorer
-> Saved Views -> "Judge Run: Failure Events"** filters on the
`augmentloop.failure.class` attribute rather than message text. An empty list
there is the expected result on a keyless replay: those are discrete failure
events, not a gauge, and a replay trips none of them.

Then in SigNoz: Metrics Explorer -> Saved Views -> "Judge Run Health:
Decisions Graded". Set the range to **Last 30 minutes** right after running
the replay (step 4). Bars broken down by grade source and correct/incorrect
label = the pipeline is alive and grading; an empty chart means the same
root causes as "Dashboard panels empty" below. Keep the range well under a
day - `increase()`/`rate()` on this metric silently returns no data on
windows of roughly 6 hours or more in this deployment (verified 2026-07-25),
regardless of grouping.

All of the above return `{"status":"success",...}`; the rules appear under
Alerts and the view appears under Metrics Explorer -> Saved Views.

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
| The headline number does not match what `python -m toyworld` printed | Almost always the time range: a dashboard aggregates every run in the window, so two replays show roughly double the decisions. Cross-service blending is already handled, since the reconciliation panels are pinned to `toy-world` and `toy-world-outcomes` | Narrow the range to a single replay. Expect an exact match on decision counts and a residue in the fifth decimal on cost, which is histogram sum storage precision, not a grading disagreement |
| On first load, panels look blended across decision types, models or grade sources | The three dashboard variables are DYNAMIC and attribute-backed, and this SigNoz version's saved dashboard schema has no field to persist a default selection (confirmed by round-tripping the live PUT/GET: the API accepts and echoes the variable back with no default or selectedValue key). With the ALL option on, an unpicked variable matches everything | Pick values from the `decision_type`, `model` and `grade_source` dropdowns at the top of the dashboard. This is a UI limitation, not a query defect, and each affected panel's description says so |
| `Gradebook Meta: Grading Our Own Build Sessions` is empty and stays empty | Expected. That dashboard filters `augmentloop.decision.type = 'build_session'`, which is populated only from this team's own git history via `dashboards/scripts/record_build_fleet_sessions.py`. It is a third proof surface, not part of the judge path, and nothing in this walkthrough imports it | Nothing to fix. Ignore it, or read the script's module docstring for what it records and why most rows carry no cost |
| A rule POSTs `{"status":"success"}` but never appears to fire, ever | Posted to `/api/v1/rules` instead of `/api/v2/rules` (SigNoz issue #10823) | Recreate via `/api/v2/rules`; always poll `GET /api/v2/rules/{id}` across two evaluation cycles before trusting a rule is live |
| A metrics query/alert/view on `gradebook.decisions.graded` (or similar) returns rows-scanned > 0 but a null/empty result | `timeAggregation: increase` or `rate` silently returns no data once the query window is roughly 6 hours or more, in this deployment | Keep `evalWindow` / Explorer time range short (well under a day); confirmed working up to ~3h in this project's testing, regardless of `groupBy` |
| An `alertOnAbsent`-only rule is rejected with `condition.thresholds: field is required` (or `condition.target`/`op`/`matchType` for the v1 shape) | This SigNoz version does not support absence as the sole condition on either schema version, despite what the platform's own docs/skills suggest | Add a structurally-inert threshold alongside `alertOnAbsent` (e.g. `op: below, target: 0` on a metric that can never go negative) so the schema validates while absence remains the only condition that can practically fire - see `dashboards/alert-grading-pipeline-silent.json`'s description |
| Both `Gradebook Grade Quality Drop` and `Gradebook Spend Spike` show `preferredChannels: null` via `GET /api/v2/rules` | Cosmetic, and narrower than it looks. Checked on 2026-07-25: the dispatcher still routes these rules to the `gradebook-alerts` receiver (its log lines carry `{__receiver__="gradebook-alerts"}:{ruleId="019f8d8e-..."}`), so a null `preferredChannels` does not mean the alert goes nowhere | Nothing to fix for routing. Set the field explicitly anyway if you want the UI to show it |
| A rule reaches `firing` but no notification ever arrives | The delivery hop, not the rule. On a default Foundry stack the `gradebook-alerts` email channel resolves to `dial tcp [::1]:25: connect: connection refused`, and alertmanager gives up after roughly 16 retries. The rule, the routing, and the dispatch are all working; there is no SMTP server to hand the mail to | Point the channel at a webhook rather than email (a Telegram or Slack webhook needs no local mail server), or run an SMTP relay on the host |
| `Gradebook Grade Quality Anomaly` never fires, on any input | Expected on a fresh or short lived stack, see the note in step 6. No seasonal history gives `anomaly_std_dev: 0`, every z score is `-Inf`, and `alert.count` stays 0 | Nothing to fix. Rely on the static floor rule until the deployment has multi day history |
