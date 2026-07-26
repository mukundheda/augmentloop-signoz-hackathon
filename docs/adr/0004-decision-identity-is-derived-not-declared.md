# 0004: Decision identity is derived, not declared

Date: 2026-07-26
Status: accepted

## Context

Issue #101 left open: "Should decision IDs be supplied by adapters or deterministically derived from immutable fields?" Two acceptance criteria in the same issue constrain the answer more tightly than the question suggests:

- "Replaying the same evidence bundle is idempotent."
- "Duplicate decision IDs with different content are rejected."

If adapters mint their own ids freely, idempotent replay depends entirely on each adapter remembering what it minted last time. A CI importer re-reading yesterday's JSONL, or a wrapper re-run after a crash, would produce fresh ids for decisions that already exist, and the decision count would inflate on retry. The headline metric has a decision count in its denominator, so that inflation lands directly on the number this project exists to defend.

But requiring derivation for everyone throws away real information. Some harnesses already carry a stable native id for exactly this concept, and forcing them to hash around it means losing the join back to their own system.

## Decision

`decision_id` is optional in the bundle.

- When absent, it is derived deterministically: sha256 over a canonical serialization of the immutable identity fields (harness, run id, session id, agent id, decision type, evaluation name, task id, provider response id). Same inputs give the same id on any machine in any language, so replay is idempotent for free rather than by adapter discipline.
- When present, it is used exactly as supplied, and the record carries which of the two happened. An id whose provenance is unknown is an id nobody can reason about later.
- Either way, a duplicate id whose content digest differs is REJECTED, not overwritten and not silently accepted. Two different decisions wearing one id is a corruption that gets worse the longer it goes unnoticed, so it fails at ingestion where someone can still fix the adapter.

Derivation covers exactly eight fields: harness, run id, session id, agent id, decision type, evaluation name, task id, and the chosen value. It excludes evidence, usage references, model, trace and span ids, harness version, timestamps, and cost. Those can all grow or arrive after the decision, and including any of them would mean a decision changed identity when a late outcome landed, which would break the reality link ADR 0001 depends on.

### Amended 2026-07-26: the chosen value is included

The first version of this ADR excluded the chosen value, on the grounds that it was mutable. That was wrong on both the fact and the consequence, and the TypeScript implementation caught it.

On the fact: the chosen value is fixed at the moment the decision is made. Unlike evidence and usage, which accumulate, it never changes afterwards. It was never in the same category as the fields listed above.

On the consequence, which matters more: excluding it silently corrupts the headline metric. Two attempts at the same task, in the same run, by the same agent, differ in nothing else that derivation looks at. Both would derive the same id, the second would be rejected as a duplicate whose content differs, and the failed attempt would disappear. Issue #101 requires the opposite in as many words: "Failed attempts count toward efficiency", and "The numerator includes incorrect attempts". An identity rule that deletes failed attempts defeats the cost-per-correct metric on the side that makes it honest.

The limit this does not solve, stated rather than hidden: two attempts that produce an identical chosen value still collide. Nothing in the record distinguishes them, because the protocol has no attempt or sequence field. An adapter that needs identical retries counted separately must supply explicit decision ids, which is one of the reasons adapter-supplied ids remain permitted.

## Consequences

- Idempotent replay is a property of the protocol rather than a promise each adapter makes separately, which is what makes CI importers and crash-recovery re-runs safe by default.
- Harnesses with genuinely stable native ids keep them and keep the join back to their own system.
- Because derivation is a pure function of published fields, an implementation in any language produces the same ids, so the Python and TypeScript implementations can be checked against each other rather than trusted.
- Cost: canonical serialization has to match byte for byte across languages, which is a real and easy thing to get wrong. It is pinned by a parity test over the shared fixture corpus rather than by both sides reading the same paragraph and hoping.
- A harness that supplies unstable ids (a fresh uuid per run for the same logical decision) defeats idempotency. The protocol cannot detect this, and it is documented as an integrator responsibility rather than silently worked around.
