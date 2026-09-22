# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Value branches around loops: the piecewise lifter's leaf regions
close whole loop bodies through the sum machinery, so a function mixing
guards, early returns, and range-based accumulator loops lifts as one
ordered Piecewise, provable branch-by-branch, sign-decidable across
the whole domain via nlsat's ite reading, and pedantic about raise
regions. The design's declines are pinned as firmly as its proofs:
loop-then-branch regions, in-branch further branching around a loop,
sequence parameters, and non-returning arms all stay honestly out."""
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
def shipping(n: int, rate: float) -> float:
    if rate < 0:
        raise ValueError("rate must be nonnegative")
    if n <= 0:
        return 0.0
    total = 0.0
    for i in range(n):
        total += rate * (i + 1)
    return total


def pick_loop(n: int, mode: float) -> float:
    if mode > 0:
        a = 0.0
        for k in range(n):
            a += k
        return a
    b = 0.0
    for k in range(n):
        b += k * k
    return b


def loop_in_else(n: int, flag: float) -> float:
    if flag >= 1:
        return 100.0
    acc = 0.0
    for j in range(n):
        acc += 2.0
    return acc


def local_feeds_leaf(n: int, base: float) -> float:
    scale = base * 2.0
    if n <= 0:
        return scale
    total = 0.0
    for i in range(n):
        total += scale
    return total


def epilogue_leaf(n: int, w: float, face: float) -> float:
    if n <= 0:
        return face
    price = 0.0
    for i in range(n):
        price += w * i
    price += face
    return price


def elif_chain(n: int, m: float) -> float:
    if m > 10:
        return 1.0
    if m > 0:
        s = 0.0
        for k in range(n):
            s += k
        return s
    return -1.0


def loop_then_branch(n: int, t: float) -> float:
    total = 0.0
    for i in range(n):
        total += i
    if t > 0:
        return total
    return -total


def branch_in_loop_branch(n: int, u: float) -> float:
    if u > 0:
        total = 0.0
        for i in range(n):
            if i > 2:
                total += i
        return total
    return 0.0


def seq_branchy(xs: list, pick: float) -> float:
    if pick > 0:
        total = 0.0
        for v in xs:
            total += v
        return total
    return 0.0


def unpack_in_leaf(n: int, theta: float) -> float:
    import math
    if n <= 0:
        return 1.0
    ax, ay = math.cos(theta), math.sin(theta)
    s = 0.0
    for i in range(n):
        s += ax * ax + ay * ay
    return s
"""


def _run(mod_fn, law, extensive=False):
    (p,) = check_conjectures(mod_fn, [claim(law, route="derive")],
                             extensive=extensive)
    return p


# --- proofs -----------------------------------------------------------------

def test_guard_plus_early_return_plus_loop_proves_both_sides(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_a")
    p = _run(mod.shipping,
             "for n in [1,20], rate in [0,5], f(n,rate) == rate*n*(n+1)/2")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _run(mod.shipping,
             "for n in [-5,0], rate in [0,5], f(n,rate) == 0")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_whole_domain_sign_proves_via_nlsat(tmp_path):
    import pytest
    pytest.importorskip("z3")
    mod = _mod(tmp_path, _BODY, "bl_b")
    p = _run(mod.shipping,
             "for n in [-5,20], rate in [0,5], f(n,rate) >= 0",
             extensive=True)
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "nlsat" in (p.sketch or "")


def test_branch_selects_between_two_loops(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_c")
    p = _run(mod.pick_loop,
             "for n in [1,20], mode in [1,5], f(n,mode) == n*(n-1)/2")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _run(mod.pick_loop,
             "for n in [1,20], mode in [-5,-1], "
             "f(n,mode) == n*(n-1)*(2*n-1)/6")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_loop_in_the_fallthrough_arm(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_d")
    p = _run(mod.loop_in_else,
             "for n in [0,30], flag in [-5,0], f(n,flag) == 2*n")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _run(mod.loop_in_else,
             "for n in [0,30], flag in [1,5], f(n,flag) == 100")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_path_local_feeds_the_loop_leaf(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_e")
    p = _run(mod.local_feeds_leaf,
             "for n in [1,15], base in [0,5], f(n,base) == 2*base*n")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_leaf_with_epilogue_statement(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_f")
    p = _run(mod.epilogue_leaf,
             "for n in [1,10], w in [0,5], face in [50,100], "
             "f(n,w,face) == w*n*(n-1)/2 + face")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    # the geometric-series leaf is a known nicety: sympy's summation
    # closed form carries a ratio-equality artifact branch, so the
    # claim honestly HOLDS rather than proving, pinned so an upgrade
    # flips deliberately
    (p,) = check_conjectures(_mod(tmp_path, """
def geometric(n: int, y: float, face: float) -> float:
    if n <= 0:
        return face
    price = 0.0
    for i in range(n):
        price += 1.0 / (1 + y) ** (i + 1)
    price += face / (1 + y) ** n
    return price
""", "bl_f2").geometric, [claim(
        "for n in [1,10], y in [0.01,0.2], face in [50,100], "
        "f(n,y,face) == (1 - (1+y)**(-n))/y + face*(1+y)**(-n)",
        route="derive")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note)


def test_elif_chain_around_a_loop(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_g")
    p = _run(mod.elif_chain,
             "for n in [1,20], m in [1,10], f(n,m) == n*(n-1)/2")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _run(mod.elif_chain,
             "for n in [1,20], m in [-5,0], f(n,m) == -1")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_tuple_unpack_normalizes_inside_a_leaf(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_h")
    p = _run(mod.unpack_in_leaf,
             "for n in [1,10], theta in [0,6], f(n,theta) == n")
    assert p.verdict == "proven", (p.verdict, p.sketch)


# --- pedantic raise handling ------------------------------------------------

def test_reachable_raise_region_falsifies(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_i")
    p = _run(mod.shipping,
             "for n in [1,5], rate in [-1,5], f(n,rate) >= 0")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_avoided_raise_region_still_proves(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_j")
    p = _run(mod.shipping,
             "for n in [1,10], rate in [0.5,5], f(n,rate) > 0")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)


# --- designed declines, pinned ----------------------------------------------

def test_loop_then_branch_proves(tmp_path):
    # the loop closes into the environment and its value flows through
    # the branches that follow, both sides prove
    mod = _mod(tmp_path, _BODY, "bl_k")
    p = _run(mod.loop_then_branch,
             "for n in [1,10], t in [1,5], f(n,t) == n*(n-1)/2")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _run(mod.loop_then_branch,
             "for n in [1,10], t in [-5,-1], f(n,t) == -n*(n-1)/2")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_conditional_update_inside_a_branch_leaf_lifts_exactly(tmp_path):
    # a loop with an in-loop conditional update, sitting under an
    # outer value branch: the in-loop If belongs to the loop closer
    # (an exact Piecewise summand), the outer If to the walk. The
    # lift keeps the summand's condition INSIDE the Sum (a
    # piecewise_fold across a Sum once leaked the bound dummy into a
    # top-level arm condition); adjudication is holds-level until the
    # conditional summand collapses to closed form.
    from mathema import analyze
    from mathema.symbolic._conditioned import lift_piecewise
    mod = _mod(tmp_path, _BODY, "bl_l")
    pw = lift_piecewise(mod.branch_in_loop_branch,
                        analyze(mod.branch_in_loop_branch))
    assert pw is not None and pw.kind == "value"
    for arm_value, arm_cond in pw.expr.args:
        assert not ({s for s in arm_cond.free_symbols}
                    - set(pw.params.values())), (
            "a Sum dummy leaked into a top-level arm condition", pw.expr)
    p = _run(mod.branch_in_loop_branch,
             "for n in [1,10] subset Z, u in [1,5], f(n,u) >= 0")
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note)


def test_sequence_parameters_stay_out_of_this_slice(tmp_path):
    mod = _mod(tmp_path, _BODY, "bl_m")
    p = _run(mod.seq_branchy, "for pick in [1,5], f(xs, pick) >= 0")
    assert p.verdict != "proven"


# --- the lift itself, inspected ---------------------------------------------

def test_the_lift_is_one_ordered_piecewise(tmp_path):
    import sympy

    from mathema import analyze
    from mathema.symbolic._conditioned import lift_piecewise
    mod = _mod(tmp_path, _BODY, "bl_n")
    pw = lift_piecewise(mod.shipping, analyze(mod.shipping))
    assert pw is not None and pw.kind == "value"
    assert isinstance(pw.expr, sympy.Piecewise) or pw.expr.has(sympy.Piecewise)
    # the raise region rides as a guard, not a Piecewise arm
    assert pw.raise_guards and any(name == "ValueError"
                                   for _c, name in pw.raise_guards)
