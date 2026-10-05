# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions with effects the examine route must see, and pure ones it must not flag.
Each is examined from its source and never called by the audit."""
import contextlib
import functools
import operator
import os
import random
import uuid
from random import random as rnd
from time import time as now
from os import getenv

import numpy as np
import pandas as pd

from examine_attack_helper import bump, same

_COUNT = [0]
_ENV = os.environ
_G = 0


class Counter:
    n = 0


@contextlib.contextmanager
def _ctx(v):
    yield v


def _globals():
    return globals()


def _counting(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        _COUNT[0] += 1
        return fn(*a, **k)
    return wrapper


def _gen():
    _COUNT.append(1)
    yield 1


# writes the examine route must see
def w_dict_alias(xs: list) -> float:
    d = {"k": xs}
    d["k"].append(1.0)
    return 0.0
def w_tuple_unpack(xs: list) -> float:
    a, b = xs, 1
    a.append(1.0)
    return float(b)
def w_closure(xs: list) -> float:
    def inner():
        xs.append(1.0)
    inner()
    return 0.0
def w_default_mutable(x: float, cache=[]) -> float:
    cache.append(x)
    return x
def w_globals_helper(x: float) -> float:
    _globals()["_G"] = x
    return x
def w_class_attr(x: float) -> float:
    Counter.n += 1
    return x
def w_other_module(x: float) -> float:
    return bump(x)
@_counting
def w_decorated(x: float) -> float:
    return x
def w_comprehension(xs: list) -> float:
    [xs.append(i) for i in range(2)]
    return 0.0
def w_with_alias(xs: list) -> float:
    with _ctx(xs) as y:
        y.append(1.0)
    return 0.0
def w_generator(x: float) -> float:
    return x + sum(_gen())
def w_partial(xs: list) -> float:
    p = functools.partial(list.append, xs)
    p(1.0)
    return 0.0
def w_map_lambda(xs: list) -> float:
    list(map(lambda v: xs.append(v), [1.0]))
    return 0.0
def w_np_view(a: np.ndarray) -> float:
    v = a[1:]
    v[0] = 5.0
    return 0.0
def w_np_slice_assign(a: np.ndarray) -> float:
    a[:] = 0.0
    return 0.0
def w_np_imul(a: np.ndarray) -> float:
    a *= 2.0
    return 0.0
def w_np_fill(a: np.ndarray) -> float:
    a.fill(0.0)
    return 0.0
def w_np_reshape_view(a: np.ndarray) -> float:
    b = a.reshape(-1)
    b[0] = 1.0
    return 0.0
def w_np_asarray(a: np.ndarray) -> float:
    b = np.asarray(a)
    b[0] = 1.0
    return 0.0
def w_np_ravel(a: np.ndarray) -> float:
    np.ravel(a)[0] = 1.0
    return 0.0
def w_ndarray_sort(a: np.ndarray) -> float:
    a.sort()
    return 0.0
def w_pd_inplace(df: pd.DataFrame) -> float:
    df.fillna(0.0, inplace=True)
    return 0.0
def w_pd_column_assign(df: pd.DataFrame) -> float:
    df["y"] = 1.0
    return 0.0
def w_pd_loc(df: pd.DataFrame) -> float:
    df.loc[0, "x"] = 1.0
    return 0.0
def w_setattr_local(obj: object) -> float:
    s = setattr
    s(obj, "a", 1)
    return 0.0
def w_environ_alias(x: float) -> float:
    _ENV["AUDIT_X"] = "1"
    return x
def w_environ_update(x: float) -> float:
    os.environ.update({"AUDIT_Y": "1"})
    return x
def w_random_from_import(x: float) -> float:
    return x + rnd()
def w_operator_setitem(xs: list) -> float:
    operator.setitem(xs, 0, 1.0)
    return 0.0
def w_return_alias(xs: list) -> float:
    y = same(xs)
    y.append(1.0)
    return 0.0
def w_walrus(xs: list) -> float:
    (y := xs).append(1.0)
    return float(len(y))
def w_for_alias(xs: list) -> float:
    for y in [xs]:
        y.append(1.0)
    return 0.0
def w_global_stmt(x: float) -> float:
    global _G
    _G = x
    return x
def w_method_alias(xs: list) -> float:
    srt = xs.sort
    srt()
    return 0.0
def w_dunder_setitem(xs: list) -> float:
    xs.__setitem__(0, 1.0)
    return 0.0
def w_slice_assign(xs: list) -> float:
    xs[:] = []
    return 0.0
def w_del(xs: list) -> float:
    del xs[0]
    return 0.0
def w_cond_alias(xs: list) -> float:
    y = xs if len(xs) >= 0 else []
    y.append(1.0)
    return 0.0

# hidden reads (is_deterministic)
def r_time_from_import(x: float) -> float:
    return x + now() * 0
def r_getenv_from_import(x: float) -> float:
    return x * float(getenv("AUDIT_S", "1"))
def r_uuid(x: float) -> float:
    return x + uuid.uuid4().int * 0
def r_unseeded_rng(x: float) -> float:
    return x + np.random.default_rng().random()
def r_unseeded_random_instance(x: float) -> float:
    return x + random.Random().random()
def r_str_hash(x: float) -> float:
    return x + hash("audit") % 2
def r_set_order(x: float) -> float:
    return x + len(next(iter({"alpha", "beta", "gamma"})))
def r_matmul(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sum(np.matmul(a, b)))
def r_einsum(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.einsum("ij,jk->", a, b))
def r_solve(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sum(np.linalg.solve(a, b)))

# pure: must not be falsified
def p_local_copy(xs: list) -> float:
    ys = list(xs)
    ys.append(1.0)
    return float(len(ys))
def p_fresh_dict(x: float) -> float:
    d = {}
    d["a"] = x
    return d["a"]
def p_local_list(x: float) -> float:
    out = []
    out.append(x)
    return out[0]
def p_rebind(xs: list) -> float:
    xs = xs + [1.0]
    return float(len(xs))
def p_np_copy(a: np.ndarray) -> float:
    a = a.copy()
    a[0] = 1.0
    return float(a[0])
def p_np_array_copy(a: np.ndarray) -> float:
    b = np.array(a)
    b[0] = 1.0
    return float(b[0])
def p_np_sort_function(a: np.ndarray) -> float:
    return float(np.sort(a)[0])
def p_pd_copy(df: pd.DataFrame) -> float:
    df = df.copy()
    df["y"] = 1.0
    return 0.0
def p_nonlocal(x: float) -> float:
    total = 0.0
    def add():
        nonlocal total
        total += x
    add()
    return total
def p_seeded_rng(x: float) -> float:
    r = random.Random(0)
    return x + r.random()
def p_rebind_then_mutate(xs: list) -> float:
    xs = [1.0, 2.0]
    xs.append(3.0)
    return float(len(xs))
def p_sum_vector(a: np.ndarray) -> float:
    return float(np.sum(a))
def r_frozenset_order(x: float) -> float:
    return x + len(list(frozenset(["alpha", "beta"]))[0])
def r_set_loop(x: float) -> float:
    total = x
    for word in {"alpha", "beta"}:
        total = total * 2 + len(word)
    return total
def p_int_set_order(x: float) -> float:
    return x + next(iter({3, 1, 2}))
def p_sorted_string_set(x: float) -> float:
    return x + len(sorted({"alpha", "beta"})[0])
def w_element_of_argument(rows: list) -> float:
    for row in rows:
        row.append(1.0)
    return 0.0
def r_secrets(x: float) -> float:
    import secrets
    return x + secrets.randbelow(2) * 0
def r_system_random(x: float) -> float:
    return x + random.SystemRandom().random() * 0
