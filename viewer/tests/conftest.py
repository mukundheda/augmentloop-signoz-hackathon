from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viewer"))
sys.path.insert(0, str(ROOT / "toy-world" / "src"))
sys.path.insert(0, str(ROOT / "reference-library" / "src"))

