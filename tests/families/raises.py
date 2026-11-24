# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The raises family: `raises(f(...), E)` claims over call arguments,
wrappers, guards, causes and exception messages.

The generated grids are sampled with a fixed seed; every case that
shows something particular about the code is pinned by name."""
import random

F = "tests.families.functions.raises"
NEG = "for x in [-5, -1], "

# Argument expressions put in the second slot of `plain(x, y)`. The
# claim `raises(f(x, ARG), ValueError)` is true exactly when building the
# argument cannot fail.
ARGUMENT_FORMS = [
    "2", "None", "'a' * 3", "1 or 1/0", "0 and 1/0", "2 if 1 else 1/0", "x / 2", "x ** 2",
    "1 / abs(x)", "(1,) + (2,)", "sorted(['b', 'a'])", "[1, 2, 3][::-1]", "{1: 2}[1]",
    "'%s' % 1", "x / x", "1 == 'a'", "True ** 5", "[1] * True",
    "1/0", "[1, 2, 3][5]", "0 ** -1", "sum([1, 'a'])", "1 / -0.0", "'a' * 1.5",
    "len(1)", "{1: 2}[3]", "1 < 'a'", "x / (x - x)", "1 % 0.0",
    "divmod(1, 0)", "1/0 if 1 else 2", "(2 if x < 0 else 1/0)",
]
FAILING_FORMS = {
    "1/0", "[1, 2, 3][5]", "0 ** -1", "sum([1, 'a'])", "1 / -0.0", "'a' * 1.5", "len(1)",
    "{1: 2}[3]", "1 < 'a'", "x / (x - x)", "1 % 0.0", "divmod(1, 0)",
    "1/0 if 1 else 2",
}
RAISE_READING = "the raise reading"
PINNED_FORMS = {
    # a literal argument that raises while it is built, before f runs
    "1/0", "[1, 2, 3][5]", "0 ** -1", "sum([1, 'a'])", "1 % 0.0",
    # arguments that build without failing
    "1 or 1/0", "x / 2",
}

DOMAINS = {
    "[-5, -1]": True, "(-5, -1]": True, "{-1, -2}": True,
    "[-5, 0]": False, "[-5, -1] ∪ [1, 5]": False,
}
WRAPPED = {"wrapped": True, "wrapped_twice": True, "cached": True,
           "negated": False, "swallowed": False}

CASES: list = []

_rng = random.Random(1123)
_forms = sorted(set(_rng.sample(ARGUMENT_FORMS, 14)) | PINNED_FORMS)
for i, form in enumerate(_forms):
    false = form in FAILING_FORMS
    CASES.append(dict(
        name=f"argument.{i:02d}", function=f"{F}:plain",
        claim=NEG + f"raises(f(x, {form}), ValueError)", truth=not false,
        shows=("building the argument raises before f runs" if false
               else "the argument builds; f raises ValueError"),
        **(dict(issue=123, rule=RAISE_READING) if false else {})))

_grid = [(fn, dom) for fn in WRAPPED for dom in DOMAINS]
for fn, dom in sorted(set(_rng.sample(_grid, 10)) | {("negated", "[-5, -1]"), ("swallowed", "[-5, -1]"),
                                                       ("wrapped", "[-5, -1]")}):
    CASES.append(dict(
        name=f"wrapper.{fn}.{dom}", function=f"{F}:{fn}",
        claim=f"for x in {dom}, raises(f(x), ValueError)",
        truth=WRAPPED[fn] and DOMAINS[dom],
        **(dict(rule=RAISE_READING) if DOMAINS[dom] and not WRAPPED[fn] else {}),
        shows="a wrapper between the call and the body"))

CASES += [
    dict(name="wrapper.overflow_caught", function=f"{F}:overflow_caught",
         claim="for x in [0, 3], f(x) > 0", truth=False, issue=126, rule=RAISE_READING,
         shows="exp(x * 1000) overflows in floats above about 0.71; the wrapper turns "
               "the OverflowError into 0"),
    dict(name="cause.mock", function=f"{F}:cause_mock", claim=NEG + "raises(f(x), ValueError)",
         truth=False,
         shows="an object that only claims to be an exception, as a cause, makes "
               "`raise ... from` raise TypeError"),
    dict(name="cause.instance", function=f"{F}:cause_instance",
         claim=NEG + "raises(f(x), ValueError)", truth=True,
         shows="a real exception instance as a cause"),
    dict(name="cause.int", function=f"{F}:cause_int", claim=NEG + "raises(f(x), ValueError)",
         truth=False, shows="an int as a cause raises TypeError"),
    dict(name="message.chain_negated", function=f"{F}:chain_negated",
         claim=NEG + "raises(f(x), ValueError)", truth=False,
         shows="the message `0 < -x < 'a'` compares a number with a text and raises TypeError"),
    dict(name="message.chain_short_circuits", function=f"{F}:chain_short_circuits",
         claim=NEG + "raises(f(x), ValueError)", truth=True,
         shows="the message `x > 0 > 'a'` stops at its first false comparison"),
    dict(name="message.chain_with_zero", function=f"{F}:chain_with_zero",
         claim="for x in [-5, 0], raises(f(x), ValueError)", truth=False,
         shows="at x = 0 the message `0 <= x < 'a'` reaches the text and raises TypeError"),
    dict(name="guard.refuses_none", function=f"{F}:guard_refuses_none",
         claim=NEG + "y in {1, None}, raises(f(x, y), KeyError)", truth=False, issue=124,
         rule=RAISE_READING,
         shows="mathema's own guard refuses y = None before the body runs"),
    dict(name="guard.refuses_nan", function=f"{F}:guard_refuses_nan",
         claim=NEG + "y in {1, nan}, raises(f(x, y), KeyError)", truth=False, issue=124,
         rule=RAISE_READING,
         shows="mathema's own guard refuses y = nan before the body runs"),
    dict(name="guard.structure_infinite", function=f"{F}:structure_finite",
         claim="for x in {-inf, -1}, raises(f(x, 1), KeyError)", truth=False, issue=125,
         rule=RAISE_READING,
         shows="a Finite structure guard refuses the listed -inf with ValueError"),
    dict(name="guard.structure_finite", function=f"{F}:structure_finite",
         claim="for x in {-2, -1}, raises(f(x, 1), KeyError)", truth=True,
         shows="the structure guard accepts every listed finite value"),
    dict(name="unnamed.read_in_branch", function=f"{F}:reads_second_in_branch",
         claim=NEG + "y in {1, None}, raises(f(x, y), ValueError)", truth=False, rule=RAISE_READING,
         shows="the second parameter is read in a branch; None there raises TypeError"),
    dict(name="unnamed.ignored", function=f"{F}:ignores_second",
         claim=NEG + "y in {1, None}, raises(f(x, y), ValueError)", truth=True,
         shows="the second parameter is never read"),
    dict(name="unnamed.ignored_nan", function=f"{F}:ignores_second",
         claim=NEG + "y in {1, nan}, raises(f(x, y), ValueError)", truth=True,
         shows="the second parameter is never read"),
    dict(name="unnamed.swapped_call", function=f"{F}:reads_second_in_branch",
         claim=NEG + "y in {1, None}, raises(f(y, x), ValueError)", truth=False, rule=RAISE_READING,
         shows="the call passes the missing value in the first slot"),
]
