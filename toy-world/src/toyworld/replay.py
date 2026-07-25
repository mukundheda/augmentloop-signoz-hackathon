"""Replay mode: deterministic, no API keys, judge-runnable (spec stories 12-13;
extended by ticket #33 to three decision types).

Reads a committed JSONL recording of real model answers (written by
`recorder.py`'s `--live --record`, never hand-authored - see that module's
docstring) and replays them through the Gradebook library. Each recorded
decision becomes a math-graded `gen_ai.evaluation.result` event: the recording
stores only what the model actually answered (`chosen`, token counts, a
response id); the correct answer, checker, and difficulty are looked up fresh
from `world.QUERIES_BY_ID` by `query_id` - the same computation that produced
the original prompt - so a recording can never silently drift from the graph
it was recorded against.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from opentelemetry import metrics, trace

from gradebook import record_decision

from .world import QUERIES_BY_ID

TRACER_NAME = "toyworld"


@dataclass(frozen=True)
class RecordingEntry:
    """One parsed line of the recording - the recorder's raw fields, unchanged."""

    decision_type: str
    query_id: str
    model: str
    chosen: object
    input_tokens: int
    output_tokens: int
    response_id: str


def load_recording(path: Path) -> list[RecordingEntry]:
    """Parse the JSONL recording, order preserved.

    Every entry's `query_id` must resolve against `world.QUERIES_BY_ID` - a
    recording that references a query the current graph doesn't have is a
    stale recording, and replay fails loud rather than silently skipping it.
    """
    entries: list[RecordingEntry] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        kind = raw.pop("type")
        if kind != "decision":
            raise ValueError(f"unknown recording entry type: {kind!r}")
        entry = RecordingEntry(**raw)
        if entry.query_id not in QUERIES_BY_ID:
            raise ValueError(
                f"recording references unknown query_id {entry.query_id!r}; "
                f"the graph in world.py has changed since this recording was made"
            )
        entries.append(entry)
    return entries


@dataclass
class ReplaySummary:
    """What one replay run produced - printed for the judge, asserted in tests."""

    decisions: int = 0
    correct: int = 0
    total_cost_usd: float = 0.0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)
    by_model_type: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)
    by_model_type_difficulty: dict[tuple[str, str, str], dict[str, float]] = field(
        default_factory=dict
    )

    @property
    def cost_per_correct_usd(self) -> Optional[float]:
        """The headline number, or None when nothing was correct (never a fake 0)."""
        return self.total_cost_usd / self.correct if self.correct else None


def replay(
    recording_path: Path,
    *,
    world_provider: Optional[trace.TracerProvider] = None,
    world_meter_provider: Optional[metrics.MeterProvider] = None,
) -> ReplaySummary:
    """Replay one recording through the Gradebook library.

    Providers are injectable for tests (in-memory exporter/reader) and wired to
    OTLP by `__main__.py`. One trace per model (`model-run <model>`), one child
    span per query (named after decision type + query id, carrying
    `augmentloop.decision.difficulty`) - the same trace shape `live.run_live`
    produces, so a replay and a live run look identical in SigNoz.
    """
    provider = world_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer(TRACER_NAME)

    entries = load_recording(recording_path)
    summary = ReplaySummary()

    for model in _models_in_order(entries):
        model_entries = [e for e in entries if e.model == model]
        with tracer.start_as_current_span(f"model-run {model}"):
            for entry in model_entries:
                query = QUERIES_BY_ID[entry.query_id]
                with tracer.start_as_current_span(
                    f"{query.decision_type} {query.query_id} decision"
                ) as span:
                    span.set_attribute(
                        "augmentloop.decision.difficulty", query.difficulty
                    )
                    record_decision(
                        name=query.eval_name,
                        model=entry.model,
                        chosen=entry.chosen,
                        correct=query.correct,
                        input_tokens=entry.input_tokens,
                        output_tokens=entry.output_tokens,
                        decision_type=query.decision_type,
                        response_id=entry.response_id,
                        explanation=query.explain(entry.chosen),
                        checker=query.checker,
                        tracer_provider=provider,
                        meter_provider=world_meter_provider,
                    )

                    from gradebook.pricing import price

                    cost = price(entry.model, entry.input_tokens, entry.output_tokens)
                    is_correct = bool(query.checker(entry.chosen, query.correct))

                    summary.decisions += 1
                    summary.correct += int(is_correct)
                    summary.total_cost_usd += cost

                    row = summary.by_model.setdefault(
                        entry.model, {"decisions": 0, "correct": 0, "cost_usd": 0.0}
                    )
                    row["decisions"] += 1
                    row["correct"] += int(is_correct)
                    row["cost_usd"] += cost

                    type_row = summary.by_model_type.setdefault(
                        (entry.model, query.decision_type),
                        {"decisions": 0, "correct": 0, "cost_usd": 0.0},
                    )
                    type_row["decisions"] += 1
                    type_row["correct"] += int(is_correct)
                    type_row["cost_usd"] += cost

                    diff_row = summary.by_model_type_difficulty.setdefault(
                        (entry.model, query.decision_type, query.difficulty),
                        {"decisions": 0, "correct": 0, "cost_usd": 0.0},
                    )
                    diff_row["decisions"] += 1
                    diff_row["correct"] += int(is_correct)
                    diff_row["cost_usd"] += cost

    return summary


def _models_in_order(entries: Iterable[RecordingEntry]) -> list[str]:
    seen: list[str] = []
    for e in entries:
        if e.model not in seen:
            seen.append(e.model)
    return seen
