# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The slug validators decided end to end with the installed
`mathema-language` compiling the pattern: skipped, with the reason,
unless the installed package states a regular-language definition for
`L[unicode]` and registers a predicate word that reads the bound method
`match` of a compiled pattern."""
import re

import pytest

pytest.importorskip("z3")
pytest.importorskip("mathema_language",
                    reason="mathema-language is not installed (the language extra)")

from mathema import regular  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.languages import resolve_language, word_reading_call  # noqa: E402

_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*$")
_SLUG_FIXED = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


def check_slug(text: str) -> str:
    if not _SLUG.match(text):
        raise ValueError(text)
    return text


def check_slug_fixed(text: str) -> str:
    if not _SLUG_FIXED.match(text):
        raise ValueError(text)
    return text


def _missing() -> "str | None":
    """What the installed mathema-language does not provide, or None."""
    try:
        unicode = resolve_language("unicode").to_json().get("definition")
    except Exception as e:
        return f"L[unicode] does not resolve ({e})"
    if not regular.is_definition(unicode):
        return "the installed mathema-language states no regular-language definition for L[unicode]"
    if word_reading_call(_SLUG.match) is None:
        return "no registered word reads re.Pattern.match"
    return None


@pytest.fixture(autouse=True)
def provided():
    missing = _missing()
    if missing is not None:
        pytest.skip(missing)


_CLAIM = 'for text in L[unicode], raises(f(text + "\\n"), ValueError)'


def test_the_fixed_validator_is_proven_for_every_text():
    (row,) = check_conjectures(check_slug_fixed, [claim(_CLAIM, route="derive")])
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.meta["mathema.derive_route"] == "smt"


def test_the_dollar_validator_is_falsified_by_the_solver():
    (row,) = check_conjectures(check_slug, [claim(_CLAIM, route="derive")])
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.meta["mathema.derive_route"] == "smt"
    found = re.fullmatch(r"text = '(.*)'", row.counterexample)
    assert found and _SLUG.match(found.group(1) + "\n")
