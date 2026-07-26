# 0005: Values are carried by reference or digest from version 1.0

Date: 2026-07-26
Status: accepted

## Context

Issue #101 left open: "Should sensitive `chosen` values support hashes and external artifact references from the first version?"

The tempting answer is to ship version 1.0 with `chosen` as a plain string, because most early fixtures are short answers, and add richer representations once someone needs them. The issue's own privacy criteria argue the other way: raw prompts and tool results must be optional and excluded by default, and artifact references must support digests instead of raw contents.

The deciding argument is not privacy alone, it is that value representation cannot be changed later without breaking everyone. Turning `chosen` from a string into an object in version 2.0 invalidates every stored bundle and every adapter simultaneously. A protocol whose pitch is that unknown future harnesses can integrate against published schemas cannot afford that break in its first year.

The second argument is that a plain string cannot express the difference between "the agent answered with an empty string" and "we did not capture the answer". Those grade differently, and a protocol that cannot tell them apart will silently grade the second as the first.

## Decision

Values are a tagged union from version 1.0, everywhere a value appears (`decision.chosen` and `structured_output` evidence):

- `inline` carries the value directly, for the common short case.
- `digest` carries a sha256 and optional byte length, proving what the value was without transmitting it.
- `artifact_reference` carries a pointer, with an optional digest so the pointer's target is tamper evident.
- `absent` carries a reason from a closed set (`redacted`, `not_captured`, `too_large`, `unknown`), so a missing value states why it is missing.

The default posture for an adapter is to prefer a digest or a reference over an inline payload. Inline is legal and convenient, not recommended.

## Consequences

- Privacy is structural rather than advisory. A harness handling credentials or customer source can participate fully while transmitting nothing, because a digest still supports the equality and file-digest evaluators.
- `absent` with a reason removes a whole class of silent misgrades, and gives an operator something actionable when coverage drops.
- The equality evaluators must define comparison across arms: a digest compares to a digest, and an inline value compares to an inline value. Comparing an inline value to a digest requires hashing the inline value with the same canonicalization, which is implemented rather than assumed.
- Cost: four arms to validate and test instead of one field, in two languages. That is paid once, in version 1.0, instead of paid as a breaking change later.
- `absent` is not a grade. A decision whose chosen value is absent can still be graded by an evaluator that reads evidence rather than the value, for example a command exit code.
