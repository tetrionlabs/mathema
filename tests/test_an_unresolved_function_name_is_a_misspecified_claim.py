# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that calls or binds a function name resolving to nothing is
`skipped:misspecified` with the invalid-conjecture reason code, in every
form. Its note opens with a one-line summary and continues with a detail
block: a title, the claim, and one plain sentence with the fix."""
import pytest

from mathema.conjecture import (_diagnostic, check_conjectures, claim)
from mathema.reason_codes import ClaimReasonCode, claim_reason_code


def f(a, b):
    return a * b * 4


MOD = f.__module__
KEY = f"{f.__module__}.{f.__qualname__}"
SINGLE = "f(100.0, 0.25) == {}"
QUANT = "for a in [1,5], f(a, 0.25) == {}"


def _row(law, **kw):
    return check_conjectures(f, [claim(law, **kw)])[0]


def _first(note):
    return note.split("\n", 1)[0].rstrip()


def _block(note):
    return note.split("\n", 1)[1].strip("\n")


@pytest.mark.parametrize("form", [SINGLE, QUANT])
def test_a_called_unbound_name(form):
    p = _row(form.format("g(1)"), name="uses_g")
    assert p.verdict == "skipped:misspecified"
    assert claim_reason_code(p) == ClaimReasonCode.INVALID_CONJECTURE
    assert _first(p.note) == "uses_g is misspecified: g is not defined."
    assert _block(p.note) == (
        "Error: claim calls an undefined function\n\n"
        "  claim uses_g of " + KEY + "\n\n"
        f"g is not defined in module {MOD}. Define it there, or bind it:\n"
        'funcs={"g": "pkg.mod.g"}')


def test_both_forms_give_the_same_title_and_explanation():
    blocks = [_block(_row(form.format("g(1)"), name="uses_g").note)
              for form in (SINGLE, QUANT)]
    assert blocks[0] == blocks[1]


def test_an_ad_hoc_claim_is_named_by_its_statement():
    p = _row(SINGLE.format("g(1)"))
    assert _first(p.note) == ("claim f(100.0, 0.25) == g(1) is "
                              "misspecified: g is not defined.")
    assert "  claim f(100.0, 0.25) == g(1)\n" in _block(p.note)
    assert "f_100_0_0_25_eq_g_1" not in p.note


@pytest.mark.parametrize("form", [SINGLE, QUANT])
def test_an_unused_stale_binding(form):
    law = form.format("100.0" if form is SINGLE else "4 * a")
    p = _row(law, name="uses_h", funcs={"h": "no.such.h"})
    assert p.verdict == "skipped:misspecified"
    assert _first(p.note) == ("uses_h is misspecified: h is bound to "
                              "no.such.h, which does not resolve.")
    assert _block(p.note) == (
        "Error: claim has a binding that does not resolve\n\n"
        "  claim uses_h of " + KEY + "\n\n"
        "h is bound to no.such.h, and the module no.such does not import. "
        "Fix the path, or remove the binding (the statement does not use h).")


def test_a_dotted_path_whose_module_imports_but_lacks_the_attribute():
    p = _row(SINGLE.format("100.0"), name="uses_h",
             funcs={"h": "json.nothere"})
    assert _first(p.note) == ("uses_h is misspecified: h is bound to "
                              "json.nothere, which does not resolve.")
    assert _block(p.note).endswith(
        "h is bound to json.nothere, and json has no attribute nothere. "
        "Fix the path, or remove the binding (the statement does not use h).")


def test_a_called_name_with_a_dotted_path_that_does_not_import():
    p = _row(SINGLE.format("h(1)"), name="uses_h",
             funcs={"h": "no_such_pkg_zz.h"})
    assert _block(p.note).endswith(
        "h is bound to no_such_pkg_zz.h, and the module no_such_pkg_zz does "
        "not import. Fix the path.")


def test_two_undefined_names_at_once():
    p = _row(SINGLE.format("g(1) + k(2)"), name="uses_two")
    assert _first(p.note) == "uses_two is misspecified: g and k are not defined."
    assert _block(p.note) == (
        "Error: claim calls undefined functions\n\n"
        "  claim uses_two of " + KEY + "\n\n"
        f"g and k are not defined in module {MOD}. Define them there, or "
        'bind them: funcs={"g": "...", "k": "..."}')


def test_the_note_has_no_em_dash_or_box_characters():
    p = _row(SINGLE.format("g(1)"), name="uses_g")
    assert not set("\u2014\u2500\u2502\u2577\u2575") & set(p.note)


def test_the_diagnostic_helper_places_a_known_location():
    text = _diagnostic(
        "claim calls an undefined function", "uses_g", "m.f",
        "f(100.0, 0.25) == g(1)",
        "g is not defined in module m. Define it there, or bind it:\n"
        'funcs={"g": "pkg.mod.g"}',
        location={"file": "claims/m.claims.yaml", "line": 12,
                  "text": "uses_g: f(100.0, 0.25) == g(1)"})
    assert text == (
        "Error: claim calls an undefined function\n\n"
        "  on claims/m.claims.yaml line 12, claim uses_g of m.f:\n"
        "  12:   uses_g: f(100.0, 0.25) == g(1)\n\n"
        "g is not defined in module m. Define it there, or bind it:\n"
        'funcs={"g": "pkg.mod.g"}')


def test_realistic_names_never_call_the_function_f_outside_the_claim_line():
    import re
    import types
    mod = types.ModuleType("pkg.orders")
    exec("def total(items):\n    return sum(items)\n", mod.__dict__)
    c = claim("f(items) == reference_total(items)", name="matches_reference")
    p = check_conjectures(mod.total, [c])[0]
    assert p.verdict == "skipped:misspecified"
    first = _first(p.note)
    title, _, rest = _block(p.note).partition("\n\n")
    where, _, explanation = rest.partition("\n\n")
    assert where == "  claim matches_reference of pkg.orders.total"
    assert "reference_total is not defined in module pkg.orders" in explanation
    for part in (first, title, where, explanation):
        assert not re.search(r"\bf\b", part), part
