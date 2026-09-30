# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_deterministic, the function-wide predicate and the named claim
alike, has a sampling half: two calls at the same inputs, compared by
kind. A NaN agrees with a NaN and the same exception type agrees with
itself, so a function that returns NaN, or raises, the same way every
time is deterministic. A body that reads the clock, the environment or
a file is never proven deterministic by structure, and a holds over it
says in its note what was read, since two back-to-back calls cannot see
that input change."""
import math
import os
import random
import time

import mathema
from mathema.conjecture import check_conjectures, claim


def pure(x: float) -> float:
    return 2 * x


def nan_above_zero(x: float) -> float:
    return math.nan if x > 0 else x


def raises_above_zero(x: float) -> float:
    if x > 0:
        raise ValueError("positive")
    return float(abs(x))


def noisy(x: float) -> float:
    return x + random.random()


def read_env(x: float) -> float:
    return x * float(os.environ.get("MATHEMA_SCALE", "1"))


def stamped(x: float) -> float:
    return x + 0.0 * time.time()


def _wide(fn):
    (p,) = check_conjectures(fn, [claim("is_deterministic(f)")])
    return p


def _named(fn):
    (p,) = check_conjectures(fn, [mathema.claim("f(x) == f(x)",
                                                name="is_deterministic")])
    return p


def test_a_body_that_does_not_lift_is_sampled_not_left_unknown():
    for probe in (_wide, _named):
        p = probe(noisy)
        assert p.verdict == "falsified", (p.verdict, p.note)
        assert "second" in str(p.counterexample), p.counterexample


def test_nan_agrees_with_nan():
    for probe in (_wide, _named):
        p = probe(nan_above_zero)
        assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_the_same_exception_agrees_with_itself():
    for probe in (_wide, _named):
        p = probe(raises_above_zero)
        assert (p.verdict, p.route) == ("holds", "probe:algorithmic"), (
            p.verdict, p.counterexample, p.note)


def test_a_hidden_read_holds_with_the_read_named():
    for fn, read in ((read_env, "os.environ"), (stamped, "time.time")):
        for probe in (_wide, _named):
            p = probe(fn)
            assert p.verdict == "holds", (fn.__name__, p.verdict, p.note)
            assert read in (p.note or ""), p.note
            assert "back-to-back" in (p.note or ""), p.note


def test_a_pure_body_is_still_proven():
    assert _wide(pure).verdict == "proven"
    assert _named(pure).verdict == "proven"


# --- comparing by kind: what agrees, what is inconclusive, what differs ----

class Order:
    """An order with no equality of its own: two equal orders are two
    objects that compare by identity."""

    def __init__(self, amount):
        self.amount = amount


def make_order(amount: float) -> Order:
    return Order(amount)


def countdown(n: float):
    return (i for i in range(int(abs(n) % 5)))


def quote_with_missing_fields(x: float) -> dict:
    return {"price": x, "spread": float("nan")}


_calls = [0]


def signed_zero(x: float) -> float:
    _calls[0] += 1
    return 0.0 if _calls[0] % 2 else -0.0


def zero_price(x: float) -> float:
    return -0.0


def test_an_object_without_equality_is_not_falsified():
    for probe in (_wide, _named):
        p = probe(make_order)
        assert p.verdict != "falsified", (p.verdict, p.counterexample)


def test_a_generator_result_is_not_falsified():
    for probe in (_wide, _named):
        p = probe(countdown)
        assert p.verdict != "falsified", (p.verdict, p.counterexample)


def test_a_dict_holding_nan_agrees_with_itself():
    for probe in (_wide, _named):
        p = probe(quote_with_missing_fields)
        assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_the_sign_of_zero_is_part_of_the_value():
    p = _wide(signed_zero)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "0.0" in p.counterexample and "-0.0" in p.counterexample


def test_a_value_claim_reads_minus_zero_as_zero():
    (p,) = check_conjectures(zero_price, [claim("f(x) == 0")])
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    (p,) = check_conjectures(zero_price, [claim("f(x) == 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)
