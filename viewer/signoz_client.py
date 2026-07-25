"""Read-only client for SigNoz Query Builder v5 raw queries."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Protocol, Sequence
from urllib import request as urllib_request


TRACE_FIELDS = [
    "trace_id",
    "span_id",
    "parent_span_id",
    "name",
    "timestamp",
    "duration_nano",
    "status_code",
    "service.name",
    "gen_ai.response.id",
    "gen_ai.request.model",
    "gen_ai.evaluation.score.label",
    "augmentloop.grade.source",
    "augmentloop.grade.reason",
    "augmentloop.cost.usd",
]

LOG_FIELDS = [
    "timestamp",
    "severity_text",
    "body",
    "trace_id",
    "span_id",
    "service.name",
    "augmentloop.failure.class",
]

_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


class SigNozResponseError(RuntimeError):
    """Raised when SigNoz returns a response this client cannot normalize."""


@dataclass(frozen=True)
class QueryRequest:
    """A read-only request passed to an injectable SigNoz transport."""

    url: str
    headers: Mapping[str, str]
    body: Mapping[str, Any]


class Transport(Protocol):
    def __call__(self, request: QueryRequest) -> Mapping[str, Any]: ...


def _as_rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise SigNozResponseError("SigNoz returned an unsupported raw response shape.")
    return [dict(row) for row in value]


def normalize_raw_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize the raw-query envelopes supported by the current API contract."""
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise SigNozResponseError("SigNoz returned an unsupported raw response shape.")

    if "result" in data:
        return _as_rows(data["result"])

    results = data.get("results")
    if isinstance(results, Mapping) and "A" in results:
        return _as_rows(results["A"])

    new_result = data.get("newResult")
    if isinstance(new_result, Mapping):
        nested_data = new_result.get("data")
        if isinstance(nested_data, Mapping) and "result" in nested_data:
            return _as_rows(nested_data["result"])

    raise SigNozResponseError("SigNoz returned an unsupported raw response shape.")


class SigNozClient:
    """Authenticated client for the read-only SigNoz raw-query endpoint."""

    def __init__(
        self,
        origin: str,
        api_key: str,
        transport: Transport | None = None,
    ) -> None:
        self._url = f"{origin.rstrip('/')}/api/v5/query_range"
        self._headers = {
            "Content-Type": "application/json",
            "SIGNOZ-API-KEY": api_key,
        }
        self._transport = transport or self._post_json

    def query_evaluation_spans(
        self, start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]:
        """Fetch evaluation spans emitted by the Toy World services."""
        return self._query(
            signal="traces",
            fields=TRACE_FIELDS,
            filter_expression=(
                "name = 'gen_ai.evaluation.result' AND "
                "service.name IN ('toy-world','toy-world-outcomes')"
            ),
            start_ms=start_ms,
            end_ms=end_ms,
        )

    def query_trace_spans(
        self, trace_ids: Sequence[str], start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]:
        """Fetch spans only from the explicitly requested traces."""
        return self._query(
            signal="traces",
            fields=TRACE_FIELDS,
            filter_expression=_trace_id_filter(trace_ids),
            start_ms=start_ms,
            end_ms=end_ms,
        )

    def query_logs(
        self, trace_ids: Sequence[str], start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]:
        """Fetch logs only from the explicitly requested traces."""
        return self._query(
            signal="logs",
            fields=LOG_FIELDS,
            filter_expression=_trace_id_filter(trace_ids),
            start_ms=start_ms,
            end_ms=end_ms,
        )

    def _query(
        self,
        *,
        signal: str,
        fields: Sequence[str],
        filter_expression: str,
        start_ms: int,
        end_ms: int,
    ) -> list[dict[str, Any]]:
        payload = {
            "start": start_ms,
            "end": end_ms,
            "requestType": "raw",
            "compositeQuery": {
                "queries": [
                    {
                        "type": "builder_query",
                        "spec": {
                            "name": "A",
                            "signal": signal,
                            "filter": {"expression": filter_expression},
                            "groupBy": [],
                            "selectFields": list(fields),
                            "aggregations": [],
                            "orderBy": [{"columnName": "timestamp", "order": "desc"}],
                            "limit": 1000,
                            "offset": 0,
                        },
                    }
                ]
            },
        }
        response = self._transport(QueryRequest(self._url, self._headers, payload))
        if not isinstance(response, Mapping):
            raise SigNozResponseError("SigNoz returned an unsupported raw response shape.")
        return normalize_raw_rows(response)

    def _post_json(self, query: QueryRequest) -> Mapping[str, Any]:
        request = urllib_request.Request(
            query.url,
            data=json.dumps(query.body).encode("utf-8"),
            headers=dict(query.headers),
            method="POST",
        )
        try:
            with urllib_request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SigNozResponseError("SigNoz query failed.") from error


def _trace_id_filter(trace_ids: Sequence[str]) -> str:
    if not trace_ids or any(
        not isinstance(trace_id, str) or _TRACE_ID.fullmatch(trace_id) is None
        for trace_id in trace_ids
    ):
        raise ValueError(
            "trace_ids must be a non-empty sequence of canonical 32-hex trace IDs"
        )
    values = ",".join(f"'{trace_id}'" for trace_id in trace_ids)
    return f"trace_id IN ({values})"
