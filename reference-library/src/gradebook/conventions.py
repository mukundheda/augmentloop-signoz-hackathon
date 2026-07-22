"""Frozen OpenTelemetry attribute names for the Gradebook contract.

Single source of truth for the attribute *keys* this library writes, mirroring
docs/conventions.md section 9 (verified against open-telemetry/
semantic-conventions-genai v1.43.0 in issue #2). Tests assert literal strings
against the doc rather than these constants, so a rename here cannot silently
pass a test.
"""

# The standard event and its standard slots (OpenTelemetry GenAI semconv)
EVENT_NAME = "gen_ai.evaluation.result"
EVAL_NAME = "gen_ai.evaluation.name"
SCORE_VALUE = "gen_ai.evaluation.score.value"
SCORE_LABEL = "gen_ai.evaluation.score.label"
EXPLANATION = "gen_ai.evaluation.explanation"
RESPONSE_ID = "gen_ai.response.id"

# Standard attributes the LLM instrumentation already sets on the model-call
# span; echoed onto the event so the observatory needs no join (recommended).
REQUEST_MODEL = "gen_ai.request.model"
INPUT_TOKENS = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# Gradebook's namespaced extension attributes (ADR 0002).
GRADE_SOURCE = "augmentloop.grade.source"    # mandatory on every event (ADR 0001)
COST_USD = "augmentloop.cost.usd"
DECISION_TYPE = "augmentloop.decision.type"  # recommended
