from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viewer"))

from observability import (
    CorrelationError,
    build_replay_observability,
    correlate_signoz,
    coverage_for,
    load_sidecar,
    stable_hex_id,
)


AGENT = {
    "response_id": "resp-1",
    "model": "anthropic/claude-haiku-4.5",
    "decision_type": "route_choice",
    "query_id": "route_choice-J1-J2",
    "chosen": "B",
    "is_correct": False,
    "chosen_path": ["J1", "J3", "J2"],
    "cost_usd": 0.00042,
    "input_tokens": 150,
    "output_tokens": 8,
    "outcome": {
        "graded_response_id": "resp-1",
        "on_time": False,
    },
}

CONFIG = {
    "signoz_origin": "http://localhost:8080",
    "dashboard_path": "/dashboard/gradebook",
    "synchronized_at": "2026-07-26T12:00:00Z",
}


def evaluation_span(
    response_id: str,
    *,
    trace_id: str = "a" * 32,
    span_id: str = "b" * 16,
    timestamp: str = "1785001000000000000",
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": "c" * 16,
        "name": "gen_ai.evaluation.result",
        "timestamp": timestamp,
        "duration_nano": "2000000",
        "status_code": "STATUS_CODE_OK",
        "service.name": "toy-world",
        "gen_ai.response.id": response_id,
        "gen_ai.request.model": "anthropic/claude-haiku-4.5",
        "gen_ai.evaluation.score.label": "correct",
        "augmentloop.grade.source": "math",
        "augmentloop.grade.reason": "matched",
        "augmentloop.cost.usd": 0.00042,
    }


def operation_span(
    *,
    trace_id: str = "a" * 32,
    span_id: str = "c" * 16,
    timestamp: str = "1785000999000000000",
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": None,
        "name": "gen_ai.model.request",
        "timestamp": timestamp,
        "duration_nano": "1000000",
        "status_code": "STATUS_CODE_OK",
        "service.name": "toy-world",
        "gen_ai.response.id": "resp-1",
        "gen_ai.request.model": "anthropic/claude-haiku-4.5",
    }


def log_row(
    *,
    trace_id: str = "a" * 32,
    span_id: str = "b" * 16,
    timestamp: str = "1785001001000000000",
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "severity_text": "INFO",
        "body": "grade resolved",
        "trace_id": trace_id,
        "span_id": span_id,
        "service.name": "toy-world",
        "augmentloop.failure.class": None,
    }


class ReplayObservabilityTests(unittest.TestCase):
    def test_replay_projection_is_deterministic_and_labelled(self) -> None:
        """Changing replay ordering, source, or IDs must be caught."""
        first = build_replay_observability(AGENT)
        second = build_replay_observability(AGENT)

        self.assertEqual(first, second)
        self.assertEqual(first["mode"], "replay")
        self.assertIsNone(first["trace_id"])
        self.assertEqual(
            [span["name"] for span in first["spans"]],
            [
                "gen_ai.model.request",
                "toyworld.route.decision",
                "gen_ai.evaluation.result",
                "toyworld.reality.outcome",
            ],
        )
        self.assertEqual({span["source"] for span in first["spans"]}, {"replay"})

    def test_replay_projection_has_no_outcome_span_without_outcome(self) -> None:
        """A missing deferred outcome must not look like completed evidence."""
        result = build_replay_observability({**AGENT, "outcome": None})

        self.assertNotIn(
            "toyworld.reality.outcome", {span["name"] for span in result["spans"]}
        )
        self.assertEqual(len(result["logs"]), 3)
        self.assertNotIn(
            stable_hex_id("resp-1", "outcome", 16),
            {log["span_id"] for log in result["logs"]},
        )

    def test_replay_projection_emits_ordered_structured_fact_logs(self) -> None:
        """Removing or misattributing any replay fact log must fail this contract."""
        result = build_replay_observability(AGENT)

        self.assertEqual(
            result["logs"],
            [
                {
                    "timestamp_unix_nano": "0",
                    "severity": "INFO",
                    "body": "Model request: anthropic/claude-haiku-4.5",
                    "source": "replay",
                    "trace_id": None,
                    "span_id": stable_hex_id("resp-1", "request", 16),
                    "attributes": {
                        "gen_ai.response.id": "resp-1",
                        "gen_ai.request.model": "anthropic/claude-haiku-4.5",
                    },
                },
                {
                    "timestamp_unix_nano": "1000000",
                    "severity": "INFO",
                    "body": "Chosen route_choice decision: B",
                    "source": "replay",
                    "trace_id": None,
                    "span_id": stable_hex_id("resp-1", "decision", 16),
                    "attributes": {
                        "gen_ai.response.id": "resp-1",
                        "augmentloop.decision.type": "route_choice",
                    },
                },
                {
                    "timestamp_unix_nano": "2000000",
                    "severity": "INFO",
                    "body": "Math grade: incorrect",
                    "source": "replay",
                    "trace_id": None,
                    "span_id": stable_hex_id("resp-1", "grade", 16),
                    "attributes": {
                        "gen_ai.response.id": "resp-1",
                        "gen_ai.evaluation.score.label": "incorrect",
                        "augmentloop.grade.source": "math",
                    },
                },
                {
                    "timestamp_unix_nano": "3000000",
                    "severity": "INFO",
                    "body": "Reality outcome: late",
                    "source": "replay",
                    "trace_id": None,
                    "span_id": stable_hex_id("resp-1", "outcome", 16),
                    "attributes": {
                        "gen_ai.response.id": "resp-1",
                        "augmentloop.grade.source": "reality",
                        "journey.on_time": False,
                    },
                },
            ],
        )

    def test_grade_span_records_math_grade_and_cost(self) -> None:
        """A wrong grade label, source, cost, or parent must fail this contract."""
        result = build_replay_observability(AGENT)
        grade = result["spans"][2]

        self.assertEqual(
            grade,
            {
                "span_id": stable_hex_id("resp-1", "grade", 16),
                "parent_span_id": stable_hex_id("resp-1", "decision", 16),
                "trace_id": None,
                "name": "gen_ai.evaluation.result",
                "service_name": "toy-world",
                "start_time_unix_nano": "2000000",
                "duration_ms": 0.0,
                "status": "ok",
                "source": "replay",
                "attributes": {
                    "gen_ai.response.id": "resp-1",
                    "gen_ai.request.model": "anthropic/claude-haiku-4.5",
                    "gen_ai.evaluation.score.label": "incorrect",
                    "augmentloop.grade.source": "math",
                    "augmentloop.cost.usd": 0.00042,
                },
                "linked_span_ids": [],
            },
        )

    def test_stable_hex_id_is_sha256_prefix(self) -> None:
        """Changing the hash scope or truncation must fail this stable-ID contract."""
        self.assertEqual(stable_hex_id("resp-1", "grade", 16), "d4d4ed6aa07f80bf")

    def test_coverage_requires_valid_synchronized_correlation(self) -> None:
        """A replay entry or malformed SigNoz IDs must not count as connected."""
        entries = [
            {"mode": "replay", "trace_id": None, "evaluation_span_id": None},
            {
                "mode": "signoz",
                "trace_id": "a" * 32,
                "evaluation_span_id": "b" * 16,
            },
            {
                "mode": "signoz",
                "trace_id": "not-a-trace-id",
                "evaluation_span_id": "c" * 16,
            },
        ]

        self.assertEqual(coverage_for(entries), {"kind": "partial", "matched": 1, "total": 3})


class SigNozCorrelationTests(unittest.TestCase):
    def test_load_sidecar_returns_valid_versioned_document(self) -> None:
        """Reading must preserve the sidecar envelope consumed by export."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sidecar.json"
            path.write_text(
                '{"schema_version":1,"entries":{},"coverage":{"matched":0,"total":2}}',
                encoding="utf-8",
            )

            self.assertEqual(
                load_sidecar(path),
                {
                    "schema_version": 1,
                    "entries": {},
                    "coverage": {"matched": 0, "total": 2},
                },
            )

    def test_correlation_joins_by_response_id_and_attaches_logs(self) -> None:
        """Dropping the response join, same-trace spans, or logs must fail."""
        sidecar = correlate_signoz(
            spans=[evaluation_span("resp-1")],
            trace_spans=[operation_span()],
            logs=[log_row()],
            response_ids={"resp-1", "resp-2"},
            config=CONFIG,
        )

        entry = sidecar["entries"]["resp-1"]
        self.assertEqual(entry["mode"], "signoz")
        self.assertEqual(entry["trace_id"], "a" * 32)
        self.assertEqual(
            [span["name"] for span in entry["spans"]],
            ["gen_ai.model.request", "gen_ai.evaluation.result"],
        )
        self.assertEqual(len(entry["logs"]), 1)
        self.assertEqual(
            sidecar["coverage"],
            {"matched": 1, "total": 2},
        )

    def test_duplicate_math_evaluation_is_rejected(self) -> None:
        """Choosing one of two authoritative math grades would hide ambiguity."""
        duplicated = evaluation_span("resp-1"), evaluation_span("resp-1")

        with self.assertRaisesRegex(CorrelationError, "duplicate math evaluation"):
            correlate_signoz(duplicated, [], [], {"resp-1"}, CONFIG)

    def test_identifiers_are_validated_before_navigation_and_normalized(self) -> None:
        """Uppercase valid IDs must normalize; malformed IDs must never form links."""
        sidecar = correlate_signoz(
            spans=[
                evaluation_span(
                    "resp-1",
                    trace_id="A" * 32,
                    span_id="B" * 16,
                )
            ],
            trace_spans=[
                operation_span(
                    trace_id="A" * 32,
                    span_id="C" * 16,
                )
            ],
            logs=[
                log_row(
                    trace_id="A" * 32,
                    span_id="B" * 16,
                )
            ],
            response_ids={"resp-1"},
            config=CONFIG,
        )

        entry = sidecar["entries"]["resp-1"]
        self.assertEqual(entry["trace_id"], "a" * 32)
        self.assertEqual(entry["evaluation_span_id"], "b" * 16)
        self.assertTrue(entry["links"]["trace"].endswith("/trace/" + "a" * 32))
        self.assertIn("a" * 32, entry["links"]["logs"])
        self.assertEqual(
            {span["span_id"] for span in entry["spans"]},
            {"b" * 16, "c" * 16},
        )

        with self.assertRaisesRegex(CorrelationError, "malformed trace ID"):
            correlate_signoz(
                [evaluation_span("resp-1", trace_id="../not-a-trace")],
                [],
                [],
                {"resp-1"},
                CONFIG,
            )

    def test_log_cannot_claim_a_span_from_another_trace(self) -> None:
        """A conflicting log trace/span association must not be silently attached."""
        with self.assertRaisesRegex(CorrelationError, "conflicting trace/span"):
            correlate_signoz(
                [evaluation_span("resp-1")],
                [
                    operation_span(
                        trace_id="d" * 32,
                        span_id="c" * 16,
                    )
                ],
                [
                    log_row(
                        trace_id="a" * 32,
                        span_id="c" * 16,
                    )
                ],
                {"resp-1"},
                CONFIG,
            )


if __name__ == "__main__":
    unittest.main()
