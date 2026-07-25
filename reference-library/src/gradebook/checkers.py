"""Reusable checkers and a closed reason-code enum (ticket #42, conventions §12).

Two jobs, both aimed at the same objection - that authoring a math grade is
costly and a bare true/false is not rigorous:

1. **Reusable checkers** for the decision shapes we had already hand-written
   more than once: verbatim substring (was `cleancut-proof/checkers.py::
   quote_checker`), fact-match against a record, tool-choice correctness, and
   did-it-complete. An adopter picks one instead of writing comparison logic.

2. **A closed, versioned `ReasonCode` enum.** Every check reports *why* it
   reached its verdict, not just whether it passed. "Not machine-checkable"
   stops being one generic bucket and becomes a specific, stable, queryable
   reason (`no_ground_truth`, `empty_answer`, ...). The recorder emits the
   winning reason as `augmentloop.grade.reason` so a dashboard can break grades
   down by it.

Deliberately NOT here: a weighted overall score. Collapsing metrics into one
blended number is exactly what ADR 0001 refuses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

# Bump when a code is added, removed, or its meaning changes. Recorded next to
# the frozen field table in docs/conventions.md §12 so a stored reason can
# always be resolved to the enum version that produced it.
REASON_CODES_VERSION = 1


class ReasonCode(str, Enum):
    """Why a check reached its verdict. Closed set - see conventions.md §12.

    An open-ended reason string becomes unqueryable the moment two people write
    the same reason differently, so this is a fixed enum, versioned above.
    """

    # --- machine-checked outcomes: the checker ran and decided ---
    MATCH = "match"          # answer provably equals / satisfies the ground truth
    MISMATCH = "mismatch"    # answer provably does not

    # --- not machine-checkable: the checker could not decide, and why ---
    NO_GROUND_TRUTH = "no_ground_truth"  # no provably-correct answer was supplied
    EMPTY_ANSWER = "empty_answer"        # the model produced nothing to check
    AMBIGUOUS = "ambiguous"              # ground truth under-specifies the answer

    @property
    def is_machine_checked(self) -> bool:
        """True only for MATCH/MISMATCH - the codes eligible for the headline."""
        return self in (ReasonCode.MATCH, ReasonCode.MISMATCH)


@dataclass(frozen=True)
class CheckResult:
    """A checker's verdict: did it pass, and the reason code for why.

    `passed` is only meaningful when `reason.is_machine_checked`; for the
    not-machine-checkable reasons `passed` is False and the reason carries the
    signal (per ADR 0001 such a decision never counts as correct).
    """

    passed: bool
    reason: ReasonCode

    @classmethod
    def decided(cls, passed: bool) -> "CheckResult":
        """A clean machine-checked verdict: MATCH if passed else MISMATCH."""
        return cls(passed, ReasonCode.MATCH if passed else ReasonCode.MISMATCH)


_WS_RE = re.compile(r"\s+")


def _squash_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _norm(value: Any) -> str:
    """Case- and whitespace-insensitive comparison form for scalar answers."""
    return _squash_ws(str(value)).casefold()


def verbatim_substring(chosen: str, reference: str) -> CheckResult:
    """The answer must appear verbatim inside a reference text.

    Whitespace is normalized on both sides and surrounding quote marks are
    tolerated; the words themselves must match exactly. The verbatim-quote check
    CleanCut's quote extraction needs, promoted out of that module.
    """
    if not reference:
        return CheckResult(False, ReasonCode.NO_GROUND_TRUTH)
    needle = _squash_ws(chosen).strip("\"'“”‘’ ")
    if not needle:
        return CheckResult(False, ReasonCode.EMPTY_ANSWER)
    return CheckResult.decided(needle in _squash_ws(reference))


def fact_match(chosen: Any, record: Any) -> CheckResult:
    """The answer must equal a known value from a record (normalized equality).

    For extracted scalars graded against a source of truth: a phone number vs.
    the CRM record, a total vs. the ledger. `None`/empty record means no ground
    truth; an empty answer is reported as such rather than as a mismatch.
    """
    if record is None or (isinstance(record, str) and not record.strip()):
        return CheckResult(False, ReasonCode.NO_GROUND_TRUTH)
    if chosen is None or (isinstance(chosen, str) and not chosen.strip()):
        return CheckResult(False, ReasonCode.EMPTY_ANSWER)
    return CheckResult.decided(_norm(chosen) == _norm(record))


def tool_choice(chosen: Any, expected: Any) -> CheckResult:
    """Did the agent pick the right tool / route / branch.

    Exact identity match on a low-cardinality choice (tool name, route id).
    `expected` of `None` means no correct choice was defined for this step.
    """
    if expected is None:
        return CheckResult(False, ReasonCode.NO_GROUND_TRUTH)
    if chosen is None:
        return CheckResult(False, ReasonCode.EMPTY_ANSWER)
    return CheckResult.decided(_norm(chosen) == _norm(expected))


def completed(chosen: Any, done_states: Iterable[Any]) -> CheckResult:
    """Did the decision reach a terminal success state.

    `chosen` is the final status; `done_states` is the set that counts as
    complete. An empty `done_states` means completion was never defined.
    """
    done = {_norm(s) for s in done_states}
    if not done:
        return CheckResult(False, ReasonCode.NO_GROUND_TRUTH)
    if chosen is None or (isinstance(chosen, str) and not chosen.strip()):
        return CheckResult(False, ReasonCode.EMPTY_ANSWER)
    return CheckResult.decided(_norm(chosen) in done)
