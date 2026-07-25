"""Export the canonical toy-world replay into static viewer data."""

from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "toy-world" / "src"))
sys.path.insert(0, str(ROOT / "reference-library" / "src"))

_PRICING_PATH = ROOT / "reference-library" / "src" / "gradebook" / "pricing.py"
_PRICING_SPEC = importlib.util.spec_from_file_location("viewer_gradebook_pricing", _PRICING_PATH)
if _PRICING_SPEC is None or _PRICING_SPEC.loader is None:
    raise ImportError(f"cannot load Gradebook pricing from {_PRICING_PATH}")
_PRICING_MODULE = importlib.util.module_from_spec(_PRICING_SPEC)
sys.modules[_PRICING_SPEC.name] = _PRICING_MODULE
_PRICING_SPEC.loader.exec_module(_PRICING_MODULE)
price = _PRICING_MODULE.price

_WORLD_PATH = ROOT / "toy-world" / "src" / "toyworld" / "world.py"
_WORLD_SPEC = importlib.util.spec_from_file_location("viewer_toyworld_world", _WORLD_PATH)
if _WORLD_SPEC is None or _WORLD_SPEC.loader is None:
    raise ImportError(f"cannot load toy world from {_WORLD_PATH}")
_WORLD_MODULE = importlib.util.module_from_spec(_WORLD_SPEC)
sys.modules[_WORLD_SPEC.name] = _WORLD_MODULE
_WORLD_SPEC.loader.exec_module(_WORLD_MODULE)
WORLD = _WORLD_MODULE.WORLD

RECORDING = ROOT / "toy-world" / "recordings" / "replay-v1.jsonl"
DATA_DIR = ROOT / "viewer" / "public" / "data"

# A compact, recognizable southbound central-Pune corridor.
STAGE_POINTS = (
    (73.8493, 18.5308),  # Shivajinagar
    (73.8420, 18.5164),  # Deccan
    (73.8534, 18.5018),  # Shaniwar Peth edge
    (73.8567, 18.4862),  # Swargate
)
DRIVER_COLORS = ("#69f0ae", "#57b8ff", "#ffcc66", "#ff6b9f")


def _feature(geometry: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def _route_coordinates(stage: int, option_index: int, option_count: int) -> list[list[float]]:
    start = STAGE_POINTS[stage]
    end = STAGE_POINTS[stage + 1]
    midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    spread = (option_index - (option_count - 1) / 2) * 0.0032
    # Offset mostly east/west so alternatives remain legible in the north/south corridor.
    control = [midpoint[0] + spread, midpoint[1] + spread * 0.18]
    return [[*start], control, [*end]]


def build_world_feature_collection() -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    features.append(
        _feature(
            {"type": "Point", "coordinates": [*STAGE_POINTS[0]]},
            {"kind": "start", "label": "Shivajinagar · START"},
        )
    )
    for stage, junction in enumerate(WORLD):
        for option_index, (route, travel_time) in enumerate(junction.options.items()):
            features.append(
                _feature(
                    {
                        "type": "LineString",
                        "coordinates": _route_coordinates(
                            stage, option_index, len(junction.options)
                        ),
                    },
                    {
                        "kind": "simulation-route",
                        "junction": junction.name,
                        "route": route,
                        "travel_time_min": travel_time,
                        "is_fastest": route == junction.true_fastest,
                        "stage_index": stage,
                    },
                )
            )
        features.append(
            _feature(
                {"type": "Point", "coordinates": [*STAGE_POINTS[stage]]},
                {"kind": "junction", "label": junction.name, "stage_index": stage},
            )
        )
    features.append(
        _feature(
            {"type": "Point", "coordinates": [*STAGE_POINTS[-1]]},
            {"kind": "finish", "label": "Swargate · FINISH"},
        )
    )
    return {
        "type": "FeatureCollection",
        "metadata": {
            "corridor": "Shivajinagar–Deccan–Swargate",
            "note": "Geography is visual context; travel times are toy-world values.",
        },
        "features": features,
    }


def _load_entries(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        entry = json.loads(raw_line)
        kind = entry.pop("type")
        if kind == "decision":
            decisions.append(entry)
        elif kind == "outcome":
            outcomes.append(entry)
        else:
            raise ValueError(f"unknown recording entry type: {kind!r}")
    return decisions, outcomes


def build_run_document(recording_path: Path = RECORDING) -> dict[str, Any]:
    decisions, outcomes = _load_entries(recording_path)
    by_junction = {junction.name: junction for junction in WORLD}
    driver_ids = list(dict.fromkeys(decision["driver"] for decision in decisions))
    drivers: list[dict[str, Any]] = []
    correct_count = 0
    total_cost = 0.0
    response_ids: set[str] = set()

    for driver_index, driver_id in enumerate(driver_ids):
        exported_decisions = []
        driver_decisions = [d for d in decisions if d["driver"] == driver_id]
        for decision in driver_decisions:
            junction = by_junction[decision["junction"]]
            if decision["chosen"] not in junction.options:
                raise ValueError(
                    f"{driver_id} chose unknown route {decision['chosen']!r}"
                )
            response_id = decision["response_id"]
            if response_id in response_ids:
                raise ValueError(f"duplicate response_id {response_id!r}")
            response_ids.add(response_id)
            cost = price(
                decision["model"],
                decision["input_tokens"],
                decision["output_tokens"],
            )
            is_correct = decision["chosen"] == junction.true_fastest
            correct_count += int(is_correct)
            total_cost += cost
            exported_decisions.append(
                {
                    "junction": junction.name,
                    "stage_index": next(
                        i for i, candidate in enumerate(WORLD) if candidate == junction
                    ),
                    "chosen": decision["chosen"],
                    "true_fastest": junction.true_fastest,
                    "correct": is_correct,
                    "travel_time_min": junction.options[decision["chosen"]],
                    "input_tokens": decision["input_tokens"],
                    "output_tokens": decision["output_tokens"],
                    "cost_usd": cost,
                    "response_id": response_id,
                }
            )
        drivers.append(
            {
                "id": driver_id,
                "model": driver_decisions[0]["model"],
                "color": DRIVER_COLORS[driver_index % len(DRIVER_COLORS)],
                "decisions": exported_decisions,
            }
        )

    for outcome in outcomes:
        if outcome["graded_response_id"] not in response_ids:
            raise ValueError(
                f"outcome for {outcome['driver']} targets unknown response "
                f"{outcome['graded_response_id']!r}"
            )

    return {
        "schema_version": 1,
        "generated_from": "toy-world/recordings/replay-v1.jsonl",
        "drivers": drivers,
        "outcomes": outcomes,
        "totals": {
            "decisions": len(decisions),
            "correct": correct_count,
            "total_cost_usd": total_cost,
            "outcomes": len(outcomes),
            "cost_per_correct_usd": total_cost / correct_count
            if correct_count
            else None,
        },
    }


def export_data(output_dir: Path = DATA_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "world.geojson").write_text(
        json.dumps(build_world_feature_collection(), indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "run.json").write_text(
        json.dumps(build_run_document(), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    export_data()
