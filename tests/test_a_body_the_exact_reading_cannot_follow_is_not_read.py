# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exact reading of a body (`mathema._exact_body`) runs it on exact
numbers standing in for the computation's floats. A construct whose
value depends on a number's text rather than its mathematics (`str(x)`,
an f-string, `x.hex()`, an explicit `Fraction(...)`, `math.isclose`,
...) would send the exact run down a different path from the
computation, so a body holding one is refused before it runs: the point
is undecided, the sweep takes the inexact path (`mathema.sweep_inexact`,
`mathema.sweep_precision`) and a correct function is never falsified on
a path it did not take. A question about the number's type (`type(x)
is float`, `x.__class__`, `isinstance(x, float)`) is answered as the
computation would, and such a body keeps its exact verdict, as every
body free of refused constructs does.

Each body runs a `while` loop so derive cannot read it and the sweep
decides the claim."""
import math
import struct
from decimal import Decimal
from fractions import Fraction

import pytest

from mathema._exact_body import exact_callee, exact_twin, unfaithful
from mathema.conjecture import check_conjectures, claim


def _spin():
    i = 0
    while i < 3:
        i += 1


def typed(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    if type(x) is float:
        return x * 0.5
    return x * 100.0


def by_class(x: float) -> float:
    _spin()
    if x.__class__ is float:
        return x * 0.5
    return x * 100.0


def is_not_type(x: float) -> float:
    _spin()
    if type(x) is not float:
        return x * 100.0
    return x * 0.5


def via_str(x: float) -> float:
    _spin()
    if "/" in str(x):
        return x * 100.0
    return x * 0.5


def via_repr(x: float) -> float:
    _spin()
    if "/" in repr(x):
        return x * 100.0
    return x * 0.5


def via_format(x: float) -> float:
    _spin()
    if "/" in format(x):
        return x * 100.0
    return x * 0.5


def via_fstring(x: float) -> float:
    _spin()
    if "/" in f"{x}":
        return x * 100.0
    return x * 0.5


def via_percent(x: float) -> float:
    _spin()
    if "/" in "%s" % x:
        return x * 100.0
    return x * 0.5


def via_str_format(x: float) -> float:
    _spin()
    if "/" in "{}".format(x):
        return x * 100.0
    return x * 0.5


def via_hex(x: float) -> float:
    _spin()
    if float.fromhex(x.hex()) == x:
        return x * 0.5
    return x * 100.0


def via_ratio(x: float) -> float:
    _spin()
    n, d = x.as_integer_ratio()
    return n / (2 * d)


def via_fraction(x: float) -> float:
    _spin()
    if isinstance(x, Fraction):
        return x * 100.0
    return Fraction(x) / 2


def via_decimal(x: float) -> float:
    _spin()
    return float(Decimal(x) / 2)


def via_isclose(x: float) -> float:
    _spin()
    if math.isclose(x * 0.5, x / 2):
        return x * 0.5
    return x * 100.0


def via_struct(x: float) -> float:
    _spin()
    (y,) = struct.unpack("d", struct.pack("d", x))
    return y * 0.5


def via_id(x: float) -> float:
    _spin()
    if id(x) == id(x):
        return x * 0.5
    return x * 100.0


def via_isinstance_rational(x: float) -> float:
    _spin()
    if isinstance(x, Fraction):
        return x * 100.0
    return x * 0.5


def via_frexp(x: float) -> float:
    _spin()
    m, e = math.frexp(x)
    return math.ldexp(m, e - 1)


def via_local_struct(x: float) -> float:
    _spin()
    import struct as s
    (y,) = s.unpack("d", s.pack("d", x))
    return y * 0.5


def via_local_fraction(x: float) -> float:
    _spin()
    from fractions import Fraction as Q
    return Q(x) / 2


def half(x: float) -> float:
    _spin()
    return x * 0.5


def root_sq(x: float) -> float:
    _spin()
    return math.sqrt(x) ** 2


def off(x: float) -> float:
    _spin()
    return x + 2e-9


def guarded(x: float) -> float:
    _spin()
    if isinstance(x, float):
        return x * 0.5
    return x * 100.0


REFUSED = [via_str, via_repr, via_format, via_fstring, via_percent,
           via_str_format, via_hex, via_ratio, via_fraction, via_decimal,
           via_isclose, via_struct, via_id, via_isinstance_rational,
           via_frexp, via_local_struct, via_local_fraction]

#: bodies asking the number's type, answered as the computation would
ANSWERED = [typed, by_class, is_not_type, guarded]

#: the refused bodies a finite sweep runs: `id(x)` is a hidden read to
#: the strict examination, which declines the sweep before any reading
SWEPT = [fn for fn in REFUSED if fn is not via_id]

#: points the computation takes the float branch at (an integer-valued
#: set reaches a function as ints, and `typed(1)` is 100.0 in Python)
_FLOATS = "for x in {0.5, 1.5, 2.5}, f(x) == x / 2"


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


def test_the_reported_false_falsification_is_gone():
    # `type(x)` of a Fraction standing in for 0.5 is `float` in the
    # twin, so the exact run takes the `x * 0.5` branch the computation
    # took and the claim is proven exactly
    p = _check(typed, _FLOATS)
    assert p.verdict == "proven", (p.verdict, p.route, p.counterexample)
    assert p.route == "derive:brute_force", p.route
    assert "mathema.exact_witness" not in p.meta, p.meta
    assert "mathema.sweep_inexact" not in p.meta, p.meta


def test_the_reported_repro_over_integers_fails_by_execution_alone():
    # the set {1, 2, 3} reaches f as ints, and typed(1) is 100.0 in
    # Python: the computation itself fails there, no exact reading
    # involved
    assert typed(1) == 100.0 and typed(1.0) == 0.5
    p = _check(typed, "for x in {1, 2, 3}, f(x) == x / 2")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert p.counterexample == "x = 1", p.counterexample
    assert "mathema.exact_witness" not in p.meta, p.meta


@pytest.mark.parametrize("fn", SWEPT, ids=lambda f: f.__name__)
def test_a_correct_body_the_reading_cannot_follow_is_not_falsified(fn):
    p = _check(fn, _FLOATS)
    assert p.verdict != "falsified", (fn.__name__, p.verdict, p.counterexample)
    assert p.route.startswith("derive:brute_force"), p.route
    assert "mathema.exact_witness" not in p.meta, p.meta
    assert p.meta["mathema.sweep_inexact"]["points"] == 3, p.meta
    assert p.meta["mathema.sweep_precision"]["points"] == 3, p.meta


def test_a_hidden_read_declines_the_sweep_before_any_reading():
    p = _check(via_id, _FLOATS)
    assert p.verdict != "falsified", (p.verdict, p.route, p.counterexample)
    assert p.route == "probe", p.route


@pytest.mark.parametrize("fn", REFUSED, ids=lambda f: f.__name__)
def test_the_refusal_is_found_on_the_syntax_tree(fn):
    found = unfaithful(fn)
    assert found, fn.__name__
    assert exact_twin(fn) is None, fn.__name__
    with pytest.raises(Exception) as caught:
        exact_callee(fn)(1.0)
    assert type(caught.value).__name__ == "NotExact", caught.value


def test_the_refusal_names_the_construct():
    found = unfaithful(via_str)
    assert any("str(x)" in text for text in found), found


def test_the_derive_witness_reading_refuses_the_same_bodies():
    from mathema.analysis import effective_facts
    from mathema.gates import _point_evaluator
    cj = claim("for x in [1, 2], f(x) == x / 2")
    deps = _point_evaluator(cj, via_str, effective_facts(via_str),
                            dict(cj.domain), {})
    assert deps is not None
    assert deps["evaluate"].exact_as_written({"x": 1.0}) is None
    deps = _point_evaluator(cj, half, effective_facts(half),
                            dict(cj.domain), {})
    assert deps["evaluate"].exact_as_written({"x": 1.0}) == (Fraction(1, 2),
                                                             Fraction(1, 2))


@pytest.mark.parametrize("fn,law,verdict", [
    (half, "for x in {1, 2, 3}, f(x) == x / 2", "proven"),
    (half, _FLOATS, "proven"),
    (root_sq, "for x in {2, 3, 5}, f(x) == x", "proven"),
    (off, "for x in {1, 2}, f(x) == x", "falsified"),
    *[(fn, _FLOATS, "proven") for fn in ANSWERED],
], ids=lambda v: getattr(v, "__name__", None))
def test_a_body_the_reading_follows_keeps_its_verdict(fn, law, verdict):
    p = _check(fn, law)
    assert p.verdict == verdict, (fn.__name__, p.verdict, p.route, p.note)
    assert p.route == "derive:brute_force", p.route
    assert not unfaithful(fn), fn.__name__
