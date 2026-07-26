"""Small builders for unit tests.

Deliberately inline and minimal rather than drawn from the shared corpus: a unit
test should fail because the behaviour it names changed, not because someone
edited a fixture for an unrelated reason. The corpus is used only where the
corpus IS the subject, in test_schema_parity.py.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from gradebook_adapter.models import (
    AbsentValue,
    Correlation,
    Decision,
    DecisionEvidenceBundle,
    EvidenceItem,
    InlineValue,
    Subject,
    UsageRecord,
    Value,
)

RUN = "run-42"


def bundle(
    *,
    decision_id: Optional[str] = None,
    decision_type: str = "task_completion",
    evaluation_name: str = "repository.tests_pass",
    chosen: Optional[Value] = None,
    evidence: Sequence[EvidenceItem] = (),
    run_id: str = RUN,
    agent_id: Optional[str] = None,
    parent_agent_id: Optional[str] = None,
    model: Optional[str] = "anthropic/claude-haiku-4.5",
    session_id: Optional[str] = None,
    task_id: Optional[str] = "repair-auth-017",
    response_id: Optional[str] = None,
    usage_refs: Sequence[str] = (),
    metadata: Optional[dict[str, Any]] = None,
) -> DecisionEvidenceBundle:
    return DecisionEvidenceBundle(
        decision=Decision(
            decision_id=decision_id,
            decision_type=decision_type,
            evaluation_name=evaluation_name,
            chosen=chosen if chosen is not None else AbsentValue(reason="not_captured"),
        ),
        subject=Subject(
            harness="hermes",
            run_id=run_id,
            agent_id=agent_id,
            parent_agent_id=parent_agent_id,
            session_id=session_id,
            model=model,
        ),
        correlation=Correlation(task_id=task_id, provider_response_id=response_id),
        evidence=tuple(evidence),
        usage_refs=tuple(usage_refs),
        metadata=metadata,
    )


def inline(value: Any) -> InlineValue:
    return InlineValue(value=value)


def usage(
    usage_id: str,
    *,
    scope: Any = "model_invocation",
    provenance: Any = "provider_token_estimate",
    run_id: str = RUN,
    decision_ids: Sequence[str] = (),
    agent_id: Optional[str] = None,
    parent_agent_id: Optional[str] = None,
    contains: Sequence[str] = (),
    model: Optional[str] = "anthropic/claude-haiku-4.5",
    input_tokens: Optional[int] = 1000,
    output_tokens: Optional[int] = 500,
    provider_cost_usd: Optional[float] = None,
    pricing_table_id: Optional[str] = None,
) -> UsageRecord:
    from gradebook_adapter.costing import PRICING_TABLE_ID
    from gradebook_adapter.models import CostProvenance, UsageScope

    prov = CostProvenance(provenance) if isinstance(provenance, str) else provenance
    needs_table = prov in (
        CostProvenance.PROVIDER_TOKEN_ESTIMATE,
        CostProvenance.HARNESS_TOKEN_ESTIMATE,
    )
    return UsageRecord(
        usage_id=usage_id,
        scope=UsageScope(scope) if isinstance(scope, str) else scope,
        run_id=run_id,
        cost_provenance=prov,
        agent_id=agent_id,
        parent_agent_id=parent_agent_id,
        contains_usage_ids=tuple(contains),
        decision_ids=tuple(decision_ids),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        provider_cost_usd=provider_cost_usd,
        pricing_table_id=pricing_table_id or (PRICING_TABLE_ID if needs_table else None),
    )
