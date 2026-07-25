# 0001: Machine-checked grades only in the headline metric

Date: 2026-07-20
Status: accepted

## Context

The build's central claim is "cost per correct decision." A grade can come from three sources: a math checker (provable), a real-world outcome (provable, arrives later), or an AI judge (an opinion). We do not yet know which kinds of decisions Vedant's SaaS offers - the AI-touchpoint inventory call has not happened. Banning AI-judge grades entirely could make the layer unusable on the real substrate; letting them count silently would let one sharp question deflate the whole claim.

## Evidence (added 2026-07-25)

When this ADR was written, excluding AI-judge grades from the headline was a design preference, and it is worth being clear that it started as one. The published literature makes it an evidence-backed decision instead. LLM judges show **self-preference bias**, scoring their own outputs higher than equivalent outputs from other models ([arXiv 2410.21819](https://arxiv.org/abs/2410.21819)); they show **verbosity bias**, rewarding longer answers independent of quality; and they show **position bias**, where the presentation order of two candidates changes which one wins. These are independently replicated findings across multiple judge families rather than a single contrarian result ([arXiv 2506.02592](https://arxiv.org/abs/2506.02592)).

The consequence for this project is specific: a judge model that is a sibling of one of the candidates it scores puts a measurable thumb on the scale, and once a judge's score and a checker's score are both a float on a dashboard, nothing downstream can tell them apart. That is the case for making the source attribute mandatory rather than optional, and for filtering on it in the query rather than describing the policy in prose.

## Decision

The foundation layer records grades from all three sources, and every grade carries its source. The headline metric (cost per correct decision) and every "correct" claim in dashboards, blog, and screencast count ONLY math and reality grades. AI-judge grades may appear as a clearly labeled secondary view ("AI-estimated quality"), never inside the headline number.

## Amendment (2026-07-26): the headline is scoped to `math`, and reality sits adjacent

The Decision above sets a **ceiling** (no AI-judge grade ever enters the headline). It was read for a while as also setting a **floor** requiring both provable sources to be summed, and the shipped dashboard and CLI do not do that: both scope the headline to `augmentloop.grade.source = 'math'` and give reality its own adjacent panels. Issue #84 filed the disagreement between the documents and the code. The code is right and this ADR is what changes.

The reason is structural rather than editorial. A `route_choice` decision is graded **twice**: once by the checker at decision time, and once later by the outcome. The metrics carry no per-decision id, deliberately, because that is unbounded cardinality, so nothing downstream can dedupe the two grades back into one decision. Summing both sources therefore counts those decisions twice and inflates the denominator.

It is worth being precise about how much. Over the committed run, blending gives **$0.377553 / 177 = $0.002133** against the **$0.002973** we publish. That denominator of 177 is 127 math-correct plus 50 reality-correct, and it is the *same double count* that produced the flattering figure this project already retracted once, when a defective grader reported 177 correct. Blending grade sources reproduces the exact arithmetic we published a correction about.

So: the headline counts `math`. Reality is not demoted and not discarded. It is the only source that can overturn a checker, it does so 15 times in the committed run, and it gets adjacent panels of its own rather than being averaged into a number it would distort. A grade that arrives late and disagrees is the most interesting signal here, which is precisely why it should not be silently added to a total.

If a future substrate has decision types where reality is the *only* provable source, the headline for those types scopes to `reality` on the same principle: one source per number, named in the query, never blended.

## Consequences

- The core claim is machine-checkable all the way down; nothing to poke.
- The layer still works on any substrate the Vedant call turns up, worst case as the labeled secondary view.
- Dashboards and queries must filter by grade source, so the source attribute is mandatory on every evaluation event, not optional.
- If the SaaS turns out to offer only AI-judge-gradeable decisions, the headline number runs on the toy world (and any skin) alone, and the SaaS proof point is narrated as the labeled secondary tier.
