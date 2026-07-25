# Refresh the visuals and the README after #33

`#33` replaced the toy world's single decision type with three, and replaced
the recording with a **real OpenRouter live run**. `docs/visuals/run-data.js`
has already been re-captured from it (commit `bf00a5e`). Everything downstream
now cites numbers that no longer exist.

## Global constraints

1. **No new instrumentation.** Render only from the committed
   `docs/visuals/run-data.js`. Do not touch `reference-library/`, `toy-world/`,
   `cleancut-proof/`, `.github/`, `casting.yaml`, or `CLAUDE.md`.
2. **No synthetic data.** Every figure on every page traces to a span in
   `run-data.js`. Nothing invented, nothing rounded into something tidier.
3. **No causal claim the data does not support.** This is the whole point of
   this change - see Task 1.
4. **Self-contained and offline:** one `.html` per visual, `run-data.js` via a
   plain `<script src>`, no CDN, no network fonts, no build step.
5. **SigNoz Periscope tokens only**, matching the merged pages.
6. **Accessibility floor:** real `<button>`s with `aria-label`s, visible focus,
   colour never the sole carrier of state.

## The data, verified - use these figures, do not re-derive them

Run: 423 spans, 63 traces, captured 2026-07-25 from `replay-v1.jsonl`.

| | |
|---|---|
| Decisions (math grades) | 180 |
| Math-correct | 122 |
| Reality verdicts | 60 |
| `ai_judge` grades | 0 |
| Total cost | $0.041230 |
| Cost per correct decision | $0.000338 |

**By decision type (math grades):**

| type | correct | cost |
|---|---|---|
| `route_choice` | 60/60 | $0.007862 |
| `next_hop` | 60/60 | $0.007495 |
| `eta_estimate` | **2/60** | $0.025874 |

**By model (math grades):**

| model | correct | cost |
|---|---|---|
| `google/gemini-2.5-flash-lite` | 42/60 | $0.000343 |
| `anthropic/claude-haiku-4.5` | 40/60 | $0.008092 |
| `anthropic/claude-sonnet-4.6` | 40/60 | $0.032796 |

**Trace structure (this is what changed):** 3 large traces, one per model,
rooted at `model-run <model>`, each holding 60 sibling decision spans named
like `route_choice route_choice-J1-J9 decision`. Plus 60 single-span traces,
one per reality verdict, in service `toy-world-outcomes`. **The 60 decisions in
a model-run are independent probes, not a sequential journey.** There is no
`junction J<n>` span anywhere any more.

**Reality verdicts:** all 60 link cross-trace to a `route_choice` decision, all
60 are `correct`, and all 60 of the decisions they judge are also math
`correct`. **There are zero math-vs-reality disagreements in this run.** Do not
write copy implying otherwise.

## Task 1: re-point the blast radius (`docs/visuals/blast-radius.html`)

**The page is currently broken and, worse, its premise is now false.** It walks
"every decision after the wrong one in the same journey", which was true when a
trace was one driver's journey. A model-run's 60 decisions are independent, so
nothing downstream is contaminated. It also finds no `junction J<n>` spans, so
it renders an empty radius for every verdict.

Rework it to show **only what the data supports**: the cross-trace span link
from a reality verdict back to the decision it judges, per conventions §6,
span-link Role 1.

- Drop the forward-walk and the "N downstream decisions are inside the radius"
  claim entirely. Delete the code, do not leave it disabled.
- Retitle the page and its copy so nothing promises a blast radius. Something
  honest about provenance/attribution. Rename the file to
  `docs/visuals/span-link.html`, delete `blast-radius.html` and
  `blast-radius.png`.
- Keep what is genuinely interesting and true: the verdict lives in a different
  service **and** a different trace, arrives later than the decision it judges,
  and is still attributable to it. Show both ends of the hop with their trace
  ids, services, the decision's model, cost, math grade and explanation, and
  the verdict's own explanation.
- 60 verdicts is too many to list flat: let the reader pick one (a rail, a
  select, your call) and show the hop for it. State the count honestly.
- **Say plainly on the page that all 60 verdicts agree with their math grade in
  this run.** That is the honest finding, and a reader who sees only agreement
  should be told it is the whole population, not a sample you chose.

## Task 2: refresh the two working visuals

Both read the new data correctly already; their numbers and screenshots are stale.

- `docs/visuals/genome-strip.html`: verify it renders 240 glyphs (180 math + 60
  reality). Its legend counts are computed at runtime, so they should be right -
  confirm, do not assume. Re-shoot `docs/visuals/genome-strip.png`.
- `docs/visuals/regret-ledger.html`: now **180 positions, 120 open, 60 closed,
  60 closed green, 0 closed red**. Open cost $0.033368; closed-green cost
  $0.007862; closed-red $0.000000. Confirm the page computes these, and check
  it degrades sanely with an empty closed-red bucket and a 120-row open book
  (the old run had 8 open rows; 120 may need a scroll container or it will run
  off the page). The `OVERTURNED` highlight will now never trigger - make sure
  its absence does not leave a dangling legend entry or dead copy.
  Re-shoot `docs/visuals/regret-ledger.png`.
- The strongest honest line available for the ledger copy: **$0.025874 sits in
  `eta_estimate` decisions the checker grades 58/60 wrong, and not one of them
  has a real-world verdict.** Use it if it fits; do not overstate it.
- Rewrite every figure in `docs/visuals/README.md` for all three visuals,
  including the blast-radius section which Task 1 replaces.

## Task 3: fix the stale table in the root `README.md`

The five-second table merged in PR #66 cites the pre-#33 fixture and is now
wrong: it claims 12 decisions, 8 correct, $0.000467 per correct decision, and
models (`claude-sonnet-4`, `claude-3.5-haiku`, `google/gemini-2.0-flash`) that
the recording no longer contains.

- Replace the model table with the real per-model figures above, dated
  2026-07-25, and state that it is a live OpenRouter run rather than a replay
  fixture.
- Update the headline sentence to 180 decisions, 122 correct, **$0.000338 per
  correct decision**.
- The framing changes and the new one is stronger: the cheapest model is now
  also the most correct (`gemini-2.5-flash-lite`, 42/60 at $0.000343, against
  `claude-sonnet-4.6` at 40/60 for $0.032796 - roughly 95x the cost for fewer
  correct answers). Rewrite the surrounding sentence to match reality instead
  of keeping the old "the cheapest model is the worst here" line, which is now
  false.
- Do not touch anything else in the root README. It is a shared file.

## Verification required for every task

- Serve with `python -m http.server 8899 --directory docs/visuals` and drive
  the real page with `playwright-cli`; `file://` is blocked in that browser.
- Screenshot at 1400px and 375px; no horizontal scroll at 375px.
- `playwright-cli console` must report 0 errors.
- Recompute every figure you print against `run-data.js` and confirm it matches
  what the page renders.
