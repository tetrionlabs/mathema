# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A finite sweep reads the function's body exactly (`mathema._exact_body`),
and every Python function that body calls is read the same way: its own
source scanned for the constructs the reading refuses, its own literals
and divisions exact, its own question about a number's type answered as
the computation would. A function that cannot be read so (a library
function, a lambda, a decorated function, a method on an object, one
whose own body is refused) leaves the point undecided, so the sweep is
proven within float64 rather than decided down a path the computation
did not take. The function as written never runs on an exact number
standing in for a float.

Each function under test runs a `while` loop so derive cannot read it
and the sweep decides the claim."""
import functools
import statistics

import pytest

from mathema.conjecture import check_conjectures, claim


def _spin():
    i = 0
    while i < 3:
        i += 1


# helper with a type check, called from the body
def _helper(y):
    if isinstance(y, float):
        return y
    return y * 100


def via_helper(x: int) -> float:
    _spin()
    return _helper(x / 2)


def _helper_type(y):
    if type(y) is float:
        return y
    return y * 100


def via_helper_type(x: int) -> float:
    _spin()
    return _helper_type(x / 2)


def _helper_str(y):
    return float(str(y)[:5])


def via_helper_str(x: int) -> float:
    _spin()
    return _helper_str(x / 4)


# helper adding an error only on a real float
def _helper_bug(y):
    if isinstance(y, float):
        return y + 1e-12
    return y


def via_helper_bug(x: int) -> float:
    _spin()
    return _helper_bug(x / 2)


def _at_most_threshold(y):
    if y <= 0.3:
        return 1
    return 0


def under_threshold(x: int) -> int:
    _spin()
    return _at_most_threshold(x / 10)


def via_map_bug(x: int) -> float:
    _spin()
    return list(map(_helper_bug, [x / 2]))[0]


def stat_mean(x: int) -> float:
    _spin()
    return statistics.mean([0.1, 0.2, 0.3]) * x


_halve = lambda y: y * 0.5  # noqa: E731


def via_lambda(x: int) -> float:
    _spin()
    return _halve(x)


class _Scale:
    def apply(self, y):
        return y * 0.5


_SCALE = _Scale()


def via_method(x: int) -> float:
    _spin()
    return _SCALE.apply(x)


def _logged(fn):
    @functools.wraps(fn)
    def inner(*args):
        return fn(*args)
    return inner


@_logged
def _decorated_half(y):
    return y * 0.5


def via_decorated(x: int) -> float:
    _spin()
    return _decorated_half(x)


def _is_even(n):
    return True if n == 0 else _is_odd(n - 1)


def _is_odd(n):
    return False if n == 0 else _is_even(n - 1)


def parity_half(n: int) -> float:
    _spin()
    return 0.5 if _is_even(n) else 1.5


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn,law", [
    (via_helper, "for x in {1, 2, 3}, f(x) == x / 2"),
    (via_helper_type, "for x in {1, 2, 3}, f(x) == x / 2"),
    (parity_half, "for n in {2, 4, 6}, f(n) == 0.5"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_helper_read_exactly_takes_the_computations_path(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route
    assert "mathema.exact_witness" not in p.meta, p.meta


def test_a_helper_comparing_at_its_own_threshold_is_not_falsified():
    # 3/10 <= 3/10 exactly, and 0.3 <= 0.3 in float: the helper returns 1
    p = _check(under_threshold, "for x in {1, 2, 3}, f(x) == 1")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
    assert p.route.startswith("derive:brute_force"), p.route
    assert "mathema.exact_witness" not in p.meta, p.meta


@pytest.mark.parametrize("fn", [via_helper_bug, via_map_bug],
                         ids=lambda f: f.__name__)
def test_a_helper_adding_a_literal_is_falsified_on_the_mathematics(fn):
    # the helper adds 1e-12 to a float: exactly x/2 + 1/10^12, which the
    # float allowance absorbs
    p = _check(fn, "for x in {1, 2, 3}, f(x) == x / 2")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force", p.route
    witness = p.meta["mathema.exact_witness"]
    assert witness["reading"] == "mathematics", witness
    assert witness["computation"] == "holds within its allowance", witness
    assert witness["exact"] == "500000000001/1000000000000 vs 1/2", witness


@pytest.mark.parametrize("fn,law", [
    (via_helper_str, "for x in {1, 2}, f(x) == x / 4"),
    (stat_mean, "for x in {1, 2, 3}, f(x) == x / 5"),
    (via_lambda, "for x in {1, 2, 3}, f(x) == x / 2"),
    (via_method, "for x in {1, 2, 3}, f(x) == x / 2"),
    (via_decorated, "for x in {1, 2, 3}, f(x) == x / 2"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_function_the_reading_cannot_follow_leaves_the_point_undecided(fn, law):
    p = _check(fn, law)
    assert p.verdict == "proven", (fn.__name__, p.verdict, p.route, p.sketch)
    assert p.route == "derive:brute_force:within_float64", p.route
    assert "mathema.exact_witness" not in p.meta, p.meta
    assert p.meta["mathema.sweep_inexact"]["points"] >= 1, p.meta


def test_the_function_as_written_never_runs_on_an_exact_number():
    from fractions import Fraction

    from mathema._exact_body import exact_callee
    seen: list = []

    def _record(y):
        # the type as the body sees it: `float` in the computation and
        # in its exact reading, `Fraction` only if run as written
        seen.append(type(y).__name__)
        return y

    def body(x):
        return _record(x / 2)
    assert exact_callee(body)(3) == Fraction(3, 2)
    # the function's own float run, then its exact reading
    assert seen == ["float", "float"], seen
