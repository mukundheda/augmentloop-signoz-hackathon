from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viewer"))

from signoz_client import SigNozClient, SigNozResponseError, normalize_raw_rows
from sync_signoz import (
    SecretLeakError,
    build_parser,
    resolve_time_range,
    synchronize,
)


class RecordingTransport:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[object] = []

    def __call__(self, request: object) -> object:
        self.requests.append(request)
        return self.response


def evaluation_row(reason: str = "matched") -> dict[str, object]:
    return {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": "c" * 16,
        "name": "gen_ai.evaluation.result",
        "timestamp": "1785001000000000000",
        "duration_nano": "2000000",
        "status_code": "STATUS_CODE_OK",
        "service.name": "toy-world",
        "gen_ai.response.id": "resp-1",
        "gen_ai.request.model": "anthropic/claude-haiku-4.5",
        "gen_ai.evaluation.score.label": "correct",
        "augmentloop.grade.source": "math",
        "augmentloop.grade.reason": reason,
        "augmentloop.cost.usd": 0.00042,
    }


class StubClient:
    def __init__(self, reason: str = "matched") -> None:
        self.reason = reason
        self.trace_ids: list[str] = []

    def query_evaluation_spans(
        self, start_ms: int, end_ms: int
    ) -> list[dict[str, object]]:
        return [evaluation_row(self.reason)]

    def query_trace_spans(
        self, trace_ids: list[str], start_ms: int, end_ms: int
    ) -> list[dict[str, object]]:
        self.trace_ids = trace_ids
        return []

    def query_logs(
        self, trace_ids: list[str], start_ms: int, end_ms: int
    ) -> list[dict[str, object]]:
        return []


class SigNozClientTests(unittest.TestCase):
    def test_evaluation_query_uses_v5_raw_trace_api(self) -> None:
        """A query against the legacy endpoint or wrong signal must fail."""
        transport = RecordingTransport({"data": {"result": []}})
        client = SigNozClient("http://localhost:8080", "secret", transport)

        client.query_evaluation_spans(1000, 2000)

        request = transport.requests[0]
        self.assertEqual(request.url, "http://localhost:8080/api/v5/query_range")
        self.assertEqual(request.headers["SIGNOZ-API-KEY"], "secret")
        self.assertEqual(request.body["requestType"], "raw")
        spec = request.body["compositeQuery"]["queries"][0]["spec"]
        self.assertEqual(spec["signal"], "traces")
        self.assertIn("name = 'gen_ai.evaluation.result'", spec["filter"]["expression"])
        self.assertIn(
            "service.name IN ('toy-world','toy-world-outcomes')",
            spec["filter"]["expression"],
        )

    def test_trace_query_filters_the_requested_trace_ids(self) -> None:
        """A missing trace-ID constraint could correlate unrelated spans."""
        transport = RecordingTransport({"data": {"result": []}})
        client = SigNozClient("http://localhost:8080", "secret", transport)

        client.query_trace_spans(["a" * 32, "b" * 32], 1000, 2000)

        spec = transport.requests[0].body["compositeQuery"]["queries"][0]["spec"]
        self.assertEqual(spec["signal"], "traces")
        self.assertEqual(
            spec["filter"]["expression"],
            "trace_id IN ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')",
        )
        self.assertEqual(
            spec["selectFields"],
            [
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
            ],
        )

    def test_log_query_filters_by_trace_ids(self) -> None:
        """A log query without the ID filter could return another trace's failure."""
        transport = RecordingTransport({"data": {"result": []}})
        client = SigNozClient("http://localhost:8080", "secret", transport)

        client.query_logs(["a" * 32, "b" * 32], 1000, 2000)

        spec = transport.requests[0].body["compositeQuery"]["queries"][0]["spec"]
        self.assertEqual(spec["signal"], "logs")
        self.assertEqual(
            spec["filter"]["expression"],
            "trace_id IN ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')",
        )
        self.assertEqual(
            spec["selectFields"],
            [
                "timestamp",
                "severity_text",
                "body",
                "trace_id",
                "span_id",
                "service.name",
                "augmentloop.failure.class",
            ],
        )

    def test_trace_query_rejects_quoted_operator_injection(self) -> None:
        """An injected quote/operator must not broaden a trace raw-read query."""
        transport = RecordingTransport({"data": {"result": []}})
        client = SigNozClient("http://localhost:8080", "secret", transport)

        with self.assertRaises(ValueError):
            client.query_trace_spans(["a" * 32 + "' OR 1 = 1"], 1000, 2000)

        self.assertEqual(transport.requests, [])

    def test_log_query_rejects_empty_trace_ids(self) -> None:
        """An empty list must not construct an unconstrained log query."""
        transport = RecordingTransport({"data": {"result": []}})
        client = SigNozClient("http://localhost:8080", "secret", transport)

        with self.assertRaises(ValueError):
            client.query_logs([], 1000, 2000)

        self.assertEqual(transport.requests, [])

    def test_normalize_raw_rows_accepts_documented_response_variants(self) -> None:
        """Moving raw result rows between supported envelopes must keep working."""
        row = {"trace_id": "a" * 32}

        self.assertEqual(normalize_raw_rows({"data": {"result": [row]}}), [row])
        self.assertEqual(normalize_raw_rows({"data": {"results": {"A": [row]}}}), [row])
        self.assertEqual(
            normalize_raw_rows({"data": {"newResult": {"data": {"result": [row]}}}}),
            [row],
        )

    def test_unknown_response_shape_does_not_echo_api_key(self) -> None:
        """An upstream shape error must never expose credentials in diagnostics."""
        client = SigNozClient(
            "http://localhost:8080",
            "super-secret",
            RecordingTransport({"unexpected": True}),
        )

        with self.assertRaises(SigNozResponseError) as error:
            client.query_evaluation_spans(1000, 2000)

        self.assertNotIn("super-secret", str(error.exception))


class SigNozSynchronizationTests(unittest.TestCase):
    def test_failed_synchronization_preserves_valid_sidecar_bytes(self) -> None:
        """A transport failure must never truncate the last valid sidecar."""
        original = b'{"schema_version":1,"entries":{}}'

        def failing_transport(request: object) -> object:
            raise OSError("SigNoz unavailable")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sidecar.json"
            output.write_bytes(original)
            client = SigNozClient(
                "http://localhost:8080",
                "super-secret",
                failing_transport,
            )

            with self.assertRaises(OSError):
                synchronize(
                    client=client,
                    response_ids={"resp-1"},
                    config={"signoz_origin": "http://localhost:8080"},
                    start_ms=1000,
                    end_ms=2000,
                    output=output,
                    api_key="super-secret",
                )

            self.assertEqual(output.read_bytes(), original)

    def test_successful_synchronization_atomically_writes_sanitized_sidecar(
        self,
    ) -> None:
        """A successful sync must write evidence only after sanitization."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sidecar.json"
            client = StubClient()

            sidecar = synchronize(
                client=client,
                response_ids={"resp-1", "resp-2"},
                config={
                    "signoz_origin": "http://localhost:8080",
                    "synchronized_at": "2026-07-26T12:00:00Z",
                },
                start_ms=1000,
                end_ms=2000,
                output=output,
                api_key="super-secret",
            )

            self.assertEqual(client.trace_ids, ["a" * 32])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), sidecar)
            self.assertNotIn("super-secret", output.read_text(encoding="utf-8"))
            self.assertFalse(output.with_name(output.name + ".tmp").exists())

    def test_secret_scan_rejects_output_before_replacing_sidecar(self) -> None:
        """An API-key value embedded in returned attributes must block replace."""
        original = b'{"schema_version":1,"entries":{}}'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sidecar.json"
            output.write_bytes(original)

            with self.assertRaises(SecretLeakError):
                synchronize(
                    client=StubClient(reason="super-secret"),
                    response_ids={"resp-1"},
                    config={"signoz_origin": "http://localhost:8080"},
                    start_ms=1000,
                    end_ms=2000,
                    output=output,
                    api_key="super-secret",
                )

            self.assertEqual(output.read_bytes(), original)
            self.assertFalse(output.with_name(output.name + ".tmp").exists())

    def test_cli_time_arguments_are_paired_and_defaults_are_bounded(self) -> None:
        """Unpaired RFC3339 bounds or a non-positive lookback must be rejected."""
        args = build_parser().parse_args([])
        self.assertEqual(args.lookback_minutes, 30)
        self.assertEqual(
            args.output,
            Path(".scratch/viewer-signoz-observability.json"),
        )

        with self.assertRaisesRegex(ValueError, "paired"):
            resolve_time_range("2026-07-26T10:00:00Z", None, 30)
        with self.assertRaisesRegex(ValueError, "positive"):
            resolve_time_range(None, None, 0)

        start_ms, end_ms = resolve_time_range(
            "2026-07-26T10:00:00Z",
            "2026-07-26T10:30:00Z",
            30,
        )
        self.assertEqual(end_ms - start_ms, 30 * 60 * 1000)


if __name__ == "__main__":
    unittest.main()
