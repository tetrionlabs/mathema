# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Each function here is drawn for in the shape its code reads, and its
probe claim keeps the verdict that shape gives: a shape read from an
annotation, a default or a use in the body; a local copy read through
or not; a raise blamed on the draw only when the raising frame holds the
drawn value; lambdas, partials, wrappers and callable instances read
through to their source. A parameter whose shape nothing establishes
(`same(x): return x`) is not drawn, and its verdict is unknown."""
import importlib.util
import sys

import pytest

from mathema.conjecture import check_conjectures, claim


SOURCES = {
    "first": """\
import dataclasses
import math
from typing import Optional, Union


def same(x):
    return x


def label(n):
    if n > 0:
        return "count: " + n
    return ""


def typo(x):
    if x > 100:
        return x.offest
    return x + 1


def negidx(x):
    if x < 0:
        return x[0]
    return x + 1


def copy_closure(y0):
    t = y0
    get = lambda: t[0]
    t = [1.0]
    return get() + y0


def copy_inner_param(y0):
    t = y0
    def first(t):
        return t[0]
    return t * 2 + first([1.0])


def copy_except(y0):
    t = y0
    try:
        raise ValueError("v")
    except ValueError as t:
        pass
    return y0 + 1


def opt_len(xs: Optional[list] = None):
    return len(xs)


def union_num(x: Union[int, str]):
    return x * 2


def none_default(x, scale=None):
    if scale is None:
        return x
    return x * scale


def none_default_bug(x, scale=None):
    return x * scale


def both(x):
    s = 0.0
    for v in x:
        s += v
    return s


def str_mul(x):
    return x * "ab"


def only_locals(x):
    return locals()["x"] + 1


def only_kwargs(**kw):
    return kw["x"] + 1


def pass_through(x):
    return helper(x)


def helper(v):
    return v + 1


def fmt(x):
    return "%d items" % x


def neg_str(x):
    return x == "a" or x + 1 > 3
""",
    "second": """\
import dataclasses
from typing import Optional, Sequence, Mapping


def first(x: float):
    return x[0]


def shout_int(x: int):
    return x.upper()


def opt_plus(x: Optional[float] = None):
    return x + 1


def seq_ann(xs: Sequence[float]):
    return sum(xs)


def tup_ann(xs: tuple):
    return len(xs)


def map_ann(d: Mapping):
    return len(d)


def set_ann(s: set):
    return len(s)


def copy_inner_param2(y0):
    t = y0
    def first(t):
        return t[0]
    return t + first([1.0])


def lam_param(y0):
    t = y0
    pick = lambda t: t[0]
    return t + pick([1.0])


def comp_reuse(y0):
    t = y0
    firsts = [t[0] for t in [[1.0], [2.0]]]
    return t + firsts[0]


def label(n):
    if n > 0:
        return "count: " + n
    return ""


def default_vs_use(x=1.0):
    return x[0]
""",
    "third": """\
import math


def typo(x):
    if x > 100:
        return x.offest
    return x + 1


def scale(v):
    return v * 2 + v.offset


def same(x):
    return x


def none_default_bug(x, scale=None):
    return x * scale


def copy_inner_param2(y0):
    t = y0
    def first(t):
        return t[0]
    return t + first([1.0])
""",
    "fourth": """\
import functools

inc = lambda x: x + 1


def add(x, y):
    return x + y


inc_p = functools.partial(add, y=1.0)


def deco(g):
    @functools.wraps(g)
    def w(*a, **k):
        return g(*a, **k)
    return w


@deco
def wrapped(x):
    return x + 1


def outer():
    def inner(x):
        return x - 1
    return inner


inner = outer()
""",
    "fifth": """\
_CACHE = {}


def keyed(key=(1, 2)):
    d = {key: 1}
    return len(d)


def cached(key=(1, 2)):
    _CACHE[key] = 1
    return 1


def tuple_concat(axes=()):
    return len(axes + (1,))
""",
    "settle": """\
import functools
from typing import Any, Optional, Union, TypeVar, SupportsAbs

T = TypeVar("T")


def s_opt_float(x: Optional[float] = None):
    return x + 1


def s_any_index(x: Any):
    return x[0]


def s_strann_upper(x: "float"):
    return x.upper()


def s_typevar_index(x: T) -> T:
    return x[0]


def s_protocol_abs(x: SupportsAbs):
    return abs(x)


def s_shape_attr(x):
    return x.shape[0]


def s_none_upper(x=None):
    return x.upper()


def s_strdefault_plus(x="a"):
    return x + 1


def s_len_and_gt(x):
    return len(x) + (x > 0)


def s_fmt_upper_mod(fmt):
    return fmt.upper() % 5


def s_union_ann(x: Union[int, str]):
    return x * 2


def s_float_ann_strmul(x: float):
    return x * "ab"


def s_int_ann_strmul(x: int):
    return x * "ab"


def s_floatann_index(x: float):
    return x[0]


def c_loop(y0):
    t = y0
    acc = 0.0
    for _ in range(2):
        acc = acc + t
        t = "x"
    return acc


def c_semicolon(y0):
    t = y0
    t = 2.0; r = t + 1
    return y0.upper() + str(r)


def c_branch(y0, flag: bool):
    t = y0
    if flag:
        t = "s"
    return t + 1.0


def c_with(y0):
    t = y0
    with open.__class__ if False else _Ctx() as t:
        pass
    return t + 1.0


class _Ctx:
    def __enter__(self):
        return "ctx"

    def __exit__(self, *a):
        return False


def c_try(y0):
    t = y0
    try:
        r = t + 1.0
    finally:
        t = None
    return r


def c_walrus(y0):
    t = y0
    if (t := "w"):
        pass
    return t + 1.0


def c_del(y0):
    t = y0
    del t
    t = "d"
    return t + 1.0


def c_star(y0):
    t = y0
    *t, = ["a"]
    return t + 1.0


def c_aug(y0):
    t = y0
    t += 1.0
    return t.upper()


def c_unpack(y0):
    a, t = y0, 1
    return a + 1.0


def r_list_literal(xs):
    return len([0] + xs)


def r_tuple_literal(xs):
    return len((0,) + xs)


def r_acc_str(x):
    acc = 0.0
    for _ in range(2):
        acc = acc + x
        acc = str(acc)
    return acc


def r_list_default(axes=[]):
    return len(axes + (1,))


def i_range(x):
    return sum(range(x))


def i_listmul(x):
    return len([0] * x)


def i_shift(x):
    return x << 1


def i_index(x):
    return [10, 20, 30][x]


def i_strmul_r(x):
    return len("ab" * x)


def i_strmul_plus_float(x):
    return len(x * "ab") + x / 2.0


def i_bitlen(x):
    return x.bit_length()


def i_and(x):
    return x & 1
""",
    "stated": """\
def b_float_ann_strmul_type(x: float):
    if x != x:
        return x * "ab"
    return 1 if isinstance(x, float) else 0


def b_float_ann_strmul(x: float):
    return x * "ab"


def b_float_ann_strmul_len(x: float) -> int:
    return len(x * "ab")


def b_float_ann_count(x: float) -> float:
    n = len("ab" * x)
    return n + x
""",
    "callers": """\
import functools

inc_a, shout_a = (lambda x: x + 1.0), (lambda x: x[0] + 1.0)

SPEC = dict(
    key=lambda x: x[0] + 1.0,
)

called = sorted([3.0, 1.0], key=lambda x: x + 1.0)
in_call = functools.partial(lambda x, k: x[0] + k, k=1.0)


def add(a, b):
    return a + b[0]


p_pos = functools.partial(add, 1.0)
p_of_p = functools.partial(functools.partial(add, b=[2.0]))
p_kw = functools.partial(add, b=[2.0])


def to_count(fn):
    @functools.wraps(fn)
    def w(n):
        return fn("a" * n)
    return w


@to_count
def shout(s):
    return len(s.upper())


def twice(fn):
    @functools.wraps(fn)
    def w(x):
        return fn(fn(x))
    return w


@twice
@twice
def bump(x):
    return x + 1.0


class K:
    def m(self, x):
        return x[0] + 1.0

    @classmethod
    def cm(cls, x):
        return x[0] + 1.0

    @staticmethod
    def sm(x):
        return x[0] + 1.0

    def __call__(self, x):
        return x[0] + 1.0


bound = K().m
inst = K()


def plain_index(x):
    return x[0] + 1.0
""",
    "magnitude": """\
def mag_int_ann(x: int):
    return x


def mag_strmul_unreached(x):
    if x is None:
        return x * "ab"
    return x
""",
    "own": """\
import dataclasses


def keyed_by(key: tuple):
    d = {key: 1}
    return len(d)


def matched(y0):
    t = y0
    match [[1.0]]:
        case [t]:
            pass
    return t[0] + y0


def defined(y0):
    t = y0
    def t():
        return [1.0]
    return t()[0] + y0


def text_or_mapping(x):
    return x.upper(), x.keys()


def repeat(x):
    return x * "ab"


def rows(x):
    return x.shape[0]


def total_into(xs: list, out=None) -> float:
    s = sum(xs)
    if out is not None:
        out.append(s)
    return s


class Picker:
    def __call__(self, x):
        return x[0] + 1.0


picker = Picker()
""",
}


@pytest.fixture(scope="module")
def modules(tmp_path_factory):
    root = tmp_path_factory.mktemp("shape_cases")
    loaded = {}
    for key, text in SOURCES.items():
        name = f"shape_case_{key}"
        path = root / f"{name}.py"
        path.write_text(text)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        loaded[key] = module
    yield loaded
    for key in SOURCES:
        sys.modules.pop(f"shape_case_{key}", None)


CASES = [
    ('first', 'same', 'f(x) > x', 'unknown'),
    ('first', 'same', 'f(x) == x', 'unknown'),
    ('first', 'label', 'f(n) == f(n)', 'falsified'),
    ('first', 'typo', 'f(x) >= x', 'falsified'),
    ('first', 'negidx', 'f(x) >= x', 'falsified'),
    ('first', 'copy_closure', 'f(y0) == y0 + 1.0', 'holds'),
    ('first', 'copy_inner_param', 'f(y0) == 2 * y0 + 1.0', 'falsified'),
    ('first', 'copy_except', 'f(y0) == y0 + 1', 'holds'),
    ('first', 'opt_len', 'f(xs) >= 0', 'holds'),
    ('first', 'union_num', 'f(x) == f(x)', 'holds'),
    ('first', 'none_default', 'f(x) == x', 'holds'),
    ('first', 'none_default_bug', 'f(x) == f(x)', 'falsified'),
    ('first', 'both', 'f(x) >= 0', 'falsified'),
    ('first', 'str_mul', 'f(x) == f(x)', 'holds'),
    ('first', 'only_locals', 'f(x) > x', 'falsified'),
    ('first', 'only_kwargs', 'f(x) > x', 'skipped:misspecified'),
    ('first', 'pass_through', 'f(x) > x', 'falsified'),
    ('first', 'fmt', 'f(x) == f(x)', 'holds'),
    ('first', 'neg_str', 'f(x) == f(x)', 'holds'),
    ('second', 'first', 'f(x) == f(x)', 'falsified'),
    ('second', 'shout_int', 'f(x) == f(x)', 'falsified'),
    ('second', 'opt_plus', 'f(x) == f(x)', 'holds'),
    ('second', 'seq_ann', 'f(xs) == f(xs)', 'holds'),
    ('second', 'tup_ann', 'f(xs) >= 0', 'holds'),
    ('second', 'map_ann', 'f(d) >= 0', 'holds'),
    ('second', 'set_ann', 'f(s) >= 0', 'holds'),
    ('second', 'copy_inner_param2', 'f(y0) == y0 + 1.0', 'holds'),
    ('second', 'lam_param', 'f(y0) == y0 + 1.0', 'holds'),
    ('second', 'comp_reuse', 'f(y0) == y0 + 1.0', 'holds'),
    ('second', 'default_vs_use', 'f(x) == f(x)', 'holds'),
    ('third', 'typo', 'for x in R, f(x) >= x', 'falsified'),
    ('third', 'typo', 'is_language_defined(f)', 'unknown'),
    ('third', 'scale', 'is_language_defined(f)', 'unknown'),
    ('third', 'same', 'is_language_defined(f)', 'unknown'),
    ('third', 'none_default_bug', 'is_language_defined(f)', 'unknown'),
    ('third', 'none_default_bug', 'f(x) >= 0', 'falsified'),
    ('third', 'copy_inner_param2', 'is_language_defined(f)', 'unknown'),
    ('fourth', 'inc', 'f(x) > x', 'falsified'),
    ('fourth', 'inc_p', 'f(x) > x', 'falsified'),
    ('fourth', 'wrapped', 'f(x) > x', 'falsified'),
    ('fourth', 'inner', 'f(x) < x', 'falsified'),
    ('fifth', 'keyed', 'f(key) == 1', 'holds'),
    ('fifth', 'cached', 'f(key) == 1', 'holds'),
    ('fifth', 'tuple_concat', 'f(axes) >= 1', 'holds'),
    ('settle', 's_opt_float', 'f(x) >= x', 'holds'),
    ('settle', 's_any_index', 'f(x) == f(x)', 'holds'),
    ('settle', 's_strann_upper', 'f(x) == f(x)', 'falsified'),
    ('settle', 's_typevar_index', 'f(x) == f(x)', 'holds'),
    ('settle', 's_protocol_abs', 'f(x) >= 0', 'holds'),
    ('settle', 's_shape_attr', 'f(x) >= 0', 'unknown'),
    ('settle', 's_none_upper', 'f(x) == f(x)', 'skipped'),
    ('settle', 's_strdefault_plus', 'f(x) == f(x)', 'holds'),
    ('settle', 's_len_and_gt', 'f(x) >= 0', 'falsified'),
    ('settle', 's_fmt_upper_mod', 'f(fmt) == f(fmt)', 'skipped'),
    ('settle', 's_union_ann', 'f(x) == f(x)', 'holds'),
    ('settle', 's_float_ann_strmul', 'f(x) == f(x)', 'falsified'),
    ('settle', 's_int_ann_strmul', 'f(x) == f(x)', 'holds'),
    ('settle', 's_floatann_index', 'f(x) == f(x)', 'falsified'),
    ('settle', 'c_loop', 'f(y0) == f(y0)', 'falsified'),
    ('settle', 'c_semicolon', 'f(y0) == f(y0)', 'skipped'),
    ('settle', 'c_branch', 'f(y0, flag) == f(y0, flag)', 'falsified'),
    ('settle', 'c_with', 'f(y0) == f(y0)', 'falsified'),
    ('settle', 'c_try', 'f(y0) == f(y0)', 'holds'),
    ('settle', 'c_walrus', 'f(y0) == f(y0)', 'falsified'),
    ('settle', 'c_del', 'f(y0) == f(y0)', 'falsified'),
    ('settle', 'c_star', 'f(y0) == f(y0)', 'falsified'),
    ('settle', 'c_aug', 'f(y0) == f(y0)', 'falsified'),
    ('settle', 'c_unpack', 'f(y0) == f(y0)', 'holds'),
    ('settle', 'r_list_literal', 'f(xs) >= 1', 'holds'),
    ('settle', 'r_tuple_literal', 'f(xs) >= 1', 'holds'),
    ('settle', 'r_acc_str', 'f(x) == f(x)', 'falsified'),
    ('settle', 'r_list_default', 'f(axes) >= 1', 'falsified'),
    ('settle', 'i_range', 'f(x) >= 0', 'holds'),
    ('settle', 'i_listmul', 'f(x) >= 0', 'holds'),
    ('settle', 'i_shift', 'f(x) == 2 * x', 'holds'),
    ('settle', 'i_index', 'f(x) >= 10', 'falsified'),
    ('settle', 'i_strmul_r', 'f(x) >= 0', 'holds'),
    ('settle', 'i_strmul_plus_float', 'f(x) == f(x)', 'holds'),
    ('settle', 'i_bitlen', 'f(x) >= 0', 'holds'),
    ('settle', 'i_and', 'f(x) <= 1', 'holds'),
    ('stated', 'b_float_ann_strmul_type', 'f(x) == 1', 'holds'),
    ('stated', 'b_float_ann_strmul', 'f(x) == f(x)', 'falsified'),
    ('stated', 'b_float_ann_strmul_len', 'f(x) >= 0', 'falsified'),
    ('stated', 'b_float_ann_count', 'f(x) == f(x)', 'falsified'),
    ('stated', 'b_float_ann_strmul', 'for x in R, f(x) == f(x)', 'falsified'),
    ('callers', 'inc_a', 'f(x) > x', 'falsified'),
    ('callers', 'shout_a', 'f(x) == f(x)', 'holds'),
    ('callers', "SPEC['key']", 'f(x) == f(x)', 'holds'),
    ('callers', 'in_call', 'f(x) == f(x)', 'holds'),
    ('callers', 'p_pos', 'f(b) == f(b)', 'holds'),
    ('callers', 'p_of_p', 'f(a) > a', 'falsified'),
    ('callers', 'p_kw', 'f(a) > a', 'falsified'),
    ('callers', 'shout', 'f(s) >= 0', 'skipped'),
    ('callers', 'bump', 'f(x) == x + 4.0', 'holds'),
    ('callers', 'bound', 'f(x) == f(x)', 'holds'),
    ('callers', 'K.cm', 'f(x) == f(x)', 'holds'),
    ('callers', 'K.sm', 'f(x) == f(x)', 'holds'),
    ('callers', 'inst', 'f(x) == f(x)', 'holds'),
    ('callers', 'plain_index', 'f(x) == f(x)', 'holds'),
    ('magnitude', 'mag_int_ann', 'abs(f(x)) <= 1000', 'holds'),
    ('magnitude', 'mag_int_ann', 'abs(f(x)) <= 100000', 'holds'),
    ('magnitude', 'mag_strmul_unreached', 'abs(f(x)) <= 1000', 'holds'),
    ('magnitude', 'mag_strmul_unreached', 'abs(f(x)) <= 100000', 'holds'),
    ('magnitude', 'mag_strmul_unreached', 'abs(f(x)) <= 10000000', 'holds'),
    ('own', 'keyed_by', 'f(key) == 1', 'holds'),
    ('own', 'matched', 'f(y0) == y0 + 1.0', 'holds'),
    ('own', 'defined', 'f(y0) == y0 + 1.0', 'holds'),
    ('own', 'text_or_mapping', 'f(x) == f(x)', 'unknown'),
    ('own', 'repeat', 'f(x) == f(x)', 'holds'),
    ('own', 'rows', 'f(x) >= 0', 'unknown'),
    ('own', 'picker', 'f(x) == f(x)', 'holds'),
]


@pytest.mark.parametrize("module, function, text, verdict", CASES)
def test_each_case_keeps_its_verdict(modules, module, function, text, verdict):
    fn = eval(function, vars(modules[module]))
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    assert p.verdict == verdict, (p.verdict, p.note, p.counterexample)
