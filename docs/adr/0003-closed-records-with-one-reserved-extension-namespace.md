# 0003: Closed records with one reserved extension namespace

Date: 2026-07-26
Status: accepted

## Context

The universal evidence protocol (issue #101) is meant to serve harnesses that do not exist yet. That goal pulls schema design in two opposite directions and the issue left the fork open: "Should schemas use strict rejection of unknown fields or allow an extension namespace?"

Strict rejection everywhere (`additionalProperties: false` and nothing else) catches typos, which matters more here than usual. A harness author who writes `decision_typ` instead of `decision_type` under a permissive schema gets a silently ungraded decision, and the number that eventually looks wrong is the headline metric. But strict rejection also means any harness that wants to carry one extra field has to wait for a protocol version bump, which for a protocol whose whole promise is "integrate without asking us" is close to a contradiction.

Full permissiveness inverts both properties: nothing waits on us, and nothing is caught.

## Decision

Every object in every schema is closed (`additionalProperties: false`), except for exactly one reserved `ext` object per top-level record, which is free-form.

- A misspelled protocol field is rejected with an actionable error, because it lands in a closed object.
- A harness that needs to carry something we did not anticipate puts it under `ext` and integrates today, with no version bump and no conversation with us.
- Because `ext` is a named namespace rather than a permissive top level, a field added there can never collide with a protocol field we add later. Version 1.1 can introduce `decision.retry_of` without breaking a harness that was already carrying `ext.retry_of`.
- A consumer that does not understand the contents of `ext` ignores them. Nothing in `ext` is ever read by the evaluator or the costing layer, and nothing in it is copied into telemetry attributes.

The fixture corpus carries this as a matched pair: the same unknown field is a rejection case at the top level and an acceptance case under `ext`. That pair is what stops a future implementation from quietly relaxing the rule.

## Consequences

- Typo detection and forward extensibility both hold, which neither pure option delivers alone.
- The cost is one extra concept for an integrator to learn, and a nesting level for their extra fields.
- `ext` is deliberately inert. If something inside it ever turns out to be load-bearing, that is the signal to promote it to a real protocol field in a minor version, and the promotion is backward compatible by construction.
- Schema evolution rule that follows from this: adding an optional field is a minor version, and tightening or removing a field is a major version. `schema_version` is a `const` in every schema, so an implementation rejects a version it does not implement rather than guessing at it.
