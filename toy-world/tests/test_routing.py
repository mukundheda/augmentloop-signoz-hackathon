"""Ticket #10 - the production routing table the right-sizing loop edits.

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

    assert "route_choice" in routing


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


def test_routing_the_decision_type_narrows_the_run_to_one_model(
    world, world_metrics
):
    """A production run must exercise ONLY the routed model.

    This is what makes a before/after pair meaningful: if the roster leaked in,
    the "after" run would still be paying for the premium model it just stopped
    routing to.
    """
    from toyworld.live import DECISION_TYPE, run_live

    provider, exporter = world
    meter_provider, _ = world_metrics
    routing = {DECISION_TYPE: "google/gemini-2.5-flash-lite"}

    seen: list[str] = []

    class RecordingClient:
        def decide(self, *, model, junction):
            from toyworld.live import ModelDecision

            seen.append(model)
            return ModelDecision(
                chosen=junction.true_fastest,
                input_tokens=200,
                output_tokens=10,
                response_id=f"r-{len(seen)}",
            )

    run_live(
        RecordingClient(),
        budget_usd=1.0,
        roster=(routed_model(routing, DECISION_TYPE),),
        world_provider=provider,
        world_meter_provider=meter_provider,
    )

    assert set(seen) == {"google/gemini-2.5-flash-lite"}


def test_production_without_live_is_refused_before_any_call(monkeypatch):
    """`--production` is meaningless in replay - argparse must refuse it early."""
    from toyworld.__main__ import main

    monkeypatch.setattr("sys.argv", ["toyworld", "--production"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 2
