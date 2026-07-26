"""Generic JSONL adapter: a log file is enough to make a harness gradeable.

The fallback path for harnesses with weak or unstable extension APIs. It reads a
JSONL stream, validates each line independently, and emits protocol records. It
imports no harness package and it grades nothing.

The one property worth knowing before using it: failure is per line. A truncated
final line, a corrupt line in the middle, or a record this protocol does not
define costs you that line and nothing else.
"""

from .reader import (
    REASONS,
    GenericJsonlAdapter,
    IngestReport,
    LineError,
    Normalizer,
    ProtocolRecord,
    read_jsonl,
    read_jsonl_file,
    to_jsonl,
)

__all__ = [
    "GenericJsonlAdapter",
    "IngestReport",
    "LineError",
    "Normalizer",
    "ProtocolRecord",
    "REASONS",
    "read_jsonl",
    "read_jsonl_file",
    "to_jsonl",
]
