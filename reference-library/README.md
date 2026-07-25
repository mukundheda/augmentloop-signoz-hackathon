# Gradebook reference library (Python)

The reference implementation of the Gradebook recording contract
([`docs/conventions.md`](../docs/conventions.md)). It applies the contract in one
call: record an AI **decision**, grade it, price it, and emit the result as the
**standard** OpenTelemetry `gen_ai.evaluation.result` event with Gradebook's two
extension attributes (`augmentloop.grade.source`, `augmentloop.cost.usd`).

The conventions doc is language-agnostic and is the real contract; this library
is a convenience for Python callers. Any stack that emits the same event is
compliant.

## Scope

**Walking skeleton (ticket #5):** the thinnest complete path - one
**math-graded** decision, priced from a single per-model pricing table, emitted
as one standard event.

**Reality grades (ticket #8):** a decision captured now (`capture_decision`)
can be graded later by its real-world outcome (`record_reality_grade`). The
late grade emits the same standard event stamped `reality`, span-links back to
the decision span (conventions §6, span-link Role 1), and always carries
`gen_ai.response.id`. `DecisionRef.from_ids` rebuilds the handle across a
process boundary (webhook, cron sweep).

The AI-judge grade source extends this same seam in later tickets.

```python
from gradebook import capture_decision, record_reality_grade

# Inside the decision flow (model-call span active):
ref = capture_decision(response_id="resp_123")

# ...later, possibly in another process, when the outcome is known:
record_reality_grade(ref, name="clip.kept", correct=True)
```

## A reality grade needs no checker (ticket #43)

The common criticism of a portable grading layer is that it "standardizes the
shape of a verdict it cannot itself produce" - the graders are the hard,
domain-specific 80%. That is true for **math** grades. It is false for
**reality** grades: the app already emits the verdict (kept vs discarded,
thumbs-down, a process exit code), so there is nothing to compare and **no
checker to write**. `RealitySignal` wraps that existing signal.

Here is the entire diff to add reality grading to an existing command runner
(`examples/reality_from_exit_code.py`) - the OS exit code is the signal, and it
is under ten lines with no checker function anywhere:

```diff
+from gradebook import RealitySignal
+signal = RealitySignal("command.succeeded", decision_type="shell_command")

+@signal.on_outcome
 def run_command(step_id, command):
     return subprocess.run(command, shell=True).returncode == 0   # existing

 # at decision time, under the model-call span:
+signal.observe(step_id, response_id=step_id)
 run_command(step_id, command)                                    # existing call
```

`run_command` is unchanged; its own success boolean becomes the grade. The
signal fires, `record_reality_grade` span-links the grade back to the decision
and stamps `grade.source = reality`. For the webhook/cron hop where the outcome
lands in another process, swap the in-memory ref store for one that persists
`ref_to_ids(...)` and rebuilds with `ref_from_ids(...)` - still no checker.

## Usage

```python
from gradebook import record_decision

record_decision(
    name="route.fastest",              # gen_ai.evaluation.name (what was graded)
    model="anthropic/claude-3.5-haiku",  # gen_ai.request.model (must be in the pricing table)
    chosen="B",                      # the AI's answer
    correct="A",                     # the provably-correct answer (math grade)
    input_tokens=180,
    output_tokens=12,
    decision_type="route_choice",    # optional (augmentloop.decision.type)
    response_id="resp_123",          # optional (gen_ai.response.id)
)
```

This emits one `gen_ai.evaluation.result` span carrying `score.value=0.0`,
`score.label="incorrect"`, `augmentloop.grade.source="math"`, and
`augmentloop.cost.usd` computed from the pricing table. Configure an
OpenTelemetry SDK `TracerProvider` (e.g. the SigNoz OTLP exporter) so the event
is exported; the library itself depends only on the OTel API.

## Develop

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
pytest
```
