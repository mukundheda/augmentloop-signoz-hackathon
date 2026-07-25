from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viewer"))

from export import (
    GRAPH,
    RECORDING,
    build_road_mapping,
    build_run_document,
    parse_osm_number,
)


class ExportV2Tests(unittest.TestCase):
    def test_parses_osm_measurements_with_units(self) -> None:
        self.assertEqual(parse_osm_number("23 meters"), 23.0)
        self.assertEqual(parse_osm_number("12.5"), 12.5)
        self.assertEqual(parse_osm_number(None), 0.0)

    def test_maps_every_graph_node_to_a_distinct_road_intersection(self) -> None:
        mapping = build_road_mapping()
        self.assertEqual(set(mapping["nodes"]), set(GRAPH))
        coordinates = {
            tuple(node["coordinate"]) for node in mapping["nodes"].values()
        }
        self.assertEqual(len(coordinates), 20)

    def test_exports_every_recorded_decision_once(self) -> None:
        run = build_run_document(RECORDING)
        decision_lines = sum(
            1
            for line in RECORDING.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["type"] == "decision"
        )
        self.assertEqual(decision_lines, 180)
        self.assertEqual(len(run["agents"]), decision_lines)
        self.assertEqual(
            len({agent["response_id"] for agent in run["agents"]}), decision_lines
        )

    def test_exports_all_three_decision_types(self) -> None:
        run = build_run_document(RECORDING)
        self.assertEqual(
            {agent["decision_type"] for agent in run["agents"]},
            {"route_choice", "eta_estimate", "next_hop"},
        )

    def test_every_toy_edge_has_a_road_polyline(self) -> None:
        mapping = build_road_mapping()
        expected = {
            f"{start}->{edge.to}"
            for start, node in GRAPH.items()
            for edge in node.edges
        }
        self.assertEqual(set(mapping["edges"]), expected)
        self.assertTrue(
            all(len(edge["polyline"]) >= 2 for edge in mapping["edges"].values())
        )

    def test_every_agent_path_stays_on_exported_road_coordinates(self) -> None:
        mapping = build_road_mapping()
        road_points = {
            tuple(point)
            for edge in mapping["edges"].values()
            for point in edge["polyline"]
        }
        run = build_run_document(RECORDING)
        self.assertTrue(
            all(
                tuple(point) in road_points
                for agent in run["agents"]
                for point in agent["chosen_polyline"]
            )
        )

    def test_outcomes_resolve_to_route_choice_agents(self) -> None:
        run = build_run_document(RECORDING)
        by_response = {agent["response_id"]: agent for agent in run["agents"]}
        self.assertTrue(run["outcomes"])
        self.assertTrue(
            all(
                outcome["graded_response_id"] in by_response
                and by_response[outcome["graded_response_id"]]["decision_type"]
                == "route_choice"
                for outcome in run["outcomes"]
            )
        )


if __name__ == "__main__":
    unittest.main()
