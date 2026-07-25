"""CleanCut real-substrate proof (T8): grade a real product's AI, honestly.

Filler detection and quote extraction are math-graded against provable truth;
historical clip-scoring decisions are graded by reality (kept vs discarded).
Blog/screencast material only - client content never enters the repo.
"""

from .checkers import PURE_FILLERS, filler_checker, lexical_fillers, quote_checker
from .runner import (
    ROSTER,
    BudgetExceededError,
    ModelCaller,
    ModelReply,
    ProofSummary,
    openrouter_caller,
    replay_clip_outcomes,
    run_detections,
)

__all__ = [
    "run_detections",
    "replay_clip_outcomes",
    "openrouter_caller",
    "ModelCaller",
    "ModelReply",
    "ProofSummary",
    "BudgetExceededError",
    "ROSTER",
    "PURE_FILLERS",
    "lexical_fillers",
    "filler_checker",
    "quote_checker",
]
