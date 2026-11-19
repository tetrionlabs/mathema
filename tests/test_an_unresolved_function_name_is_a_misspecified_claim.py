# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that calls or binds a function name resolving to nothing is
`skipped:misspecified` with the invalid-conjecture reason code, in every
form, and its note names the claim, each unresolved name, where it was
looked for, whether the statement calls it or the binding is unused,
and the fix."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.reason_codes import ClaimReasonCode, claim_reason_code


def f(a, b):
    return a * b * 4


def _row(law, **kw):
    return check_conjectures(f, [claim(law, **kw)])[0]


SINGLE = "f(100.0, 0.25) == {}"
QUANT = "for a in [1,5], f(a, 0.25) == {}"


@pytest.mark.parametrize("form", [SINGLE, QUANT])
def test_a_called_unbound_name(form):
    p = _row(form.format("g(1)"))
    assert p.verdict == "skipped:misspecified"
    assert claim_reason_code(p) == ClaimReasonCode.INVALID_CONJECTURE
    for part in (repr(p.name), "['g']", f"module `{f.__module__}`",
                 "calling scope", "The statement calls `g`", "is misspecified",
                 "define `g` in the module", 'funcs={"g": "pkg.mod.g"}'):
        assert part in p.note, part


def test_both_forms_say_the_same_thing_about_the_name():
    tails = []
    for form in (SINGLE, QUANT):
        p = _row(form.format("g(1)"))
        tails.append(p.note.replace(repr(p.name), "NAME")
                     .split("inferred")[0])
    assert tails[0] == tails[1]


@pytest.mark.parametrize("form", [SINGLE, QUANT])
def test_an_unused_stale_binding(form):
    p = _row(form.format("100.0" if form is SINGLE else "4 * a"),
             funcs={"h": "no.such.h"})
    assert p.verdict == "skipped:misspecified"
    for part in ("['h']", "`h` is an unused binding",
                 "never calls it", "remove the unused binding of `h`",
                 "funcs={'h': 'no.such.h'}"):
        assert part in p.note, part


def test_a_dotted_path_whose_module_imports_but_lacks_the_attribute():
    p = _row(SINGLE.format("h(1)"), funcs={"h": "json.nothere"})
    assert p.verdict == "skipped:misspecified"
    assert "the module `json` imports but has no function `nothere`" in p.note
    assert "funcs={'h': 'json.nothere'}" in p.note


def test_a_dotted_path_whose_module_does_not_import():
    p = _row(SINGLE.format("h(1)"), funcs={"h": "no_such_pkg_zz.h"})
    assert p.verdict == "skipped:misspecified"
    assert "the module `no_such_pkg_zz` could not be imported" in p.note


def test_two_unresolved_names_at_once():
    p = _row(SINGLE.format("g(1) + k(2)"))
    assert p.verdict == "skipped:misspecified"
    assert "['g', 'k']" in p.note
    assert "The statement calls `g`" in p.note
    assert "The statement calls `k`" in p.note
    assert "no em" not in p.note and "—" not in p.note
