# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every spelling an earlier release wrote or accepted still parses, and
comes back as the canonical claim (here for a `float` parameter, the
annotation an earlier record's statement was written for): the fused `:float|missing`, the
unicode `∪ {∅}`, the exclusion `\\ {∅}`, a set unioned with `{∅}`, a
space followed by `| {missing}`. A written `:=` is refused, in a binding
and in a statement, and a member cannot be excluded from a class the
domain admits."""
import pytest

import mathema
from mathema.conjecture import InvalidConjecture, claim
from mathema.domain import (InvalidDomain, MissingDefaults, _parse_binding, complete,
                            parse_binding, render_domain)


@pytest.mark.parametrize("old, canonical", [
    ("[0.0, 1.0]:float|missing", "[0.0, 1.0] : float|missing"),
    ("[0, 1] ⊂ ℝ ∪ {∅}", "[0.0, 1.0] : float|missing"),
    ("[0, 1] | {missing} ⊂ R", "[0.0, 1.0] : float|missing"),
    ("[0.0, 1.0] \\ {missing}:float", "[0.0, 1.0] : float"),
    ("[0, 1] \\ {∅}", "[0.0, 1.0] : float"),
    ('{"a"} ∪ {∅}', '{"a", missing}'),
    ("{0.25}|missing", "{0.25, missing}"),
    ("R|missing", "R|missing"),
    ("ℝ ∪ {∅}", "R|missing"),
    ("[0,10] ⊂ Z ∪ {∅}", "[0, 10] : int|missing"),
    ("[0.0, 1.0]^n:float|missing", "([0.0, 1.0] | {missing})^n : float"),
    ("[0, 1]^n | {missing}", "([0.0, 1.0] | {missing})^n : float"),
    ("R^(n,n)|missing", "(R | {missing})^(n,n)"),
    ("ℝⁿˣⁿ ∪ {∅}", "(R | {missing})^(n,n)"),
    ("N|missing", "N|missing"),
    ("L[unicode]|missing", "L[unicode]|missing"),
    ('L[unicode] \\ {""}|missing', 'L[unicode] \\ {""}|missing'),
    ("L[unicode] \\ {∅}", "L[unicode] \\ {missing}"),
])
def test_an_old_spelling_parses_to_the_canonical_domain(old, canonical):
    b = complete(parse_binding(f"x in {old}")[1], FLOAT)
    assert render_domain(b, ascii_mode=True) == canonical


FLOAT = MissingDefaults(False, ("nan",), "float")


def double(x: float) -> float:
    return 2 * x


def test_an_old_record_statement_reads_back_as_the_canonical_claim():
    old = "for x in [0.0, 1.0]:float|missing, f(x) >= 0"
    report = mathema.check(double, claims=[claim(old, name="c")])
    assert next(p for p in report.probes if p.name == "c").statement == \
        "for x in [0.0, 1.0] : float|missing, f(x) >= 0"


def test_a_definition_in_a_binding_is_refused():
    reason = _parse_binding("x in [0, 1] := float")
    assert isinstance(reason, str) and "`:=`" in reason


def test_a_definition_in_a_statement_is_refused():
    with pytest.raises(InvalidConjecture, match="defines:"):
        claim("missing := {null, nan}")
    with pytest.raises(InvalidConjecture, match=":="):
        claim("for x in [0, 1] := float, f(x) >= 0")


def test_a_member_excluded_from_an_admitted_class_is_refused():
    reason = _parse_binding("x in [0, 1] : float|missing \\ {nan}")
    assert isinstance(reason, str) and "name the members you admit" in reason
    with pytest.raises((InvalidDomain, InvalidConjecture),
                       match="name the members you admit"):
        claim("for x in [0, 1] | {missing} \\ {nan}, f(x) >= 0")
