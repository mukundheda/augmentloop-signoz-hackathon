# AugmentLoop x Agents of SigNoz

[![CI](https://github.com/mukundheda/augmentloop-signoz-hackathon/actions/workflows/ci.yml/badge.svg)](https://github.com/mukundheda/augmentloop-signoz-hackathon/actions/workflows/ci.yml)

Team AugmentLoop's entry for the [Agents of SigNoz](https://wemakedevs.org/hackathons/signoz) hackathon (WeMakeDevs x SigNoz, July 20-26 2026), Track 01: AI & Agent Observability.

**Status:** Building **Gradebook** - a report-card layer for AI decisions, shown on SigNoz. See `CONTEXT.md` for the glossary and issue #3 for the full spec. This README gets a full rewrite before submission.

## Run it with no API key

```bash
pip install -e reference-library -e toy-world
python -m toyworld
```

Replay mode is the default. It replays a committed recording deterministically - no API keys, no model calls, same numbers on every machine - and fills the SigNoz dashboards from a judge's own laptop. Live mode (real models, `[live]` extra, one OpenRouter key) is opt-in; nothing about the proof depends on it.

## What counts as proof

| Grade source | Where the verdict comes from | Counts in the headline number? |
| --- | --- | --- |
| `math` | a checker computes the provably-correct answer | **yes** |
| `reality` | the real world proved it, usually later | **yes** |
| `ai_judge` | another model scored it - an opinion | **no**, labeled secondary view only |

Every evaluation event carries `augmentloop.grade.source`, so that filter lives in the query rather than in this paragraph ([ADR 0001](docs/adr/0001-machine-checked-grades-only-in-the-headline-metric.md)).

### Same three junctions, three models

From the committed replay recording, run 2026-07-25, priced from the shared pricing table:

| Model | Correct | Cost |
| --- | --- | --- |
| `anthropic/claude-sonnet-4` | 3/3 | $0.002382 |
| `anthropic/claude-3.5-haiku` | 4/6 | $0.001274 |
| `google/gemini-2.0-flash` | 1/3 | $0.000079 |

12 decisions, 8 correct, **$0.000467 per correct decision**. The cheapest model is also the worst one here - which is exactly why right-sizing is measured per decision type instead of assumed. `python -m toyworld` prints these same numbers, so the dashboards can be checked against ground truth.

## How it is built

- **No eval framework.** The library's only runtime dependency is `opentelemetry-api`.
- **Integration is one wrapper call.** `record_decision(...)` around a decision you already make; nothing else in the calling code changes.
- **The emitted telemetry is the contract, not the function signatures.** The library records the standard OpenTelemetry `gen_ai.evaluation.result` event; anything that reads that event works, whatever we do to our own API.
- **The tests assert literal frozen attribute names** - `"gen_ai.evaluation.score.value"`, not the library's own constants - so renaming an attribute cannot silently pass.

## Team

- Mukund Heda ([@mukundheda](https://github.com/mukundheda)) - lead, integration
- Vedant - core engine
- Rutik ([@Rutik332](https://github.com/Rutik332)) - UI
- Anish - SigNoz configuration, content

## Reproducibility

SigNoz is deployed via [Foundry](https://github.com/SigNoz/foundry). The deployment is fully declared by `casting.yaml` (with `casting.yaml.lock` pinning exact versions), as required by the hackathon rules:

```bash
foundryctl cast -f casting.yaml
```

The MCP server molding is enabled; after casting, mint an API key in the SigNoz UI (Settings -> API Keys) and point an MCP client at `http://localhost:8000/mcp` with a `SIGNOZ-API-KEY` header.

## AI assistance disclosure

Per the hackathon rules, we disclose AI assistant use: this project is built with heavy use of Claude Code (Anthropic) and Gemini-based tooling across planning, implementation, testing, and documentation. All AI-generated work is reviewed by a team member before merging; the commit history is the audit trail. The agent workflow conventions the team follows live in `CLAUDE.md` and `.claude/skills/`.

## How we work (for judges and the curious)

Work flows issue-first: ideas are grilled into a spec, the spec is broken into vertical-slice tickets with explicit blocking edges (GitHub issue dependencies), and each ticket is implemented in an isolated agent session against pre-agreed test seams, then reviewed for both coding standards and spec fidelity before merge. The skills encoding this pipeline are committed in `.claude/skills/` (adapted from [mattpocock/skills](https://github.com/mattpocock/skills), MIT).

## Submission checklist

- [ ] `casting.yaml` + `casting.yaml.lock` current with the final deployment
- [ ] Blog post (Medium / Dev.to / Substack)
- [ ] Screencast
- [ ] This README rewritten for the final build (what it is, how to run it, architecture)
