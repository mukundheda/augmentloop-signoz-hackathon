# Cross-language parity runner

```
python universal-adapter/parity/run.py
```

Exit code 0 means every comparison agreed. Any other exit code means at least one
divergence, and every divergence is printed with both values and the character
offset where they part company.

No build step, no bundler, no `npm install`, no `node_modules`. Node 22+ executes
the TypeScript sources directly and the TypeScript package has zero npm
dependencies, which is a claim this runner would be an embarrassing place to
break. Python is invoked as the interpreter running `run.py`.

## Why this exists

The package ships two implementations of one protocol: `python/` (pytest) and
`typescript/` (node:test). Each has a corpus test asserting that IT agrees with
the shared fixture corpus. Neither can check the claim the acceptance criteria
actually make, which is that the two agree with EACH OTHER, because neither test
runner can execute the other language.

Two self-reports are not a parity proof. They establish that each implementation
agrees with a file, which leaves free to drift every choice the file does not
pin: how a number is spelled, how an astral character is escaped, which of two
keys sorts first, whether an explicit null survives a round trip. Those choices
are invisible until an identifier computed on one side fails to match the same
identifier computed on the other, at which point the protocol has silently
stopped being language neutral.

So this runner drives both implementations over identical inputs in one process
tree and diffs the answers.

## How it works

Three files, and the split between them is the point.

- `probe.py` and `probe.ts` ANSWER questions. Each loads the same inputs, asks
  its own implementation what it makes of them, and writes a map of
  `key -> answer as a string` to stdout as JSON. Neither probe decides whether an
  answer is acceptable, because a probe that could pass itself could report
  agreement it never observed.
- `run.py` JUDGES. It runs both probes, diffs the two maps, and fails on any key
  where the two strings differ or where one probe answered and the other did not.

Every answer is a string, including failures, which are recorded as
`error:<ClassName>`. That makes "both sides refused this input" a comparable
observation rather than a crash. Error MESSAGES are deliberately not compared:
the two languages word them differently on purpose, and diffing prose would
produce noise thick enough to bury a real divergence.

The shared inputs are:

- `../fixtures/index.json`, the 82 case corpus, read by both probes with no
  reinterpretation.
- `cases/canonical.json`, an adversarial value set for canonical serialization.
- `cases/records.json`, validation inputs at the type-system edges the corpus
  does not reach.

The case files are plain JSON so that neither language authors them. JSON cannot
spell NaN, the infinities, or a 513 character string without a 513 character
line, so those are written as `{"$parity": "..."}` escape objects that both
probes expand identically before anything is measured.

## What is compared

| Group | Comparisons | What it drives |
| --- | --- | --- |
| `validation_corpus` | 85 | The verdict on every document in the shared corpus. Cases marked `not_validated` are raw harness input, so the only shared observation is that both languages parse them to the same JSON type. Cases with `container: "array"` are compared element by element. |
| `canonical_fixture` | 85 | The canonical serialization of every document in the corpus, byte for byte. |
| `canonical` | 67 | The canonical serialization of a deliberately hostile value set: exact integers spelled as floats, negative zero, values below the six-decimal floor, the 1e15 rejection boundary, NaN and the infinities, non-ASCII, astral characters needing surrogate pairs, lone surrogates, control characters, the empty string, the empty object, the empty array, nesting, and null versus absent. Also the key sort trap where U+FFFF is a lower code point than U+1F600 but a higher first UTF-16 code unit, which is where a default JavaScript sort would silently disagree with Python. |
| `validation_extra` | 60 | 60 further validation inputs: the RFC 3339 shape rules including the impossible date that is accepted on purpose, the Python `True is an int` trap, integral floats used as token counts, `1e400` overflowing to infinity in both parsers, identifier length limits counted in code points versus code units, closed records versus the `ext` namespace, the math authority invariants, and records routed to the wrong validator. |
| `decision_id` | 18 | The derived decision id for every VALID bundle document in the corpus, not a sample. |
| `content_digest` | 18 | The bundle content digest, which is what makes a replay idempotent and a duplicate-with-different-content a rejection, for the same documents. |
| `pricing` | 3 | The pricing table id over the real table in `gradebook.pricing`, plus that table's canonical serialization and its model count. |
| **Total** | **336** | |

Every rule pinned in `python/tests/test_cross_language_rules.py` is driven here,
against the other language rather than against Python's own expectations: the
integer spelling rule, the six-decimal fraction rule, the 1e15 and non-finite
rejections, the non-ASCII and surrogate-pair escaping, the code point key sort,
null versus absent, the pricing table id shape, and the impossible date that is
accepted deliberately.

## What this proves, and what it does not

It proves the two implementations produce the same answer on these inputs.

**It does not prove either implementation is CORRECT.** Both could agree on the
same bug, and a shared bug is exactly the failure this runner is blind to: it
compares them to each other, not to the schemas and not to the specification. The
checks that face correctness live elsewhere, in
`python/tests/test_schema_parity.py`, which drives the corpus through the frozen
JSON Schemas as well as the hand written validator, and in the two suites' own
assertions. A green run here plus a red run there means two implementations
consistently wrong. Do not quote this runner as evidence of anything except
agreement.

Other limits, stated rather than implied:

- **The pricing table crosses the boundary as data, not as code.** The table
  lives in `gradebook.pricing`, a Python module TypeScript cannot import. So
  `probe.py` exports the table and `run.py` hands it to `probe.ts` as a file.
  What is compared is the id the two implementations derive from one identical
  table. This does not prove TypeScript could independently locate the table.
  Nothing could prove that, since the table has no TypeScript home.
- **Decision ids are compared for valid bundles only.** Python's
  `derive_decision_id` takes a typed model, so an invalid bundle fails at decode
  before any id exists, while TypeScript's `deriveDecisionId` reads a plain
  object and will happily derive an id for a malformed one. That is a difference
  in API strictness, not in the protocol, and comparing it would report a
  divergence that does not exist. Validation verdicts for invalid bundles ARE
  compared, in `validation_corpus`.
- **Error messages are not compared**, only error class names. See above.
- **Evaluation, cost attribution and OTel emission are not compared.** The two
  modules take structurally different inputs (Python dataclasses against
  TypeScript object literals) and comparing them needs a shared input encoding
  this runner does not yet have. This is the largest honest gap. Their
  cross-language behaviour currently rests on the two suites' separate
  self-reports, exactly the situation this runner was built to end for the
  serialization and validation layers.
- **The adapters in `../adapters/` are not compared.** They are empty.
- **Nothing here measures performance, memory, or concurrency.** Parity of
  answers only.

## Current status: 6 open divergences

The runner exits non-zero today. That is the runner working, not the runner
broken. Reporting green while these are open would make it worse than useless.
Both findings are in the implementations, which are outside this directory, so
nothing here has been changed to hide them.

**1. `$` means different things in the two languages (4 comparisons).**
`validation_extra :: datetime/embedded-newline`, `anchoring/trace-id-trailing-newline`,
`anchoring/span-id-trailing-newline`, `anchoring/sha256-digest-trailing-newline`.

A value that is otherwise well formed but carries a trailing newline, for example
`"2026-07-26T12:00:00Z\n"`, is ACCEPTED by Python and REJECTED by TypeScript. In
Python's `re`, `$` matches before a final newline; in ECMAScript it does not. The
patterns in `validation.py` are written `^...$` and the ones in `validation.ts`
are written `/^...$/`, and they are not the same assertion. It affects every
pattern-checked field: `observed_at`, `trace_id`, `span_id` and the sha256
digests. The schema is no help here, because a Python JSON Schema validator
applies the schema's own `^...$` pattern with Python's semantics and accepts the
trailing newline too. The Python fix is `\Z` rather than `$`, in every pattern,
in one commit.

**2. An explicitly null optional field does not survive Python's round trip
(2 comparisons).** `content_digest :: ruflo/expected-ruflo-swarm.bundles.json#0`
and `#1`.

Both fixtures carry `correlation.provider_response_id: null` written out
explicitly. TypeScript's `contentDigest` reads the raw object and hashes that
null. Python's `bundle_content_digest` decodes into a typed model and re-emits
it, and `Correlation.to_dict` omits fields that are `None`, so the null is gone
before hashing. The two languages then compute different content digests for the
same wire bytes. Since the content digest is what distinguishes a replay from a
conflicting duplicate, a mixed-language ingest would disagree about whether a
re-sent bundle is the same decision. This one is also a straight contradiction of
the canonical rule the package states in three places, that an absent key and a
present null are not interchangeable.

Note what does NOT diverge: `decision_id`, for the same fixtures. Derivation
hashes an explicit eight-field map that writes its nulls deliberately, so it is
immune. That is a good design being vindicated, and it is also why the content
digest gap went unnoticed.

## Adding a case

Add it to `cases/canonical.json` or `cases/records.json` and run the runner. The
probes are driven entirely by those files and by the corpus index, so neither
probe needs editing. If a new input needs something JSON cannot spell, add a
`$parity` escape to BOTH probes in the same commit, or the two sides stop asking
the same question and `run.py` will say so.

Keep the two probes structurally identical. A question one probe asks and the
other does not is reported as a missing answer rather than quietly reducing the
number of things compared, which is the one way a parity runner can lie.
