# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Claims about `floor`, `ceiling` and `%` are decided, not declined.

sympy cannot settle the sign of an expression containing an integer
part, so every ordinary fact about one (`x - floor(x)` lies in `[0, 1)`,
`step * floor(x / step) <= x`, a remainder is below its modulus) used to
come back undecided and fall to sampling.

Each of those integer parts satisfies an exact bound, which mathema can
supply even though sympy will not: `floor(u) = u - t` and
`ceiling(u) = u + t` for some `t` in `[0, 1)`, and `Mod(a, n)` is
`n * s` for some `s` in `[0, 1)` when `n` is positive, tightened to
`(n - 1) * s` with `s` in `[0, 1]` when both operands are integers. Replacing
each node with a fresh auxiliary carrying those bounds turns the
question into a bounded one the interval rung already decides.

The replacement is an over-approximation: the real integer parts move
with their arguments, these auxiliaries move independently, so the
relaxed expression's range CONTAINS the true range. That direction is
the safe one, and the second half of this file is what pins it. A claim
that is false must never come back proven, however the relaxation
widens things.
"""
import importlib
import math
import sys
import textwrap

import pytest

import mathema

_SRC = '''
    import math

    def frac_part(x: float) -> float:
        """Fractional part of x."""
        return x - math.floor(x)

    def floored(x: float) -> float:
        """Floor of x."""
        return float(math.floor(x))

    def floor_quantize(x: float, step: float) -> float:
        """Quantize x down to a multiple of step."""
        return step * math.floor(x / step)

    def half_down(n: int) -> int:
        """Floor of n/2."""
        return n // 2

    def ceil_div(a: int, b: int) -> int:
        """Ceiling of a/b."""
        return -(-a // b)

    def clock_hour(h: int, d: int) -> int:
        """Hour on a 24-hour clock after a duration."""
        return (h + d) % 24

    def real_remainder(x: float) -> float:
        """Remainder of x modulo 3.0."""
        return x % 3.0

    def floor_doubling(x: float) -> float:
        """floor(2x) - 2 floor(x), always 0 or 1."""
        return math.floor(2 * x) - 2 * math.floor(x)
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("intparts") / "ipmod.py"
    path.write_text(textwrap.dedent(_SRC))
    sys.path.insert(0, str(path.parent))
    sys.modules.pop("ipmod", None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module("ipmod")
    finally:
        sys.path.remove(str(path.parent))


def _verdict(fn, law):
    (p,) = mathema.claims.check_conjectures(
        fn, [mathema.claim(law, route="derive")])
    return p


# --- the facts that now prove ----------------------------------------------

@pytest.mark.parametrize("func,law", [
    ("frac_part", "for x in [-20,20], f(x) >= 0"),
    ("frac_part", "for x in [-20,20], f(x) <= 1"),
    ("floor_quantize",
     "for x in [-100,100], step in [0.1,10], f(x,step) <= x"),
    ("floor_quantize",
     "for x in [-100,100], step in [0.1,10], x - f(x,step) <= step"),
    ("half_down", "for n in [2,1000] subset Z, 2*f(n) <= n"),
    ("ceil_div",
     "for a in [1,500] subset Z, b in [1,30] subset Z, f(a,b) >= a/b"),
    ("ceil_div",
     "for a in [1,500] subset Z, b in [1,30] subset Z, f(a,b) <= a/b + 1"),
    ("clock_hour",
     "for h in [0,23] subset Z, d in [0,100] subset Z, f(h,d) <= 23"),
])
def test_an_integer_part_fact_proves(mod, func, law):
    p = _verdict(getattr(mod, func), law)
    assert p.verdict == "proven", (p.verdict, p.note)


# --- the soundness bar: an over-approximation must not over-claim -----------

@pytest.mark.parametrize("func,law,why", [
    ("frac_part", "for x in [-20,20], f(x) <= 0.5", "frac reaches 0.9"),
    ("frac_part", "for x in [-20,20], f(x) >= 0.5", "frac is 0 at integers"),
    ("frac_part", "for x in [-20,20], f(x) > 0", "frac is exactly 0 there"),
    ("floored", "for x in [-20,20], f(x) >= x", "floor(0.5) = 0 < 0.5"),
    ("half_down", "for n in [2,1000] subset Z, 2*f(n) == n", "odd n"),
    ("half_down", "for n in [2,1000] subset Z, 2*f(n) >= n", "odd n"),
    ("clock_hour",
     "for h in [0,23] subset Z, d in [0,100] subset Z, f(h,d) <= 22",
     "23 is reachable"),
    ("clock_hour",
     "for h in [0,23] subset Z, d in [0,100] subset Z, f(h,d) >= 1",
     "0 is reachable"),
    ("real_remainder", "for x in [-5,5], f(x) <= 2", "f(2.5) = 2.5"),
    ("real_remainder", "for x in [-5,5], f(x) <= 2.5", "f(2.9) = 2.9"),
    ("real_remainder", "for x in [0,5], f(x) != 2.5", "f(2.5) = 2.5"),
])
def test_a_false_integer_part_claim_never_proves(mod, func, law, why):
    p = _verdict(getattr(mod, func), law)
    assert p.verdict != "proven", (law, why, p.verdict, p.sketch)


def test_a_claim_and_its_negation_are_never_both_proven(mod):
    """The property directly, for this rung: the relaxation widens the
    range, and a widened range must not let both sides of a pair
    through."""
    for law, negation in [("f(x) >= 0", "f(x) < 0"),
                          ("f(x) <= 1", "f(x) > 1"),
                          ("f(x) <= 0.5", "f(x) > 0.5")]:
        a = _verdict(mod.frac_part, f"for x in [-20,20], {law}")
        b = _verdict(mod.frac_part, f"for x in [-20,20], {negation}")
        assert not (a.verdict == "proven" and b.verdict == "proven"), \
            (law, negation, a.verdict, b.verdict)


def test_a_real_remainder_is_bounded_by_its_modulus_not_one_less(mod):
    """`n - 1` bounds an integer remainder; a real one reaches any value
    below the modulus."""
    p = _verdict(mod.real_remainder, "for x in [-5,5], f(x) <= 3")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _verdict(mod.real_remainder, "for x in [-5,5], f(x) >= 0")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_a_relaxation_never_disproves_a_true_claim(mod):
    """The relaxed range contains the true one, so a relaxed expression
    that can be negative says nothing about the real one: the two
    floors here move together, the auxiliaries do not."""
    p = _verdict(mod.floor_doubling, "for x in [-5,5], f(x) >= 0")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)
    assert (p.meta or {}).get("mathema.corroboration") != "uncorroborated"


def test_a_relaxed_disproof_is_not_reported_as_one():
    import sympy

    from mathema.domain import Interval
    from mathema.symbolic._proof_support import _prove_relation
    x = sympy.Symbol("x", real=True)
    lhs = sympy.floor(2 * x) - 2 * sympy.floor(x)
    result = _prove_relation(lhs, sympy.Integer(0), ">=",
                             {"x": Interval(-5.0, 5.0)}, None, {"x": x})
    assert result.status != "disproven", result


# --- the relaxation itself --------------------------------------------------

def test_the_relaxation_declines_a_modulus_that_is_not_provably_positive():
    """`Mod(a, n)` lies in `[0, n-1]` only for positive `n`, so a
    modulus whose sign the domain does not settle has no remainder range
    to state and must be left alone."""
    import sympy

    from mathema.domain import Interval
    from mathema.symbolic._proof_support import _resolve_int_parts
    a, n = sympy.symbols("a n")
    expr = sympy.Mod(a, n)
    # n straddles zero, so nothing is claimed about the remainder
    out, dom, par = _resolve_int_parts(
        expr, {"a": Interval(0, 10), "n": Interval(-5, 5)},
        {"a": a, "n": n})
    assert out == expr and dom.keys() == {"a", "n"}, (out, dom)


def test_repeated_integer_parts_share_one_auxiliary():
    """`floor(u) - floor(u)` is exactly zero, so the same node must not
    be given two independent auxiliaries."""
    import sympy

    from mathema.domain import Interval
    from mathema.symbolic._proof_support import _resolve_int_parts
    x = sympy.Symbol("x", real=True)
    out, _dom, _par = _resolve_int_parts(
        sympy.floor(x) - sympy.floor(x), {"x": Interval(0, 10)}, {"x": x})
    assert sympy.simplify(out) == 0, out


def test_too_many_integer_parts_declines_rather_than_widening_forever():
    import sympy

    from mathema.domain import Interval
    from mathema.symbolic._proof_support import (_MAX_INT_PART_AUX,
                                                 _resolve_int_parts)
    xs = sympy.symbols(f"x0:{_MAX_INT_PART_AUX + 1}", real=True)
    expr = sum(sympy.floor(x) for x in xs)
    domain = {f"x{i}": Interval(0, 10) for i in range(len(xs))}
    params = {f"x{i}": x for i, x in enumerate(xs)}
    out, dom, _par = _resolve_int_parts(expr, domain, params)
    assert out == expr, out
    assert dom.keys() == domain.keys(), dom


def test_python_floor_div_and_math_floor_agree_with_the_claims(mod):
    """A guard on the fixtures themselves: the facts asserted above are
    about these implementations, so a reader can check them by hand."""
    assert mod.half_down(7) == 3 and 2 * 3 <= 7
    assert mod.ceil_div(7, 3) == 3 and 3 >= 7 / 3
    assert mod.clock_hour(23, 1) == 0
    assert math.isclose(mod.frac_part(2.25), 0.25)
    assert mod.floor_quantize(7.3, 2.0) == 6.0


def test_floor_division_in_a_claim_is_evaluable_on_the_probe_route(mod):
    from mathema.conjecture import check_conjectures, claim
    r = check_conjectures(mod.half_down, [claim(
        "for n in [0, 20] subset Z, f(n) == n // 2", route="probe")])[0]
    assert r.verdict == "holds", (r.verdict, r.note)


def test_a_false_floor_division_claim_is_falsified_with_a_witness(mod):
    from mathema.conjecture import check_conjectures, claim
    r = check_conjectures(mod.half_down, [claim(
        "for n in [0, 20] subset Z, f(n) == n // 3")])[0]
    assert r.verdict == "falsified", (r.verdict, r.note)
    assert r.counterexample
