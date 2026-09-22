# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Guard reachability that cannot fabricate a counterexample: a guard
disproof requires an EXECUTED witness (the real call, run at the
point, must actually raise), a failed call-argument analysis reads as
unexcludable (undecided), never as "no guards", and genuine pedantic
falsifications still corroborate trivially. Fixtures mirror the
false-falsified family from the proof corpus (vis-viva composed with a
computed call-site argument against a scaled guard comparison)."""
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


_VIS_VIVA = """
import math

def vis_viva_speed(GM: float, r: float, a: float) -> float:
    if r <= 0:
        raise ValueError("radius must be positive")
    if a <= 0:
        raise ValueError("semi-major axis must be positive")
    if r > 2 * a:
        raise ValueError("radius cannot exceed apoapsis distance 2a")
    return math.sqrt(GM * (2 / r - 1 / a))
"""


def test_computed_argument_against_scaled_guard_never_falsifies(tmp_path):
    # the corpus's false-falsified shape: a computed multiplicative
    # call argument (r = a*(1-ecc)) meets a guard whose comparison side
    # is a scaled parameter (2*a). The composition is TRUE by
    # construction (a*(1-ecc) <= a < 2*a on the declared box), so any
    # falsified verdict here is an engine artifact.
    mod = _mod(tmp_path, _VIS_VIVA, "gw_a")
    (p,) = check_conjectures(mod.vis_viva_speed, [claim(
        "for GM in [1,100], a in [1,10], let ecc be [0,0.9], "
        "f(GM, a*(1-ecc), a) == sqrt(GM*(2/(a*(1-ecc)) - 1/a))",
        route="derive")])
    assert p.verdict != "falsified", (p.verdict, p.note, p.counterexample)


def test_direct_scaled_guard_raises_claim_still_proves(tmp_path):
    # the isolating control from the same corpus finding: the same
    # 2*a guard, approached with a directly-declared free variable,
    # proves as its own raises() claim
    mod = _mod(tmp_path, _VIS_VIVA, "gw_b")
    (p,) = check_conjectures(mod.vis_viva_speed, [claim(
        "for GM in [1,100], a in [1,10], r in [21,500], "
        "raises(f(GM,r,a), ValueError)", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_genuine_guard_witness_still_falsifies_pedantically(tmp_path):
    # corroboration must not weaken the pedantic rule: a reachable
    # raise region falsifies, because executing the witness reproduces
    # the raise
    mod = _mod(tmp_path, _VIS_VIVA, "gw_c")
    (p,) = check_conjectures(mod.vis_viva_speed, [claim(
        "for GM in [1,100], r in [-5,5], a in [1,10], f(GM,r,a) >= 0",
        route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample


def test_corroboration_executes_the_real_function(tmp_path):
    # a function whose guard TEXT looks reachable but whose body never
    # raises (the guard re-checks and returns instead): the symbolic
    # witness fails execution, so the verdict must stay short of
    # falsified
    mod = _mod(tmp_path, """
def soft_guard(x: float) -> float:
    if x < 0:
        return 0.0
    return x ** 0.5
""", "gw_d")
    (p,) = check_conjectures(mod.soft_guard, [claim(
        "for x in [-1,1], f(x) >= 0", route="derive")])
    assert p.verdict != "falsified", (p.verdict, p.note)


def test_witness_values_match_the_functions_arithmetic(tmp_path):
    # integer-domain witnesses execute as ints: a float landing in a
    # range() must not fabricate a TypeError corroboration
    mod = _mod(tmp_path, """
def stepper(n: int, rate: float) -> float:
    if rate < 0:
        raise ValueError("rate must be nonnegative")
    total = 0.0
    for i in range(n):
        total += rate
    return total
""", "gw_e")
    (p,) = check_conjectures(mod.stepper, [claim(
        "for n in [1,5], rate in [0,5], f(n,rate) >= 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    (p,) = check_conjectures(mod.stepper, [claim(
        "for n in [1,5], rate in [-2,5], f(n,rate) >= 0", route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.note)


_BLASIUS = """
def blasius_drop(rho: float, v: float, diameter: float, mu: float) -> float:
    if rho <= 0:
        raise ValueError("density must be positive")
    if v <= 0:
        raise ValueError("velocity must be positive")
    if diameter <= 0:
        raise ValueError("diameter must be positive")
    if mu <= 0:
        raise ValueError("viscosity must be positive")
    re = rho * v * diameter / mu
    if re < 4000:
        raise ValueError("Reynolds number below the turbulent range")
    f = 0.316 * re ** -0.25
    return f * rho * v ** 2 / (2 * diameter)
"""


def test_computed_guard_quantity_resolves_past_lead_guards(tmp_path):
    # the poisoning wall: one computed-expression guard (re < 4000)
    # used to defeat EVERY guard's raises() claim in the function,
    # because local resolution stopped at the first lead guard. The
    # computed guard's own claim, and the bare-parameter guard beside
    # it, both prove now.
    mod = _mod(tmp_path, _BLASIUS, "gw_f")
    (p,) = check_conjectures(mod.blasius_drop, [claim(
        "for rho in [0.1,1], v in [0.001,0.01], diameter in [0.001,0.01], "
        "mu in [0.1,1], raises(f(rho,v,diameter,mu), ValueError)",
        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    (p,) = check_conjectures(mod.blasius_drop, [claim(
        "for rho in [-10,-0.1], v in [1,50], diameter in [0.1,2], "
        "mu in [1e-5,0.1], raises(f(rho,v,diameter,mu), ValueError)",
        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    (p,) = check_conjectures(mod.blasius_drop, [claim(
        "for rho in [500,2000], v in [10,50], diameter in [0.5,2], "
        "mu in [1e-6,1e-5], f(rho,v,diameter,mu) == "
        "0.316*(rho*v*diameter/mu)**-0.25 * rho*v**2/(2*diameter)",
        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_compound_call_arguments_reach_through_guards(tmp_path):
    # the two-factor compound-argument wall (k*x against an internal
    # offset < x guard) and the let-bound guard slot both adjudicate
    # through argument substitution + the general condition decision
    mod = _mod(tmp_path, """
import math

def gap(x: float, offset: float) -> float:
    if offset < x:
        raise ValueError("offset below x")
    return offset - x

def lorentz_time(t: float, x: float, beta: float) -> float:
    if beta >= 1 or beta <= -1:
        raise ValueError("beta must satisfy |beta| < 1")
    return (t - beta * x) / math.sqrt(1 - beta ** 2)
""", "gw_g")
    (p,) = check_conjectures(mod.gap, [claim(
        "for x in [0,2], offset in [3,10], let k be [1,5], "
        "f(k*x, k*offset) == k*f(x, offset)", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    (p,) = check_conjectures(mod.lorentz_time, [claim(
        "for t in [-20,20], x in [-20,20], let b2 be [-0.6,0.6], "
        "f(t, x, b2) == (t - b2*x)/sqrt(1 - b2**2)", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_type_misspecified_domain_skips_loudly_not_falsifies(tmp_path):
    # the corpus's geometric-twin finding: a float-typed closed form
    # bound to an int-typed loop counterpart, quantified over a REAL
    # n; sampling n=7.7 into range() raised TypeError and was once
    # reported falsified. The signature's own int contract makes that
    # a claim-domain misspecification: skip loudly, name the fix.
    mod = _mod(tmp_path, """
def closed_form_twin(a: float, r: float, n: float) -> float:
    return a * (1 - r ** n) / (1 - r)

def geometric_series_finite(a: float, r: float, n: int) -> float:
    total = 0.0
    term = a
    for _ in range(n):
        total = total + term
        term = term * r
    return total
""", "gw_h")
    (p,) = check_conjectures(mod.closed_form_twin, [claim(
        "for a in [1,5], r in [0.1,0.9], n in [1,10], "
        "f(a,r,n) == g(a,r,n)", route="probe",
        funcs={"g": mod.geometric_series_finite})])
    assert p.verdict == "skipped:misspecified", (p.verdict, p.note)
    assert "subset Z" in (p.note or "") and "n" in (p.note or "")
    # with the domain fixed, honest empirical evidence
    (p,) = check_conjectures(mod.closed_form_twin, [claim(
        "for a in [1,5], r in [0.1,0.9], n in [1,10] subset Z, "
        "f(a,r,n) == g(a,r,n)", route="probe",
        funcs={"g": mod.geometric_series_finite})])
    assert p.verdict == "holds", (p.verdict, p.note)
    # a genuine TypeError at an all-integral sample still falsifies
    mod2 = _mod(tmp_path, """
def rejects(n: int) -> float:
    if n % 2 == 0:
        raise TypeError("even input rejected")
    return float(n)
""", "gw_i")
    (p,) = check_conjectures(mod2.rejects, [claim(
        "for n in [2,2] subset Z, f(n) >= 0", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
