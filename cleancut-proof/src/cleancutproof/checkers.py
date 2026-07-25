"""Math checkers for the CleanCut substrate (ticket #11).

Two provable checks, per the ADR 0001 rule that only machine-checkable answers
feed the headline:

- **Filler detection**: ground truth is a lexical scan of the transcript
  against CleanCut's own PURE_FILLERS list (hesitation sounds - um, uh, er...).
  Deliberately *only* the pure fillers: contextual ones ("like", "actually")
  are judgment calls with no provable answer, so they are excluded from the
  math grade - exactly the ADR 0001 line. The list below mirrors
  `app/core/filler_detector.py::PURE_FILLERS` in the CleanCut codebase; re-sync
  it at capture time if CleanCut's list changes.
- **Quote extraction**: the pulled quote must be a verbatim substring of the
  transcript (whitespace-normalized, case preserved). A quote the transcript
  never said is provably wrong.
"""

from __future__ import annotations

import re

from gradebook import verbatim_substring

# Mirror of CleanCut's PURE_FILLERS (hesitation sounds only - lexically provable).
PURE_FILLERS: frozenset[str] = frozenset(
    {
        "um", "uh", "er", "ah", "eh", "hm", "hmm", "mm", "mmm",
        "umm", "uhh", "ahh", "ehh",
    }
)

_WORD_RE = re.compile(r"[a-z']+")


def lexical_fillers(transcript: str) -> list[str]:
    """The provably-correct answer: every pure-filler token in the transcript.

    Returns the ordered list of filler occurrences (duplicates preserved) so
    the grade compares full detections, not just vocabulary.
    """
    return [w for w in _WORD_RE.findall(transcript.lower()) if w in PURE_FILLERS]


def normalize_words(text: str) -> list[str]:
    """Lower-case word tokens - the comparison form for filler answers."""
    return _WORD_RE.findall(text.lower())


def filler_checker(chosen: str, correct: list[str]) -> bool:
    """Compare a model's filler answer against the lexical ground truth.

    `chosen` is the model's raw answer text (a list of words in any format);
    `correct` is `lexical_fillers(transcript)`. Correct means the model found
    exactly the pure-filler occurrences - same words, same counts, order
    ignored (models list vocabulary in any order; a missed or invented
    occurrence is a miss).
    """
    return sorted(normalize_words(chosen)) == sorted(correct)


def quote_checker(chosen: str, correct: str) -> bool:
    """The pulled quote must appear verbatim in the transcript.

    Now a thin adopter of the library's reusable `verbatim_substring` checker
    (ticket #42) - the verbatim-substring logic lives in `gradebook.checkers`,
    not hand-rolled here. Returns a bool for the runner's per-model tally;
    `runner.run_detections` passes `verbatim_substring` itself to
    `record_decision`, so the emitted grade still carries the reason code.
    """
    return verbatim_substring(chosen, correct).passed
