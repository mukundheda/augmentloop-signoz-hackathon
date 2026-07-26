# Result: the `next_hop` reroute was approved, applied, and re-run

Companion to `right-sizing-next-hop-2026-07-27.md`, which is the proposal. This
is what happened after a human said yes.

## The approved edit

```diff
--- a/toy-world/routing.json
+++ b/toy-world/routing.json
@@ -1,5 +1,5 @@
 {
   "route_choice": "anthropic/claude-sonnet-4.6",
   "eta_estimate": "anthropic/claude-sonnet-4.6",
-  "next_hop": "anthropic/claude-sonnet-4.6"
+  "next_hop": "google/gemini-2.5-flash-lite"
 }
```

Approved by Mukund. The agent that produced the proposal did not apply it and
could not: every edit to `routing.json` sits in the `ask` list. That gate is the
demonstration, not paperwork around it.

## The slice that changed

This is the honest comparison, because it is the only thing the edit touched.
Both runs are `python -m toyworld --live --production`, 20 real `next_hop`
decisions each, same junctions, same grader, same telemetry shape.

| `next_hop` | before (`claude-sonnet-4.6`) | after (`gemini-2.5-flash-lite`) |
| --- | ---: | ---: |
| correct | 19 / 20 | **20 / 20** |
| cost for the slice | $0.031380 | **$0.001101** |
| cost per correct decision | $0.0016516 | **$0.0000551** |

**30.0x cheaper, and it got one more answer right.** The proposal predicted
"~30x cheaper, 95% to 100%" before the run. That is the prediction and the
outcome, not a number chosen after the fact.

## The whole-run numbers, with the caveat that matters

| whole production run | before | after |
| --- | ---: | ---: |
| decisions | 60 | 60 |
| correct | 53 | 56 |
| total cost | $0.275391 | $0.251157 |
| cost per correct decision | $0.005196 | $0.004485 |

**Do not attribute all of that to the reroute.** Only `next_hop` was rerouted.
The other two decision types still ran on `claude-sonnet-4.6` and still moved
between runs, because live model calls are not deterministic: `eta_estimate`
went 19/20 to 20/20 and `route_choice` went 15/20 to 16/20 with no configuration
change at all. Roughly two of the three extra correct answers are run-to-run
variance in decision types nobody touched.

The slice table above is the claim. The whole-run table is context.

## Verified in SigNoz, not just in the CLI

The after-run's spans are queryable in the live stack, and the split matches the
CLI output exactly:

| model | decision type | correct | incorrect |
| --- | --- | ---: | ---: |
| `anthropic/claude-sonnet-4.6` | eta_estimate | 20 | 0 |
| `anthropic/claude-sonnet-4.6` | route_choice | 16 | 4 |
| `google/gemini-2.5-flash-lite` | next_hop | 20 | 0 |

## What this does not claim

Twenty queries per decision type is a demonstration, not a statistical result,
and the honest-limits section of `docs/right-sizing-loop.md` already says so. A
20/20 against 19/20 is not evidence that one model is better at `next_hop`; it
is evidence that the cheaper model did not get worse while costing 30x less,
which is the only claim the reroute needs.

The reroute was also not proposed for the other two types, and that is the more
interesting half of the result: `gemini-2.5-flash-lite` scores 0/20 on
`eta_estimate`. A tool that only ever says "go cheaper" would have moved all
three and destroyed one of them.
