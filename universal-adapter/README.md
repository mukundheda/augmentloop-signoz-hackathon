# Universal Agent Evidence Protocol

A harness-neutral, language-neutral way for any agentic system to be graded by
Gradebook, without Gradebook knowing anything about it.

The whole design follows from one sentence: **a harness supplies evidence, never
a grade.** A framework reporting `success: true` is telling you what it believes,
which is data. Whether the decision was actually correct is determined here, from
an evaluation manifest supplied by whoever owns the task, against an evaluator
that runs independently of the agent being graded.

Everything else in this directory exists to make that sentence enforceable rather
than aspirational.

## Why a protocol instead of adapters

The direct route is to write a Hermes integration, then a Ruflo integration, then
an AutoGen one. That produces four copies of the correctness rules, four cost
attribution schemes that disagree at the edges, and four couplings to extension
APIs that change without warning. Worse, it makes Gradebook depend on the
frameworks it is supposed to be able to judge impartially.

So the contract is the four JSON Schemas in [`schemas/`](schemas/), and the
frameworks are on the outside of it. A harness that does not exist yet can
integrate by reading those files. Nobody needs to ship it support.

## The four records

| Record | Answers | Supplied by |
| --- | --- | --- |
| [`DecisionEvidenceBundle`](schemas/decision-evidence-bundle.schema.json) | what decision was made, by whom, and what evidence is attached | the harness, through an adapter |
| [`UsageRecord`](schemas/usage-record.schema.json) | what was consumed, and how trustworthy that number is | the harness, through an adapter |
| [`EvaluationManifest`](schemas/evaluation-manifest.schema.json) | what the correct answer is, and who has authority to say so | whoever owns the task, independently |
| [`OutcomeRecord`](schemas/outcome-record.schema.json) | what reality later proved, and when | the world, after the fact |

Usage is deliberately a separate record from evidence rather than a field inside
it. One model call can inform several decisions, and a parent agent's totals
often already contain its children's calls. Keeping cost in its own record with a
stable `usage_id` is what makes it possible to charge that call exactly once.

## The invariants, and where each is enforced

These are the rules that make a grade worth reading. Each is enforced at a named
place, because "we are careful about this" is not enforcement.

**A harness cannot grade itself.** A framework's self-report is its own evidence
kind, `harness_claim`. No evaluator accepts that kind as authority. A claim may
trigger evaluation; it can never conclude it.

**A model's opinion cannot reach the headline metric.** `authority: "math"`
accepts only deterministic evaluator kinds. The one kind whose determinism is not
visible in its shape is `callback`, since a callback resolves from a registry that
could wrap a model, so a callback must declare `determinism` explicitly and only
`deterministic` may carry math authority. The schema cannot inspect what a named
callback actually does, so this does not make the bad case impossible. It makes it
an explicit false statement in a reviewable file instead of a silent pass by
omission, and the reference implementations enforce the same rule again at
registration, where a manifest disagreeing with the registry is a hard error.

**Authority may be given up, never taken.** A manifest may always claim less
authority than its evaluator could support. An `ai_judge` grade backed by a
deterministic checker is legal, because being conservative should never be
punished. The forbidden direction is the other one.

**Missing information stays missing.** Token counts and costs are nullable and are
never defaulted to zero. Zero is a measurement; null is an admission. A usage
record claiming `provider_reported` provenance without a provider figure fails
schema validation, so the honesty is structural rather than cultural.

**Cost coverage is shown, never assumed.** Coverage is the fraction of graded
decisions carrying attributable cost, and no cost figure is presented without it.
The protocol applies no threshold of its own ([ADR 0007](../docs/adr/0007-cost-coverage-is-reported-never-thresholded.md)).

**Replay is idempotent.** A `decision_id` omitted from a bundle is derived
deterministically from immutable identity fields, so re-importing yesterday's
logs does not inflate the decision count, which sits in the denominator of the
headline metric. A duplicate id whose content differs is rejected rather than
overwritten ([ADR 0004](../docs/adr/0004-decision-identity-is-derived-not-declared.md)).

**Values need not be transmitted.** `chosen` is a tagged union from version 1.0:
inline, digest, artifact reference, or explicitly absent with a reason. A harness
handling credentials or customer source can participate fully while sending
nothing ([ADR 0005](../docs/adr/0005-values-carried-by-reference-or-digest-from-v1.md)).

## Integrating a harness nobody has heard of

You need no code from this repository. The schemas are the contract.

1. **Choose your decision boundary** and name it in `decision_type`. Tool call,
   message, agent run, whole task: all are legitimate, and they are not
   comparable to each other. Only decisions sharing a `decision_type` are ever
   compared, which is why the field is required.
2. **Emit one `DecisionEvidenceBundle` per decision.** Fill what you have.
   Omit or null what you do not, and never invent a response id, a token count, a
   model name or a timestamp to fill a field.
3. **Emit `UsageRecord`s separately**, each with a `usage_id` that is stable
   across re-runs. If a parent agent's totals already include a child's calls,
   say so in `contains_usage_ids` rather than leaving it to be guessed at. If all
   you have is a session total, emit one record with `scope: "run"` and
   `cost_provenance: "run_aggregate"`; it will be attributed once, and coverage
   will honestly show what that cost the precision.
4. **Have someone who is not the agent write the `EvaluationManifest.`** This is
   the step that carries the whole design. If the thing being graded can choose
   or edit its own grader, nothing downstream is worth reading.
5. **Send `OutcomeRecord`s whenever reality answers**, which is usually much later.
   Each names the `decision_id` it judges, so the late grade links back to the
   decision it may overturn.
6. **Validate before you ship.** Run your output against the schemas. If it
   passes, any conforming implementation will accept it.

Anything you need to carry that the protocol does not model goes under the `ext`
object, which is the only place unknown fields are legal. You do not need to wait
for us to add a field ([ADR 0003](../docs/adr/0003-closed-records-with-one-reserved-extension-namespace.md)).

## Collection strategies

The protocol does not assume your harness supports any particular plugin model.

- **Native hooks**, where the framework exposes lifecycle or tool hooks.
- **OpenTelemetry mapping**, for harnesses that already emit agent and tool spans.
  A span supplies correlation and usage. It does not supply correctness, so an
  independent evaluator is still required.
- **A CLI wrapper**, which supervises a harness process without modifying it.
- **A CI or artifact importer**, reading JSONL, benchmark output, test reports or
  repository state after the fact. This is the fallback for frameworks with weak
  or unstable extension APIs, and it works on runs that have already finished.
- **Agent-declared claims**, where an agent marks its own decision boundaries.
  The declaration is untrusted and establishes only where a decision starts and
  stops, never whether it was right.

A note on wrappers and native hooks specifically: both run close to the agent, so
neither grades. They collect. Evaluation is a separate step for reasons set out
in [ADR 0006](../docs/adr/0006-collection-and-evaluation-are-separate-processes.md),
the short version being that an agent asked to make tests pass can edit the tests,
and a wrapper that evaluates inside the workspace it just supervised will
faithfully report a passing math grade for it.

## Conformance

[`fixtures/`](fixtures/) is the shared corpus: 82 cases, each declaring the schema
it targets and whether it must be accepted or rejected, indexed in
[`fixtures/index.json`](fixtures/index.json). Both reference implementations are
driven from this one file, so "Python and TypeScript agree" is checked against a
single declared expectation per case rather than each side asserting its own.

Every one of the 36 invalid fixtures isolates a single authored violation and
names it. The corpus is not decoration: writing it exposed two real defects in the
schemas it was written against, and forced one ambiguous design question to be
decided rather than discovered later by an integrator.

The `hermes/` and `ruflo/` fixtures carry the load-bearing claim. They are two
deliberately different raw shapes, one a nested per-session event stream with per
call token usage, the other a flat unordered record list joined only by run id
with cost available only as a session total. They normalize to the same canonical
protocol, which is what "harness neutral" has to mean if it means anything. Both
are hand written illustrative shapes, labelled as such in the files themselves,
and no harness package is imported anywhere in this directory.

## Where the schemas differ from the originating issue

The spec in issue #101 carried illustrative JSON that the frozen schemas do not
accept. In each case the schema is what implementations follow, and the
difference is deliberate rather than an oversight. Recorded here so a reader
working from the issue text is not left guessing which one is authoritative.

| Issue text | Schema | Why |
| --- | --- | --- |
| `cost_provenance: "token_estimate"` | `provider_token_estimate` or `harness_token_estimate` | Token counts from the provider and token counts a harness estimated are not equally trustworthy, and the precedence order has to be able to tell them apart. |
| evaluator `kind: "command"` | `command_exit_code` | Names what is actually checked. The exit status is the verdict; the command is how it is obtained. |
| `artifact_digest: "sha256:..."` as a string | object with `algorithm` and `digest` | A string forces every consumer to parse a prefix convention, and silently accepts a digest whose algorithm nobody agreed on. |
| `chosen: "search_database"` as a bare string | the tagged value union | See [ADR 0005](../docs/adr/0005-values-carried-by-reference-or-digest-from-v1.md). A bare string cannot distinguish an empty answer from an uncaptured one, and cannot carry a digest. |
| "application-provided checker callback" listed among deterministic evaluators without qualification | callback must declare `determinism` | This is the hole that would have let a model's opinion reach the headline metric. |
| "attach run-level cost to the terminal verified task decision" | no schema field identifies a terminal decision | Left to the implementations as an explicit option, defaulting to the last graded decision on the documented convention that callers list decisions in run order. Inventing a schema field for it would have been guessing at a concept the protocol does not otherwise model. |

## Relationship to Gradebook

This layer produces graded decisions. Emitting them is still the existing
contract: the standard OpenTelemetry `gen_ai.evaluation.result` event with
Gradebook's extension attributes, unchanged, and still checkable by
[`conformance/check_conformance.py`](../conformance/check_conformance.py).

Existing Gradebook users are unaffected and are not required to adopt any of this.
`record_decision`, `capture_decision` and `record_reality_grade` behave exactly as
before.
