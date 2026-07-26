"""Path wiring only. This adapter sits on the reference implementation and the
generic JSONL adapter, both in this repo rather than on PyPI.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ADAPTERS = HERE.parent
REFERENCE = ADAPTERS.parent / "python"

for path in (HERE, ADAPTERS / "generic-jsonl", REFERENCE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:  # pragma: no cover - import guard, exercised only when misinstalled
    import gradebook_adapter  # noqa: F401
    import gradebook_adapter_jsonl  # noqa: F401
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "this wrapper needs universal-adapter/python and "
        "universal-adapter/adapters/generic-jsonl. Install them together:\n"
        "  pip install -e reference-library -e universal-adapter/python "
        "-e universal-adapter/adapters/generic-jsonl "
        "-e universal-adapter/adapters/cli-wrapper[test]"
    ) from exc
