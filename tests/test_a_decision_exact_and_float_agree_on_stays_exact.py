# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exact reading of a body (`mathema._exact_body`) holds an exact
number where the computation held a float, so a decision on it (a
comparison, a branch or loop test, a subscript or dict key, an order,
`floor`, `round`, `int()`, `//`, `%`, an exception a `try` catches) is
taken twice: by the exact reading and by the function's own float run
at the same point, decision by decision. Where the two agree at every
decision the exact path stands and the proof stays exact
(`derive:brute_force`); where any decision differs, the float run
reaches a decision the exact one does not, or one run raises where the
other does not, the point is undecided and the sweep is proven within
float64. A point where the runs differ never stands as exact.

A body touching no float has nothing to read differently and is proven
exactly, decorated with `@enforce_domain` or not.

Each function under test runs a `while` loop so derive cannot read it
and the sweep decides the claim."""
import math
import sys
import textwrap
from fractions import Fraction

import pytest

from mathema._exact_body import NotExact, exact_callee, exact_twin
from mathema.conjecture import check_conjectures, claim


def _spin():
    i = 0
    while i < 3:
        i += 1


def _check(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


def _exact(p):
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force", (p.route, p.note)
    assert "mathema.sweep_inexact" not in p.meta, p.meta


def _capped(p):
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
    assert p.route == "derive:brute_force:within_float64", (p.route, p.note)
    assert "mathema.exact_witness" not in p.meta, p.meta
    assert p.meta["mathema.sweep_inexact"]["points"] >= 1, p.meta


# --- a comparison and a branch --------------------------------------------

def under_threshold(x: int) -> int:
    _spin()
    if x / 10 <= 0.3:
        return 1
    return 0


def sum_branch(x: int) -> int:
    _spin()
    if x / 10 + 0.2 == 0.3:
        return 1
    return 0


def test_a_comparison_both_runs_decide_alike_stays_exact():
    # 1/10, 2/10, 3/10 <= 3/10, and 0.1, 0.2, 0.3 <= 0.3 in float
    _exact(_check(under_threshold, "for x in {1, 2, 3}, f(x) == 1"))


def test_a_comparison_the_float_run_decides_otherwise_is_capped():
    # 1/10 + 2/10 == 3/10 exactly; 0.1 + 0.2 is 0.30000000000000004
    _capped(_check(sum_branch, "for x in {1}, f(x) == 0"))


def test_the_twin_takes_an_agreed_decision_and_declines_a_differing_one():
    assert exact_callee(under_threshold)(3) == 1
    with pytest.raises(NotExact):
        exact_callee(sum_branch)(1)


def test_the_bare_twin_still_declines_every_decision_on_a_stand_in():
    def compares(y):
        return y <= 0.3
    with pytest.raises(NotExact):
        exact_twin(compares)(Fraction(1, 10))


def truncated(x: int) -> int:
    _spin()
    return int(0.1 * 3 * 10) + 0 * x


def floored(x: int) -> int:
    _spin()
    return math.floor(x - 1e-17)


def test_a_rounding_both_runs_reach_alike_stays_exact():
    # int(3.0000000000000004) and int(3) are both 3
    _exact(_check(truncated, "for x in {1}, f(x) == 3"))


def test_a_rounding_the_float_run_reaches_otherwise_is_capped():
    # x - 1e-17 is x in float, floor x; exactly it is below x, floor x - 1
    _capped(_check(floored, "for x in {1, 2}, f(x) == x"))


# --- a loop revisiting a decision -----------------------------------------

def halves(n: int) -> int:
    _spin()
    t = 0.0
    k = 0
    while t < n:
        t += 0.5
        k += 1
    return k


def tenths(n: int) -> int:
    _spin()
    t = 0.0
    k = 0
    while t < 1.0:
        t += 0.1
        k += 1
    return k + 0 * n


def test_a_loop_whose_every_test_agrees_stays_exact():
    # halves are exact in float: both runs loop 2n times
    _exact(_check(halves, "for n in {1, 2, 3}, f(n) == 2 * n"))


def test_a_loop_whose_test_differs_on_a_later_pass_is_capped():
    # ten passes exactly, eleven in float: the eleventh test differs
    _capped(_check(tenths, "for n in {1, 2}, f(n) == 11"))


# --- a decision inside a helper the body calls ----------------------------

def _at_most(y):
    if y <= 0.3:
        return 1
    return 0


def _summed_at_most(y):
    if y + 0.2 <= 0.3:
        return 1
    return 0


def via_helper(x: int) -> int:
    _spin()
    return _at_most(x / 10)


def via_summing_helper(x: int) -> int:
    _spin()
    return _summed_at_most(x / 10)


def test_a_helper_whose_decisions_agree_stays_exact():
    _exact(_check(via_helper, "for x in {1, 2, 3}, f(x) == 1"))


def test_a_helper_whose_decision_differs_is_capped():
    # 1/10 + 2/10 <= 3/10 exactly; 0.30000000000000004 > 0.3 in float
    _capped(_check(via_summing_helper, "for x in {1}, f(x) >= 0"))


# --- an order by a key ----------------------------------------------------

def first_by_key(x: int) -> int:
    _spin()
    values = [0.1 * x + 0.2, 0.3]
    return sorted(range(2), key=lambda i: values[i])[0]


def test_an_order_both_runs_reach_alike_stays_exact():
    # 0.4 and 0.5 after 0.3 either way
    _exact(_check(first_by_key, "for x in {2, 3}, f(x) == 1"))


def test_an_order_the_float_run_reaches_otherwise_is_capped():
    # exactly a tie, kept in place; 0.30000000000000004 after 0.3 in float
    _capped(_check(first_by_key, "for x in {1}, f(x) >= 0"))


# --- a dict key -----------------------------------------------------------

def priced(x: int) -> float:
    _spin()
    table = {0.5: 2.0, 1.0: 3.0}
    return table[x * 0.5]


def found(x: int) -> int:
    _spin()
    table = {0.3: 1}
    key = x * 0.1 + 0.2
    if key in table:
        return table[key]
    return 0


def test_a_dict_key_both_runs_find_alike_stays_exact():
    _exact(_check(priced, "for x in {1, 2}, f(x) == x + 1"))


def test_a_dict_key_the_float_run_misses_is_capped():
    # 3/10 is the key exactly; 0.30000000000000004 is not in float
    _capped(_check(found, "for x in {1}, f(x) >= 0"))


# --- a float run that raises where the exact one does not -----------------

def overflow_caught(x: int) -> float:
    _spin()
    try:
        return 10.0 ** (300 * x)
    except OverflowError:
        return -1.0


def test_a_float_run_that_raises_where_the_exact_one_does_not_is_capped():
    # 10.0 ** 600 overflows in float; 10 ** 600 is exact
    _capped(_check(overflow_caught, "for x in {1, 2}, f(x) <= 1e300"))
    with pytest.raises(NotExact):
        exact_callee(overflow_caught)(2)


def test_both_runs_raising_alike_at_the_same_line_is_one_outcome():
    def inverse(x):
        return 1 / (x * 0.5 - 0.5)
    with pytest.raises(ZeroDivisionError):
        exact_callee(inverse)(1)
    assert exact_callee(inverse)(3) == 1


# --- a body touching no float ---------------------------------------------

def lookup_key(name: str) -> str:
    _spin()
    return name.strip().lower()


_ENFORCED = '''
    from mathema import enforce_domain

    @enforce_domain({"name": frozenset({"Alice", " alice ", "ALICE"})})
    def enforced_key(name: str) -> str:
        """The lookup key for a username."""
        i = 0
        while i < 3:
            i += 1
        return name.strip().lower()
'''


@pytest.fixture
def enforced(tmp_path, monkeypatch):
    (tmp_path / "shadow_enforced_mod.py").write_text(textwrap.dedent(_ENFORCED))
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    sys.modules.pop("shadow_enforced_mod", None)
    yield importlib.import_module("shadow_enforced_mod").enforced_key
    sys.modules.pop("shadow_enforced_mod", None)


def test_a_body_touching_no_float_is_proven_exactly():
    _exact(_check(lookup_key,
                  'for name in {"Alice", " alice ", "ALICE"}, '
                  'f(name) == "alice"'))


def test_a_domain_enforced_body_touching_no_float_is_proven_exactly(enforced):
    _exact(_check(enforced, 'f(name) == "alice"'))


def test_the_domain_check_of_an_enforced_function_still_raises(enforced):
    with pytest.raises(Exception) as caught:
        exact_callee(enforced)("bob")
    assert type(caught.value).__name__ == "DomainError", caught.value
