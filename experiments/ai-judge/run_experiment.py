"""Run the ai_judge SIDE EXPERIMENT over a committed toy-world recording.

Reads toy-world/recordings/replay-v2.jsonl READ-ONLY (never writes to it or
to any other committed run artifact), re-derives each decision's math grade
the same way toyworld.replay does (query.checker(chosen, query.correct),
looked up fresh from world.QUERIES_BY_ID - never a stored value), and asks a
real LLM (grader.AiJudgeGrader) to grade the same decision blind, i.e. without
ever being shown query.correct.

Writes two output files into this directory (both gitignored-by-convention
scratch, not committed run artifacts of the real product):
  - results.jsonl   one row per judged decision, full detail, for reproducing
                    every number in WRITEUP.md and quoting disagreements
  - summary.json    the aggregate confusion matrix + cost recompute

Usage:
  python3 experiments/ai-judge/run_experiment.py \\
      --recording toy-world/recordings/replay-v2.jsonl \\
      --judge-model qwen/qwen-2.5-72b-instruct \\
      --out experiments/ai-judge/results.jsonl \\
      --concurrency 8

Requires OPENROUTER_API_KEY (repo-root .env, or already exported). Never
prints or logs the key itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "reference-library" / "src"))
sys.path.insert(0, str(REPO_ROOT / "toy-world" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gradebook.pricing import price  # noqa: E402
from toyworld.openrouter import OpenRouterClient  # noqa: E402
from toyworld.replay import load_recording  # noqa: E402
from toyworld.world import QUERIES_BY_ID  # noqa: E402

from grader import AiJudgeGrader  # noqa: E402


def _load_env_file(path: Path) -> None:
    """Minimal .env loader (no python-dotenv dependency in this repo's env):
    only sets vars not already present in the environment, and never prints
    or logs any value - the key must stay out of stdout/history."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def _judge_one(grader: AiJudgeGrader, entry, query) -> dict:
    verdict = grader.judge(problem_prompt=query.prompt, chosen=entry.chosen)
    checker_correct = bool(query.checker(entry.chosen, query.correct))
    decision_cost_usd = price(entry.model, entry.input_tokens, entry.output_tokens)
    return {
        "query_id": entry.query_id,
        "decision_type": entry.decision_type,
        "model": entry.model,
        "chosen": entry.chosen,
        "correct_answer": query.correct if not isinstance(query.correct, float) else round(query.correct, 3),
        "checker_label": "correct" if checker_correct else "incorrect",
        "decision_cost_usd": decision_cost_usd,
        "judge_label": verdict.label,
        "judge_reasoning": verdict.reasoning,
        "judge_raw_text": verdict.raw_text,
        "judge_input_tokens": verdict.input_tokens,
        "judge_output_tokens": verdict.output_tokens,
        "judge_reported_cost_usd": verdict.reported_cost_usd,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recording",
        type=Path,
        default=REPO_ROOT / "toy-world" / "recordings" / "replay-v2.jsonl",
    )
    parser.add_argument("--judge-model", default="qwen/qwen-2.5-72b-instruct")
    parser.add_argument(
        "--out", type=Path, default=Path(__file__).resolve().parent / "results.jsonl"
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=Path(__file__).resolve().parent / "summary.json",
    )
    parser.add_argument(
        "--decision-type",
        default=None,
        help="Restrict to one decision type (route_choice|eta_estimate|next_hop). "
        "Default: all.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap the number of decisions judged."
    )
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    _load_env_file(REPO_ROOT / ".env")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY not set (checked env and repo-root .env)")

    decisions, _outcomes = load_recording(args.recording)  # read-only; recording untouched
    if args.decision_type:
        decisions = [d for d in decisions if d.decision_type == args.decision_type]
    if args.limit:
        decisions = decisions[: args.limit]

    print(
        f"Judging {len(decisions)} decisions from {args.recording} "
        f"with judge model {args.judge_model!r} (concurrency={args.concurrency})",
        file=sys.stderr,
    )

    grader = AiJudgeGrader(judge_model=args.judge_model)
    results: list[dict] = []
    t0 = time.time()

    with args.out.open("w") as out_f:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {
                pool.submit(_judge_one, grader, entry, QUERIES_BY_ID[entry.query_id]): entry
                for entry in decisions
            }
            done = 0
            for fut in as_completed(futures):
                entry = futures[fut]
                try:
                    row = fut.result()
                except Exception as exc:  # noqa: BLE001 - record failures, don't crash the batch
                    row = {
                        "query_id": entry.query_id,
                        "decision_type": entry.decision_type,
                        "model": entry.model,
                        "chosen": entry.chosen,
                        "error": repr(exc),
                    }
                results.append(row)
                out_f.write(json.dumps(row) + "\n")
                out_f.flush()
                done += 1
                if done % 25 == 0 or done == len(decisions):
                    print(f"  {done}/{len(decisions)}", file=sys.stderr)

    elapsed = time.time() - t0

    # --- Aggregate ---
    good_rows = [r for r in results if "error" not in r]
    error_rows = [r for r in results if "error" in r]

    confusion = {
        ("correct", "correct"): 0,
        ("correct", "incorrect"): 0,
        ("incorrect", "correct"): 0,
        ("incorrect", "incorrect"): 0,
        ("unparseable", "correct"): 0,
        ("unparseable", "incorrect"): 0,
    }
    for r in good_rows:
        confusion[(r["judge_label"], r["checker_label"])] += 1

    judge_correct_count = sum(1 for r in good_rows if r["judge_label"] == "correct")
    checker_correct_count = sum(1 for r in good_rows if r["checker_label"] == "correct")
    agree_count = sum(1 for r in good_rows if r["judge_label"] == r["checker_label"])

    # Cost per correct decision divides ALL spend by the number of correct
    # decisions. It is not the cost of the correct decisions alone: the money
    # spent on wrong answers is exactly what the metric exists to charge you
    # for. Summing only the correct rows is the flattering error this project
    # already shipped once and retracted in the README, and it makes both
    # columns below look better while changing nothing real. Do not "fix" this
    # back.
    total_decision_cost = sum(r["decision_cost_usd"] for r in good_rows)

    ai_judge_cost_per_correct = (
        total_decision_cost / judge_correct_count if judge_correct_count else None
    )
    checker_cost_per_correct = (
        total_decision_cost / checker_correct_count if checker_correct_count else None
    )

    experiment_spend = sum(
        r.get("judge_reported_cost_usd") or 0.0 for r in good_rows
    )

    disagreements = [
        r
        for r in good_rows
        if r["judge_label"] in ("correct", "incorrect")
        and r["judge_label"] != r["checker_label"]
    ]

    summary = {
        "recording": str(args.recording),
        "judge_model": args.judge_model,
        "decisions_judged": len(results),
        "errors": len(error_rows),
        "elapsed_seconds": round(elapsed, 1),
        "confusion_matrix": {f"{k[0]}_x_{k[1]}": v for k, v in confusion.items()},
        "judge_correct_count": judge_correct_count,
        "checker_correct_count": checker_correct_count,
        "agree_count": agree_count,
        "disagree_count": len(disagreements),
        "unparseable_count": sum(1 for r in good_rows if r["judge_label"] == "unparseable"),
        "total_decision_cost_usd": round(total_decision_cost, 6),
        "ai_judge_cost_per_correct_usd": (
            round(ai_judge_cost_per_correct, 6) if ai_judge_cost_per_correct else None
        ),
        "checker_cost_per_correct_usd": (
            round(checker_cost_per_correct, 6) if checker_cost_per_correct else None
        ),
        "experiment_api_spend_usd": round(experiment_spend, 6),
    }

    args.summary_out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {len(results)} rows to {args.out}", file=sys.stderr)
    print(f"Wrote summary to {args.summary_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
