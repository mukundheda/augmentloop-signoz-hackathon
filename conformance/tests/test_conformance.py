"""Ticket #44 - the conformance checker passes a real second-language event and
fails malformed ones.

The conforming fixture is the *actual* output of the TypeScript emitter
(`conformance/samples/conforming.json`, produced by `node ts-emitter/emit.ts
--json`) - so this genuinely validates an implementation the checker did not
write, not a Python round-trip.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_conformance import check_event, conforms  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _load(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def test_typescript_emitter_output_conforms():
    # The real TS emitter output must pass with zero error-level findings.
    event = _load("conforming.json")
    assert conforms(event)
    assert [f for f in check_event(event) if f.level == "error"] == []


def test_missing_grade_source_is_nonconforming():
    event = _load("malformed-missing-grade-source.json")
    assert not conforms(event)
    errors = [f.message for f in check_event(event) if f.level == "error"]
    assert any("augmentloop.grade.source" in m for m in errors)


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda e: e.update(name="gen_ai.something_else"), "event name"),
        (lambda e: e["attributes"].pop("gen_ai.evaluation.name"), "gen_ai.evaluation.name"),
        (lambda e: e["attributes"].__setitem__("augmentloop.grade.source", "vibes"), "grade.source"),
        (lambda e: e["attributes"].__setitem__("gen_ai.evaluation.score.value", 0.5), "score.value"),
        (lambda e: e["attributes"].__setitem__("gen_ai.evaluation.score.label", "great"), "score.label"),
        (lambda e: e["attributes"].__setitem__("augmentloop.cost.usd", -1), "cost.usd"),
    ],
)
def test_each_frozen_field_violation_fails(mutate, needle):
    event = _load("conforming.json")
    mutate(event)
    assert not conforms(event), f"expected nonconforming after mutating for {needle}"
    assert any(needle in f.message for f in check_event(event) if f.level == "error")


def test_missing_response_id_is_a_warning_not_an_error():
    event = _load("conforming.json")
    event["attributes"].pop("gen_ai.response.id")
    # Recommended, not required: still conforms, but surfaces a warning.
    assert conforms(event)
    assert any(
        f.level == "warning" and "gen_ai.response.id" in f.message for f in check_event(event)
    )


def test_ai_judge_may_carry_a_raw_non_binary_score():
    # ai_judge is not machine-checked, so score need not be 0/1 - only typed.
    event = _load("conforming.json")
    event["attributes"]["augmentloop.grade.source"] = "ai_judge"
    event["attributes"]["gen_ai.evaluation.score.value"] = 0.73
    event["attributes"]["gen_ai.evaluation.score.label"] = "mostly_relevant"
    assert conforms(event)
