"""Ticket #10 - the production routing table the right-sizing loop edits;
extended by ticket #33 to three decision types, each independently routable.

Right-sizing reroutes a *decision type* to a cheaper model (CONTEXT.md
"Right-sizing"; conventions.md section on `augmentloop.decision.type`). The
routing table is the thing that changes when a human approves a proposal: a
committed, diffable file mapping decision type -> the model that serves it in
production. These tests pin the contract the MCP loop's "apply" step writes to.
"""

import json

import pytest

from toyworld.routing import (
    DEFAULT_ROUTING_PATH,
    RoutingError,
    load_routing,
    routed_model,
)
from toyworld.world import DECISION_TYPES


def _write(tmp_path, mapping):
    path = tmp_path / "routing.json"
    path.write_text(json.dumps(mapping))
    return path


def test_loads_the_decision_type_to_model_mapping(tmp_path):
    path = _write(tmp_path, {"route_choice": "anthropic/claude-sonnet-4.6"})

    assert load_routing(path) == {"route_choice": "anthropic/claude-sonnet-4.6"}


def test_committed_routing_file_is_loadable_and_priced():
    """The real committed table must always be valid - it drives `--production`."""
    routing = load_routing(DEFAULT_ROUTING_PATH)

    assert set(routing) == set(DECISION_TYPES)


def test_rejects_a_model_with_no_pricing_row(tmp_path):
    """A reroute to an unpriceable model must fail before any span is emitted.

    Same fail-loud discipline as live mode's budget ceiling: cost is not
    optional, so an unknown model is a config error, not a runtime surprise.
    """
    path = _write(tmp_path, {"route_choice": "anthropic/claude-imaginary-9"})

    with pytest.raises(RoutingError) as excinfo:
        load_routing(path)

    assert "claude-imaginary-9" in str(excinfo.value)


def test_rejects_an_empty_table(tmp_path):
    path = _write(tmp_path, {})

    with pytest.raises(RoutingError):
        load_routing(path)


def test_rejects_a_non_string_model(tmp_path):
    path = _write(tmp_path, {"route_choice": ["anthropic/claude-haiku-4.5"]})

    with pytest.raises(RoutingError):
        load_routing(path)


def test_missing_file_fails_loud_naming_the_path(tmp_path):
    missing = tmp_path / "nope.json"

    with pytest.raises(RoutingError) as excinfo:
        load_routing(missing)

    assert "nope.json" in str(excinfo.value)


def test_malformed_json_fails_loud(tmp_path):
    path = tmp_path / "routing.json"
    path.write_text("{not json")

    with pytest.raises(RoutingError):
        load_routing(path)


def test_routed_model_returns_the_model_serving_a_decision_type():
    routing = {"route_choice": "google/gemini-2.5-flash-lite"}

    assert routed_model(routing, "route_choice") == "google/gemini-2.5-flash-lite"


def test_routed_model_fails_loud_on_an_unrouted_decision_type():
    routing = {"route_choice": "anthropic/claude-sonnet-4.6"}

    with pytest.raises(RoutingError) as excinfo:
        routed_model(routing, "filler_detection")

    assert "filler_detection" in str(excinfo.value)


def test_each_decision_type_can_be_routed_to_a_different_model(
    world, world_metrics
):
    """A production run must exercise ONLY each decision type's routed model,
    and different types can route to different models independently - this is
    what makes "reroute next_hop to the cheap model, leave route_choice on the
    premium one" a real, expressible right-sizing proposal (ticket #33)."""
    from toyworld.live import run_live
    from toyworld.world import ALL_QUERIES

    provider, exporter = world
    meter_provider, _ = world_metrics
    routing = {
        "route_choice": "anthropic/claude-sonnet-4.6",
        "eta_estimate": "anthropic/claude-haiku-4.5",
        "next_hop": "google/gemini-2.5-flash-lite",
    }

    seen: dict[str, set[str]] = {}

    class RecordingClient:
        def decide(self, *, model, query):
            seen.setdefault(query.decision_type, set()).add(model)
            from toyworld.live import ModelDecision

            return ModelDecision(
                chosen=query.correct,
                input_tokens=200,
                output_tokens=10,
                response_id=f"r-{query.query_id}-{model}",
            )

    pairs = [(routed_model(routing, q.decision_type), q) for q in ALL_QUERIES]
    summary = run_live(
        RecordingClient(),
        budget_usd=10.0,
        pairs=pairs,
        world_provider=provider,
        world_meter_provider=meter_provider,
    )

    assert seen == {
        "route_choice": {"anthropic/claude-sonnet-4.6"},
        "eta_estimate": {"anthropic/claude-haiku-4.5"},
        "next_hop": {"google/gemini-2.5-flash-lite"},
    }
    assert summary.decisions == len(ALL_QUERIES)


def test_production_without_live_is_refused_before_any_call(monkeypatch):
    """`--production` is meaningless in replay - argparse must refuse it early."""
    from toyworld.__main__ import main

    monkeypatch.setattr("sys.argv", ["toyworld", "--production"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 2


def test_record_without_live_is_refused_before_any_call(monkeypatch):
    """`--record` captures a live run; it is meaningless without `--live`."""
    from toyworld.__main__ import main

    monkeypatch.setattr("sys.argv", ["toyworld", "--record"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 2
