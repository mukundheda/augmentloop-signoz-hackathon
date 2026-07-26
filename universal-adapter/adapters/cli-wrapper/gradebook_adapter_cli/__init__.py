"""CLI wrapper: integrate a harness without modifying it, and without grading it.

`gradebook-run` supervises a harness process from the outside and writes an
evidence bundle. It never produces a verdict by default, because the agent it
supervises has write access to the workspace an evaluator would run in, and an
evaluator the graded agent could have edited is not an independent one
(ADR 0006). Evaluation is a separate step against a manifest the task owner
supplies.
"""

from .wrapper import (
    COLLECTION_KEY,
    EXIT_WRAPPER_ERROR,
    SHARED_PROCESS_KEY,
    UNSAFE_EVALUATE_WARNING,
    WRAPPER_ID,
    WRAPPER_VERSION,
    CollectionResult,
    ProcessObservation,
    WrapperError,
    collect,
    digest_file,
    evaluate_locally,
    guard_self_grading,
    ledger_from,
    load_manifest,
    load_usage_export,
    main,
    run_process,
)

__all__ = [
    "COLLECTION_KEY",
    "EXIT_WRAPPER_ERROR",
    "SHARED_PROCESS_KEY",
    "UNSAFE_EVALUATE_WARNING",
    "WRAPPER_ID",
    "WRAPPER_VERSION",
    "CollectionResult",
    "ProcessObservation",
    "WrapperError",
    "collect",
    "digest_file",
    "evaluate_locally",
    "guard_self_grading",
    "ledger_from",
    "load_manifest",
    "load_usage_export",
    "main",
    "run_process",
]
