"""Reading a log nobody promised to finish writing.

The tests that matter are the damaged ones. A JSONL importer is read while the
file is still being appended to, so truncation is the normal case rather than the
exceptional one, and the requirement is that damage never spreads: a bad line
costs you that line and nothing around it.
"""

from __future__ import annotations

import json

from gradebook_adapter.costing import EvidenceLedger
from gradebook_adapter_jsonl import (
    GenericJsonlAdapter,
    read_jsonl,
    read_jsonl_file,
    to_jsonl,
)


def bundle_line(decision_id: str, *, chosen: str = "search_database") -> str:
    return json.dumps({
        "schema_version": "1.0",
        "decision": {
            "decision_id": decision_id,
            "decision_type": "tool_choice",
            "evaluation_name": "agent.tool_choice",
            "chosen": {"kind": "inline", "value": chosen},
        },
        "subject": {"harness": "custom-loop", "run_id": "run-42"},
        "evidence": [],
    })


def usage_line(usage_id: str) -> str:
    return json.dumps({
        "schema_version": "1.0",
        "usage_id": usage_id,
        "scope": "model_invocation",
        "run_id": "run-42",
        "cost_provenance": "unknown",
    })


def outcome_line(outcome_id: str) -> str:
    return json.dumps({
        "schema_version": "1.0",
        "outcome_id": outcome_id,
        "decision_id": "decision-1",
        "outcome_type": "pull_request_merged",
        "correct": True,
        "observed_at": "2026-07-27T10:00:00Z",
    })


def test_a_clean_stream_yields_every_record_by_type() -> None:
    stream = "\n".join([bundle_line("decision-1"), usage_line("usage-1"),
                        outcome_line("outcome-1")]) + "\n"
    report = read_jsonl(stream)

    assert report.accepted == 3
    assert report.rejected == 0
    assert report.incomplete_tail is None
    assert report.bundles[0].decision.decision_id == "decision-1"
    assert report.usage[0].usage_id == "usage-1"
    assert report.outcomes[0].correct is True


def test_a_truncated_final_line_does_not_cost_the_completed_records() -> None:
    """The headline requirement: partial ingestion must not corrupt what is done."""
    good = bundle_line("decision-1")
    partial = usage_line("usage-1")[:40]  # a half-flushed write
    report = read_jsonl(good + "\n" + partial)

    assert report.accepted == 1
    assert report.bundles[0].decision.decision_id == "decision-1"
    # Reported as an unterminated tail, not as corruption, and kept verbatim so
    # the next read can resume from it.
    assert report.incomplete_tail == partial
    assert report.line_errors == ()


def test_a_corrupt_line_in_the_middle_is_reported_and_stepped_over() -> None:
    stream = "\n".join([
        bundle_line("decision-1"),
        '{"schema_version": "1.0", "usage_id": ',  # complete line, broken JSON
        usage_line("usage-1"),
    ]) + "\n"
    report = read_jsonl(stream)

    assert report.accepted == 2
    assert [e.line_number for e in report.line_errors] == [2]
    assert report.line_errors[0].reason == "not_json"
    # Terminated, so it is someone's bug rather than a truncated write.
    assert report.incomplete_tail is None


def test_a_terminated_broken_last_line_is_corruption_not_a_tail() -> None:
    """The newline is the whole signal: a finished line that will not parse is a
    bug in whatever wrote it, and saying otherwise would hide it forever."""
    report = read_jsonl(bundle_line("decision-1") + "\n" + '{"broken": ' + "\n")
    assert report.incomplete_tail is None
    assert report.line_errors[0].reason == "not_json"


def test_an_invalid_record_is_rejected_with_actionable_errors() -> None:
    bad = json.dumps({
        "schema_version": "1.0",
        "usage_id": "usage-1",
        "scope": "tool_call",  # not one of the four scopes
        "run_id": "run-42",
        "cost_provenance": "unknown",
    })
    report = read_jsonl(bundle_line("decision-1") + "\n" + bad + "\n")

    assert report.accepted == 1
    error = report.line_errors[0]
    assert error.reason == "invalid_record"
    assert any(e.path == "/scope" for e in error.errors)
    assert "line 2" in str(error)


def test_a_line_this_protocol_does_not_define_is_named_not_guessed() -> None:
    stream = bundle_line("decision-1") + "\n" + json.dumps({"hello": "world"}) + "\n"
    report = read_jsonl(stream)
    assert report.accepted == 1
    assert report.line_errors[0].reason == "unknown_record_type"
    assert "normalize" in report.line_errors[0].detail


def test_blank_lines_and_a_byte_order_mark_are_not_errors() -> None:
    stream = "﻿" + bundle_line("decision-1") + "\n\n   \n" + usage_line("u-1") + "\n"
    report = read_jsonl(stream)
    assert report.accepted == 2
    assert report.rejected == 0
    assert report.blank_lines == 2


def test_a_conflicting_duplicate_decision_keeps_the_record_already_held() -> None:
    ledger = EvidenceLedger()
    stream = "\n".join([
        bundle_line("decision-1", chosen="first"),
        bundle_line("decision-1", chosen="second"),
        usage_line("usage-1"),
    ]) + "\n"

    report = read_jsonl(stream, ledger=ledger)

    assert report.line_errors[0].reason == "conflicting_decision_id"
    assert report.line_errors[0].line_number == 2
    # The held record survives, and the stream keeps going past the conflict.
    assert ledger.bundles["decision-1"].decision.chosen.value == "first"  # type: ignore[union-attr]
    assert len(report.usage) == 1


def test_replaying_the_same_stream_into_one_ledger_is_idempotent() -> None:
    ledger = EvidenceLedger()
    stream = bundle_line("decision-1") + "\n" + usage_line("usage-1") + "\n"

    read_jsonl(stream, ledger=ledger)
    read_jsonl(stream, ledger=ledger)

    assert ledger.decision_ids == ("decision-1",)
    assert len(ledger.usage) == 1


def test_a_normalizer_converts_harness_shaped_lines() -> None:
    """The seam is the integrator's, because only they know their field names."""
    def normalize(line):  # type: ignore[no-untyped-def]
        if line.get("event") != "tool_call":
            return None
        return {
            "schema_version": "1.0",
            "decision": {
                "decision_type": "tool_choice",
                "evaluation_name": "agent.tool_choice",
                "chosen": {"kind": "inline", "value": line["tool"]},
            },
            "subject": {"harness": "custom-loop", "run_id": line["run"]},
            "evidence": [],
        }

    stream = "\n".join([
        json.dumps({"event": "tool_call", "tool": "search_database", "run": "run-42"}),
        json.dumps({"event": "heartbeat"}),
    ]) + "\n"
    report = read_jsonl(stream, normalize=normalize)

    assert len(report.bundles) == 1
    assert report.bundles[0].decision.chosen.value == "search_database"  # type: ignore[union-attr]
    assert report.line_errors[0].reason == "dropped_by_normalizer"


def test_the_adapter_interface_returns_bundles_and_usage() -> None:
    adapter = GenericJsonlAdapter()
    stream = bundle_line("decision-1") + "\n" + usage_line("usage-1") + "\n"
    assert len(adapter.normalize_run(stream)) == 1
    assert len(adapter.normalize_usage(stream)) == 1


def test_emitted_jsonl_round_trips_and_always_terminates_its_last_line() -> None:
    report = read_jsonl(bundle_line("decision-1") + "\n" + usage_line("usage-1") + "\n")
    text = to_jsonl(report.records)

    assert text.endswith("\n")
    again = read_jsonl(text)
    assert again.accepted == 2
    assert again.incomplete_tail is None
    assert again.bundles[0] == report.bundles[0]


def test_reading_from_a_file_reports_the_same_way(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "run.jsonl"
    path.write_text(bundle_line("decision-1") + "\n" + usage_line("usage-1")[:20],
                    encoding="utf-8")
    report = read_jsonl_file(path)
    assert report.accepted == 1
    assert report.incomplete_tail is not None


def test_an_iterable_of_lines_is_accepted_as_a_source() -> None:
    lines = [bundle_line("decision-1") + "\n", usage_line("usage-1") + "\n"]
    assert read_jsonl(lines).accepted == 2


def test_the_summary_says_what_happened_in_one_line() -> None:
    report = read_jsonl(bundle_line("decision-1") + "\n" + '{"partial"')
    assert "1 record(s) accepted" in report.summary()
    assert "unterminated" in report.summary()
