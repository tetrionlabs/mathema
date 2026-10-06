# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_deterministic, the function-wide predicate and the named claim
alike, is read from the source: an input the arguments do not carry
(the environment, the clock, a file, a draw from a shared generator, a
module-level value the call itself changes) falsifies it with the read
as the witness, wherever it is imported; a body whose result depends on
its arguments alone is proven, whatever it returns (NaN, a raise, an
object, a generator). Nothing runs."""
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


def price_in_fx_local(price: float) -> float:
    import os as _os
    return price * float(_os.environ.get("FX_RATE_T", "1"))


def price_in_fx_from_import(price: float) -> float:
    from os import environ
    return price * float(environ.get("FX_RATE_T", "1"))


def stamped_local(x: float) -> float:
    from time import time as now
    return x + 0.0 * now()


class Order:
    """An order with no equality of its own."""

    def __init__(self, amount):
        self.amount = amount


def make_order(x: float) -> Order:
    return Order(x)


def countdown(x: float):
    return (i for i in range(int(abs(x) % 5)))


_calls_made = [0]


def metered_cost(units: float) -> float:
    """A price that rises after the hundredth call."""
    _calls_made[0] += 1
    return units * (1.0 if _calls_made[0] <= 100 else 1.5)


def minus_five(x: float) -> float:
    return x - 5


def _wide(fn):
    (p,) = check_conjectures(fn, [claim("is_deterministic(f)")])
    return p


def _named(fn):
    (p,) = check_conjectures(fn, [mathema.claim("f(x) == f(x)",
                                                name="is_deterministic")])
    return p


def test_a_draw_from_the_shared_generator_falsifies_both_forms():
    for probe in (_wide, _named):
        p = probe(noisy)
        assert (p.verdict, p.route) == ("falsified", "examine"), (
            p.verdict, p.note)
        assert "draws from the shared random generator" in p.counterexample


def test_a_hidden_read_falsifies_with_the_read_named():
    for fn, read in ((read_env, "reads os.environ"),
                     (stamped, "time.time"),
                     (price_in_fx_local, "reads os.environ"),
                     (price_in_fx_from_import, "reads os.environ"),
                     (stamped_local, "time.time")):
        p = _wide(fn)
        assert (p.verdict, p.route) == ("falsified", "examine"), (
            fn.__name__, p.verdict, p.note)
        assert read in p.counterexample, p.counterexample


def test_module_state_the_call_reads_and_writes_falsifies():
    p = _wide(metered_cost)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "the module-level _calls_made, which the call also changes" in \
        p.counterexample


def test_what_the_function_returns_does_not_matter():
    for fn in (pure, nan_above_zero, raises_above_zero, make_order,
               countdown):
        for probe in (_wide, _named):
            p = probe(fn)
            assert (p.verdict, p.route) == ("proven", "examine"), (
                fn.__name__, p.verdict, p.note)


def test_a_claim_named_is_deterministic_that_states_something_else():
    # an ordinary claim: the derive route's disproof stands, reproduced
    # by executing f at its witness
    (p,) = check_conjectures(minus_five, [mathema.claim(
        "f(x) >= 0", name="is_deterministic")])
    assert (p.verdict, p.route) == ("falsified", "probe:semi_analytical"), \
        (p.verdict, p.note)
    assert p.meta.get("mathema.corroboration") == "reproduced"


def zero_price(x: float) -> float:
    return -0.0


def test_a_value_claim_reads_minus_zero_as_zero():
    (p,) = check_conjectures(zero_price, [claim("f(x) == 0")])
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    (p,) = check_conjectures(zero_price, [claim("f(x) == 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)
