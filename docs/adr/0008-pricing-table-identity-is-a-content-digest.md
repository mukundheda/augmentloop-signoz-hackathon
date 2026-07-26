# 0008: Pricing table identity is a content digest

Date: 2026-07-26
Status: accepted

## Context

Issue #101 left open: "Which pricing-table identifier should be included in calculated usage records?" The acceptance criterion it serves is "Token pricing records the pricing-table version."

The requirement is real. A calculated cost is tokens multiplied by rates, and the rates drift: `reference-library/src/gradebook/pricing.py` already carries a retired tier kept only for older recordings, and its own docstring says the values are vendor list prices that drift and should be re-checked before submission. A stored cost figure with no record of which rates produced it cannot be reproduced or audited later, and two figures computed months apart cannot be compared.

The obvious answer is a hand-maintained version string, bumped whenever the table changes. It fails in the one case that matters. A version string records what someone remembered to write down, and the failure mode is silent: an edit without a bump produces two different cost figures wearing the same version, which is worse than no version at all because it looks trustworthy.

There is also a practical constraint. `pricing.py` currently has an open pull request against it, and adding a version constant there would conflict with in-flight work on a file this new package has no business editing.

## Decision

`pricing_table_id` is a content digest of the table itself, computed by the adapter rather than declared by the table:

```
gradebook.pricing@<first 12 hex characters of sha256 over the canonically serialized table>
```

- It cannot go stale. Any edit to any rate changes the identifier, because the identifier IS the rates.
- It requires no coordination and no discipline. Nobody has to remember to bump anything.
- It requires no change to `reference-library`. The adapter imports the existing table and hashes it, so this package stays a consumer of Gradebook rather than a modifier of it, and the open pull request against `pricing.py` is unaffected.
- The schema makes it mandatory exactly where it means something: a usage record whose `cost_provenance` is a token estimate must carry it, enforced by a conditional in the schema rather than by convention. A `provider_reported` cost does not carry it, because no pricing table was involved.

Canonical serialization is pinned precisely, because Python and TypeScript must produce the identical string from the identical table: JSON with keys sorted, no insignificant whitespace, and rates serialized in a fixed form. A cross-language parity test asserts the two agree, rather than both sides reading this paragraph and hoping.

Twelve hex characters is 48 bits, which is ample to distinguish the handful of table revisions that will ever exist and short enough to read in a log line.

## Consequences

- Any stored cost can be traced to the exact rates that produced it, and a figure computed under different rates is visibly different rather than quietly incomparable.
- The identifier is opaque. It says two figures used different rates, not which rate changed. Answering that is a git question, and the digest gives the reader the thing to search for.
- Because the digest is derived, a cosmetic reordering of the table changes the identifier even though no rate moved. Canonical serialization with sorted keys removes the common case of this; a genuine rate correction changing the identifier is the intended behaviour, not a bug.
- This deliberately does not solve provider-reported cost, which needs no table. That path stays untouched and keeps its precedence over anything calculated.
