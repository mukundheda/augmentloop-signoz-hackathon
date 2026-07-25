from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viewer"))

from observability import build_replay_observability, coverage_for, stable_hex_id


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


if __name__ == "__main__":
    unittest.main()
