"""ANTI-DRIFT. The hand written validator must agree with the JSON Schemas.

This is the most important test in the package. `validation.py` is hand written
so that its errors are actionable, and the price of that choice is that it can
quietly stop agreeing with the frozen schemas the TypeScript implementation and
every future harness read. A validator that is 95 percent right is worse than no
validator: it rejects records other implementations accept, and accepts records
they reject, and the disagreement surfaces as a mysterious cross-language bug
rather than as a failing test.

So every case in the shared corpus goes through BOTH validators and the two
verdicts must match. If they ever differ, this fails loudly and names the case.

One configuration note, on `format`. JSON Schema treats `format` as an
annotation unless a validator opts into asserting it, so the corpus would get
different verdicts from Python and TypeScript purely on setup. The schema now
carries an RFC 3339 `pattern` alongside `format: date-time` for exactly that
reason, which makes the verdict identical by construction. The format checker is
still enabled below, and where the installed jsonschema has no native date-time
checker, this package's own parser is registered as one so both sides at least
enforce the same keyword.
"""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest
from conftest import FixtureCase, load_schema, require_fixture_cases

from gradebook_adapter.validation import (
    format_errors,
    is_rfc3339_datetime,
    validate_record,
)


def _format_checker() -> jsonschema.FormatChecker:
    checker = jsonschema.FormatChecker()
    if "date-time" not in checker.checkers:
        @checker.checks("date-time")
        def _date_time(value: Any) -> bool:
            return not isinstance(value, str) or is_rfc3339_datetime(value)
    return checker


def _validator(schema_name: str) -> Any:
    schema = load_schema(schema_name)
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema, format_checker=_format_checker())


def _cases() -> list[FixtureCase]:
    try:
        return require_fixture_cases()
    except Exception:  # pragma: no cover - corpus absent, collection stays green
        return []


def _ids(cases: list[FixtureCase]) -> list[str]:
    return [case.name for case in cases]


CASES = _cases()


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_hand_written_validator_agrees_with_the_json_schema(case: FixtureCase) -> None:
    require_fixture_cases()
    if not case.should_validate:
        pytest.skip(f"{case.name} is raw harness input, not a protocol record")

    schema_validator = _validator(case.schema or "")
    for index, document in enumerate(case.documents):
        mine = validate_record(document, case.schema or "")
        theirs = list(schema_validator.iter_errors(document))
        assert (not mine) == (not theirs), (
            f"VALIDATOR DRIFT in {case.name}[{index}].\n"
            f"hand written validator: {'accepted' if not mine else 'rejected'}\n"
            f"json schema:            {'accepted' if not theirs else 'rejected'}\n"
            f"hand written errors:\n{format_errors(mine) or '  (none)'}\n"
            f"json schema errors:\n"
            + ("\n".join(f"  {e.json_path}: {e.message}" for e in theirs) or "  (none)")
        )


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_corpus_verdicts_match_the_declared_expectation(case: FixtureCase) -> None:
    require_fixture_cases()
    if not case.should_validate:
        pytest.skip(f"{case.name} is raw harness input, not a protocol record")

    for index, document in enumerate(case.documents):
        errors = validate_record(document, case.schema or "")
        if case.expects_valid:
            assert not errors, (
                f"{case.name}[{index}] is indexed as valid but was rejected:\n"
                f"{format_errors(errors)}\nnote: {case.note}"
            )
        else:
            # Deliberately no assertion on the NUMBER of errors: one authored
            # mistake can legitimately trip more than one rule.
            assert errors, (
                f"{case.name}[{index}] is indexed as invalid but was accepted.\n"
                f"note: {case.note}"
            )


def test_every_rejection_says_where_and_what_was_expected() -> None:
    """Actionability is an acceptance criterion, so it is asserted, not assumed."""
    cases = require_fixture_cases()
    invalid = [c for c in cases if c.should_validate and not c.expects_valid]
    assert invalid, "the corpus should carry invalid cases"

    for case in invalid:
        for document in case.documents:
            errors = validate_record(document, case.schema or "")
            for error in errors:
                assert error.message, f"{case.name}: an error with no message"
                assert error.expected, (
                    f"{case.name}: error at {error.path!r} says what was wrong but "
                    "not what was expected, which is the half an integrator needs"
                )
                assert error.path == "" or error.path.startswith("/"), (
                    f"{case.name}: {error.path!r} is not a JSON pointer"
                )


def test_corpus_covers_all_four_record_types() -> None:
    cases = require_fixture_cases()
    covered = {case.schema for case in cases if case.should_validate}
    assert covered == {
        "decision-evidence-bundle",
        "usage-record",
        "evaluation-manifest",
        "outcome-record",
    }
