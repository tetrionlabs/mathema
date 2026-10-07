# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim words whose exact value is irrational or needs more than
one elimination: `rank`, `pinv`, `eigvals`, `eigvalsh`, `cond` and the
spectral matrix norms, computed from the matrix's exact entries.

A rank and a pseudoinverse are rational, so they are computed exactly
(Gaussian elimination over the rationals, and a rank factorization).
An eigenvalue is a root of the characteristic polynomial, which has
integer coefficients once the matrix is scaled by the common
denominator of its entries: each root of its square-free part is
approximated to 60 significant digits and certified by an inclusion
disk computed in exact arithmetic (see `_certified`), so the value
rounded to a float is the root's own rounding. A value that cannot be
certified raises `Untrusted`, which leaves the point undecided rather
than decided on a float.
"""
from __future__ import annotations

import math
from fractions import Fraction

__all__ = ["Untrusted", "eigvals", "eigvalsh", "pinv", "rank", "singular_values"]

#: digits the root approximations carry
_DIGITS = 60
#: the largest radius, relative to the root, a certifying disk may have
_WIDTH = Fraction(1, 10 ** 35)


class Untrusted(ArithmeticError):
    """A claim word whose exact value could not be certified at this
    point; the point is left undecided."""


def _lcm_denominator(rows) -> int:
    d = 1
    for row in rows:
        for v in row:
            d = math.lcm(d, v.denominator)
    return d


def _echelon(rows):
    """`(reduced rows, pivot columns)`: the reduced row echelon form of
    a matrix of exact rationals, its zero rows dropped."""
    m = [list(r) for r in rows]
    pivots: list = []
    r = 0
    cols = len(m[0]) if m else 0
    for c in range(cols):
        p = next((i for i in range(r, len(m)) if m[i][c] != 0), None)
        if p is None:
            continue
        m[r], m[p] = m[p], m[r]
        lead = m[r][c]
        m[r] = [v / lead for v in m[r]]
        for i in range(len(m)):
            if i != r and m[i][c] != 0:
                f = m[i][c]
                m[i] = [a - f * b for a, b in zip(m[i], m[r])]
        pivots.append(c)
        r += 1
        if r == len(m):
            break
    return m[:r], pivots


def rank(rows) -> int:
    """The rank of a matrix of exact rationals."""
    return len(_echelon(rows)[1]) if rows and rows[0] else 0


def _transpose(rows):
    return [list(c) for c in zip(*rows)]


def _matmul(a, b):
    return [[sum((x * y for x, y in zip(row, col)), Fraction(0))
             for col in zip(*b)] for row in a]


def _inverse(rows):
    from ._linalg_eval import _exact_identity, _exact_solve
    return _exact_solve(rows, _exact_identity(len(rows)))


def pinv(rows):
    """The Moore-Penrose pseudoinverse of a matrix of exact rationals,
    exact: with `A = C F` a rank factorization (`C` the pivot columns of
    `A`, `F` the nonzero rows of its reduced echelon form), `pinv(A) =
    F.T (F F.T)^-1 (C.T C)^-1 C.T`; the zero matrix for rank 0."""
    m, n = len(rows), len(rows[0])
    F, pivots = _echelon(rows)
    if not pivots:
        return [[Fraction(0)] * m for _ in range(n)]
    C = [[row[c] for c in pivots] for row in rows]
    Ct = _transpose(C)
    Ft = _transpose(F)
    left = _matmul(Ft, _inverse(_matmul(F, Ft)))
    right = _matmul(_inverse(_matmul(Ct, C)), Ct)
    return _matmul(left, right)


def _charpoly(rows) -> "tuple[list[int], int]":
    """`(coefficients, d)`: the integer characteristic polynomial of `d`
    times the square matrix `rows`, `d` the common denominator of its
    entries, highest degree first. Its roots are `d` times the
    eigenvalues."""
    from sympy import ZZ
    from sympy.polys.matrices import DomainMatrix
    d = _lcm_denominator(rows)
    n = len(rows)
    scaled = DomainMatrix([[ZZ(int(v * d)) for v in row] for row in rows],
                          (n, n), ZZ)
    return [int(c) for c in scaled.charpoly()], d


def _mpf_fraction(v) -> Fraction:
    """An mpmath real as the exact rational it holds."""
    sign, man, exp, _ = v._mpf_
    value = Fraction(int(man)) * (Fraction(2) ** int(exp))
    return -value if sign else value


def _factors(coeffs):
    """The square-free factors of an integer polynomial, each as
    `(integer coefficients, multiplicity)`."""
    from sympy import Poly, Symbol
    x = Symbol("x")
    _, factors = Poly(coeffs, x).sqf_list()
    return [([int(c) for c in q.all_coeffs()], m) for q, m in factors]


def _value_and_slope(coeffs, re: Fraction, im: Fraction):
    """`p(z)` and `p'(z)` at `z = re + i im`, exactly, each as a pair
    of rationals (real part, imaginary part), by Horner's rule."""
    zero = Fraction(0)
    p = (zero, zero)
    dp = (zero, zero)
    for c in coeffs:
        dp = (dp[0] * re - dp[1] * im + p[0], dp[0] * im + dp[1] * re + p[1])
        p = (p[0] * re - p[1] * im + c, p[0] * im + p[1] * re)
    return p, dp


def _certified(coeffs, approx) -> list:
    """Intent:
        The roots of the square-free integer polynomial `coeffs`, one per
        approximation in `approx`, each certified: the disk around an
        approximation `z` of radius `n |p(z) / p'(z)|` (`n` the degree)
        holds a root, the radius is at most 1e-35 of `|z|`, and the disks
        are disjoint, so each holds exactly one. An approximation whose
        imaginary part is negligible is taken on the real axis, where a
        disk holding exactly one root holds a real one (roots of a real
        polynomial come in conjugate pairs).

    Raises:
        Untrusted: a disk is too wide, or two disks meet.
    """
    import mpmath
    n = len(coeffs) - 1
    scale = max(abs(z) for z in approx) or 1
    centres, radii = [], []
    for z in approx:
        im = mpmath.im(z)
        real = abs(im) <= scale * mpmath.mpf(10) ** (-_DIGITS // 2)
        re_ = _mpf_fraction(mpmath.mpf(mpmath.re(z)))
        im_ = Fraction(0) if real else _mpf_fraction(mpmath.mpf(im))
        p, dp = _value_and_slope(coeffs, re_, im_)
        slope = dp[0] ** 2 + dp[1] ** 2
        if slope == 0:
            raise Untrusted("a root approximation sits where the "
                            "polynomial's slope is 0")
        radius2 = n * n * (p[0] ** 2 + p[1] ** 2) / slope
        size2 = re_ ** 2 + im_ ** 2
        if radius2 > max(size2 * _WIDTH ** 2, Fraction(1, 10 ** 600)):
            raise Untrusted("a root of the characteristic polynomial "
                            "did not certify")
        centres.append((re_, im_))
        radii.append(radius2)
    for i in range(len(centres)):
        for j in range(i + 1, len(centres)):
            gap = (centres[i][0] - centres[j][0]) ** 2 \
                + (centres[i][1] - centres[j][1]) ** 2
            if gap <= 2 * (radii[i] + radii[j]):
                raise Untrusted("two roots of the characteristic "
                                "polynomial could not be separated")
    return [mpmath.mpf(mpmath.re(z)) if c[1] == 0 else mpmath.mpc(z)
            for z, c in zip(approx, centres)]


#: the most Newton steps a root's refinement takes
_NEWTON_STEPS = 60


def _newton(q, z):
    """One root of the integer polynomial `q` by Newton's method from
    the mpmath number `z`, to the working precision, or None when a step
    meets a zero slope or the iteration does not settle."""
    import mpmath
    tolerance = mpmath.mpf(10) ** (-_DIGITS + 5)
    if mpmath.im(z) == 0:
        z = mpmath.re(z)
    for _ in range(_NEWTON_STEPS):
        value, slope = mpmath.polyval(q, z, derivative=True)
        if slope == 0:
            return None
        step = value / slope
        z -= step
        if abs(step) <= tolerance * max(abs(z), 1):
            return z
    return None


def _refined(q, start: list) -> "list | None":
    """The roots of the square-free integer polynomial `q` from the
    approximations `start` (mpmath numbers, possibly more than its
    degree, as for one factor among several): each refined by Newton's
    method, the ones that settle on the same root counted once. None
    unless exactly one root per degree of `q` results."""
    import mpmath
    found: list = []
    close = mpmath.mpf(10) ** (-_DIGITS // 2)
    for z in start:
        root = _newton(q, z)
        if root is None:
            continue
        if any(abs(root - r) <= close * max(abs(r), 1) for r in found):
            continue
        found.append(root)
    return found if len(found) == len(q) - 1 else None


def _factor_roots(q, start) -> list:
    """The certified roots of one square-free factor `q`: refined from
    `start` when that gives one root per degree, else found by mpmath's
    polyroots.

    Raises:
        Untrusted: a root that cannot be certified.
    """
    import mpmath
    if len(q) == 2:
        # a linear factor's root is the rational -q[1] / q[0], exactly
        root = Fraction(-q[1], q[0])
        return [mpmath.mpf(root.numerator) / root.denominator]
    bits = max(abs(c).bit_length() for c in q)
    refined = None
    if start:
        # the polynomial's value cancels across coefficients of `bits`
        # bits, so Newton's steps are taken with that many bits to spare
        with mpmath.workprec(mpmath.mp.prec + 2 * bits):
            refined = _refined(q, start)
    if refined is not None:
        # converged approximations that do not certify are roots too
        # close to separate at this precision, which no other root
        # finder separates either
        return _certified(q, refined)
    try:
        found = mpmath.polyroots(q, maxsteps=400,
                                 extraprec=max(4 * _DIGITS, 2 * bits))
    except mpmath.libmp.libhyper.NoConvergence as e:
        raise Untrusted("the characteristic polynomial's roots did not "
                        "converge") from e
    return _certified(q, found)


def _roots(coeffs, real_only: bool, start=None, scale: int = 1) -> list:
    """Intent:
        Every root of an integer polynomial, with multiplicity, as
        mpmath numbers, each certified (see `_certified`). `start` are
        approximations of the roots divided by `scale` (an eigenvalue
        routine's), refined by Newton's method on each square-free
        factor; a factor they do not settle is solved by mpmath's
        polyroots.

    Raises:
        Untrusted: a root that cannot be certified, or a complex root
            when `real_only`.
    """
    import mpmath
    with mpmath.workdps(_DIGITS):
        seeds = [mpmath.mpmathify(z) * scale for z in start or ()]
        # each trailing zero coefficient is a root at 0, exactly
        zeros = 0
        while len(coeffs) > 1 and coeffs[-1] == 0:
            coeffs = coeffs[:-1]
            zeros += 1
        out: list = [mpmath.mpf(0)] * zeros
        for q, mult in _factors(coeffs):
            if len(q) == 1:
                continue
            roots = _factor_roots(q, seeds)
            if real_only and any(isinstance(r, mpmath.mpc) for r in roots):
                raise Untrusted("a complex root where every root is real")
            out += [r for r in roots for _ in range(mult)]
        return out


def _to_number(v):
    """An mpmath value as the float nearest it; beyond float range a
    rational of its digits; a complex value as a complex float."""
    import mpmath
    from ._linalg_eval import _rounded
    if isinstance(v, mpmath.mpc):
        if v.imag == 0:
            v = v.real
        else:
            return complex(float(v.real), float(v.imag))
    return _rounded(_mpf_fraction(mpmath.mpf(v)))


def _float_start(rows, routine: str) -> "list | None":
    """numpy's float eigenvalues of `rows` (`routine` "eigvals" or
    "eigvalsh"), the starting points the roots are refined from; None
    when the matrix does not fit in floats or numpy fails."""
    import numpy as np
    try:
        a = np.array([[float(v) for v in row] for row in rows])
        if not np.isfinite(a).all():
            return None
        return list(getattr(np.linalg, routine)(a))
    except (OverflowError, np.linalg.LinAlgError, ValueError):
        return None


def _gram_start(rows) -> "list | None":
    """The squares of numpy's float singular values of `rows`, as
    mpmath numbers (so a square beyond float range stays finite), the
    starting points for the eigenvalues of its Gram matrix; None when
    the matrix does not fit in floats or numpy fails."""
    import mpmath
    import numpy as np
    try:
        a = np.array([[float(v) for v in row] for row in rows])
        if not np.isfinite(a).all():
            return None
        return [mpmath.mpf(float(s)) ** 2
                for s in np.linalg.svd(a, compute_uv=False)]
    except (OverflowError, np.linalg.LinAlgError, ValueError):
        return None


def eigvalsh(rows) -> list:
    """The eigenvalues of a symmetric matrix read from its lower
    triangle, ascending, each certified and rounded once."""
    import mpmath
    n = len(rows)
    sym = [[rows[max(i, j)][min(i, j)] for j in range(n)] for i in range(n)]
    coeffs, d = _charpoly(sym)
    start = _float_start(sym, "eigvalsh")
    with mpmath.workdps(_DIGITS):
        return [_to_number(r / d)
                for r in sorted(_roots(coeffs, True, start, d))]


def eigvals(rows) -> list:
    """The eigenvalues of a square matrix, sorted by real then
    imaginary part, each certified and rounded once."""
    import mpmath
    coeffs, d = _charpoly(rows)
    start = _float_start(rows, "eigvals")
    with mpmath.workdps(_DIGITS):
        roots = [r / d for r in _roots(coeffs, False, start, d)]
        roots.sort(key=lambda r: (mpmath.re(r), mpmath.im(r)))
        return [_to_number(r) for r in roots]


def singular_values(rows) -> list:
    """The singular values of a matrix, descending, as mpmath numbers
    (60 digits, from certified eigenvalues of its Gram matrix)."""
    import mpmath
    m, n = len(rows), len(rows[0])
    t = _transpose(rows)
    gram = _matmul(t, rows) if m >= n else _matmul(rows, t)
    coeffs, d = _charpoly(gram)
    start = _gram_start(rows)
    with mpmath.workdps(_DIGITS):
        values = [max(r / d, mpmath.mpf(0))
                  for r in _roots(coeffs, True, start, d)]
        return sorted((mpmath.sqrt(v) for v in values), reverse=True)


def from_mp(v):
    """`_to_number` for a caller outside this module."""
    return _to_number(v)
