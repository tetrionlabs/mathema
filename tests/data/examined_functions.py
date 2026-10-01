# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions whose effects the examine route reads from their source."""
import logging
import math
import os
import random
import socket
import sys
import time

import numpy as np
# a logger of its own, reaching no handler
log = logging.Logger("ex.audit")
_TABLE = {"a": 1}
_COUNT = [0]
def pure(x: float) -> float:
    return 2 * math.sqrt(abs(x)) + max(x, 0.0)
def alias_append(xs: list) -> float:
    ys = xs
    ys.append(1.0)
    return float(len(xs))
def env_alias(x: float) -> float:
    e = os.environ
    e["MODE"] = "fast"
    return x
def env_read(x: float) -> float:
    return x * float(os.environ.get("S", "1"))
def iadd(xs: list) -> list:
    xs += [1]
    return xs
def local_import(x: float) -> float:
    import os as o
    o.environ["Z"] = "1"
    return x
def path_alias(x: float) -> float:
    p = sys.path
    p.append("/x")
    return x
def rand_alias(x: float) -> float:
    r = random
    return x + r.random()
def shuffles(xs: list) -> list:
    random.shuffle(xs)
    return xs
def helper_writes(x: float) -> float:
    return _bump(x)
def _bump(x):
    _COUNT[0] += 1
    return x
def clock(x: float) -> float:
    return x + time.time() * 0
def npdraw(x: float) -> float:
    return x + np.random.rand()
def dotted(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b)
def nplin(a: np.ndarray) -> float:
    return float(np.linalg.norm(a))
def logs(x: float) -> float:
    log.info("x %s", x)
    return x
def table(x: float) -> float:
    return x * _TABLE["a"]
def dyn(x: float) -> float:
    return getattr(math, "sqrt")(x)
def sorts(xs: list) -> float:
    xs.sort()
    return xs[0]
def sorted_copy(xs: list) -> float:
    return sorted(xs)[0]
def chdir(x: float) -> float:
    os.chdir("/")
    return x
def gen(mu: float, rng: np.random.Generator) -> float:
    return mu + rng.standard_normal()
def recursive(n: int) -> int:
    return 1 if n <= 1 else n * recursive(n - 1)
def ufunc_out(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    np.add(a, 1, out=b)
    return b
def dead_branch(x: float) -> float:
    if x > 10:
        os.environ["Q"] = "1"
    return x
def prints(x: float) -> float:
    print(x)
    return x
def explodes(x: float) -> float:
    raise RuntimeError("executed")
def hostname(x: float) -> float:
    return x + len(socket.gethostname())
def _bump_int(n):
    _COUNT[0] += 1
    return n
def counted(n: int) -> int:
    return _bump_int(n)
def dead_else(x: float) -> float:
    if x < 10:
        return x
    else:
        _COUNT[0] += 1
    return x
