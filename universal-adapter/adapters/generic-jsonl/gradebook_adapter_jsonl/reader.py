"""Read a JSONL stream of harness records and emit protocol records.

This is the fallback path (issue #101, strategy D): the harness has no usable
extension API, but it writes a log, or CI leaves a results file behind. Nothing
here imports any harness package, and nothing here grades anything.

The whole design follows from one property of the input. A JSONL file is read
while it is still being written. The last line is routinely half-flushed, a
crash truncates mid-object, and a shared log interleaves records this adapter
does not recognise. So the unit of failure is ONE LINE, never the stream:

- A line that cannot be parsed is reported with its line number and skipped.
  Every complete record before and after it is still ingested. Partial ingestion
  must not silently corrupt completed records, so a bad line is never allowed to
  discard a good one, and it is never allowed to pass silently either.
- A truncated FINAL line is reported separately from a corrupt one, because they
  need different responses. A corrupt line in the middle is a bug in whoever
  wrote it. An unterminated last line is normal for a file still being appended
  to, and the honest thing is to keep it verbatim so the next read can resume.
  The distinction is made by the newline: a line with a terminator was finished
  being written, one without it may not have been.
- A duplicate decision whose content differs is reported against its line and the
  already-held record is kept. Rejection, not overwrite (ADR 0004).

Records that are already protocol-shaped pass straight through. For a harness
whose lines are shaped differently, `normalize` takes a caller-supplied function
that converts one raw line into a protocol record. That seam is deliberately the
integrator's to fill: this package cannot know their field names, and guessing at
them is exactly how an adapter invents data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Union

from gradebook_adapter.costing import ConflictingDecisionIdError, EvidenceLedger
from gradebook_adapter.models import (
    DecisionEvidenceBundle,
    EvaluationManifest,
    OutcomeRecord,
    RecordDecodeError,
    UsageRecord,
)
from gradebook_adapter.validation import (
    ValidationError,
    format_errors,
    infer_record_type,
    validate_record,
)

# One line in, one protocol-shaped dict out, or None to drop the line on purpose.
Normalizer = Callable[[Mapping[str, Any]], Optional[Mapping[str, Any]]]

ProtocolRecord = Union[
    DecisionEvidenceBundle, UsageRecord, EvaluationManifest, OutcomeRecord
]


def _decode(record_type: str, document: Mapping[str, Any]) -> ProtocolRecord:
    """Decode a document already known to be valid for `record_type`.

    Spelled out rather than looked up in a table so the return type is the union
    a caller can actually branch on. A table of constructors erases that, and the
    erasure is what would let a manifest slip into the ledger as evidence.
    """
    if record_type == "decision-evidence-bundle":
        return DecisionEvidenceBundle.from_dict(document)
    if record_type == "usage-record":
        return UsageRecord.from_dict(document)
    if record_type == "evaluation-manifest":
        return EvaluationManifest.from_dict(document)
    return OutcomeRecord.from_dict(document)


@dataclass(frozen=True)
class LineError:
    """One rejected line, with everything needed to fix it.

    `reason` is a closed set so a caller can branch on it, and `detail` is the
    sentence a human reads. Both, because a machine and a person need different
    things from the same failure.
    """

    line_number: int
    reason: str
    detail: str
    errors: tuple[ValidationError, ...] = ()

    def __str__(self) -> str:
        head = f"line {self.line_number}: {self.detail}"
        if not self.errors:
            return head
        return head + "\n" + format_errors(self.errors)


REASONS: tuple[str, ...] = (
    "not_json",
    "not_an_object",
    "unknown_record_type",
    "invalid_record",
    "undecodable_record",
    "conflicting_decision_id",
    "dropped_by_normalizer",
)


@dataclass(frozen=True)
class IngestReport:
    """What one pass over a stream produced, including what it refused."""

    bundles: tuple[DecisionEvidenceBundle, ...] = ()
    usage: tuple[UsageRecord, ...] = ()
    manifests: tuple[EvaluationManifest, ...] = ()
    outcomes: tuple[OutcomeRecord, ...] = ()
    line_errors: tuple[LineError, ...] = ()
    incomplete_tail: Optional[str] = None
    lines_read: int = 0
    blank_lines: int = 0

    @property
    def accepted(self) -> int:
        return (
            len(self.bundles) + len(self.usage) + len(self.manifests)
            + len(self.outcomes)
        )

    @property
    def rejected(self) -> int:
        return len(self.line_errors)

    @property
    def records(self) -> tuple[ProtocolRecord, ...]:
        return (*self.bundles, *self.usage, *self.manifests, *self.outcomes)

    def summary(self) -> str:
        parts = [
            f"{self.accepted} record(s) accepted",
            f"{self.rejected} line(s) rejected",
        ]
        if self.incomplete_tail is not None:
            parts.append(
                f"final line of {len(self.incomplete_tail)} character(s) was "
                "unterminated and was left for the next read"
            )
        return "; ".join(parts)


def read_jsonl(
    source: Union[str, Iterable[str]],
    *,
    ledger: Optional[EvidenceLedger] = None,
    normalize: Optional[Normalizer] = None,
) -> IngestReport:
    """Parse a JSONL stream into protocol records, one line at a time.

    Pass a `ledger` to have accepted records deduplicated as they arrive; a
    conflicting duplicate decision id is reported against its line and the
    already-held record survives untouched.
    """
    lines = _raw_lines(source)
    bundles: list[DecisionEvidenceBundle] = []
    usage: list[UsageRecord] = []
    manifests: list[EvaluationManifest] = []
    outcomes: list[OutcomeRecord] = []
    errors: list[LineError] = []
    incomplete_tail: Optional[str] = None
    blank = 0

    for index, raw in enumerate(lines, start=1):
        is_last = index == len(lines)
        terminated = raw.endswith(("\n", "\r"))
        text = raw.strip().lstrip("﻿")
        if not text:
            blank += 1
            continue

        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            if is_last and not terminated:
                # Normal for a file still being appended to. Kept verbatim so the
                # next read can prepend it, rather than reported as corruption.
                incomplete_tail = raw
            else:
                errors.append(LineError(
                    index, "not_json",
                    f"could not be parsed as JSON ({exc.msg} at column "
                    f"{exc.colno}); the line was complete, so this is a bug in "
                    "whatever wrote it rather than a truncated write",
                ))
            continue

        if not isinstance(document, Mapping):
            errors.append(LineError(
                index, "not_an_object",
                f"is a JSON {type(document).__name__}, and every protocol record "
                "is an object",
            ))
            continue

        if normalize is not None:
            normalized = normalize(document)
            if normalized is None:
                errors.append(LineError(
                    index, "dropped_by_normalizer",
                    "the caller's normalizer returned None, so this line carried "
                    "nothing this protocol represents",
                ))
                continue
            document = normalized

        record_type = infer_record_type(document)
        if record_type is None:
            errors.append(LineError(
                index, "unknown_record_type",
                "does not carry a discriminating field (usage_id, outcome_id, "
                "evaluator/authority, or decision/subject), so it cannot be "
                "validated as any of the four record types. Supply a normalize "
                "function if these are harness-shaped rather than protocol-shaped.",
            ))
            continue

        problems = validate_record(document, record_type)
        if problems:
            errors.append(LineError(
                index, "invalid_record",
                f"is not a valid {record_type}", tuple(problems),
            ))
            continue

        try:
            record = _decode(record_type, document)
        except RecordDecodeError as exc:  # pragma: no cover - validation precedes it
            errors.append(LineError(index, "undecodable_record", str(exc)))
            continue

        if isinstance(record, DecisionEvidenceBundle):
            if ledger is not None:
                try:
                    ledger.add_bundle(record)
                except ConflictingDecisionIdError as exc:
                    # The held record wins and the stream keeps going: one bad
                    # line must not cost us the records around it.
                    errors.append(LineError(index, "conflicting_decision_id", str(exc)))
                    continue
            bundles.append(record)
        elif isinstance(record, UsageRecord):
            if ledger is not None:
                ledger.add_usage(record)
            usage.append(record)
        elif isinstance(record, OutcomeRecord):
            if ledger is not None:
                ledger.add_outcome(record)
            outcomes.append(record)
        else:
            # Manifests are the task owner's, not the harness's. They are carried
            # through when a stream happens to hold them, and never ingested into
            # the ledger, which holds evidence only.
            manifests.append(record)

    return IngestReport(
        bundles=tuple(bundles),
        usage=tuple(usage),
        manifests=tuple(manifests),
        outcomes=tuple(outcomes),
        line_errors=tuple(errors),
        incomplete_tail=incomplete_tail,
        lines_read=len(lines),
        blank_lines=blank,
    )


def read_jsonl_file(path: Union[str, Path], *,
                    ledger: Optional[EvidenceLedger] = None,
                    normalize: Optional[Normalizer] = None) -> IngestReport:
    """Same as `read_jsonl`, from a file. Decoding errors are lines, not crashes."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return read_jsonl(text, ledger=ledger, normalize=normalize)


def to_jsonl(records: Sequence[ProtocolRecord]) -> str:
    """Emit protocol records as JSONL, one record per line, newline terminated.

    Always terminated, including the last line. That is what lets a reader tell a
    finished file from one that is still being written, which is the distinction
    the whole reader is built around.
    """
    lines = [json.dumps(record.to_dict(), sort_keys=True) for record in records]
    return "".join(line + "\n" for line in lines)


class GenericJsonlAdapter:
    """The `HarnessEvidenceAdapter` shape from issue #101, over a JSONL source.

    Two methods, no harness imports, no grading. A harness that can produce a log
    file needs nothing else to be gradeable.
    """

    def __init__(self, *, normalize: Optional[Normalizer] = None) -> None:
        self._normalize = normalize

    def normalize_run(
        self, source: Union[str, Iterable[str]]
    ) -> tuple[DecisionEvidenceBundle, ...]:
        return read_jsonl(source, normalize=self._normalize).bundles

    def normalize_usage(
        self, source: Union[str, Iterable[str]]
    ) -> tuple[UsageRecord, ...]:
        return read_jsonl(source, normalize=self._normalize).usage


def _raw_lines(source: Union[str, Iterable[str]]) -> list[str]:
    """Lines WITH their terminators, because the terminator is load bearing."""
    if isinstance(source, str):
        return source.splitlines(keepends=True)
    return list(source)
