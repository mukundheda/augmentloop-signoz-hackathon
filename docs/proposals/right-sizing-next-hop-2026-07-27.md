# Proposal: reroute `next_hop` from `claude-sonnet-4.6` to `gemini-2.5-flash-lite`

**Status:** proposed, awaiting human approval. Not applied. Per
`docs/right-sizing-loop.md`, the agent's reach stops here - a human types yes
to a specific, named edit in `toy-world/routing.json`, or does not.

## How this was produced

1. **Baseline (beat 1):** ran the production live run exactly as documented -
   `cd toy-world && python -m toyworld --live --production` - 60 real
   decisions (20 each of `route_choice`, `eta_estimate`, `next_hop`), all
   currently routed to `anthropic/claude-sonnet-4.6` per the committed
   `routing.json`. Window: **2026-07-26 ~21:04-21:08 UTC**. Real spend:
   **$0.275391**, 53/60 correct, cost per correct decision $0.005196.

2. **Reading the numbers (beat 2):** the production run alone only exercises
   the one model `routing.json` already points at, so it cannot by itself
   justify *rerouting to* anything - there is no second model in that run to
   compare against. Per `docs/right-sizing-loop.md`'s own guidance ("base it
   on the larger committed/historical runs already in SigNoz if the run is
   too small"), I queried SigNoz for the full 7-model roster comparison.

   The raw all-time history in the `toy-world` service (9,232 graded
   decisions found in a 30-day scan) turned out to be contaminated: it mixes
   in pre-fix defective replay runs from before three grader bugs were fixed
   (see `toy-world/README.md`'s changelog note), so per-model correct rates
   computed from it disagreed with the documented clean numbers (e.g.
   `claude-sonnet-4.6` / `eta_estimate` read 85% there vs. the documented
   95%). Rather than build a proposal on a blend I could not trust, I ran one
   fresh, deterministic, **$0-cost** replay of the committed recording
   (`python -m toyworld`, no flags, no API keys - the exact mechanism
   `toy-world/README.md` describes as reproducing the real `--live --record`
   run bit-for-bit) and scoped every SigNoz query to that run's own narrow
   window, **2026-07-26 21:14:19-21:14:28 UTC**. This produced exactly
   420 decisions (7 models x 3 decision types x 20 queries), matching
   `toy-world/README.md`'s committed table and the CLI's own printed output
   number-for-number.

## SigNoz access path

Reached the SigNoz MCP server (`http://localhost:8000/mcp`,
`SIGNOZ-API-KEY` header) as a genuine MCP JSON-RPC client - `initialize`,
`tools/list`, then `tools/call` for `signoz_list_dashboards`,
`signoz_get_dashboard` (to read the "Gradebook: Cost per Correct Decision"
dashboard's `panel-8-right-sizing-table` query definition), `signoz_list_metrics`,
`signoz_query_metrics`, and `signoz_aggregate_traces` - **not** through Claude
Code's native `mcp__signoz__*` tool bindings, because those tools were not
exposed in this agent session (a `ToolSearch` for them came back empty). The
protocol calls were made manually over HTTP with `curl`, speaking the same
JSON-RPC wire format Claude Code's MCP client would use, against the same
running server. Stating this plainly per instructions: this is MCP-protocol
access, not the internal SigNoz query-range HTTP API, but it went through a
hand-rolled client rather than the IDE's tool wrapper.

One correction en route: `signoz_query_metrics`'s smart-default wrapper
rejected `timeAggregation: "latest"` for the two `gradebook.*` counters
("not valid for metric type monotonic counter"; only `rate`/`increase`
allowed), even though the saved dashboard panel itself uses `"latest"`
successfully via the raw builder API. Rather than fight the counter's
increase-over-a-window semantics, I switched to `signoz_aggregate_traces`
(count / sum directly over the graded spans in the window) and verified it
reproduced the CLI's own printed numbers exactly, both for tonight's 60-decision
run and for the clean 420-decision replay.

## The data behind this proposal (clean 420-decision replay, verified via SigNoz)

All values below are cross-checked three ways: `toy-world/README.md`'s
committed table, the CLI's own stdout from the replay I ran, and the SigNoz
`signoz_aggregate_traces` query scoped to that replay's exact window. All
three agree to the dollar.

| Decision type | Model | Correct / n | Cost (20 queries) | Cost per correct |
|---|---|---|---|---|
| `next_hop` | `anthropic/claude-sonnet-4.6` | 19/20 (95%) | $0.031380 | $0.0016516 |
| `next_hop` | `google/gemini-2.5-flash-lite` | 20/20 (100%) | $0.001101 | $0.0000551 |
| `next_hop` | `openai/gpt-4o-mini` | 20/20 (100%) | $0.001520 | $0.0000760 |
| `next_hop` | `deepseek/deepseek-chat` | 20/20 (100%) | $0.002012 | $0.0001006 |
| `eta_estimate` | `anthropic/claude-sonnet-4.6` | 19/20 (95%) | $0.207645 | $0.0109287 |
| `eta_estimate` | `google/gemini-2.5-flash-lite` | 0/20 (0%) | $0.001100 | undefined (no correct) |
| `route_choice` | `anthropic/claude-sonnet-4.6` | 14/20 (70%) | $0.042696 | $0.0030497 |
| `route_choice` | `google/gemini-2.5-flash-lite` | 12/20 (60%) | $0.001134 | $0.0000945 |

(Tonight's independent live production run landed on the identical
`next_hop`/`claude-sonnet-4.6` figures - 19/20, $0.031380 - a second,
separately-executed data point agreeing with the replay's recorded numbers to
the dollar, which is itself a useful cross-check.)

## The four-part proposal

1. **Decision type:** `next_hop`
2. **Model change:** `anthropic/claude-sonnet-4.6` -> `google/gemini-2.5-flash-lite`
3. **Correct-rate, both models, n=20 each (confirmed in two independent runs
   for sonnet, one clean 420-decision run for gemini):**
   - `claude-sonnet-4.6`: 19/20 (95%)
   - `gemini-2.5-flash-lite`: 20/20 (100%)
   Quality does not merely hold, it improves slightly.
4. **Expected cost change:** cost per correct decision falls from
   **$0.0016516 to $0.0000551 - roughly 30x cheaper.** Raw cost per decision
   falls from $0.0015690 to $0.0000551 (~28.5x, matching the ~1/28th figure
   already documented in `toy-world/README.md`). Over the 20-query slice
   measured, that is a **96.5% reduction** in `next_hop` spend ($0.031380 ->
   $0.001101).

**No change proposed for `eta_estimate` or `route_choice`:**

- `eta_estimate`: `gemini-2.5-flash-lite` scores **0/20** against sonnet's
  19/20 - this is the exact catastrophic case `docs/right-sizing-loop.md`
  warns about. Sonnet stays.
- `route_choice`: the cheapest alternative (`gemini-2.5-flash-lite`, 12/20)
  is a real quality drop from sonnet's already-mediocre 14/20 (70% vs 60%
  correct). Per the doc's own "nobody is good at `route_choice`" caveat, this
  loop can tell you which model is cheapest for a decision type, not whether
  the decision type is being answered well - rerouting an already-poor
  decision type to something cheaper *and* worse is not right-sizing, it is
  cutting quality for cost with no offsetting proof of correctness. Leaving
  this at sonnet is the honest call until a human decides otherwise.

## The exact diff for human approval

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

This diff was **not applied**. `toy-world/routing.json` is untouched by this
agent. If approved, beat 4 is re-running
`cd toy-world && python -m toyworld --live --production` and confirming
`next_hop`'s correct-rate held (or improved) and its cost fell, the same way
this proposal was measured.

## Total spend disclosure

- Beat 1 (production baseline, real `--live` calls): **$0.275391**.
- Beat 2 (this proposal): **$0.00** - the 420-decision comparison came from
  a deterministic replay of the already-committed recording, which makes no
  API calls.
- **Total real API spend this session: $0.275391.**
