# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim's witness over a language is shrunk inside the
language before it is reported, as the hazard families' witnesses
are: each step takes one of the language's own `shrink` candidates
that is still in the claim's domain and still fails the claim, within
a bounded number of evaluations, and the record says the witness was
shrunk. A witness already minimal is reported as found."""
import html

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language

ANY = StringLanguage("any_text", char_ok=lambda c: True, pool="abcx<&é ")


@pytest.fixture(autouse=True)
def any_text():
    register_language("any_text", ANY)
    try:
        yield
    finally:
        unregister_language("any_text")


def escape(s):
    """The markup characters of s as entities."""
    return html.escape(s)


def headline(s):
    """At most eighty characters of s."""
    return s[:80]


def ends_with_x(s):
    """s with an x appended."""
    return s + "x"


def test_a_containment_witness_shrinks_to_the_character_that_fails():
    (p,) = check_conjectures(escape, [claim('for s in L[any_text], "&" not in f(s)')])
    assert p.verdict == "falsified"
    assert p.counterexample.split(":")[0] in ("('&')", "('<')", "('>')", "('\"')", "(\"'\")"), \
        p.counterexample
    assert p.meta["mathema.witness_shrunk"]["steps"] >= 0


def test_a_length_witness_stays_the_member_at_the_bound():
    (p,) = check_conjectures(headline, [claim("for s in L[any_text, len <= 81], f(s) == s")])
    assert p.verdict == "falsified"
    assert p.counterexample.startswith("('" + "a" * 81 + "')")


def test_a_shrunk_witness_stays_in_the_domain_and_still_fails():
    (p,) = check_conjectures(ends_with_x, [claim(
        'for s in L[any_text] \\ {""}, "xx" not in f(s)')])
    assert p.verdict == "falsified"
    witness = p.counterexample.split(":")[0]
    assert witness == "('x')", p.counterexample
    assert "shrunk" in p.note
