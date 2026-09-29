# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Evaluating a claim's vectors, matrices and tables.

A claim over vectors or matrices reads its operators the way numpy
does: `A @ B` is the matrix product, `*`, `+`, `-` and `**` act element
by element (a number scales or shifts every element), `abs(A)` is
elementwise, `matrix_power(A, k)` is the matrix power, and `norm(x)` is
the Euclidean norm of a vector and the Frobenius norm of a matrix. A
drawn vector or matrix is evaluated as a numpy array whatever the
function's own runtime type, so `x + y` never concatenates two lists;
the function still receives its argument as its own runtime type, and
what it returns is read back as an array.

`FUNCTIONS` is the one namespace every probe of a claim evaluates in:
the ordinary probe, the premise filter and the matrix structure
family. A table parameter (a pandas or polars DataFrame) is evaluated
as a `Table`, whose columns `df.returns` and `df["returns"]` are
vectors.
"""
from __future__ import annotations

import builtins
import math

from .matrices import _numpy

__all__ = ["FUNCTIONS", "Table", "as_array", "comparable", "from_law",
           "is_array", "largest_gap", "law_callable", "roundoff_allowance",
           "scalar", "shown", "to_law", "to_plain"]


def _np():
    np = _numpy()
    if np is None:
        raise ValueError("vector and matrix arithmetic needs numpy")
    return np


def is_array(value) -> bool:
    """Whether `value` is a numpy array."""
    np = _numpy()
    return np is not None and isinstance(value, np.ndarray)


class Table(dict):
    """A table in a claim: a dict of named columns, each a numpy
    vector, whose columns read as attributes (`df.returns`) or items
    (`df["returns"]`)."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                f"the table has no column {name!r} (columns: "
                f"{', '.join(self) or 'none'})") from None


_HOLED: list = []


def _holed(array, holes: dict):
    """`array` carrying the hole values its missing positions were drawn
    as (`None`, `pd.NA`), `{position: value}`, so the function receives
    them as drawn when the array goes back to a plain list; the array
    itself holds NaN there."""
    if not holes:
        return array
    if not _HOLED:
        np = _np()

        class HoledArray(np.ndarray):  # type: ignore[name-defined]
            """A float array with the hole values it stands for."""
            hole_values: dict = {}

        _HOLED.append(HoledArray)
    out = array.view(_HOLED[0])
    out.hole_values = dict(holes)
    return out


def _numbers(value) -> bool:
    from .runtime_types import abstract_of
    from .runtime_types._abstract import AbstractMat, AbstractVec
    return isinstance(abstract_of(value), (AbstractVec, AbstractMat))


def as_array(value):
    """Intent:
        A drawn value as the claim evaluates it: a vector or matrix of
        numbers (a list, nested lists, an array) as a float numpy
        array with NaN at each missing position, a dict of columns as
        a `Table`, anything else unchanged.
    """
    np = _numpy()
    if np is None:
        return value
    if isinstance(value, Table):
        return value
    if isinstance(value, dict):
        cols = {str(k): as_array(v) for k, v in value.items()}
        if cols and all(is_array(c) and c.ndim == 1 for c in cols.values()):
            return Table(cols)
        return value
    if is_array(value):
        return value.astype(float) if value.dtype.kind in "biu" else value
    if isinstance(value, (list, tuple)) and value and _numbers(value):
        from .domain import is_missing

        def kept(v):
            # a hole drawn as something other than a float NaN
            return is_missing(v) and not isinstance(v, float)
        if all(isinstance(r, (list, tuple)) for r in value):
            return _holed(np.array([[math.nan if is_missing(v) else float(v)
                                     for v in r] for r in value], dtype=float),
                          {(i, j): v for i, r in enumerate(value)
                           for j, v in enumerate(r) if kept(v)})
        return _holed(np.array([math.nan if is_missing(v) else float(v)
                                for v in value], dtype=float),
                      {(k,): v for k, v in enumerate(value) if kept(v)})
    return value


def to_plain(value):
    """Intent:
        An evaluated value as the plain value a function receives when
        its runtime type is a list: an array as a list (nested for a
        matrix), a `Table` as a dict of column lists. Anything else
        unchanged.
    """
    if isinstance(value, Table):
        return {k: to_plain(v) for k, v in value.items()}
    if is_array(value):
        out = value.tolist()
        for position, hole in (getattr(value, "hole_values", None) or {}).items():
            # the hole value the array was drawn with, back in its slot
            if len(position) == 1 and isinstance(out, list) and position[0] < len(out):
                out[position[0]] = hole
            elif len(position) == 2 and isinstance(out, list) \
                    and position[0] < len(out) and isinstance(out[position[0]], list) \
                    and position[1] < len(out[position[0]]):
                out[position[0]][position[1]] = hole
        return out
    return value


def to_law(value):
    """Intent:
        A value a function returned, as the claim reads it: a vector or
        matrix of numbers as an array (so the claim's `+` and `*` act
        on its elements), a dict of numeric columns as a `Table`, a
        numpy scalar as a Python number. Anything else unchanged.
    """
    if is_array(value):
        if value.ndim == 0:
            return value.item()
        return value
    np = _numpy()
    if np is not None and isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple, dict)):
        return as_array(value)
    return value


def scalar(value):
    """A 1-by-1 array as the number it holds; anything else
    unchanged."""
    if is_array(value) and value.shape == (1, 1):
        return value.item()
    return value


def shown(value):
    """Intent:
        An evaluated value as a counterexample shows it: arrays as
        lists, numpy numbers as Python numbers, a `Table` as a dict,
        element by element through lists and tuples.
    """
    np = _numpy()
    if isinstance(value, Table):
        return {k: shown(v) for k, v in value.items()}
    if is_array(value):
        return shown(value.tolist())
    if np is not None and isinstance(value, np.generic):
        return value.item()
    if isinstance(value, list):
        return [shown(v) for v in value]
    if isinstance(value, tuple):
        return tuple(shown(v) for v in value)
    return value


def from_law(value):
    """Intent:
        A value a claim computed, as the function's argument: arrays
        and tables become the plain lists the runtime type adapters
        realise. The inverse of `as_array`.
    """
    return to_plain(value)


def law_callable(fn, plain_args: bool = True):
    """Intent:
        `fn` as a claim calls it: arrays and tables among the arguments
        become plain lists first when `plain_args` (the runtime type
        adapters realise them from there), and the result is read back
        with `to_law`. Signature readers see `fn` itself.
    """
    import functools

    @functools.wraps(fn)
    def call(*args, **kwargs):
        if plain_args:
            args = tuple(from_law(a) for a in args)
            kwargs = {k: from_law(v) for k, v in kwargs.items()}
        return to_law(fn(*args, **kwargs))
    return call


def comparable(lv, rv):
    """Intent:
        Two evaluated sides as the relation compares them: a `Table`
        against a `Table` with the same columns becomes two matrices
        with one column each, in column-name order, compared element
        by element. Tables with different columns become two plain
        dicts, equal only when identical. Anything else unchanged.
    """
    if not (isinstance(lv, Table) or isinstance(rv, Table)):
        return lv, rv
    if isinstance(lv, Table) and isinstance(rv, Table) \
            and sorted(lv) == sorted(rv):
        np = _np()
        keys = sorted(lv)
        return (np.column_stack([lv[k] for k in keys]),
                np.column_stack([rv[k] for k in keys]))
    return to_plain(lv), to_plain(rv)


def largest_gap(lv, rv) -> float:
    """The largest absolute difference between two evaluated sides,
    element by element, ignoring positions that are not finite."""
    np = _numpy()
    if np is None:
        return 0.0
    try:
        gaps = np.abs(np.asarray(lv, dtype=float) - np.asarray(rv, dtype=float))
    except (TypeError, ValueError):
        return 0.0
    finite = gaps[np.isfinite(gaps)]
    return float(finite.max()) if finite.size else 0.0


#: how far each input moves, relatively, to measure a draw's round-off
_NUDGE = 2.0 ** -50
#: how many times the measured movement counts as round-off
_ROUNDOFF_FACTOR = 64.0


def roundoff_allowance(evaluate, env: dict, names, sides) -> float:
    """Intent:
        The round-off one draw of a claim can carry: every input named
        in `names` (arrays, table columns and float numbers) is moved
        by a few units in its last place, three times with fresh
        signs, and `evaluate(env)` recomputes both sides; the largest
        movement of each side, scaled by `_ROUNDOFF_FACTOR`, is how
        far the exact comparison may be off at this draw. 0.0 when no
        input is a float or no recomputation succeeds.

    Notes:
        A determinant of a product with entries near 1e6 and 1e-9
        moves by far more than its own value's last place, since the
        entries it cancels are large; the allowance measures that
        cancellation at the draw rather than assuming a scale.
    """
    import random
    np = _numpy()
    if np is None:
        return 0.0
    rng = random.Random(0x5EED)

    def nudged(value):
        if isinstance(value, Table):
            return Table({k: nudged(v) for k, v in value.items()})
        if is_array(value) and value.dtype.kind == "f":
            signs = np.array([rng.choice((-1.0, 1.0))
                              for _ in range(value.size)]).reshape(value.shape)
            return value * (1.0 + signs * _NUDGE)
        if isinstance(value, float):
            return value * (1.0 + rng.choice((-1.0, 1.0)) * _NUDGE)
        return value
    moved = [0.0, 0.0]
    for _ in range(3):
        jenv = dict(env)
        for name in names:
            if name in jenv:
                jenv[name] = nudged(jenv[name])
        try:
            with np.errstate(all="ignore"):
                new = evaluate(jenv)
        except Exception:
            continue
        for k in (0, 1):
            moved[k] = max(moved[k], largest_gap(new[k], sides[k]))
    return _ROUNDOFF_FACTOR * (moved[0] + moved[1])


def _is_array_arg(value) -> bool:
    return is_array(value) and value.ndim >= 1


# --- the vocabulary ---------------------------------------------------

def _abs(x):
    if _is_array_arg(x):
        return _np().abs(x)
    return builtins.abs(x)


def _norm(x, ord=None):
    """The Euclidean norm of a vector, the Frobenius norm of a matrix,
    or `numpy.linalg.norm`'s `ord` norm (`2` spectral, `1`, `inf`); the
    absolute value of a number. The Euclidean and Frobenius norms read
    the value slots, 0 over none."""
    if isinstance(x, (int, float, complex)) and not isinstance(x, bool):
        return builtins.abs(x)
    np = _np()
    a = as_array(x) if not is_array(x) else x
    if not is_array(a):
        raise TypeError(f"norm of {type(x).__name__}")
    if a.dtype.kind in "fc" and np.isnan(a).any() and ord is None:
        # over the value slots, a hole contributing nothing; 0 over none
        a = np.where(np.isnan(a), 0.0, a)
    # every norm is homogeneous, so it is computed on the array scaled
    # to its largest magnitude: squaring an entry near the float
    # maximum overflows where the norm itself does not
    scale = float(np.max(np.abs(a))) if a.size else 0.0
    if scale == 0.0 or not math.isfinite(scale):
        return float(np.linalg.norm(a) if ord is None
                     else np.linalg.norm(a, ord))
    unit = a / scale
    return scale * float(np.linalg.norm(unit) if ord is None
                         else np.linalg.norm(unit, ord))


def _holes(a) -> bool:
    """Whether an array holds a hole (a NaN position)."""
    np = _np()
    return bool(a.dtype.kind in "fc" and np.isnan(a).any())


#: the reductions with an identity, which they give over no value slot
_IDENTITY = {"sum": 0.0, "prod": 1.0}


def _over_values(numpy_name: str, a, axis=None, **kwargs):
    """A reduction over the value slots of `a`: numpy's NaN-skipping
    reduction. Over no value slot a reduction with an identity gives it
    (`sum` 0, `prod` 1) and one without gives a hole."""
    np = _np()
    out = getattr(np, "nan" + numpy_name)(a, axis=axis, **kwargs)
    empty = np.all(np.isnan(a), axis=axis)
    out = np.where(empty, _IDENTITY.get(numpy_name, np.nan), out)
    return out.item() if getattr(out, "ndim", 1) == 0 else out


def _reduction(builtin_fn, numpy_name):
    def reduce(*args, axis=None, **kwargs):
        if len(args) == 1 and _is_array_arg(args[0]):
            if _holes(args[0]):
                # over the value slots; a vector of holes reduces to one
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    return _over_values(numpy_name, args[0], axis=axis, **kwargs)
            out = getattr(_np(), numpy_name)(args[0], axis=axis, **kwargs)
            return out.item() if getattr(out, "ndim", 1) == 0 else out
        if axis is not None:
            raise TypeError(f"{numpy_name}(..., axis=) needs an array")
        return builtin_fn(*args, **kwargs)
    reduce.__name__ = numpy_name
    return reduce


def _mean(*args, axis=None):
    if len(args) == 1 and _is_array_arg(args[0]):
        if _holes(args[0]):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                return _over_values("mean", args[0], axis=axis)
        out = _np().mean(args[0], axis=axis)
        return out.item() if getattr(out, "ndim", 1) == 0 else out
    values = list(args[0]) if len(args) == 1 else list(args)
    return builtins.sum(values) / len(values)


def _prod(*args, axis=None):
    if len(args) == 1 and _is_array_arg(args[0]):
        if _holes(args[0]):
            return _over_values("prod", args[0], axis=axis)
        out = _np().prod(args[0], axis=axis)
        return out.item() if getattr(out, "ndim", 1) == 0 else out
    return math.prod(args[0] if len(args) == 1 else args)


def _values(args):
    """The one vector a reduction reads: its single argument as an
    array, or its several numeric arguments gathered into one."""
    np = _np()
    if len(args) == 1:
        a = args[0]
        return a if is_array(a) else np.asarray(as_array(a), dtype=float)
    return np.asarray(args, dtype=float)


def _moment(numpy_name):
    """`std` or `var` as numpy computes them over the value slots:
    `ddof` is subtracted from the number of value slots in the divisor
    (0 by default, the population statistic; 1 for the sample
    statistic), and `axis` reduces a matrix along one axis."""
    def moment(*args, ddof=0, axis=None):
        a = _values(args)
        if _holes(a):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                return _over_values(numpy_name, a, axis=axis, ddof=ddof)
        out = getattr(_np(), numpy_name)(a, ddof=ddof, axis=axis)
        return out.item() if getattr(out, "ndim", 1) == 0 else out
    moment.__name__ = numpy_name
    return moment


def _count(*args, axis=None):
    """The number of value slots: every element of a vector or matrix
    that is not a hole, or those along `axis` (one count per remaining
    index); `len` counts every slot."""
    a = _values(args)
    np = _np()
    present = ~np.isnan(a) if a.dtype.kind in "fc" else np.ones(a.shape, dtype=bool)
    if axis is None:
        return int(present.sum())
    counts = present.sum(axis=axis)
    return counts.astype(float) if a.ndim > 1 else int(counts)


def _cumulative(numpy_name):
    """`cumsum` or `cumprod`: the running sums or products over the
    value slots, a hole kept at its own position; a matrix read in row
    order without `axis`, along it with one."""
    def running(*args, axis=None):
        a = _values(args)
        np = _np()
        if _holes(a):
            out = getattr(np, "nan" + numpy_name)(a, axis=axis)
            holes = np.isnan(a) if axis is not None or a.ndim == 1 \
                else np.isnan(a).ravel()
            return np.where(holes, np.nan, out)
        return getattr(np, numpy_name)(a, axis=axis)
    running.__name__ = numpy_name
    return running


def _running_extremum(ufunc_name, word):
    """`cummax` or `cummin`: the running maximum or minimum, element
    `i` the greatest (least) of elements `0..i`; a matrix is read in
    row order without `axis`, along it with one."""
    def running(*args, axis=None):
        a = _values(args)
        if axis is None:
            a, axis = a.ravel(), 0
        return getattr(_np(), ufunc_name).accumulate(a, axis=axis)
    running.__name__ = word
    return running


def _median(*args, axis=None):
    """The median of the value slots: the middle element of the sorted
    values, or the mean of the middle two for an even count; along
    `axis` for a matrix; a hole when every slot is one."""
    a = _values(args)
    if _holes(a):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return _over_values("median", a, axis=axis)
    out = _np().median(a, axis=axis)
    return out.item() if getattr(out, "ndim", 1) == 0 else out


def _quantile(a, q):
    """The `q`-quantile of a vector's value slots (`0 <= q <= 1`),
    interpolated linearly between the two sorted values it falls
    between, as numpy and pandas compute it by default; a hole when
    every slot is one."""
    values = _values((a,))
    if _holes(values):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return _over_values("quantile", values, q=q)
    out = _np().quantile(values, q)
    return out.item() if getattr(out, "ndim", 1) == 0 else out


def _matrix(x):
    a = as_array(x) if not is_array(x) else x
    if not is_array(a):
        raise TypeError(f"expected a vector or matrix, got "
                        f"{type(x).__name__}")
    return a


def _det(A):
    return float(_np().linalg.det(_matrix(A)))


def _inv(A):
    return _np().linalg.inv(_matrix(A))


def _trace(A):
    return float(_np().trace(_matrix(A)))


def _transpose(A):
    return _matrix(A).T


def _identity(n):
    if isinstance(n, float) and n.is_integer():
        n = int(n)
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError(f"I(n) needs a whole size, got {n!r}")
    return _np().eye(n)


def _matrix_power(A, k):
    if isinstance(k, float) and k.is_integer():
        k = int(k)
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError(f"matrix_power needs a whole exponent, got {k!r}")
    return _np().linalg.matrix_power(_matrix(A), k)


def _dot(x, y):
    a, b = _matrix(x), _matrix(y)
    np = _np()
    if a.ndim == 1 and b.ndim == 1 and (_holes(a) or _holes(b)):
        # over the value slots both vectors hold; 0 where none is
        both = ~(np.isnan(a) | np.isnan(b))
        return float(np.dot(a[both], b[both])) if both.any() else 0.0
    out = np.dot(a, b)
    return out.item() if getattr(out, "ndim", 1) == 0 else out


def _outer(x, y):
    return _np().outer(_matrix(x), _matrix(y))


def _kron(A, B):
    return _np().kron(_matrix(A), _matrix(B))


def _diag(x):
    return _np().diag(_matrix(x))


def _rank(A):
    return int(_np().linalg.matrix_rank(_matrix(A)))


def _eigvals(A):
    """The eigenvalues of a square matrix, complex in general, sorted
    by real then imaginary part so two calls list them alike."""
    np = _np()
    values = np.linalg.eigvals(_matrix(A))
    values = values[np.lexsort((values.imag, values.real))]
    if np.all(values.imag == 0):
        return values.real
    return values


def _eigvalsh(A):
    """The eigenvalues of a symmetric matrix, real and ascending."""
    return _np().linalg.eigvalsh(_matrix(A))


def _cond(A):
    return float(_np().linalg.cond(_matrix(A)))


def _solve(A, b):
    return _np().linalg.solve(_matrix(A), _matrix(b))


def _pinv(A):
    return _np().linalg.pinv(_matrix(A))


#: the claim-level functions a vector or matrix claim evaluates with,
#: each a number's ordinary function on a number
FUNCTIONS = {
    "abs": _abs, "Abs": _abs, "norm": _norm,
    "sum": _reduction(builtins.sum, "sum"),
    "min": _reduction(builtins.min, "min"),
    "max": _reduction(builtins.max, "max"),
    "mean": _mean, "prod": _prod,
    "std": _moment("std"), "var": _moment("var"), "count": _count,
    "cumsum": _cumulative("cumsum"), "cumprod": _cumulative("cumprod"),
    "median": _median, "quantile": _quantile,
    "cummax": _running_extremum("maximum", "cummax"),
    "cummin": _running_extremum("minimum", "cummin"),
    "det": _det, "inv": _inv, "trace": _trace, "transpose": _transpose,
    "I": _identity, "matrix_power": _matrix_power,
    "dot": _dot, "outer": _outer, "kron": _kron, "diag": _diag,
    "rank": _rank, "eigvals": _eigvals, "eigvalsh": _eigvalsh,
    "cond": _cond, "solve": _solve, "pinv": _pinv,
}
