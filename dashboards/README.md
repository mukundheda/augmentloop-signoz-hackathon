# Dashboards, alert rules and saved views

Everything SigNoz shows for this project, committed as JSON so it can be imported
rather than rebuilt by hand. Nine files: two dashboards, five alert rules, three
saved views.

Import each one in the SigNoz UI. Dashboards go to **Dashboards -> New -> Import
JSON**, alert rules to **Alerts -> New Alert -> Import JSON**, saved views to the
Traces or Logs explorer. The cold-machine walkthrough in
[`../docs/judge-run.md`](../docs/judge-run.md) does all of it in order, on a clean
machine, with the replay run that fills them.

## Dashboards

| File | What it answers |
| --- | --- |
| [`gradebook-cost-per-correct-decision.json`](gradebook-cost-per-correct-decision.json) | The headline. What does it cost this system to be right? 11 panels. |
| [`gradebook-meta-build-fleet.json`](gradebook-meta-build-fleet.json) | The same grading turned on our own work: the coding-agent sessions that built this repo. |

The headline dashboard is the one to open first. Its panels are ordered to walk
the argument rather than to fill a grid:

1. **Cost per 1,000 Correct Decisions** and **Cost per Correct Decision, by Model**
   are the number itself, whole-run and split by model.
2. **Correct Rate (%) by Model** is the other half of that ratio, so a cheap model
   that is cheap because it is wrong cannot hide inside the average.
3. **Cost Over Time, by Grade Source** separates spend by where the verdict's
   authority came from.
4. **AI-Estimated Quality** and the two **Reality** panels sit apart on purpose.
   The AI-judge panel is labeled a secondary view and the reality panels are
   labeled adjacent, because neither is summed into the headline. That separation
   is the project's central claim, so it is enforced in the panel layout and not
   only in prose. The reasoning is in
   [ADR 0001](../docs/adr/0001-machine-checked-grades-only-in-the-headline-metric.md).
5. **Right-Sizing Grid: Decision Type x Model** is the finding: no model wins every
   column, so routing keys on decision type rather than on picking one model.
6. **Failure Events by Class** and **Recent Failure Events** read the logs signal,
   and **Services Emitting Through the Contract** confirms which services are
   actually reporting.

## Alert rules

All five are metric or log based and spend nothing to evaluate. They cover all
three of SigNoz's rule types.

| File | Type | Fires when |
| --- | --- | --- |
| [`alert-grade-quality-anomaly.json`](alert-grade-quality-anomaly.json) | anomaly | Grade quality departs from its own recent seasonal baseline. This is the primary quality detector. |
| [`alert-grade-quality-drop.json`](alert-grade-quality-drop.json) | threshold | Correct rate falls through a static floor. Kept underneath the anomaly rule as a backstop. |
| [`alert-grading-pipeline-silent.json`](alert-grading-pipeline-silent.json) | threshold (absence) | No decisions of any grade source arrive at all, which is the failure a quality rule cannot see. |
| [`alert-spend-spike.json`](alert-spend-spike.json) | threshold | Total decision cost jumps against its recent level. |
| [`alert-budget-guard-trips.json`](alert-budget-guard-trips.json) | log based | The library's budget guard trips repeatedly, meaning runs are hitting the spend cap rather than finishing. |

Two of these are dormant on a freshly cast stack, and we would rather write that
down than let a judge discover it. The anomaly rule needs seasonal history before
it can fire, so it stays quiet on a stack that is minutes old. Any firing rule
reaches SigNoz's dispatcher but dies at the last hop, because the cast stack runs
no SMTP and so has nowhere to deliver. Both are measured facts recorded in
[`../docs/judge-run.md`](../docs/judge-run.md), not predictions.

## Saved views

Explorer queries, saved so the interesting question is one click away instead of
a rebuild.

| File | Explorer | Shows |
| --- | --- | --- |
| [`view-decision-traces.json`](view-decision-traces.json) | Traces | Decision spans next to the reality grades that land later and link back to them. |
| [`view-failure-events.json`](view-failure-events.json) | Logs | The three failure classes, each stamped with its trace and span. |
| [`view-judge-run-health.json`](view-judge-run-health.json) | Metrics | Decisions graded, the fastest way to confirm a replay run actually landed. |

## scripts/

[`scripts/record_build_fleet_sessions.py`](scripts/record_build_fleet_sessions.py)
emits the build-session decisions that fill the meta dashboard. It is what makes
that dashboard reproducible rather than a screenshot.
