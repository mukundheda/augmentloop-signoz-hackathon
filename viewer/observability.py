"""Deterministic observability evidence for committed replay data."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Mapping


_HEX_16 = re.compile(r"^[0-9a-f]{16}$")
_HEX_32 = re.compile(r"^[0-9a-f]{32}$")


def stable_hex_id(response_id: str, label: str, length: int) -> str:
    """Return a replay-stable hexadecimal identifier scoped to one response."""
    return hashlib.sha256(f"{response_id}:{label}".encode()).hexdigest()[:length]


def _span(
    response_id: str,
    label: str,
    *,
    parent_label: str | None,
    name: str,
    service_name: str,
    start_time_unix_nano: str,
    attributes: Mapping[str, Any],
    linked_span_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "span_id": stable_hex_id(response_id, label, 16),
        "parent_span_id": (
            stable_hex_id(response_id, parent_label, 16)
            if parent_label is not None
            else None
        ),
        "trace_id": None,
        "name": name,
        "service_name": service_name,
        "start_time_unix_nano": start_time_unix_nano,
        "duration_ms": 0.0,
        "status": "ok",
        "source": "replay",
        "attributes": dict(attributes),
        "linked_span_ids": linked_span_ids or [],
    }


def build_replay_observability(agent: Mapping[str, Any]) -> dict[str, Any]:
    """Project committed decision facts into non-navigable replay evidence."""
    response_id = str(agent["response_id"])
    model = agent["model"]
    decision_id = stable_hex_id(response_id, "decision", 16)
    spans = [
        _span(
            response_id,
            "request",
            parent_label=None,
            name="gen_ai.model.request",
            service_name="toy-world",
            start_time_unix_nano="0",
            attributes={
                "gen_ai.response.id": response_id,
                "gen_ai.request.model": model,
                "gen_ai.usage.input_tokens": agent["input_tokens"],
                "gen_ai.usage.output_tokens": agent["output_tokens"],
            },
        ),
        _span(
            response_id,
            "decision",
            parent_label="request",
            name="toyworld.route.decision",
            service_name="toy-world",
            start_time_unix_nano="1000000",
            attributes={
                "gen_ai.response.id": response_id,
                "gen_ai.request.model": model,
                "augmentloop.decision.type": agent["decision_type"],
                "augmentloop.query.id": agent["query_id"],
                "augmentloop.decision.chosen": str(agent["chosen"]),
            },
        ),
        _span(
            response_id,
            "grade",
            parent_label="decision",
            name="gen_ai.evaluation.result",
            service_name="toy-world",
            start_time_unix_nano="2000000",
            attributes={
                "gen_ai.response.id": response_id,
                "gen_ai.request.model": model,
                "gen_ai.evaluation.score.label": (
                    "correct" if agent["is_correct"] else "incorrect"
                ),
                "augmentloop.grade.source": "math",
                "augmentloop.cost.usd": agent["cost_usd"],
            },
        ),
    ]
    if agent.get("outcome") is not None:
        outcome = agent["outcome"]
        spans.append(
            _span(
                response_id,
                "outcome",
                parent_label=None,
                name="toyworld.reality.outcome",
                service_name="toy-world-outcomes",
                start_time_unix_nano="3000000",
                attributes={
                    "gen_ai.response.id": response_id,
                    "gen_ai.request.model": model,
                    "augmentloop.grade.source": "reality",
                    "journey.on_time": bool(outcome["on_time"]),
                },
                linked_span_ids=[decision_id],
            )
        )

    return {
        "mode": "replay",
        "response_id": response_id,
        "service_name": "toy-world",
        "trace_id": None,
        "evaluation_span_id": stable_hex_id(response_id, "grade", 16),
        "synchronized_at": None,
        "spans": spans,
        "logs": [],
        "links": {"dashboard": ""},
    }


def coverage_for(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize only evidence eligible for exact SigNoz navigation."""
    values = list(entries)
    matched = sum(
        entry.get("mode") == "signoz"
        and isinstance(entry.get("trace_id"), str)
        and _HEX_32.fullmatch(entry["trace_id"]) is not None
        and isinstance(entry.get("evaluation_span_id"), str)
        and _HEX_16.fullmatch(entry["evaluation_span_id"]) is not None
        for entry in values
    )
    total = len(values)
    if matched == 0:
        kind = "offline"
    elif matched == total:
        kind = "connected"
    else:
        kind = "partial"
    return {"kind": kind, "matched": matched, "total": total}
