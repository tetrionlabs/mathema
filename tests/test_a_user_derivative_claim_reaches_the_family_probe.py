# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim a user writes as `d(f(x), x) >= 0` (or another derivative-sign
statement a built-in family states) over a body derive cannot read is
decided by that family's own probe: the same verdict, route, sample
count and witness as the family's row with the identical statement, and
a note naming the family check that decided it. A body derive can read
is still decided by derive."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim


def sigmoid_stable(x: float) -> float:
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    z = math.exp(x)
    return z / (1 + z)


def paid(payment: float) -> float:
    total = 0.0
    month = 0
    while month < 12:
        total = total + payment * (1.01 ** month)
        month += 1
    return total


def remaining(payment: float) -> float:
    balance = 1000.0
    for _ in range(12):
        balance = balance * 1.01 - payment
    return balance


def square_loop(x: float) -> float:
    total = 0.0
    for _ in range(3):
        total += x * x
    return total


def label(x: float) -> str:
    out = ""
    for _ in range(2):
        out += "a" if x >= 0 else "b"
    return out


def cube(x: float) -> float:
    return x ** 3 + x


def _user_and_family(fn, text: str, family: str):
    """The user's claim and the family's row, each checked on its own,
    as each would be from a fresh draw."""
    (user,) = check_conjectures(fn, [claim(text, name="mine")])
    (row,) = check_conjectures(fn, [claim(text, name=family)])
    return user, row


@pytest.mark.parametrize("fn, text, family, verdict", [
    (sigmoid_stable, "for x in [-10, 10], d(f(x), x) >= 0",
     "monotonic_increasing[x]", "holds"),
    (paid, "for payment in [-10, 10], d(f(payment), payment) >= 0",
     "monotonic_increasing[payment]", "holds"),
    (remaining, "for payment in [-10, 10], d(f(payment), payment) >= 0",
     "monotonic_increasing[payment]", "falsified"),
    (remaining, "for payment in [-10, 10], d(f(payment), payment) <= 0",
     "monotonic_decreasing[payment]", "holds"),
    (square_loop, "for x in [-10, 10], d(f(x), x, x) >= 0", "convex[x]", "holds"),
    (square_loop, "for x in [-10, 10], d(f(x), x, x) <= 0", "concave[x]", "falsified"),
    (square_loop, "for x in [-10, 10], d(f(x), x, x) == 0", "affine[x]", "falsified"),
])
def test_the_user_claim_and_the_family_row_agree(fn, text, family, verdict):
    user, row = _user_and_family(fn, text, family)
    assert row.verdict == verdict
    assert row.route == "probe:algorithmic"
    assert (user.verdict, user.route, user.n, user.counterexample) == \
        (row.verdict, row.route, row.n, row.counterexample)
    if verdict == "falsified":
        assert user.counterexample
    assert f"as {family} does" in user.note


def test_the_note_says_how_each_operator_was_checked():
    (first,) = check_conjectures(paid, [claim(
        "for payment in [-10, 10], d(f(payment), payment) >= 0", name="mine")])
    assert "comparing f at ordered pairs of payment" in first.note
    (second,) = check_conjectures(square_loop, [claim(
        "for x in [-10, 10], d(f(x), x, x) >= 0", name="mine")])
    assert "estimated by finite differences" in second.note


def test_a_derivative_of_a_non_numeric_result_stays_undecided():
    user, row = _user_and_family(label, "for x in [-10, 10], d(f(x), x) >= 0",
                                 "monotonic_increasing[x]")
    assert user.verdict not in ("holds", "proven", "falsified")
    assert user.verdict == row.verdict


def test_a_body_derive_reads_is_still_decided_by_derive():
    (user,) = check_conjectures(cube, [claim(
        "for x in [-10, 10], d(f(x), x) >= 0", name="mine")])
    assert (user.verdict, user.route) == ("proven", "derive")
    assert "as monotonic_increasing[x] does" not in (user.note or "")
    assert (user.meta or {}).get("mathema.float_companion") != \
        "none (a built-in claim decides this claim)"


def test_a_bound_d_is_the_callers_function_not_the_derivative():
    def slope(g, x):
        return -1.0
    (user,) = check_conjectures(paid, [claim(
        "for payment in [-10, 10], d(f(payment), payment) >= 0", name="mine",
        funcs={"d": slope})])
    assert user.route != "probe:algorithmic"


@pytest.mark.parametrize("name", ["mine", "monotonic_increasing[payment]"])
def test_a_probe_route_claim_reaches_the_family_probe(name):
    (p,) = check_conjectures(paid, [claim(
        "for payment in [-10, 10], d(f(payment), payment) >= 0", name=name,
        route="probe")])
    assert (p.verdict, p.route) == ("holds", "probe:algorithmic")


def test_a_recorded_row_adjudicates_again_the_same_way():
    from mathema.spec import entry_claims
    (first,) = check_conjectures(remaining, [claim(
        "for payment in [-10, 10], d(f(payment), payment) >= 0", name="mine")])
    row = {"name": first.name, "statement": first.statement,
           "route": first.route.split(":", 1)[0], "domain": first.domain}
    (again,) = check_conjectures(remaining, entry_claims({"claims": [row]}))
    assert (again.verdict, again.route) == (first.verdict, first.route)
    assert "(not increasing)" in again.counterexample


@pytest.mark.parametrize("text", [
    "for x in [-10, 10], d(f(x), x) >= 1",
    "for x in [-10, 10], d(f(x), x) > 0",
    "for x in [-10, 10], 0 <= d(f(x), x)",
])
def test_another_derivative_spelling_says_why_it_stays_undecided(text):
    (p,) = check_conjectures(square_loop, [claim(text, name="mine")])
    assert p.verdict == "unknown"
    assert "unrecognized call" not in p.note
    assert ("the probe decides a derivative claim only as the shape claims "
            "state it (a first derivative compared with 0 by <= or >=, a "
            "second derivative compared with 0 by ==, <= or >=)") in p.note
    assert "is not one of them" in p.note
    assert "derive could not read" in p.note
