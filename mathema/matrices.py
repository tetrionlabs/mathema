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

The hierarchy `level` names, cheapest first, is the taxonomy the whole
feature is organised around:

    finite          every entry is a real, non-nan, finite number
    elementwise     a relation between entries (a_ij == a_ji)
    structural      a whole-matrix identity (A == Aᵀ)
    spectral        an eigenvalue condition (λ_i > 0)
    quadratic-form  xᵀAx > 0 for all x, decided soundly by Cholesky
"""
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field


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


def _check_finite(m) -> "bool | None":
    np = _numpy()
    if np is not None:
        try:
            arr = np.asarray(m, dtype=float)
        except (ValueError, TypeError):
            return None
        return bool(np.isfinite(arr).all())
    rows = _as_rows(m)
    if rows is None:
        # a 1-D numeric sequence is still finite-checkable
        if isinstance(m, (list, tuple)) and m and all(
                not isinstance(v, bool) and isinstance(v, (int, float))
                for v in m):
            return all(v == v and abs(v) != float("inf") for v in m)
        return None
    return all(v == v and abs(v) != float("inf") for row in rows for v in row)


def _check_real(m) -> "bool | None":
    # in Python a float/int is already real; the property is meaningful
    # against complex entries, which _as_rows rejects, so a rectangular
    # numeric matrix is real by construction and a complex one is not
    np = _numpy()
    if np is not None:
        try:
            arr = np.asarray(m)
        except (ValueError, TypeError):
            return None
        return not np.iscomplexobj(arr)
    rows = _as_rows(m)
    return None if rows is None else True


def _pairwise(m, rel) -> "bool | None":
    rows = _as_rows(m)
    if rows is None or not _square(rows):
        return None
    n = len(rows)
    return all(rel(rows[i][j], rows[j][i], i, j)
               for i in range(n) for j in range(n))


def _check_symmetric(m) -> "bool | None":
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
