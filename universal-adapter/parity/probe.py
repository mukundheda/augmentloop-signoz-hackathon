"""Python half of the cross-language parity runner.

Do not run this by hand to answer a parity question. Run:

    python universal-adapter/parity/run.py

This program answers questions; it never judges the answers. It loads the shared
inputs (the fixture corpus and the case files in parity/cases/), asks the Python
implementation what it makes of each one, and writes a flat map of
"group/key" -> "answer as a string" to stdout as JSON. probe.ts answers the same
questions from the TypeScript implementation, and run.py diffs the two maps.

Keeping the judgement out of here is deliberate. A probe that decided for itself
whether an answer was acceptable could report agreement it had not observed, and
a parity runner that reports green on a check it did not really perform is worse
than no parity runner at all.

Every answer is a STRING, including failures, so that "both sides refused this
input" is a comparable observation rather than a crash. Failures are recorded as
"error:<ClassName>" and never as the error message: the two languages word their
messages differently on purpose, and comparing prose would produce noise that
buries a real divergence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ADAPTER_ROOT = HERE.parent
FIXTURES = ADAPTER_ROOT / "fixtures"
CASES = HERE / "cases"

sys.path.insert(0, str(ADAPTER_ROOT / "python"))

from gradebook import pricing  # noqa: E402
from gradebook_adapter.costing import PRICING_TABLE_ID  # noqa: E402
from gradebook_adapter.models import (  # noqa: E402
    DecisionEvidenceBundle,
    bundle_content_digest,
    canonical_json,
    derive_decision_id,
)
from gradebook_adapter.validation import validate_record  # noqa: E402


def read_json(path: Path) -> Any:
    # Explicit utf-8. Python's default encoding is platform dependent and the
    # corpus carries non-ASCII, so an implicit decode would make this probe's
    # answers depend on which machine it ran on.
    return json.loads(path.read_text(encoding="utf-8"))


def attempt(fn: Callable[[], str]) -> str:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - the class name IS the answer
        return f"error:{type(exc).__name__}"


def decode_escapes(value: Any) -> Any:
    """Expand the $parity escapes the case files use for unspellable inputs.

    JSON has no NaN, no infinities, and no comfortable way to write a 513
    character string, so the case files spell those as tagged objects and both
    probes expand them identically before anything is measured.
    """
    if isinstance(value, list):
        return [decode_escapes(item) for item in value]
    if isinstance(value, dict):
        tag = value.get("$parity")
        if isinstance(tag, str) and len(value) <= 3:
            if tag == "nan":
                return float("nan")
            if tag == "inf":
                return float("inf")
            if tag == "-inf":
                return float("-inf")
            if tag == "repeat":
                return str(value["char"]) * int(value["count"])
            raise ValueError(f"unknown $parity escape {tag!r}")
        return {key: decode_escapes(item) for key, item in value.items()}
    return value


def json_type(value: Any) -> str:
    """The JSON type name, which both languages must agree a document has."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return f"unrepresentable:{type(value).__name__}"


def documents(case: dict[str, Any], parsed: Any) -> list[Any]:
    """A case is one document, or every element of one, as the index declares."""
    if case.get("container") == "array":
        if not isinstance(parsed, list):
            return []
        return list(parsed)
    return [parsed]


def main() -> int:
    answers: dict[str, dict[str, str]] = {
        "canonical": {},
        "canonical_fixture": {},
        "validation_corpus": {},
        "validation_extra": {},
        "decision_id": {},
        "content_digest": {},
        "pricing": {},
    }

    # 1. Canonical serialization over the adversarial value set.
    for case in read_json(CASES / "canonical.json")["cases"]:
        value = decode_escapes(case["value"])
        answers["canonical"][case["id"]] = attempt(lambda v=value: canonical_json(v))

    # 2. The shared fixture corpus: validation verdicts, and the canonical form
    #    of every document in it. The corpus is real protocol data, so it is the
    #    most representative serialization input available.
    index = read_json(FIXTURES / "index.json")
    for case in index["cases"]:
        name = case["file"]
        path = FIXTURES / name
        if not path.exists():
            answers["validation_corpus"][name] = "error:MissingFixture"
            continue
        parsed = read_json(path)
        docs = documents(case, parsed)

        if case["expect"] == "not_validated":
            # Raw harness input. Validating it against a protocol schema would
            # be a category error, so the only shared observation available is
            # that both languages parse it into the same shape.
            answers["validation_corpus"][name] = f"not_validated:{json_type(parsed)}"
        else:
            if case.get("container") == "array" and not isinstance(parsed, list):
                answers["validation_corpus"][name] = "error:NotAnArray"
                continue
            for position, document in enumerate(docs):
                key = f"{name}#{position}"
                verdict = attempt(
                    lambda d=document: "accepted"
                    if not validate_record(d, case["schema"])
                    else "rejected"
                )
                answers["validation_corpus"][key] = verdict

        for position, document in enumerate(docs):
            key = f"{name}#{position}"
            answers["canonical_fixture"][key] = attempt(lambda d=document: canonical_json(d))

        # 3. Derived decision ids, for every VALID bundle document in the corpus.
        #    Invalid bundles are excluded on purpose: see the README section
        #    "What this does not prove".
        if case["schema"] == "decision-evidence-bundle" and case["expect"] == "valid":
            for position, document in enumerate(docs):
                key = f"{name}#{position}"
                answers["decision_id"][key] = attempt(
                    lambda d=document: derive_decision_id(DecisionEvidenceBundle.from_dict(d))
                )
                answers["content_digest"][key] = attempt(
                    lambda d=document: bundle_content_digest(DecisionEvidenceBundle.from_dict(d))
                )

    # 4. Extra validation inputs, at the type-system edges the corpus does not
    #    reach.
    for case in read_json(CASES / "records.json")["cases"]:
        record = decode_escapes(case["record"])
        answers["validation_extra"][case["id"]] = attempt(
            lambda r=record: "accepted" if not validate_record(r, case["kind"]) else "rejected"
        )

    # 5. The pricing table id, over the real table in gradebook.pricing.
    #    TypeScript cannot import a Python module, so the table itself is
    #    exported here and handed to probe.ts by run.py. What is compared is the
    #    id the two implementations derive from the same table.
    table = {
        "currency": "usd",
        "models": {
            slug: {
                "input_per_1m_usd": rate.input_per_mtok,
                "output_per_1m_usd": rate.output_per_mtok,
            }
            for slug, rate in pricing.PRICES.items()
        },
    }
    answers["pricing"]["pricing_table_id"] = PRICING_TABLE_ID
    answers["pricing"]["pricing_table_canonical"] = attempt(lambda: canonical_json(table))
    answers["pricing"]["pricing_table_model_count"] = str(len(table["models"]))

    sys.stdout.write(
        json.dumps(
            {"implementation": "python", "answers": answers, "pricing_table": table},
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
