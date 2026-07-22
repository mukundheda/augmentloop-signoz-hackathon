# 0001: Machine-checked grades only in the headline metric

Date: 2026-07-20
Status: accepted

## Context

The build's central claim is "cost per correct decision." A grade can come from three sources: a math checker (provable), a real-world outcome (provable, arrives later), or an AI judge (an opinion). We do not yet know which kinds of decisions Vedant's SaaS offers - the AI-touchpoint inventory call has not happened. Banning AI-judge grades entirely could make the layer unusable on the real substrate; letting them count silently would let one sharp question deflate the whole claim.

## Decision

The foundation layer records grades from all three sources, and every grade carries its source. The headline metric (cost per correct decision) and every "correct" claim in dashboards, blog, and screencast count ONLY math and reality grades. AI-judge grades may appear as a clearly labeled secondary view ("AI-estimated quality"), never inside the headline number.

## Consequences

- The core claim is machine-checkable all the way down; nothing to poke.
- The layer still works on any substrate the Vedant call turns up, worst case as the labeled secondary view.
- Dashboards and queries must filter by grade source, so the source attribute is mandatory on every evaluation event, not optional.
- If the SaaS turns out to offer only AI-judge-gradeable decisions, the headline number runs on the toy world (and any skin) alone, and the SaaS proof point is narrated as the labeled secondary tier.
