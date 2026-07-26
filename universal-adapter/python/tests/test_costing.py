"""Cost attribution: charge everything once, invent nothing, admit the gaps.

Every test here is a way the numerator of cost-per-correct gets corrupted in
practice. Double counting inflates it, a fabricated zero deflates it, and a
comparison at low coverage makes a number out of an absence.
"""

from __future__ import annotations

import pytest
from support import bundle, usage

from gradebook.checkers import ReasonCode
from gradebook.grading import GradeSource
from gradebook_adapter.costing import (
    PRICING_TABLE_ID,
    EvidenceLedger,
    InsufficientCoverageError,
    UnpriceableUsageError,
    attribute_costs,
    compare_cost_per_correct,
    compute_pricing_table_id,
    cost_per_correct,
    record_cost,
)
from gradebook_adapter.evaluation import EvaluationResult
from gradebook_adapter.models import CostProvenance

# 1000 input + 500 output on claude-haiku-4.5 (1.00 / 5.00 per Mtok).
HAIKU_CALL = 1000 * 1.00 / 1_000_000 + 500 * 5.00 / 1_000_000


def result(decision_id: str, *, passed: bool = True,
           authority: GradeSource = GradeSource.MATH,
           graded: bool = True,
           decision_type: str = "task_completion") -> EvaluationResult:
    return EvaluationResult(
        decision_id=decision_id,
        decision_type=decision_type,
        evaluation_name="repository.tests_pass",
        evaluator_kind="exact_equality",
        graded=graded,
        passed=passed and graded,
        authority=authority if graded else None,
        reason=ReasonCode.MATCH if passed else ReasonCode.MISMATCH,
        detail="",
    )


def ledger_with(*decision_ids: str) -> EvidenceLedger:
    ledger = EvidenceLedger()
    for decision_id in decision_ids:
        ledger.add_bundle(bundle(decision_id=decision_id))
    return ledger


# --------------------------------------------------------------------------
# Pricing table identity
# --------------------------------------------------------------------------


def test_the_pricing_table_id_is_derived_from_the_live_table() -> None:
    assert PRICING_TABLE_ID.startswith("gradebook.pricing@")
    assert len(PRICING_TABLE_ID) == len("gradebook.pricing@") + 12
    assert compute_pricing_table_id() == PRICING_TABLE_ID


def test_the_pricing_table_id_changes_when_a_rate_changes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The digest IS the version, so nobody has to remember to bump anything."""
    from gradebook import pricing

    before = compute_pricing_table_id()
    patched = dict(pricing.PRICES)
    patched["anthropic/claude-haiku-4.5"] = pricing.ModelRate(2.00, 5.00)
    monkeypatch.setattr(pricing, "PRICES", patched)
    assert compute_pricing_table_id() != before


# --------------------------------------------------------------------------
# Deduplication
# --------------------------------------------------------------------------


def test_the_same_usage_id_is_charged_once() -> None:
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("usage-101", decision_ids=("d-1",)))
    ledger.add_usage(usage("usage-101", decision_ids=("d-1",)))  # parent reports it too

    report = attribute_costs(ledger, {"d-1": result("d-1")})
    assert report.per_decision["d-1"].usage_ids == ("usage-101",)
    assert report.cost_for("d-1") == pytest.approx(HAIKU_CALL)


def test_a_parent_that_declares_containment_replaces_its_children() -> None:
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("child-1", decision_ids=("d-1",)))
    ledger.add_usage(usage("child-2", decision_ids=("d-1",)))
    ledger.add_usage(usage("parent-1", decision_ids=("d-1",), scope="agent",
                           contains=("child-1", "child-2"),
                           input_tokens=2000, output_tokens=1000))

    report = attribute_costs(ledger, {"d-1": result("d-1")})
    assert report.charged_usage_ids == ("parent-1",)
    assert "child-1" in report.skipped_usage
    assert report.cost_for("d-1") == pytest.approx(2 * HAIKU_CALL)


def test_a_parent_aggregate_is_dropped_when_children_are_reported_separately() -> None:
    """The classic multi-agent double count, with no containment declaration."""
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("child-call", decision_ids=("d-1",), agent_id="coder-1",
                           parent_agent_id="lead"))
    ledger.add_usage(usage("lead-total", decision_ids=("d-1",), scope="agent",
                           agent_id="lead", input_tokens=5000, output_tokens=2500))

    report = attribute_costs(ledger, {"d-1": result("d-1")})
    assert report.charged_usage_ids == ("child-call",)
    assert "superseded" in report.skipped_usage["lead-total"]
    assert report.cost_for("d-1") == pytest.approx(HAIKU_CALL)


def test_a_usage_record_naming_two_decisions_splits_evenly() -> None:
    ledger = ledger_with("d-1", "d-2")
    ledger.add_usage(usage("usage-101", decision_ids=("d-1", "d-2")))

    report = attribute_costs(ledger, {"d-1": result("d-1"), "d-2": result("d-2")})
    assert report.cost_for("d-1") == pytest.approx(HAIKU_CALL / 2)
    assert report.cost_for("d-2") == pytest.approx(HAIKU_CALL / 2)


# --------------------------------------------------------------------------
# Run-level cost
# --------------------------------------------------------------------------


def test_a_run_total_is_assigned_exactly_once_to_the_terminal_decision() -> None:
    ledger = ledger_with("d-1", "d-2")
    ledger.add_usage(usage("run-total", scope="run", provenance="run_aggregate",
                           provider_cost_usd=None, input_tokens=10_000,
                           output_tokens=2_000))

    results = {"d-1": result("d-1", passed=False), "d-2": result("d-2")}
    report = attribute_costs(ledger, results)

    assert "d-1" not in report.per_decision
    assert report.per_decision["d-2"].usage_ids == ("run-total",)
    assert report.per_decision["d-2"].provenance is CostProvenance.RUN_AGGREGATE
    assert report.unassigned_run_aggregates == ()


def test_the_terminal_decision_can_be_stated_explicitly() -> None:
    ledger = ledger_with("d-1", "d-2")
    ledger.add_usage(usage("run-total", scope="run", provenance="run_aggregate"))
    results = {"d-1": result("d-1"), "d-2": result("d-2")}

    report = attribute_costs(ledger, results, terminal_decision_id="d-1")
    assert report.per_decision["d-1"].usage_ids == ("run-total",)
    assert "d-2" not in report.per_decision


def test_a_run_total_is_never_copied_onto_every_decision() -> None:
    ledger = ledger_with("d-1", "d-2", "d-3")
    ledger.add_usage(usage("run-total", scope="run", provenance="run_aggregate"))
    results = {d: result(d) for d in ("d-1", "d-2", "d-3")}

    report = attribute_costs(ledger, results)
    charged_to = [d for d, entry in report.per_decision.items() if entry.is_known]
    assert len(charged_to) == 1


def test_a_run_total_yields_to_narrower_records_that_carry_a_cost() -> None:
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("call-1", decision_ids=("d-1",)))
    ledger.add_usage(usage("run-total", scope="run", provenance="run_aggregate",
                           input_tokens=99_000, output_tokens=99_000))

    report = attribute_costs(ledger, {"d-1": result("d-1")})
    assert report.charged_usage_ids == ("call-1",)
    assert report.cost_for("d-1") == pytest.approx(HAIKU_CALL)


def test_a_run_total_survives_when_the_narrower_records_have_no_cost() -> None:
    """Otherwise the only money anybody reported would be thrown away."""
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("call-1", decision_ids=("d-1",), provenance="unknown",
                           model=None, input_tokens=None, output_tokens=None))
    ledger.add_usage(usage("run-total", scope="run", provenance="run_aggregate"))

    report = attribute_costs(ledger, {"d-1": result("d-1")})
    assert "run-total" in report.charged_usage_ids
    assert report.cost_for("d-1") is not None


def test_a_run_total_with_nothing_to_attach_to_is_reported_not_spread() -> None:
    ledger = EvidenceLedger()
    ledger.add_usage(usage("run-total", scope="run", provenance="run_aggregate"))

    report = attribute_costs(ledger, {})
    assert report.unassigned_run_aggregates == ("run-total",)
    assert report.per_decision == {}


# --------------------------------------------------------------------------
# Provenance and unknown cost
# --------------------------------------------------------------------------


def test_a_provider_figure_wins_over_a_token_estimate() -> None:
    record = usage("usage-101", provenance="provider_reported",
                   provider_cost_usd=0.5)
    cost, provenance = record_cost(record)
    assert cost == 0.5
    assert provenance is CostProvenance.PROVIDER_REPORTED

    # Even when the record calls itself an estimate, a provider figure is the
    # only source that reflects the actual contract, discounts and rounding.
    mixed = usage("usage-102", provenance="provider_token_estimate",
                  provider_cost_usd=0.25)
    assert record_cost(mixed) == (0.25, CostProvenance.PROVIDER_REPORTED)


def test_unknown_cost_stays_unknown_and_never_becomes_zero() -> None:
    record = usage("usage-101", provenance="unknown", model=None,
                   input_tokens=None, output_tokens=None)
    assert record_cost(record) == (None, CostProvenance.UNKNOWN)

    ledger = ledger_with("d-1")
    ledger.add_usage(usage("usage-101", decision_ids=("d-1",), provenance="unknown",
                           model=None, input_tokens=None, output_tokens=None))
    report = attribute_costs(ledger, {"d-1": result("d-1")})
    assert report.cost_for("d-1") is None
    assert report.per_decision["d-1"].is_known is False


def test_a_token_estimate_with_no_tokens_is_not_an_estimate() -> None:
    record = usage("usage-101", provenance="harness_token_estimate",
                   input_tokens=None, output_tokens=None)
    assert record_cost(record) == (None, CostProvenance.UNKNOWN)


def test_an_unpriceable_model_fails_loud_by_default() -> None:
    record = usage("usage-101", model="acme/未来-1")
    with pytest.raises(UnpriceableUsageError):
        record_cost(record)
    assert record_cost(record, allow_unpriceable=True) == (None, CostProvenance.UNKNOWN)


def test_a_summed_cost_is_only_as_strong_as_its_weakest_part() -> None:
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("measured", decision_ids=("d-1",),
                           provenance="provider_reported", provider_cost_usd=0.1))
    ledger.add_usage(usage("estimated", decision_ids=("d-1",),
                           provenance="harness_token_estimate"))

    report = attribute_costs(ledger, {"d-1": result("d-1")})
    assert report.per_decision["d-1"].provenance is CostProvenance.HARNESS_TOKEN_ESTIMATE


# --------------------------------------------------------------------------
# Coverage and the headline metric
# --------------------------------------------------------------------------


def test_cost_coverage_reports_the_gap_rather_than_hiding_it() -> None:
    ledger = ledger_with("d-1", "d-2", "d-3", "d-4")
    ledger.add_usage(usage("usage-1", decision_ids=("d-1",)))
    results = {d: result(d) for d in ("d-1", "d-2", "d-3", "d-4")}

    report = attribute_costs(ledger, results)
    assert report.coverage.graded_decisions == 4
    assert report.coverage.decisions_with_cost == 1
    assert report.coverage.ratio == 0.25


def test_coverage_is_undefined_rather_than_zero_when_nothing_was_graded() -> None:
    report = attribute_costs(EvidenceLedger(), {})
    assert report.coverage.ratio is None


def test_incorrect_attempts_stay_in_the_numerator() -> None:
    """A harness that succeeds on the fifth try spent five attempts of money."""
    ledger = ledger_with("d-1", "d-2")
    ledger.add_usage(usage("usage-1", decision_ids=("d-1",)))  # failed attempt
    ledger.add_usage(usage("usage-2", decision_ids=("d-2",)))  # the one that worked
    results = {"d-1": result("d-1", passed=False), "d-2": result("d-2")}

    report = attribute_costs(ledger, results)
    metric = cost_per_correct(report, results)

    assert metric.correct_decisions == 1
    assert metric.total_cost_usd == pytest.approx(2 * HAIKU_CALL)
    assert metric.value == pytest.approx(2 * HAIKU_CALL)


def test_an_ai_judge_pass_is_not_a_verified_correct_decision() -> None:
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("usage-1", decision_ids=("d-1",)))
    results = {"d-1": result("d-1", authority=GradeSource.AI_JUDGE)}

    metric = cost_per_correct(attribute_costs(ledger, results), results)
    assert metric.correct_decisions == 0
    assert metric.value is None  # undefined, not zero and not infinite


def test_ungraded_decisions_are_not_in_the_denominator() -> None:
    ledger = ledger_with("d-1", "d-2")
    ledger.add_usage(usage("usage-1", decision_ids=("d-1",)))
    results = {"d-1": result("d-1"), "d-2": result("d-2", graded=False)}

    metric = cost_per_correct(attribute_costs(ledger, results), results)
    assert metric.graded_decisions == 1


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


def _metric(ledger_ids: tuple[str, ...], attributed: tuple[str, ...]):  # type: ignore[no-untyped-def]
    ledger = ledger_with(*ledger_ids)
    for index, decision_id in enumerate(attributed):
        ledger.add_usage(usage(f"usage-{index}", decision_ids=(decision_id,)))
    results = {d: result(d) for d in ledger_ids}
    return cost_per_correct(attribute_costs(ledger, results), results)


def test_comparing_requires_an_explicit_coverage_floor() -> None:
    """No default, so nobody compares at 12 percent coverage by accident."""
    left = _metric(("d-1",), ("d-1",))
    right = _metric(("d-2",), ("d-2",))
    with pytest.raises(TypeError):
        compare_cost_per_correct(left, right)  # type: ignore[call-arg]


def test_a_comparison_below_the_floor_is_refused_with_the_numbers() -> None:
    thin = _metric(("d-1", "d-2", "d-3", "d-4"), ("d-1",))
    thick = _metric(("d-5",), ("d-5",))

    with pytest.raises(InsufficientCoverageError) as excinfo:
        compare_cost_per_correct(thin, thick, min_coverage=0.8)
    assert "25%" in str(excinfo.value)
    assert "1 of 4" in str(excinfo.value)


def test_a_comparison_above_the_floor_returns_the_ratio() -> None:
    left = _metric(("d-1",), ("d-1",))
    right = _metric(("d-2",), ("d-2",))
    comparison = compare_cost_per_correct(left, right, min_coverage=1.0)
    assert comparison.ratio == pytest.approx(1.0)


def test_unlike_decision_types_are_not_compared() -> None:
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("usage-1", decision_ids=("d-1",)))
    results = {"d-1": result("d-1")}
    report = attribute_costs(ledger, results)

    tasks = cost_per_correct(report, results, decision_type="task_completion")
    tools = cost_per_correct(report, results, decision_type="task_completion")
    object.__setattr__(tools, "decision_type", "tool_choice")

    with pytest.raises(ValueError):
        compare_cost_per_correct(tasks, tools, min_coverage=0.0)


def test_usage_that_names_no_decision_lowers_coverage_rather_than_vanishing() -> None:
    ledger = ledger_with("d-1")
    ledger.add_usage(usage("orphan"))
    report = attribute_costs(ledger, {"d-1": result("d-1")})
    assert report.unattributed_usage_ids == ("orphan",)
    assert report.coverage.ratio == 0.0
