# Proposal: a `reality` evaluator category for `gen_ai.evaluation.result`

**Status:** raised upstream, not yet resolved. This document consolidates an
argument already made piecemeal across a GitHub comment and two ADRs into one
place, so a reader (or a judge) doesn't have to reconstruct it from three
sources.

**Where this stands right now:** we commented with this argument on
[open-telemetry/semantic-conventions-genai#359](https://github.com/open-telemetry/semantic-conventions-genai/pull/359#issuecomment-5079243760)
("Add evaluator provenance attributes to `gen_ai.evaluation.*`") on
2026-07-25. This document is that comment, written up properly, not a new
claim. We have not opened a separate PR against the spec itself - the
existing thread already proposes the mechanism we're extending, and adding a
second competing PR would fragment the conversation rather than help it.

## The gap PR #359 doesn't quite close

PR #359 proposes an `evaluator.type` enum on `gen_ai.evaluation.result` with
four values: `deterministic`, `llm_judge`, `human`, `custom`. That's a real
and useful gap-fill: right now, if a deterministic checker and an LLM judge
grade the same trace, they emit identical-looking events, and nothing
downstream can tell a proof from an opinion.

We built the same pattern independently before finding that thread: an
app-level attribute, `augmentloop.grade.source`, with three values, `math`,
`reality`, `ai_judge`. Two of them map cleanly:

| Ours | Their enum | Meaning |
| --- | --- | --- |
| `math` | `deterministic` | A checker computes the provably-correct answer and compares |
| `ai_judge` | `llm_judge` | Another model scores the output - an opinion |

The third doesn't:

| Ours | Their enum | Meaning |
| --- | --- | --- |
| `reality` | **no slot** | The real world proved it, later |

## Why `reality` isn't `deterministic` and isn't `llm_judge`

`reality` is a grade that arrives asynchronously, after the decision's span
has already closed, from an actual outcome rather than a check computed at
evaluation time: the clip was actually kept by the editor, the estimated
arrival actually landed inside tolerance. It fails both existing categories
on the same test:

- Not `deterministic` - nothing computes it *at eval time*. There is no
  checker to run against the graph; the answer isn't known until later.
- Not `llm_judge` - no model ever scores it. It's a fact about what happened,
  not an opinion about what should have happened.

Concretely, in our own committed run: of 140 decisions carrying a `reality`
grade, 43 were marked wrong by the deterministic shortest-path checker and
still arrived inside tolerance. Zero went the other way. Neither grade is
wrong - they answer different questions - but a spec that only has
`deterministic` and `llm_judge` has no honest place to put either the grade
or that disagreement.

## What we think the fix is

Resolution timing is orthogonal to evaluator type, and the enum currently
conflates them. Two ways to close the gap, in order of how much we'd want:

1. **A fifth `evaluator.type` value** - something like `outcome` or
   `realized` - for grades computed from a real-world result rather than a
   check or an opinion.
2. **Failing that, a line in the spec** noting explicitly that resolution
   timing (at-eval-time vs. deferred) is a separate axis from evaluator type,
   so an implementer knows a deferred grade isn't automatically
   miscategorized as `custom`.

Either way, we handle the "arrives late" part today by re-emitting the event
with a span link back to the original decision span, plus the same
`gen_ai.response.id` as a correlation fallback - so a verdict that lands
minutes or hours after the decision closes stays one hop away from the
decision it judges. That mechanism is substrate-agnostic: it's the same
pattern whether the real world is a graph we drew (the toy world) or an
editor's actual publish decision (CleanCut, our production surface).

## Full detail

- [`docs/conventions.md` section 3](https://github.com/mukundheda/augmentloop-signoz-hackathon/blob/main/docs/conventions.md#3-our-two-mandatory-extension-fields-adr-0002) - the two mandatory extension fields (`augmentloop.grade.source`, `augmentloop.cost.usd`)
- [`docs/conventions.md` section 6](https://github.com/mukundheda/augmentloop-signoz-hackathon/blob/main/docs/conventions.md#6-span-link-role-1-deferred-grades-link-back-mandatory) - how the deferred `reality` grade links back
- [ADR 0001](../adr/0001-machine-checked-grades-only-in-the-headline-metric.md) - why the headline metric counts machine-checked grades (`math` + `reality`) only, never `ai_judge`
- [ADR 0002](../adr/0002-extend-the-standard-eval-event-do-not-deviate.md) - why we extend the standard event with namespaced attributes rather than invent a parallel schema

We're not claiming to have invented evaluation-into-OpenTelemetry - the
standard event and the `evaluator.type` proposal both predate this project.
The contribution here is narrow and specific: a third category the current
proposal doesn't have a slot for, evidenced by a real disagreement in a real
run, not a hypothetical.
