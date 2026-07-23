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
(real models via OpenRouter) is ticket #9.

## Run it (one command)

From the repo root, with the SigNoz stack up (`foundryctl cast -f casting.yaml`):

```bash
pip install -e reference-library -e toy-world
python -m toyworld
```

Endpoint defaults to `http://localhost:4318`; override with
`OTEL_EXPORTER_OTLP_ENDPOINT`.

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
