# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The derive route reasons over the reals and the declared sets, and
infinity there is infinity (P1). Nothing about the float carrier reaches
it: not the largest double, not the exponent where `math.exp` overflows,
not a declared pseudo-infinity. A proof over R is a proof over R, and an
overflow is a fact about the computation, reported by the `[float]`
companion and the probe route.

What still enters derive is mathematics and the author's own definition
of the function (P2): the real domain of the primitives, and a raise the
function's own source states explicitly, whatever its exception type."""
import math
import os

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


def sq(x):
    return x**2


def ex(x):
    return math.exp(x)


def g(x):
    if x > 5:
        raise OverflowError("too big")
    return x


def _derive(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, route="derive", **kw)])
    return p


def _rows(fn, law):
    rows = {p.name: p for p in mathema.check(fn, claims=[law]).probes}
    (name,) = [n for n in rows if not n.endswith("[float]")
               and rows[n].statement.endswith(law.split(", ", 1)[-1])]
    return rows[name], rows.get(f"{name}[float]")


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("law", ["for x in R, f(x) >= 0",
                                 "for x in R, x**2 >= 0"])
def test_a_square_is_proven_over_the_reals_with_or_without_a_pseudo_infinity(law):
    plain = _derive(sq, law)
    bounded = _derive(sq, law, pseudo_infinity=1e100)
    for p in (plain, bounded):
        assert p.verdict == "proven", (p.verdict, p.note)
        assert p.route == "derive", p.route
        assert p.condition.startswith("∀ x ∈ ℝ"), p.condition
        assert "e+" not in p.condition and "[" not in p.condition, p.condition
    assert (plain.verdict, plain.condition) == (bounded.verdict,
                                                bounded.condition)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("law", ["for x in R, f(x) > 0",
                                 "for x in R, exp(x) > 0"])
def test_an_exponential_is_positive_over_the_reals(law):
    p = _derive(ex, law)
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.route.startswith("derive"), p.route


@pytest.mark.needs_full_proof_budget
def test_the_square_companion_reports_the_overflow_at_the_float_corner():
    proof, companion = _rows(sq, "for x in R, f(x) >= 0")
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert companion is not None
    assert companion.verdict == "falsified", (companion.verdict,
                                              companion.note)
    assert "e+308" in companion.counterexample, companion.counterexample
    assert "OverflowError" in (companion.counterexample
                               + companion.sketch), companion.sketch


@pytest.mark.needs_full_proof_budget
def test_the_exponential_companion_reports_the_overflow_at_a_corner():
    # `>= 0` so the underflow corner (exp(-1e308) is exactly 0.0) passes
    # and the witness is the overflow one
    proof, companion = _rows(ex, "for x in R, f(x) >= 0")
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert companion is not None
    assert companion.verdict == "falsified", (companion.verdict,
                                              companion.note)
    assert "raises OverflowError" in (companion.counterexample + " "
                                      + companion.sketch), companion.sketch


def test_the_symbolic_package_reads_no_carrier_constant():
    root = os.path.join(os.path.dirname(mathema.__file__), "symbolic")
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                text = fh.read()
            for constant in ("_DBL_MAX", "709.78", "sys.float_info.max"):
                assert constant not in text, (name, constant)


def test_an_explicit_raise_in_the_source_still_falsifies_on_derive():
    p = _derive(g, "for x in [0, 10], f(x) >= 0")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.route == "derive", p.route
    assert p.meta.get("mathema.corroboration") == "reproduced", p.meta
    assert p.counterexample


@pytest.mark.needs_full_proof_budget
def test_an_explicit_overflow_raise_bounds_the_definedness_region():
    (inside,) = check_conjectures(
        g, [claim("x <= 5", name="is_defined", route="derive")])
    assert inside.verdict == "proven", (inside.verdict, inside.note)
    assert inside.route.startswith("derive"), inside.route
    (wider,) = check_conjectures(
        g, [claim("x <= 10", name="is_defined", route="derive")])
    assert wider.verdict == "falsified", (wider.verdict, wider.note)
    assert wider.counterexample
