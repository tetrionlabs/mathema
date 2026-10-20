# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A sign claim over a symbolic-length sum is proven termwise only when
each term really has that sign.

The termwise rung reads `Sum(t(xs[i]), (i, 0, L-1)) >= 0` as "every
term is nonnegative", deciding the summand with each element replaced
by a real symbol. Two different elements are two different numbers, so
they must become two different symbols: collapsing `xs[i]*xs[0]` into
one symbol squared proves a sum that is negative at `[1, -2]`.

An elementwise law transform (`f(g(xs, c))` with g bound to
`mathema.f.scale_seq`) that leaves the closed form unchanged has not
been applied, and the proof attempt refuses rather than reading
`f(g(xs, c))` as `f(xs)`.
"""
import textwrap

import pytest
import sympy

from mathema.symbolic._base import NotSymbolic
from mathema.symbolic._seq_common import (_termwise_sum_decide,
                                          map_sequence_elements)


def _seq():
    xs = sympy.IndexedBase("xs")
    i = sympy.Symbol("i", integer=True)
    L = sympy.Symbol("L", integer=True, nonnegative=True)
    return xs, i, L


def _status(lhs, relation=">="):
    r = _termwise_sum_decide(lhs, sympy.S.Zero, relation, {}, None)
    return None if r is None else r.status


def test_a_term_mixing_the_bound_element_with_a_fixed_one_is_not_proven():
    xs, i, L = _seq()
    assert _status(sympy.Sum(xs[i] * xs[0], (i, 0, L - 1))) != "proven"


def test_two_different_positions_are_two_different_numbers():
    xs, i, L = _seq()
    assert _status(sympy.Sum(xs[i] * xs[L - 1 - i], (i, 0, L - 1))) \
        != "proven"
    assert _status(sympy.Sum(xs[i] * xs[i + 1], (i, 0, L - 2))) \
        != "proven"


def test_a_genuine_termwise_square_still_proves():
    xs, i, L = _seq()
    assert _status(sympy.Sum(xs[i] * xs[i], (i, 0, L - 1))) == "proven"
    assert _status(sympy.Sum(xs[i] ** 2 + 1, (i, 0, L - 1)), ">") \
        in ("proven", None)


def test_two_sequences_at_the_same_position_stay_independent():
    xs, i, L = _seq()
    ys = sympy.IndexedBase("ys")
    assert _status(sympy.Sum(xs[i] * ys[i], (i, 0, L - 1))) != "proven"
    assert _status(sympy.Sum(xs[i] ** 2 + ys[i] ** 2, (i, 0, L - 1))) \
        == "proven"


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("termwise") / "termwisemod.py"
    p.write_text(textwrap.dedent('''
        def against_first(xs: list) -> float:
            t = 0
            for v in xs:
                t += v * xs[0]
            return t


        def squares(xs: list) -> float:
            t = 0
            for v in xs:
                t += v * v
            return t


        def count(xs: list) -> float:
            t = 0.0
            for v in xs:
                t = t + 1
            return t
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("termwisemod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _check(fn, law, **kw):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, **kw)])
    return p


@pytest.mark.parametrize("route", ["derive", None])
def test_a_sum_against_the_first_element_is_not_proven(mod, route):
    kw = {"route": route} if route else {}
    p = _check(mod.against_first, "for xs in R^n, f(xs) >= 0", **kw)
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert mod.against_first([1, -2]) < 0
    (witness,) = p.meta["mathema.counterexample_args"]
    assert mod.against_first(witness) < 0


def test_a_sum_of_squares_still_proves(mod):
    p = _check(mod.squares, "for xs in R^n, f(xs) >= 0")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_an_elementwise_transform_that_changes_nothing_refuses():
    xs, i, L = _seq()
    ys = sympy.IndexedBase("ys")
    with pytest.raises(NotSymbolic):
        map_sequence_elements(sympy.Sum(ys[i], (i, 0, L - 1)), xs,
                              lambda e, c: c * e, (sympy.Integer(2),))
    c = sympy.Symbol("c", real=True)
    mapped = map_sequence_elements(sympy.Sum(xs[i], (i, 0, L - 1)) + xs[0],
                                   xs, lambda e, c: c * e, (c,))
    assert mapped == sympy.Sum(c * xs[i], (i, 0, L - 1)) + c * xs[0]


def test_a_transform_of_a_fold_that_never_reads_an_element_is_not_proven(
        mod):
    p = _check(mod.count, "let c be [0.1, 10], f(g(xs, c)) == f(xs)",
               route="derive", funcs={"g": "mathema.f.scale_seq"})
    assert p.verdict != "proven" or p.route != "derive", (p.verdict,
                                                          p.sketch)
