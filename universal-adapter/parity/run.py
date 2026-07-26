"""CROSS-LANGUAGE PARITY RUNNER for the universal adapter.

RUN IT WITH ONE COMMAND, from anywhere:

    python universal-adapter/parity/run.py

Exit code 0 means every comparison agreed. Any other exit code means at least one
divergence, and every one of them is printed with both values.

WHY THIS EXISTS
---------------
This package ships two implementations of one protocol, in Python and in
TypeScript. Each has its own test suite asserting that IT agrees with the shared
fixture corpus. Neither could ever check the claim that actually matters, which
is that the two agree with EACH OTHER on the same input, because neither test
runner can execute the other language. Two separate self-reports are not a parity
proof; they are two implementations agreeing with a file, which leaves every
choice the file does not pin free to drift.

So this runner drives both implementations over identical inputs in one process
tree and diffs the answers. It adds no opinions of its own: probe.py and probe.ts
only answer questions, and the only thing here that can fail is two answers not
being the same string.

WHAT IT PROVES, AND WHAT IT DOES NOT
------------------------------------
It proves the two implementations agree on these inputs. It does NOT prove either
one is CORRECT: both could agree on the same bug, and a shared bug is exactly the
kind this runner is blind to. Read parity/README.md before quoting a green run as
evidence of anything more than agreement.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

# Long answers (a canonical serialization of a whole fixture, say) are truncated
# in the report. The divergence offset is always shown in full, because that is
# the part that tells you where to look.
_SHOW = 400

GROUP_TITLES = {
    "canonical": "canonical serialization, adversarial value set",
    "canonical_fixture": "canonical serialization, every document in the corpus",
    "validation_corpus": "validation verdict, shared fixture corpus",
    "validation_extra": "validation verdict, type-system edge cases",
    "decision_id": "derived decision id, every valid bundle in the corpus",
    "content_digest": "bundle content digest, every valid bundle in the corpus",
    "pricing": "pricing table id, over the real gradebook.pricing table",
}


def run_probe(command: list[str], label: str) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, cwd=str(HERE))
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(
            f"the {label} probe failed (exit {completed.returncode}). It cannot be "
            f"treated as agreement, so this run is a failure.\n"
            f"command: {' '.join(command)}\n{stderr}"
        )
    text = completed.stdout.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"the {label} probe did not emit JSON on stdout, so nothing can be "
            f"compared.\n{exc}\nfirst 500 characters:\n{text[:500]}"
        ) from None


def shorten(value: str) -> str:
    if len(value) <= _SHOW:
        return value
    return f"{value[:_SHOW]}... [{len(value)} characters total]"


def first_difference(left: str, right: str) -> str:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return f"first differs at character {index}: {a!r} vs {b!r}"
    return f"identical for {min(len(left), len(right))} characters, then the lengths differ"


def main() -> int:
    python_report = run_probe([sys.executable, str(HERE / "probe.py")], "Python")

    # The pricing table lives in a Python module, so it is exported from the
    # Python probe and handed to the TypeScript one. What gets compared is the id
    # each implementation derives from that one table.
    table = python_report.get("pricing_table")
    with tempfile.TemporaryDirectory() as workspace:
        table_path = Path(workspace) / "pricing-table.json"
        table_path.write_text(json.dumps(table), encoding="utf-8")
        node_report = run_probe(
            ["node", str(HERE / "probe.ts"), str(table_path)], "TypeScript"
        )

    left: dict[str, dict[str, str]] = python_report["answers"]
    right: dict[str, dict[str, str]] = node_report["answers"]

    groups = sorted(set(left) | set(right))
    divergences: list[tuple[str, str, str, str]] = []
    compared = 0
    per_group: list[tuple[str, int, int]] = []

    for group in groups:
        mine = left.get(group, {})
        theirs = right.get(group, {})
        keys = sorted(set(mine) | set(theirs))
        agreed = 0
        for key in keys:
            compared += 1
            a = mine.get(key, "<the Python probe did not answer this>")
            b = theirs.get(key, "<the TypeScript probe did not answer this>")
            if a == b:
                agreed += 1
            else:
                divergences.append((group, key, a, b))
        per_group.append((group, len(keys), agreed))

    print("CROSS-LANGUAGE PARITY: Python vs TypeScript, universal-adapter")
    print("=" * 78)
    for group, total, agreed in per_group:
        status = "agree" if agreed == total else f"DIVERGE ({total - agreed})"
        title = GROUP_TITLES.get(group, group)
        print(f"  {agreed:>4} / {total:<4} {status:<14} {group:<18} {title}")
    print("-" * 78)
    total_agreed = sum(agreed for _, _, agreed in per_group)
    print(f"  {total_agreed} of {compared} comparisons agreed")

    if not divergences:
        print()
        print("PARITY HOLDS across all", compared, "comparisons.")
        print("This is agreement, not correctness. See parity/README.md.")
        return 0

    print()
    print(f"{len(divergences)} DIVERGENCE(S). Each is a place where the two")
    print("implementations of one protocol answered differently on identical input.")
    for group, key, a, b in divergences:
        print()
        print("=" * 78)
        print(f"{group} :: {key}")
        print(f"  python     : {shorten(a)}")
        print(f"  typescript : {shorten(b)}")
        print(f"  {first_difference(a, b)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
