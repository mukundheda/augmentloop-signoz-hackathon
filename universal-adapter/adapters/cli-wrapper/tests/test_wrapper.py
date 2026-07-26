"""What the wrapper records, and what it refuses to conclude.

The wrapped processes here are real `python -c` invocations rather than fakes,
because the thing under test is an observation of a process and a mocked one
would not be an observation of anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from gradebook_adapter.models import (
    AbsentValue,
    ArtifactReference,
    CommandResultEvidence,
    EvaluationManifest,
    FileStateEvidence,
)
from gradebook_adapter.validation import validate_decision_evidence_bundle
from gradebook_adapter_cli import (
    COLLECTION_KEY,
    EXIT_WRAPPER_ERROR,
    SHARED_PROCESS_KEY,
    CollectionResult,
    WrapperError,
    collect,
    guard_self_grading,
    load_usage_export,
    main,
    run_process,
)
from gradebook_adapter_jsonl import read_jsonl


def python(*statements: str) -> list[str]:
    return [sys.executable, "-c", "; ".join(statements)]


def observe(*statements: str, **kwargs: object):  # type: ignore[no-untyped-def]
    return run_process(python(*statements), **kwargs)  # type: ignore[arg-type]


def collected(**kwargs: object) -> CollectionResult:
    observation = observe("pass")
    return collect(observation, harness="hermes",  # type: ignore[arg-type]
                   evaluation_name="repository.tests_pass", **kwargs)


def manifest_document(command: list[str]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "task_id": "repair-auth-017",
        "decision_type": "task_completion",
        "evaluation_name": "repository.tests_pass",
        "authority": "math",
        "evaluator": {
            "kind": "command_exit_code", "command": command, "expected_exit_code": 0,
        },
    }


# --------------------------------------------------------------------------
# Observation
# --------------------------------------------------------------------------


def test_the_wrapper_observes_exit_status_and_timing() -> None:
    observation = observe("import sys; sys.exit(3)")
    assert observation.exit_code == 3
    assert observation.pid > 0
    assert observation.duration_ms >= 0
    assert observation.started_at.endswith("Z")
    assert observation.ended_at >= observation.started_at
    assert observation.command_name.startswith(sys.executable)


def test_a_timeout_is_recorded_rather_than_hidden() -> None:
    observation = observe("import time; time.sleep(30)", timeout_seconds=0.5)
    assert observation.timed_out is True
    assert observation.duration_ms < 30_000


def test_a_command_that_cannot_start_is_a_wrapper_error_not_a_grade() -> None:
    with pytest.raises(WrapperError):
        run_process(["definitely-not-a-real-binary-9a8b7c"])


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------


def test_the_bundle_it_writes_is_a_valid_protocol_record() -> None:
    result = collected()
    assert validate_decision_evidence_bundle(result.bundle.to_dict()) == []


def test_process_identity_and_timing_land_in_ext_not_metadata() -> None:
    """Timestamps and pids are high cardinality, and metadata is for labels.

    `ext` is inert: no evaluator reads it, no costing rule reads it, and nothing
    in it reaches a telemetry attribute. That is exactly where a pid belongs.
    """
    result = collected()
    collection = (result.bundle.ext or {})[COLLECTION_KEY]

    assert result.bundle.metadata is None
    assert collection["evidence_only"] is True
    assert collection["exit_code"] == 0
    assert collection["wrapper"] == "gradebook-run"
    assert "started_at" in collection and "pid" in collection


def test_declared_artifacts_are_recorded_as_digests_never_as_contents(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "app.js"
    artifact.write_text("console.log('secret-ish source code')", encoding="utf-8")

    result = collected(artifacts=[artifact])
    files = [e for e in result.bundle.evidence if isinstance(e, FileStateEvidence)]

    assert len(files) == 1
    assert len(files[0].artifact_digest.digest) == 64
    assert files[0].artifact_digest.byte_length == artifact.stat().st_size
    assert "secret-ish" not in json.dumps(result.bundle.to_dict())


def test_the_wrapped_process_appears_as_command_result_evidence() -> None:
    result = collected()
    commands = [e for e in result.bundle.evidence
                if isinstance(e, CommandResultEvidence)]
    assert len(commands) == 1
    assert commands[0].evidence_id == "process"
    assert commands[0].exit_code == 0


def test_an_uncaptured_answer_is_absent_rather_than_empty() -> None:
    assert collected().bundle.decision.chosen == AbsentValue(reason="not_captured")


def test_a_chosen_artifact_becomes_a_reference_with_a_digest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace-after-agent.tar"
    workspace.write_bytes(b"whatever the agent produced")

    chosen = collected(chosen_artifact=workspace).bundle.decision.chosen
    assert isinstance(chosen, ArtifactReference)
    assert chosen.digest is not None


def test_a_generated_run_id_is_marked_as_generated() -> None:
    result = collected()
    collection = (result.bundle.ext or {})[COLLECTION_KEY]
    assert collection["run_id_generated"] is True
    assert any("generated by the wrapper" in note for note in result.notes)

    given = collected(run_id="run-42")
    assert given.bundle.subject.run_id == "run-42"
    assert (given.bundle.ext or {})[COLLECTION_KEY]["run_id_generated"] is False


def test_usage_is_not_attributed_to_a_decision_it_did_not_name(
    tmp_path: Path,
) -> None:
    """Silent attribution would fabricate exactly what coverage exists to measure."""
    export = tmp_path / "usage.json"
    export.write_text(json.dumps([{
        "schema_version": "1.0", "usage_id": "usage-1", "scope": "model_invocation",
        "run_id": "run-42", "cost_provenance": "unknown",
    }]), encoding="utf-8")
    records, problems = load_usage_export(export)
    assert problems == ()

    default = collected(usage=records)
    assert default.usage[0].decision_ids == ()

    opted_in = collected(usage=records, attribute_usage=True)
    assert opted_in.usage[0].decision_ids == (opted_in.decision_id,)
    assert any("operator assertion" in note for note in opted_in.notes)


def test_an_invalid_usage_record_is_reported_and_skipped(tmp_path: Path) -> None:
    export = tmp_path / "usage.jsonl"
    export.write_text(
        json.dumps({"schema_version": "1.0", "usage_id": "usage-1", "scope": "run",
                    "run_id": "run-42", "cost_provenance": "unknown"}) + "\n"
        + json.dumps({"schema_version": "1.0", "usage_id": "usage-2",
                      "scope": "tool_call", "run_id": "run-42",
                      "cost_provenance": "unknown"}) + "\n",
        encoding="utf-8",
    )
    records, problems = load_usage_export(export)
    assert [r.usage_id for r in records] == ["usage-1"]
    assert len(problems) == 1
    assert "/scope" in problems[0]


# --------------------------------------------------------------------------
# It does not grade
# --------------------------------------------------------------------------


def test_collection_produces_no_verdict_anywhere_in_the_record() -> None:
    """ADR 0006: this step observes, and the word "correct" never appears."""
    document = json.dumps(collected().bundle.to_dict())
    for word in ("correct", "verdict", "score", "authority", "gen_ai.evaluation"):
        assert word not in document


def test_evidence_only_is_stamped_and_the_shared_process_flag_is_absent() -> None:
    result = collected()
    assert SHARED_PROCESS_KEY not in (result.bundle.ext or {})
    assert (result.bundle.ext or {})[COLLECTION_KEY]["evidence_only"] is True


def test_shared_process_is_stamped_on_the_bundle_and_every_usage_record(
    tmp_path: Path,
) -> None:
    export = tmp_path / "usage.json"
    export.write_text(json.dumps({
        "schema_version": "1.0", "usage_id": "usage-1", "scope": "run",
        "run_id": "run-42", "cost_provenance": "unknown",
    }), encoding="utf-8")
    records, _ = load_usage_export(export)

    result = collected(usage=records, shared_process=True)

    assert (result.bundle.ext or {})[SHARED_PROCESS_KEY] is True
    assert (result.usage[0].ext or {})[SHARED_PROCESS_KEY] is True
    assert (result.bundle.ext or {})[COLLECTION_KEY]["evidence_only"] is False
    # And it survives the round trip, because that is the whole point of
    # recording it rather than printing it.
    reread = read_jsonl(result.to_jsonl())
    assert (reread.bundles[0].ext or {})[SHARED_PROCESS_KEY] is True
    assert (reread.usage[0].ext or {})[SHARED_PROCESS_KEY] is True


def test_grading_the_agent_by_its_own_exit_status_is_refused() -> None:
    """The narrowest detectable form of the ADR 0006 failure."""
    observation = observe("pass")
    manifest = EvaluationManifest.from_dict(
        manifest_document(list(observation.command))
    )
    with pytest.raises(WrapperError) as excinfo:
        guard_self_grading(manifest, observation)
    assert "the very process this wrapper supervised" in str(excinfo.value)


def test_a_different_command_in_the_manifest_is_allowed() -> None:
    observation = observe("pass")
    manifest = EvaluationManifest.from_dict(manifest_document(["npm", "test"]))
    guard_self_grading(manifest, observation)  # does not raise


# --------------------------------------------------------------------------
# End to end through the command line
# --------------------------------------------------------------------------


def test_the_default_run_writes_evidence_and_says_it_graded_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "evidence.jsonl"
    code = main([
        "--harness", "hermes", "--evaluation-name", "repository.tests_pass",
        "--run-id", "run-42", "--out", str(out),
        "--", *python("import sys; sys.exit(0)"),
    ])
    assert code == 0

    report = read_jsonl(out.read_text(encoding="utf-8"))
    assert len(report.bundles) == 1
    assert report.rejected == 0
    assert "evidence only, nothing was graded" in capsys.readouterr().err


def test_the_wrapper_exit_status_mirrors_the_harness(tmp_path: Path) -> None:
    out = tmp_path / "evidence.jsonl"
    code = main([
        "--harness", "hermes", "--evaluation-name", "e", "--out", str(out),
        "--", *python("import sys; sys.exit(7)"),
    ])
    # CI still sees a failing agent, and the evidence is written either way.
    assert code == 7
    assert out.exists()


def test_a_wrapper_error_uses_its_own_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Distinct from any harness status, so the two are never confused."""
    assert main(["--harness", "hermes", "--evaluation-name", "e"]) == EXIT_WRAPPER_ERROR
    assert "no harness command given" in capsys.readouterr().err


def test_evaluation_name_must_be_supplied_and_is_never_guessed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--harness", "hermes", "--", *python("pass")])
    assert code == EXIT_WRAPPER_ERROR
    assert "not guessable" in capsys.readouterr().err


def test_evaluate_without_a_manifest_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main([
        "--harness", "hermes", "--evaluation-name", "e", "--evaluate",
        "--", *python("pass"),
    ])
    assert code == EXIT_WRAPPER_ERROR
    assert "a verdict with no independent source of truth" in capsys.readouterr().err


def test_evaluate_warns_loudly_and_records_that_it_shared_a_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "task.json"
    manifest.write_text(json.dumps(manifest_document(["npm", "test"])),
                        encoding="utf-8")
    out = tmp_path / "evidence.jsonl"

    main([
        "--harness", "hermes", "--manifest", str(manifest), "--evaluate",
        "--out", str(out), "--", *python("pass"),
    ])

    stderr = capsys.readouterr().err
    assert "NOT suitable for benchmark or production grading" in stderr
    # No command_result names "npm test", so with no fallback there is nothing to
    # grade from, which is the correct answer rather than a convenient one.
    assert "NOT graded" in stderr

    report = read_jsonl(out.read_text(encoding="utf-8"))
    assert (report.bundles[0].ext or {})[SHARED_PROCESS_KEY] is True


def test_evidence_goes_to_stdout_when_no_out_is_given(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main([
        "--harness", "hermes", "--evaluation-name", "e",
        # Written backwards so the sentinel is in the child's OUTPUT and not in
        # its argv, which the wrapper legitimately records as process identity.
        "--", *python('import sys', 'sys.stdout.write("TUPTUO"[::-1])'),
    ])
    captured = capsys.readouterr()
    report = read_jsonl(captured.out)
    assert len(report.bundles) == 1
    assert report.rejected == 0
    # The agent's own output is echoed to stderr so the evidence stream on stdout
    # stays parseable, and it is never recorded as evidence.
    assert "OUTPUT" not in captured.out
    assert "OUTPUT" in captured.err


def test_the_written_file_is_readable_by_the_jsonl_adapter(tmp_path: Path) -> None:
    """The two adapters are two halves of one format, so this is the seam test."""
    artifact = tmp_path / "app.js"
    artifact.write_text("x", encoding="utf-8")
    out = tmp_path / "evidence.jsonl"

    main([
        "--harness", "hermes", "--evaluation-name", "repository.tests_pass",
        "--run-id", "run-42", "--task-id", "repair-auth-017",
        "--artifact", str(artifact), "--out", str(out),
        "--", *python("pass"),
    ])

    report = read_jsonl(out.read_text(encoding="utf-8"))
    assert report.rejected == 0
    assert report.incomplete_tail is None
    bundle = report.bundles[0]
    assert bundle.subject.run_id == "run-42"
    assert any(isinstance(e, FileStateEvidence) for e in bundle.evidence)


def test_a_secret_in_argv_is_redacted_out_of_process_identity() -> None:
    """argv is process identity, and process identity routinely carries a token.

    Redacted on the way into the record rather than on the way out of it: the
    evidence file outlives whatever was going to filter it later.
    """
    observation = observe("pass")
    leaky = observation.__class__(
        command=(*observation.command, "--api-key", "sk-live-abcdef0123456789"),
        pid=observation.pid, exit_code=0, started_at=observation.started_at,
        ended_at=observation.ended_at, duration_ms=1,
    )
    result = collect(leaky, harness="hermes", evaluation_name="e")

    document = json.dumps(result.bundle.to_dict())
    assert "sk-live-abcdef0123456789" not in document
    assert "[redacted]" in document
