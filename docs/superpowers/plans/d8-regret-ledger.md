# D8: Regret Ledger (issue #62)

Third of lane D's four visualizations. D6 (blast radius) and D7 (genome strip)
are merged; this follows the same shape and the same rule: **finished, not
half-rendered.**

## The idea

An options-book framing. A decision that has been math-graded but has **no
real-world verdict yet** is an *open position* carrying unrealized risk. When
reality arrives it *closes* that position green or red. The page should read
like a trading desk's book, not like a chat log or a dashboard tile.

## Global constraints

These bind every task and the review:

1. **No new instrumentation.** The page renders only from `docs/visuals/run-data.js`,
   already committed and produced by `docs/visuals/capture_run.py`. Do not add
   attributes, do not change the recorder, do not touch any package under
   `reference-library/`, `toy-world/` or `cleancut-proof/`.
2. **No synthetic data.** Every number on screen traces to a span in
   `run-data.js`. No invented positions, no placeholder rows, no rounding a
   number into something tidier than it is.
3. **Self-contained and offline.** One `.html` file that loads `run-data.js`
   with a plain `<script src>` tag. No CDN, no fonts fetched over the network,
   no build step, no framework.
4. **SigNoz Periscope tokens only**, matching the two visuals already merged.
   Copy the `:root` token block from `docs/visuals/genome-strip.html` verbatim
   rather than inventing values. Canvas `--bg-ink-500` `#0b0c0e`.
5. **Honest about the sample.** This run has 12 decisions and 4 reality
   verdicts. Do not imply a larger book than exists.

## The data, already analysed - use this, do not re-derive it

`window.RUN.spans` is a flat array of 32 spans. The relevant shape:

- A **decision** is a span named `gen_ai.evaluation.result` with
  `attributes["augmentloop.grade.source"] === "math"`, service `toy-world`.
  There are **12**. Each carries `gen_ai.response.id`, `augmentloop.cost.usd`,
  `gen_ai.request.model`, `gen_ai.evaluation.score.label`, and
  `gen_ai.evaluation.explanation`.
- A **reality verdict** is a span named `gen_ai.evaluation.result` with
  `augmentloop.grade.source === "reality"`, service `toy-world-outcomes`.
  There are **4**. Each carries `links[0].spanId`, pointing at the *junction
  decision span* it judges (NOT at the math grade event), plus its own
  `gen_ai.response.id` copied from the decision.
- The junction span (`name` starts with `junction`) is the **parent** of the
  math grade event. So to match a verdict to its decision, either:
  - follow `verdict.links[0].spanId` to the junction span, then find the math
    grade whose `parentSpanId` is that junction span's `spanId`; or
  - match `verdict.attributes["gen_ai.response.id"]` to the math grade's
    `gen_ai.response.id`. **Prefer this second route** - it is the correlation
    key the conventions doc mandates for exactly this purpose, and it is one
    lookup instead of two.
**These figures are verified against the committed `run-data.js`, not estimated.
Your page must reproduce them exactly at runtime:**

| | |
|---|---|
| Decisions (positions) | 12 |
| Closed | 4 |
| Open | 8 |
| Closed green (reality `correct`) | 2 |
| Closed red (reality `incorrect`) | 2 |
| Cost sitting in open positions | $0.002501 |

The four closed positions in full:

| `gen_ai.response.id` | math grade | reality grade | cost |
|---|---|---|---|
| `replay-d1-J3` | incorrect | **correct** | $0.000218 |
| `replay-d2-J3` | correct | correct | $0.000759 |
| `replay-d3-J1` | incorrect | incorrect | $0.000025 |
| `replay-d4-J2` | incorrect | incorrect | $0.000231 |

**`replay-d1-J3` is the most interesting row in the run and the page must not
flatten it:** the driver took a provably slower route (math says incorrect) and
still arrived on time (reality says correct). A position can close against its
own math grade. That is the honest case for why reality grades exist at all
rather than trusting the checker alone, and it should be legible on the page,
not buried.

## Task 1: the Regret Ledger page

Create `docs/visuals/regret-ledger.html`.

**Required behaviour:**

- A book of all 12 decisions, each row a position, showing at minimum: the
  decision (`gen_ai.evaluation.name` and the junction), the model, the cost, the
  math grade, and the position state.
- **Open and closed positions must be visibly distinct at a glance** - this is
  the ticket's one hard acceptance criterion. Open positions carry unrealized
  risk; closed ones are settled green or red.
- Summary figures at the top: how many open, how many closed green, how many
  closed red, and the dollar amount sitting in each bucket. Every figure derived
  from the data at runtime, never hardcoded.
- Where a position is closed, show what closed it (the verdict's explanation)
  and make the math-grade-vs-reality-grade relationship legible.

**Free choices** (make them and defend them in the report): row ordering,
whether open positions sort above closed, exact typography and density,
whether rows expand, how the trading-desk feel is achieved.

**Verification, required before reporting DONE:**

- Serve the directory (`python -m http.server 8899 --directory docs/visuals`)
  and drive the real page with `playwright-cli`; `file://` is blocked in that
  browser.
- Screenshot at 1400px and at 375px. Confirm no horizontal scroll at 375px.
- `playwright-cli console` must show 0 errors.
- Confirm against the raw data that your open/closed counts equal 8/4 and that
  the dollar sums match the spans you summed.
- Save the desktop screenshot as `docs/visuals/regret-ledger.png`.
- Add a section to `docs/visuals/README.md` in the same voice as the existing
  two, embedding that screenshot and stating the real figures.

**Accessibility floor** (the other two visuals meet it): interactive elements
are real `<button>`s with `aria-label`s and a visible focus ring; colour is
never the only carrier of state - pair it with a word.
