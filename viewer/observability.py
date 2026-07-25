"""Deterministic observability evidence for committed replay data."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit


_HEX_16 = re.compile(r"^[0-9a-f]{16}$")
_HEX_32 = re.compile(r"^[0-9a-f]{32}$")
_HEX_16_MIXED = re.compile(r"[0-9a-fA-F]{16}")
_HEX_32_MIXED = re.compile(r"[0-9a-fA-F]{32}")
_DIGITS = re.compile(r"\d+")

_SPAN_ATTRIBUTE_FIELDS = (
    "gen_ai.response.id",
    "gen_ai.request.model",
    "gen_ai.evaluation.score.label",
    "augmentloop.grade.source",
    "augmentloop.grade.reason",
    "augmentloop.cost.usd",
)
_LOG_ATTRIBUTE_FIELDS = (
    "service.name",
    "augmentloop.failure.class",
)


class CorrelationError(ValueError):
    """Raised when SigNoz evidence cannot be correlated unambiguously."""


def load_sidecar(path: Path) -> dict[str, Any]:
    """Load a version-1 synchronized sidecar, or an empty one when absent."""
    if not path.exists():
        return {
            "schema_version": 1,
            "entries": {},
            "coverage": {"matched": 0, "total": 0},
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CorrelationError("invalid SigNoz observability sidecar") from error
    if (
        not isinstance(value, Mapping)
        or value.get("schema_version") != 1
        or not isinstance(value.get("entries"), Mapping)
    ):
        raise CorrelationError("invalid SigNoz observability sidecar")
    return dict(value)


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


def _replay_log(
    response_id: str,
    label: str,
    *,
    timestamp_unix_nano: str,
    body: str,
    attributes: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic replay log linked to its projected span."""
    return {
        "timestamp_unix_nano": timestamp_unix_nano,
        "severity": "INFO",
        "body": body,
        "source": "replay",
        "trace_id": None,
        "span_id": stable_hex_id(response_id, label, 16),
        "attributes": dict(attributes),
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

    grade_label = "correct" if agent["is_correct"] else "incorrect"
    logs = [
        _replay_log(
            response_id,
            "request",
            timestamp_unix_nano="0",
            body=f"Model request: {model}",
            attributes={
                "gen_ai.response.id": response_id,
                "gen_ai.request.model": model,
            },
        ),
        _replay_log(
            response_id,
            "decision",
            timestamp_unix_nano="1000000",
            body=(
                f"Chosen {agent['decision_type']} decision: {agent['chosen']}"
            ),
            attributes={
                "gen_ai.response.id": response_id,
                "augmentloop.decision.type": agent["decision_type"],
            },
        ),
        _replay_log(
            response_id,
            "grade",
            timestamp_unix_nano="2000000",
            body=f"Math grade: {grade_label}",
            attributes={
                "gen_ai.response.id": response_id,
                "gen_ai.evaluation.score.label": grade_label,
                "augmentloop.grade.source": "math",
            },
        ),
    ]
    if agent.get("outcome") is not None:
        on_time = bool(agent["outcome"]["on_time"])
        logs.append(
            _replay_log(
                response_id,
                "outcome",
                timestamp_unix_nano="3000000",
                body=f"Reality outcome: {'on time' if on_time else 'late'}",
                attributes={
                    "gen_ai.response.id": response_id,
                    "augmentloop.grade.source": "reality",
                    "journey.on_time": on_time,
                },
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
        "logs": logs,
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


def _canonical_identifier(value: object, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise CorrelationError(f"malformed {label} ID in SigNoz evidence")
    return value.lower()


def _optional_span_id(value: object) -> str | None:
    if value in (None, ""):
        return None
    return _canonical_identifier(value, _HEX_16_MIXED, "span")


def _timestamp(value: object) -> str:
    text = str(value)
    if _DIGITS.fullmatch(text) is None:
        raise CorrelationError("malformed timestamp in SigNoz evidence")
    return text


def _primitive_attributes(
    row: Mapping[str, Any], fields: Iterable[str]
) -> dict[str, str | int | float | bool]:
    attributes: dict[str, str | int | float | bool] = {}
    for field in fields:
        value = row.get(field)
        if value is None or not isinstance(value, (str, int, float, bool)):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        attributes[field] = value
    return attributes


def _status(value: object) -> str:
    normalized = str(value or "").upper()
    if normalized in {"2", "ERROR", "STATUS_CODE_ERROR"}:
        return "error"
    if normalized in {"1", "OK", "STATUS_CODE_OK"}:
        return "ok"
    return "unset"


def _normalize_span(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        duration_ms = float(row.get("duration_nano", 0)) / 1_000_000
    except (TypeError, ValueError) as error:
        raise CorrelationError("malformed span duration in SigNoz evidence") from error
    if not math.isfinite(duration_ms):
        raise CorrelationError("malformed span duration in SigNoz evidence")
    return {
        "span_id": _canonical_identifier(row.get("span_id"), _HEX_16_MIXED, "span"),
        "parent_span_id": _optional_span_id(row.get("parent_span_id")),
        "trace_id": _canonical_identifier(
            row.get("trace_id"), _HEX_32_MIXED, "trace"
        ),
        "name": str(row.get("name", "")),
        "service_name": str(row.get("service.name", "")),
        "start_time_unix_nano": _timestamp(row.get("timestamp")),
        "duration_ms": duration_ms,
        "status": _status(row.get("status_code")),
        "source": "signoz",
        "attributes": _primitive_attributes(row, _SPAN_ATTRIBUTE_FIELDS),
        "linked_span_ids": [],
    }


def _normalize_log(
    row: Mapping[str, Any],
    span_traces: Mapping[str, str],
) -> dict[str, Any]:
    trace_id = (
        _canonical_identifier(row.get("trace_id"), _HEX_32_MIXED, "trace")
        if row.get("trace_id") not in (None, "")
        else None
    )
    span_id = _optional_span_id(row.get("span_id"))
    known_trace = span_traces.get(span_id) if span_id is not None else None
    if trace_id is not None and known_trace is not None and trace_id != known_trace:
        raise CorrelationError("log has conflicting trace/span relationship")
    resolved_trace = trace_id or known_trace
    severity = str(row.get("severity_text") or "INFO").upper()
    if severity == "WARNING":
        severity = "WARN"
    if severity not in {"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"}:
        severity = "INFO"
    return {
        "timestamp_unix_nano": _timestamp(row.get("timestamp")),
        "severity": severity,
        "body": str(row.get("body", "")),
        "source": "signoz",
        "trace_id": resolved_trace,
        "span_id": span_id,
        "attributes": _primitive_attributes(row, _LOG_ATTRIBUTE_FIELDS),
    }


def _safe_origin(config: Mapping[str, Any]) -> str | None:
    raw_origin = (
        config.get("signoz_origin") or config.get("origin") or config.get("url")
    )
    if not isinstance(raw_origin, str):
        return None
    parsed = urlsplit(raw_origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _navigation_links(
    config: Mapping[str, Any], trace_id: str
) -> dict[str, str]:
    origin = _safe_origin(config)
    if origin is None:
        return {"dashboard": ""}
    trace_url = f"{origin}/trace/{trace_id}"
    logs_url = f"{origin}/logs?{urlencode({'traceId': trace_id})}"
    dashboard = ""
    dashboard_path = config.get("dashboard_path")
    if isinstance(dashboard_path, str) and dashboard_path:
        dashboard = urljoin(origin + "/", dashboard_path.lstrip("/"))
    return {
        "trace": trace_url,
        "logs": logs_url,
        "dashboard": dashboard,
    }


def _synchronized_at(config: Mapping[str, Any]) -> str:
    value = config.get("synchronized_at")
    if isinstance(value, str) and value:
        return value
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def correlate_signoz(
    spans: Iterable[Mapping[str, Any]],
    trace_spans: Iterable[Mapping[str, Any]],
    logs: Iterable[Mapping[str, Any]],
    response_ids: Iterable[str],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Correlate sanitized SigNoz evidence with committed Gradebook responses."""
    expected_response_ids = {str(response_id) for response_id in response_ids}
    evaluation_rows = [dict(row) for row in spans]
    trace_rows = [dict(row) for row in trace_spans]

    normalized_evaluations = [
        (row, _normalize_span(row)) for row in evaluation_rows
    ]
    normalized_trace_spans = [(row, _normalize_span(row)) for row in trace_rows]

    span_traces: dict[str, str] = {}
    for _, span in [*normalized_evaluations, *normalized_trace_spans]:
        prior_trace = span_traces.setdefault(span["span_id"], span["trace_id"])
        if prior_trace != span["trace_id"]:
            raise CorrelationError("span ID has conflicting trace relationship")

    normalized_logs = [_normalize_log(dict(row), span_traces) for row in logs]

    math_evaluations: dict[str, dict[str, Any]] = {}
    for row, span in normalized_evaluations:
        response_id = row.get("gen_ai.response.id")
        grade_source = row.get("augmentloop.grade.source")
        if grade_source == "reality" and response_id not in expected_response_ids:
            raise CorrelationError("reality grade does not identify a decision")
        if grade_source != "math" or response_id not in expected_response_ids:
            continue
        response_key = str(response_id)
        if response_key in math_evaluations:
            raise CorrelationError(
                f"duplicate math evaluation for response {response_key!r}"
            )
        math_evaluations[response_key] = span

    all_spans = [
        span for _, span in [*normalized_evaluations, *normalized_trace_spans]
    ]
    synchronized_at = _synchronized_at(config)
    entries: dict[str, dict[str, Any]] = {}
    for response_id in sorted(math_evaluations):
        evaluation = math_evaluations[response_id]
        trace_id = evaluation["trace_id"]
        by_span_id: dict[str, dict[str, Any]] = {}
        for span in all_spans:
            if span["trace_id"] == trace_id:
                by_span_id.setdefault(span["span_id"], span)
        correlated_spans = sorted(
            by_span_id.values(),
            key=lambda span: int(span["start_time_unix_nano"]),
        )
        correlated_logs = sorted(
            (
                log
                for log in normalized_logs
                if log.get("trace_id") == trace_id
            ),
            key=lambda log: int(log["timestamp_unix_nano"]),
        )
        entries[response_id] = {
            "mode": "signoz",
            "response_id": response_id,
            "service_name": evaluation["service_name"],
            "trace_id": trace_id,
            "evaluation_span_id": evaluation["span_id"],
            "synchronized_at": synchronized_at,
            "spans": correlated_spans,
            "logs": correlated_logs,
            "links": _navigation_links(config, trace_id),
        }

    return {
        "schema_version": 1,
        "entries": entries,
        "coverage": {
            "matched": len(entries),
            "total": len(expected_response_ids),
        },
    }
