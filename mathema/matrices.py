# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Matrix structure properties, in one place.

A matrix value can carry structure a scalar cannot: it may be
symmetric, triangular, positive-definite, orthogonal, or simply
finite. Three questions are asked of that structure, by three callers:

- does a value HAVE the property (the claim family, the runtime
  guard),
- how to SYNTHESISE a value that has it (the sampler, under a marker
  or an `assuming` premise),
- what weaker properties it ENTAILS (a positive-definite matrix is
  symmetric), so declaring one narrows the domain to all it implies.

`MatrixProperty` answers all three, and `PROPERTIES` is the registry
every surface reads, so a property's meaning lives in exactly one
place. The checks are numpy-fast when numpy is importable and fall
back to pure Python otherwise, except the spectral ones (eigenvalues,
definiteness), which have no cheap pure-Python form and decline
(`None`) rather than compute an unsound answer. numpy is not a
runtime dependency of mathema, only a fast path when present.
`is_finite` and `is_real` read a number (an int, a bool, a float, a
complex, a Fraction or a Decimal), or a vector or matrix of numbers,
by value and identically with or without numpy: a number is finite
when it is neither an infinity nor a NaN (a complex one when both
parts are), and real unless it is a complex number with a nonzero
imaginary part. An empty vector or matrix is finite and real. Any
other value (None, a string, a ragged nesting) is undecided, "the
result is not a number".

The hierarchy `level` names, cheapest first, is the taxonomy the whole
feature is organised around:

    finite          every entry is a real, non-nan, finite number
    elementwise     a relation between entries (a_ij == a_ji)
    structural      a whole-matrix identity (A == Aᵀ)
    spectral        an eigenvalue condition (λ_i > 0)
    quadratic-form  xᵀAx > 0 for all x, decided soundly by Cholesky
"""
from __future__ import annotations

import cmath
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction


def _numpy():
    """numpy if importable, else None: the one guarded import every
    check and synth routes through, so a numpy-free environment degrades
    in exactly one place."""
    try:
        import numpy
        return numpy
    except Exception:
        return None


def _as_rows(m) -> "list | None":
    """A matrix value as a list of equal-length rows of numbers, or
    None when it is not a rectangular 2-D numeric nested sequence (a
    scalar, a ragged list, a 1-D vector). The shape every pure-Python
    check agrees on before it runs."""
    if not isinstance(m, (list, tuple)) or not m:
        return None
    rows = []
    width = None
    for row in m:
        if not isinstance(row, (list, tuple)):
            return None
        if width is None:
            width = len(row)
        elif len(row) != width:
            return None
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               for v in row):
            return None
        rows.append(list(row))
    return rows if width else None


def _square(rows: list) -> bool:
    return bool(rows) and all(len(r) == len(rows) for r in rows)


# --- checks: (value) -> bool | None ----------------------------------
# None means "cannot decide this shape" (a non-square value for a
# symmetry check, a spectral check with no numpy), never a guess.

_TOL = 1e-9


#: why `is_finite` or `is_real` leaves a value undecided when it is not
#: a number, nor a vector or matrix of numbers
NOT_A_NUMBER = "the result is not a number"

_NUMBER_TYPES = (int, float, complex, Fraction, Decimal)


def _plain(v):
    """A numpy scalar as the Python value it holds and a numpy array as
    nested lists; any other value unchanged."""
    np = _numpy()
    if np is not None and isinstance(v, (np.ndarray, np.generic)):
        return v.tolist()
    return v


def _nested(seq) -> "tuple | None":
    """`(entries, shape)` of a list or tuple nested to a uniform depth
    with the same length at every level, whose innermost elements are
    all numbers (an int, a bool, a float, a complex, a Fraction or a
    Decimal, numpy scalars included); None for any other value. An
    empty list has no entries and shape `(0,)`."""
    items = [_plain(v) for v in seq]
    if items and all(isinstance(v, (list, tuple)) for v in items):
        parts = [_nested(v) for v in items]
        if any(p is None for p in parts):
            return None
        shapes = {p[1] for p in parts}
        if len(shapes) != 1:
            return None
        return ([e for p in parts for e in p[0]],
                (len(items), *shapes.pop()))
    if not all(isinstance(v, _NUMBER_TYPES) for v in items):
        return None
    return items, (len(items),)


def _entries(m) -> "list | None":
    """The numbers `m` holds: `[m]` for a single number, every entry of
    a vector, matrix or deeper rectangular nesting of numbers (none
    for an empty one), the entries of an array-like value (a pandas or
    polars series) read through numpy; None for any other value
    (None, a string, a dict, a ragged or partly non-numeric
    nesting)."""
    m = _plain(m)
    if isinstance(m, _NUMBER_TYPES):
        return [m]
    if not isinstance(m, (list, tuple, str, bytes, dict)) \
            and hasattr(m, "__array__"):
        np = _numpy()
        if np is None:
            return None
        try:
            m = np.asarray(m).tolist()
        except (ValueError, TypeError):
            return None
        if isinstance(m, _NUMBER_TYPES):
            return [m]
    if not isinstance(m, (list, tuple)):
        return None
    got = _nested(m)
    return None if got is None else got[0]


def holds_complex(value) -> bool:
    """Whether `value` is a complex number, or a vector or matrix with a
    complex entry (a complex numpy array included)."""
    entries = _entries(value)
    return entries is not None and any(isinstance(v, complex)
                                       for v in entries)


def is_numeric(value) -> bool:
    """Whether `value` is a number, or a vector, matrix or deeper
    rectangular nesting of numbers, the values `is_finite` and
    `is_real` decide."""
    return _entries(value) is not None


def _finite_value(v) -> bool:
    """Whether the number `v` is finite: an int, a bool or a Fraction
    always is; a float or a Decimal when it is neither an infinity nor
    a NaN; a complex when both its parts are."""
    if isinstance(v, (int, Fraction)):
        return True
    if isinstance(v, Decimal):
        return v.is_finite()
    if isinstance(v, complex):
        return cmath.isfinite(v)
    return math.isfinite(v)


def _real_value(v) -> bool:
    """Whether the number `v` is real: not a complex, or a complex with
    a zero imaginary part."""
    return not isinstance(v, complex) or v.imag == 0


def _check_finite(m) -> "bool | None":
    """Whether every number `m` holds is finite (see `_finite_value`);
    an empty vector or matrix is (no entry is infinite or NaN). None
    when `m` is not a number nor a nesting of numbers (`NOT_A_NUMBER`).
    The same reading with or without numpy."""
    entries = _entries(m)
    if entries is None:
        return None
    return all(_finite_value(v) for v in entries)


def _check_real(m) -> "bool | None":
    """Whether every number `m` holds is real, read by value: an int,
    a bool, a float, a Fraction or a Decimal is real, and a complex
    number is real when its imaginary part is zero (`1 + 0j` is,
    `1 + 2j` and `complex(0, nan)` are not); an empty vector or matrix
    is. None when `m` is not a number nor a nesting of numbers
    (`NOT_A_NUMBER`). The same reading with or without numpy."""
    entries = _entries(m)
    if entries is None:
        return None
    return all(_real_value(v) for v in entries)


def _pairwise(m, rel) -> "bool | None":
    rows = _as_rows(m)
    if rows is None or not _square(rows):
        return None
    n = len(rows)
    return all(rel(rows[i][j], rows[j][i], i, j)
               for i in range(n) for j in range(n))


def _check_symmetric(m) -> "bool | None":
    if holds_complex(m):
        return None      # a complex matrix: real matrices only
    np = _numpy()
    if np is not None:
        try:
            a = np.asarray(m, dtype=float)
        except (ValueError, TypeError):
            return None
        if a.ndim != 2 or a.shape[0] != a.shape[1]:
            return None
        return bool(np.allclose(a, a.T, atol=_TOL))
    return _pairwise(m, lambda x, y, i, j: abs(x - y) <= _TOL)


def _check_skew(m) -> "bool | None":
    if holds_complex(m):
        return None      # a complex matrix: real matrices only
    np = _numpy()
    if np is not None:
        try:
            a = np.asarray(m, dtype=float)
        except (ValueError, TypeError):
            return None
        if a.ndim != 2 or a.shape[0] != a.shape[1]:
            return None
        return bool(np.allclose(a, -a.T, atol=_TOL))
    return _pairwise(m, lambda x, y, i, j: abs(x + y) <= _TOL)


def _triangular(m, upper: bool) -> "bool | None":
    rows = _as_rows(m)
    if rows is None or not _square(rows):
        return None
    n = len(rows)
    for i in range(n):
        for j in range(n):
            below = (j < i) if upper else (j > i)
            if below and abs(rows[i][j]) > _TOL:
                return False
    return True


def _check_diagonal(m) -> "bool | None":
    up = _triangular(m, upper=True)
    lo = _triangular(m, upper=False)
    if up is None or lo is None:
        return None
    return up and lo


def _check_identity(m) -> "bool | None":
    rows = _as_rows(m)
    if rows is None or not _square(rows):
        return None
    n = len(rows)
    return all(abs(rows[i][j] - (1.0 if i == j else 0.0)) <= _TOL
               for i in range(n) for j in range(n))


def _check_orthogonal(m) -> "bool | None":
    if holds_complex(m):
        return None      # a complex matrix: real matrices only
    np = _numpy()
    if np is None:
        return None      # QᵀQ == I needs a matrix product; decline
    try:
        a = np.asarray(m, dtype=float)
    except (ValueError, TypeError):
        return None
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        return None
    return bool(np.allclose(a.T @ a, np.eye(a.shape[0]), atol=_TOL))


def _check_positive_definite(m) -> "bool | None":
    if holds_complex(m):
        return None      # a complex matrix: real matrices only
    np = _numpy()
    if np is None:
        return None      # sound PD test needs eigen/Cholesky
    try:
        a = np.asarray(m, dtype=float)
    except (ValueError, TypeError):
        return None
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        return None
    if not np.allclose(a, a.T, atol=_TOL):
        return False     # PD is defined for symmetric matrices
    try:
        np.linalg.cholesky(a)   # succeeds iff symmetric positive-definite
        return True
    except np.linalg.LinAlgError:
        return False


def _check_positive_semidefinite(m) -> "bool | None":
    if holds_complex(m):
        return None      # a complex matrix: real matrices only
    np = _numpy()
    if np is None:
        return None
    try:
        a = np.asarray(m, dtype=float)
    except (ValueError, TypeError):
        return None
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        return None
    if not np.allclose(a, a.T, atol=_TOL):
        return False
    return bool((np.linalg.eigvalsh(a) >= -_TOL).all())


# --- synth: (n, rng) -> a matrix WITH the property -------------------

def _rand(n: int, rng: random.Random) -> list:
    return [[rng.uniform(-5, 5) for _ in range(n)] for _ in range(n)]


def _synth_general(n, rng):
    return _rand(n, rng)


def _synth_symmetric(n, rng):
    b = _rand(n, rng)
    return [[(b[i][j] + b[j][i]) / 2.0 for j in range(n)] for i in range(n)]


def _synth_skew(n, rng):
    b = _rand(n, rng)
    return [[(b[i][j] - b[j][i]) / 2.0 for j in range(n)] for i in range(n)]


def _synth_upper(n, rng):
    b = _rand(n, rng)
    return [[b[i][j] if j >= i else 0.0 for j in range(n)] for i in range(n)]


def _synth_lower(n, rng):
    b = _rand(n, rng)
    return [[b[i][j] if j <= i else 0.0 for j in range(n)] for i in range(n)]


def _synth_diagonal(n, rng):
    return [[rng.uniform(-5, 5) if i == j else 0.0 for j in range(n)]
            for i in range(n)]


def _synth_identity(n, rng):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _synth_positive_definite(n, rng):
    # BᵀB + nI is symmetric positive-definite by construction, the nI
    # shift keeping it clear of the singular boundary
    b = _rand(n, rng)
    bt_b = [[sum(b[k][i] * b[k][j] for k in range(n)) for j in range(n)]
            for i in range(n)]
    for i in range(n):
        bt_b[i][i] += n
    return bt_b


def _synth_orthogonal(n, rng):
    np = _numpy()
    if np is None:
        return _synth_identity(n, rng)   # the one orthogonal matrix in reach
    # QR of a random matrix gives a uniformly-random orthogonal Q
    q, _ = np.linalg.qr(np.asarray(_rand(n, rng)))
    return q.tolist()


def _synth_finite(n, rng):
    return _rand(n, rng)


def _synth_singular(n, rng):
    # a random matrix with one row or one column zeroed: the
    # determinant is exactly zero, and elimination meets an exactly
    # zero pivot, so a solver reports it singular rather than returning
    # a huge but finite inverse
    m = _rand(n, rng)
    k = rng.randrange(n)
    if rng.random() < 0.5:
        m[k] = [0.0] * n
    else:
        for row in m:
            row[k] = 0.0
    return m


#: one draw in this many of an unstructured matrix is rank-deficient
RANK_EDGE_EVERY = 8


def rank_edge(m, draw: int):
    """The matrix `m` with one row zeroed when `draw` is one of the
    rank-deficient draws (every `RANK_EDGE_EVERY`-th, the row chosen by
    the draw's own index), its diagonal shifted so the trace is zero on
    the draw half a period later (a square `m` only), else `m`
    unchanged. A random matrix is full rank and has a nonzero trace
    with probability one, so a claim false only where the rank drops
    (`det(A @ A.T) > 0`) or the trace vanishes (`A / trace(A)`) needs
    its edge drawn on purpose, the way the scalar probe draws its
    boundary values."""
    if not m or not isinstance(m, list) or not isinstance(m[0], list):
        return m
    phase = draw % RANK_EDGE_EVERY
    if phase == RANK_EDGE_EVERY // 2 - 1 and len(m) == len(m[0]) and len(m) > 1:
        try:
            shift = sum(float(m[i][i]) for i in range(len(m))) / len(m)
        except (TypeError, ValueError):
            return m
        if shift != shift or shift in (float("inf"), float("-inf")):
            return m
        out = [list(row) for row in m]
        for i in range(len(m)):
            out[i][i] = float(m[i][i]) - shift
        # the shift can leave a rounding residue; the last entry takes it
        residue = sum(out[i][i] for i in range(len(m)))
        out[-1][-1] -= residue
        return out
    if phase != RANK_EDGE_EVERY - 1:
        return m
    k = (draw // RANK_EDGE_EVERY) % len(m)
    return [[0.0] * len(row) if i == k else row for i, row in enumerate(m)]


# --- the registry ----------------------------------------------------

@dataclass(frozen=True)
class MatrixProperty:
    """One named matrix property: how to check it, synthesise a value
    with it, and what it entails. `check(M)` returns `bool | None`
    (None = undecidable for this value or without numpy); `synth(n,
    rng)` builds an n-by-n value that has it; `implies` are the weaker
    properties it entails, so declaring this one narrows the domain to
    all of them."""

    name: str
    level: str
    check: Callable
    synth: Callable
    implies: frozenset = field(default_factory=frozenset)


PROPERTIES: dict = {
    p.name: p for p in (
        MatrixProperty("is_finite", "finite", _check_finite, _synth_finite),
        MatrixProperty("is_real", "finite", _check_real, _synth_general),
        MatrixProperty("is_symmetric", "structural", _check_symmetric,
                       _synth_symmetric),
        MatrixProperty("is_skew_symmetric", "structural", _check_skew,
                       _synth_skew),
        MatrixProperty("is_upper_triangular", "elementwise",
                       lambda m: _triangular(m, upper=True), _synth_upper),
        MatrixProperty("is_lower_triangular", "elementwise",
                       lambda m: _triangular(m, upper=False), _synth_lower),
        MatrixProperty("is_diagonal", "elementwise", _check_diagonal,
                       _synth_diagonal,
                       implies=frozenset({"is_upper_triangular",
                                          "is_lower_triangular",
                                          "is_symmetric"})),
        MatrixProperty("is_identity", "elementwise", _check_identity,
                       _synth_identity,
                       implies=frozenset({"is_diagonal", "is_symmetric",
                                          "is_upper_triangular",
                                          "is_lower_triangular",
                                          "is_orthogonal",
                                          "is_positive_definite"})),
        MatrixProperty("is_orthogonal", "spectral", _check_orthogonal,
                       _synth_orthogonal),
        MatrixProperty("is_positive_definite", "quadratic-form",
                       _check_positive_definite, _synth_positive_definite,
                       implies=frozenset({"is_symmetric",
                                          "is_positive_semidefinite"})),
        MatrixProperty("is_positive_semidefinite", "quadratic-form",
                       _check_positive_semidefinite,
                       _synth_positive_definite,
                       implies=frozenset({"is_symmetric"})),
    )
}


def synth_for(props, n: int, rng: random.Random, tries: int = 40):
    """A square n-by-n matrix that has EVERY property in `props`.
    Picks the most specific declared property (the one whose entailed
    closure covers the most of the set) and synthesises from it, since
    a specific property's value already satisfies what it implies
    (a positive-definite matrix is symmetric); any residual properties
    are met by rejection over `tries`. Returns the best matrix found,
    or a generic one when `props` is empty. A property with no
    checkable form without numpy (spectral) cannot be rejection-
    verified, so its synth is trusted by construction."""
    names = set(props)
    if not names:
        return _rand(n, rng)
    ordered = sorted(names, key=lambda p: -len(entailed([p]) & names))
    lead = PROPERTIES[ordered[0]]
    best = None
    for _ in range(tries):
        m = lead.synth(n, rng)
        if all(PROPERTIES[p].check(m) is not False for p in names):
            return m
        best = m
    return best



def entailed(names) -> set:
    """The transitive closure of `implies` over the given property
    names: declaring `is_positive_definite` also asserts
    `is_symmetric` (and, through it, nothing further), so the domain
    narrows to every property entailed, not just the one written."""
    out: set = set()
    stack = list(names)
    while stack:
        name = stack.pop()
        if name in out or name not in PROPERTIES:
            continue
        out.add(name)
        stack.extend(PROPERTIES[name].implies)
    return out
