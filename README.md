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

Every evaluation event carries `augmentloop.grade.source`, so that filter lives in the query rather than in this paragraph ([ADR 0001](docs/adr/0001-machine-checked-grades-only-in-the-headline-metric.md)). We raised the same evaluator-provenance question upstream, in [a comment on OpenTelemetry semantic-conventions-genai PR #359](https://github.com/open-telemetry/semantic-conventions-genai/pull/359#issuecomment-5079243760).

### Same three decision types, three models

From a live OpenRouter run captured 2026-07-25 and committed as the replay recording, priced from the shared pricing table:

| Model | Correct | Cost |
| --- | --- | --- |
| `anthropic/claude-sonnet-4.6` | 53/60 | $0.278031 |
| `anthropic/claude-haiku-4.5` | 42/60 | $0.096187 |
| `google/gemini-2.5-flash-lite` | 32/60 | $0.003335 |

The per-type split is the finding that matters: `google/gemini-2.5-flash-lite` is 20/20 on `next_hop`, edging out `anthropic/claude-sonnet-4.6`'s 19/20, at roughly 1/83rd of sonnet's cost for the run ($0.003335 vs $0.278031) - and that same gemini run scores 0/20 on `eta_estimate`, where sonnet is 20/20. One model, best choice for one decision type and unusable for another, in the same 60-decision run: that is why this project routes per decision type rather than per program (`docs/right-sizing-loop.md`), and it's the clearest evidence for it so far. 180 decisions, 127 correct, **$0.002973 per correct decision**. 20 decisions per model per type is a small sample and this is one run, so read the per-type pattern as a signal worth routing on, not a settled ranking of these three models. `python -m toyworld` prints these same numbers, so the dashboards can be checked against ground truth.

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
