# 0002: Extend the standard eval event, do not deviate

Date: 2026-07-22
Status: accepted

## Context

Early on we assumed "putting evaluation results into OpenTelemetry is unclaimed territory" and that our moat was inventing that plumbing. A triple-verified pass against primary sources killed that claim:

- `gen_ai.evaluation.result` is already a standardized OpenTelemetry GenAI semantic-convention event (semconv PR #2563, schema v1.39, stability "Development"). It carries `gen_ai.evaluation.name` (required), `.score.value`, `.score.label`, `.explanation`, `.response.id`.
- A small MIT library, **eval2otel**, already emits that standard event.

So the wiring exists. But the same primary-source reading showed exactly where it stops, and that gap is our foundation:

- The standard event has **no attribute for grade source** (was this a provable check or an AI's opinion). That is a genuine, verified gap - nothing in the OTel GenAI registry records whether a grade is provable or an opinion.
- The standard event also has **no dollar-cost attribute** - but the raw ingredient for one is already native: OTel standardizes token usage (`gen_ai.client.token.usage` as a metric, `gen_ai.usage.*_tokens` as attributes). So the honest gap is narrower than "cost has zero native support": what's missing is turning already-standard token counts into a dollar figure and attaching it to the same event as the grade, so cost and correctness can be divided together. Our contribution here is a per-model pricing table applied to those tokens, not new cost observability.
- eval2otel's own scope explicitly **excludes** "computing correctness verdicts, cost analysis, grade classification, agent-specific benchmarking" - which is precisely the Gradebook foundation.

The design temptation this ADR closes off: invent a private `augmentloop.grade` schema because the standard one "isn't enough." That would forfeit the "Best Use of SigNoz / OpenTelemetry" credit and read as not-invented-here.

## Decision

Gradebook emits the **real** `gen_ai.evaluation.result` event with its standard attributes, and layers our additions as **namespaced extension attributes on that same event**, never a parallel custom schema:

- Grade source is carried as a mandatory extension attribute (working name `augmentloop.grade.source`, values `math` / `reality` / `ai_judge`) - see ADR 0001 for why it is mandatory and why only `math` and `reality` count in the headline.
- Cost is carried as an extension attribute (working name `augmentloop.cost.usd`) on the decision, computed from the already-standard token counts times a per-model rate from a single pricing table - not a new metering mechanism, a dollar figure attached to data OTel already reports.

Where the standard already has a slot, we use the standard slot (score, name, explanation, response id). We extend only where the standard is genuinely silent (grade source, cost). Exact attribute names are finalized in the conventions doc during the Day-1 verify against the live semconv YAML, not frozen here.

## Consequences

- Anyone already reading OTel GenAI telemetry can read ours; the additions are additive, not a fork. Scores "Best Use of SigNoz" higher than a bespoke schema would.
- The honest moat is stated precisely and is defensible under a sharp judge question: machine-checked correctness (ADR 0001) + grade-source honesty + cost-per-correct + the right-sizing approve loop + three proof surfaces. "We invented eval-into-OTel" is **not** claimed anywhere - eval2otel exists and we credit it.
- Grade source being absent from the standard is a real, verified gap, and cost-as-a-dollar-figure-on-the-eval-event is a smaller but still real gap on top of already-standard token data. Framed honestly (a pricing table over standard tokens, not invented cost observability), this still earns a small honesty callout in the blog and a low-cost upstream issue/PR to the semconv repo (same move as the Jul-19 signoz-mcp-server bug). The upstream PR is a nice-to-have, not a submission dependency. Overclaiming this as "we added cost observability" is a live risk (flagged by the Jul-22 unbiased review) and must not appear in the blog or screencast copy.
- Day-1 verify is load-bearing: confirm the event's stability and exact attribute shape directly from the `open-telemetry/semantic-conventions-genai` YAML before the conventions doc freezes names (tracked in issue #2).
