# Gradebook

[![CI](https://github.com/mukundheda/augmentloop-signoz-hackathon/actions/workflows/ci.yml/badge.svg)](https://github.com/mukundheda/augmentloop-signoz-hackathon/actions/workflows/ci.yml)

"Our AI is doing well" is usually an assertion. Gradebook is a small OpenTelemetry layer that makes it a measurement: every AI decision is recorded as a standard `gen_ai.evaluation.result` event, stamped with where its grade's authority came from - a deterministic checker (`math`), a real-world outcome (`reality`), or another model's opinion (`ai_judge`). Only the first two ever enter the headline number, **cost per correct decision**, which is what the SigNoz dashboards show. Agents propose, humans decide: the agent can propose moving a decision type to a cheaper model, but a human approves the diff and nothing applies itself.

![Grade provenance strip: 240 glyphs, one per grade, covering the 180 decisions in the committed run; blue for math grades and amber for reality grades, wrong decisions carrying a red foot along the baseline, with a legend reading 180 math, 60 reality and 0 ai_judge](docs/visuals/genome-strip.png)

*Every grade in the committed run, one glyph, in the order it arrived: 240 grades over 180 decisions, because each of the 60 `route_choice` decisions is graded twice - once by the checker, once later by the outcome. Hue is where that grade's authority came from; the red feet along the baseline are the wrong decisions. **180 `math`, 60 `reality`, 0 `ai_judge`.** The zero is the point: a model's opinion never silently enters the number. Two more renders over the same run are in [`docs/visuals/`](docs/visuals/) - static files, no server, no API key.*

## What counts as proof

| Grade source | Where the verdict comes from | Counts in the headline number? |
| --- | --- | --- |
| `math` | a checker computes the provably-correct answer | **yes** |
| `reality` | the real world proved it, usually later | **yes** |
| `ai_judge` | another model scored it - an opinion | **no**, labeled secondary view only |

Every evaluation event carries `augmentloop.grade.source`, so that filter lives in the query rather than in this paragraph ([ADR 0001](docs/adr/0001-machine-checked-grades-only-in-the-headline-metric.md)).

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

## How it is built

- **No eval framework.** The library's only runtime dependency is `opentelemetry-api`.
- **Integration is one wrapper call.** `record_decision(...)` around a decision you already make; nothing else in the calling code changes.
- **The emitted telemetry is the contract, not the function signatures.** The library records the standard OpenTelemetry `gen_ai.evaluation.result` event; anything that reads that event works, whatever we do to our own API.
- **The tests assert literal frozen attribute names** - `"gen_ai.evaluation.score.value"`, not the library's own constants - so renaming an attribute cannot silently pass.
- **The approval gate is configuration, not good intentions.** A reroute is a diff in `toy-world/routing.json`; that file and every SigNoz MCP write tool sit in the `ask` list in `.claude/settings.json`, so the agent cannot apply its own proposal.

## Reproducibility

SigNoz is deployed via [Foundry](https://github.com/SigNoz/foundry). The deployment is fully declared by `casting.yaml` (with `casting.yaml.lock` pinning exact versions), as required by the hackathon rules:

```bash
foundryctl cast -f casting.yaml
```

The MCP server molding is enabled; after casting, mint an API key in the SigNoz UI (Settings -> API Keys) and point an MCP client at `http://localhost:8000/mcp` with a `SIGNOZ-API-KEY` header.

A full cold-machine walkthrough - install, cast, create the admin account, run the replay, import the dashboards and alert rules - is in [docs/judge-run.md](docs/judge-run.md), executed end to end on a clean Windows 11 machine. Creating the admin account is a required step, not a login formality: SigNoz has no organization until it exists, and the OTLP endpoint refuses connections until it does, so a replay run before that step exports nothing. Two dashboards, four alert rules, and the saved health view are committed as JSON in [`dashboards/`](dashboards/).

## AI assistance disclosure

Per the hackathon rules, we disclose AI assistant use: this project is built with heavy use of Claude Code (Anthropic) and Gemini-based tooling across planning, implementation, testing, and documentation. All AI-generated work is reviewed by a team member before merging; the commit history is the audit trail. The agent workflow conventions the team follows live in `CLAUDE.md` and `.claude/skills/`.

## Team and how we work

Team AugmentLoop's entry for the [Agents of SigNoz](https://wemakedevs.org/hackathons/signoz) hackathon (WeMakeDevs x SigNoz, July 20-26 2026), Track 01: AI & Agent Observability.

- Mukund Heda ([@mukundheda](https://github.com/mukundheda)) - lead, integration
- Vedant - core engine
- Rutik ([@Rutik332](https://github.com/Rutik332)) - UI
- Anish - SigNoz configuration, content

Work flows issue-first: ideas are grilled into a spec, the spec is broken into vertical-slice tickets with explicit blocking edges (GitHub issue dependencies), and each ticket is implemented in an isolated agent session against pre-agreed test seams, then reviewed for both coding standards and spec fidelity before merge. The skills encoding this pipeline are committed in `.claude/skills/` (adapted from [mattpocock/skills](https://github.com/mattpocock/skills), MIT). `CONTEXT.md` is the glossary.
