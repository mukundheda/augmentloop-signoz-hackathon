"""Ticket C6 (#51) - the budget-guard trip failure log (conventions §13).

The other two failure classes (unknown-model pricing miss, missing response id)
live in the gradebook library and are tested there. The budget guard is the one
that lives in the toy-world run loop: when a run stops before it can overspend,
it emits one structured log, linked to the model-run span that hit the cap.
Asserts on the emitted log only, same discipline as test_live.py.
"""

from toyworld.live import DEFAULT_ROSTER, ModelDecision, run_live


class _Client:
    """A deterministic, free stand-in model that always picks the true fastest."""

    def decide(self, *, model, query):
        # #33 replaced the single-junction API with per-query decisions; the
        # correct answer now comes off the query itself.
        return ModelDecision(
            chosen=query.correct,
            input_tokens=200,
            output_tokens=10,
            response_id=f"live-{model}-{query.query_id}",
        )


def test_budget_guard_trip_emits_one_structured_log_linked_to_the_model_run(
    world, gradebook_log_bridge
):
    provider, exporter = world
    # A cap below a single call's cost ceiling: the guard trips on the first
    # junction of the first model, before any decision is placed.
    summary = run_live(_Client(), budget_usd=0.0, world_provider=provider)
    assert summary.budget_exhausted
    assert summary.decisions == 0

    logs = gradebook_log_bridge.get_finished_logs()
    assert len(logs) == 1, "one budget-guard log per run that hits the cap"
    record = logs[0].log_record

    assert record.attributes["augmentloop.failure.class"] == "budget_guard_tripped"
    assert record.attributes["augmentloop.budget.usd"] == 0.0
    assert record.attributes["augmentloop.spend.usd"] == 0.0
    assert record.attributes["gen_ai.request.model"] in DEFAULT_ROSTER
    assert record.attributes["augmentloop.decision.type"] == "route_choice"

    # Linked to the model-run span that hit the cap (click-log -> jump-to-span).
    model_runs = [
        s for s in exporter.get_finished_spans() if s.name.startswith("model-run ")
    ]
    assert record.span_id in {s.context.span_id for s in model_runs}
    assert record.trace_id in {s.context.trace_id for s in model_runs}


def test_a_run_within_budget_emits_no_failure_log(world, gradebook_log_bridge):
    provider, _ = world
    summary = run_live(_Client(), budget_usd=100.0, world_provider=provider)
    assert not summary.budget_exhausted
    assert len(gradebook_log_bridge.get_finished_logs()) == 0
