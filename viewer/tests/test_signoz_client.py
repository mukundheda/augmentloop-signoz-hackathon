from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viewer"))

from signoz_client import SigNozClient, SigNozResponseError, normalize_raw_rows


class RecordingTransport:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[object] = []

    def __call__(self, request: object) -> object:
        self.requests.append(request)
        return self.response


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


if __name__ == "__main__":
    unittest.main()
