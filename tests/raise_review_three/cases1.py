# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Review-three cases, batch 1: messages, bounds, lambdas, aliases."""
import math
from math import isinf as isnan  # noqa: F401  a misleading alias, used by pol_alias
from math import isnan as true_isnan

NEG = "for x in [-5, -1], "
D = {"x": (-5, -1)}
R = "raises(f(x), ValueError)"


def r(fn, exc="ValueError", text=None, dom=None):
    return (fn, (text or NEG + f"raises(f(x), {exc})"), ("f(x)", exc, dom or D))


# --- prefix that fails only at one interior point, read as unable to fail ---

def lam_default(x: float) -> float:
    if x < 0:
        g = lambda a=1 / (x + 3.25): a  # noqa: E731,F841
        raise ValueError("neg")
    return x


def lam_default_name(x: float) -> float:
    if x < 0:
        g = lambda a=undefined_name: a  # noqa: E731,F841,F821
        raise ValueError("neg")
    return x


# --- format specs and message text ---

def spec_f(x: float) -> float:
    if x < 0:
        raise ValueError(f"{x:.3f}")
    return x


def spec_nested(x: float) -> float:
    if x < 0:
        n = 3
        raise ValueError(f"{x:.{n}f}")
    return x


def spec_pct(x: float) -> float:
    if x < 0:
        raise ValueError(f"{x:.99%}")
    return x


def spec_e_int(x: int) -> int:
    if x < 0:
        raise ValueError(f"{x * x * x * x * x * x:.2e}")
    return x


def pct_s(x: float) -> float:
    if x < 0:
        raise ValueError("%s and %r" % (x, x))
    return x


def pct_one(x: float) -> float:
    if x < 0:
        raise ValueError("%s" % x)
    return x


def pct_tuple_local(x: float) -> float:
    if x < 0:
        t = (x, x)
        raise ValueError("%s" % t)
    return x


def brace_attr(x: float) -> float:
    if x < 0:
        raise ValueError("{0.real}".format(x))
    return x


def brace_ok(x: float) -> float:
    if x < 0:
        raise ValueError("{} {}".format(x, "a"))
    return x


def brace_super_digit(x: float) -> float:
    if x < 0:
        raise ValueError("{²}".format(x))  # noqa: F523,F524
    return x


def typename(x: float) -> float:
    if x < 0:
        raise ValueError(type(x).__name__)
    return x


def none_or_nan(x: float) -> float:
    if x < 0:
        raise ValueError(f"{x is None or math.isnan(x)}")
    return x


def str_isnan(x: str) -> str:
    if x == "a":
        raise ValueError(f"{x is None or math.isnan(x)}")
    return x


def str_spec(x: str) -> str:
    if x == "a":
        raise ValueError(f"{x:.3f}")
    return x


# --- bounds ---

def mod_neg(x: float) -> float:
    if x < 0:
        y = x % -1.5
        z = 1 / (y - 7)  # |y| <= 1.5 so y - 7 is never 0
        raise ValueError(z)
    return x


def floordiv_inf(x: float) -> float:
    if x < 0:
        y = (x * 1e308 * 10) // 3
        raise ValueError(y)
    return x


def mod_inf(x: float) -> float:
    if x < 0:
        y = (x * 1e308 * 10) % 3
        raise ValueError(y)
    return x


def big_mid(x: int) -> int:
    if x < 0:
        y = x * 10 ** 300
        w = y * y
        v = w // 10 ** 600
        u = v + 0.5  # noqa: F841
        raise ValueError("neg")
    return x


def floordiv_small(x: float) -> float:
    if x < 0:
        y = x // 0.5
        raise ValueError(y)
    return x


def mod_zero(x: float) -> float:
    if x < 0:
        y = x % 0
        raise ValueError(y)
    return x


def div_least(x: float) -> float:
    if x < 0:
        y = 1 / (x - 0.0)
        raise ValueError(y)
    return x


def div_sum(x: float) -> float:
    if x < 0:
        y = 1 / (x + 3)
        raise ValueError(y)
    return x


def neg_then_div(x: float) -> float:
    if x < 0:
        y = 1 / -x
        raise ValueError(y)
    return x


def abs_then_div(x: float) -> float:
    if x < 0:
        y = 1 / abs(x + 3)
        raise ValueError(y)
    return x


def isnan_int(x: int) -> int:
    if x < 0:
        y = x * 10 ** 300
        raise ValueError(math.isnan(y * y))
    return x


def mod_floordiv_chain(x: int) -> int:
    if x < 0:
        y = x // 1 + 0.5
        raise ValueError(y)
    return x


# --- names ---

ValueErrorAlias = KeyError


def alias_name(x: float) -> float:
    if x < 0:
        raise ValueErrorAlias("neg")
    return x


def true_isnan_guard(x: float) -> float:
    if x < 0:
        raise ValueError(true_isnan(x))
    return x


def ok_case(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


def float_semantics(x: float) -> float:
    if x * 3 / 3 == x:
        raise ValueError("neg")
    return x


def float_semantics_rare(x: float) -> float:
    if x + 0.1 - 0.1 == x or x == -2.7:
        raise ValueError("neg")
    return x


CASES = [
    r(ok_case),
    r(lam_default),
    r(lam_default_name),
    r(spec_f), r(spec_nested), r(spec_pct),
    (spec_e_int, "for x in [-5, -1], raises(f(x), ValueError)", ("f(x)", "ValueError", D)),
    r(pct_s), r(pct_one), r(pct_tuple_local), r(brace_attr), r(brace_ok),
    r(brace_super_digit), r(typename), r(none_or_nan),
    (str_isnan, "for x in {'a'}, raises(f(x), ValueError)", ("f(x)", "ValueError", {"x": frozenset({"a"})})),
    (str_spec, "for x in {'a'}, raises(f(x), ValueError)", ("f(x)", "ValueError", {"x": frozenset({"a"})})),
    r(mod_neg), r(floordiv_inf), r(mod_inf), r(big_mid), r(floordiv_small), r(mod_zero),
    r(div_least), r(div_sum), r(neg_then_div), r(abs_then_div), r(isnan_int), r(mod_floordiv_chain),
    r(alias_name, "ValueError"), r(alias_name, "KeyError"), r(alias_name, "ValueErrorAlias"),
    r(true_isnan_guard),
    (float_semantics, "for x in [0, 1], raises(f(x), ValueError)", ("f(x)", "ValueError", {"x": (0, 1)})),
    (float_semantics_rare, "for x in [-5, -1], raises(f(x), ValueError)", ("f(x)", "ValueError", D)),
]
