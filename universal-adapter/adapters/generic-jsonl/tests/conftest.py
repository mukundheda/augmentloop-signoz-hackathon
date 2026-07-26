"""Path wiring only. The adapter needs the reference implementation beside it.

Normally both are installed with `pip install -e ...`; adding the paths keeps the
suite runnable straight from a checkout, which is how anyone reviewing a pull
request will run it.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REFERENCE = HERE.parents[1] / "python"

for path in (HERE, REFERENCE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:  # pragma: no cover - import guard, exercised only when misinstalled
    import gradebook_adapter  # noqa: F401
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "gradebook_adapter is this repo's reference implementation at "
        "universal-adapter/python. Install it alongside this adapter:\n"
        "  pip install -e reference-library -e universal-adapter/python "
        "-e universal-adapter/adapters/generic-jsonl[test]"
    ) from exc
