# Visuals

Renders over telemetry this build already emits. No new instrumentation, no
synthetic data: `capture_run.py` runs the same `toyworld.replay` through the
same Gradebook library and swaps only the exporter for an in-memory one, the
way the test suite does. Every span, attribute and span link in `run-data.js`
is the one that would have gone to SigNoz.

They are static files, so they open with a double-click and need no server, no
SigNoz, and no API key.

## Verdict attribution

A model-run trace holds 60 independent decision spans, not a sequential
journey - so there is no downstream to contaminate when reality disagrees with
one of them, and no `junction J<n>` span to walk forward through. What the data
still supports is the single hop: the conventions §6 span link (`Role 1`) that
carries a reality verdict, in service `toy-world-outcomes` and its own trace,
back to the one `route_choice` decision it judges, in service `toy-world` and
the model-run trace that made it.

![Verdict attribution, rendered from the committed replay recording on 2026-07-25: the reality verdict for route_choice-J1-J10, decided by anthropic/claude-sonnet-4.6, span-links back across trace and service to the decision it judges, both graded correct](span-link.png)

**60 reality verdicts, all 60 judging a `route_choice` decision, all 60
agreeing with that decision's math grade.** That is the whole population
recorded in this run, not a sample chosen to look good. Each verdict arrives
6.0-15.0ms after the decision's math grade, in a different trace and a
different service, and is still attributable to it by the span link alone.
Pick any of the 60 verdicts in the rail to see both ends of its hop: the
decision's model, cost, math grade and explanation, and the verdict's own
explanation.

The span link is the point. It is the piece of architecture that makes a late,
cross-service, cross-trace verdict attributable to the decision that earned
it, and it is otherwise invisible plumbing. This page no longer claims a blast
radius - the old copy walked "every decision after the wrong one in the same
journey," which was true when a trace was one driver's journey through three
junctions, and is false now that a trace is 60 independent probes. Shipping
that claim over this data would assert a causal chain that does not exist, so
it was cut rather than left to render an empty radius.

## Grade provenance (genome strip)

Every graded decision in the run is one glyph, in the order it was graded.
**Hue is where the grade's authority came from**, saturation is whether it was
right, height is what it cost.

![Grade provenance strip: 240 glyphs, blue for math grades and amber for reality grades, wrong decisions carrying a red foot along the baseline, with a legend showing 180 math (58 wrong), 60 reality (0 wrong) and 0 ai_judge](genome-strip.png)

Blue is a `math` grade, amber is a `reality` grade, and sienna is reserved for
`ai_judge`. A wrong decision washes out and keeps a fully saturated cherry foot,
so bad runs read as red streaks along the baseline without inspecting a single
glyph. The dashed divider is where the run crosses into `toy-world-outcomes` -
the late grades that arrive after the decisions they judge.

**180 math (58 wrong), 60 reality (0 wrong), 0 ai_judge.** The zero is the
point, not an omission: an AI's opinion never silently enters the headline
number ([ADR
0001](../adr/0001-machine-checked-grades-only-in-the-headline-metric.md)), and
the strip shows that as a fact about the run rather than a promise in prose.
Click any glyph for its model, cost and reasoning.

The glyph-width formula clamps between 6px and 30px so the strip scales from a
handful of decisions up to the thousands the idea is really for. At this run's
240 real glyphs it has already packed down to the 6px floor - checked directly
against this data rather than a simulated clone: still clickable, and hue and
the red baseline still read at a glance.

## Regret ledger

An options-book framing: a decision that has been math-graded but has no
real-world verdict yet is an open position carrying unrealized risk. When
reality arrives it closes that position green or red.

![Regret ledger, rendered from the committed replay recording on 2026-07-25: 180 positions, 120 open and 60 closed (60 green, 0 red), the open and closed books each capped in their own scroll container, with the closed book showing route_choice-J1-J9's position, math-graded correct and closed correct by its reality verdict](regret-ledger.png)

**180 positions, 120 open, 60 closed - 60 green, 0 red.** $0.033368 sits in
open positions, unrealized; $0.007862 in positions reality confirmed correct;
$0.000000 in positions reality found wrong, because none did. Do not read a
track record into that: every closed position in this run happens to be
green, and none has closed red yet to test whether the ledger would show one
honestly. The stronger, honest line is in the open book instead - $0.025874
sits in `eta_estimate` decisions the checker grades **58/60 wrong**, and not
one of the 60 has a real-world verdict. That is unrealized risk in the literal
sense: an opinion the world has not weighed in on.

The `OVERTURNED` state - a position that closes against its own math grade -
never fires in this run; 0 of the 60 closed positions disagree with their math
grade. The code path that renders it stays, for a run where reality does
disagree, but this page says plainly when a state has zero instances rather
than leaving a legend entry or example for something a reader will never see
here.

180 decisions is well past the 8-row open book the page was first built
against, so both books now scroll inside a capped rail instead of running the
page off the bottom. Click any position for its full detail, including the
reality verdict's explanation where one has arrived.

## Regenerating

```bash
pip install -e reference-library -e toy-world
python docs/visuals/capture_run.py     # rewrites run-data.js from a fresh run
```

Then open `docs/visuals/span-link.html`, `docs/visuals/genome-strip.html`, or
`docs/visuals/regret-ledger.html`. All three read the same `run-data.js`. The
replay is deterministic, so the numbers do not move between runs; only the
trace and span ids do.
