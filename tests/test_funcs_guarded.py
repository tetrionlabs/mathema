# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A guard-carrying bound function (funcs=) no longer disqualifies the
claim: the branch is its partiality contract, so the value path lifts
conditioned on the guards, and the guards gate the claim exactly as
f's own raise regions do. The corpus's blast radius: every CDF and
survival function, orbital pairs, rate-constant pairs."""
import math

from mathema.claims import check_conjectures, claim


def survival(x, lam):
    if lam <= 0:
        raise ValueError("rate must be positive")
    return math.exp(-lam * x)


def test_guarded_bound_function_lifts_and_the_pair_identity_proves():
    def cdf(x, lam):
        if lam <= 0:
            raise ValueError("rate must be positive")
        return 1.0 - math.exp(-lam * x)
    (p,) = check_conjectures(cdf, [claim(
        "for x in [0,10], lam in [0.1,5], f(x,lam) + g(x,lam) == 1",
        funcs={"g": survival}, route="derive")])
    assert p.verdict == "proven"


def test_orbital_pair_identity_proves_through_the_shared_guard():
    def apoapsis(a, e):
        if a <= 0:
            raise ValueError("semi-major axis")
        return a * (1 + e)

    def periapsis(a, e):
        if a <= 0:
            raise ValueError("semi-major axis")
        return a * (1 - e)
    (p,) = check_conjectures(apoapsis, [claim(
        "for a in [0.5,10], e in [0,0.9], f(a,e) + g(a,e) == 2*a",
        funcs={"g": periapsis}, route="derive")])
    assert p.verdict == "proven"


def test_a_reachable_guard_still_gates_the_claim():
    def plain(x, lam):
        return 1.0 - math.exp(-lam * x)
    # lam reaches the guard region: the claim must not prove, and the
    # raise inside the domain falsifies pedantically
    (p,) = check_conjectures(plain, [claim(
        "for x in [0,10], lam in [-1,5], f(x,lam) + g(x,lam) == 1",
        funcs={"g": survival}, route="derive")])
    assert p.verdict == "falsified"


def _mod(tmp_path, body, name):
    import importlib
    import sys
    import textwrap
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module(name)
        importlib.reload(mod)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


_PIPE = """
import math

def reynolds(rho: float, v: float, diameter: float, mu: float) -> float:
    if mu <= 0:
        raise ValueError("viscosity must be positive")
    return rho * v * diameter / mu

def blasius_f(re: float) -> float:
    if re <= 0:
        raise ValueError("re must be positive")
    return 0.316 * re ** -0.25

def drop(rho: float, v: float, diameter: float, mu: float) -> float:
    re = rho * v * diameter / mu
    f = 0.316 * re ** -0.25
    return f * rho * v ** 2 / (2 * diameter)
"""


def test_nested_guarded_composition_proves(tmp_path):
    # the "a funcs=-bound function must be unconditionally guard-free"
    # restriction is gone: a guarded bound function lifts as its full
    # piecewise (valid at ANY argument), so a multi-variable argument
    # g(rho, v, diameter, mu) and a nested h(g(...)) both compose
    mod = _mod(tmp_path, _PIPE, "fgp_a")
    (p,) = check_conjectures(mod.drop, [claim(
        "for rho in [500,2000], v in [10,50], diameter in [0.5,2], "
        "mu in [1e-6,1e-5], f(rho,v,diameter,mu) == "
        "h(g(rho,v,diameter,mu)) * rho*v**2/(2*diameter)",
        funcs={"g": mod.reynolds, "h": mod.blasius_f}, route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_derivative_through_nested_guarded_composition_proves(tmp_path):
    # the stacked gap: a d(...) claim through two independently-guarded
    # bound functions, previously unliftable with zero probe fallback
    mod = _mod(tmp_path, _PIPE, "fgp_b")
    (p,) = check_conjectures(mod.drop, [claim(
        "for rho in [500,2000], v in [10,50], diameter in [0.5,2], "
        "mu in [1e-6,1e-5], d(h(g(rho,v,diameter,mu)), v) <= 0",
        funcs={"g": mod.reynolds, "h": mod.blasius_f}, route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_bound_functions_reachable_guard_still_falsifies(tmp_path):
    # pedantic and corroborated: mu straddling zero makes the bound
    # reynolds raise inside the declared domain; the claim has no
    # value there
    mod = _mod(tmp_path, _PIPE, "fgp_c")
    (p,) = check_conjectures(mod.drop, [claim(
        "for rho in [500,2000], v in [10,50], diameter in [0.5,2], "
        "mu in [-1,1], f(rho,v,diameter,mu) == "
        "h(g(rho,v,diameter,mu)) * rho*v**2/(2*diameter)",
        funcs={"g": mod.reynolds, "h": mod.blasius_f}, route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_sum_wraps_a_loop_lifted_bound_function(tmp_path):
    # a branch-free scalar loop closes to a plain expression for the
    # funcs= binding, so Sum(g(j), ...) in the claim text composes,
    # literal and symbolic upper bounds alike
    mod = _mod(tmp_path, """
def triangular(n: int) -> float:
    total = 0.0
    for i in range(n):
        total += i + 1
    return total

def outer(n: int) -> float:
    return float(n)
""", "fgp_d")
    (p,) = check_conjectures(mod.outer, [claim(
        "Sum(g(j), j, 1, 4) == 20", funcs={"g": mod.triangular},
        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    (p,) = check_conjectures(mod.outer, [claim(
        "for n in [1,10] subset Z, Sum(g(j), j, 1, n) == n*(n+1)*(n+2)/6",
        funcs={"g": mod.triangular}, route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
