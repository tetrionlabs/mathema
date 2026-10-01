# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Second examine attack: w_ write shared state, r_ read hidden input or
order, p_ are pure and deterministic. Examined, never called."""
import asyncio
import copy
import functools
import json
import random
import threading

import numpy as np

from examine_attacks2_helper import Acc

_G = []


def _counting(fn):
    def wrapper(*a, **k):
        _G.append(1)
        return fn(*a, **k)
    return wrapper


def _plain(x: float) -> float:
    return x


# decorator applied by assignment
w_assign_decorated = _counting(_plain)


def w_dict_values(d: dict) -> float:
    for v in d.values():
        v.append(1.0)
    return 0.0
def w_dict_values_list(d: dict) -> float:
    vs = list(d.values())
    vs[0].append(1.0)
    return 0.0
def w_list_copy_elem(xs: list) -> float:
    ys = list(xs)
    ys[0].append(1.0)
    return 0.0
def w_shallow_copy_elem(xs: list) -> float:
    ys = copy.copy(xs)
    ys[0].append(1.0)
    return 0.0
def w_sorted_elem(xs: list) -> float:
    sorted(xs)[0].append(1.0)
    return 0.0
def w_setdefault(d: dict) -> float:
    d.setdefault("k", []).append(1.0)
    return 0.0
def w_get_elem(d: dict) -> float:
    d.get("k").append(1.0)
    return 0.0
def w_asarray_reshape(a: np.ndarray) -> float:
    b = np.asarray(a).reshape(-1)
    b[0] = 0.0
    return 0.0
def w_row_iadd(a: np.ndarray) -> float:
    for row in a:
        row *= 2.0
    return 0.0
def w_row_setitem(a: np.ndarray) -> float:
    for row in a:
        row[0] = 0.0
    return 0.0
def w_slice_view_iadd(a: np.ndarray) -> float:
    a[1:] += 1.0
    return 0.0
def w_slice_name_iadd(a: np.ndarray) -> float:
    b = a[1:]
    b += 1.0
    return 0.0
def w_method_self_param(c: Acc, x: float) -> float:
    return c.bump(x)
def w_fresh_method_global(x: float) -> float:
    c = Acc()
    return c.leak(x)
def w_fresh_method_argwrite(xs: list) -> float:
    c = Acc()
    return c.absorb(xs)
def w_property_setter(x: float) -> float:
    c = Acc()
    c.prop = x
    return x
def w_property_setter_param(c: Acc, x: float) -> float:
    c.prop = x
    return x
def w_iadd_param(c: Acc, x: float) -> float:
    c += x
    return 0.0
def w_iadd_fresh(x: float) -> float:
    c = Acc()
    c += x
    return 0.0
def w_gen_expr_closure(xs: list) -> float:
    g = (xs.append(i) for i in range(2))
    list(g)
    return 0.0
def w_gen_fn_closure(xs: list) -> float:
    def gen():
        xs.append(1.0)
        yield 1.0
    return sum(gen())
def w_thread(x: float) -> float:
    t = threading.Thread(target=_G.append, args=(x,))
    t.start()
    t.join()
    return x
def w_asyncio(x: float) -> float:
    async def co():
        _G.append(x)
    asyncio.run(co())
    return x
def w_json_dump(obj: dict, fp) -> float:
    json.dump(obj, fp)
    return 0.0
def w_local_fn_argwrite(xs: list) -> float:
    def g(v):
        v.append(1.0)
    g(xs)
    return 0.0
@functools.lru_cache(maxsize=None)
def w_lru(x: float) -> float:
    _G.append(x)
    return x
def w_reduce_lambda(xs: list, out: list) -> float:
    functools.reduce(lambda acc, v: acc.append(v) or acc, xs, out)
    return 0.0

def r_random_none(x: float) -> float:
    return random.Random(None).random() + x
def r_default_rng_none(x: float) -> float:
    return np.random.default_rng(seed=None).random() + x
def r_default_rng_none_pos(x: float) -> float:
    return np.random.default_rng(None).random() + x
def r_generator_pcg(x: float) -> float:
    return np.random.Generator(np.random.PCG64()).random() + x
def r_set_from_list(xs: list[str]) -> str:
    return ",".join(set(xs))
def r_set_from_list_for(xs: list[str]) -> str:
    out = ""
    for s in set(xs):
        out += s
    return out
def r_str_of_set(x: float) -> str:
    return str({"alpha", "beta", "gamma"})
def r_fstring_set(x: float) -> str:
    return f"{ {'alpha', 'beta'} }"
def r_set_union(a: set[str], b: set[str]) -> list:
    return list(a | b)
def r_thread_race(x: float) -> float:
    out = []
    ts = [threading.Thread(target=out.append, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return float(out[0])
def r_lru_shared(x: float) -> list:
    return _cached_list(x)
@functools.lru_cache(maxsize=None)
def _cached_list(x):
    return [x]

def p_slice_copy_append(xs: list) -> list:
    ys = xs[:]
    ys.append(1.0)
    return ys
def p_list_copy_append(xs: list) -> list:
    ys = list(xs)
    ys.append(1.0)
    return ys
def p_copy_slice_extend(xs: list) -> float:
    xs[1:].extend([1.0])
    return 0.0
def p_np_copy_reshape(a: np.ndarray) -> float:
    b = a.copy().reshape(-1)
    b[0] = 0.0
    return float(b.sum())
def p_np_add_then_write(a: np.ndarray) -> float:
    b = a + 1.0
    b[0] = 0.0
    return float(b.sum())
def p_loop_float_iadd(xs: list) -> float:
    t = 0.0
    for v in xs:
        v += 1.0
        t += v
    return t
def p_fresh_rows(n: int) -> float:
    rows = [[] for _ in range(3)]
    for r in rows:
        r.append(n)
    return float(len(rows))
def p_sorted_set(xs: list[str]) -> str:
    return ",".join(sorted(set(xs)))
def p_local_lambda(xs: list) -> list:
    return list(map(lambda v: v * 2.0, xs))
def p_helper_returns_fresh(xs: list) -> list:
    ys = _fresh_copy(xs)
    ys.append(1.0)
    return ys
def _fresh_copy(xs):
    return [v for v in xs]
def p_seeded_random(x: float) -> float:
    return random.Random(42).random() + x
def p_dict_comprehension(d: dict) -> dict:
    return {k: v * 2.0 for k, v in d.items()}
def p_set_floats_iter(xs: list) -> float:
    return sum(set(xs))
def p_tuple_swap(a: float, b: float) -> float:
    a, b = b, a
    return a - b
def p_np_sum(a: np.ndarray) -> float:
    return float(np.sum(a))
