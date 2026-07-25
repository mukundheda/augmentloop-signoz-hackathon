"""Toy world demo harness (T3, extended by ticket #33): a 20-junction road
network with three decision types, judges run themselves.

Replay mode is the default and the point: deterministic, no API keys, one
command - and the SigNoz dashboards fill from a judge's own machine.
"""

from .replay import RecordingEntry, ReplaySummary, load_recording, replay
from .world import Query

__all__ = [
    "replay",
    "load_recording",
    "ReplaySummary",
    "RecordingEntry",
    "Query",
]
