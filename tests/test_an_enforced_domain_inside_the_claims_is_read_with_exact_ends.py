# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`excluded_outside_domain(x)` is proven by construction when the
`enforce_domain` wrapper refuses every number outside the claim's
domain: the enforced domain is inside the claim's. An end is inside
only when it is: the wrapper on `[0, 1]` accepts 0 and 1, which
`(0, 1)` leaves out, so that claim is not proven; the wrapper on
`(0, 1)` is inside `[0, 1]`. A finite enforced set is inside an
interval that holds every member."""
import pytest

from mathema import enforce_domain
from mathema.claim_families import _enforced_inside
from mathema.conjecture import check_conjectures, claim


@enforce_domain({"x": "[0, 1]"})
def closed(x):
    return x * 2.0


@enforce_domain({"x": "(0, 1)"})
def opened(x):
    return x * 2.0


@enforce_domain({"x": "[0, 1)"})
def open_above(x):
    return x * 2.0


@enforce_domain({"x": "(0, 1]"})
def open_below(x):
    return x * 2.0


@enforce_domain({"x": "{0, 1}"})
def two_points(x):
    return x * 2.0


_FN = {"[0, 1]": closed, "(0, 1)": opened, "[0, 1)": open_above,
       "(0, 1]": open_below}
#: enforced, the claim's domain, whether the enforced one is inside it
_ENDS = [(enforced, stated,
          (enforced[0] == "(" or stated[0] == "[")
          and (enforced[-1] == ")" or stated[-1] == "]"))
         for enforced in _FN for stated in _FN]


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


def _inside(fn, stated: str) -> bool:
    bound = claim(f"for x in {stated}, f(x) == 1").domain["x"]
    return _enforced_inside(fn.__mathema_enforced_domain__["x"], bound)


@pytest.mark.parametrize("enforced, stated, inside", _ENDS,
                         ids=[f"{e} in {s}" for e, s, _ in _ENDS])
def test_an_interval_is_inside_another_by_its_ends(enforced, stated, inside):
    assert _inside(_FN[enforced], stated) is inside
    p = _row(_FN[enforced], f"for x in {stated}, excluded_outside_domain(x)")
    if inside:
        assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
        assert "rejection by construction" in p.sketch, p.sketch
    else:
        assert "rejection by construction" not in (p.sketch or ""), p.sketch
        assert p.verdict != "proven", (p.verdict, p.route, p.sketch)


@pytest.mark.parametrize("enforced, stated, inside", [
    ("[0, 1]", "[0, 2]", True), ("[0, 1]", "(-1, 2)", True),
    ("[0, 1]", "[0.5, 2]", False), ("(0, 1)", "(0, 0.5)", False),
    ("(0, 1)", "(0, 1.5)", True), ("[0, 1)", "[0, 1.5)", True),
])
def test_a_shifted_interval_is_read_by_its_numbers(enforced, stated, inside):
    assert _inside(_FN[enforced], stated) is inside


@pytest.mark.parametrize("stated, inside", [
    ("[0, 1]", True), ("[0, 100]", True), ("[-1, 2)", True),
    ("{0, 1}", True), ("{0, 1, 2}", True),
    ("(0, 1)", False), ("[0, 1)", False), ("(0, 1]", False),
    ("{0}", False), ("{0, 2}", False), ("[0.5, 1]", False),
])
def test_a_finite_enforced_set_is_inside_what_holds_every_member(
        stated, inside):
    assert _inside(two_points, stated) is inside
    p = _row(two_points, f"for x in {stated}, excluded_outside_domain(x)")
    if inside:
        assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
    else:
        assert "rejection by construction" not in (p.sketch or ""), p.sketch
        assert p.verdict != "proven", (p.verdict, p.route, p.sketch)


def test_an_interval_is_not_inside_a_finite_set():
    assert _inside(closed, "{0, 1}") is False
