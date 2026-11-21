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
    "r3a": """\
import math

def h_idx(v):
    return v[0]

def pt_gt(x):
    if x > 0:
        return h_idx(x)
    return 0.0

def pt_plain(x):
    return h_idx(x) + 1.0

def lam_inner(x):
    g = lambda: x[0]
    return g() + 1.0

def comp_inner(x):
    return sum([x[i] for i in range(2)])

def nested_inner(x):
    def g():
        return x[0]
    return g() * 2.0

def reassigned_float(x):
    x = float(x)
    return x[0]

def plus_zero(x):
    t = x + 0
    return t[0]

def mutate_list(xs: list):
    xs.append("a")
    return xs[-1] + 1.0

def c_raise(x):
    return math.sqrt(x) + len(x)

def chained(x):
    try:
        return x[0]
    except TypeError as e:
        raise ValueError("bad") from e

def chained_type(x):
    try:
        return x + 1.0
    except TypeError:
        raise TypeError("float wanted")

_G = None

def set_g_list():
    global _G
    _G = [1.0]

def g_copy(y0):
    global _G
    _G = y0
    set_g_list()
    return _G[0] + y0

def acc_zero(y0):
    t = y0
    for k in range(2):
        if k == 1:
            return t.upper()
        t = t + ""
    return t

def acc_int_zero(y0):
    t = y0
    out = 0
    for k in range(2):
        out = out + t[0]
        t = t + 0
    return out

def dup_unpack(y0):
    t, t = y0, [1.0]
    return t[0] + y0

def swap_copy(y0, y1):
    a, b = y1, y0
    return a[0] + b

def for_target(y0):
    t = y0
    for t in [[1.0]]:
        pass
    return t[0] + y0

def loop_rebind_after(y0):
    t = y0
    s = 0.0
    for _ in range(2):
        s = s + t
        t = [1.0]
    return s

def acc_flip(y0):
    t = y0
    out = 0
    for _ in range(2):
        out = out + len(str(t))
        t = t * "ab"
    return out

def acc_list(y0):
    t = y0
    n = 0.0
    for _ in range(2):
        n = n + t[0]
        t = [t]
    return n

def acc_keeps(y0):
    total = y0
    for v in (1.0, 2.0):
        total = total + v
    return total

def nonlocal_copy(y0):
    t = y0
    def setit():
        nonlocal t
        t = [1.0]
    setit()
    return t[0] + y0

def walrus_copy(y0):
    if (t := y0) is not None:
        return t[0]
    return 0.0

def with_copy(y0):
    t = y0
    return t + 1.0

def try_rebind(y0):
    t = y0
    try:
        t = [1.0]
    except Exception:
        pass
    return t[0] + y0

def copy_then_branch(y0, flag: bool):
    t = y0
    if flag:
        t = [1.0]
    return t[0]

def copy_then_overwrite(y0):
    t = y0
    t = 2.0
    return t + 1.0

def tri(x):
    return sum(range(x))

def bl(x):
    return x.bit_length()

def shl(x):
    return x << 1

def listmul(x):
    return len([0] * x)

def none_guard_mag(x):
    if x is None:
        return x * "ab"
    return x

def none_guard_sq(x):
    if x is None:
        return range(x)
    return x * x

def isint_guard(x):
    if isinstance(x, int):
        return x >> 0
    return x * 3.0 / 3.0

def notnone_else(x):
    if x is not None:
        return x * 2.0
    return x << 1

def lit_index(x):
    return (1.0, 2.0, 3.0)[x] * 2.0

def mix_cont(xs, flag: bool):
    if flag:
        return len([0] + xs)
    return len(xs + (1,))

def tup_sum(xs):
    return sum((0.0,) + xs)

def shape_and_len(x):
    return x.shape[0] + len(x)

def shape_and_idx(x):
    return x.shape[0] + x[0]

def shape_copy(x):
    a = x
    return a.shape[0]

def ndim_only(x):
    return x.ndim

lam_a, lam_b = (lambda x: x + 1.0), (lambda x: x[0] + 1.0)
twins = (lambda x: x + 1.0, lambda x: x + 1.0)
cont = (lambda x:
        x[0] + 1.0)
nest_same = lambda x: (lambda x: x + 1.0)(x[0])
outer_only = lambda x: (lambda x: x[0])

class BaseCall:
    def __call__(self, x):
        return x[0] + 1.0

class SubCall(BaseCall):
    pass

sub_inst = SubCall()

def _late_call(self, x):
    return x + 1.0

class LateCall:
    pass

LateCall.__call__ = _late_call
late_inst = LateCall()

class StaticCall:
    __call__ = staticmethod(lambda x: x[0] + 1.0)

static_inst = StaticCall()

def first_float(x: float):
    return x[0]

def upper_int(x: int):
    return x.upper()

def cmp_and_idx(x):
    return x[0] if x > 0 else 0.0

def ann_list_numeric(x: list):
    return x + 1.0
""",
    "r3b": """\
import math

def bl_ann(x: int):
    return x.bit_length()

def tri_ann(x: int):
    return sum(range(x))

def bl(x):
    return x.bit_length()

def tri(x):
    return sum(range(x))

def ident_int_ann(x: int):
    return x

# empty-input row
_MISSING = object()

def pick(xs: list, k=_MISSING):
    if k is _MISSING:
        return float(len(xs))
    return len(xs) * k

def mean_k(xs: list, k=None):
    if k is None:
        return 0.0
    return sum(xs) / len(xs) * k

def mean_req(xs: list, k):
    return sum(xs) / len(xs) * k

def mean_req_noev(xs: list, k):
    if k:
        return sum(xs) / len(xs)
    return 0.0

def mutdef(xs: list, acc=[]):
    acc.append(1.0)
    return sum(xs) + len(acc)

def kwonly(xs: list, *, k=None):
    if k is None:
        return 0.0
    return sum(xs) / len(xs)

def kwonly_req(xs: list, *, k):
    return sum(xs) / len(xs) + k

def star_args(xs: list, *rest):
    return sum(xs) / len(xs) if rest else 0.0

def star_kw(xs: list, **kw):
    return sum(xs) / len(xs) if kw else 0.0

def dflt_float(xs: list, k=0.0):
    if k > 0.5:
        return sum(xs) / len(xs)
    return 0.0

# lambda messages
same2 = (lambda x: x, lambda x: x)
two_seq = (lambda x: x[0], lambda x: x[1])

# stated domains and families
def typo(x):
    if x > 100:
        return x.offest
    return x + 1

def sq(x):
    return x * x

def half(x):
    return x / 2

def first(xs):
    return xs[0]

def strmul(x):
    return x * "ab"

def guarded(x):
    if x is None:
        return x * "ab"
    return x
""",
    "r3c": """\
def acc_wrap(y0):
    t = y0
    out = 0.0
    for k in range(2):
        if k > 0:
            out = out + t[0]
        t = [t]
    return out

def acc_str(y0):
    t = y0
    n = 0
    for k in range(2):
        if k > 0:
            n = n + len(t.upper())
        t = str(t) + "!"
    return n + y0

def acc_aug(y0):
    t = y0
    out = 0.0
    for k in range(2):
        if k > 0:
            out = out + t[0]
        t += [1.0] if isinstance(t, list) else 0.0
    return out

def acc_num_ok(y0):
    t = y0
    for _ in range(2):
        t = t * 2.0
    return t

pair_u = ("éé", lambda x: x + 1.0, lambda x: x[0] + 1.0)

class Holder:
    lam = (lambda x: x + 1.0, lambda x: x[0] + 1.0)

def none_mid(x):
    if x is None:
        return 0
    if x == "none":
        return x * "ab"
    return x

def eq_none(x):
    if x == None:
        return x << 2
    return x * x

def ifexp_none(x):
    return (x << 1) if x is None else x * x

def raise_guard(x):
    if not isinstance(x, int):
        return x * x
    return x << 1
""",
    "r3d": """\
def closure_copy(y0):
    t = y0
    g = lambda: t[0]
    return g() + 1.0

def comp_copy(y0):
    t = y0
    return sum([t[i] for i in range(2)])

def nested_def_copy(y0):
    t = y0
    def g():
        return t * 2.0
    return g()

def gen_copy(y0):
    t = y0
    return max(v for v in t)
""",
    "r3f": """\
multi = (lambda x: x + 1.0,
         lambda x: x[0] + 1.0)
multi2 = (lambda x: x[0] + 1.0, lambda y: y + 1.0,
          lambda x: x + 1.0)
""",
    "r3g": """\
def dis_copy(y0):
    t = y0
    return t.upper(), t.keys()

def dis_default(x="a"):
    return x.keys()

def dis_ann(x: dict = 1.0):
    return x.keys()

def dis_three(x):
    return x.upper(), x.keys(), x[0] > "a" == x.append
""",
    "r3h": """\
import functools

def as_count(fn):
    @functools.wraps(fn)
    def w(n):
        return fn("b" * n)
    return w

@as_count
def loud(s):
    return len(s.upper())

def ident_shift(x):
    return x << 0

def sum_upto(x):
    return sum(range(x))
""",
    "r3e": """\
_MISSING = object()

def pick(xs: list, k=_MISSING):
    if k is _MISSING:
        return float(len(xs))
    return len(xs) * k

def mean_k(xs: list, k=None):
    if k is None:
        return 0.0
    return sum(xs) / len(xs) * k

def mean_req(xs: list, k: float):
    return sum(xs) / len(xs) * k

def mutdef(xs: list, acc=[]):
    acc.append(1.0)
    return sum(xs) + len(acc)

def kwonly(xs: list, *, k=None):
    if k is None:
        return 0.0
    return sum(xs) / len(xs)

def star_args(xs: list, *rest):
    return sum(xs) / len(xs) if rest else 0.0

def dflt_float(xs: list, k=0.0):
    if k > 0.5:
        return sum(xs) / len(xs)
    return 0.0

def mean_plain(xs: list):
    return sum(xs) / len(xs)

def scaled_total(xs: list, scale=1.0):
    return sum(xs) * scale / max(len(xs), 1)

def first_or(xs: list, d=None):
    if d is None:
        return xs[0]
    return xs[0] if xs else d

def nodefault_seq(xs: list, ys):
    return len(xs) + ys[0]

def nodefault_none(xs: list, k):
    return 0.0 if k else sum(xs) / len(xs)
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
    ('first', 'same', 'f(x) > x', 'falsified'),
    ('first', 'same', 'f(x) == x', 'holds'),
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
    ('first', 'str_mul', 'f(x) == f(x)', 'unknown'),
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
    ('settle', 'i_listmul', 'f(x) >= 0', 'unknown'),
    ('settle', 'i_shift', 'f(x) == 2 * x', 'falsified'),
    ('settle', 'i_index', 'f(x) >= 10', 'holds'),
    ('settle', 'i_strmul_r', 'f(x) >= 0', 'unknown'),
    ('settle', 'i_strmul_plus_float', 'f(x) == f(x)', 'unknown'),
    ('settle', 'i_bitlen', 'f(x) >= 0', 'holds'),
    ('settle', 'i_and', 'f(x) <= 1', 'falsified'),
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
    ('callers', 'shout', 'f(s) >= 0', 'unknown'),
    ('callers', 'bump', 'f(x) == x + 4.0', 'holds'),
    ('callers', 'bound', 'f(x) == f(x)', 'holds'),
    ('callers', 'K.cm', 'f(x) == f(x)', 'holds'),
    ('callers', 'K.sm', 'f(x) == f(x)', 'holds'),
    ('callers', 'inst', 'f(x) == f(x)', 'holds'),
    ('callers', 'plain_index', 'f(x) == f(x)', 'holds'),
    ('magnitude', 'mag_int_ann', 'abs(f(x)) <= 1000', 'holds'),
    ('magnitude', 'mag_int_ann', 'abs(f(x)) <= 100000', 'holds'),
    ('magnitude', 'mag_strmul_unreached', 'abs(f(x)) <= 1000', 'falsified'),
    ('magnitude', 'mag_strmul_unreached', 'abs(f(x)) <= 100000', 'falsified'),
    ('magnitude', 'mag_strmul_unreached', 'abs(f(x)) <= 10000000', 'falsified'),
    ('r3a', 'pt_gt', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'pt_plain', 'f(x) == f(x)', 'holds'),
    ('r3a', 'lam_inner', 'f(x) == f(x)', 'holds'),
    ('r3a', 'comp_inner', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'nested_inner', 'f(x) == f(x)', 'holds'),
    ('r3a', 'reassigned_float', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'plus_zero', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'mutate_list', 'f(xs) == f(xs)', 'falsified'),
    ('r3a', 'c_raise', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'chained', 'f(x) == f(x)', 'holds'),
    ('r3a', 'chained_type', 'f(x) == f(x)', 'holds'),
    ('r3a', 'g_copy', 'f(y0) == 1.0 + y0', 'holds'),
    ('r3a', 'acc_zero', 'f(y0) == f(y0)', 'holds'),
    ('r3a', 'acc_int_zero', 'f(y0) == f(y0)', 'falsified'),
    ('r3a', 'dup_unpack', 'f(y0) == 1.0 + y0', 'holds'),
    ('r3a', 'swap_copy', 'f(y0, y1) == f(y0, y1)', 'holds'),
    ('r3a', 'for_target', 'f(y0) == 1.0 + y0', 'holds'),
    ('r3a', 'loop_rebind_after', 'f(y0) == f(y0)', 'falsified'),
    ('r3a', 'acc_flip', 'f(y0) == f(y0)', 'falsified'),
    ('r3a', 'acc_list', 'f(y0) == f(y0)', 'falsified'),
    ('r3a', 'acc_keeps', 'f(y0) == y0 + 3.0', 'holds'),
    ('r3a', 'nonlocal_copy', 'f(y0) == 1.0 + y0', 'holds'),
    ('r3a', 'walrus_copy', 'f(y0) == f(y0)', 'holds'),
    ('r3a', 'with_copy', 'f(y0) == y0 + 1.0', 'holds'),
    ('r3a', 'try_rebind', 'f(y0) == 1.0 + y0', 'holds'),
    ('r3a', 'copy_then_branch', 'f(y0, flag) == f(y0, flag)', 'holds'),
    ('r3a', 'copy_then_overwrite', 'f(y0) == 3.0', 'holds'),
    ('r3a', 'tri', 'f(x) <= 1000000', 'holds'),
    ('r3a', 'tri', 'f(x) >= 0', 'holds'),
    ('r3a', 'bl', 'f(x) <= 10', 'holds'),
    ('r3a', 'shl', 'abs(f(x)) < 4096', 'falsified'),
    ('r3a', 'listmul', 'f(x) <= 1000', 'unknown'),
    ('r3a', 'none_guard_mag', 'abs(f(x)) <= 10000000', 'falsified'),
    ('r3a', 'none_guard_mag', 'f(x) == x', 'holds'),
    ('r3a', 'none_guard_sq', 'f(x) < 1e300', 'falsified'),
    ('r3a', 'isint_guard', 'f(x) == x', 'falsified'),
    ('r3a', 'notnone_else', 'f(x) == 2 * x', 'falsified'),
    ('r3a', 'lit_index', 'f(x) == f(x)', 'holds'),
    ('r3a', 'mix_cont', 'f(xs, flag) == f(xs, flag)', 'falsified'),
    ('r3a', 'tup_sum', 'f(xs) == f(xs)', 'holds'),
    ('r3a', 'shape_and_len', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'shape_and_idx', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'shape_copy', 'f(x) >= 0', 'unknown'),
    ('r3a', 'ndim_only', 'f(x) >= 0', 'unknown'),
    ('r3a', 'lam_a', 'f(x) > x', 'falsified'),
    ('r3a', 'lam_b', 'f(x) == f(x)', 'holds'),
    ('r3a', 'twins[0]', 'f(x) > x', 'falsified'),
    ('r3a', 'twins[1]', 'f(x) > x', 'falsified'),
    ('r3a', 'cont', 'f(x) == f(x)', 'holds'),
    ('r3a', 'nest_same', 'f(x) == f(x)', 'holds'),
    ('r3a', 'outer_only', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'sub_inst', 'f(x) == f(x)', 'holds'),
    ('r3a', 'late_inst', 'f(x) > x', 'falsified'),
    ('r3a', 'static_inst', 'f(x) == f(x)', 'holds'),
    ('r3a', 'first_float', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'upper_int', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'cmp_and_idx', 'f(x) == f(x)', 'falsified'),
    ('r3a', 'ann_list_numeric', 'f(x) == f(x)', 'falsified'),
    ('r3b', 'bl_ann', 'f(x) <= 10', 'holds'),
    ('r3b', 'tri_ann', 'f(x) <= 1000000', 'holds'),
    ('r3b', 'ident_int_ann', 'abs(f(x)) <= 100000', 'holds'),
    ('r3b', 'bl', 'f(x) <= 10', 'holds'),
    ('r3b', 'tri', 'f(x) <= 1000000', 'holds'),
    ('r3b', 'pick', 'f(xs, k) == f(xs, k)', 'holds'),
    ('r3b', 'pick', 'f(xs) == f(xs)', 'holds'),
    ('r3b', 'mean_k', 'f(xs, k) == f(xs, k)', 'holds'),
    ('r3b', 'mean_req', 'f(xs, k) == f(xs, k)', 'holds'),
    ('r3b', 'mean_req_noev', 'f(xs, k) == f(xs, k)', 'holds'),
    ('r3b', 'mutdef', 'f(xs, acc) == f(xs, acc)', 'holds'),
    ('r3b', 'mutdef', 'f(xs) >= 1', 'falsified'),
    ('r3b', 'kwonly', 'f(xs, k=k) == f(xs, k=k)', 'holds'),
    ('r3b', 'kwonly_req', 'f(xs, k=k) == f(xs, k=k)', 'holds'),
    ('r3b', 'star_args', 'f(xs) == f(xs)', 'holds'),
    ('r3b', 'star_kw', 'f(xs) == f(xs)', 'holds'),
    ('r3b', 'dflt_float', 'f(xs, k) == f(xs, k)', 'holds'),
    ('r3b', 'same2[0]', 'f(x) == x', 'holds'),
    ('r3b', 'two_seq[0]', 'f(x) == f(x)', 'holds'),
    ('r3b', 'typo', 'for x in R, f(x) >= x', 'falsified'),
    ('r3b', 'typo', 'is_language_defined(f)', 'unknown'),
    ('r3b', 'sq', 'for x in R, f(x) >= 0', 'falsified'),
    ('r3b', 'sq', 'is_language_defined(f)', 'unknown'),
    ('r3b', 'half', 'for x in Z, f(x) <= x', 'falsified'),
    ('r3b', 'half', 'for x in R, 2 * f(x) == x', 'holds'),
    ('r3b', 'first', 'for xs in R^3, f(xs) == xs[0]', 'holds'),
    ('r3b', 'first', 'is_language_defined(f)', 'skipped'),
    ('r3b', 'strmul', 'for x in Z, f(x) == f(x)', 'holds'),
    ('r3b', 'strmul', 'for x in R, f(x) == f(x)', 'falsified'),
    ('r3b', 'strmul', 'is_language_defined(f)', 'unknown'),
    ('r3b', 'guarded', 'for x in R, abs(f(x)) <= 10000000', 'falsified'),
    ('r3b', 'guarded', 'is_language_defined(f)', 'unknown'),
    ('r3b', 'pick', 'is_language_defined(f)', 'unknown'),
    ('r3b', 'tri', 'is_language_defined(f)', 'unknown'),
    ('r3b', 'tri', 'for x in N, f(x) <= 1000000', 'holds'),
    ('r3c', 'acc_wrap', 'f(y0) == y0', 'holds'),
    ('r3c', 'acc_str', 'f(y0) == f(y0)', 'holds'),
    ('r3c', 'acc_aug', 'f(y0) == f(y0)', 'holds'),
    ('r3c', 'acc_num_ok', 'f(y0) == 4 * y0', 'holds'),
    ('r3c', 'pair_u[1]', 'f(x) > x', 'falsified'),
    ('r3c', 'pair_u[2]', 'f(x) == f(x)', 'holds'),
    ('r3c', 'Holder.lam[0]', 'f(x) > x', 'falsified'),
    ('r3c', 'Holder.lam[1]', 'f(x) == f(x)', 'holds'),
    ('r3c', 'eq_none', 'f(x) < 1e300', 'falsified'),
    ('r3c', 'ifexp_none', 'f(x) < 1e300', 'falsified'),
    ('r3c', 'raise_guard', 'f(x) < 1e300', 'falsified'),
    ('r3d', 'closure_copy', 'f(y0) == f(y0)', 'holds'),
    ('r3d', 'comp_copy', 'f(y0) == f(y0)', 'falsified'),
    ('r3d', 'nested_def_copy', 'f(y0) == 2 * y0', 'holds'),
    ('r3d', 'gen_copy', 'f(y0) == f(y0)', 'holds'),
    ('r3f', 'multi[0]', 'f(x) > x', 'falsified'),
    ('r3f', 'multi2[0]', 'f(x) == f(x)', 'holds'),
    ('r3g', 'dis_copy', 'f(y0) == f(y0)', 'unknown'),
    ('r3g', 'dis_default', 'f(x) == f(x)', 'holds'),
    ('r3g', 'dis_ann', 'f(x) == f(x)', 'holds'),
    ('r3g', 'dis_three', 'f(x) == f(x)', 'unknown'),
    ('r3h', 'loud', 'f(s) >= 0', 'unknown'),
    ('r3h', 'ident_shift', 'abs(f(x)) <= 1000', 'falsified'),
    ('r3h', 'ident_shift', 'abs(f(x)) <= 999', 'falsified'),
    ('r3h', 'ident_shift', 'f(x) >= -1000', 'falsified'),
    ('r3h', 'sum_upto', 'f(x) <= 499500', 'holds'),
    ('own', 'keyed_by', 'f(key) == 1', 'holds'),
    ('own', 'matched', 'f(y0) == y0 + 1.0', 'holds'),
    ('own', 'defined', 'f(y0) == y0 + 1.0', 'holds'),
    ('own', 'text_or_mapping', 'f(x) == f(x)', 'unknown'),
    ('own', 'repeat', 'f(x) == f(x)', 'unknown'),
    ('own', 'rows', 'f(x) >= 0', 'unknown'),
    ('own', 'picker', 'f(x) == f(x)', 'holds'),
]


# Python 3.10 records no column of the operation that raised, so where
# one line holds several operations a raise on a drawn value is a draw
# defect there rather than a finding; and a static `__call__` is not read
# as callable. Each entry says less than 3.11 does, never more.
BEFORE_3_11 = {
    ('settle', 's_len_and_gt', 'f(x) >= 0'): 'unknown',
    ('settle', 'r_list_default', 'f(axes) >= 1'): 'unknown',
    ('r3a', 'cmp_and_idx', 'f(x) == f(x)'): 'unknown',
    ('r3a', 'static_inst', 'f(x) == f(x)'): 'skipped:misspecified',
}


@pytest.mark.parametrize("module, function, text, verdict", CASES)
def test_each_case_keeps_its_verdict(modules, module, function, text, verdict):
    if sys.version_info < (3, 11):
        verdict = BEFORE_3_11.get((module, function, text), verdict)
    fn = eval(function, vars(modules[module]))
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    assert p.verdict == verdict, (p.verdict, p.note, p.counterexample)


@pytest.mark.parametrize("function, verdict", [("pick", "holds"), ("mean_k", "falsified")])
def test_the_empty_input_rows_keep_their_verdict(modules, function, verdict):
    import mathema
    fn = getattr(modules["r3e"], function)
    rows = [p.verdict for p in mathema.check(fn).probes
            if p.name.startswith("is_empty_safe")]
    assert rows and verdict in rows, rows
    if verdict == "holds":
        assert set(rows) == {"holds"}, rows
