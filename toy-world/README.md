# Toy world (T3, extended by #33): the judge-runnable demo harness

A 20-junction weighted road network where the engine knows every travel time,
so **every answer key is computed** - a shortest-path calculation, never a
lookup and never hand-authored. Three decision types of genuinely different
difficulty run over the same graph, so the product's central claim (route each
decision type to the cheapest model that is still good enough at it) has
something to compare instead of a one-row table:

| Decision type | Difficulty | What it asks | Machine check |
|---|---|---|---|
| `route_choice` | hard | Which of two candidate multi-hop routes is fastest? Both candidates are real graph paths - the true shortest path and the best alternative that diverges from its first hop. | Exact match against the shortest-path label. |
| `eta_estimate` | medium | Estimate the travel time (minutes) of the fastest route between two junctions. | Within **±15%** of the true shortest-path time (`ETA_TOLERANCE_FRACTION` in `world.py`) - a numeric tolerance, not exact match. |
| `next_hop` | easy | At one junction, which single outgoing edge minimizes travel time? | Exact match against the cheapest edge. |

Difficulty is also tagged per decision (`augmentloop.decision.difficulty`:
`easy`/`medium`/`hard`) from the branching factor of the decision's starting
junction - independent of decision type, so correct-rate can be sliced either
way. Each decision is recorded through the
[Gradebook reference library](../reference-library/README.md).

**Replay mode is the default and the point:** the committed recording
(`recordings/replay-v1.jsonl`) replays deterministically, needs **no API
keys**, and fills the SigNoz dashboards from a judge's own machine.

> **The committed recording is currently a PLACEHOLDER.** It was written by
> the recorder (`--live --record`, below) run against a trivial
> always-correct oracle client, not a real model - every model in it scores
> 100%. That was a deliberate choice: rather than invent any per-model
> differentiation to make the numbers "interesting," the placeholder makes a
> maximally boring claim (a clean sweep) so it cannot be mistaken for a real
> comparative result. The real, split result (spec: "the cheapest model is
> fine at one-step decisions and falls apart on multi-hop routing") needs a
> real `--live --record` run against real models, which this PR's author
> could not perform (no API key in the build environment). See the PR
> description for exact next steps.

## Run it (one command)

From the repo root, with the SigNoz stack up (`foundryctl cast -f casting.yaml`):

```bash
pip install -e reference-library -e toy-world
python -m toyworld
```

Endpoint defaults to `http://localhost:4318`; override with
`OTEL_EXPORTER_OTLP_ENDPOINT`.

## Live mode (#9, extended by #33)

Live mode runs **every roster model over every query with real calls** -
3 decision types x 3 roster models x 20 queries = ~180 decisions - so the same
decision type is graded and priced across models. The panel itself already
ships on the #7 dashboard ("Gradebook: Cost per Correct Decision"), grouped
dynamically by `gen_ai.request.model`; **the two new decision types
(`eta_estimate`, `next_hop`) will not appear on any dashboard that allowlists
specific `augmentloop.decision.type` values until that allowlist is widened -
see the PR description.**

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

`--production` runs only the model each decision type's committed
`routing.json` entry currently assigns - each of the three types can route to
a different model, so a before/after reroute of just `next_hop` (say) is
directly comparable without the other two types' spend leaking in.

## The recorder (#33: `--live --record`)

Writes every `--live` decision to a replay file as it happens - the mechanism
that lets a real run become the next committed recording, instead of a
hand-authored one:

```bash
python -m toyworld --live --record --budget 2.00
# writes recordings/replay-v1.jsonl (default; override with --output)
```

The recording stores only what the model actually answered (`chosen`, token
counts, a response id) - never the correct answer. `replay.py` recomputes the
correct answer, checker, and difficulty fresh from `world.QUERIES_BY_ID` by
`query_id` at replay time, the same computation that produced the original
prompt, so a recording can never silently drift from the graph it was
recorded against.

The recorder is built and unit-tested against a deterministic, duck-typed
fake `ModelClient` (`tests/test_recorder.py`, same discipline as
`tests/test_live.py`) - it has **not** been run against a real provider as of
this PR.

## What you see in SigNoz

- **Service:** `toy-world`.
- **Traces:** one trace per model (`model-run <model>`) - a waterfall of
  `<decision_type> <query_id> decision` -> `gen_ai.evaluation.result`.
- **Events:** every grade carries `augmentloop.grade.source` (`math`),
  `augmentloop.decision.type` (`route_choice` / `eta_estimate` / `next_hop`),
  `augmentloop.cost.usd` priced from the shared pricing table, and the frozen
  standard attributes.
- **Decision spans** additionally carry `augmentloop.decision.difficulty`
  (`easy` / `medium` / `hard`).
- The run prints the same numbers (decisions, correct, cost per correct, per
  model, per model x decision type) so the dashboards can be eyeballed
  against ground truth.

## Test

From the repo root, on Python 3.10 or newer:

```bash
pip install -e reference-library -e "toy-world[test]"
cd toy-world && pytest
```

All assertions are on emitted telemetry (in-memory exporter) or the computed
answer key (`world.py`'s pure graph functions), never internals.
No API keys, and the `[live]` extra is not needed - the live clients check for
their key before importing a provider SDK, so their fail-loud paths are
testable without one.

**Both packages must be in the same `pip install`.** `gradebook` is also an
unrelated project on PyPI; installing `toy-world` on its own resolves the
dependency against that one and every test dies at collection. `tests/conftest.py`
detects this and prints the fix.
