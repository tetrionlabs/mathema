# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Residue-theory evaluation of real definite integrals: the classic
contour substitutions, each turning a global real integral into a
finite algebraic computation at the poles of a complex extension.

A `ContourPattern` packages one such method: recognize the integrand
shape, discharge the method's side conditions exactly against the
claim's declared parameter domains, enumerate the poles in the
relevant region, and sum residues. Every side condition must discharge
outright, an undecidable pole position or growth condition declines
the pattern (undecided, never a guess). The two founding patterns:

- **semicircle**: a rational integrand over (-oo, oo), closed with an
  upper half-plane semicircle. The arc vanishes when the denominator
  degree exceeds the numerator's by at least two, and the value is
  2*pi*i times the residues at the poles strictly above the real axis
  (higher-order poles need no special case: the residue computation
  itself handles multiplicity).
- **unit_circle**: a rational function of cos(theta) and sin(theta)
  over one full period. The substitution z = e^{i*theta} sends the
  integral around the unit circle (cos = (z + 1/z)/2, sin =
  (z - 1/z)/(2i), d(theta) = dz/(iz)), and the value is 2*pi*i times
  the residues strictly inside |z| = 1.
- **jordan**: a Fourier kernel, rational times cos(c*x) or sin(c*x)
  over the whole line. The kernel is the real or imaginary part of
  e^{i*c*x}, whose modulus decays exponentially in the half-plane the
  sign of c selects, so Jordan's lemma closes the contour there with
  only one degree of denominator headroom needed.
- **half_line**: an even integrand over [0, oo) is half its own
  full-line integral, which the other patterns then evaluate.
- **keyhole**: x^b * f(x) over [0, oo) with a non-integer exponent b.
  The keyhole contour walks both sides of a branch cut along the
  positive axis, where z^b differs by the factor e^{2*pi*i*b}, so the
  contour integral is (1 - e^{2*pi*i*b}) times the real one.
- **keyhole_log** / **keyhole_plain**: the Log-weighted keyhole. The
  discontinuity of Log across the same cut isolates the plain
  integral of a rational f over [0, oo) (no symmetry needed), and the
  Log^2 form isolates the log-weighted integral f(x)*log(x).

The engine also carries the adjudication policy for disagreements with
sympy's own symbolic integration, which is known to evaluate some of
exactly these shapes wrongly (a discontinuous antiderivative read
across the range): when both produce a value and the values differ,
direct numeric quadrature of the original integral at sampled domain
points decides which mechanism is right, and the record says so."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

import sympy

from .._sampling import _RNG_SEED, _synth_scalar
from ._proof_support import (
    ProofResult, _decide_relation, _humanize, _interval_bounds,
)

_QUADRATURE_TRIALS = 3


@dataclass(frozen=True)
class ContourPattern:
    """One contour method: `detect` maps `(integrand, var, lo, hi)` to
    an opaque match object (or `None` when the shape doesn't apply),
    and `evaluate` maps `(match, domain, params)` to the integral's
    exact value together with a provenance sketch naming the contour,
    the poles used, and their residues, or `None` when any side
    condition fails to discharge."""
    name: str
    detect: Callable
    evaluate: Callable


def _strict_sign(expr, domain: dict, params: dict, max_cells: int = 32):
    """Intent:
        Decide whether `expr` is strictly positive everywhere (+1) or
        strictly negative everywhere (-1) on the declared parameter
        box, by interval evaluation with bisection refinement.

    Notes:
        `None` when the hull straddles at every affordable cell size or
        evaluation fails, the caller declines its pattern. Strictness
        matters: a pole's distance from the contour must be bounded
        away from zero, so a hull endpoint landing exactly on zero is
        not good enough.
    """
    forms = [expr]
    even_abs = expr.replace(
        lambda e: (isinstance(e, sympy.Pow) and isinstance(e.base, sympy.Abs)
                   and getattr(e.exp, "is_Integer", False) and e.exp % 2 == 0),
        lambda e: e.base.args[0] ** e.exp)
    # |u|^(2k) equals u^(2k) for the real-valued expressions interval
    # evaluation covers (a hull only exists at all when every
    # subexpression evaluates real over the box), and the Abs-free form
    # often cancels where the Abs form cannot.
    for candidate in (even_abs, sympy.radsimp(even_abs),
                      sympy.cancel(sympy.together(even_abs))):
        try:
            if candidate not in forms:
                forms.append(candidate)
        except Exception:
            continue

    def hull_sign(cell_domain):
        for form in forms:
            got = _one_hull_sign(form, cell_domain)
            if got in (1, -1):
                return got
        return _one_hull_sign(forms[0], cell_domain)

    def _one_hull_sign(form, cell_domain):
        from ._proof_support import _verified_sign
        hull = _interval_bounds(form, cell_domain, params)
        if hull is None:
            return None
        lo = hull.min if isinstance(hull, sympy.AccumBounds) else hull
        hi = hull.max if isinstance(hull, sympy.AccumBounds) else hull
        if _verified_sign(lo) == 1:
            return 1
        if _verified_sign(hi) == -1:
            return -1
        return 0   # straddles: needs a finer cell

    worklist = [dict(domain)]
    signs: set = set()
    cells = 1
    while worklist:
        cell = worklist.pop()
        entry = hull_sign(cell)
        if entry is None:
            return None
        if entry in (1, -1):
            signs.add(entry)
            if len(signs) > 1:
                return None
            continue
        # straddling: bisect the widest finite bounded dimension
        widest, width = None, None
        for p, bound in cell.items():
            if not (isinstance(bound, tuple) and len(bound) == 2):
                continue
            try:
                w = float(bound[1] - bound[0])
            except (TypeError, OverflowError):
                continue
            if w > 0 and w != float("inf") and (width is None or w > width):
                widest, width = p, w
        if widest is None or cells >= max_cells:
            return None
        lo, hi = cell[widest]
        mid = (lo + hi) / 2
        for half in ((lo, mid), (mid, hi)):
            sub = dict(cell)
            sub[widest] = half
            worklist.append(sub)
        cells += 1
    if len(signs) == 1:
        return signs.pop()
    return None


def _enumerate_poles(denominator, z):
    """Intent:
        The denominator's roots as an explicit finite list, or `None`
        when sympy cannot enumerate them exactly.

    Notes:
        A `ConditionSet` (or any non-finite set) declines: residue
        methods need every pole accounted for, so a partial enumeration
        is worthless and an approximate one unsound.
    """
    try:
        roots = sympy.solveset(denominator, z, sympy.S.Complexes)
    except Exception:
        return None
    if not isinstance(roots, sympy.FiniteSet):
        return None
    return list(roots)


def _real_value(value):
    """Intent:
        The value with any residual imaginary bookkeeping cancelled, or
        `None` if an imaginary part genuinely survives.

    Notes:
        A residue sum for a real integral is real; an `I` that
        `expand_complex` cannot cancel means the computation went
        somewhere unsound (a missed pole, a branch issue) and the
        pattern must decline rather than report a complex "value".
    """
    try:
        collapsed = sympy.simplify(value)
        if collapsed.has(sympy.I):
            # plain simplification left an I standing; expand_complex
            # separates real and imaginary parts explicitly and can
            # cancel bookkeeping the generic pass missed.
            collapsed = sympy.simplify(sympy.expand_complex(collapsed))
    except Exception:
        return None
    if collapsed.has(sympy.I):
        return None
    return collapsed


def _detect_semicircle(integrand, var, lo, hi):
    if not (lo == -sympy.oo and hi == sympy.oo):
        return None
    z = sympy.Symbol("z")
    frac = sympy.cancel(sympy.together(integrand.subs(var, z)))
    num, den = sympy.fraction(frac)
    try:
        num_poly = sympy.Poly(num, z)
        den_poly = sympy.Poly(den, z)
    except sympy.PolynomialError:
        return None
    return {"z": z, "frac": frac, "num": num_poly, "den": den_poly}


def _evaluate_semicircle(match, domain: dict, params: dict):
    z, frac = match["z"], match["frac"]
    num_poly, den_poly = match["num"], match["den"]
    if den_poly.degree() < num_poly.degree() + 2:
        return None   # the closing arc's contribution doesn't vanish
    poles = _enumerate_poles(den_poly.as_expr(), z)
    if poles is None:
        return None
    upper = []
    for pole in poles:
        im_part = sympy.simplify(sympy.im(pole))
        if im_part.is_zero:
            return None   # a pole on the contour itself: not this method
        sign = (1 if im_part.is_positive else
                -1 if im_part.is_negative else
                _strict_sign(im_part, domain, params))
        if sign is None:
            return None   # pole side undecidable over the domain
        if sign == 1:
            upper.append(pole)
    residues = []
    for pole in upper:
        try:
            residues.append(sympy.residue(frac, z, pole))
        except Exception:
            return None
    value = _real_value(2 * sympy.pi * sympy.I * sum(residues, sympy.Integer(0)))
    if value is None:
        return None
    pole_text = ", ".join(_humanize(p) for p in upper) or "none"
    return value, (f"semicircle contour closed in the upper half-plane "
                   f"(denominator degree exceeds numerator's by 2+, so the "
                   f"arc vanishes); poles above the axis: {pole_text}; "
                   f"2*pi*i times their residues gives {_humanize(value)}")


def _detect_unit_circle(integrand, var, lo, hi):
    period_ok = (lo == 0 and hi == 2 * sympy.pi) or \
                (lo == -sympy.pi and hi == sympy.pi)
    if not period_ok:
        return None
    if not integrand.has(sympy.sin, sympy.cos, sympy.tan):
        return None
    z = sympy.Symbol("z")
    on_circle = integrand.subs([
        (sympy.tan(var), sympy.sin(var) / sympy.cos(var)),
    ]).subs([
        (sympy.cos(var), (z + 1 / z) / 2),
        (sympy.sin(var), (z - 1 / z) / (2 * sympy.I)),
    ])
    if on_circle.has(var):
        return None   # something trigonometric this substitution missed
    frac = sympy.cancel(sympy.together(on_circle / (sympy.I * z)))
    num, den = sympy.fraction(frac)
    try:
        den_poly = sympy.Poly(den, z)
        sympy.Poly(num, z)
    except sympy.PolynomialError:
        return None
    return {"z": z, "frac": frac, "den": den_poly}


def _evaluate_unit_circle(match, domain: dict, params: dict):
    z, frac, den_poly = match["z"], match["frac"], match["den"]
    poles = _enumerate_poles(den_poly.as_expr(), z)
    if poles is None:
        return None
    classified: dict = {}
    for pole in poles:
        distance = sympy.simplify(sympy.Abs(pole) ** 2 - 1)
        if distance.is_zero:
            return None   # a pole on the contour: not this method
        classified[pole] = (1 if distance.is_positive else
                            -1 if distance.is_negative else
                            _strict_sign(distance, domain, params))
    undecided = [p for p, sign in classified.items() if sign is None]
    if len(undecided) == 1 and den_poly.degree() == 2:
        # Vieta: a quadratic's roots multiply to c0/c2, so when that
        # ratio has modulus exactly 1, the roots' distances from the
        # unit circle are reciprocal; the undecided root sits
        # strictly on the other side of its already-classified partner.
        coeffs = den_poly.all_coeffs()
        ratio = sympy.simplify(coeffs[-1] / coeffs[0])
        unit_product = (sympy.simplify(ratio - 1) == 0
                        or sympy.simplify(ratio + 1) == 0)
        partner = next(p for p in classified if p is not undecided[0])
        if unit_product and classified[partner] in (1, -1):
            classified[undecided[0]] = -classified[partner]
            undecided = []
    if undecided:
        return None   # a pole's side of the contour is undecidable
    inside = [p for p, sign in classified.items() if sign == -1]
    residues = []
    for pole in inside:
        try:
            residues.append(sympy.residue(frac, z, pole))
        except Exception:
            return None
    value = _real_value(2 * sympy.pi * sympy.I * sum(residues, sympy.Integer(0)))
    if value is None:
        return None
    pole_text = ", ".join(_humanize(p) for p in inside) or "none"
    return value, (f"unit-circle contour via z = e^(i*theta) (cos -> "
                   f"(z + 1/z)/2, sin -> (z - 1/z)/(2i), d(theta) -> "
                   f"dz/(iz)); poles inside |z| = 1: {pole_text}; "
                   f"2*pi*i times their residues gives {_humanize(value)}")


def _detect_jordan(integrand, var, lo, hi):
    if not (lo == -sympy.oo and hi == sympy.oo):
        return None
    w_g = sympy.Wild("g")
    w_c = sympy.Wild("c", exclude=[var])
    for kernel, part in ((sympy.cos(w_c * var), "cos"),
                         (sympy.sin(w_c * var), "sin")):
        matched = integrand.match(w_g * kernel)
        if matched is None:
            continue
        g, c = matched[w_g], matched[w_c]
        if g.has(sympy.sin, sympy.cos, sympy.tan) or c.is_zero:
            continue
        z = sympy.Symbol("z")
        frac = sympy.cancel(sympy.together(g.subs(var, z)))
        num, den = sympy.fraction(frac)
        try:
            num_poly = sympy.Poly(num, z)
            den_poly = sympy.Poly(den, z)
        except sympy.PolynomialError:
            continue
        return {"z": z, "frac": frac, "num": num_poly, "den": den_poly,
                "c": c, "part": part}
    return None


def _evaluate_jordan(match, domain: dict, params: dict):
    z, frac = match["z"], match["frac"]
    num_poly, den_poly = match["num"], match["den"]
    c, part = match["c"], match["part"]
    if den_poly.degree() < num_poly.degree() + 1:
        return None   # even Jordan's lemma needs one degree of headroom
    c_sign = (1 if c.is_positive else
              -1 if c.is_negative else
              _strict_sign(c, domain, params))
    if c_sign is None:
        return None   # which half-plane closes depends on c's sign
    poles = _enumerate_poles(den_poly.as_expr(), z)
    if poles is None:
        return None
    chosen = []
    for pole in poles:
        im_part = sympy.simplify(sympy.im(pole))
        if im_part.is_zero:
            return None   # a pole on the contour: not this method
        side = (1 if im_part.is_positive else
                -1 if im_part.is_negative else
                _strict_sign(im_part, domain, params))
        if side is None:
            return None
        if side == c_sign:
            chosen.append(pole)
    exponential = frac * sympy.exp(sympy.I * c * z)
    total = sympy.Integer(0)
    for pole in chosen:
        try:
            total += sympy.residue(exponential, z, pole)
        except Exception:
            return None
    complex_value = c_sign * 2 * sympy.pi * sympy.I * total
    try:
        expanded = sympy.expand_complex(complex_value)
        value = sympy.simplify(sympy.re(expanded) if part == "cos"
                               else sympy.im(expanded))
    except Exception:
        return None
    if value.has(sympy.I) or value.has(sympy.re) or value.has(sympy.im):
        return None
    half_plane = "upper" if c_sign == 1 else "lower"
    pole_text = ", ".join(_humanize(p) for p in chosen) or "none"
    return value, (f"Jordan's lemma: {part}({_humanize(c)}*x) is the "
                   f"{'real' if part == 'cos' else 'imaginary'} part of "
                   f"e^(i*{_humanize(c)}*x), whose contour closes in the "
                   f"{half_plane} half-plane; poles there: {pole_text}; "
                   f"the residue sum gives {_humanize(value)}")


def _detect_half_line(integrand, var, lo, hi):
    if not (lo == 0 and hi == sympy.oo):
        return None
    try:
        mirrored = sympy.simplify(integrand - integrand.subs(var, -var))
    except Exception:
        return None
    if mirrored != 0:
        return None
    return {"integrand": integrand, "var": var}


def _evaluate_half_line(match, domain: dict, params: dict):
    integrand, var = match["integrand"], match["var"]
    full_line = sympy.Integral(integrand, (var, -sympy.oo, sympy.oo))
    inner = evaluate_integral(full_line, domain, params)
    if inner is None:
        return None
    value, name, sketch = inner
    return value / 2, (f"even integrand: the [0, oo) integral is half "
                       f"the full-line one; {sketch} (via {name})")


def _strictly_positive(expr, domain: dict, params: dict) -> bool:
    """Intent:
        One-sided convenience over `_strict_sign`: is `expr` strictly
        positive everywhere on the box?
    """
    if expr.is_positive:
        return True
    if expr.is_negative or expr.is_zero:
        return False
    return _strict_sign(expr, domain, params) == 1


def _classify_pole_position(pole, domain: dict, params: dict):
    """Intent:
        Which side of a positive-real-axis branch cut a pole sits on:
        "upper", "lower", or "negaxis" (strictly negative real axis),
        `None` for the origin, a pole on the cut itself, or an
        undecidable position.

    Notes:
        On the negative axis the principal branch of z^b and log(z)
        agree with the keyhole branch (both read arg = pi there), so
        such poles need no correction factor; a strictly-lower-half
        pole reads arg from (pi, 2*pi) on the keyhole branch, 2*pi more
        than the principal value.
    """
    if pole.is_zero:
        return None
    im_part = sympy.simplify(sympy.im(pole))
    if im_part.is_zero:
        re_part = sympy.simplify(sympy.re(pole))
        if re_part.is_negative or _strict_sign(re_part, domain, params) == -1:
            return "negaxis"
        return None
    if im_part.is_positive or _strict_sign(im_part, domain, params) == 1:
        return "upper"
    if im_part.is_negative or _strict_sign(im_part, domain, params) == -1:
        return "lower"
    return None


def _noninteger_exponent(b, domain: dict, params: dict) -> bool:
    """Intent:
        Is the exponent provably NOT an integer, exactly (a rational
        literal) or via its hull sitting strictly inside one integer
        gap over the declared domain?
    """
    if b.is_number:
        return b.is_integer is False
    hull = _interval_bounds(b, domain, params)
    if hull is None:
        return False
    lo = hull.min if isinstance(hull, sympy.AccumBounds) else hull
    hi = hull.max if isinstance(hull, sympy.AccumBounds) else hull
    try:
        import math as _math
        floor_lo = _math.floor(float(lo.evalf(30)))
        return bool(lo.evalf(30) > floor_lo) and bool(hi.evalf(30) < floor_lo + 1)
    except (TypeError, OverflowError, ValueError):
        return False


def _rational_parts(g, var):
    """Intent:
        `g` as `(z, frac, num_poly, den_poly)` in a fresh symbol, or
        `None` when it is not a rational function of `var`.
    """
    z = sympy.Symbol("z")
    frac = sympy.cancel(sympy.together(g.subs(var, z)))
    num, den = sympy.fraction(frac)
    try:
        return z, frac, sympy.Poly(num, z), sympy.Poly(den, z)
    except sympy.PolynomialError:
        return None


def _detect_keyhole(integrand, var, lo, hi):
    if not (lo == 0 and hi == sympy.oo):
        return None
    w_b = sympy.Wild("b", exclude=[var])
    w_g = sympy.Wild("g")
    matched = integrand.match(var ** w_b * w_g)
    if matched is None:
        return None
    b, g = matched[w_b], matched[w_g]
    if b.is_zero or b.is_integer or g.has(sympy.log):
        return None
    parts = _rational_parts(g, var)
    if parts is None:
        return None
    z, frac, num_poly, den_poly = parts
    return {"z": z, "frac": frac, "num": num_poly, "den": den_poly, "b": b}


def _evaluate_keyhole(match, domain: dict, params: dict):
    z, frac = match["z"], match["frac"]
    num_poly, den_poly, b = match["num"], match["den"], match["b"]
    if not _noninteger_exponent(b, domain, params):
        return None
    # convergence: integrable at 0 (b > -1) and at infinity
    # (b + deg num - deg den < -1), both strict
    if not _strictly_positive(b + 1, domain, params):
        return None
    headroom = sympy.Integer(den_poly.degree() - num_poly.degree() - 1) - b
    if not _strictly_positive(headroom, domain, params):
        return None
    poles = _enumerate_poles(den_poly.as_expr(), z)
    if poles is None or not poles:
        return None
    twist = sympy.exp(2 * sympy.pi * sympy.I * b)
    total = sympy.Integer(0)
    for pole in poles:
        position = _classify_pole_position(pole, domain, params)
        if position is None:
            return None
        try:
            res = sympy.residue(z ** b * frac, z, pole)
        except Exception:
            return None
        total += res * (twist if position == "lower" else 1)
    value = _real_value(2 * sympy.pi * sympy.I * total / (1 - twist))
    if value is None:
        return None
    pole_text = ", ".join(_humanize(p) for p in poles)
    return value, (f"keyhole contour around the branch cut of z^({_humanize(b)}) "
                   f"on the positive axis (the two sides differ by the factor "
                   f"e^(2*pi*i*({_humanize(b)}))); poles: {pole_text}; the "
                   f"corrected residue sum gives {_humanize(value)}")


def _log_keyhole_sums(frac, z, poles, positions):
    """Intent:
        The two residue sums of the Log-keyhole method: `f * L` and
        `f * L^2`, with `L` the keyhole logarithm represented per pole
        by an expression analytic there.
    """
    s1 = sympy.Integer(0)
    s2 = sympy.Integer(0)
    for pole, position in zip(poles, positions):
        if position == "negaxis":
            rep = sympy.log(-z) + sympy.I * sympy.pi
        elif position == "lower":
            rep = sympy.log(z) + 2 * sympy.pi * sympy.I
        else:
            rep = sympy.log(z)
        s1 += sympy.residue(frac * rep, z, pole)
        s2 += sympy.residue(frac * rep ** 2, z, pole)
    return s1, s2


def _log_keyhole_values(g, var, domain: dict, params: dict):
    """Intent:
        `(I0, Ilog)`, the exact values of the plain and log-weighted
        [0, oo) integrals of a rational `g`, or `None` when a side
        condition fails.

    Notes:
        Crossing the positive-axis cut adds 2*pi*i to Log, so the
        contour integral of f*L isolates the plain integral and the
        one of f*L^2 isolates the log-weighted one:
        I0 = -sum Res(f*L), Ilog = (4*pi^2*I0 - 2*pi*i*sum Res(f*L^2))
        / (4*pi*i).
    """
    parts = _rational_parts(g, var)
    if parts is None:
        return None
    z, frac, num_poly, den_poly = parts
    if den_poly.degree() < num_poly.degree() + 2:
        return None
    constant_term = den_poly.eval(0)
    if constant_term.is_zero is not False:
        return None   # a possible pole at the origin sits on the cut
    poles = _enumerate_poles(den_poly.as_expr(), z)
    if poles is None or not poles:
        return None
    positions = [_classify_pole_position(p, domain, params) for p in poles]
    if any(pos is None for pos in positions):
        return None
    try:
        s1, s2 = _log_keyhole_sums(frac, z, poles, positions)
    except Exception:
        return None
    i0 = _real_value(-s1)
    if i0 is None:
        return None
    ilog = _real_value((4 * sympy.pi ** 2 * i0 - 2 * sympy.pi * sympy.I * s2)
                       / (4 * sympy.pi * sympy.I))
    if ilog is None:
        return None
    return i0, ilog, poles


def _detect_keyhole_log(integrand, var, lo, hi):
    if not (lo == 0 and hi == sympy.oo):
        return None
    w_g = sympy.Wild("g")
    matched = integrand.match(w_g * sympy.log(var))
    if matched is None or matched[w_g].has(sympy.log):
        return None
    return {"g": matched[w_g], "var": var}


def _evaluate_keyhole_log(match, domain: dict, params: dict):
    got = _log_keyhole_values(match["g"], match["var"], domain, params)
    if got is None:
        return None
    _i0, ilog, poles = got
    pole_text = ", ".join(_humanize(p) for p in poles)
    return ilog, (f"Log^2 keyhole: crossing the positive-axis cut adds 2*pi*i "
                  f"to Log, so the squared form isolates the log-weighted "
                  f"integral; poles: {pole_text}; value {_humanize(ilog)}")


def _detect_keyhole_plain(integrand, var, lo, hi):
    if not (lo == 0 and hi == sympy.oo):
        return None
    if integrand.has(sympy.log, sympy.sin, sympy.cos, sympy.tan, sympy.exp):
        return None
    return {"g": integrand, "var": var}


def _evaluate_keyhole_plain(match, domain: dict, params: dict):
    got = _log_keyhole_values(match["g"], match["var"], domain, params)
    if got is None:
        return None
    i0, _ilog, poles = got
    pole_text = ", ".join(_humanize(p) for p in poles)
    return i0, (f"Log keyhole: crossing the positive-axis cut adds 2*pi*i to "
                f"Log, which isolates the [0, oo) integral without any "
                f"symmetry; poles: {pole_text}; value {_humanize(i0)}")


_CONTOUR_PATTERNS: list[ContourPattern] = [
    ContourPattern("unit_circle", _detect_unit_circle, _evaluate_unit_circle),
    ContourPattern("jordan", _detect_jordan, _evaluate_jordan),
    ContourPattern("semicircle", _detect_semicircle, _evaluate_semicircle),
    ContourPattern("keyhole", _detect_keyhole, _evaluate_keyhole),
    ContourPattern("keyhole_log", _detect_keyhole_log, _evaluate_keyhole_log),
    ContourPattern("half_line", _detect_half_line, _evaluate_half_line),
    ContourPattern("keyhole_plain", _detect_keyhole_plain, _evaluate_keyhole_plain),
]


def contour_patterns() -> tuple[ContourPattern, ...]:
    """The registered contour methods, in the order the engine tries
    them."""
    return tuple(_CONTOUR_PATTERNS)


def register_contour_pattern(pattern: ContourPattern) -> None:
    """Add a contour method to the registry. Raises `ValueError` on a
    duplicate name: proof records identify the method by name."""
    if any(p.name == pattern.name for p in _CONTOUR_PATTERNS):
        raise ValueError(f"a contour pattern named {pattern.name!r} is "
                         "already registered")
    _CONTOUR_PATTERNS.append(pattern)


def _evaluate_pv(integral: "sympy.Integral", domain: dict, params: dict):
    """Intent:
        The Cauchy principal value of a full-line rational integral by
        the indented contour: 2*pi*i times the residues strictly above
        the axis, plus pi*i times the residues at SIMPLE real poles
        (the indentation walks half way around each).

    Notes:
        Every real pole must be provably simple, a higher-order real
        pole has no principal value at all, so the root multiset must
        be complete (`sympy.roots` accounting for the full degree) and
        each real root's multiplicity checked. Declines otherwise.
    """
    if len(integral.limits) != 1 or len(integral.limits[0]) != 3:
        return None
    var, lo, hi = integral.limits[0]
    if not (lo == -sympy.oo and hi == sympy.oo):
        return None
    parts = _rational_parts(integral.function, var)
    if parts is None:
        return None
    z, frac, num_poly, den_poly = parts
    if den_poly.degree() < num_poly.degree() + 2:
        return None
    try:
        multiplicities = sympy.roots(den_poly)
    except Exception:
        return None
    if sum(multiplicities.values()) != den_poly.degree():
        return None   # incomplete root accounting: unsound to proceed
    total = sympy.Integer(0)
    real_poles = []
    for pole, mult in multiplicities.items():
        im_part = sympy.simplify(sympy.im(pole))
        if im_part.is_zero:
            if mult != 1:
                return None   # a higher-order real pole: no PV exists
            try:
                total += sympy.Rational(1, 2) * sympy.residue(frac, z, pole)
            except Exception:
                return None
            real_poles.append(pole)
            continue
        side = (1 if im_part.is_positive else
                -1 if im_part.is_negative else
                _strict_sign(im_part, domain, params))
        if side is None:
            return None
        if side == 1:
            try:
                total += sympy.residue(frac, z, pole)
            except Exception:
                return None
    value = _real_value(2 * sympy.pi * sympy.I * total)
    if value is None:
        return None
    pole_text = ", ".join(_humanize(p) for p in real_poles) or "none"
    return value, (f"indented contour: full residues above the axis plus "
                   f"half residues at the simple real poles ({pole_text}) "
                   f"give the principal value {_humanize(value)}")


def evaluate_integral(integral: "sympy.Integral", domain: dict, params: dict):
    """Intent:
        Evaluate one deferred definite integral by the first contour
        pattern whose shape matches and whose side conditions all
        discharge.

    Notes:
        Returns `(value, pattern_name, sketch)` or `None`. Only a
        single-variable integral with exactly one limit triple is
        attempted; iterated integrals wait for a future pass.
    """
    if len(integral.limits) != 1 or len(integral.limits[0]) != 3:
        return None
    var, lo, hi = integral.limits[0]
    integrand = integral.function
    for pattern in _CONTOUR_PATTERNS:
        try:
            match = pattern.detect(integrand, var, lo, hi)
        except Exception:
            continue
        if match is None:
            continue
        try:
            outcome = pattern.evaluate(match, domain, params)
        except Exception:
            continue
        if outcome is None:
            continue
        value, sketch = outcome
        return value, pattern.name, sketch
    return None


def _numeric_agreement(integral, candidate, domain: dict, params: dict):
    """Intent:
        Does direct numeric quadrature of `integral` agree with
        `candidate` at sampled points of the declared parameter box?

    Notes:
        `True`/`False` on a clear answer over at least one cleanly
        evaluated point (relative tolerance 1e-6); `None` when nothing
        evaluates. Quadrature never goes through an antiderivative, so
        it is the independent referee between a contour value and
        sympy's own symbolic integration.
    """
    free = sorted((integral.free_symbols | candidate.free_symbols), key=str)
    name_by_symbol = {sym: name for name, sym in params.items()}
    bounds = {}
    for sym in free:
        lo_hi = domain.get(name_by_symbol.get(sym))
        bounds[sym] = ((float(lo_hi[0]), float(lo_hi[1]))
                       if isinstance(lo_hi, tuple) else None)
    rng = random.Random(_RNG_SEED)
    checked = 0
    for _ in range(_QUADRATURE_TRIALS):
        point = {sym: _synth_scalar(rng, bounds[sym]) for sym in free}
        try:
            numeric = complex(integral.subs(point).evalf())
            claimed = complex(candidate.subs(point).evalf())
        except Exception:
            continue
        scale = max(abs(numeric), abs(claimed), 1.0)
        if abs(numeric - claimed) > 1e-6 * scale:
            return False
        checked += 1
    return True if checked else None


def residue_attempts(lhs, rhs, relation: str, domain: dict, bound_context,
                     params: dict) -> "ProofResult | None":
    """Intent:
        Replace every deferred `Integral` in the claim that a contour
        pattern can evaluate, adjudicate any disagreement with sympy's
        own integration numerically, and re-run the relation decision
        on the substituted claim.

    Notes:
        The trust policy: a contour value with every side condition
        discharged stands as exact. When sympy's `doit()` produces a
        different closed form, quadrature referees, the contour value
        must win numerically or this rung declines entirely (a contour
        value that loses to quadrature means a bug on our side, never
        material for a verdict). The sketch names the contour, the
        poles, and any disagreement, so the record carries the full
        derivation.
    """
    diff = lhs - rhs
    pv_apps = sorted((e for e in diff.atoms(sympy.core.function.AppliedUndef)
                      if e.func.__name__ == "P.V." and len(e.args) == 1
                      and isinstance(e.args[0], sympy.Integral)),
                     key=sympy.default_sort_key)
    integrals = sorted((i for i in diff.atoms(sympy.Integral)
                        if not any(i == app.args[0] for app in pv_apps)),
                       key=sympy.default_sort_key)
    if not integrals and not pv_apps:
        return None
    substitutions = {}
    notes = []
    pattern_names = []
    disagreements = []
    for app in pv_apps:
        # no doit referee here: sympy's principal_value already had its
        # turn in the decision preamble, and there is no direct numeric
        # quadrature for a divergent-at-the-pole integrand, the
        # half-residue value stands on its own discharged conditions.
        outcome = _evaluate_pv(app.args[0], domain, params)
        if outcome is None:
            continue
        value, sketch = outcome
        substitutions[app] = value
        pattern_names.append("pv_indented")
        notes.append(sketch)
    for integral in integrals:
        outcome = evaluate_integral(integral, domain, params)
        if outcome is None:
            continue
        value, name, sketch = outcome
        try:
            sympy_value = integral.doit(deep=True)
        except Exception:
            sympy_value = None
        if sympy_value is not None and not sympy_value.has(sympy.Integral):
            try:
                agree = sympy.simplify(sympy_value - value) == 0
            except Exception:
                agree = False
            if not agree:
                if _numeric_agreement(integral, value, domain, params) is not True:
                    return None
                notes.append("sympy's symbolic integration gave "
                             f"{_humanize(sympy_value)} for the same integral; "
                             "numeric quadrature confirms the contour value "
                             "and rejects it")
                disagreements.append({
                    "integral": str(integral),
                    "sympy": str(sympy_value),
                    "contour": str(value),
                    "referee": "quadrature",
                })
        substitutions[integral] = value
        pattern_names.append(name)
        notes.append(sketch)
    if not substitutions:
        return None
    new_lhs = lhs.xreplace(substitutions)
    new_rhs = rhs.xreplace(substitutions)
    result = _decide_relation(new_lhs, new_rhs, relation, domain,
                              bound_context, params)
    if result.status not in ("proven", "disproven"):
        return None
    meta = dict(result.meta)
    meta["mathema.derive_route"] = f"residue:{'+'.join(sorted(set(pattern_names)))}"
    if disagreements:
        meta["mathema.engine_disagreement"] = disagreements
    return ProofResult(result.status,
                       sketch="; ".join(notes) + f"; {result.sketch}",
                       counterexample=result.counterexample,
                       witness=result.witness,
                       quantifier=result.quantifier, meta=meta)
