# 0006: Collecting evidence and running evaluators are separate processes

Date: 2026-07-26
Status: accepted

## Context

Issue #101 left open: "Should the CLI wrapper execute evaluators directly, or only produce evidence for a separate evaluator process?"

The convenient answer is that the wrapper does both. One command, `gradebook-run --manifest task.json -- some-agent run ...`, supervises the agent and then runs the test suite and emits a graded decision. Nobody has to wire two steps together.

The problem is what the wrapper is wrapping. It supervises an agent whose entire job is to modify a workspace, and it would then run the evaluator inside that same workspace, immediately after the agent finished editing it. The agent being graded would have had write access to the thing that grades it. It does not require malice: an agent asked to make the tests pass can edit the tests, weaken an assertion, add a skip marker, or change a script that the manifest's command resolves through. The wrapper would faithfully observe exit code 0 and report a `math` grade.

Issue #101 names this outcome as the most dangerous failure in the whole design: "The most dangerous failure is treating framework completion as correctness", with the mitigation "make it structurally impossible to emit a `math` grade without an evaluator result". A wrapper that runs the evaluator inside the graded workspace satisfies the letter of that mitigation while reintroducing the exact failure it was written to prevent. There is an evaluator result. It just is not independent.

## Decision

Collection and evaluation are separate steps, and the CLI wrapper produces evidence only by default.

- The wrapper captures process identity, start and end time, exit status, declared artifacts and their digests, and usage exports. It writes an evidence bundle. It does not grade.
- Evaluation is a separate invocation that reads the manifest and the recorded evidence and produces the verdict. The manifest is supplied by whoever owns the task, not by the agent and not by the harness, and the evaluator command is declared in the manifest rather than read out of harness evidence, so the process being graded cannot choose the test that grades it.
- `--evaluate` exists as an explicit opt-in for local development, where the operator is the same person as the agent's supervisor and the convenience is worth more than the independence. It is opt-in, it is documented as unsuitable for benchmark or production grading, and the resulting usage records carry the fact that collection and evaluation shared a process.

Artifact digests are what make the separation useful rather than merely ceremonial. The wrapper records what the workspace looked like when the agent stopped, so a later evaluator can detect that it is being asked to grade something other than what was submitted.

## Consequences

- The default path cannot produce a grade that the graded agent could have influenced, which is the property the whole protocol is for.
- Two steps instead of one. That is the cost, and it is the point.
- Evidence bundles become durable artifacts with value independent of grading: they can be re-evaluated later against a corrected manifest, which also means a grading bug can be fixed and re-run without re-running the agent.
- Deferred evaluation composes naturally with reality outcomes, which already arrive later by definition (ADR 0001). Both are the same shape: a verdict that lands after the decision it judges.
- This constrains harness collectors too. A native hook collector runs inside the harness process and is therefore in the same position as `--evaluate`. Native collectors gather evidence and never conclude.
