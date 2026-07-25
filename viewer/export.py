"""Export the current 20-junction toy world onto real Pune road geometry."""

from __future__ import annotations

import heapq
import importlib.util
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "viewer" / "public" / "data"
RECORDING = ROOT / "toy-world" / "recordings" / "replay-v2.jsonl"
OSM_SOURCE = ROOT / ".scratch" / "osm-pune-source.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


WORLD_MODULE = _load_module(
    "viewer_toyworld_world", ROOT / "toy-world" / "src" / "toyworld" / "world.py"
)
PRICING_MODULE = _load_module(
    "viewer_gradebook_pricing",
    ROOT / "reference-library" / "src" / "gradebook" / "pricing.py",
)

GRAPH = WORLD_MODULE.GRAPH
QUERIES_BY_ID = WORLD_MODULE.QUERIES_BY_ID
shortest_path = WORLD_MODULE.shortest_path
second_best_path = WORLD_MODULE.second_best_path
price = PRICING_MODULE.price

HIGHWAY_WIDTHS = {
    "motorway": 0.20,
    "trunk": 0.18,
    "primary": 0.16,
    "secondary": 0.14,
    "tertiary": 0.12,
    "residential": 0.085,
    "living_street": 0.075,
    "service": 0.055,
    "unclassified": 0.07,
}
# One hue per roster model, chosen to stay apart from the scene's three semantic
# colours: green resolves a correct route, red a wrong one, yellow trails the
# optimal alternative. A model with no entry here falls back to amber, which
# collides with that yellow ghost, so every roster model needs a real hue.
# Ordered cheapest to most expensive, matching live.DEFAULT_ROSTER.
MODEL_COLORS = {
    "mistralai/mistral-small-24b-instruct-2501": "#c6f24d",
    "google/gemini-2.5-flash-lite": "#66f0a9",
    "meta-llama/llama-3.3-70b-instruct": "#ffa14d",
    "openai/gpt-4o-mini": "#ff7ae0",
    "deepseek/deepseek-chat": "#5b8cff",
    "anthropic/claude-haiku-4.5": "#55d7ff",
    "anthropic/claude-sonnet-4.6": "#a88bff",
}
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def parse_osm_number(value: object) -> float:
    """Parse the leading numeric quantity from permissive OSM tag values."""
    if value is None:
        return 0.0
    match = _NUMBER.search(str(value))
    return float(match.group(0)) if match else 0.0


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon_scale = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * lon_scale, a[1] - b[1])


def _osm() -> dict[str, Any]:
    if not OSM_SOURCE.exists():
        raise FileNotFoundError(
            f"{OSM_SOURCE} is missing; fetch the bounded central-Pune Overpass extract"
        )
    return json.loads(OSM_SOURCE.read_text(encoding="utf-8"))


def _road_graph() -> tuple[
    dict[int, tuple[float, float]],
    dict[int, list[tuple[int, float]]],
    list[dict[str, Any]],
]:
    coordinates: dict[int, tuple[float, float]] = {}
    adjacency: dict[int, list[tuple[int, float]]] = defaultdict(list)
    ways: list[dict[str, Any]] = []
    for element in _osm()["elements"]:
        tags = element.get("tags", {})
        geometry = element.get("geometry") or []
        nodes = element.get("nodes") or []
        if "highway" not in tags or len(geometry) < 2 or len(nodes) != len(geometry):
            continue
        points = [(float(p["lon"]), float(p["lat"])) for p in geometry]
        ways.append({"id": element["id"], "tags": tags, "points": points})
        for node_id, point in zip(nodes, points):
            coordinates[int(node_id)] = point
        for left, right in zip(nodes, nodes[1:]):
            left_id, right_id = int(left), int(right)
            length = _distance(coordinates[left_id], coordinates[right_id])
            adjacency[left_id].append((right_id, length))
            adjacency[right_id].append((left_id, length))
    return coordinates, adjacency, ways


def _target_points() -> list[tuple[float, float]]:
    lons = (73.8440, 73.8500, 73.8560, 73.8620)
    lats = (18.5260, 18.5190, 18.5120, 18.5050, 18.4980)
    return [(lon, lat) for lat in lats for lon in lons]


def _select_nodes(
    coordinates: dict[int, tuple[float, float]],
    adjacency: dict[int, list[tuple[int, float]]],
) -> dict[str, int]:
    candidates = [
        node_id
        for node_id, edges in adjacency.items()
        if len({neighbor for neighbor, _ in edges}) >= 2
    ]
    selected: dict[str, int] = {}
    used: set[int] = set()
    for index, target in enumerate(_target_points(), 1):
        node_id = min(
            (candidate for candidate in candidates if candidate not in used),
            key=lambda candidate: _distance(coordinates[candidate], target),
        )
        selected[f"J{index}"] = node_id
        used.add(node_id)
    return selected


def _dijkstra(
    start: int,
    finish: int,
    coordinates: dict[int, tuple[float, float]],
    adjacency: dict[int, list[tuple[int, float]]],
) -> list[int]:
    queue: list[tuple[float, int]] = [(0.0, start)]
    distances = {start: 0.0}
    previous: dict[int, int] = {}
    while queue:
        distance, node = heapq.heappop(queue)
        if node == finish:
            break
        if distance != distances.get(node):
            continue
        for neighbor, weight in adjacency.get(node, []):
            candidate = distance + weight
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    if finish not in distances:
        raise ValueError(f"Pune road graph has no path from {start} to {finish}")
    path = [finish]
    while path[-1] != start:
        path.append(previous[path[-1]])
    path.reverse()
    return path


_ROAD_MAPPING_CACHE: dict[str, Any] | None = None


def build_road_mapping() -> dict[str, Any]:
    global _ROAD_MAPPING_CACHE
    if _ROAD_MAPPING_CACHE is not None:
        return _ROAD_MAPPING_CACHE
    committed = DATA_DIR / "toyworld-roads.json"
    if not OSM_SOURCE.exists() and committed.exists():
        _ROAD_MAPPING_CACHE = json.loads(committed.read_text(encoding="utf-8"))
        return _ROAD_MAPPING_CACHE
    coordinates, adjacency, _ = _road_graph()
    selected = _select_nodes(coordinates, adjacency)
    nodes = {
        name: {
            "osm_node_id": node_id,
            "coordinate": list(coordinates[node_id]),
            "layer": (int(name[1:]) - 1) // 4,
        }
        for name, node_id in selected.items()
    }
    edges: dict[str, dict[str, Any]] = {}
    for start, junction in GRAPH.items():
        for edge in junction.edges:
            road_nodes = _dijkstra(
                selected[start], selected[edge.to], coordinates, adjacency
            )
            edges[f"{start}->{edge.to}"] = {
                "start": start,
                "end": edge.to,
                "minutes": edge.minutes,
                "osm_nodes": road_nodes,
                "polyline": [list(coordinates[node]) for node in road_nodes],
            }
    _ROAD_MAPPING_CACHE = {
        "schema_version": 1,
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "corridor": "Shivajinagar–Deccan–Swargate",
            "attribution": "© OpenStreetMap contributors",
            "toy_weights_are_real_traffic": False,
        },
    }
    return _ROAD_MAPPING_CACHE


def _combine_path(path: Iterable[str], mapping: dict[str, Any]) -> list[list[float]]:
    names = list(path)
    if len(names) == 1:
        return [mapping["nodes"][names[0]]["coordinate"]]
    combined: list[list[float]] = []
    for start, end in zip(names, names[1:]):
        segment = mapping["edges"][f"{start}->{end}"]["polyline"]
        combined.extend(segment if not combined else segment[1:])
    return combined


def _route_candidates(query_id: str) -> dict[str, tuple[str, ...]]:
    _, start, end = query_id.split("-", 2)
    best_path, best_time = shortest_path(GRAPH, start, end)
    alternative = second_best_path(GRAPH, start, end)
    if alternative is None:
        raise ValueError(f"{query_id} has no alternative path")
    alt_path, alt_time = alternative
    candidates = sorted([(best_path, best_time), (alt_path, alt_time)])
    return {label: tuple(candidate[0]) for label, candidate in zip("AB", candidates)}


def _agent_paths(
    decision: dict[str, Any], query: Any
) -> tuple[tuple[str, ...], tuple[str, ...], str, str]:
    query_id = decision["query_id"]
    if query.decision_type == "route_choice":
        candidates = _route_candidates(query_id)
        chosen_path = candidates.get(str(decision["chosen"]), (query_id.split("-")[1],))
        correct_path = candidates[str(query.correct)]
        return chosen_path, correct_path, chosen_path[0], chosen_path[-1]
    if query.decision_type == "next_hop":
        start = query_id.removeprefix("next_hop-")
        neighbors = {edge.to for edge in GRAPH[start].edges}
        chosen = str(decision["chosen"])
        chosen_path = (start, chosen) if chosen in neighbors else (start,)
        correct_path = (start, str(query.correct))
        return chosen_path, correct_path, start, chosen_path[-1]
    _, start, end = query_id.split("-", 2)
    correct_path, _ = shortest_path(GRAPH, start, end)
    return tuple(correct_path), tuple(correct_path), start, end


def _load_recording(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        kind = entry.pop("type")
        (decisions if kind == "decision" else outcomes).append(entry)
    return decisions, outcomes


def build_run_document(recording_path: Path = RECORDING) -> dict[str, Any]:
    mapping = build_road_mapping()
    decisions, outcomes = _load_recording(recording_path)
    outcome_by_response = {
        outcome["graded_response_id"]: outcome for outcome in outcomes
    }
    agents: list[dict[str, Any]] = []
    total_cost = 0.0
    correct_count = 0
    for index, decision in enumerate(decisions):
        query = QUERIES_BY_ID.get(decision["query_id"])
        if query is None:
            raise ValueError(f"unknown query {decision['query_id']!r}")
        chosen_path, correct_path, start, destination = _agent_paths(decision, query)
        is_correct = bool(query.checker(decision["chosen"], query.correct))
        cost = price(
            decision["model"], decision["input_tokens"], decision["output_tokens"]
        )
        total_cost += cost
        correct_count += int(is_correct)
        agents.append(
            {
                "agent_id": f"agent-{index + 1:03d}",
                "response_id": decision["response_id"],
                "model": decision["model"],
                "color": MODEL_COLORS.get(decision["model"], "#ffcc66"),
                "decision_type": query.decision_type,
                "difficulty": query.difficulty,
                "query_id": query.query_id,
                "start": start,
                "destination": destination,
                "chosen": decision["chosen"],
                "correct_answer": query.correct,
                "is_correct": is_correct,
                "chosen_path": list(chosen_path),
                "correct_path": list(correct_path),
                "chosen_polyline": _combine_path(chosen_path, mapping),
                "correct_polyline": _combine_path(correct_path, mapping),
                "cost_usd": cost,
                "input_tokens": decision["input_tokens"],
                "output_tokens": decision["output_tokens"],
                "outcome": outcome_by_response.get(decision["response_id"]),
            }
        )
    response_ids = {agent["response_id"] for agent in agents}
    if any(outcome["graded_response_id"] not in response_ids for outcome in outcomes):
        raise ValueError("recording contains an outcome with no decision")
    # Every roster model needs its own hue or the viewer renders several models in
    # the same fallback amber and the legend stops meaning anything. Fail here
    # rather than ship a run document that looks fine and reads wrong.
    uncoloured = sorted({a["model"] for a in agents} - set(MODEL_COLORS))
    if uncoloured:
        raise ValueError(
            f"no MODEL_COLORS entry for {', '.join(uncoloured)} - add one per model "
            "in export.py before exporting"
        )
    by_type = Counter(agent["decision_type"] for agent in agents)
    by_model = Counter(agent["model"] for agent in agents)
    return {
        "schema_version": 2,
        "generated_from": recording_path.relative_to(ROOT).as_posix(),
        "agents": agents,
        "outcomes": outcomes,
        "totals": {
            "decisions": len(agents),
            "correct": correct_count,
            "total_cost_usd": total_cost,
            "outcomes": len(outcomes),
            "cost_per_correct_usd": total_cost / correct_count
            if correct_count
            else None,
            "by_type": dict(by_type),
            "by_model": dict(by_model),
        },
    }


def build_pune_map() -> dict[str, Any]:
    committed = DATA_DIR / "pune-map.geojson"
    if not OSM_SOURCE.exists() and committed.exists():
        return json.loads(committed.read_text(encoding="utf-8"))
    _, _, road_ways = _road_graph()
    features: list[dict[str, Any]] = []
    for way in road_ways:
        highway = way["tags"].get("highway", "unclassified")
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "road",
                    "osm_id": way["id"],
                    "highway": highway,
                    "name": way["tags"].get("name", ""),
                    "width": HIGHWAY_WIDTHS.get(highway, 0.06),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(point) for point in way["points"]],
                },
            }
        )
    building_count = 0
    for element in _osm()["elements"]:
        tags = element.get("tags", {})
        geometry = element.get("geometry") or []
        if "building" not in tags or len(geometry) < 4:
            continue
        coordinates = [[float(p["lon"]), float(p["lat"])] for p in geometry]
        if coordinates[0] != coordinates[-1]:
            coordinates.append(coordinates[0])
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "building",
                    "osm_id": element["id"],
                    "height": parse_osm_number(tags.get("height")),
                    "levels": parse_osm_number(tags.get("building:levels")),
                },
                "geometry": {"type": "Polygon", "coordinates": [coordinates]},
            }
        )
        building_count += 1
        if building_count >= 1800:
            break
    for name, coordinate in (
        ("Shivajinagar", [73.8493, 18.5308]),
        ("Deccan", [73.8420, 18.5164]),
        ("Shaniwar Wada", [73.8553, 18.5195]),
        ("Saras Baug", [73.8535, 18.4998]),
        ("Swargate", [73.8567, 18.4862]),
    ):
        features.append(
            {
                "type": "Feature",
                "properties": {"kind": "landmark", "name": name},
                "geometry": {"type": "Point", "coordinates": coordinate},
            }
        )
    return {
        "type": "FeatureCollection",
        "metadata": {
            "attribution": "© OpenStreetMap contributors",
            "copyright_url": "https://www.openstreetmap.org/copyright",
            "bounds": [73.840, 18.495, 73.865, 18.530],
            "prepared": "2026-07-26",
        },
        "features": features,
    }


def export_data(output_dir: Path = DATA_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = {
        "toyworld-roads.json": build_road_mapping(),
        "pune-map.geojson": build_pune_map(),
        "run.json": build_run_document(),
    }
    for filename, value in assets.items():
        (output_dir / filename).write_text(
            json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8"
        )
    # Keep the original fetch out of the runtime build once the reduced map exists.


if __name__ == "__main__":
    export_data()
