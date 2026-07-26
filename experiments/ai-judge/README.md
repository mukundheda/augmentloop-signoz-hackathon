# ai_judge side experiment

**This directory is not part of the product.** It is a one-off experiment that
exists to support ADR 0001 with a real number instead of an assertion.

## Why this exists

`GradeSource.AI_JUDGE` (`reference-library/src/gradebook/grading.py`) has
never been emitted by anything in this repo. It exists only as an enum value
and as an accepted string in `conformance/check_conformance.py`. The
committed run's census is 420 `math` grades, 140 `reality` grades, 0
`ai_judge` grades - and `docs/adr/0001-machine-checked-grades-only-in-the-
headline-metric.md` explains why: the headline metric ("cost per correct
decision") only counts sources a machine or the real world can prove, because
published research shows LLM judges carry self-preference, verbosity, and
position bias.

That ADR was, by its own admission, a design preference before it cited
evidence. This experiment gives it one more thing: a concrete measurement of
what trusting an `ai_judge` grade over this repo's own toy-world recording
would actually have cost, in dollars and in false verdicts.

## What it does NOT do

- It does **not** change `GradeSource`, `record_decision`, or any file the
  headline metric depends on.
- It does **not** modify `toy-world/recordings/replay-v2.jsonl` or any other
  committed run artifact - it opens the recording read-only.
- It does **not** touch `README.md`, `docs/visuals/`, `conformance/`,
  `benchmarks/`, `ci.yml`, or `viewer/` - the committed "0 ai_judge" claim for
  the real run stays true.
- It does **not** emit OpenTelemetry to the shared collector. The judge calls
  live entirely in this directory's own process and output files; nothing
  from this experiment can reach the SigNoz dashboards or contaminate the
  `toy-world` / `toy-world-outcomes` services the real run uses. (The task
  that produced this experiment allowed emitting under a distinct service
  name as an option; this run skips emission entirely, which is a strictly
  stronger isolation guarantee and needed no new wiring.)

## What it does

`grader.py` builds an `ai_judge` grader: for a given recorded decision, it
shows a real LLM (via OpenRouter) the EXACT prompt the graded model saw -
including the full road map - and that model's chosen answer, and asks the
judge to work out the correct answer itself and render a verdict. The judge
is never shown `world.Query.correct` or the checker's own verdict. It reuses
`toyworld.openrouter.OpenRouterClient` for the actual HTTP call (key
handling, base URL, retry/backoff on transient errors) rather than a new
client, per the constraint that produced this experiment.

`run_experiment.py` runs that grader over every decision in
`toy-world/recordings/replay-v2.jsonl`, compares the judge's verdict to the
recording's own math grade (`query.checker(chosen, query.correct)`, looked up
fresh from `world.QUERIES_BY_ID` - never a stored value, same discipline
`replay.py` uses), and reports a confusion matrix plus a recomputed "cost per
correct decision" using the judge's verdicts as the correctness signal
instead of the checker's.

## Judge model

`qwen/qwen-2.5-72b-instruct`, via OpenRouter. Chosen deliberately because it
is **not** one of the seven candidate models the toy world grades
(`anthropic/claude-haiku-4.5`, `anthropic/claude-sonnet-4.6`,
`google/gemini-2.5-flash-lite`, `mistralai/mistral-small-24b-instruct-2501`,
`meta-llama/llama-3.3-70b-instruct`, `openai/gpt-4o-mini`,
`deepseek/deepseek-chat`) - using one of those as its own judge would put
ADR 0001's self-preference bias directly into this experiment's own result
for that model's ~60 rows. It is cheap (~$0.36/M input, $0.40/M output
tokens on OpenRouter) and capable enough to actually do the graph arithmetic
the toy world's questions require, rather than guessing.

## Known issue while running

OpenRouter intermittently routes this slug to an upstream that returns a 200
response body shaped `{"error": {"code": 400, "message": "... does not
support endpoint: completions"}}` with `choices=None`, rather than a raised
HTTP error - so `OpenRouterClient`'s own retry loop (which only catches
`RateLimitError`/`APIStatusError`) never sees it. Measured ~1 in 5 calls on a
10-call sequential probe. `grader.py` retries this specific shape up to 3
times with backoff before giving up; `run_experiment.py` records any
still-failing row as an `"error"` entry rather than crashing the batch, and
those are excluded from the confusion matrix and cost recompute (counted
separately as `errors` in `summary.json`).

## Reproduce

```bash
cd augmentloop-signoz-hackathon
source .venv/bin/activate   # needs toy-world[live] installed for the openai SDK
python3 experiments/ai-judge/run_experiment.py \
    --recording toy-world/recordings/replay-v2.jsonl \
    --judge-model qwen/qwen-2.5-72b-instruct \
    --concurrency 8
```

Requires `OPENROUTER_API_KEY` in the repo-root `.env` (already gitignored).
Outputs `results.jsonl` (one row per judged decision, full detail) and
`summary.json` (aggregate) into this directory - both are experiment scratch,
not committed run artifacts of the real product.

See `WRITEUP.md` for the results of the run this repo actually did.
