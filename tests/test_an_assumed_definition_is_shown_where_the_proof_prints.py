# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A proof that rests on a definition the check could not confirm on
every string (its language's `contains()` raised on one, so the
definition is `assumed`) still stands, and the record says so where it
prints: under the proven line, `assuming <statement> (assumed)`. A proof
whose definitions were all checked prints no such line."""
import pytest

import mathema
import test_a_definition_check_never_reports_checked_for_what_it_skipped as S
from mathema.languages import register_language, unregister_language

pytest.importorskip("z3")


@pytest.fixture(autouse=True)
def served():
    for language in (S.OVER_AB, S.PARTIAL):
        register_language(language.name, language)
    try:
        yield
    finally:
        for language in (S.OVER_AB, S.PARTIAL):
            unregister_language(language.name)


def _same(s: str) -> str:
    return s


def test_the_proven_line_says_which_definition_is_assumed():
    printed = str(mathema.check(_same, claims=["L[overab] subset L[partial]"]))
    assert "proven" in printed, printed
    assert "assuming L[partial] == its stated definition (assumed)" in printed, printed
    assert "L[overab] == its stated definition" not in printed, printed


def test_a_proof_on_checked_definitions_prints_no_assumption():
    printed = str(mathema.check(_same, claims=["L[overab] subset L[overab]"]))
    assert "proven" in printed and "assuming" not in printed, printed
