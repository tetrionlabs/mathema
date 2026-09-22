# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Real-world-shaped functions across several fields, checked against
the derive route as it stands today. This file has two jobs at once:
confirm the route actually handles ordinary code people write (not just
synthetic fixtures shaped to fit its exact grammar), and, for the
ones it doesn't yet handle; catalog *why*, in a form future work can
act on directly. A function that currently fails is `pytest.mark.skip`,
never deleted or left to error: the skip reason is the real,
live-verified `derivability_report()`/`ProofResult.sketch` message, not
a guess, and doubles as the roadmap entry for whichever piece of
machinery would need to exist to close it.

Each skip is tagged with a short category name in its reason, matching
across functions where the same underlying gap recurs, so grepping
this file for a category name surfaces every real-world example that
hits it, not just one.

**History, in the order these were found and closed**, since several
categories this catalog originally surfaced are fixed as of today, not
hypothetical:

1. **post-processed accumulator return** (`return total / n`, hit by
   both `sample_mean` and `rms`), fixed: `lift_fold()` no longer
   requires a bare `return <accumulator>`.
2. **dot product via a literal `np.dot(...)` call** (`dot_weights`),
   fixed: `lift_dot()`, a narrow primitive recognizing exactly that
   call form, no loop or general vector type needed.
3. **nested loops, multiple sequential accumulator passes, non-affine
   (but purely additive) updates, and a dot product recognized
   directly from loop structure** (`dot_product`, `rms`,
   `softmax_denominator`, `sample_variance_two_pass`,
   `present_value_series`), fixed: `lift_sum()`, a more general
   sibling to `lift_fold()` for the specific case where the
   accumulator's own coefficient is exactly 1 (pure addition, never
   multiplying the accumulator by anything), no telescoping needed at
   all in that case, just wrapping the update directly in a (possibly
   nested) `Sum`, however nonlinear the update itself is in the loop
   item.
4. **a local array built from `np.linspace`/`np.arange`, transformed
   elementwise, returned bare or as one element of a tuple**
   (`ellipse_path`), fixed: recognized as a `_SymbolicArray` (a known
   closed form in terms of a fresh index symbol), propagated explicitly
   through already-mapped elementwise ops/calls, indexed in claim text
   via `f(...)[i]` (a bare int for a boundary claim, or a bound name for
   a claim over the whole array), no explicit Python loop involved, so
   this is an extension of the base `lift()` path itself, not a new
   `lift_XXX()` sibling. Only a *locally built* array, a sequence
   *parameter* (`normalize_by_max`, below) is still out of scope; that
   needs a real vector type, not just this.
5. **clamp resolution between two independently domain-bounded
   parameters** (`kinetic_energy_capped`'s `min(v, v_max) ** 2`),
   fixed: `_resolve_clamps()` originally only collapsed a `Min`/`Max`
   when one side was a plain numeric literal; extended to also collapse
   between two parameters whose declared domains provably don't
   overlap. The `Pow` wrapping the clamp was never actually the
   blocker, `expr.atoms()`/`.subs()` already reach through it; the
   real gap was symbol-vs-symbol never being attempted at all.

**Still open**: **multiple accumulators updated within the same loop
body** (`sample_second_moment_single_pass`, a classic single-pass
optimization, distinct from *sequential* multi-loop, which is closed;
`_recognize_sum_piece()` in `mathema/symbolic/_sum.py` requires exactly
one statement per loop-nest level, a core part of its recursive
recognition, not a superficial check); **two sequences consumed
together via a shared, non-trivial index expression** (`polygon_area_
shoelace`'s `j = (i + 1) % n`, same underlying gap as `dot_product`
before phase 3 above, but with an index expression more complex than a
plain `range(len(...))`); **vector-valued parameters**
(`normalize_by_max`'s own `xs` parameter, needs a real vector type,
distinct from a locally built array, which phase 4 above now handles);
and a **reduction over a locally built array** (`np.sum`/`np.dot` on
one, as opposed to returning it elementwise, named here, not yet
backed by its own test case in this file)."""
import math

import numpy as np
import pytest

from mathema.conjecture import claim, check_conjectures
from mathema.analysis import analyze_source
from mathema.symbolic import lift_fold


# --- Physics -----------------------------------------------------------

def projectile_range(v0: float, theta: float, g: float) -> float:
    return v0 ** 2 * math.sin(2 * theta) / g


def rc_discharge(v0: float, t: float, tau: float) -> float:
    return v0 * math.exp(-t / tau)


def kinetic_energy_capped(m: float, v: float, v_max: float) -> float:
    return 0.5 * m * min(v, v_max) ** 2


def free_fall_impulse_sum(forces: list, dt: float) -> float:
    impulse = 0.0
    for f in forces:
        impulse += f * dt
    return impulse


def test_projectile_range_proves():
    results = check_conjectures(
        projectile_range,
        [claim("for v0 in [1, 100], theta in [0, 1], g in [1, 20], "
              "f(v0, theta, g) == v0**2 * sin(2*theta) / g", route="derive")])
    assert results[0].verdict == "proven"


def test_rc_discharge_proves():
    results = check_conjectures(
        rc_discharge,
        [claim("for v0 in [0, 10], t in [0, 5], tau in [0.1, 10], "
              "f(v0, t, tau) == v0 * exp(-t/tau)", route="derive")])
    assert results[0].verdict == "proven"


def test_kinetic_energy_capped_proves():
    results = check_conjectures(
        kinetic_energy_capped,
        [claim("for m in [1, 10], v in [10, 20], v_max in [1, 5], "
              "f(m, v, v_max) == 0.5*m*v_max**2", route="derive")])
    assert results[0].verdict == "proven"


def test_free_fall_impulse_sum_is_a_recognized_fold_structurally():
    # a bare `return impulse` accumulator sum, lift_fold() recognizes
    # the shape; provable *claims* against it are limited by the fold
    # law grammar's lack of a `Sum(...)` primitive (see
    # test_symbolic.py's own fold-claim coverage), not by lifting.
    facts = analyze_source(free_fall_impulse_sum)
    assert lift_fold(free_fall_impulse_sum, facts) is not None


# --- Finance -------------------------------------------------------------

def compound_interest(principal: float, rate: float, n: float, t: float) -> float:
    return principal * (1 + rate / n) ** (n * t)


def present_value_series(cashflows: list, r: float) -> float:
    pv = 0.0
    for i, cf in enumerate(cashflows):
        pv += cf / (1 + r) ** i
    return pv


def test_compound_interest_proves():
    results = check_conjectures(
        compound_interest,
        [claim("for principal in [0, 1000], rate in [0, 1], n in [1, 12], t in [0, 10], "
              "f(principal, rate, n, t) == principal*(1+rate/n)**(n*t)", route="derive")])
    assert results[0].verdict == "proven"


def test_present_value_series_proves():
    # `for i, cf in enumerate(cashflows)`, an index paired with an
    # item, not one of lift_fold()'s own two recognized loop-iterable
    # shapes, but lift_sum()'s general "pure sum" recognizer handles
    # `enumerate()` directly (see classify_loop_header), closing to
    # Sum(cashflows[i]/(1+r)**i, ...).
    results = check_conjectures(
        present_value_series,
        [claim("f(cashflows, r) == f(cashflows, r)", route="derive")])
    assert results[0].verdict == "proven"


# --- Biology / stats -----------------------------------------------------

def logistic_growth_step(pop: float, r: float, k: float) -> float:
    return pop + r * pop * (1 - pop / k)


def sample_mean(xs: list) -> float:
    total = 0.0
    for x in xs:
        total += x
    return total / len(xs)


def sample_variance_two_pass(xs: list) -> float:
    total = 0.0
    for x in xs:
        total += x
    mean = total / len(xs)
    sq = 0.0
    for x in xs:
        sq += (x - mean) ** 2
    return sq / len(xs)


def sample_second_moment_single_pass(xs: list) -> float:
    sum_x = 0.0
    sum_x2 = 0.0
    for x in xs:
        sum_x += x
        sum_x2 += x * x
    n = len(xs)
    return sum_x2 / n - (sum_x / n) ** 2


def test_logistic_growth_step_proves():
    results = check_conjectures(
        logistic_growth_step,
        [claim("for pop in [0, 100], r in [0, 1], k in [1, 200], "
              "f(pop, r, k) == pop + r*pop*(1 - pop/k)", route="derive")])
    assert results[0].verdict == "proven"


def test_sample_mean_is_a_recognized_fold_structurally():
    # `return total / len(xs)`; a post-processed accumulator return
    # (dividing by count), no longer an automatic refusal (see
    # lift_fold()'s own docstring): the return expression is lifted
    # with the accumulator bound to a bare symbol, and `len(xs)`
    # resolves against the fold's own symbolic length the same way it
    # already did in a claim. Structural check, not a proven claim,
    # since a *universally true* claim about a mean's own value is
    # awkward to state in the fold law grammar's narrow vocabulary,
    # see test_symbolic.py's own fold-claim tests for what that grammar
    # can express.
    facts = analyze_source(sample_mean)
    assert lift_fold(sample_mean, facts) is not None


def test_sample_variance_two_pass_proves():
    # 2 sequential loops (a mean pass, then a sum-of-squared-deviations
    # pass using it), lift_fold() only ever recognizes a single loop,
    # but lift_sum()'s sequential walk recognizes the intermediate
    # scalar (`mean`) as an ordinary local, available to the second
    # pass, not a special case. Also exercises a real sympy quirk
    # (_safe_simplify): the second pass's own Sum contains the first
    # pass's Sum inside its summand, which plain sympy.simplify() can't
    # handle without raising, see symbolic.py's own _safe_simplify.
    results = check_conjectures(
        sample_variance_two_pass, [claim("f(xs) == f(xs)", route="derive")])
    assert results[0].verdict == "proven"


@pytest.mark.xfail(strict=True, reason="[multiple-accumulators-per-loop] two running totals (sum_x, "
                        "sum_x2) updated in the *same* loop body, a classic single-pass "
                        "optimization, distinct from the multi-loop case above; "
                        "lift_fold() requires the loop body be exactly one statement")
def test_sample_second_moment_single_pass_proves():
    results = check_conjectures(
        sample_second_moment_single_pass, [claim("f(xs) == 0.0", route="derive")])
    assert results[0].verdict == "proven"


# --- Signal processing -----------------------------------------------------

def rms(signal: list) -> float:
    total = 0.0
    for v in signal:
        total += v * v
    return math.sqrt(total / len(signal))


def dot_product(a: list, b: list) -> float:
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


def softmax_denominator(logits: list) -> float:
    total = 0.0
    for z in logits:
        total += math.exp(z)
    return total


def test_rms_proves():
    # `total += v * v` squares the loop item, not affine, so
    # lift_fold() always declined it, but the accumulator's own
    # coefficient is still exactly 1 (pure addition), which is all
    # lift_sum() needs: no telescoping required, just Sum(v**2, ...).
    results = check_conjectures(rms, [claim("f(signal) == f(signal)", route="derive")])
    assert results[0].verdict == "proven"


def test_dot_product_proves():
    # two sequence parameters (a, b) consumed together via a shared
    # `range(len(a))` index, lift_fold() requires exactly one
    # sequence-typed parameter, and lift_dot() only recognizes the
    # literal `np.dot(a, b)` call (see dot_weights above), neither
    # matches this hand-written loop. lift_sum()'s "index" loop-header
    # form (see classify_loop_header) recognizes it directly: `i` binds
    # to the fresh Sum index itself, and the update expression
    # subscripts *both* sequences by it.
    results = check_conjectures(
        dot_product, [claim("f(a, b) == f(a, b)", route="derive")])
    assert results[0].verdict == "proven"


def test_softmax_denominator_proves():
    # `total += exp(z)`, not affine in the loop item (exp is
    # nonlinear), so lift_fold()'s closed-form telescoping machinery
    # always refused it. lift_sum() carries it as a genuinely symbolic
    # Sum(exp(logits[k]), (k, 0, L-1)) instead, no telescoping
    # attempted at all, since none is needed for a purely additive
    # accumulator regardless of how nonlinear the summand itself is.
    results = check_conjectures(
        softmax_denominator, [claim("f(logits) == f(logits)", route="derive")])
    assert results[0].verdict == "proven"


# --- ML --------------------------------------------------------------------

def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def dot_weights(weights: list, features: list) -> float:
    return float(np.dot(weights, features))


def normalize_by_max(xs: list) -> list:
    m = max(xs)
    return [x / m for x in xs]


def test_sigmoid_proves():
    results = check_conjectures(
        sigmoid, [claim("for z in [-5, 5], f(z) == 1/(1+exp(-z))", route="derive")])
    assert results[0].verdict == "proven"


def test_dot_weights_proves():
    # `return float(np.dot(weights, features))`, a whole-body dot
    # product between the function's own two sequence parameters,
    # recognized directly (lift_dot(), no general vector type needed):
    # Sum(weights[k]*features[k], (k, 0, L-1)).
    results = check_conjectures(
        dot_weights, [claim("f(weights, features) == f(weights, features)", route="derive")])
    assert results[0].verdict == "proven"


@pytest.mark.xfail(strict=True, reason="[vector-valued] xs (parameter) and the list-comprehension "
                        "return value are both array-valued, lift() only reasons over "
                        "scalar parameters and scalar returns; out of scope without a "
                        "real vector type")
def test_normalize_by_max_proves():
    results = check_conjectures(
        normalize_by_max, [claim("f(xs) == xs", route="derive")])
    assert results[0].verdict == "proven"


# --- Geometry ----------------------------------------------------------

def distance_2d(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def polygon_area_shoelace(xs: list, ys: list) -> float:
    area = 0.0
    n = len(xs)
    for i in range(n):
        j = (i + 1) % n
        area += xs[i] * ys[j] - xs[j] * ys[i]
    return abs(area) / 2.0


def ellipse_path(cx: float, cy: float, a: float, b: float, n: float) -> tuple:
    phi = np.linspace(0.0, 2.0 * np.pi, n)
    x = cx + a * np.cos(phi)
    y = cy + b * np.sin(phi)
    return x, y


def test_distance_2d_proves():
    results = check_conjectures(
        distance_2d,
        [claim("for x1 in [0, 1], y1 in [0, 1], x2 in [0, 1], y2 in [0, 1], "
              "f(x1, y1, x2, y2) == sqrt((x2-x1)**2 + (y2-y1)**2)", route="derive")])
    assert results[0].verdict == "proven"


@pytest.mark.xfail(strict=True, reason="[indexed-multi-sequence-fold] xs, ys consumed together via a "
                        "shared, modular (i+1) % n index, same underlying gap as "
                        "dot_product, with the added complication of a non-trivial index "
                        "expression rather than a plain range(len(...))")
def test_polygon_area_shoelace_proves():
    results = check_conjectures(
        polygon_area_shoelace, [claim("f(xs, ys) >= 0", route="derive")])
    assert results[0].verdict == "proven"


def test_ellipse_path_proves():
    # arbital.geometry.ellipse_path's own real deep-dive blocker: a local
    # array built via np.linspace, transformed elementwise (np.cos/
    # np.sin), returned as a tuple of two arrays, _SymbolicArray, one
    # claim per array, each indexed by a bound name (i) substituted for
    # phi's own closed form (i*(2*pi)/(n-1)).
    results = check_conjectures(
        ellipse_path, [claim("f(cx, cy, a, b, n)[0][i] == cx + a*cos(2*pi*i/(n-1))",
                            route="derive")])
    assert results[0].verdict == "proven"
    results = check_conjectures(
        ellipse_path, [claim("f(cx, cy, a, b, n)[1][i] == cy + b*sin(2*pi*i/(n-1))",
                            route="derive")])
    assert results[0].verdict == "proven"


# --- Chemistry / engineering -----------------------------------------------

def michaelis_menten(s: float, vmax: float, km: float) -> float:
    return vmax * s / (km + s)


def arrhenius_rate(a: float, ea: float, t: float, r_gas: float) -> float:
    return a * math.exp(-ea / (r_gas * t))


def test_michaelis_menten_proves():
    results = check_conjectures(
        michaelis_menten,
        [claim("for s in [0, 10], vmax in [0, 5], km in [0.1, 5], "
              "f(s, vmax, km) == vmax*s/(km+s)", route="derive")])
    assert results[0].verdict == "proven"


def test_arrhenius_rate_proves():
    results = check_conjectures(
        arrhenius_rate,
        [claim("for a in [0, 10], ea in [0, 100], t in [1, 500], r_gas in [1, 10], "
              "f(a, ea, t, r_gas) == a*exp(-ea/(r_gas*t))", route="derive")])
    assert results[0].verdict == "proven"
