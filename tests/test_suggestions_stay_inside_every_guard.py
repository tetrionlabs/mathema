# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A suggestion binds the working domain exactly: endpoints as the
guard wrote them (never rounded outward), open ends open, a declared
union intersected with what a raise guard leaves (never replaced by
it), a guard on several parameters stated as an `assuming` premise,
and no suggestion at all over a guard that cannot be stated. No
suggested row is refused by the function's own guard, except the
rows that feed the function's output back in, which falsify by
design when the output leaves the domain."""
import inspect
import math
import os
import sys

import pytest

from mathema import check
from mathema.suggest import suggest_claims

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))
import guarded_suggestions as G  # noqa: E402

#: rows that feed the output back in, and rows about the guard itself
_FEEDS_BACK = ("raises[", "idempotent", "associative", "is_missing_safe",
               "is_empty_safe", "is_absent_safe")


def _suggested(fn):
    return {c.name: c for c in suggest_claims(fn)}


@pytest.mark.parametrize("fn", [
    fn for name, fn in sorted(vars(G).items())
    if inspect.isfunction(fn) and fn.__module__ == G.__name__
    or hasattr(fn, "__wrapped__") and not name.startswith("_")],
    ids=lambda f: f.__name__)
def test_no_suggested_row_is_refused_by_the_guard(fn):
    suggested = set(_suggested(fn))
    for p in check(fn).probes:
        if p.name.startswith(_FEEDS_BACK) or p.name not in suggested:
            continue
        text = f"{p.counterexample or ''} {p.note or ''}"
        assert "DomainError" not in text and "ValueError" not in text, (
            fn.__name__, p.name, p.statement, p.counterexample)


def test_an_endpoint_is_bound_as_the_guard_wrote_it():
    s = _suggested(G.fine_upper)["monotonic_increasing[x]"]
    assert tuple(s.domain["x"]) == (-1.0, 0.1234567), s.domain
    s = _suggested(G.declared_fine)["idempotent"]
    assert tuple(s.domain["x"]) == (-1.0, 0.1234567), s.domain


def test_an_irrational_endpoint_is_rounded_inward():
    lo, hi = tuple(_suggested(G.sqrt_guard)["monotonic_increasing[x]"]
                   .domain["x"])
    assert lo * lo <= 2 and hi * hi <= 2, (lo, hi)
    assert -lo > 1.414 and hi > 1.414


def test_an_open_declared_end_stays_open_under_a_cut():
    d = _suggested(G.open_left_cut)["monotonic_increasing[x]"].domain["x"]
    assert "(0" in repr(d) and "0.5]" in repr(d), d


def test_a_cut_intersects_a_declared_union_rather_than_replacing_it():
    d = _suggested(G.open_split_scalar)["monotonic_increasing[w]"] \
        .domain["w"]
    assert [tuple(p) for p in d.pieces] == [(-1.0, -0.5), (0.5, 2.0)], d


def test_a_guard_on_two_parameters_is_an_assuming_premise():
    s = _suggested(G.two_param_guard)["monotonic_increasing[x]"]
    assert " ".join(s.assuming.split()) == "assuming x <= y", s.assuming
    assert "commutative" not in _suggested(G.two_param_guard)


def test_no_suggestion_crosses_a_guard_mathema_cannot_state():
    names = set(_suggested(G.guarded_nan))
    assert not {n for n in names if not n.startswith(
        ("raises[", "is_deterministic", "is_state_safe",
         "is_missing_safe"))}, names
    assert math.isnan(float("nan"))
