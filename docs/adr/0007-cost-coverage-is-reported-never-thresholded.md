# 0007: Cost coverage is reported, never thresholded by the protocol

Date: 2026-07-26
Status: accepted

## Context

Issue #101 left open: "What cost-coverage threshold is required before comparing harnesses?"

Cost coverage is the fraction of graded decisions that have an attributable cost. It exists because harnesses differ enormously in what they expose: some report per-call usage, some report only a session total, some report nothing. A cost-per-correct figure computed at 15 percent coverage and one computed at 98 percent coverage are not the same kind of number, and comparing them produces a confident ranking of nothing.

The question invites the library to pick a number, say 0.8, and refuse to compare below it. That is attractive and wrong for two reasons. First, any number we pick is unjustifiable: there is no measurement behind 0.8, and once it ships it acquires an authority it never earned. Second, and worse, a built-in threshold turns coverage into a gate that gets passed rather than a fact that gets read. A caller who clears 0.8 stops thinking about coverage, when the honest situation may be that the covered 80 percent is systematically the cheap decisions.

This project already made the analogous call once. ADR 0001 does not average `reality` grades into the headline metric with a correction factor. It reports them beside it, because the honest move when two things are not comparable is to show both, not to blend them behind a constant.

## Decision

The protocol computes cost coverage and exposes it. It never applies a threshold of its own.

- Coverage is calculated as graded decisions with attributable cost divided by all graded decisions, and reported alongside every cost-per-correct figure. A cost figure is never presented without its coverage.
- Comparison helpers take an explicit `min_coverage` argument with NO default value. Calling code must state the threshold it considers acceptable. There is no way to compare two harnesses without having written a number down.
- Coverage is reported per harness and per decision type, not only in aggregate, because a healthy aggregate can hide one decision type with almost no attribution.
- Nothing is inferred to raise coverage. An unattributable usage record lowers coverage rather than being spread across decisions, and missing cost stays missing rather than becoming zero.

## Consequences

- The library never silently blesses a comparison. The threshold is always a decision someone made and can be asked to defend.
- Low coverage becomes visible as a data problem to fix rather than an error to route around, which is the behaviour we want from an observability tool.
- Cost: every caller who compares has to supply a number, and there is no default to lean on. That friction is intentional and is the entire mechanism.
- Reporting coverage per decision type is what makes the right-sizing finding safe. Routing by decision type is only sound if each type's cost is actually attributed, and this makes a thin column obvious instead of averaged away.
- Open and deliberately unanswered: what threshold is appropriate in practice. That is an empirical question that needs runs across several harnesses to answer, and inventing an answer now would be exactly the kind of unbacked precision this project retracts elsewhere.
