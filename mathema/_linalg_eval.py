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
        if all(isinstance(r, (list, tuple)) for r in value):
            return np.array([[math.nan if is_missing(v) else float(v)
                              for v in r] for r in value], dtype=float)
        return np.array([math.nan if is_missing(v) else float(v)
                         for v in value], dtype=float)
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
        return value.tolist()
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
    except OverflowError:
        return _exact_largest_gap(lv, rv)
    except (TypeError, ValueError):
        return 0.0
    finite = gaps[np.isfinite(gaps)]
    return float(finite.max()) if finite.size else 0.0


def _exact_largest_gap(lv, rv) -> float:
    """`largest_gap` where a side holds an exact value beyond float
    range: each finite difference taken exactly, the largest rounded to
    a float, a difference beyond float range left out with the
    non-finite ones."""
    from fractions import Fraction
    np = _np()
    a = np.asarray(lv, dtype=object).ravel().tolist()
    b = np.asarray(rv, dtype=object).ravel().tolist()
    if len(b) == 1 and len(a) > 1:
        b = b * len(a)
    if len(a) == 1 and len(b) > 1:
        a = a * len(b)
    best = 0.0
    for x, y in zip(a, b):
        try:
            gap = abs(Fraction(x) - Fraction(y))
            best = max(best, float(gap))
        except (TypeError, ValueError, OverflowError):
            continue
    return best


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
    absolute value of a number."""
    if isinstance(x, (int, float, complex)) and not isinstance(x, bool):
        return builtins.abs(x)
    np = _np()
    a = as_array(x) if not is_array(x) else x
    if not is_array(a):
        raise TypeError(f"norm of {type(x).__name__}")
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


def _reduction(builtin_fn, numpy_name):
    def reduce(*args, axis=None, **kwargs):
        if len(args) == 1 and _is_array_arg(args[0]):
            out = getattr(_np(), numpy_name)(args[0], axis=axis, **kwargs)
            return out.item() if getattr(out, "ndim", 1) == 0 else out
        if axis is not None:
            raise TypeError(f"{numpy_name}(..., axis=) needs an array")
        return builtin_fn(*args, **kwargs)
    reduce.__name__ = numpy_name
    return reduce


def _values(args):
    """The one vector a reduction reads: its single argument as an
    array, or its several numeric arguments gathered into one."""
    np = _np()
    if len(args) == 1:
        a = args[0]
        return a if is_array(a) else np.asarray(as_array(a), dtype=float)
    return np.asarray(args, dtype=float)


def _raw(args):
    """The one vector or matrix a word reads, its elements as given:
    an array as it is, a list (or nested lists) as an object array with
    nan at each missing position, several numbers gathered into one
    vector. Integers stay integers."""
    np = _np()
    from .domain import is_missing
    a = args[0] if len(args) == 1 else list(args)
    if is_array(a):
        return a
    if isinstance(a, (list, tuple)):
        def element(v):
            if isinstance(v, (list, tuple)):
                return [element(x) for x in v]
            return math.nan if is_missing(v) else v
        out = np.empty(0, dtype=object)
        rows = [element(v) for v in a]
        if rows and all(isinstance(r, list) for r in rows):
            out = np.empty((len(rows), len(rows[0])), dtype=object)
            for i, r in enumerate(rows):
                out[i, :] = r
            return out
        out = np.empty(len(rows), dtype=object)
        out[:] = rows
        return out
    return np.asarray(as_array(a))


def _element(v):
    """One array element as a Python number."""
    return v.item() if hasattr(v, "item") else v


def _along(args, axis, of_list):
    """`of_list` applied to the one vector the arguments give, or along
    `axis` of a matrix (one value per remaining index)."""
    a = _raw(args)
    if axis is None:
        return of_list([_element(v) for v in a.ravel()])
    return _np().apply_along_axis(
        lambda v: of_list([_element(x) for x in v]), axis, a)


def _is_complex(v) -> bool:
    import numbers
    return isinstance(v, numbers.Complex) and not isinstance(v, numbers.Real)


def _exact(v):
    """A real number as an exact rational; an infinity or nan as the
    float it is."""
    import numbers
    from fractions import Fraction
    if isinstance(v, Fraction):
        return v
    if isinstance(v, numbers.Integral):
        return Fraction(int(v))
    f = float(v)
    return Fraction(f) if math.isfinite(f) else f


def _rounded(x):
    """An exact value rounded once to the nearest float; a value beyond
    float range stays exact (a `Fraction`), so an infinity a computation
    returns is judged against it rather than against another infinity."""
    from fractions import Fraction
    if not isinstance(x, Fraction):
        return x
    try:
        return float(x)
    except OverflowError:
        return x


def _ext_add(values: list):
    """The sum of exact rationals and infinities: nan when a summand is
    nan or both infinities appear (no value), the infinity when one
    appears, else the exact sum."""
    from fractions import Fraction
    infinite = {v for v in values if isinstance(v, float)}
    if any(math.isnan(v) for v in infinite) or len(infinite) > 1:
        return math.nan
    if infinite:
        return infinite.pop()
    return builtins.sum(values, Fraction(0))


def _ext_mul(values: list):
    """The product of exact rationals and infinities: nan when a factor
    is nan or an infinity meets a zero (no value), a signed infinity
    when an infinity appears, else the exact product."""
    from fractions import Fraction
    if any(isinstance(v, float) and math.isnan(v) for v in values):
        return math.nan
    if any(isinstance(v, float) for v in values):
        if any(v == 0 for v in values):
            return math.nan
        negative = builtins.sum(1 for v in values if v < 0) % 2
        return -math.inf if negative else math.inf
    return math.prod(values, start=Fraction(1))


def _parts(values: list):
    """The real and imaginary parts of a list of numbers, each exact,
    or None when a part is not finite."""
    from fractions import Fraction
    re, im = [], []
    for v in values:
        if not _is_complex(v):
            x = _exact(v)
            if isinstance(x, float):
                return None
            re.append(x)
            im.append(Fraction(0))
            continue
        z = complex(v)
        if not (math.isfinite(z.real) and math.isfinite(z.imag)):
            return None
        re.append(_exact(z.real))
        im.append(_exact(z.imag))
    return re, im


def _complex_result(re, im) -> complex:
    """A complex value from exact parts, each rounded once.

    Raises:
        OverflowError: a part lies beyond float range, which a complex
            float cannot hold.
    """
    return complex(float(re), float(im))


def _exact_sum(values: list):
    """The exact sum of a list of numbers, rounded once (see
    `_rounded`); complex numbers sum their parts apart."""
    if any(_is_complex(v) for v in values):
        parts = _parts(values)
        if parts is None:
            return complex(math.nan, math.nan)
        return _complex_result(_ext_add(parts[0]), _ext_add(parts[1]))
    return _rounded(_ext_add([_exact(v) for v in values]))


def _exact_mean(values: list):
    """The exact sum of a list over its length, rounded once; no value
    when empty."""
    if not values:
        return math.nan
    if any(_is_complex(v) for v in values):
        parts = _parts(values)
        if parts is None:
            return complex(math.nan, math.nan)
        n = len(values)
        return _complex_result(_ext_add(parts[0]) / n,
                               _ext_add(parts[1]) / n)
    total = _ext_add([_exact(v) for v in values])
    return total if isinstance(total, float) else _rounded(total / len(values))


def _product(values: list):
    """The exact product of a list's elements, rounded once."""
    from fractions import Fraction
    if any(_is_complex(v) for v in values):
        parts = _parts(values)
        if parts is None:
            return complex(math.nan, math.nan)
        re, im = Fraction(1), Fraction(0)
        for a, b in zip(*parts):
            re, im = re * a - im * b, re * b + im * a
        return _complex_result(re, im)
    return _rounded(_ext_mul([_exact(v) for v in values]))


def _exact_variance(values: list, ddof):
    """The mean squared deviation from the mean (the squared modulus for
    complex numbers), `ddof` taken from the length in the divisor,
    exact; nan (no value) for fewer than `ddof + 1` elements or an
    element that is nan or infinite."""
    n = len(values) - _exact(ddof)
    if n <= 0:
        return math.nan
    parts = _parts(values)
    if parts is None:
        return math.nan
    re, im = parts
    mean_re = builtins.sum(re) / len(re)
    mean_im = builtins.sum(im) / len(im)
    return builtins.sum((a - mean_re) ** 2 + (b - mean_im) ** 2
                        for a, b in zip(re, im)) / n


def exact_log(x, base=None) -> float:
    """The logarithm of an exact positive rational beyond float range,
    from the logarithms of its numerator and denominator (Python reads
    a whole number of any size); `base` None is the natural logarithm.

    Raises:
        ValueError: `x` is not positive.
    """
    if x <= 0:
        raise ValueError("math domain error")
    if base == 2:
        return math.log2(x.numerator) - math.log2(x.denominator)
    if base == 10:
        return math.log10(x.numerator) - math.log10(x.denominator)
    return math.log(x.numerator) - math.log(x.denominator)


def exact_sqrt(x):
    """The square root of an exact non-negative rational, rounded once
    (see `_exact_sqrt`).

    Raises:
        ValueError: `x` is negative.
    """
    if x < 0:
        raise ValueError("math domain error")
    return _exact_sqrt(x)


def _exact_sqrt(x):
    """The square root of an exact non-negative rational, rounded once;
    beyond float range it stays exact to 60 significant digits."""
    from decimal import Decimal, localcontext
    from fractions import Fraction
    if isinstance(x, float):
        return x if math.isnan(x) else math.sqrt(x)
    if x == 0:
        return 0.0
    with localcontext() as ctx:
        ctx.prec = 60
        root = (Decimal(x.numerator) / Decimal(x.denominator)).sqrt()
    value = float(root)
    return Fraction(root) if math.isinf(value) else value


def _sum(*args, axis=None):
    """The sum of a vector's elements, exact and rounded once; along
    `axis` for a matrix."""
    if len(args) == 1 and _is_array_arg(args[0]):
        return _along(args, axis, _exact_sum)
    if axis is not None:
        raise TypeError("sum(..., axis=) needs an array")
    return builtins.sum(*args)


def _mean(*args, axis=None):
    """The exact mean of a vector's elements, rounded once; along
    `axis` for a matrix."""
    if len(args) == 1 and _is_array_arg(args[0]):
        return _along(args, axis, _exact_mean)
    return _exact_mean(list(args[0]) if len(args) == 1 else list(args))


def _prod(*args, axis=None):
    """The exact product of a vector's elements, rounded once; along
    `axis` for a matrix."""
    if len(args) == 1 and _is_array_arg(args[0]):
        return _along(args, axis, _product)
    return math.prod(args[0] if len(args) == 1 else args)


def _moment(word):
    """`var` or `std`: the variance is the mean squared deviation from
    the mean, `ddof` subtracted from the number of positions in the
    divisor (0 by default, the population statistic; 1 for the sample
    statistic), and the standard deviation its square root, each exact
    and rounded once; `axis` reduces a matrix along one axis."""
    def of_list(values, ddof):
        variance = _exact_variance(values, ddof)
        if word == "std":
            return _exact_sqrt(variance)
        return _rounded(variance)

    def moment(*args, ddof=0, axis=None):
        return _along(args, axis, lambda values: of_list(values, ddof))
    moment.__name__ = word
    return moment


def _count(*args, axis=None):
    """The number of positions: every element of a vector or matrix,
    or the positions along `axis` (one count per remaining index)."""
    a = _values(args)
    if axis is None:
        return int(a.size)
    np = _np()
    return np.full(np.delete(np.array(a.shape), axis), a.shape[axis],
                   dtype=float) if a.ndim > 1 else int(a.shape[axis])


def _running(of_list, word):
    """A running word: entry `i` is `of_list` of elements `0..i`; a
    matrix is read in row order without `axis`, along it with one."""
    def entries(values):
        out = [of_list(values[:i + 1]) for i in range(len(values))]
        np = _np()
        if all(isinstance(v, float) for v in out):
            return np.array(out, dtype=float)
        if all(isinstance(v, (float, complex)) for v in out):
            return np.array(out, dtype=complex)
        result = np.empty(len(out), dtype=object)
        result[:] = out
        return result

    def running(*args, axis=None):
        a = _raw(args)
        if axis is None:
            return entries([_element(v) for v in a.ravel()])
        return _np().apply_along_axis(
            lambda v: entries([_element(x) for x in v]), axis, a)
    running.__name__ = word
    return running


def _extremum(pick):
    """The greatest (`pick` is max) or least (min) element of a list by
    exact comparison; no value (nan) where `_ordered` gives none."""
    def of_list(values):
        ordered = _ordered(values)
        return math.nan if ordered is None else _rounded(pick(ordered))
    return of_list


def _ordered(values: list):
    """The elements of a list sorted, each exact, or None when the list
    has no order statistic: it is empty, holds a missing element (nan),
    or holds a complex number (complex numbers have no order)."""
    if not values or any(_is_complex(v) for v in values):
        return None
    exact = [_exact(v) for v in values]
    if any(isinstance(v, float) and math.isnan(v) for v in exact):
        return None
    return sorted(exact)


def _between(a, b, g):
    """The point the fraction `g` (0 < g < 1) of the way from `a` to
    `b >= a`, exact for finite ends: between -inf and +inf there is no
    such point (nan), and an infinite end is the point itself."""
    if isinstance(a, float) and isinstance(b, float):
        return math.nan if a != b else a
    if isinstance(a, float):
        return a
    if isinstance(b, float):
        return b
    return _rounded(a + g * (b - a))


def _median_of(values: list):
    """The median of a list of numbers: the middle element of the
    sorted list, or the midpoint of the two middle elements for an even
    length, exact and rounded once. A missing element, a complex element
    or an empty list has no median (nan)."""
    from fractions import Fraction
    ordered = _ordered(values)
    if ordered is None:
        return math.nan
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return _rounded(ordered[mid])
    a, b = ordered[mid - 1], ordered[mid]
    return _rounded(a) if a == b else _between(a, b, Fraction(1, 2))


def _median(*args, axis=None):
    """The median: the middle element of the sorted vector, or the
    mean of the middle two for an even length; along `axis` for a
    matrix, one median per remaining index."""
    return _along(args, axis, _median_of)


def _level(q):
    """A quantile level as the number written: a float by its shortest
    decimal spelling (`0.1` is one tenth), an integer or rational as it
    is."""
    import numbers
    from fractions import Fraction
    if isinstance(q, Fraction):
        return q
    if isinstance(q, numbers.Integral):
        return Fraction(int(q))
    f = float(q)
    if not math.isfinite(f):
        raise ValueError(f"a quantile level lies in [0, 1], not {q!r}")
    return Fraction(repr(f))


def _quantile_of(values: list, q):
    """The `q`-quantile of a list of numbers by linear interpolation
    (Hyndman and Fan's type 7): with the list sorted and `h = (n - 1)
    q`, the element at `floor(h)` plus the fraction `h - floor(h)` of
    the gap to the next one, computed exactly and rounded once. No
    value (nan) where `_ordered` gives none."""
    level = _level(q)
    if not 0 <= level <= 1:
        raise ValueError(f"a quantile level lies in [0, 1], not {q!r}")
    ordered = _ordered(values)
    if ordered is None:
        return math.nan
    h = (len(ordered) - 1) * level
    lo = math.floor(h)
    hi = min(lo + 1, len(ordered) - 1)
    a, b = ordered[lo], ordered[hi]
    if h == lo or a == b:
        return _rounded(a)
    return _between(a, b, h - lo)


def _quantile(a, q):
    """The `q`-quantile of a vector (`0 <= q <= 1`), interpolated
    linearly between the two sorted elements it falls between, as
    numpy and pandas compute it by default; several levels give one
    quantile each."""
    values = [_element(v) for v in _raw((a,)).ravel()]
    if is_array(q) or isinstance(q, (list, tuple)):
        return _np().array([_quantile_of(values, _element(level))
                            for level in _np().asarray(q).ravel()])
    return _quantile_of(values, q)


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


def _exact_inner(xs: list, ys: list):
    """The sum of the products of two equal-length lists, exact and
    rounded once; complex elements multiply and sum their parts apart.
    No value (nan) where a product or the sum has none (an infinity
    times zero, opposite infinities, a missing element)."""
    from fractions import Fraction
    if any(_is_complex(v) for v in (*xs, *ys)):
        px, py = _parts(xs), _parts(ys)
        if px is None or py is None:
            return complex(math.nan, math.nan)
        re = builtins.sum((a * c - b * d for a, b, c, d
                           in zip(px[0], px[1], py[0], py[1])), Fraction(0))
        im = builtins.sum((a * d + b * c for a, b, c, d
                           in zip(px[0], px[1], py[0], py[1])), Fraction(0))
        return _complex_result(re, im)
    products = [_ext_mul([_exact(x), _exact(y)]) for x, y in zip(xs, ys)]
    return _rounded(_ext_add(products))


def _dot(x, y):
    """The inner product of two vectors, a matrix times a vector, a
    vector times a matrix, or the product of two matrices, each entry
    exact and rounded once."""
    np = _np()
    a, b = _raw((x,)), _raw((y,))
    if a.ndim == 0 or b.ndim == 0:
        return _matrix(x) * _matrix(y)
    if a.ndim > 2 or b.ndim > 2:
        raise ValueError("dot reads vectors and matrices")
    if a.shape[-1] != b.shape[0]:
        raise ValueError(f"dot of shapes {a.shape} and {b.shape}: the "
                         f"inner dimensions differ")
    a2 = a.reshape(1, -1) if a.ndim == 1 else a
    b2 = b.reshape(-1, 1) if b.ndim == 1 else b
    entries = [[_exact_inner([_element(v) for v in a2[i]],
                             [_element(v) for v in b2[:, j]])
                for j in range(b2.shape[1])] for i in range(a2.shape[0])]
    if a.ndim == 1 and b.ndim == 1:
        return entries[0][0]
    out = np.array(entries)
    if a.ndim == 1:
        return out[0]
    if b.ndim == 1:
        return out[:, 0]
    return out


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
    "sum": _sum,
    "min": _reduction(builtins.min, "min"),
    "max": _reduction(builtins.max, "max"),
    "mean": _mean, "prod": _prod,
    "std": _moment("std"), "var": _moment("var"), "count": _count,
    "cumsum": _running(_exact_sum, "cumsum"),
    "cumprod": _running(_product, "cumprod"),
    "median": _median, "quantile": _quantile,
    "cummax": _running(_extremum(max), "cummax"),
    "cummin": _running(_extremum(min), "cummin"),
    "det": _det, "inv": _inv, "trace": _trace, "transpose": _transpose,
    "I": _identity, "matrix_power": _matrix_power,
    "dot": _dot, "outer": _outer, "kron": _kron, "diag": _diag,
    "rank": _rank, "eigvals": _eigvals, "eigvalsh": _eigvalsh,
    "cond": _cond, "solve": _solve, "pinv": _pinv,
}
