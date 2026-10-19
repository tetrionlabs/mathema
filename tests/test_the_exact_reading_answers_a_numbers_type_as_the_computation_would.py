# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exact reading of a body (`mathema._exact_body`) runs it on exact
numbers standing in for the computation's floats, and answers a
question about a number's type as the computation would: `type(x)`,
`x.__class__`, `isinstance(x, float)` and `type(x) is float` say
`float` of an exact number standing where the computation had a float,
`int` of an int the claim or the body wrote. A value the computation
holds as a float is held by the twin as a Fraction or a sympy number,
never a bare int (`float(3)`, `math.sqrt(4)`), so a body
that branches on the type takes the branch the computation took and a
correct body proves exactly. A type reached by any path other than its
bare builtin name (`builtins.float`, a module alias) and text turned
back into a number stay refused: the point is undecided, the sweep is
proven within float64.

Each body runs a `while` loop so derive cannot read it and the sweep
decides the claim."""
import builtins
import math
from fractions import Fraction

import pytest

from mathema._exact_body import exact_twin, unfaithful
from mathema._exact_side import ExactInt
from mathema.conjecture import check_conjectures, claim

#: the real `float` under another name: the twin cannot tell it from
#: its own exact `float`, so a comparison against it is refused
Real = float


def _spin():
    i = 0
    while i < 3:
        i += 1


def typed(x: float) -> float:
    _spin()
    if type(x) is float:
        return x * 0.5
    return x * 100.0


def typed_not(x: float) -> float:
    _spin()
    if type(x) is not float:
        return x * 100.0
    return x * 0.5


def by_class(x: float) -> float:
    _spin()
    if x.__class__ is float:
        return x * 0.5
    return x * 100.0


def asserted_type(x: float) -> float:
    _spin()
    assert type(x) is float
    return x * 0.5


def asserted_isinstance(x: float) -> float:
    _spin()
    assert isinstance(x, float)
    return x * 0.5


def typed_int(n: int) -> float:
    _spin()
    if type(n) is int:
        return n / 2
    return n * 100.0


def named(x: float) -> float:
    _spin()
    if type(x).__name__ == "float":
        return x * 0.5
    return x * 100.0


def in_tuple(x: float) -> float:
    _spin()
    if type(x) in (float, int):
        return x * 0.5
    return x * 100.0


def whole(n: int) -> float:
    # float(n) is a float in the computation, whole or not
    _spin()
    y = float(n) * 2
    if isinstance(y, float):
        return y / 4
    return y * 100


def whole_type(n: int) -> float:
    _spin()
    y = float(n)
    if type(y) is float:
        return y * 0.5
    return y * 100.0


def rooted(x: float) -> float:
    # math.sqrt(4) is 2.0, a float
    _spin()
    y = math.sqrt(x)
    if isinstance(y, float):
        return y * y
    return -1.0


def powered(x: float) -> float:
    # 4 ** 0.5 is 2.0, a float
    _spin()
    y = x ** 0.5
    if isinstance(y, int):
        return -1.0
    return y * y


def two_to(n: int) -> float:
    # 2 ** 3.0 is 8.0, a float
    _spin()
    y = 2 ** float(n)
    if isinstance(y, float):
        return y
    return -1.0


def floor_half(x: float) -> float:
    # 5.5 // 2 is 2.0, a float
    _spin()
    y = x // 2
    if isinstance(y, float):
        return y
    return -1.0


def split(x: float) -> float:
    # divmod(5.5, 2) is (2.0, 1.5), two floats
    _spin()
    q, r = divmod(x, 2)
    if isinstance(q, float) and isinstance(r, float):
        return q * 2 + r
    return -1.0


def aliased(x: float) -> float:
    _spin()
    if type(x) is Real:
        return x * 0.5
    return x * 100.0


def via_builtins(x: float) -> float:
    _spin()
    if type(x) is builtins.float:
        return x * 0.5
    return x * 100.0


def is_fraction(x: float) -> float:
    _spin()
    if type(x) is Fraction:
        return x * 100.0
    return x * 0.5


def from_text(x: float) -> float:
    _spin()
    return float(f"{x:.2f}") * 0.5


def from_str(x: float) -> float:
    _spin()
    return float(str(x)) / 2


def kinds(x):
    return (isinstance(x, float), type(x) is float, x.__class__ is float,
            isinstance(x, int), type(x) is int, type(x).__name__)


#: points the computation takes the float branch at
_FLOATS = "for x in {0.5, 1.5, 2.5}, f(x) == x / 2"


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn,law", [
    (typed, _FLOATS),
    (typed_not, _FLOATS),
    (by_class, _FLOATS),
    (asserted_type, _FLOATS),
    (asserted_isinstance, _FLOATS),
    (named, _FLOATS),
    (in_tuple, _FLOATS),
    (typed_int, "for n in {1, 2, 3}, f(n) == n / 2"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_body_branching_on_the_type_takes_the_computations_branch(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route, p.note,
                                   p.counterexample)
    assert p.route == "derive:brute_force", p.route
    assert "mathema.sweep_inexact" not in p.meta, p.meta
    assert not unfaithful(fn), fn.__name__


@pytest.mark.parametrize("fn,law", [
    (whole, "for n in {1, 2, 3}, f(n) == n / 2"),
    (whole_type, "for n in {1, 2, 3}, f(n) == n / 2"),
    (rooted, "for x in {4, 9}, f(x) == x"),
    (powered, "for x in {4, 9}, f(x) == x"),
    (two_to, "for n in {1, 2, 3}, f(n) == 2 ** n"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_whole_value_the_computation_had_as_a_float_is_still_a_float(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route, p.note,
                                   p.counterexample)
    assert p.route == "derive:brute_force", p.route
    assert "mathema.exact_witness" not in p.meta, p.meta


@pytest.mark.parametrize("fn,law", [
    (floor_half, "for x in {5.5, 7.5}, f(x) == floor(x / 2)"),
    (split, "for x in {5.5, 7.5}, f(x) == x"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_floor_of_a_float_is_declined_and_proven_within_float64(fn, law):
    # `x // 2` and `divmod(x, 2)` of a value the computation held as a
    # float are a decision the reading declines
    p = _check(fn, law)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route, p.note,
                                   p.counterexample)
    assert p.route == "derive:brute_force:within_float64", p.route
    assert "mathema.exact_witness" not in p.meta, p.meta


def test_the_twin_answers_type_and_isinstance_alike():
    twin = exact_twin(kinds)
    assert twin is not None and not unfaithful(kinds)
    assert twin(Fraction(1, 2)) == (True, True, True, False, False, "float")
    assert twin(ExactInt(3)) == (False, False, False, True, True, "int")
    assert twin(3) == (False, False, False, True, True, "int")
    assert twin(True) == (False, False, False, True, False, "bool")
    assert twin("3") == (False, False, False, False, False, "str")
    sympy = pytest.importorskip("sympy")
    assert twin(sympy.sqrt(2)) == (True, True, True, False, False, "float")
    assert kinds(0.5) == (True, True, True, False, False, "float")
    assert kinds(3) == (False, False, False, True, True, "int")


def test_the_twin_holds_a_float_the_computation_had_as_a_fraction():
    def every(n, x):
        return (float(n), math.sqrt(x), x ** 0.5, 2 ** float(n), n * 2)
    twin = exact_twin(every)
    assert twin is not None
    out = twin(ExactInt(3), Fraction(9))
    assert out[:4] == (Fraction(3), Fraction(3), Fraction(3), Fraction(8))
    assert all(type(v) is Fraction for v in out[:4]), out
    # an int stays an int where the computation's value is one
    assert out[4] == 6 and isinstance(out[4], int)


def test_the_twin_declines_a_floor_or_rounding_of_a_float():
    from mathema._exact_body import NotExact

    def floor_division(x):
        return x // 2

    def quotient_remainder(x):
        return divmod(x, 2)

    def rounding_to(x):
        return round(x, 1)

    def whole_below(x):
        return math.floor(x)

    def rounding(x):
        return round(x)
    for fn in (floor_division, quotient_remainder, rounding_to, whole_below,
               rounding):
        twin = exact_twin(fn)
        assert twin is not None, fn.__name__
        # on a value the computation held as a float, a decision
        with pytest.raises(NotExact):
            twin(Fraction(9))
        # on an int, the computation's own
        assert twin(9) == fn(9), fn.__name__


@pytest.mark.parametrize("fn", [aliased, via_builtins, is_fraction, from_text,
                                from_str], ids=lambda f: f.__name__)
def test_a_type_by_another_name_or_text_made_a_number_stays_refused(fn):
    assert unfaithful(fn), fn.__name__
    assert exact_twin(fn) is None, fn.__name__
    p = _check(fn, _FLOATS)
    assert p.verdict != "falsified", (fn.__name__, p.verdict, p.counterexample)
    assert p.route == "derive:brute_force:within_float64", (fn.__name__, p.route)
    assert "mathema.exact_witness" not in p.meta, p.meta
