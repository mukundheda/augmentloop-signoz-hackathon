# Gradebook

[![CI](https://github.com/mukundheda/augmentloop-signoz-hackathon/actions/workflows/ci.yml/badge.svg)](https://github.com/mukundheda/augmentloop-signoz-hackathon/actions/workflows/ci.yml)

"Our AI is doing well" is usually an assertion. Gradebook is a small OpenTelemetry layer that makes it a measurement: every AI decision is recorded as a standard `gen_ai.evaluation.result` event, stamped with where its grade's authority came from - a deterministic checker (`math`), a real-world outcome (`reality`), or another model's opinion (`ai_judge`). Only the first two ever enter the headline number, **cost per correct decision**, which is what the SigNoz dashboards show. Agents propose, humans decide: the agent can propose moving a decision type to a cheaper model, but a human approves the diff and nothing applies itself.

![Grade provenance strip: 240 glyphs, one per grade, covering the 180 decisions in the committed run; blue for math grades and amber for reality grades, wrong decisions carrying a red foot along the baseline, with a legend reading 180 math, 60 reality and 0 ai_judge](docs/visuals/genome-strip.png)

*Every grade in the committed run, one glyph, in the order it arrived: 240 grades over 180 decisions, because each of the 60 `route_choice` decisions is graded twice - once by the checker, once later by the outcome. Hue is where that grade's authority came from; the red feet along the baseline are the wrong decisions. **180 `math`, 60 `reality`, 0 `ai_judge`.** The zero is the point: a model's opinion never silently enters the number. Two more renders over the same run are in [`docs/visuals/`](docs/visuals/) - static files, no server, no API key.*

## What counts as proof

| Grade source | Where the verdict comes from | Counts in the headline number? |
| --- | --- | --- |
| `math` | a checker computes the provably-correct answer | **yes**, this is the headline |
| `reality` | the real world proved it, usually later | **provable, but adjacent**: its own panels, never summed into the headline |
| `ai_judge` | another model scored it - an opinion | **no**, labeled secondary view only |

Every evaluation event carries `augmentloop.grade.source`, so that filter lives in the query rather than in this paragraph ([ADR 0001](docs/adr/0001-machine-checked-grades-only-in-the-headline-metric.md)).

Reality sits beside the headline rather than inside it for a structural reason, not a preference. A `route_choice` decision is graded twice, once by the checker and once later by the outcome, and the metrics deliberately carry no per-decision id because that would be unbounded cardinality. So nothing downstream can dedupe the pair, and summing both sources counts those decisions twice: it gives $0.002133 against the $0.002973 we publish, on a denominator of 177 that is 127 math-correct plus 50 reality-correct. That is the same double count behind a flattering figure this project already retracted once. Reality is not the lesser source, it is the only one that can overturn a checker and it does so 15 times in this run, which is exactly why it gets its own panels instead of being averaged into a total it would distort.

## How it fits together

```
            toy-world  (the demo substrate, 20 weighted junctions)
   +--------------------------------------------------------------+
   |  an AI driver decides: route_choice / eta_estimate / next_hop |
   |  the world already computed the right answer from the graph   |
   +---------------------------------+----------------------------+
                                     |  record_decision(...)
                                     v
   +--------------------------------------------------------------+
   |  gradebook   (reference-library; only dep: opentelemetry-api) |
   |    event      gen_ai.evaluation.result + augmentloop.grade.*  |
   |    counter    gradebook.decisions.graded                      |
   |    histogram  gradebook.decision.cost.usd                     |
   |    logs       3 failure classes, trace/span stamped           |
   +--------+--------------------------------------+--------------+
            |  service: toy-world                  |  service: toy-world-outcomes
            |  math grade, at decision time        |  reality grade, later,
            |                                      |  span-linked back to the
            |          OTLP / http  :4318          |  decision it overturns
            v                                      v
   +--------------------------------------------------------------+
   |  SigNoz          cast by Foundry from casting.yaml (11 lines) |
   |  traces . metrics . logs . 2 dashboards . 5 alert rules       |
   +---------------------------------+----------------------------+
                                     |  MCP  :8000
                                     v
   +--------------------------------------------------------------+
   |  agent reads 28 tools, proposes a reroute in routing.json     |
   |  human approves the diff. 13 write tools gated to `ask`.      |
   +--------------------------------------------------------------+
```

## Run it with no API key

```bash
pip install -e reference-library -e toy-world
python -m toyworld
```

The demo is a toy traffic world: AI drivers pick a route, estimate an arrival time, and choose a next hop, and the world already knows the right answer to each, so every decision is machine-gradeable. It is a demonstration of the mechanism, not production scale.

Both grade sources in this run are computed by the world itself: the `reality` verdict is a looser on-time check applied after the fact, not an outside event. What is real is the mechanism - the verdict arrives late, from a separate service and a separate trace, span-linked back to the decision it judges, and it overturns the math grade on 15 of 60.

Replay mode is the default. It replays a committed recording deterministically - no API keys, no model calls, same numbers on every machine - and fills the SigNoz dashboards from a judge's own laptop once SigNoz is up ([cold-machine walkthrough](docs/judge-run.md)). Live mode (real models, `[live]` extra, one OpenRouter key) is opt-in; nothing about the proof depends on it.

## The finding: right-size per decision type, not per model

From a live OpenRouter run captured 2026-07-25 and committed as the replay recording, priced from the shared pricing table:

| Model | `eta_estimate` | `next_hop` | `route_choice` | Correct | Cost |
| --- | --- | --- | --- | --- | --- |
| `anthropic/claude-sonnet-4.6` | 20/20 | 19/20 | 14/20 | 53/60 | $0.278031 |
| `anthropic/claude-haiku-4.5` | 17/20 | 16/20 | 9/20 | 42/60 | $0.096187 |
| `google/gemini-2.5-flash-lite` | **0/20** | **20/20** | 12/20 | 32/60 | $0.003335 |

Read the gemini row. On `next_hop` it is the best model in the run - 20/20, ahead of sonnet's 19/20 - for $0.001101 against sonnet's $0.031380 on that decision type, and 1/83rd of sonnet's cost across the run as a whole. On `eta_estimate` it is unusable: 0/20. The same model, in the same run, is the right choice for one decision type and the wrong choice for another. That is why routing here keys on decision type rather than on the program ([docs/right-sizing-loop.md](docs/right-sizing-loop.md)).

Across all 180 decisions: 127 correct, $0.377553 spent, **$0.002973 per correct decision**.

20 decisions per model per type is a small sample and this is one run, so read the per-type split as a signal worth routing on, not a settled ranking of these three models. `python -m toyworld` prints these same numbers, so the dashboards can be checked against ground truth.

## See it move

Three renders over the same committed run, all static files in [`docs/visuals/`](docs/visuals/), no server and no API key:

| | |
| --- | --- |
| [Genome strip](docs/visuals/genome-strip.html) | every grade in arrival order, coloured by where its authority came from (the image at the top of this README) |
| [Span link](docs/visuals/span-link.html) | one decision and the reality grade that arrives later on a separate trace and links back to it |
| [Regret ledger](docs/visuals/regret-ledger.html) | every decision as an open position that closes when the outcome lands. 50 close green, 10 close red, and `OVERTURNED` fires 15 times, each one a model that took the slower route and still arrived inside tolerance. That case is exactly why two grade sources exist rather than one |

And the whole run as motion: [`viewer/`](viewer/README.md) replays all 180 decisions as agents driving locally bundled OpenStreetMap roads through central Pune. Model colours stay visible in transit, math-correct routes resolve green and wrong ones red, the optimal alternative trails as a yellow ghost, and the deferred reality outcomes pulse their linked route after the last wave. Overview, top-down, street and follow cameras.

```bash
cd viewer && python export.py && npm install && npm run dev
```

## How it is built

- **No eval framework.** The library's only runtime dependency is `opentelemetry-api`.
- **Integration is one wrapper call.** `record_decision(...)` around a decision you already make; nothing else in the calling code changes.
- **The emitted telemetry is the contract, not the function signatures.** The library records the standard OpenTelemetry `gen_ai.evaluation.result` event; anything that reads that event works, whatever we do to our own API.
- **The tests assert literal frozen attribute names** - `"gen_ai.evaluation.score.value"`, not the library's own constants - so renaming an attribute cannot silently pass.
- **The approval gate is configuration, not good intentions.** A reroute is a diff in `toy-world/routing.json`; that file and every SigNoz MCP write tool sit in the `ask` list in `.claude/settings.json`, so the agent cannot apply its own proposal.

## Reproducibility

SigNoz is deployed via [Foundry](https://github.com/SigNoz/foundry). The deployment is fully declared by `casting.yaml`, and `casting.yaml.lock` records the resolved deployment spec Foundry produced from it, as required by the hackathon rules:

```bash
foundryctl cast -f casting.yaml
```

The lock pins ClickHouse and ClickHouse Keeper at `25.12.5`. The three SigNoz images resolve to `latest`, so that tag is the one thing `foundryctl cast` cannot reproduce for you a week from now. For anyone who wants the exact build this entry was developed, demoed and measured against:

| Image | Tag at cast time | Digest |
| --- | --- | --- |
| `signoz/signoz` | `v0.133.0` | `sha256:588a8ea3deeab1a6a4cb42261607457c36eee6ffbb510184880f1f826be4b646` |
| `signoz/signoz-otel-collector` | `v0.144.6` | `sha256:7e4e539a73f1f88fbc1cd7e659ab3950908e83ce1f2a37a297452f910d072174` |
| `signoz/signoz-mcp-server` | `main-2a64f20` | `sha256:da4fb0379d603a492fdbc0f384854f7d412a4c43347df2e086d17fc16770dd00` |

The MCP server molding is enabled; after casting, mint an API key in the SigNoz UI (Settings -> API Keys) and point an MCP client at `http://localhost:8000/mcp` with a `SIGNOZ-API-KEY` header.

A full cold-machine walkthrough - install, cast, create the admin account, run the replay, import the dashboards and alert rules - is in [docs/judge-run.md](docs/judge-run.md), executed end to end on a clean Windows 11 machine. Creating the admin account is a required step, not a login formality: SigNoz has no organization until it exists, and the OTLP endpoint refuses connections until it does, so a replay run before that step exports nothing. Two dashboards, five alert rules spanning all three of SigNoz's rule types (threshold, anomaly, and log-based), and the saved health view are committed as JSON in [`dashboards/`](dashboards/). Two of those rules are documented as dormant on a cold stack rather than quietly shipped: the anomaly rule cannot fire without seasonal history, and a firing rule reaches the dispatcher but dies at the last hop because the stack runs no SMTP. Both are measured facts written into [docs/judge-run.md](docs/judge-run.md), not predictions.

## Two things we found in SigNoz along the way

Neither is a complaint. Both are places where our telemetry is correct and SigNoz's current UI cannot yet show it, and we would rather write them down than quietly design around them.

**Exemplars are recorded by the SDK and dropped before ClickHouse.** We deliberately record both metric instruments while the evaluation event's span is current, so OpenTelemetry's default `TraceBasedExemplarFilter` attaches the originating trace and span id to every data point. A spike on a cost chart should then be one click from the decision that caused it. It is not, and we chased it down four independent ways before accepting it: the live schema has no exemplar column anywhere under `signoz_metrics` or `signoz_meter`; none of the three metrics exporters in the collector config handle exemplars; the `signozclickhousemetrics` exporter's own Go source never calls `.Exemplars()` on an incoming datapoint, so the value is dropped rather than filtered; and SigNoz maintainers confirm it in [discussions/1795](https://github.com/SigNoz/signoz/discussions/1795), pointing at the "View Traces" pivot as the workaround. We kept emitting the exemplar anyway, because it costs nothing and a future version may start reading it, and we do not claim a literal exemplar click-through anywhere in our copy. Full write-up in [docs/conventions.md](docs/conventions.md) section 10.1.

**The service map cannot draw a span link.** SigNoz's dependency graph is built from in-trace parent/child spans, so the relationship this project is actually about, a reality grade landing later on its own trace and pointing back at the decision it overturns, is invisible there by construction. That is why the [span-link visual](docs/visuals/span-link.html) exists as a static render rather than as a screenshot of the service map.

## AI assistance disclosure

Per the hackathon rules, we disclose AI assistant use: this project is built with heavy use of Claude Code (Anthropic) and Gemini-based tooling across planning, implementation, testing, and documentation. All AI-generated work is reviewed by a team member before merging; the commit history is the audit trail. The agent workflow conventions the team follows live in `CLAUDE.md` and `.claude/skills/`.

## Team and how we work

Team AugmentLoop's entry for the [Agents of SigNoz](https://wemakedevs.org/hackathons/signoz) hackathon (WeMakeDevs x SigNoz, July 20-26 2026), Track 01: AI & Agent Observability.

- Mukund Heda ([@mukundheda](https://github.com/mukundheda)) - lead, integration
- Vedant - core engine
- Rutik ([@Rutik332](https://github.com/Rutik332)) - UI
- Anish - SigNoz configuration, content

Work flows issue-first: ideas are grilled into a spec, the spec is broken into vertical-slice tickets with explicit blocking edges (GitHub issue dependencies), and each ticket is implemented in an isolated agent session against pre-agreed test seams, then reviewed for both coding standards and spec fidelity before merge. The skills encoding this pipeline are committed in `.claude/skills/` (adapted from [mattpocock/skills](https://github.com/mattpocock/skills), MIT). `CONTEXT.md` is the glossary.
