"""Convert a graded decision into the EXISTING gradebook contract.

This package deliberately owns no telemetry vocabulary of its own. Everything
here funnels into `record_decision`, `capture_decision` and
`record_reality_grade`, so the emitted event stays the standard
`gen_ai.evaluation.result` with Gradebook's existing extensions, and an adopter
who already reads those dashboards sees adapter-sourced decisions in them with
no new query. Nothing in this module changes gradebook's behaviour for existing
callers: it only calls the public seams, with providers injected rather than
taken from global state.

Two refusals are load bearing, and both are places where a lesser implementation
would fabricate:

1. An UNGRADED decision is never emitted. There is no verdict to report, and
   emitting one would be inventing correctness.
2. An `ai_judge` verdict is never emitted through `record_decision`, because
   that seam stamps `augmentloop.grade.source = math`. Sending an opinion
   through it would launder a model's guess into the headline metric, which is
   the single failure this whole protocol exists to prevent.

Privacy. Three things must not reach telemetry: raw payloads, secret-like
values, and high-cardinality identifiers on METRIC attributes. The defence is
structural rather than a filter bolted on the end. This module builds the
gradebook call from an explicit allowlist of fields, and `chosen` is never one
of them: the value the agent produced is used to derive a verdict and is then
left behind. Metric attributes come entirely from gradebook's own fixed set
(grade source, score label, model, decision type, grade reason), so a decision
id, a run id or a metadata blob has no path into a metric series at all.
`redact` is the last line, not the first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional, Sequence

from gradebook.checkers import CheckResult, ReasonCode
from gradebook.grading import GradeSource
from gradebook.recorder import (
    DecisionRef,
    capture_decision,
    record_decision,
    record_reality_grade,
)
from opentelemetry import trace
from opentelemetry.metrics import MeterProvider

from .costing import DecisionCost
from .evaluation import EvaluationResult
from .models import CostProvenance, DecisionEvidenceBundle, OutcomeRecord, UsageRecord

REDACTED = "[redacted]"

# Field names whose VALUE is presumed sensitive regardless of what it looks like.
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|authorization|credential|"
    r"private[_-]?key|access[_-]?key|client[_-]?secret|session[_-]?key)",
    re.IGNORECASE,
)

# Value shapes that are secrets wherever they appear. Kept narrow on purpose: a
# greedy pattern that redacts model slugs or ids would make telemetry useless and
# push people to disable redaction entirely.
_SECRET_VALUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

_MAX_EXPLANATION = 1024


class EmissionError(Exception):
    """Base class for the cases this module refuses to guess its way past."""


class NotGradedError(EmissionError):
    """A decision with no verdict was handed to the emitter."""


class AuthorityNotEmittableError(EmissionError):
    """The verdict's authority has no seam in the reference library."""


class CostNotRepresentableError(EmissionError):
    """The attributed cost cannot be carried faithfully by `record_decision`."""


def is_secret_like_key(name: str) -> bool:
    """Whether a field NAME implies its value must never be emitted."""
    return _SECRET_KEY_RE.search(name) is not None


def redact(text: Optional[str]) -> Optional[str]:
    """Replace secret-shaped substrings. Structure is kept, the secret is not."""
    if text is None:
        return None
    out = text
    for pattern in _SECRET_VALUE_RES:
        out = pattern.sub(REDACTED, out)
    return out


@dataclass(frozen=True)
class EmissionInputs:
    """What `record_decision` needs, assembled only from usage records.

    Nothing here is inferred. If a harness did not report a model or token
    counts, these stay None and the emitter fails loud rather than inventing the
    numbers that price a decision.
    """

    model: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    response_id: Optional[str]


def resolve_emission_inputs(bundle: DecisionEvidenceBundle,
                            usage: Sequence[UsageRecord]) -> EmissionInputs:
    """Collect model, tokens and response id for one decision's charged usage."""
    models = {record.model for record in usage if record.model is not None}
    if bundle.subject.model is not None:
        models.add(bundle.subject.model)
    model = models.pop() if len(models) == 1 else None

    def _total(attribute: str) -> Optional[int]:
        values: list[Optional[int]] = [
            getattr(record, attribute) for record in usage
        ]
        # One unreported count makes the total unreported. A partial sum
        # presented as a total is the same lie as a fabricated zero.
        if not values or any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    correlation = bundle.correlation
    response_id = correlation.provider_response_id if correlation else None
    if response_id is None:
        for record in usage:
            if record.provider_response_id is not None:
                response_id = record.provider_response_id
                break
    return EmissionInputs(
        model=model,
        input_tokens=_total("input_tokens"),
        output_tokens=_total("output_tokens"),
        response_id=response_id,
    )


def emit_graded_decision(
    bundle: DecisionEvidenceBundle,
    result: EvaluationResult,
    *,
    usage: Sequence[UsageRecord] = (),
    cost: Optional[DecisionCost] = None,
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
    on_stronger_cost: Literal["raise", "reprice"] = "raise",
) -> None:
    """Record one math-graded decision through gradebook's existing seam.

    The already-computed verdict is replayed into `record_decision` through its
    `checker` hook, so gradebook does not re-grade anything and the authority
    stays where the evaluator put it.

    `on_stronger_cost` exists because of a real gap between this protocol and the
    reference library: `record_decision` prices a decision from tokens and its
    own table and takes no dollar figure, so a provider-reported cost, which by
    the protocol's precedence WINS over any calculated figure, cannot be carried
    through it. Default is to raise rather than silently emit the weaker number
    under the stronger one's name. Pass "reprice" to accept the table estimate
    knowingly.
    """
    if not result.graded:
        raise NotGradedError(
            f"decision {result.decision_id!r} has no verdict (reason "
            f"{result.reason.value}), so there is nothing to record. An ungraded "
            "decision is not an incorrect one, and emitting it as either would "
            "invent a grade."
        )
    if result.authority is not GradeSource.MATH:
        raise AuthorityNotEmittableError(
            f"decision {result.decision_id!r} was graded with authority "
            f"{result.authority.value if result.authority else 'none'}. "
            "gradebook.record_decision stamps augmentloop.grade.source=math, so "
            "sending anything else through it would misreport the authority. "
            "Report ai_judge results separately, and use emit_reality_outcome "
            "for reality."
        )

    inputs = resolve_emission_inputs(bundle, usage)
    if inputs.model is None or inputs.input_tokens is None or inputs.output_tokens is None:
        raise CostNotRepresentableError(
            f"decision {result.decision_id!r} cannot be emitted: "
            "gradebook.record_decision requires a model and both token counts to "
            "price the decision, and this decision reports "
            f"model={inputs.model!r}, input_tokens={inputs.input_tokens!r}, "
            f"output_tokens={inputs.output_tokens!r}. Missing cost stays missing "
            "rather than being filled in with zeros."
        )
    if (
        cost is not None
        and cost.provenance is CostProvenance.PROVIDER_REPORTED
        and on_stronger_cost == "raise"
    ):
        raise CostNotRepresentableError(
            f"decision {result.decision_id!r} has a provider-reported cost of "
            f"{cost.cost_usd}, which outranks any figure computed from tokens, "
            "but record_decision recomputes cost from its own pricing table and "
            "accepts no dollar figure. Pass on_stronger_cost='reprice' to accept "
            "the table estimate, knowing it is the weaker source."
        )

    record_decision(
        name=result.evaluation_name,
        model=inputs.model,
        # `chosen` is never a payload here. The verdict is already decided, and
        # these two are only what the replay checker below compares, so a stray
        # default checker still reaches the same answer instead of a wrong one.
        chosen=result.reason.value,
        correct=ReasonCode.MATCH.value,
        checker=_replay(result),
        input_tokens=inputs.input_tokens,
        output_tokens=inputs.output_tokens,
        decision_type=bundle.decision.decision_type,
        response_id=redact(inputs.response_id),
        explanation=_explanation(result),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )


def capture_pending_decision(bundle: DecisionEvidenceBundle) -> DecisionRef:
    """Capture the active decision span so a later outcome can grade it.

    Call inside the decision's own flow. The provider response id comes from the
    bundle's correlation block; gradebook fails loud when it is missing, which is
    the right time to find out, because a reality grade with no correlation key
    is an unattributable claim.
    """
    correlation = bundle.correlation
    return capture_decision(
        response_id=correlation.provider_response_id if correlation else None
    )


def emit_reality_outcome(
    ref: DecisionRef,
    outcome: OutcomeRecord,
    *,
    evaluation_name: str,
    decision_type: Optional[str] = None,
    cost: Optional[DecisionCost] = None,
    model: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
) -> None:
    """Record a later real-world result as a reality grade.

    This is the one path where a stronger cost survives intact: unlike
    `record_decision`, `record_reality_grade` accepts a dollar figure directly,
    so a provider-reported cost is emitted as measured rather than re-estimated.
    """
    record_reality_grade(
        ref,
        name=evaluation_name,
        correct=outcome.correct,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=None if cost is None else cost.cost_usd,
        decision_type=decision_type,
        explanation=_truncate(redact(outcome.explanation)),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )


def _replay(result: EvaluationResult) -> Callable[[Any, Any], CheckResult]:
    """Hand `record_decision` the verdict that was already reached.

    Not a re-grade. The evaluator is the authority and this only carries its
    answer, including the reason sub-code, into the event.
    """
    decided = CheckResult(result.passed, result.reason)

    def checker(chosen: Any, correct: Any) -> CheckResult:
        return decided

    return checker


def _explanation(result: EvaluationResult) -> Optional[str]:
    """A human-readable reason, built from the evaluator and never the payload."""
    return _truncate(redact(f"{result.evaluator_kind}: {result.detail}"))


def _truncate(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= _MAX_EXPLANATION:
        return text
    return text[: _MAX_EXPLANATION - 3] + "..."
