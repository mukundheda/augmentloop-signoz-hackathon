from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viewer"))
sys.path.insert(0, str(ROOT / "toy-world" / "src"))
sys.path.insert(0, str(ROOT / "reference-library" / "src"))

from export import RECORDING, WORLD, build_run_document, build_world_feature_collection


class ExportTests(unittest.TestCase):
    def test_exports_one_simulation_route_per_world_option(self) -> None:
        document = build_world_feature_collection()
        routes = [
            feature
            for feature in document["features"]
            if feature["properties"]["kind"] == "simulation-route"
        ]
        self.assertEqual(len(routes), 7)
        self.assertEqual(len(routes), sum(len(junction.options) for junction in WORLD))

    def test_fastest_flags_match_the_world_answer_key(self) -> None:
        document = build_world_feature_collection()
        actual = {
            (feature["properties"]["junction"], feature["properties"]["route"]): feature[
                "properties"
            ]["is_fastest"]
            for feature in document["features"]
            if feature["properties"]["kind"] == "simulation-route"
        }
        expected = {
            (junction.name, route): route == junction.true_fastest
            for junction in WORLD
            for route in junction.options
        }
        self.assertEqual(actual, expected)

    def test_run_totals_are_the_hand_checked_recording_totals(self) -> None:
        document = build_run_document(RECORDING)
        self.assertEqual(document["totals"]["decisions"], 12)
        self.assertEqual(document["totals"]["correct"], 8)
        self.assertEqual(document["totals"]["outcomes"], 4)
        self.assertAlmostEqual(document["totals"]["total_cost_usd"], 0.0037354)
        self.assertAlmostEqual(
            document["totals"]["cost_per_correct_usd"], 0.000466925
        )

    def test_every_outcome_targets_an_exported_decision(self) -> None:
        document = build_run_document(RECORDING)
        response_ids = {
            decision["response_id"]
            for driver in document["drivers"]
            for decision in driver["decisions"]
        }
        self.assertTrue(
            all(
                outcome["graded_response_id"] in response_ids
                for outcome in document["outcomes"]
            )
        )

    def test_pune_context_has_required_attribution(self) -> None:
        path = Path(__file__).parents[1] / "public" / "data" / "pune-context.geojson"
        context = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            context["metadata"]["attribution"], "© OpenStreetMap contributors"
        )
        self.assertEqual(
            context["metadata"]["corridor"], "Shivajinagar–Deccan–Swargate"
        )
        self.assertTrue(context["features"])


if __name__ == "__main__":
    unittest.main()
