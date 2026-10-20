# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The domain-box interval-evaluation pass: a bounded domain (or a
function's known global range) used as a rigorous sign fact, tried
before sympy's ask()/is_nonnegative machinery. Proves `>= 0` when the
box's interval never goes negative, disproves when it never reaches
zero from below, proves `!=` when the interval excludes zero, and
stays silent (falls through) whenever the interval straddles zero,
because interval arithmetic over-approximates and must never falsify
from an unattained bound."""
import math

from mathema.conjecture import check_conjectures, claim


def half_cos(theta: float) -> float:
    return math.cos(theta) / 2.0


def normalish(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x))


def rational(v: float) -> float:
    return 5.0 / (2.0 * v - 1.0)


def parabola(x: float) -> float:
    return x * x - 2.0 * x


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


def test_bounded_box_proves_a_lone_trig_sign():
    p = _one(half_cos, "for theta in [-0.1, 0.1], f(theta) >= 0")
    assert p.verdict == "proven"
    assert "interval evaluation" in p.sketch


def test_known_function_range_proves_an_unbounded_claim():
    # no domain at all: erf's global range [-1, 1] is the whole fact
    p = _one(normalish, "f(x) <= 1")
    assert p.verdict == "proven"
    p = _one(normalish, "f(x) >= 0")
    assert p.verdict == "proven"


def test_bare_rational_over_a_box_proves_sign_and_disequality():
    assert _one(rational, "for v in [10, 1000], f(v) >= 0").verdict == "proven"
    p = _one(rational, "for v in [10, 1000], f(v) != 0")
    assert p.verdict == "proven"
    assert "never zero" in p.sketch


def test_interval_disproves_an_unreachable_bound():
    p = _one(half_cos, "for theta in [-0.1, 0.1], f(theta) >= 1")
    assert p.verdict == "falsified"
    assert "always negative" in p.sketch


def test_dependency_prone_polynomial_still_proves():
    # x**2 - 2x on [3, 5]: a naive interval on the raw form straddles
    # zero (the dependency problem), but the pass runs on the
    # domain-resolved difference, whose shape lets the box land
    # positive, and either way, a straddling interval is only ever
    # silent, never a falsification.
    p = _one(parabola, "for x in [3, 5], f(x) >= 0")
    assert p.verdict == "proven"


def test_trig_product_proves_after_sympy_collapses_the_dependency():
    # sin(x)*cos(x) + 0.6: simplification folds the product to
    # sin(2*x)/2, removing the dependency, and the single hull
    # [1/10, 11/10] then proves the sign on the fast path, no
    # extensive machinery needed.
    def sincos(x: float) -> float:
        return math.sin(x) * math.cos(x) + 0.6

    p = _one(sincos, "for x in [-1.4, 1.4], f(x) >= 0")
    assert p.verdict == "proven"
    assert p.route == "derive"


def test_exponential_decay_gap_proves_on_the_fast_path():
    # exp(-x) - exp(-2x) >= 0 on [0, 50]: factoring to
    # (exp(x) - 1)*exp(-2x) gives the one-box hull a clean sign even
    # though the bound is attained at x = 0.
    def exp_decay_gap(x: float) -> float:
        return math.exp(-x) - math.exp(-2.0 * x)

    p = _one(exp_decay_gap, "for x in [0, 50], f(x) >= 0")
    assert p.verdict == "proven"
    assert p.route == "derive"


def test_straddling_interval_never_falsifies_a_true_claim():
    # x*sin(x) >= 0 is true on [-1, 1], but interval arithmetic sees
    # [-1, 1] * [-0.85, 0.85] straddling zero. The pass must stay
    # silent here (over-approximation can't witness attainability);
    # whatever the downstream machinery concludes, "falsified" would be
    # a lie and is the one forbidden outcome.
    import math as _math

    def xsin(x: float) -> float:
        return x * _math.sin(x)

    p = _one(xsin, "for x in [-1, 1], f(x) >= 0")
    assert p.verdict != "falsified", (p.verdict, p.sketch)
