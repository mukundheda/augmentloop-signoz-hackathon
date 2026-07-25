# D9: Half-Life Decay / Geiger Counter (issue #63)

Last of lane D's four visualizations. D6 (span link), D7 (genome strip) and D8
(regret ledger) are merged. Same shape, same rule: **finished, not
half-rendered.**

## The premise the ticket was written on is not in the data

Issue #63's second acceptance criterion says decay must be "driven by real
elapsed time between decision and reality grade". That time does not exist:

- An outcome row in the recording is `{graded_response_id, on_time, model}`
  (`toy-world/recordings/replay-v1.jsonl`, `replay.py:56-63`). **A reality
  grade carries no timestamp.** Nothing records when the world weighed in.
- The only decision-to-verdict delta available in `run-data.js` is 2.66ms to
  5.98ms, against a total run wall clock of 7.1ms. That is the replay loop
  iterating, not a modeled delay. It also correlates with loop index, so
  plotted as a decay curve it would look like a clean, convincing signal.

Rendering that as trust decay is the fabricated-latency figure this lane
already cut once (PR #80 removed "verdict arrives 6.0-15.0ms later" for exactly
this reason). **Do not resurrect it.** Nothing on this page may place a reality
verdict at a point in time.

**What is real, and what this page is instead:** decisions *do* carry a real
timestamp, embedded by OpenRouter in `gen_ai.response.id`
(`gen-1785000655-QbzMVktYXeFlvd6fYJ5y` -> epoch seconds). They span 446
seconds of genuine API calls. So a decision can be placed in time, and its age
at the end of the run is a real elapsed time. The decay is **how long a
decision has stood unconfirmed**, measured from when it was really made, and
for two thirds of them the confirmation never comes at all.

## What makes this page different from D8, which you must read first

`docs/visuals/regret-ledger.html` already ships the 120-open/60-closed split,
the open-position dollars, and the 15 overturned positions. **A table of
positions is D8. Building another one fails this ticket.** D9 owns the one
dimension none of the three merged visuals use: **time**. Its spine is the
446-second timeline, not a list.

It also owns the point D8 states but does not explain: the unconfirmed 120 are
not a backlog that will drain. `replay.py:210-230` only ever converts a
`route_choice` outcome into a reality grade, because `world.journey_on_time` is
the only real-world signal this world has. `eta_estimate` and `next_hop`
decisions are **structurally unconfirmable** - not slow, never coming. Their
trust decays to the floor and stays there. That is the page's thesis.

## Global constraints

These bind every task and the review:

1. **No new instrumentation.** The page renders only from
   `docs/visuals/run-data.js`, already committed and produced by
   `docs/visuals/capture_run.py`. Do not add attributes, do not change the
   recorder, do not touch any package under `reference-library/`, `toy-world/`
   or `cleancut-proof/`. Parsing the epoch out of `gen_ai.response.id` at
   render time is reading data we already emit, which is why this is allowed.
2. **No synthetic data.** Every number on screen traces to a span in
   `run-data.js`. No invented arrival times, no interpolated verdicts, no
   rounding a number into something tidier than it is.
3. **Self-contained and offline.** One `.html` file loading `run-data.js` with
   a plain `<script src>` tag. No CDN, no network fonts, no build step, no
   framework.
4. **SigNoz Periscope tokens only.** Copy the `:root` block from
   `docs/visuals/genome-strip.html` verbatim rather than inventing values.
   Canvas `--bg-ink-500` `#0b0c0e`.
5. **Honest about the sample.** 180 decisions, 60 confirmed, one 446-second
   window, one recording. Do not imply a longer observation than exists.

## The data, already analysed - use this, do not re-derive it

`window.RUN.spans` is a flat array of 423 spans. Relevant shape:

- A **decision** is a span named `gen_ai.evaluation.result` with
  `attributes["augmentloop.grade.source"] === "math"`, service `toy-world`.
  There are **180**. Each carries `gen_ai.response.id`,
  `augmentloop.decision.type`, `augmentloop.cost.usd`, `gen_ai.request.model`,
  `gen_ai.evaluation.score.label` and `gen_ai.evaluation.explanation`.
- A **reality verdict** is the same span name with `grade.source === "reality"`,
  service `toy-world-outcomes`. There are **60**. Match it to its decision on
  `gen_ai.response.id` - the correlation key `docs/conventions.md` mandates.
  Its timestamps are replay-loop artifacts; **do not read them.**
- **Decision time**: `gen_ai.response.id` matches `/^gen-(\d{10})-/`; group 1 is
  Unix epoch seconds of the real model call. Offset from the earliest gives
  0..446s. Verified present on all 180.

**These figures are verified against the committed `run-data.js`, not
estimated. Your page must reproduce them exactly at runtime:**

| | |
|---|---|
| Decisions | 180 |
| Observation window | 446s (7.4 min) |
| Confirmed by reality | 60 |
| Never confirmed | 120 (66.7%) |
| Total cost | $0.377553 |
| Cost never confirmed | $0.319381 (84.6%) |
| Cost confirmed | $0.058172 |
| Oldest unconfirmed decision, at run end | 415s |
| Median unconfirmed age, at run end | 107.5s |

Confirmation is entirely determined by decision type, not by model:

| type | n | confirmed | cost | first..last |
|---|---|---|---|---|
| `route_choice` | 60 | **60 (100%)** | $0.058172 | 0s..408s |
| `eta_estimate` | 60 | **0** | $0.276440 | 31s..427s |
| `next_hop` | 60 | **0** | $0.042941 | 109s..446s |

Every model confirms at exactly 20/60 (33%) - haiku-4.5, sonnet-4.6,
gemini-2.5-flash-lite alike. **Model is not the variable; decision type is.**
The page must not let a viewer read this as a model quality difference.

Unconfirmed ages at run end: `eta_estimate` oldest 415s / median 193.0s;
`next_hop` oldest 337s / median 84.0s.

The run cycles in blocks of 20: 20 route_choice, 20 eta_estimate, 20 next_hop,
repeat. On a timeline that reads as a real rhythm - a confirmable burst, then
two unconfirmable ones. Do not smooth it away.

Of the 60 confirmed, **45 agree with the math grade and 15 disagree**, all in
the same direction: math said `incorrect`, reality said `correct`. D8 covers
this as OVERTURNED. Reference it, do not re-litigate it.

## Task 1: the Half-Life page

Create `docs/visuals/half-life.html`.

**Required behaviour:**

- A **446-second timeline** as the page's spine, every decision placed at its
  real offset. This is the load-bearing element; if the page reads as a table,
  it has failed.
- Each decision **decays visibly the longer it stands unconfirmed**, computed
  from real elapsed seconds. A confirmed decision stops decaying when its
  verdict lands - but since a verdict has no timestamp, it must not be drawn at
  a time position. Settling it at the decision's own mark is the honest choice.
- **A Geiger counter**: playing the run back scrubs a playhead across the
  timeline, ticking as decisions land. Unconfirmed decisions accumulate and the
  chatter thickens; the run ends loud, not quiet, because 120 never resolve.
- **Sound is optional, off by default, behind a real `<button>`** that says
  which state it is in. A page that makes noise unprompted in a judging room is
  a liability. Use WebAudio built inline - no audio files, no library. Every
  tick must also be visible, so the page works fully muted.
- **The floor line**: `eta_estimate` and `next_hop` decay to a floor and stay
  there, and the page must say in words that this is structural - the world has
  no outcome signal for them - not a slow verdict.
- Summary figures at the top, all computed at runtime, never hardcoded: how
  many decisions, how many still unconfirmed at run end, the dollars in each
  bucket, the oldest unconfirmed age.
- **One self-check, in the page.** Four figures in this repo went stale in a
  single evening when someone else's merge changed the recording. Mirror
  `capture_run.py`'s `_check`: assert at load that every decision's
  `gen_ai.response.id` parses to an epoch and that confirmed + unconfirmed
  equals the decision count, and surface a visible banner if it fails rather
  than rendering a confident wrong page. Not a test file - `docs/` is not a
  package and a pytest there would never run in CI.

**Free choices** (make them, and defend them in the report): the decay curve's
shape and whether a half-life constant is named, playback speed and whether
scrubbing is manual, how a decision is marked, whether types get their own
lanes, exact typography and density.

**One trap to avoid:** a half-life implies a rate you can derive. You cannot
derive one here, because no verdict has a time. If you name a half-life
constant it is a **display parameter you chose**, and the page must label it as
such, in view, not in a comment.

**Verification, required before reporting DONE:**

- Serve the directory (`python -m http.server 8899 --directory docs/visuals`)
  and drive the real page with `playwright-cli`; `file://` is blocked there.
- Screenshot at 1400px and at 375px. Confirm no horizontal scroll at 375px.
- `playwright-cli console` must show 0 errors.
- Confirm against the raw data that your counts are 180/60/120 and that the
  dollar sums match the spans you summed.
- Confirm the page contains no reality-verdict timestamp anywhere, and that
  removing the reality spans' `startUnixNano` would change nothing on screen.
- Save the desktop screenshot as `docs/visuals/half-life.png`.

## Task 2: the README section

Add a section to `docs/visuals/README.md` in the same voice as the existing
three, embedding `half-life.png` and stating the real figures. It must say
plainly that reality verdicts carry no timestamp in this run and that the page
therefore places decisions in time and verdicts not at all. Update the
"Regenerating" list at the end to include the new page.

**Accessibility floor** (the other three meet it): interactive elements are
real `<button>`s with `aria-label`s and a visible focus ring; colour is never
the only carrier of state - pair it with a word; the page is fully usable with
sound off.
