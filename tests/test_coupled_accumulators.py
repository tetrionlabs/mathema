# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two linearly coupled accumulators close by the matrix power: the
iterative Fibonacci pair proves its own Binet form; nonlinear
coupling, parameter coefficients, and non-diagonalizable updates
decline rather than guess; and claim text may wrap the lifted
function in Sum(...) with symbolic bounds."""
import textwrap

from mathema.conjecture import check_conjectures, claim


def _mod(tmp_path, body, name):
    import importlib
    import sys
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module(name)
        importlib.reload(mod)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


_BODY = """
def fib(n: int) -> float:
    a = 0.0
    b = 1.0
    for _ in range(n):
        a, b = b, a + b
    return a


def nonlinear_pair(n: int) -> float:
    import math
    total = 0.0
    x = 1.0
    for _ in range(n):
        total, x = total + x, math.log(math.exp(x) - x + 1.0)
    return total


def plain_fold(n: int, j: int) -> int:
    total = 0
    for k in range(j + 1):
        total += n
    return total
"""


def test_fibonacci_pair_proves_binet(tmp_path):
    mod = _mod(tmp_path, _BODY, "coup_a")
    (p,) = check_conjectures(mod.fib, [claim(
        "for n in [0,20], f(n) == "
        "(((1+sqrt(5))/2)^n - ((1-sqrt(5))/2)^n)/sqrt(5)",
        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_nonlinear_coupling_stays_honestly_out(tmp_path):
    mod = _mod(tmp_path, _BODY, "coup_b")
    (p,) = check_conjectures(mod.nonlinear_pair, [claim(
        "for n in [0,10], f(n) >= 0", route="derive")])
    assert p.verdict != "proven"


def test_sum_over_the_lifted_function_in_claim_text(tmp_path):
    mod = _mod(tmp_path, _BODY, "coup_c")
    (p,) = check_conjectures(mod.plain_fold, [claim(
        "Sum(f(4, j), j, 0, 4) == 60", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    (p,) = check_conjectures(mod.plain_fold, [claim(
        "for n in [1,9], Sum(f(n, j), j, 0, 4) == 15*n", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
