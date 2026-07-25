# Toy world (T3): the judge-runnable demo harness

A tiny road network - three junctions, four AI drivers - where the engine knows
every travel time, so the provably-fastest route at each junction is computable
and **every driver decision is math-gradeable**. Each decision is recorded
through the [Gradebook reference library](../reference-library/README.md);
journey outcomes arrive afterwards as **reality grades that span-link back** to
the decisions they judge (conventions §6, span-link Role 1).

**Replay mode is the default and the point:** the committed recording
(`recordings/replay-v1.jsonl`) replays deterministically, needs **no API
keys**, and fills the SigNoz dashboards from a judge's own machine. Live mode
(real models via OpenRouter) is the #9 data foundation for the
model-vs-model comparison; see [Live mode](#live-mode-9) below.

## Run it (one command)

From the repo root, with the SigNoz stack up (`foundryctl cast -f casting.yaml`):

```bash
pip install -e reference-library -e toy-world
python -m toyworld
```

Endpoint defaults to `http://localhost:4318`; override with
`OTEL_EXPORTER_OTLP_ENDPOINT`.

## Live mode (#9)

Live mode runs **every roster model over the same junctions with real calls**,
under a per-run budget cap, so the same decision is graded and priced across
models - the data the model-vs-model comparison panel reads from. The panel
itself already ships on the #7 dashboard ("Gradebook: Cost per Correct
Decision"), grouped dynamically by `gen_ai.request.model`, so new roster slugs
appear automatically with no dashboard change.

```bash
pip install -e reference-library -e 'toy-world[live]'    # note the [live] extra
export OPENROUTER_API_KEY=...                             # one key reaches all 3 models
python -m toyworld --live --budget 0.50                  # cap defaults to $0.50/run
```

The budget cap is enforced **before each call** (a call it can't afford is
never placed), never on Max plans. The current roster is `claude-haiku-4.5`,
`claude-sonnet-4.6`, and `gemini-2.5-flash-lite` (grounded against
OpenRouter's live `/models` catalog; the spec's original "Gemini Flash" was
delisted, so the Flash-Lite tier stands in for the cross-provider leg).

`--provider direct` is a temporary fallback for while OpenRouter credits are
provisioned: Anthropic natively (`ANTHROPIC_API_KEY`) + Gemini via its
OpenAI-compatible endpoint (`GEMINI_API_KEY`). OpenRouter stays the default.

## What you see in SigNoz

- **Services:** `toy-world` (journeys + decisions) and `toy-world-outcomes`
  (the late reality grades) - the deferred grade demonstrably crosses a
  service boundary, as it would in a real system.
- **Traces:** one trace per driver journey - a real waterfall of
  `journey driver-N` -> `junction JN decision` -> `gen_ai.evaluation.result`.
- **Events:** every grade carries `augmentloop.grade.source` (`math` for route
  choices, `reality` for journey outcomes), `augmentloop.cost.usd` priced from
  the shared pricing table, and the frozen standard attributes.
- The run prints the same numbers (decisions, correct, cost per correct, per
  model) so the dashboards can be eyeballed against ground truth.

## Test

```bash
pip install -e "toy-world[test]"
cd toy-world && pytest
```

All assertions are on emitted telemetry (in-memory exporter), never internals.
