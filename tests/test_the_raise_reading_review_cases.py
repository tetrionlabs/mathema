# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The functions two reviews of the raise reading used to probe it, each
with the claim it was probed with and the verdict mathema gives: a
`proven` only where the claim is true and was read, and for every case
where the function's real behaviour contradicts the claim, a verdict
that is not `proven`. A function that exits the process or never
finishes is checked through the derive prover directly and never run."""
import builtins
import functools
import math
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim

_BIG = 10 ** 300
_NEAR = (179769313486231580793728971405303415079934132710037826936173778980444968292764750946649017977587207096330286416692887910946555547851940402630657488671505820681908902000708383676273854845817711531764475730270069855571366959622842914819860834936475292719074168444365510704342711559699508093042880177904174497791
         + 4989600773836799529132479070093925771226990714529979588052066548876451785318362793117968131290681654971765441016278723103616304651091870092985811934760035582204005558722307158063310116666923386609933687578536986926478638411270796957755769718436085405946387916809117520482063620781496216846336)


class Refusing(TypeError):
    def __init__(self, *args):
        raise KeyError("no")


def mod_big(x: int) -> int:
    if x < 0:
        y = x % 1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
        z = y * y
        w = z + 0.5  # noqa: F841
        raise ValueError("neg")
    return x


def mod_big_text(x: int) -> int:
    if x < 0:
        y = x % 1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
        z = y * y * y * y * y * y * y * y * y * y * y * y * y * y * y
        raise TypeError(str(z))
    return x


def near_max(x: int) -> int:
    if x < 0:
        y = 179769313486231580793728971405303415079934132710037826936173778980444968292764750946649017977587207096330286416692887910946555547851940402630657488671505820681908902000708383676273854845817711531764475730270069855571366959622842914819860834936475292719074168444365510704342711559699508093042880177904174497791 + 4989600773836799529132479070093925771226990714529979588052066548876451785318362793117968131290681654971765441016278723103616304651091870092985811934760035582204005558722307158063310116666923386609933687578536986926478638411270796957755769718436085405946387916809117520482063620781496216846336
        w = y + 0.5  # noqa: F841
        raise ValueError("neg")
    return x


def gen_raise(x: float):
    if x < 0:
        raise ValueError("neg")
    yield x


async def async_raise(x: float):
    if x < 0:
        raise ValueError("neg")
    return x


def gen_value(x: float) -> float:
    if x < 0:
        return x + 1
    yield x


async def async_value(x: float) -> float:
    return x + 1


def swallow(fn):
    @functools.wraps(fn)
    def swallowing(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError:
            return 0.0
    return swallowing


@swallow
def decorated(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


def neg_raise(x: float) -> float:
    if x < 0:
        raise ValueError(f"{x}")
    return x


def keyword_arg(x: float) -> float:
    if x < 0:
        raise ValueError(msg="negative")
    return x


def unicode_err(x: float) -> float:
    if x < 0:
        raise UnicodeDecodeError("bad")
    return x


def group_err(x: float) -> float:
    if x < 0:
        raise ExceptionGroup("bad")  # noqa: F821
    return x


def prefix_divides(x: float) -> float:
    if x < 0:
        y = 1 / (x + 1)  # noqa: F841
        raise TypeError("negative")
    return x


def prefix_sqrt(x: float) -> float:
    if x < 0:
        y = math.sqrt(x)  # noqa: F841
        raise TypeError("negative")
    return x


def subclass(x: float) -> float:
    if x < 0:
        raise ZeroDivisionError("z")
    return x


def alias(x: float) -> float:
    if x < 0:
        raise IOError("z")
    return x


def big_int(x: int) -> int:
    if x > 0:
        raise TypeError(f"{x}")
    return x


def stopiter(x: float) -> float:
    if x < 0:
        raise StopIteration("s")
    return x


def oserror_one(x: float) -> float:
    if x < 0:
        raise OSError(2)
    return x


def from_cause(x: float) -> float:
    if x < 0:
        raise ValueError("a") from KeyError("b")
    return x


def nan_div(x: float) -> float:
    if x < 0:
        y = 1 / x
        raise ValueError(f"{y}")
    return x


def mod_float(x: float) -> float:
    if x < 0:
        y = x % 1.5
        raise ValueError(y)
    return x


def compare_mixed(x: float) -> float:
    if x < 0:
        raise ValueError(x < "a")
    return x


def isnan_test(x: float) -> float:
    if x < 0:
        if math.isnan(x):
            return 0.0
        raise ValueError("neg")
    return x


_NEG = "for x in [-5, -1], "

#: (function, claim, verdict)
CASES = [
    (mod_big, _NEG + "raises(f(x), ValueError)", "falsified"),
    (mod_big_text, _NEG + "raises(f(x), TypeError)", "falsified"),
    (near_max, _NEG + "raises(f(x), ValueError)", "falsified"),
    (gen_raise, _NEG + "raises(f(x), ValueError)", "falsified"),
    (async_raise, _NEG + "raises(f(x), ValueError)", "falsified"),
    (gen_value, _NEG + "f(x) == x + 1", "falsified"),
    (async_value, _NEG + "f(x) == x + 1", "falsified"),
    (decorated, _NEG + "raises(f(x), ValueError)", "falsified"),
    (neg_raise, "for x in {-1, -2, nan}, raises(f(x), ValueError)", "falsified"),
    (neg_raise, "for x in {-1, -2, None}, raises(f(x), ValueError)", "falsified"),
    (neg_raise, _NEG + "raises(f(x), ValueError)", "proven"),
    (keyword_arg, _NEG + "raises(f(x), ValueError)", "falsified"),
    (unicode_err, _NEG + "raises(f(x), UnicodeDecodeError)", "falsified"),
    (group_err, _NEG + "raises(f(x), ExceptionGroup)", "falsified"),
    (prefix_divides, _NEG + "raises(f(x), TypeError)", "falsified"),
    (prefix_sqrt, _NEG + "raises(f(x), TypeError)", "falsified"),
    (subclass, _NEG + "raises(f(x), ArithmeticError)", "proven"),
    (alias, _NEG + "raises(f(x), OSError)", "proven"),
    (big_int, "for x in [1, oo), raises(f(x), TypeError)", "holds"),
    (stopiter, _NEG + "raises(f(x), StopIteration)", "proven"),
    (oserror_one, _NEG + "raises(f(x), OSError)", "proven"),
    (from_cause, _NEG + "raises(f(x), ValueError)", "holds"),
    (nan_div, _NEG + "raises(f(x), ValueError)", "proven"),
    (mod_float, _NEG + "raises(f(x), ValueError)", "proven"),
    (compare_mixed, _NEG + "raises(f(x), ValueError)", "falsified"),
    (isnan_test, _NEG + "raises(f(x), ValueError)", "holds"),
]


@pytest.mark.skipif(not hasattr(builtins, "ExceptionGroup"), reason="Python 3.11 or later")
@pytest.mark.parametrize("fn,text,verdict", CASES,
                         ids=[f"{fn.__name__}:{text[len(_NEG):] if text.startswith(_NEG) else text}"
                              for fn, text, _ in CASES])
def test_a_review_case_gets_its_verdict(fn, text, verdict):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        (row,) = check_conjectures(fn, [claim(text)])
    assert row.verdict == verdict, (row.verdict, row.route, row.sketch, row.note)


# ---- missing-value policies read from a guard -------------------------------

def pol_rare(x: Optional[float], y: float) -> float:
    if y == 0.123456:
        return y
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_literal(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_kw(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError(msg="x is required")
    return x * y


def pol_prefix(x: Optional[float], y: float) -> float:
    if x is None:
        z = 1 / y  # noqa: F841
        raise TypeError("x is required")
    return x * y


def pol_ctor(x: Optional[float], y: float) -> float:
    if x is None:
        raise Refusing("x is required")
    return x * y


def pol_local(x: Optional[float], y: float) -> float:
    class TypeError(Exception):  # noqa: A001
        pass
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_kw_value(x: Optional[float], y: float) -> float:
    if x is None:
        raise ValueError(msg="x is required")
    return x * y


def pol_or(x: Optional[float], y: float) -> float:
    if x is None or y is None:
        raise TypeError("x is required")
    return x * y


POLICY_CASES = [
    (pol_rare, "absent(f, x) raises", "holds"),
    (pol_rare, "absent(f, x) raises(TypeError)", "holds"),
    (pol_literal, "absent(f, x) raises", "proven"),
    (pol_literal, "absent(f, x) raises(TypeError)", "proven"),
    (pol_kw, "absent(f, x) raises(TypeError)", "holds"),
    (pol_prefix, "absent(f, x) raises(TypeError)", "holds"),
    (pol_ctor, "absent(f, x) raises(TypeError)", "falsified"),
    (pol_local, "absent(f, x) raises(TypeError)", "holds"),
    (pol_kw_value, "absent(f, x) raises(ValueError)", "falsified"),
    (pol_or, "absent(f, x) raises(TypeError)", "proven"),
]


@pytest.mark.parametrize("fn,text,verdict", POLICY_CASES,
                         ids=[f"{fn.__name__}:{text}" for fn, text, _ in POLICY_CASES])
def test_a_review_policy_case_gets_its_verdict(fn, text, verdict):
    rows = check_conjectures(fn, [claim("for x in [0, 1], y in [-1, 1], f(x, y) == x * y"),
                                  claim(text)])
    row = rows[-1]
    assert row.verdict == verdict, (row.verdict, row.route, row.note)


# ---- cases that exit or never finish: the prover alone ----------------------

def sysexit(x: float) -> float:
    if x < 0:
        raise SystemExit("bye")
    return x


def _spin(x):
    while True:
        pass


def spin_arg(x: float) -> float:
    if x < 0:
        raise ValueError(_spin(x))
    return x


@pytest.mark.parametrize("fn,exception,status", [
    (sysexit, None, "proven"),
    (sysexit, "SystemExit", "proven"),
    (spin_arg, "ValueError", "undecided"),
    (spin_arg, None, "undecided"),
], ids=["sysexit unnamed", "sysexit named", "spin named", "spin unnamed"])
def test_a_review_case_that_must_not_run_is_proven_only_as_read(fn, exception, status):
    from mathema import analyze
    from mathema.symbolic._prove import try_prove_raises
    proof = try_prove_raises(fn, analyze(fn), "f(x)", exception, {"x": (-5, -1)})
    assert proof.status == status, (proof.status, proof.sketch)


# ---- reader cases no route reaches ------------------------------------------

def eg_any(x):
    raise ExceptionGroup("m", x)  # noqa: F821


def ude_any(x):
    raise UnicodeDecodeError("a", b"", x, 1, "r")


def rebind_cls(x):
    global ValueError
    ValueError = KeyError  # noqa: F841
    raise ValueError("neg")


def rebind_str(x: float):
    global str
    str = len  # noqa: F841
    raise ValueError(str(x))


@pytest.mark.parametrize("fn,kinds", [
    (eg_any, None), (ude_any, None), (rebind_cls, None), (rebind_str, "float"),
], ids=["eg_any", "ude_any", "rebind_cls", "rebind_str"])
def test_a_review_reader_case_is_unread_and_not_known_to_finish(fn, kinds):
    import ast
    import inspect
    import textwrap
    from mathema._raise_reading import ANY, UnreadRaise, ValueKind, read_raise_path
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
    body = [s for s in tree.body if not isinstance(s, ast.Global)]
    kind = ANY if kinds is None else ValueKind(frozenset({float}))
    reading = read_raise_path(fn, [("stmt", s) for s in body[:-1]], body[-1], {"x": kind})
    assert isinstance(reading, UnreadRaise) and not reading.halts, reading


# ---- third review: a lambda's defaults run when the lambda is built ---------

def pol_lam(x: Optional[float], y: float) -> float:
    g = lambda a=1 / (y - 0.123456): a  # noqa: E731,F841
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_lam_inner(x: Optional[float], y: float) -> float:
    if x is None:
        g = lambda a=1 / (y - 0.123456): a  # noqa: E731,F841
        raise TypeError("x is required")
    return x * y


def pol_lam_kw(x: Optional[float], y: float) -> float:
    g = lambda *, a=1 / (y - 0.123456): a  # noqa: E731,F841
    if x is None:
        raise TypeError("x is required")
    return x * y


def pol_lam_plain(x: Optional[float], y: float) -> float:
    g = lambda: 1 / (y - 0.123456)  # noqa: E731,F841
    if x is None:
        raise TypeError("x is required")
    return x * y


@pytest.mark.parametrize("fn,verdict", [
    (pol_lam, "holds"), (pol_lam_inner, "holds"), (pol_lam_kw, "holds"),
    (pol_lam_plain, "proven"),
], ids=lambda v: getattr(v, "__name__", v))
def test_a_lambda_default_is_read_where_the_lambda_is_built(fn, verdict):
    if fn is not pol_lam_plain:
        with pytest.raises(ZeroDivisionError):
            fn(None, 0.123456)
    rows = check_conjectures(fn, [claim("for x in [0, 1], y in [-1, 1], f(x, y) == x * y"),
                                  claim("absent(f, x) raises(TypeError)")])
    assert rows[-1].verdict == verdict, (rows[-1].verdict, rows[-1].note)


# ---- third review: the policy route reads what the call does ----------------

def _rare_swallow(fn):
    @functools.wraps(fn)
    def rarely(x, y):
        if y == 0.123456:
            return 0.0
        return fn(x, y)
    return rarely


@_rare_swallow
def pol_wrap_rare(x: Optional[float], y: float) -> float:
    if x is None:
        raise TypeError("x is required")
    return x * y


def test_a_policy_behind_a_wrapper_is_not_proven_from_the_inner_guard():
    assert pol_wrap_rare(None, 0.123456) == 0.0
    rows = check_conjectures(pol_wrap_rare, [
        claim("for x in [0, 1], y in [-1, 1], f(x, y) == x * y"),
        claim("absent(f, x) raises(TypeError)")])
    assert rows[-1].verdict == "holds", (rows[-1].verdict, rows[-1].note)


# ---- third review: a format field that is not a decimal index ---------------

def brace_super_digit(x: float) -> float:
    if x < 0:
        raise ValueError("{²}".format(x))  # noqa: F523,F524
    return x


def test_a_format_field_of_a_digit_that_is_not_decimal_is_not_read():
    with pytest.raises(KeyError):
        brace_super_digit(-2.0)
    (row,) = check_conjectures(brace_super_digit,
                               [claim("for x in [-5, -1], raises(f(x), ValueError)")])
    assert row.verdict == "falsified", (row.verdict, row.sketch)


# ---- third review: a name imported then rebound -----------------------------

def import_rebind(x: float) -> float:
    import math as m  # noqa: F401
    m = 5  # noqa: F811,F841
    raise ValueError(m.isnan(x))


def test_a_module_name_rebound_after_its_import_is_not_the_module():
    import ast
    import inspect
    import textwrap
    from mathema._raise_reading import ReadRaise, ValueKind, read_raise_path
    with pytest.raises(AttributeError):
        import_rebind(-3.0)
    tree = ast.parse(textwrap.dedent(inspect.getsource(import_rebind))).body[0]
    body = tree.body
    reading = read_raise_path(import_rebind, [("stmt", s) for s in body[:-1]], body[-1],
                              {"x": ValueKind(frozenset({float}), 5.0, 1.0)})
    assert not isinstance(reading, ReadRaise), reading


# ---- third review: an instance wrapper whose attribute read runs code -------

def _p1(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


def _p2(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


class Shadow:
    fn = property(lambda self: (lambda x: 0.0))

    def __init__(self, fn):
        self.__dict__["fn"] = fn
        functools.update_wrapper(self, fn)
        self.__name__ = "shadow_" + fn.__name__

    def __call__(self, x):
        return self.fn(x)


class GetAttr:
    def __init__(self, fn):
        self.fn = fn
        functools.update_wrapper(self, fn)
        self.__name__ = "getattr_" + fn.__name__

    def __getattribute__(self, name):
        if name == "fn":
            return lambda x: 0.0
        return object.__getattribute__(self, name)

    def __call__(self, x):
        return self.fn(x)


@pytest.mark.parametrize("wrapper", [Shadow(_p1), GetAttr(_p2)], ids=["Shadow", "GetAttr"])
def test_an_instance_whose_attribute_read_runs_code_is_not_read_through(wrapper):
    assert wrapper(-2.0) == 0.0
    (row,) = check_conjectures(wrapper, [claim("for x in [-5, -1], raises(f(x), TypeError)")])
    assert row.verdict != "proven", (row.verdict, row.route, row.sketch)


# ---- third review: names, places and wording --------------------------------

_ALIASED = """
from math import isinf as isnan


def pol_alias_isnan(x: float, y: float) -> float:
    if isnan(x):
        raise ValueError("x is nan")
    return x * y
"""


def test_a_guard_callee_counts_by_what_it_is_not_by_its_name():
    import ast
    from mathema.policy import _true_at_hole
    space: dict = {}
    exec(_ALIASED, space)
    test = ast.parse("isnan(x)", mode="eval").body
    assert not _true_at_hole(test, "x", "missing", "nan", space["pol_alias_isnan"])
    assert _true_at_hole(test, "x", "missing", "nan", _a_true_isnan_guard)


def _a_true_isnan_guard(x: float) -> float:
    if math.isnan(x):
        raise ValueError("nan")
    return x


def test_a_wrapper_is_named_by_its_module_never_a_machine_path():
    from mathema.symbolic._base import wrapper_refusal
    function_text = wrapper_refusal(pol_wrap_rare)
    instance_text = wrapper_refusal(Shadow(_p1))
    for text in (function_text, instance_text):
        assert "/" not in text and "decorator" not in text, text
    assert f"module {__name__} line" in function_text, function_text
    assert "an instance of `Shadow`" in instance_text, instance_text


def _nested_rebinds(x):
    def inner():
        global ValueError
        ValueError = KeyError  # noqa: F841
    raise ValueError("neg")


def test_a_rebound_name_says_what_is_not_known_without_naming_a_claim():
    import ast
    import inspect
    import textwrap
    from mathema._raise_reading import ANY, UnreadRaise, read_raise_path
    tree = ast.parse(textwrap.dedent(inspect.getsource(_nested_rebinds))).body[0]
    reading = read_raise_path(_nested_rebinds, [], tree.body[-1], {"x": ANY})
    assert isinstance(reading, UnreadRaise), reading
    assert "nested" in reading.reason and "claim" not in reading.reason, reading.reason
