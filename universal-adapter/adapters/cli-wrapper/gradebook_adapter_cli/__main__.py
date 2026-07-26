"""`python -m gradebook_adapter_cli`, the same entry point as `gradebook-run`."""

from __future__ import annotations

import sys

from .wrapper import main

if __name__ == "__main__":
    sys.exit(main())
