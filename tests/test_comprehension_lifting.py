# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Comprehension sums on the derive route: sum(<genexp>), sum(xs),
sum(map(...)), and sum(filter(...)) desugar in the normalize pre-pass
to the explicit accumulator loop the sum machinery already closes, a
genexp's `if` filter becomes the exact Piecewise summand, and a
scalar-range genexp proves in closed form. Comprehension VALUES (a
built list) stay out (vector-valued), with the honest reason code, and
a comparison living only inside parentheses is named as
not-claim-syntax rather than mis-split."""
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim


def _mod(tmp_path, body, name):
    import importlib
    import sys
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module(name)
        importlib.reload(mod)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


_BODY = """
def sq_sum(xs: list) -> float:
    return sum(x * x for x in xs)

def pos_sum(xs: list) -> float:
    return sum(x for x in xs if x > 0)

def range_sq(n: int) -> float:
    return sum(i * i for i in range(n))

def plain_sum(xs: list) -> float:
    return sum(xs)

def mapped(xs: list) -> float:
    return sum(map(lambda v: v * 2, xs))

def filtered(xs: list) -> float:
    return sum(filter(lambda v: v > 0, xs))

def loop_twin(xs: list) -> float:
    total = 0.0
    for x in xs:
        total = total + x * x
    return total

def builds(xs: list) -> list:
    return [v * 2 for v in xs]
"""


def _run(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, route="derive", **kw)])
    return p


def test_genexp_sum_matches_the_explicit_loop_lift(tmp_path):
    import sympy

    from mathema import analyze
    from mathema.symbolic import lift_sum
    mod = _mod(tmp_path, _BODY, "cl_a")
    a = lift_sum(mod.sq_sum, analyze(mod.sq_sum))
    b = lift_sum(mod.loop_twin, analyze(mod.loop_twin))
    assert a is not None and b is not None

    def canon(e):
        (s_,) = e.atoms(sympy.Sum)
        idx, lo, hi = s_.limits[0]
        k = sympy.Symbol("k", integer=True)
        return sympy.Sum(s_.function.xreplace({idx: k}), (k, lo, hi))

    # identical up to the fresh dummy index's name
    assert canon(a.expr) == canon(b.expr)


def test_genexp_sums_prove(tmp_path):
    mod = _mod(tmp_path, _BODY, "cl_b")
    assert _run(mod.sq_sum, "f(xs) >= 0").verdict == "proven"
    # the filter is the exact Piecewise summand
    assert _run(mod.pos_sum, "f(xs) >= 0").verdict == "proven"
    p = _run(mod.range_sq,
             "for n in [0,20] subset Z, f(n) == n*(n-1)*(2*n-1)/6")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_bare_and_higher_order_sums_prove(tmp_path):
    mod = _mod(tmp_path, _BODY, "cl_c")
    assert _run(mod.plain_sum, "for xs in [0, 10], f(xs) >= 0").verdict == "proven"
    assert _run(mod.mapped, "for xs in [0, 5], f(xs) >= 0").verdict == "proven"
    assert _run(mod.filtered, "f(xs) >= 0").verdict == "proven"


def test_comprehension_value_stays_out_with_the_honest_code(tmp_path):
    from mathema.inventory import derivability_report
    mod = _mod(tmp_path, _BODY, "cl_d")
    report = derivability_report(mod.builds)
    assert report["liftable"] is False
    p = _run(mod.builds, "f(xs) == f(xs)")
    assert p.verdict != "proven"


def test_nested_comparison_is_not_misplit(tmp_path):
    from mathema.grammar import NoRelation, split_relation
    with pytest.raises(NoRelation) as e:
        split_relation("all(f(v) >= 0 for v in xs)")
    assert "inside parentheses" in str(e.value)
    assert "Sum(" in str(e.value)
    # ordinary nested comparisons in call args still split fine
    assert split_relation("f(max(a, b)) >= 0") == ("f(max(a, b))", ">=", "0")
