"""Reality grades from an app's existing signal - with no checker (ticket #43).

The sharpest criticism of a portable grading layer is that the portable part is
the easy 20% (the emit wrapper), while the graders - the 80% that makes
"correct" mean anything - are domain-specific and hand-written per decision.
*"Standardizes the shape of a verdict it cannot itself produce."*

This module is the rebuttal, and it is true rather than rhetorical. **Only math
grades need a checker.** A *reality* grade needs a signal the app already emits:
kept vs discarded, edited-then-saved, undo, thumbs-down, retry. The signal *is*
the verdict - there is nothing to compare, so there is no checker to write.

`RealitySignal` wraps that existing signal:

- `observe(key, response_id=...)` at decision time captures the decision span
  (via `capture_decision`) and stores its `DecisionRef` under an app-owned key
  (a clip id, a message id).
- `on_outcome` decorates the app's *existing* outcome handler. When it fires for
  a known key, the handler's own return value becomes the reality grade - mapped
  to correct/incorrect by `positive` (default: plain truthiness). The adopter
  writes no checker.

Cross-process (the decision and its outcome usually live in different
processes - a request handler and a webhook): swap the default in-memory store
for any object with `put`/`pop`, persisting each `DecisionRef` as the three
primitive ids `DecisionRef.from_ids` rebuilds from. `ref_to_ids` /
`ref_from_ids` do that serialization.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Optional, Protocol

from opentelemetry import metrics, trace

from .recorder import DecisionRef, capture_decision, record_reality_grade


class RefStore(Protocol):
    """Where pending `DecisionRef`s live between decision time and outcome time.

    The default is an in-memory dict (same process). For the webhook/cron hop,
    supply a store backed by Redis/DB that serializes each ref via `ref_to_ids`,
    which emits JSON-safe hex ids for the reason given in that function.
    """

    def put(self, key: Any, ref: DecisionRef) -> None: ...
    def pop(self, key: Any) -> Optional[DecisionRef]: ...


class _DictStore:
    """Default same-process store."""

    def __init__(self) -> None:
        self._d: dict[Any, DecisionRef] = {}

    def put(self, key: Any, ref: DecisionRef) -> None:
        self._d[key] = ref

    def pop(self, key: Any) -> Optional[DecisionRef]:
        return self._d.pop(key, None)


def ref_to_ids(ref: DecisionRef) -> dict[str, Any]:
    """Serialize a `DecisionRef` to the three primitives `from_ids` rebuilds from.

    For persisting a pending decision across a process boundary (store the dict,
    rebuild with `ref_from_ids` when the outcome signal arrives elsewhere).

    The ids are emitted as **hex strings**, which is OpenTelemetry's own wire
    format (`032x` for the 128-bit trace id, `016x` for the 64-bit span id), and
    not as raw ints. The store this is written to is usually Redis or a database,
    so the value goes through JSON, and `JSON.parse` holds integers exactly only
    up to 2**53 - 1. A 128-bit trace id serialized as an int comes back out of a
    JavaScript consumer as a *different* trace id, silently, and the reality
    grade's span link then points at a trace that does not exist. That failure is
    invisible from Python, whose ints are arbitrary precision.
    """
    ctx = ref.span_context
    return {
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
        "response_id": ref.response_id,
    }


def ref_from_ids(ids: dict[str, Any]) -> DecisionRef:
    """Inverse of `ref_to_ids`.

    Accepts the hex strings `ref_to_ids` writes, and still accepts raw ints so a
    store already holding the previous format keeps working.
    """
    return DecisionRef.from_ids(
        trace_id=_as_id(ids["trace_id"]),
        span_id=_as_id(ids["span_id"]),
        response_id=ids["response_id"],
    )


def _as_id(value: Any) -> int:
    """Read a trace/span id written as hex (current) or as a raw int (legacy)."""
    return value if isinstance(value, int) else int(value, 16)


class RealitySignal:
    """Bind an app's existing outcome signal to reality grades, no checker."""

    def __init__(
        self,
        name: str,
        *,
        decision_type: Optional[str] = None,
        positive: Callable[[Any], bool] = bool,
        store: Optional[RefStore] = None,
        tracer_provider: Optional[trace.TracerProvider] = None,
        meter_provider: Optional[metrics.MeterProvider] = None,
    ) -> None:
        """
        Args:
            name: `gen_ai.evaluation.name` for the emitted grades (e.g. "clip.kept").
            decision_type: optional `augmentloop.decision.type`.
            positive: maps the app signal's own value to correct/incorrect. The
                default (`bool`) fits signals that are already truthy for the
                good outcome (kept=True, thumbs-up=1) - so the adopter maps
                nothing. This is a per-signal semantic, not a per-decision
                checker: one line for the whole signal, not comparison logic.
            store: pending-ref store; default is in-memory (same process).
            tracer_provider / meter_provider: injectable for tests / wiring.
        """
        self._name = name
        self._decision_type = decision_type
        self._positive = positive
        self._store: RefStore = store or _DictStore()
        self._tracer_provider = tracer_provider
        self._meter_provider = meter_provider

    def use_providers(
        self,
        *,
        tracer_provider: Optional[trace.TracerProvider] = None,
        meter_provider: Optional[metrics.MeterProvider] = None,
    ) -> None:
        """Wire telemetry after construction.

        A module-scope `RealitySignal` (so its `on_outcome` decorator can wrap a
        handler at import) usually can't be handed its providers until `main()`
        has built them. Set them here rather than at construction.
        """
        if tracer_provider is not None:
            self._tracer_provider = tracer_provider
        if meter_provider is not None:
            self._meter_provider = meter_provider

    def observe(self, key: Any, *, response_id: str) -> None:
        """At decision time (model-call span active): remember this decision.

        Call this where the AI makes the decision, under an app-owned key the
        later signal also knows (a clip id, a message id).
        """
        self._store.put(key, capture_decision(response_id=response_id))

    def on_outcome(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorate the app's EXISTING outcome handler.

        The wrapped handler's first positional argument is the decision key; its
        return value is the verdict. When the key is one we `observe`d, a reality
        grade records itself - `record_reality_grade` span-links it back to the
        decision and stamps `grade.source = reality`. The handler runs unchanged
        and its return value is passed through untouched.
        """

        @functools.wraps(fn)
        def wrapper(key: Any, *args: Any, **kwargs: Any) -> Any:
            result = fn(key, *args, **kwargs)
            self.record(key, result)
            return result

        return wrapper

    def record(self, key: Any, signal_value: Any) -> bool:
        """Record a reality grade for `key` from a raw signal value.

        The imperative form of `on_outcome`, for signals that are not a single
        function call (a message-queue consumer, a polled status). Returns True
        if a pending decision matched `key` and a grade was recorded.
        """
        ref = self._store.pop(key)
        if ref is None:
            return False
        record_reality_grade(
            ref,
            name=self._name,
            correct=bool(self._positive(signal_value)),
            decision_type=self._decision_type,
            tracer_provider=self._tracer_provider,
            meter_provider=self._meter_provider,
        )
        return True
