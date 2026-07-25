"""Ticket #33 - the recorder (`--live --record`): writes a replay file FROM a
real run.

Built and unit-tested against a deterministic, duck-typed fake `ModelClient` -
same discipline as `test_live.py`'s `FakeClient` - no key, no spend. This
module has NOT been exercised against a real provider as of this PR (see the
PR description): these tests prove the WRITING mechanism is correct (schema,
determinism, round-trip through replay), not that any particular model's
answers are captured, since no real model call is made here.
"""

import json

from toyworld.live import ModelDecision
from toyworld.recorder import record_live
from toyworld.replay import load_recording
from toyworld.replay import replay as run_replay
from toyworld.world import ALL_QUERIES, ROUTE_CHOICE_QUERIES


class FakeClient:
    def __init__(self, chooser, tokens=(120, 5)):
        self._chooser = chooser
        self._in, self._out = tokens
        self._n = 0

    def decide(self, *, model, query):
        self._n += 1
        return ModelDecision(
            chosen=self._chooser(model, query),
            input_tokens=self._in,
            output_tokens=self._out,
            response_id=f"rec-{model.split('/')[-1]}-{query.query_id}-{self._n}",
        )


def _perfect(model, query):
    return query.correct


def test_record_live_writes_one_json_line_per_decision(tmp_path):
    output = tmp_path / "recording.jsonl"
    query = ROUTE_CHOICE_QUERIES[0]

    summary = record_live(
        FakeClient(_perfect),
        budget_usd=10.0,
        pairs=[("anthropic/claude-sonnet-4.6", query)],
        output_path=output,
    )

    lines = output.read_text().strip().splitlines()
    assert len(lines) == 1 == summary.decisions
    entry = json.loads(lines[0])
    assert entry == {
        "type": "decision",
        "decision_type": "route_choice",
        "query_id": query.query_id,
        "model": "anthropic/claude-sonnet-4.6",
        "chosen": query.correct,
        "input_tokens": 120,
        "output_tokens": 5,
        "response_id": entry["response_id"],  # opaque, just must be present
    }
    assert entry["response_id"]


def test_recording_never_stores_the_correct_answer(tmp_path):
    """The recorder must never write an answer key to the file - only what the
    model actually said (spec: "never hand-author the recording's answers")."""
    output = tmp_path / "recording.jsonl"
    record_live(
        FakeClient(_perfect), budget_usd=10.0, pairs=None, output_path=output,
        roster=("anthropic/claude-sonnet-4.6",), queries=ROUTE_CHOICE_QUERIES[:3],
    )

    for line in output.read_text().strip().splitlines():
        entry = json.loads(line)
        assert "correct" not in entry


def test_recorded_file_round_trips_through_replay(tmp_path, world):
    output = tmp_path / "recording.jsonl"
    provider, exporter = world

    record_summary = record_live(
        FakeClient(_perfect),
        budget_usd=10.0,
        pairs=None,
        roster=("anthropic/claude-sonnet-4.6",),
        queries=ALL_QUERIES[:10],
        output_path=output,
    )

    entries = load_recording(output)
    assert len(entries) == record_summary.decisions == 10

    replay_summary = run_replay(output, world_provider=provider)
    assert replay_summary.decisions == 10
    assert replay_summary.correct == 10  # FakeClient(_perfect) always answers correctly


def test_record_live_also_emits_telemetry_like_an_ordinary_live_run(tmp_path, world):
    """Recording is additive, not a separate code path - a recording run
    populates the dashboards exactly like `--live` without `--record`."""
    output = tmp_path / "recording.jsonl"
    provider, exporter = world

    record_live(
        FakeClient(_perfect),
        budget_usd=10.0,
        pairs=None,
        roster=("anthropic/claude-sonnet-4.6",),
        queries=ALL_QUERIES[:5],
        output_path=output,
        world_provider=provider,
    )

    events = [
        s for s in exporter.get_finished_spans() if s.name == "gen_ai.evaluation.result"
    ]
    assert len(events) == 5


def test_record_live_respects_the_budget_cap(tmp_path, world):
    provider, _ = world
    output = tmp_path / "recording.jsonl"

    summary = record_live(
        FakeClient(_perfect, tokens=(300, 20)),
        budget_usd=0.0,
        pairs=None,
        roster=("anthropic/claude-sonnet-4.6",),
        queries=ALL_QUERIES,
        output_path=output,
        world_provider=provider,
    )

    assert summary.budget_exhausted
    assert summary.decisions == 0
    assert output.read_text() == ""


def test_record_live_creates_missing_parent_directories(tmp_path):
    output = tmp_path / "nested" / "dir" / "recording.jsonl"
    query = ROUTE_CHOICE_QUERIES[0]

    record_live(
        FakeClient(_perfect),
        budget_usd=10.0,
        pairs=[("anthropic/claude-sonnet-4.6", query)],
        output_path=output,
    )

    assert output.exists()
