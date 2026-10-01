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

import pytest

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
        assert "two calls returned" in str(p.counterexample), p.counterexample


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


def test_the_witness_names_the_inputs_once_and_both_outcomes():
    import re
    p = _wide(noisy)
    assert re.fullmatch(r"at x = \S+, two calls returned \S+ and \S+",
                        p.counterexample), p.counterexample


def test_the_hidden_read_caveat_reads_as_one_sentence():
    p = _wide(read_env)
    assert ("the body reads os.environ, which does not change between two "
            "back-to-back calls, so this holds only while it stays as it is"
            ) in p.note, p.note


def minus_five(x: float) -> float:
    return x - 5


def test_the_derive_override_is_for_the_self_equality_statement_only():
    # a claim named is_deterministic that states something else keeps
    # the derive route's disproof
    (p,) = check_conjectures(minus_five, [mathema.claim(
        "f(x) >= 0", name="is_deterministic")])
    assert (p.verdict, p.route) == ("falsified", "derive"), (p.verdict, p.note)


def price_in_fx_local(price: float) -> float:
    import os as _os
    return price * float(_os.environ.get("FX_RATE_T", "1"))


def price_in_fx_from_import(price: float) -> float:
    from os import environ
    return price * float(environ.get("FX_RATE_T", "1"))


def stamped_local(x: float) -> float:
    from time import time as now
    return x + 0.0 * now()


def test_a_read_imported_inside_the_body_is_named():
    for fn, read in ((price_in_fx_local, "os.environ"),
                     (price_in_fx_from_import, "os.environ"),
                     (stamped_local, "time.time")):
        p = _wide(fn)
        assert p.verdict == "holds", (fn.__name__, p.verdict, p.note)
        assert f"the body reads {read}" in (p.note or ""), (fn.__name__, p.note)


_calls_made = [0]


def metered_cost(units: float) -> float:
    """A price that rises after the hundredth call."""
    _calls_made[0] += 1
    return units * (1.0 if _calls_made[0] <= 100 else 1.5)


def test_mutable_module_state_it_reads_and_writes_is_named():
    p = _wide(metered_cost)
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    assert "the module-level _calls_made" in (p.note or ""), p.note


import logging  # noqa: E402

_log = logging.getLogger(__name__)


def logged_double(x: float) -> float:
    _log.debug("doubling %s", x)
    return 2 * x


def test_a_module_logger_is_not_named_as_kept_state():
    p = _wide(logged_double)
    assert "module-level" not in (p.note or ""), p.note


# --- comparing by kind across numeric types --------------------------------------

from decimal import Decimal  # noqa: E402

import numpy as np  # noqa: E402

from mathema.claim_families import _same_kind  # noqa: E402


class Touchy:
    """A value whose equality raises."""

    def __eq__(self, other):
        raise TypeError("no comparison")

    __hash__ = object.__hash__


@pytest.mark.parametrize("a, b", [
    (np.float32("nan"), np.float32("nan")),
    (complex(math.nan, 1.0), complex(math.nan, 1.0)),
    (Decimal("NaN"), Decimal("NaN")),
    (np.array([math.nan, 1.0], dtype=object),
     np.array([math.nan, 1.0], dtype=object)),
    (np.float64(2.5), np.float64(2.5)),
])
def test_equal_values_of_every_numeric_kind_agree(a, b):
    assert _same_kind(a, b) is True


@pytest.mark.parametrize("a, b", [
    (np.float32(-0.0), np.float32(0.0)),
    (complex(1.0, -0.0), complex(1.0, 0.0)),
    (Decimal("-0"), Decimal("0")),
    (np.array([complex(1, 0.0)]), np.array([complex(1, -0.0)])),
])
def test_the_sign_of_zero_counts_in_every_numeric_kind(a, b):
    assert _same_kind(a, b) is False


def test_a_comparison_that_raises_is_inconclusive():
    assert _same_kind(Touchy(), Touchy()) is None


def test_pandas_objects_compare_by_values_index_and_dtype():
    pd = pytest.importorskip("pandas")
    a = pd.Series([1.0, 2.0]).pct_change()
    assert _same_kind(a, pd.Series([1.0, 2.0]).pct_change()) is True
    assert _same_kind(a, pd.Series([math.nan, 2.0])) is False
    frame = pd.DataFrame({"x": [1.0, math.nan]})
    assert _same_kind(frame, frame.copy()) is True


def price_changes(x: float):
    pd = pytest.importorskip("pandas")
    return pd.Series([x, 2 * x]).pct_change()


def test_a_deterministic_series_result_holds():
    pytest.importorskip("pandas")
    p = _wide(price_changes)
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_an_uncomparable_result_says_why_and_what_to_do():
    p = _wide(make_order)
    assert ("two calls return Order objects, and Order defines no equality, "
            "so mathema cannot tell whether they agree. Give Order an "
            "__eq__, or claim what its fields are") in (p.note or ""), p.note
    p = _wide(countdown)
    assert ("two calls return generators, and comparing them would use them "
            "up") in (p.note or ""), p.note
