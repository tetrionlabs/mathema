# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive reads `raise E(...)` as raising E only when building the
exception cannot raise something else first, and only when the name E
is the class the claim names. An argument that reads an undefined name,
divides, indexes, takes an attribute or calls a function is evaluated
before the raise and may raise its own exception; a `from` clause is
evaluated too; a bare `raise` re-raises something else. In each such
case derive does not decide a `raises(f(x), E)` claim, and the probe
decides it by running the function. A literal message, an f-string
over parameters and a parameter passed as the argument are read as
before."""
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim


def undefined_name(x: float) -> float:
    if x < 0:
        raise ValueError(no_such_name)  # noqa: F821
    return x


def division(x: float) -> float:
    if x < 0:
        raise ValueError(1 / (x + 1))
    return x


def index(x: float) -> float:
    if x < 0:
        raise ValueError("abc"[int(x) - 10])
    return x


def attribute_of_none(x: float) -> float:
    if x < 0:
        raise ValueError(None.message)
    return x


def _fails(x):
    raise KeyError(x)


def call_that_raises(x: float) -> float:
    if x < 0:
        raise ValueError(_fails(x))
    return x


class Refusing(ValueError):
    def __init__(self, *args):
        raise KeyError("no")


def constructor_raises(x: float) -> float:
    if x < 0:
        raise Refusing("negative")
    return x


def cause_is_evaluated(x: float) -> float:
    if x < 0:
        raise ValueError("negative") from _fails(x)
    return x


def bare_reraise(x: float) -> float:
    if x < 0:
        raise
    return x


def local_class_of_that_name(x: float) -> float:
    class ValueError(Exception):  # noqa: A001
        pass
    if x < 0:
        raise ValueError("negative")
    return x


def format_specification(x: float) -> float:
    if x < 0:
        raise ValueError(f"{x:d}")
    return x


_CLAIM = "for x in [-5, -1], raises(f(x), ValueError)"

NOT_READ = [undefined_name, division, index, attribute_of_none, call_that_raises,
            cause_is_evaluated, bare_reraise, local_class_of_that_name, format_specification]


@pytest.mark.parametrize("fn", NOT_READ, ids=[f.__name__ for f in NOT_READ])
def test_a_raise_that_may_raise_something_else_is_not_proven(fn):
    (derive,) = check_conjectures(fn, [claim(_CLAIM, route="derive")])
    assert derive.verdict != "proven", (derive.verdict, derive.sketch)
    (best,) = check_conjectures(fn, [claim(_CLAIM)])
    assert best.verdict != "proven", (best.verdict, best.route, best.sketch)


@pytest.mark.parametrize("fn,real", [
    (undefined_name, NameError), (attribute_of_none, AttributeError),
    (call_that_raises, KeyError), (cause_is_evaluated, KeyError), (index, IndexError),
])
def test_the_function_really_raises_something_else_and_the_claim_is_falsified(fn, real):
    with pytest.raises(real):
        fn(-2.0)
    (row,) = check_conjectures(fn, [claim(_CLAIM)])
    assert row.verdict == "falsified", (row.verdict, row.note)


def test_the_sketch_names_the_expression_that_was_not_read():
    (row,) = check_conjectures(format_specification, [claim(_CLAIM, route="derive")])
    assert "the exception's argument `f'{x:d}'` is evaluated before the raise" in (
        (row.sketch or "") + (row.note or ""))


class Plain(ValueError):
    """A subclass with no constructor of its own."""


def raises_a_plain_subclass(x: float) -> float:
    if x < 0:
        raise Plain("negative")
    return x


def test_a_subclass_with_no_constructor_of_its_own_is_read_as_before():
    (row,) = check_conjectures(raises_a_plain_subclass,
                               [claim("for x in [-5, -1], raises(f(x), Plain)", route="derive")])
    assert row.verdict == "proven", (row.verdict, row.sketch)


def test_a_class_whose_constructor_raises_is_not_the_class_the_claim_names():
    (row,) = check_conjectures(constructor_raises,
                               [claim("for x in [-5, -1], raises(f(x), Refusing)")])
    assert row.verdict != "proven", (row.verdict, row.sketch)


def test_a_module_that_rebinds_the_exception_name_is_not_proven(tmp_path, monkeypatch):
    import importlib
    import sys
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "rebinds_the_name.py").write_text(
        "class _Other(Exception):\n    pass\n\n\nValueError = _Other\n\n\n"
        "def f(x: float) -> float:\n    if x < 0:\n        raise ValueError('negative')\n"
        "    return x\n")
    sys.modules.pop("rebinds_the_name", None)
    try:
        module = importlib.import_module("rebinds_the_name")
        (row,) = check_conjectures(module.f, [claim(_CLAIM, route="derive")])
        assert row.verdict != "proven", (row.verdict, row.sketch)
    finally:
        sys.modules.pop("rebinds_the_name", None)


# ---- the common shapes are read as before --------------------------------

def literal_message(x: float) -> float:
    if x < 0:
        raise ValueError("negative")
    return x


def f_string_of_the_parameter(x: float) -> float:
    if x < 0:
        raise ValueError(f"bad {x!r}")
    return x


def f_string_default_format(x: float) -> float:
    if x < 0:
        raise ValueError(f"bad {x}")
    return x


def parameter_as_the_argument(x: float) -> float:
    if x < 0:
        raise KeyError(x)
    return x


def repr_of_the_parameter(x: float) -> float:
    if x < 0:
        raise ValueError(repr(x))
    return x


def no_argument(x: float) -> float:
    if x < 0:
        raise ValueError
    return x


def a_local_bound_before(x: float) -> float:
    y = x * 2
    if x < 0:
        raise ValueError(y)
    return x


def from_none(x: float) -> float:
    if x < 0:
        raise ValueError("negative") from None
    return x


@pytest.mark.parametrize("fn,exception", [
    (literal_message, "ValueError"), (f_string_of_the_parameter, "ValueError"),
    (f_string_default_format, "ValueError"), (parameter_as_the_argument, "KeyError"),
    (repr_of_the_parameter, "ValueError"), (no_argument, "ValueError"),
    (a_local_bound_before, "ValueError"), (from_none, "ValueError"),
])
def test_a_raise_that_cannot_fail_is_proven_as_before(fn, exception):
    (row,) = check_conjectures(fn, [claim(f"for x in [-5, -1], raises(f(x), {exception})",
                                          route="derive")])
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    assert row.route == "derive"


def test_a_claim_that_names_no_exception_is_proven_whatever_the_argument_does():
    (row,) = check_conjectures(division, [claim("for x in [-5, -1], raises(f(x))",
                                                route="derive")])
    assert row.verdict == "proven", (row.verdict, row.sketch)


# ---- a guard read for a missing-value policy -----------------------------

def guard_divides(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError(1 / y)
    return x * y


def guard_with_a_literal(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError("x is required")
    return x * y


def _policy_row(fn):
    rows = check_conjectures(fn, [claim("for x in [0, 1], y in [-1, 1], f(x, y) == x * y"),
                                  claim("absent(f, x) raises(TypeError)")])
    return rows[-1]


def test_a_policy_is_not_proven_from_a_guard_whose_raise_may_raise_something_else():
    with pytest.raises(ZeroDivisionError):
        guard_divides(None, 0.0)
    row = _policy_row(guard_divides)
    assert row.verdict != "proven", (row.verdict, row.note)


def test_a_policy_from_a_guard_with_a_literal_message_is_proven_as_before():
    row = _policy_row(guard_with_a_literal)
    assert row.verdict == "proven", (row.verdict, row.note)


# ---- a raise that sits in a function the body calls ------------------------

_HELPER_MODULE = """
class _Other(Exception):
    pass


ValueError = _Other


def check(x: float) -> float:
    if x < 0:
        raise ValueError("negative")
    return x
"""

_CALLER_MODULE = """
import raise_helper
from raise_helper import check


def through_module(x: float) -> float:
    return raise_helper.check(x) + 1


def through_name(x: float) -> float:
    return check(x) + 1


def own_raise_then_module(x: float) -> float:
    if x > 100:
        raise ValueError("big")
    return raise_helper.check(x) + 1


def own_raise_then_name(x: float) -> float:
    if x > 100:
        raise ValueError("big")
    return check(x) + 1
"""


@pytest.mark.parametrize("name", ["through_module", "through_name", "own_raise_then_module",
                                  "own_raise_then_name"])
def test_a_raise_in_a_called_function_is_not_read_under_the_callers_names(
        tmp_path, monkeypatch, name):
    import importlib
    import sys
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "raise_helper.py").write_text(_HELPER_MODULE)
    (tmp_path / "raise_caller.py").write_text(_CALLER_MODULE)
    for module in ("raise_helper", "raise_caller"):
        sys.modules.pop(module, None)
    try:
        fn = getattr(importlib.import_module("raise_caller"), name)
        with pytest.raises(Exception) as raised:
            fn(-2.0)
        assert not isinstance(raised.value, ValueError)
        for route in ("derive", "best"):
            (row,) = check_conjectures(fn, [claim(_CLAIM, route=route)])
            assert row.verdict != "proven", (route, row.verdict, row.sketch)
    finally:
        for module in ("raise_helper", "raise_caller"):
            sys.modules.pop(module, None)
