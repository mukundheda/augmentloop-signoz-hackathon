"""Ticket #42 - reusable checkers + the closed reason-code enum.

The checkers are pure functions, so these assert their CheckResult directly.
The recorder-side emission of `augmentloop.grade.reason` is covered in
test_record_math_decision.py against emitted telemetry.
"""

import pytest

from gradebook import (
    CheckResult,
    ReasonCode,
    completed,
    fact_match,
    tool_choice,
    verbatim_substring,
)
from gradebook.checkers import REASON_CODES_VERSION


def test_reason_enum_is_closed_and_versioned():
    # The exact closed set - a new code is a deliberate, reviewable change here
    # (and in conventions.md §12), never an ad-hoc string.
    assert {r.value for r in ReasonCode} == {
        "match",
        "mismatch",
        "no_ground_truth",
        "empty_answer",
        "ambiguous",
    }
    assert isinstance(REASON_CODES_VERSION, int) and REASON_CODES_VERSION >= 1


def test_only_match_and_mismatch_are_machine_checked():
    assert ReasonCode.MATCH.is_machine_checked
    assert ReasonCode.MISMATCH.is_machine_checked
    for r in (ReasonCode.NO_GROUND_TRUTH, ReasonCode.EMPTY_ANSWER, ReasonCode.AMBIGUOUS):
        assert not r.is_machine_checked


def test_decided_helper_maps_bool_to_match_mismatch():
    assert CheckResult.decided(True) == CheckResult(True, ReasonCode.MATCH)
    assert CheckResult.decided(False) == CheckResult(False, ReasonCode.MISMATCH)


# --- verbatim_substring ---

def test_verbatim_substring_match_and_mismatch():
    ref = "Consistency beats intensity every single time."
    assert verbatim_substring("Consistency beats intensity", ref) == CheckResult(
        True, ReasonCode.MATCH
    )
    assert verbatim_substring('"beats intensity"', ref).passed  # quotes tolerated
    assert verbatim_substring("consistency is better", ref) == CheckResult(
        False, ReasonCode.MISMATCH
    )


def test_verbatim_substring_normalizes_whitespace():
    assert verbatim_substring("beats    intensity", "x beats intensity y").passed


def test_verbatim_substring_reasons_for_undecidable_inputs():
    assert verbatim_substring("anything", "").reason is ReasonCode.NO_GROUND_TRUTH
    assert verbatim_substring("   ", "a reference").reason is ReasonCode.EMPTY_ANSWER


# --- fact_match ---

def test_fact_match_normalized_equality():
    assert fact_match("555-1234", "555-1234").passed
    assert fact_match("  ACME  Corp ", "acme corp").passed  # case + whitespace
    assert not fact_match("555-9999", "555-1234").passed


def test_fact_match_reasons():
    assert fact_match("x", None).reason is ReasonCode.NO_GROUND_TRUTH
    assert fact_match("", "the record").reason is ReasonCode.EMPTY_ANSWER


# --- tool_choice ---

def test_tool_choice_identity():
    assert tool_choice("A", "A") == CheckResult(True, ReasonCode.MATCH)
    assert tool_choice("B", "A") == CheckResult(False, ReasonCode.MISMATCH)
    assert tool_choice("search_web", "SEARCH_WEB").passed  # normalized


def test_tool_choice_reasons():
    assert tool_choice("A", None).reason is ReasonCode.NO_GROUND_TRUTH
    assert tool_choice(None, "A").reason is ReasonCode.EMPTY_ANSWER


# --- completed ---

def test_completed_terminal_states():
    assert completed("done", {"done", "resolved"}).passed
    assert completed("RESOLVED", {"done", "resolved"}).passed  # normalized
    assert not completed("in_progress", {"done"}).passed


def test_completed_reasons():
    assert completed("done", set()).reason is ReasonCode.NO_GROUND_TRUTH
    assert completed(None, {"done"}).reason is ReasonCode.EMPTY_ANSWER
