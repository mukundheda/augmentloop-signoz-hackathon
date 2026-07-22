# Gradebook reference library (Python)

The reference implementation of the Gradebook recording contract
([`docs/conventions.md`](../docs/conventions.md)). It applies the contract in one
call: record an AI **decision**, grade it, price it, and emit the result as the
**standard** OpenTelemetry `gen_ai.evaluation.result` event with Gradebook's two
extension attributes (`augmentloop.grade.source`, `augmentloop.cost.usd`).

The conventions doc is language-agnostic and is the real contract; this library
is a convenience for Python callers. Any stack that emits the same event is
compliant.

## Scope (walking skeleton, ticket #5)

The thinnest complete path: one **math-graded** decision, priced from a single
per-model pricing table, emitted as one standard event. Reality/AI-judge grade
sources and deferred span-links (conventions §6) extend this same seam in later
tickets.

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
