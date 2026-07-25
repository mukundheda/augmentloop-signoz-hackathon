"""Synchronize sanitized SigNoz evidence into an atomic viewer sidecar."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Protocol, Sequence

from observability import CorrelationError, correlate_signoz
from signoz_client import SigNozClient


ROOT = Path(__file__).resolve().parents[1]
RECORDING = ROOT / "toy-world" / "recordings" / "replay-v1.jsonl"
DEFAULT_OUTPUT = Path(".scratch/viewer-signoz-observability.json")
_TRACE_ID = re.compile(r"[0-9a-fA-F]{32}")
_SECRET_FIELD = re.compile(
    r'"(?:authorization|api[_-]?key|signoz-api-key|cookie|set-cookie|'
    r'password|secret|access[_-]?token|refresh[_-]?token)"\s*:',
    re.IGNORECASE,
)


class QueryClient(Protocol):
    def query_evaluation_spans(
        self, start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]: ...

    def query_trace_spans(
        self, trace_ids: Sequence[str], start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]: ...

    def query_logs(
        self, trace_ids: Sequence[str], start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]: ...


class SecretLeakError(RuntimeError):
    """Raised before replacement when serialized evidence contains a secret."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize Gradebook-correlated SigNoz evidence."
    )
    parser.add_argument("--lookback-minutes", type=int, default=30)
    parser.add_argument("--from", dest="from_time")
    parser.add_argument("--to", dest="to_time")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dashboard-path")
    return parser


def _parse_rfc3339(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid RFC3339 timestamp: {value!r}") from error
    if parsed.tzinfo is None:
        raise ValueError("RFC3339 timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def resolve_time_range(
    from_value: str | None,
    to_value: str | None,
    lookback_minutes: int,
    *,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Resolve paired RFC3339 bounds or a positive rolling lookback."""
    if (from_value is None) != (to_value is None):
        raise ValueError("--from and --to must be paired")
    if from_value is not None and to_value is not None:
        start = _parse_rfc3339(from_value)
        end = _parse_rfc3339(to_value)
    else:
        if lookback_minutes <= 0:
            raise ValueError("--lookback-minutes must be positive")
        end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        start = end - timedelta(minutes=lookback_minutes)
    if start >= end:
        raise ValueError("synchronization start must precede end")
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def load_response_ids(path: Path = RECORDING) -> set[str]:
    """Load the authoritative decision response IDs from the committed recording."""
    response_ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("type") != "decision":
            continue
        response_id = row.get("response_id")
        if not isinstance(response_id, str) or not response_id:
            raise CorrelationError("recording contains a decision without response_id")
        if response_id in response_ids:
            raise CorrelationError(f"recording contains duplicate {response_id!r}")
        response_ids.add(response_id)
    return response_ids


def _trace_ids(spans: Iterable[Mapping[str, Any]]) -> list[str]:
    trace_ids: set[str] = set()
    for span in spans:
        value = span.get("trace_id")
        if not isinstance(value, str) or _TRACE_ID.fullmatch(value) is None:
            raise CorrelationError("malformed trace ID in SigNoz evidence")
        trace_ids.add(value.lower())
    return sorted(trace_ids)


def _assert_no_secrets(serialized: str, api_key: str) -> None:
    if _SECRET_FIELD.search(serialized) is not None:
        raise SecretLeakError("sanitized sidecar contains a secret-bearing field")
    if api_key and api_key in serialized:
        raise SecretLeakError("sanitized sidecar contains the configured API key")


def write_sidecar_atomic(
    output: Path,
    sidecar: Mapping[str, Any],
    *,
    api_key: str,
) -> None:
    """Flush a sibling temporary file and replace only after secret scanning."""
    serialized = json.dumps(
        sidecar,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.write("\n")
            handle.flush()
        _assert_no_secrets(serialized, api_key)
        temporary.replace(output)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def synchronize(
    *,
    client: QueryClient,
    response_ids: Iterable[str],
    config: Mapping[str, Any],
    start_ms: int,
    end_ms: int,
    output: Path,
    api_key: str,
) -> dict[str, Any]:
    """Query, correlate, sanitize, and atomically persist SigNoz evidence."""
    evaluations = client.query_evaluation_spans(start_ms, end_ms)
    trace_ids = _trace_ids(evaluations)
    if trace_ids:
        trace_spans = client.query_trace_spans(trace_ids, start_ms, end_ms)
        logs = client.query_logs(trace_ids, start_ms, end_ms)
    else:
        trace_spans = []
        logs = []
    sidecar = correlate_signoz(
        evaluations,
        trace_spans,
        logs,
        response_ids,
        config,
    )
    write_sidecar_atomic(output, sidecar, api_key=api_key)
    return sidecar


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        start_ms, end_ms = resolve_time_range(
            args.from_time,
            args.to_time,
            args.lookback_minutes,
        )
    except ValueError as error:
        parser.error(str(error))

    environment = environ or os.environ
    api_key = environment.get("SIGNOZ_API_KEY", "")
    if not api_key:
        parser.error("SIGNOZ_API_KEY is required")
    origin = environment.get("SIGNOZ_URL", "http://localhost:8080")
    config = {
        "signoz_origin": origin,
        "dashboard_path": args.dashboard_path,
        "synchronized_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    response_ids = load_response_ids()
    sidecar = synchronize(
        client=SigNozClient(origin, api_key),
        response_ids=response_ids,
        config=config,
        start_ms=start_ms,
        end_ms=end_ms,
        output=args.output,
        api_key=api_key,
    )
    matched = sidecar["coverage"]["matched"]
    total = sidecar["coverage"]["total"]
    unmatched = sorted(response_ids - set(sidecar["entries"]))
    print(f"SigNoz observability coverage: {matched}/{total}")
    if unmatched:
        print("Unmatched response IDs: " + ", ".join(unmatched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
