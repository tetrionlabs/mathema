# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Semantic type markers: attach a `typing.Annotated` marker to a
parameter or return type, and mathema infers a standard claim
automatically, a fourth claim-authoring surface, alongside the file/
decorator/docstring ones in authoring.py, except *inferred* rather than
explicitly stated.

    from typing import Annotated
    from mathema.types import Probability, Shape

    def bayes_update(prior: Annotated[float, Probability],
                     likelihood: Annotated[float, Probability]) -> Annotated[float, Probability]:
        ...

    def matmul(a: Annotated[list, Shape("m", "n")],
              b: Annotated[list, Shape("n", "p")]) -> Annotated[list, Shape("m", "p")]:
        ...

Markers are deliberately general mathematics only, matching the
domain-specific-goes-outside boundary drawn in
05-pushing-derive-further.md: Probability/Positive/Shape are math, not a
business vertical (a `StockPrice` marker would not belong here).

Domain markers (Probability/Positive/Nonnegative) fold into an ordinary
domain-scoped claim, reusing check()'s existing `domain=` mechanism.
`Shape` is structural, not algebraic; it can't be expressed in the
scalar claim-law grammar (there is no index quantifier over a variable-
length structure), so it's checked the way probing.py already checks
`monotone`/`is_numerically_stable`: a bespoke Python probe, not a parsed
law string. Precedence-wise this surface is the lowest of the four: a
human writing a decorator or docstring claim is a more deliberate
statement than an incidentally-implied one from a type hint, so a
same-named explicit claim from any other surface overrides an inferred
one (see authoring.declared_from_function, which does not consult this
module; type inference is folded in one level further out, in
type_probes(), so it never competes with an ordinary claim name)."""
from __future__ import annotations

import inspect
import random
import typing
from dataclasses import dataclass, field

from .grammar import Interval
from .probing import Probe, _RNG_SEED


@dataclass(frozen=True)
class Probability:
    """Value in [0, 1]."""


@dataclass(frozen=True)
class Positive:
    """Value > 0."""


@dataclass(frozen=True)
class Nonnegative:
    """Value >= 0."""


@dataclass(frozen=True)
class Negative:
    """Value < 0."""


@dataclass(frozen=True)
class Nonpositive:
    """Value <= 0."""


@dataclass(frozen=True)
class UnitInterval:
    """Value in [0, 1]. The plain-interval reading of the same bound
    `Probability` carries, for a quantity that lives in [0, 1] without
    being a probability."""


@dataclass(frozen=True)
class UnitBall:
    """Value in [-1, 1] inclusive, the closed unit ball in one dimension:
    the range of sin/cos, a correlation coefficient, a cosine
    similarity."""


@dataclass(frozen=True)
class InRange:
    """Value in a stated interval, the general bound marker for anything
    the fixed markers above do not name. `InRange(0, 1)` is the closed
    `[0, 1]`; `closed` sets each endpoint, so `InRange(0, 1, (True,
    False))` is `[0, 1)`. Always spelled with arguments, so (like
    `Shape`) it has no bare-class shorthand."""
    lo: float
    hi: float
    closed: tuple = (True, True)


@dataclass(frozen=True)
class Shape:
    """Expected outer dimensions of a nested-list "matrix"/"vector"
    value: concrete ints or symbolic dimension-name strings shared across
    the signature (`Shape("m", "n")` on one parameter and `Shape("n",
    "p")` on another means both must agree on the size bound to "n"
    within a trial). 1-D: `Shape("n")`; 2-D: `Shape("m", "n")`."""
    dims: tuple = field(default_factory=tuple)

    def __init__(self, *dims):
        object.__setattr__(self, "dims", dims)


class Structure:
    """A matrix STRUCTURE marker: the value has the named property
    (`is_symmetric`, `is_positive_definite`, ...). The concrete marker
    classes below (`Symmetric`, `PositiveDefinite`, ...) each fix
    `prop` to their registry name as a class attribute, so a signature
    reads `Annotated[list, Mat("n", "n"), Symmetric]` and every
    consumer resolves the property through
    `mathema.matrices.PROPERTIES`. Not a dataclass: a field default
    would shadow the per-subclass class attribute, and a structure
    marker carries no per-instance data anyway."""
    prop: str = ""

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __eq__(self, other) -> bool:
        return type(self) is type(other)

    def __hash__(self) -> int:
        return hash(type(self))


def _structure_markers() -> dict:
    """One frozen marker class per registry property, name derived from
    the `is_<snake>` predicate (`is_positive_definite` ->
    `PositiveDefinite`). Generated so the marker vocabulary and the
    checkable/synthesisable property set can never drift apart."""
    from .matrices import PROPERTIES
    out: dict = {}
    for name in PROPERTIES:
        cls_name = "".join(part.capitalize()
                           for part in name[len("is_"):].split("_"))
        cls = type(cls_name, (Structure,),
                   {"__doc__": f"Matrix structure marker: {name}.",
                    "prop": name})
        out[cls_name] = cls
    return out


_STRUCTURE_MARKERS = _structure_markers()
globals().update(_STRUCTURE_MARKERS)
#: the marker classes usable in a signature, by class name
STRUCTURE_MARKER_TYPES = tuple(_STRUCTURE_MARKERS.values())


def Vec(*items):
    """Shorthand for a shaped list parameter: `Vec("n")` is exactly
    `Annotated[list, Shape("n")]`, and `Vec("m", "n")` a matrix. A
    structure marker may ride the same call, `Mat("n", "n", Symmetric,
    PositiveDefinite)`, folding into sibling markers so it produces the
    identical `Annotated[list, Shape(...), Symmetric, PositiveDefinite]`
    the long form does. Every reader (`shapes_from_signature`,
    `structures_from_signature`, the dimension resolver, the probes)
    sees the same markers either spelling produces.

        def matvec(a: Mat("m", "n"), x: Vec("n")) -> Vec("m"):
            ...
        def solve(a: Mat("n", "n", PositiveDefinite), b: Vec("n")): ...
    """
    dims = tuple(d for d in items if isinstance(d, (str, int)))
    props = tuple(d for d in items if not isinstance(d, (str, int)))
    markers = (Shape(*dims),) + tuple(
        (m() if isinstance(m, type) else m) for m in props)
    return typing.Annotated[(list, *markers)]


#: `Mat` reads better than `Vec` for a two-or-more dimensional value;
#: it is the same factory, so the choice is only which word states the
#: author's intent more plainly. `Mat("m", "n")` == `Vec("m", "n")`.
Mat = Vec

#: the shorthand constructors that expand to `Annotated[list, Shape(...)]`.
#: A reader working on an annotation's own source TEXT cannot see that
#: expansion (`analysis._annotation_base`), so it matches these names.
SHAPED_LIST_FACTORIES = ("Vec", "Mat")


_DOMAIN_MARKERS = {
    Probability: Interval(0.0, 1.0),
    Positive: Interval(1e-9, 1e6),      # sampled strictly away from 0
    Nonnegative: Interval(0.0, 1e6),
    Negative: Interval(-1e6, -1e-9),    # sampled strictly away from 0
    Nonpositive: Interval(-1e6, 0.0),
    UnitInterval: Interval(0.0, 1.0),
    UnitBall: Interval(-1.0, 1.0),
}


def _marker_interval(m) -> Interval | None:
    """The interval a domain marker implies, or None when the marker is
    not a bound (a Shape or Structure). Fixed-bound markers map by their
    type; an `InRange` carries its own endpoints and per-endpoint
    closedness."""
    if isinstance(m, InRange):
        closed_lo, closed_hi = m.closed
        return Interval(float(m.lo), float(m.hi), closed_lo, closed_hi)
    return _DOMAIN_MARKERS.get(type(m))


def _hints(fn) -> dict:
    try:
        return typing.get_type_hints(fn, include_extras=True)
    except Exception:
        return {}


_MARKER_TYPES = (Probability, Positive, Nonnegative, Negative, Nonpositive,
                 UnitInterval, UnitBall, InRange, Shape, Structure)

#: the fixed-bound markers usable bare (no parens); InRange/Shape need args
_BARE_BOUND_MARKERS = (Probability, Positive, Nonnegative, Negative,
                       Nonpositive, UnitInterval, UnitBall)


def _markers(hint) -> tuple:
    """Marker instances in an Annotated hint's metadata. Accepts the bare
    class too (`Annotated[float, Probability]`, no parens) as shorthand
    for a zero-arg marker instance; `Shape` always needs dims, so this
    only applies to the domain markers."""
    # a bare marker used directly as the annotation, no Annotated wrapper:
    # `-> InRange(0, 1)`, `x: Probability`. An ordinary type (`float`,
    # `list[int]`) matches neither branch and falls through unchanged.
    if isinstance(hint, _MARKER_TYPES):
        return (hint,)
    if isinstance(hint, type) and issubclass(hint, (*_BARE_BOUND_MARKERS,
                                                    Structure)):
        return (hint(),)
    out = []
    for m in getattr(hint, "__metadata__", ()):
        if isinstance(m, _MARKER_TYPES):
            out.append(m)
        elif isinstance(m, type) and issubclass(m, (*_BARE_BOUND_MARKERS,
                                                     Structure)):
            out.append(m())
        elif getattr(m, "__metadata__", None):
            # a nested Annotated: `Mat(...)`/`Vec(...)` already return an
            # Annotated, so `Annotated[T, Mat("n", "m")]` carries one as
            # its metadata. Recurse into it so the wrapped spelling
            # resolves exactly like the bare `X: Mat("n", "m")`.
            out.extend(_markers(m))
    return tuple(out)


def domain_from_signature(fn) -> dict:
    """Per-parameter domain implied by a bound marker (Probability,
    Positive, InRange, UnitBall, ...) on that parameter, ready to merge
    into `domain=` exactly like an explicitly declared one. A parameter
    with no marker is absent.

    A bound marker also asserts the value is PRESENT: the domain
    excludes the missing sentinel (nan/None/missing), so a marked
    parameter can never be missing (a probability is not nan). The
    domain is therefore a `Domain` carrying `excluded={MISSING}`, not a
    bare `Interval`, and renders explicitly as `[lo, hi] \\ {missing}`."""
    from .domain import MISSING, Domain
    hints = _hints(fn)
    out: dict = {}
    for name, hint in hints.items():
        if name == "return":
            continue
        for m in _markers(hint):
            bound = _marker_interval(m)
            if bound is not None:
                out[name] = Domain(base_type="R", pieces=(bound,),
                                   excluded=frozenset({MISSING}))
    return out


#: the SEMANTIC output bound per fixed marker, as
#: (lo, hi, closed_lo, closed_hi) with None on a side the marker leaves
#: unbounded. Distinct from the sampling intervals in _DOMAIN_MARKERS,
#: which clamp an unbounded side to +-1e6 for drawing inputs; a return
#: marker states `f(...) > 0`, not `f(...) <= 1e6`.
_MARKER_BOUNDS: dict = {
    Probability: (0.0, 1.0, True, True),
    UnitInterval: (0.0, 1.0, True, True),
    UnitBall: (-1.0, 1.0, True, True),
    Positive: (0.0, None, False, None),
    Nonnegative: (0.0, None, True, None),
    Negative: (None, 0.0, None, False),
    Nonpositive: (None, 0.0, None, True),
}


def _marker_bound(m) -> tuple | None:
    if isinstance(m, InRange):
        closed_lo, closed_hi = m.closed
        return (float(m.lo), float(m.hi), closed_lo, closed_hi)
    return _MARKER_BOUNDS.get(type(m))


def return_bound(fn) -> tuple | None:
    """The semantic output bound a marker on fn's RETURN implies, as
    (lo, hi, closed_lo, closed_hi) with None on an unbounded side, or
    None when the return carries no bound marker. What a bound
    suggestion renders as `lo <= f(...) <= hi` (or a one-sided
    inequality when a side is unbounded): `-> Probability` gives
    `0 <= f(...) <= 1`, `-> Positive` gives `f(...) > 0`."""
    hint = _hints(fn).get("return")
    if not hint:
        return None
    for m in _markers(hint):
        b = _marker_bound(m)
        if b is not None:
            return b
    return None


def _return_probability(fn) -> bool:
    hint = _hints(fn).get("return")
    return any(isinstance(m, Probability) for m in _markers(hint)) if hint else False


def shapes_from_signature(fn) -> dict[str, Shape]:
    """Every Shape marker for fn's parameters and return, read from the
    signature's Annotated hints; the typing system is the one place
    a type belongs, so there is no docstring spelling for this."""
    hints = _hints(fn)
    out: dict[str, Shape] = {}
    for name, hint in hints.items():
        dims = _shape_dims(hint)
        if dims is not None:
            out[name] = Shape(*dims)
    return out


def structures_from_signature(fn) -> dict[str, tuple]:
    """Every matrix STRUCTURE property declared per parameter (and the
    return), as `{name: (prop, ...)}` in registry-entailment-closed
    form: a `PositiveDefinite` marker yields `is_positive_definite`
    and everything it implies (`is_symmetric`, ...), so a declared
    structure narrows the domain to all it entails. The structural
    analogue of `shapes_from_signature`."""
    from .matrices import entailed
    hints = _hints(fn)
    out: dict[str, tuple] = {}
    for name, hint in hints.items():
        props = [m.prop for m in _markers(hint) if isinstance(m, Structure)]
        if props:
            out[name] = tuple(sorted(entailed(props)))
    return out


def matrix_param_names(fn) -> frozenset:
    """The parameters (and the return) fn's signature declares to be
    matrices: those with a 2-D `Shape` marker, or any structure marker
    (a structure is a property OF a matrix). These are the names
    `claim()` reads the matrix sugar (`A^T`, `|A|`, `A^-1`) on, so a
    function's own claims parse matrix-aware without restating the type
    in the claim text."""
    mats = {name for name, sh in shapes_from_signature(fn).items()
            if len(sh.dims) == 2}
    mats |= set(structures_from_signature(fn))
    return frozenset(mats)


def _shape_dims(hint) -> tuple | None:
    for m in _markers(hint):
        if isinstance(m, Shape):
            return m.dims
    return None


def _synth_nested(dims: tuple, sizes: dict, rng: random.Random):
    """A nested list of the given (possibly symbolic) outer dims, sizes
    resolved through `sizes` (name -> concrete int for this trial)."""
    if not dims:
        return rng.uniform(-10, 10)
    d = dims[0]
    n = sizes[d] if isinstance(d, str) else d
    return [_synth_nested(dims[1:], sizes, rng) for _ in range(n)]


def _actual_shape(value) -> tuple:
    shape = []
    while isinstance(value, list):
        shape.append(len(value))
        value = value[0] if value else None
    return tuple(shape)


_TYPE_PROBE_TRIALS = 32   # default sample count for a Shape-derived probe,
                         # smaller than probing.py's own _N_BASE since a
                         # shape check is a single structural fact, not a
                         # battery of algebraic laws needing broad coverage


_SHAPE_MISMATCH_TRIALS = 3   # per shared dim, domain_enforced-sized, not the
                            # full adaptive battery: this checks one specific
                            # guard, the same scale as domain_enforced's own
                            # fixed n=2 boundary check, not a law needing
                            # broad coverage


def _call(fn, sig, args: dict):
    return fn(**args) if all(p in sig.parameters for p in args) \
        else fn(*[args[p] for p in sig.parameters if p in args])


def _shape_enforced_probe(fn, sig, param_dims: dict, names: set,
                          rng: random.Random) -> Probe | None:
    """Does the real function guard against mismatched input shapes, the
    same way domain_enforced() checks whether a scalar guard exists,
    not "is the output the right shape for consistent input" (type_probes'
    own `shape` check, which assumes shape is a pure function of the
    input dims and says nothing about a function whose real output shape
    depends on the data itself, e.g. a converged cluster count), but "does
    it reject or gracefully decline inconsistent input at all". Only
    meaningful for a dim shared by two or more parameters (`Shape("m",
    "n")`/`Shape("n", "p")` sharing `n`, say); there's nothing to
    mismatch a single parameter's own dim against. `None` if no dim is
    shared this way."""
    shared = sorted(n for n in names
                    if sum(1 for dims in param_dims.values() if n in dims) > 1)
    if not shared:
        return None

    stmt = (f"{fn.__name__}(" + ", ".join(param_dims) + ") rejects "
            f"mismatched sizes on shared dims {shared}")
    rejected, accepted_examples, checked = 0, [], 0
    for dim in shared:
        candidates = [p for p, dims in param_dims.items() if dim in dims]
        for _ in range(_SHAPE_MISMATCH_TRIALS):
            sizes = {n: rng.randint(1, 4) for n in names}
            bad_param = rng.choice(candidates)
            bad_sizes = dict(sizes)
            bad_sizes[dim] = sizes[dim] + 1 + rng.randint(0, 2)
            args = {p: _synth_nested(dims, bad_sizes if p == bad_param else sizes, rng)
                   for p, dims in param_dims.items()}
            checked += 1
            try:
                result = _call(fn, sig, args)
            except Exception:
                rejected += 1
                continue
            if result is None:
                rejected += 1
                continue
            accepted_examples.append(f"{bad_param}[{dim}]={bad_sizes[dim]} "
                                     f"vs {dim}={sizes[dim]} elsewhere")
    if rejected == checked:
        return Probe("shape_enforced", stmt, "holds", n=checked)
    # one truth, no mode: a declared shared dim the code silently
    # accepts a mismatch on is a witnessed policy violation
    return Probe("shape_enforced", stmt, "falsified", n=checked,
                 counterexample="; ".join(accepted_examples[:3]),
                 note="silently accepting a shape mismatch violates the "
                      "declared shared dims")


def type_probes(fn, trials: int = _TYPE_PROBE_TRIALS) -> list[Probe]:
    """Structural claims inferred from Shape markers, Annotated hints or
    see shapes_from_signature(). Two checks:

    - `shape`: synthesizes inputs whose declared dims agree on shared
      symbolic names within a trial, calls the real function, and checks
      the real output's shape against what its own declared Shape
      resolves to. This assumes output shape is a pure function of the
      input dims, sound for an elementwise transform, meaningless for
      something like a clustering function whose real output size
      depends on the data (how many clusters it actually converges to),
      not just the input's declared length.
    - `shape_enforced`: the input-side check that assumption's failure
      mode motivates instead, does the function reject a *mismatched*
      input shape (raise, or return `None`) rather than silently
      proceeding on data its own declared contract says it shouldn't
      accept. Whether the function's real output shape is data-dependent
      or not, this is always well-defined: either it guards its input or
      it doesn't. See _shape_enforced_probe().

    Empty if the signature has no Shape markers at all; this is purely
    additive, never a claim about a function that never opted in."""
    shapes = shapes_from_signature(fn)
    if "return" not in shapes:
        return []
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return []
    param_dims = {p: shapes[p].dims for p in sig.parameters if p in shapes}
    return_dims = shapes["return"].dims
    if not param_dims:
        return []

    names = {d for dims in param_dims.values() for d in dims if isinstance(d, str)}
    names |= {d for d in return_dims if isinstance(d, str)}
    rng = random.Random(_RNG_SEED)
    stmt = (f"shape({fn.__name__}(" + ", ".join(param_dims) + f")) == "
            f"{return_dims}, for shared dims {sorted(names) or 'none'}")

    checked, cx = 0, None
    for _ in range(trials):
        sizes = {n: rng.randint(1, 4) for n in names}
        args = {p: _synth_nested(dims, sizes, rng) for p, dims in param_dims.items()}
        expected = tuple(sizes[d] if isinstance(d, str) else d for d in return_dims)
        try:
            result = _call(fn, sig, args)
        except Exception:
            continue
        checked += 1
        actual = _actual_shape(result)
        if actual != expected:
            cx = f"dims={sizes}: expected shape {expected}, got {actual}"
            break
    if cx is not None:
        probes = [Probe("shape", stmt, "falsified", n=checked, counterexample=cx)]
    elif checked == 0:
        probes = [Probe("shape", stmt, "skipped", note="no evaluable inputs")]
    else:
        probes = [Probe("shape", stmt, "holds", n=checked)]

    enforced = _shape_enforced_probe(fn, sig, param_dims, names, rng)
    if enforced is not None:
        probes.append(enforced)
    return probes
