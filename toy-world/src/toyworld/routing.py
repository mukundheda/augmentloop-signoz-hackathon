"""The production routing table (ticket #10): which model serves which decision.

Right-sizing is the hero action of the propose-approve-apply loop: the agent
reads cost per correct decision *by model*, proposes rerouting a decision type
to a cheaper model, a human approves, and the next run proves quality held
while cost dropped (CONTEXT.md "Right-sizing").

This module is the "apply" surface of that loop. The routing table is a
committed JSON file rather than a flag or an environment variable on purpose:

- a proposal becomes a **one-line diff** a human can read before approving, which
  is what makes "nothing changes until a human approves" auditable rather than
  merely claimed;
- the change is **version controlled**, so the before/after runs either side of
  a reroute are reproducible from git history, not from someone's shell;
- it keys on **decision type**, not on the whole program, matching the
  conventions doc: right-sizing targets a *kind* of decision (reroute
  `route_choice`, not "everything").

The toy world has three decision types (ticket #33: `route_choice`,
`eta_estimate`, `next_hop`), so the table now has real rows to compare instead
of one - a substrate with different decision types (CleanCut's
`filler_detection` and `quote_extraction`) wears the same table with more
rows, which is the point of keying on decision type at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from gradebook.pricing import PRICES

# Lives beside the package (toy-world/routing.json), not inside src/, so it
# reads as configuration a human edits rather than code that ships in the wheel.
DEFAULT_ROUTING_PATH = Path(__file__).resolve().parents[2] / "routing.json"


class RoutingError(ValueError):
    """Raised when the routing table is missing, malformed, or unpriceable.

    Always fails before any model call or span is emitted: a bad reroute should
    cost nothing and produce no misleading telemetry.
    """


def load_routing(path: Path = DEFAULT_ROUTING_PATH) -> dict[str, str]:
    """Read and validate the decision-type -> model table.

    Validation is deliberately strict. This file is written by an approval step,
    so the moment it is wrong is the moment a human just said yes to something
    - much better to refuse loudly here than to emit a run's worth of spans
    priced against a model that does not exist.
    """
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise RoutingError(f"no routing table at {path}") from exc
    except json.JSONDecodeError as exc:
        raise RoutingError(f"routing table at {path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or not raw:
        raise RoutingError(
            f"routing table at {path} must be a non-empty object mapping "
            f"decision type to model"
        )

    for decision_type, model in raw.items():
        if not isinstance(model, str):
            raise RoutingError(
                f"routing table at {path}: decision type {decision_type!r} must "
                f"map to a model name (a string), got {type(model).__name__}"
            )
        if model not in PRICES:
            raise RoutingError(
                f"routing table at {path}: decision type {decision_type!r} routes "
                f"to {model!r}, which has no row in the Gradebook pricing table. "
                f"Add a pricing row before routing production traffic to it."
            )

    return dict(raw)


def routed_model(routing: Mapping[str, str], decision_type: str) -> str:
    """The model currently serving `decision_type` in production."""
    try:
        return routing[decision_type]
    except KeyError as exc:
        known = ", ".join(sorted(routing)) or "(none)"
        raise RoutingError(
            f"no route for decision type {decision_type!r}; routed types: {known}"
        ) from exc
