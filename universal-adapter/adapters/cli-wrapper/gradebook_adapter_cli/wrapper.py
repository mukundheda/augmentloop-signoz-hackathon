"""Wrap a harness process and record what it did. Do not grade it.

    gradebook-run --harness hermes --evaluation-name repository.tests_pass \\
                  --artifact dist/app.js --out evidence.jsonl -- hermes run ...

This is strategy C from issue #101: integration without modifying the harness.
The wrapper observes a process from the outside, so it works for a harness with
no plugin API, no hooks and no OpenTelemetry, including one that does not exist
yet. It imports nothing from any harness.

WHY IT DOES NOT GRADE (ADR 0006). The wrapper supervises an agent whose entire
job is to modify a workspace. Running the evaluator here would run it inside that
same workspace, moments after the agent finished editing it, which gives the
agent being graded write access to the thing that grades it. It needs no malice:
an agent asked to make the tests pass can edit the tests, weaken an assertion,
add a skip marker, or change a script the manifest's command resolves through.
The wrapper would faithfully observe exit code 0 and report a math grade. There
would be an evaluator result; it just would not be independent.

So collection and evaluation are two steps, and this is the first one. It writes
evidence: process identity, start and end time, exit status, declared artifacts
and their digests, and usage exports. A separate evaluation step reads the
manifest, which the task owner supplies rather than the agent, and produces the
verdict. Artifact digests are what make that separation real rather than
ceremonial: they record what the workspace looked like when the agent stopped, so
a later evaluator can tell it is being asked to grade something other than what
was submitted.

`--evaluate` exists for local development, where the operator is the agent's
supervisor and the convenience is worth more than the independence. It is opt-in,
it is UNSUITABLE FOR BENCHMARK OR PRODUCTION GRADING, and when used it stamps
every record it writes with the fact that collection and evaluation shared a
process, so nobody has to reconstruct that later from a shell history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from gradebook_adapter.costing import EvidenceLedger
from gradebook_adapter.emission import redact
from gradebook_adapter.evaluation import (
    EvaluationContext,
    EvaluationError,
    EvaluationResult,
    evaluate,
)
from gradebook_adapter.models import (
    AbsentValue,
    ArtifactReference,
    CommandResultEvidence,
    Correlation,
    Decision,
    DecisionEvidenceBundle,
    Digest,
    EvaluationManifest,
    EvidenceItem,
    FileStateEvidence,
    RecordDecodeError,
    Subject,
    UsageRecord,
    resolve_decision_identity,
)
from gradebook_adapter.validation import (
    format_errors,
    validate_evaluation_manifest,
    validate_usage_record,
)
# The wrapper WRITES the evidence file that the generic JSONL adapter READS. They
# are two halves of one format, so they share the writer rather than each owning
# a copy of it that can drift.
from gradebook_adapter_jsonl import to_jsonl

WRAPPER_ID = "gradebook-run"
WRAPPER_VERSION = "0.0.1"

# Stamped into `ext`, the one namespace where a field this protocol does not
# define is legal. It is inert: no evaluator and no costing rule reads it, and
# nothing in it reaches telemetry. It exists so the provenance of a grade
# survives in the record instead of in somebody's memory.
SHARED_PROCESS_KEY = "gradebook_adapter.collection_and_evaluation_shared_process"
COLLECTION_KEY = "gradebook_adapter.collection"

EXIT_WRAPPER_ERROR = 2

UNSAFE_EVALUATE_WARNING = (
    "WARNING: --evaluate ran the evaluator in the same process that supervised "
    "the agent, inside the workspace the agent just edited. The agent had write "
    "access to the thing that graded it. This is for local development only and "
    "is NOT suitable for benchmark or production grading (ADR 0006). The records "
    "written carry this fact."
)


class WrapperError(Exception):
    """A wrapper-level failure: bad flags, unreadable artifact, bad manifest.

    Distinct from the wrapped process failing, which is data rather than an
    error, and is why the two use different exit codes.
    """


# --------------------------------------------------------------------------
# Observation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcessObservation:
    """What the wrapper saw from outside the process. All of it measured."""

    command: tuple[str, ...]
    pid: int
    exit_code: int
    started_at: str
    ended_at: str
    duration_ms: int
    timed_out: bool = False
    working_directory: Optional[str] = None

    @property
    def command_name(self) -> str:
        """argv joined by single spaces: the name a manifest would have to use.

        Deliberately the same rule the command_exit_code evaluator matches on, so
        a manifest that really does intend to grade the wrapped process by its own
        exit status has to name it exactly, in a file the task owner owns.
        """
        return " ".join(self.command)


def _now() -> str:
    """RFC 3339 in UTC. Observed, never adjusted, never invented."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_process(command: Sequence[str], *, working_directory: Optional[str] = None,
                timeout_seconds: Optional[float] = None,
                capture_stdout: bool = False) -> ProcessObservation:
    """Run the harness and observe it. Its output is never stored as evidence.

    Raw stdout is deliberately not captured into the record: tool output and
    patches carry credentials, source code and personal data, and issue #101 is
    explicit that raw payloads are excluded by default. `capture_stdout` only
    buffers it so it can be echoed to stderr when the evidence file is going to
    stdout; it never reaches the bundle.
    """
    if not command:
        raise WrapperError("no command to run; put it after -- ")

    started = _now()
    started_at = datetime.now(timezone.utc)
    try:
        process = subprocess.Popen(  # noqa: S603 - argv form, no shell
            list(command),
            cwd=working_directory,
            stdout=subprocess.PIPE if capture_stdout else None,
        )
    except OSError as exc:
        raise WrapperError(f"could not start {command[0]!r}: {exc}") from None

    timed_out = False
    try:
        stdout, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, _ = process.communicate()

    if capture_stdout and stdout:
        # Echoed, not recorded. The operator still sees their agent's output.
        sys.stderr.buffer.write(stdout)
        sys.stderr.flush()

    ended_at = datetime.now(timezone.utc)
    if process.returncode is None:  # pragma: no cover - communicate() has waited
        raise WrapperError(
            "the process exited without an exit status, so there is nothing to "
            "record; a fabricated status would be exactly the invention this "
            "protocol forbids"
        )
    return ProcessObservation(
        command=tuple(command),
        pid=process.pid,
        exit_code=process.returncode,
        started_at=started,
        ended_at=_now(),
        duration_ms=int((ended_at - started_at).total_seconds() * 1000),
        timed_out=timed_out,
        working_directory=working_directory,
    )


def digest_file(path: Path) -> Digest:
    """sha256 of a file's bytes, with its length. The point of the whole ADR.

    A digest records what the workspace looked like when the agent stopped, so a
    later evaluator can detect that it is grading something else.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise WrapperError(f"could not read declared artifact {path}: {exc}") from None
    return Digest(digest=hashlib.sha256(data).hexdigest(), byte_length=len(data))


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectionResult:
    bundle: DecisionEvidenceBundle
    usage: tuple[UsageRecord, ...]
    decision_id: str
    notes: tuple[str, ...] = ()

    def to_jsonl(self) -> str:
        return to_jsonl((self.bundle, *self.usage))


def collect(
    observation: ProcessObservation,
    *,
    harness: str,
    evaluation_name: str,
    decision_type: str = "task_completion",
    run_id: Optional[str] = None,
    harness_version: Optional[str] = None,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    model: Optional[str] = None,
    provider_response_id: Optional[str] = None,
    artifacts: Sequence[Path] = (),
    chosen_artifact: Optional[Path] = None,
    usage: Sequence[UsageRecord] = (),
    attribute_usage: bool = False,
    shared_process: bool = False,
) -> CollectionResult:
    """Turn one observed process into one evidence bundle. No verdict anywhere."""
    notes: list[str] = []
    generated_run_id = run_id is None
    if generated_run_id:
        # A wrapper invocation genuinely IS a new run, so minting an id here is
        # observation rather than invention. It is recorded as generated so nobody
        # later mistakes it for an id the harness knows about.
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        notes.append(f"run_id {run_id} was generated by the wrapper, not observed")

    # Process identity is argv, and argv routinely carries a token: nobody thinks
    # of `--api-key sk-...` as a payload until it is sitting in an evidence file
    # that gets shared. Redacted on the way in, not on the way out, because the
    # record outlives whatever was going to filter it later.
    command_name = redact(observation.command_name) or observation.command_name

    evidence: list[EvidenceItem] = [
        CommandResultEvidence(
            evidence_id="process",
            command_name=command_name,
            exit_code=observation.exit_code,
            duration_ms=observation.duration_ms,
        )
    ]
    for index, artifact in enumerate(artifacts, start=1):
        evidence.append(FileStateEvidence(
            evidence_id=f"artifact-{index}",
            path=str(artifact).replace(os.sep, "/"),
            artifact_digest=digest_file(artifact),
        ))

    if chosen_artifact is not None:
        chosen: Any = ArtifactReference(
            value=str(chosen_artifact).replace(os.sep, "/"),
            digest=digest_file(chosen_artifact),
        )
    else:
        # Not captured, and said so. An empty inline value would be a claim that
        # the agent produced nothing.
        chosen = AbsentValue(reason="not_captured")

    collection: dict[str, Any] = {
        "wrapper": WRAPPER_ID,
        "wrapper_version": WRAPPER_VERSION,
        "pid": observation.pid,
        "started_at": observation.started_at,
        "ended_at": observation.ended_at,
        "duration_ms": observation.duration_ms,
        "exit_code": observation.exit_code,
        "timed_out": observation.timed_out,
        "evidence_only": not shared_process,
        "run_id_generated": generated_run_id,
    }
    if observation.working_directory is not None:
        collection["working_directory"] = observation.working_directory

    # Timestamps and a pid are high cardinality, so they go in `ext` and never in
    # `metadata`, which is for low-cardinality labels and is the field a metric
    # dimension would ever be built from.
    ext: dict[str, Any] = {COLLECTION_KEY: collection}
    if shared_process:
        ext[SHARED_PROCESS_KEY] = True

    bundle = DecisionEvidenceBundle(
        decision=Decision(
            decision_type=decision_type,
            evaluation_name=evaluation_name,
            chosen=chosen,
        ),
        subject=Subject(
            harness=harness,
            run_id=run_id or "",
            harness_version=harness_version,
            agent_id=agent_id,
            session_id=session_id,
            model=model,
        ),
        # Omitted entirely when nothing correlates, rather than written as an
        # empty object. An empty correlation block reads like a claim that we
        # looked and found nothing, when in fact nobody supplied anything.
        correlation=(
            Correlation(task_id=task_id, provider_response_id=provider_response_id)
            if (task_id is not None or provider_response_id is not None)
            else None
        ),
        evidence=tuple(evidence),
        usage_refs=tuple(record.usage_id for record in usage),
        ext=ext,
    )
    decision_id = resolve_decision_identity(bundle).decision_id

    prepared: list[UsageRecord] = []
    for record in usage:
        updated = record
        if attribute_usage and not record.decision_ids:
            # An operator assertion, opt-in, because one wrapped run is one
            # decision. Never done by default: silently attributing usage to a
            # decision it did not name would fabricate the attribution that cost
            # coverage exists to measure.
            updated = _replace_usage(record, decision_ids=(decision_id,))
        if shared_process:
            updated = _replace_usage(
                updated, ext={**dict(updated.ext or {}), SHARED_PROCESS_KEY: True}
            )
        prepared.append(updated)

    if attribute_usage and prepared:
        notes.append(
            f"{sum(1 for r in usage if not r.decision_ids)} usage record(s) were "
            f"attributed to {decision_id} by --attribute-usage, which is an "
            "operator assertion and not something the harness reported"
        )

    return CollectionResult(bundle=bundle, usage=tuple(prepared),
                            decision_id=decision_id, notes=tuple(notes))


def _replace_usage(record: UsageRecord, **changes: Any) -> UsageRecord:
    data = {
        field: getattr(record, field)
        for field in (
            "usage_id", "scope", "run_id", "cost_provenance", "agent_id",
            "parent_agent_id", "contains_usage_ids", "decision_ids",
            "provider_response_id", "model", "input_tokens", "output_tokens",
            "cached_input_tokens", "provider_cost_usd", "pricing_table_id", "ext",
        )
    }
    data.update(changes)
    return UsageRecord(**data)


def load_usage_export(path: Path) -> tuple[tuple[UsageRecord, ...], tuple[str, ...]]:
    """Read a harness usage export: a JSON array, one object, or JSONL.

    Invalid records are reported and skipped rather than fixed up. A usage record
    nobody can validate contributes nothing but a wrong number.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WrapperError(f"could not read usage export {path}: {exc}") from None

    documents: list[Any] = []
    try:
        parsed = json.loads(text)
        documents = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                documents.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise WrapperError(
                    f"{path} is neither JSON nor JSONL: line {number} does not "
                    f"parse ({exc.msg})"
                ) from None

    records: list[UsageRecord] = []
    problems: list[str] = []
    for index, document in enumerate(documents):
        errors = validate_usage_record(document)
        if errors:
            problems.append(f"{path}[{index}] is not a valid usage record:\n"
                            + format_errors(errors))
            continue
        try:
            records.append(UsageRecord.from_dict(document))
        except RecordDecodeError as exc:  # pragma: no cover - validation precedes it
            problems.append(f"{path}[{index}]: {exc}")
    return tuple(records), tuple(problems)


def load_manifest(path: Path) -> EvaluationManifest:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WrapperError(f"could not read manifest {path}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise WrapperError(f"manifest {path} is not JSON: {exc.msg}") from None
    errors = validate_evaluation_manifest(document)
    if errors:
        raise WrapperError(f"manifest {path} is not valid:\n{format_errors(errors)}")
    return EvaluationManifest.from_dict(document)


# --------------------------------------------------------------------------
# The opt-in that is not the default
# --------------------------------------------------------------------------


def guard_self_grading(manifest: EvaluationManifest,
                       observation: ProcessObservation) -> None:
    """Refuse to grade the wrapped process by its own exit status.

    The narrowest, most detectable form of the ADR 0006 failure: a manifest whose
    command IS the command we just supervised. That is not independent evaluation,
    it is the agent's own exit code wearing a manifest.
    """
    evaluator = manifest.evaluator
    command = getattr(evaluator, "command", None)
    if command is not None and tuple(command) == observation.command:
        raise WrapperError(
            f"refusing to evaluate: the manifest's command {' '.join(command)!r} "
            "is the very process this wrapper supervised, so the grade would be "
            "the agent's own exit status. Declare the check the task owner "
            "actually wants, and run it as a separate step."
        )


def evaluate_locally(bundle: DecisionEvidenceBundle,
                     manifest: EvaluationManifest) -> EvaluationResult:
    """Run the evaluator here, which is what --evaluate exists to make explicit.

    No checker registry is wired, so a callback manifest fails loud rather than
    silently producing nothing: a CLI cannot own the application's checkers.
    """
    return evaluate(bundle, manifest, context=EvaluationContext())


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=WRAPPER_ID,
        description=(
            "Wrap a harness process and write an evidence bundle. Collection "
            "only: this does not grade, because the agent it supervises has "
            "write access to the workspace an evaluator would run in (ADR 0006)."
        ),
        epilog=(
            "Put the harness command after --, e.g.\n"
            "  gradebook-run --harness hermes "
            "--evaluation-name repository.tests_pass \\\n"
            "                --out evidence.jsonl -- hermes run task.yaml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--harness", required=True,
                        help="harness name, e.g. hermes. Not guessed from argv.")
    parser.add_argument("--harness-version")
    parser.add_argument("--evaluation-name",
                        help="what is being graded; taken from --manifest if given")
    parser.add_argument("--decision-type",
                        help="unit of decision; taken from --manifest if given, "
                             "otherwise task_completion")
    parser.add_argument("--run-id", help="generated if omitted, and marked as such")
    parser.add_argument("--agent-id")
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--model", help="provider model slug; never inferred")
    parser.add_argument("--provider-response-id")
    parser.add_argument("--artifact", action="append", default=[], type=Path,
                        help="file whose state is evidence; recorded as a path "
                             "and a sha256 digest, never as contents")
    parser.add_argument("--chosen-artifact", type=Path,
                        help="the artifact that IS the agent's answer; becomes "
                             "decision.chosen as an artifact reference")
    parser.add_argument("--usage-export", action="append", default=[], type=Path,
                        help="harness usage records (JSON array, object or JSONL)")
    parser.add_argument("--attribute-usage", action="store_true",
                        help="attribute usage records that name no decision to "
                             "this run's decision. An operator assertion, off by "
                             "default.")
    parser.add_argument("--manifest", type=Path,
                        help="evaluation manifest; read for naming, and required "
                             "by --evaluate")
    parser.add_argument("--evaluate", action="store_true",
                        help="LOCAL DEVELOPMENT ONLY. Runs the evaluator in this "
                             "process, inside the workspace the agent just "
                             "edited. Unsuitable for benchmark or production "
                             "grading; the records written say so.")
    parser.add_argument("--out", type=Path,
                        help="evidence JSONL destination; stdout when omitted")
    parser.add_argument("--cwd", help="working directory for the wrapped process")
    parser.add_argument("--timeout", type=float,
                        help="seconds before the wrapped process is killed")
    return parser


def split_argv(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    """Everything after the first bare -- is the harness command."""
    argv = list(argv)
    if "--" not in argv:
        return argv, []
    index = argv.index("--")
    return argv[:index], argv[index + 1:]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Collect evidence, write it, and report. Never grade unless told to."""
    own, command = split_argv(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(own)

    try:
        return _run(args, command)
    except WrapperError as exc:
        print(f"{WRAPPER_ID}: {exc}", file=sys.stderr)
        return EXIT_WRAPPER_ERROR


def _run(args: argparse.Namespace, command: list[str]) -> int:
    if not command:
        raise WrapperError(
            "no harness command given; put it after --, e.g. "
            "gradebook-run --harness hermes -- hermes run task.yaml"
        )

    manifest: Optional[EvaluationManifest] = None
    if args.manifest is not None:
        manifest = load_manifest(args.manifest)
    if args.evaluate and manifest is None:
        raise WrapperError("--evaluate needs --manifest: a verdict with no "
                           "independent source of truth is not a verdict")

    evaluation_name = args.evaluation_name or (
        manifest.evaluation_name if manifest else None
    )
    if evaluation_name is None:
        raise WrapperError(
            "--evaluation-name is required (or supply --manifest, which names "
            "it); this is the question being graded and it is not guessable"
        )
    decision_type = args.decision_type or (
        manifest.decision_type if manifest else "task_completion"
    )

    usage: list[UsageRecord] = []
    problems: list[str] = []
    for export in args.usage_export:
        records, issues = load_usage_export(export)
        usage.extend(records)
        problems.extend(issues)

    to_stdout = args.out is None
    observation = run_process(
        command, working_directory=args.cwd, timeout_seconds=args.timeout,
        # When the evidence is going to stdout, the child's stdout is echoed to
        # stderr instead, so the evidence stream stays parseable.
        capture_stdout=to_stdout,
    )

    result = collect(
        observation,
        harness=args.harness,
        evaluation_name=evaluation_name,
        decision_type=decision_type,
        run_id=args.run_id,
        harness_version=args.harness_version,
        agent_id=args.agent_id,
        session_id=args.session_id,
        task_id=args.task_id,
        model=args.model,
        provider_response_id=args.provider_response_id,
        artifacts=args.artifact,
        chosen_artifact=args.chosen_artifact,
        usage=usage,
        attribute_usage=args.attribute_usage,
        shared_process=bool(args.evaluate),
    )

    payload = result.to_jsonl()
    if to_stdout:
        sys.stdout.write(payload)
    else:
        args.out.write_text(payload, encoding="utf-8")

    for problem in problems:
        print(f"{WRAPPER_ID}: {problem}", file=sys.stderr)
    for note in result.notes:
        print(f"{WRAPPER_ID}: {note}", file=sys.stderr)
    print(
        f"{WRAPPER_ID}: collected 1 bundle and {len(result.usage)} usage record(s) "
        f"for decision {result.decision_id}; the wrapped process exited "
        f"{observation.exit_code}",
        file=sys.stderr,
    )

    if args.evaluate and manifest is not None:
        guard_self_grading(manifest, observation)
        print(UNSAFE_EVALUATE_WARNING, file=sys.stderr)
        try:
            verdict = evaluate_locally(result.bundle, manifest)
        except EvaluationError as exc:
            raise WrapperError(f"evaluation failed: {exc}") from None
        print(
            f"{WRAPPER_ID}: {'graded' if verdict.graded else 'NOT graded'} "
            f"({verdict.reason.value}), "
            f"authority {verdict.authority.value if verdict.authority else 'none'}: "
            f"{verdict.detail}",
            file=sys.stderr,
        )
    elif not args.evaluate:
        print(
            f"{WRAPPER_ID}: evidence only, nothing was graded. Evaluate this file "
            "in a separate step against a manifest the task owner supplies.",
            file=sys.stderr,
        )

    # The wrapper's own status mirrors the harness, so CI still sees a failing
    # agent. A wrapper-level failure uses a distinct code so the two are never
    # confused for each other.
    return observation.exit_code


def ledger_from(result: CollectionResult) -> EvidenceLedger:
    """Convenience for callers that want the records in memory, not on disk."""
    ledger = EvidenceLedger()
    ledger.add_bundle(result.bundle)
    for record in result.usage:
        ledger.add_usage(record)
    return ledger
