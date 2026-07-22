# Gradebook Conventions - the recording contract

Status: accepted · Owners: Anish + Mukund · Parent ticket: #4 · Spec: #3
Governs: ADR [0001](adr/0001-machine-checked-grades-only-in-the-headline-metric.md) (machine-checked grades only in the headline) and ADR [0002](adr/0002-extend-the-standard-eval-event-do-not-deviate.md) (extend the standard event, do not deviate).
Names frozen against the live semantic-conventions YAML during the Day-1 verify (#2, checked 2026-07-22 at semconv **v1.43.0**).

---

## 0. What this document is (read this first)

This is the rulebook for the telemetry Gradebook emits. It describes **exactly which OpenTelemetry event to send and which fields to put on it** for every AI decision we grade. It is deliberately **language-agnostic**: follow it in Python, TypeScript, Go, or by hand, and your decisions show up correctly in SigNoz. The Python reference library is just a convenience that applies these rules for you - it is not required to be compliant.

If you record a decision the way this doc says, the SigNoz dashboards can answer the two questions the whole build exists for: **is the AI getting things right, and what does it cost per right answer?**

The contract has three mandatory parts:
1. Emit the **standard** `gen_ai.evaluation.result` event (Section 2).
2. Stamp **two extra fields** on it - grade source and cost (Section 3).
3. When a grade arrives **later** than the decision, **link it back** (Section 6).

Everything else in this doc is either how to fill the standard fields (Sections 4-5) or recommended-but-optional conventions that make the dashboards richer (Section 7).

---

## 1. The unit: one decision, one grade

- A **decision** is one AI choice that has a right answer we can check by machine (glossary: *Decision*). The fastest route in the toy world; whether a word is a filler word; whether a quote is verbatim. Each decision is the atomic unit of the build.
- A **grade** is the verdict on that decision: was it correct, given what the agent could know at the time? Every grade is emitted as **one** `gen_ai.evaluation.result` event and is stamped with its **grade source** (Section 3).
- A decision that has no machine-checkable answer is not part of the headline. It may still be graded by an AI judge, but only as a clearly-labelled secondary signal (Section 5).

---

## 2. The event: `gen_ai.evaluation.result` (standard OpenTelemetry)

We emit the **real** standardized event, never a private schema (ADR 0002). Source of truth: `open-telemetry/semantic-conventions-genai`, files `model/gen-ai/events.yaml` + `model/gen-ai/registry.yaml`, at `SEMCONV_VERSION=v1.43.0`.

> **Stability warning.** This event's stability is `development` (experimental). The field **names** below were verified stable across the 07-14 → 07-22 window (only requirement levels tightened), but an experimental event can still change. Pin the schema URL you emit against, and re-run the #2 verify before bumping the semconv version.

### Standard fields (defined by OpenTelemetry)

| Field | Type | OTel requirement | What it means | How Gradebook uses it |
|---|---|---|---|---|
| `gen_ai.evaluation.name` | string | **required** | Name of the evaluation metric | A short, low-cardinality id for *what* was graded, e.g. `correctness`, `route.fastest`, `quote.verbatim`. Keep it stable so dashboards can group by it. |
| `gen_ai.evaluation.score.value` | double | conditionally required ("If applicable") | Numeric score from the evaluator | Correctness as a number: `1.0` = correct, `0.0` = incorrect for math/reality grades; the judge's raw score for ai_judge (Section 4). Always set it for our grades. |
| `gen_ai.evaluation.score.label` | string | conditionally required ("If applicable") | Human-readable label; **low cardinality** | `"correct"` / `"incorrect"` for math/reality; the judge's label for ai_judge. Always set it for our grades. |
| `gen_ai.evaluation.explanation` | string | recommended | Free-form reason for the score | Optional short reason (e.g. "chose route B, true fastest was A"). Useful for debugging; never parsed by dashboards. |
| `gen_ai.response.id` | string | recommended ("when available") | Id of the completion being evaluated | **Always set it** when you have it. It is the correlation key that ties this grade to the exact model call it judges, and the fallback link for deferred grades (Section 6). |
| `error.type` | string | set only on failure | Error class, if the evaluation *itself* failed | Set only if the grader errored (imported error-attribute group). Not used in the normal path. |

### Where the event attaches

- The event **SHOULD be parented to the decision's operation span** (the span the LLM instrumentation created for the model call) whenever the grade is produced in the same flow.
- When you cannot parent it (the grade arrives later, or in a different process), you **MUST** set `gen_ai.response.id`, and for later-arriving grades you also add a span link (Section 6).

---

## 3. Our two mandatory extension fields (ADR 0002)

The standard event has no slot for *where a grade's authority comes from* and no slot for *money*. We add exactly two fields, as **namespaced extension attributes on the same standard event** - never a parallel schema (ADR 0002).

| Field | Type | Required? | Values | Meaning |
|---|---|---|---|---|
| `augmentloop.grade.source` | string | **mandatory on every grade** | `math` \| `reality` \| `ai_judge` | Where the grade's authority comes from (Section 3.1). Mandatory because every dashboard filters on it (ADR 0001). |
| `augmentloop.cost.usd` | double | on decisions where cost is known | US dollars | The money the decision cost: token counts (already reported by the standard instrumentation) times a per-model rate from a single pricing table. |

### 3.1 The three grade sources

- **`math`** - a checker computes the provably-correct answer and compares. The toy world's true fastest route; a filler word against a lexical check; a quote via a verbatim-substring check. A fact, not an opinion.
- **`reality`** - the real world proves it, usually **later** than the decision. The clip was actually kept; the appointment actually landed. A fact, but a delayed one - so it must link back (Section 6).
- **`ai_judge`** - another model scored it. An **opinion**, not a fact. Always allowed, always stamped `ai_judge`, and (per Section 5) never counted in the headline number.

### 3.2 Cost - the honest framing (ADR 0002, do not overclaim)

`augmentloop.cost.usd` is a **pricing table applied to token counts OpenTelemetry already reports** (`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, captured automatically by the LLM instrumentation). It is **not** a new cost-observability system. In the blog, screencast, and any copy: we attach a dollar figure to standard token data so cost and correctness live on the same event and can be divided. We never say "we added cost observability." Update prices in one place (the pricing table); do not scatter rate constants.

---

## 4. How correctness is encoded

One binary correctness grade, two fields, filled the same way every time:

- **math / reality grades** (the provable ones):
  - `gen_ai.evaluation.score.value` = `1.0` if correct, `0.0` if incorrect.
  - `gen_ai.evaluation.score.label` = `"correct"` or `"incorrect"`.
  - Set **both** every time (they are "conditionally required - if applicable"; for a binary correctness grade they always apply).
- **ai_judge grades** (the opinions):
  - `score.value` = the judge's raw score (document the range you use, e.g. 0.0-1.0).
  - `score.label` = the judge's label (keep it low-cardinality).
  - `augmentloop.grade.source` = `ai_judge`, always.

`gen_ai.evaluation.name` carries *what* was graded (the metric id), not the outcome. Use one stable name per check so a dashboard can group all grades of the same kind.

---

## 5. The headline rule (ADR 0001) - why grade source is mandatory

The build's central number, **cost per correct decision**, and every "correct" claim in dashboards, blog, and screencast, count **only grades where `augmentloop.grade.source` is `math` or `reality`** and the grade is correct. `ai_judge` grades appear **only** in a clearly-labelled secondary view ("AI-estimated quality"), never mixed into the headline.

This rule is enforced downstream, in the SigNoz/ClickHouse queries and dashboard filters, **not** in the recording library - the library's job is only to record the grade honestly with its source. That is exactly why `augmentloop.grade.source` is mandatory on every event: a grade with no source cannot be safely placed on either side of the line.

(The headline aggregation itself - the division, the math+reality filter - lives in SigNoz queries, per the spec's seam decision. This doc governs what is *recorded*, so those queries have honest inputs.)

---

## 6. Span-link Role 1: deferred grades link back (mandatory)

A **reality** grade usually arrives after the decision's span has already closed (the clip is kept minutes later; the appointment lands the next day). To keep it traceable to its cause:

- The deferred grade event **MUST carry an OpenTelemetry span link** whose linked span context is the **decision span** it judges.
- It **MUST also set `gen_ai.response.id`** to the decision's completion id, as the always-present correlation fallback when a live span context is not available across process or time boundaries.

The result: a grade that lands long after the decision is still one link away from the exact step that caused it. An operator following a bad outcome can walk from the late grade back through the decision chain (spec user story 25).

This is **Role 1** of span links - foundation-level and required on every substrate. (Role 2, agent-to-agent cause-and-effect inside the toy world or a skin, is a bonus and is out of scope for this contract.)

---

## 7. Recommended fields for the observatory (not mandatory)

The three mandatory parts above make the headline honest. These optional conventions make the *dashboards* work well. They are recommended, not required for compliance.

- **Model identity** - the model-vs-model comparison and right-sizing panels need to know which model made each decision. The standard `gen_ai.request.model` attribute is already set by the instrumentation on the decision span. **Recommended:** also copy `gen_ai.request.model` onto the evaluation event, so model comparison is a single-table query and needs no join.
- **Decision type** - right-sizing targets a *kind* of decision (reroute "filler detection" to a cheaper model, not "everything"). **Recommended:** add `augmentloop.decision.type` (string, low-cardinality: e.g. `route_choice`, `filler_detection`, `quote_extraction`).
- **Token counts** - `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` are emitted automatically by the LLM instrumentation (Traceloop/OpenLLMetry, confirmed in the #2 verify). They are the raw ingredient for `augmentloop.cost.usd`; you do not hand-count tokens.
- **Cardinality guardrail (important):** never put per-decision unique ids in labels - no vehicle ids, no request ids, no user ids as attributes you group by. Group-able labels must stay low-cardinality: model, decision type, grade source, grade label, metric name. High-cardinality ids belong in `gen_ai.response.id` / span ids for correlation, not in dashboard group-bys.

---

## 8. A worked example (end to end, in words)

**A math-graded decision (toy world, graded immediately).**
A driver-agent picks route B at a junction. The engine knows the true fastest route is A. Gradebook emits one `gen_ai.evaluation.result` event, parented to the model-call span, with:

```
gen_ai.evaluation.name        = "route.fastest"
gen_ai.evaluation.score.value = 0.0
gen_ai.evaluation.score.label = "incorrect"
gen_ai.response.id            = "<the completion id>"
augmentloop.grade.source      = "math"
augmentloop.cost.usd          = 0.00021        # input+output tokens x Haiku rate
gen_ai.request.model          = "anthropic/claude-haiku"   # recommended
augmentloop.decision.type     = "route_choice"             # recommended
```

The dashboard counts this as one decision, source `math`, incorrect, costing $0.00021 - eligible for the headline (Section 5).

**A reality-graded decision (arrives later, links back).**
A clip-scoring decision predicts a high viral score and the clip is kept. Ten minutes later the "kept vs discarded" outcome is known. Gradebook emits a second `gen_ai.evaluation.result` event with `augmentloop.grade.source = "reality"`, `score.label = "correct"`, the same `gen_ai.response.id`, **and a span link pointing back to the original decision span** (Section 6). The late grade is still one hop from the decision that earned it.

---

## 9. Frozen names + provenance

Verified 2026-07-22 against `open-telemetry/semantic-conventions-genai` @ `v1.43.0` (issue #2). Frozen for this build:

- Standard event: `gen_ai.evaluation.result` (stability `development`).
- Standard fields used: `gen_ai.evaluation.name`, `gen_ai.evaluation.score.value`, `gen_ai.evaluation.score.label`, `gen_ai.evaluation.explanation`, `gen_ai.response.id`.
- Our extensions: `augmentloop.grade.source` (mandatory), `augmentloop.cost.usd`.
- Recommended: `gen_ai.request.model`, `augmentloop.decision.type`, `gen_ai.usage.*_tokens`.

If the semconv version is bumped, re-run the #2 verify and reconcile this list before the change lands. Grade source being absent from the standard is a real, verified gap - the basis for the honest moat (ADR 0002) and a possible small upstream issue/PR, not a submission dependency.

---

## Cross-references

- ADR [0001](adr/0001-machine-checked-grades-only-in-the-headline-metric.md) - machine-checked grades only in the headline metric.
- ADR [0002](adr/0002-extend-the-standard-eval-event-do-not-deviate.md) - extend the standard event, do not deviate.
- [CONTEXT.md](../CONTEXT.md) - glossary (Decision, Grade, Grade source, Cost, Span link roles).
- Spec #3 - the product build (six layers); this doc is the Foundation layer's recording contract.
- Verify #2 - Day-1 technical verifies; froze the names above and confirmed token auto-capture.
