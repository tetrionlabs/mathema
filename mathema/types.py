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

import random
import typing
from dataclasses import dataclass, field

from .grammar import Interval
from .probing import Probe, _RNG_SEED
from ._signatures import callable_signature


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


def Vec(*items, runtime: "str | None" = None):
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

    `runtime` names the parameter's runtime type, the object the
    function receives (`Vec("n", runtime="pandas.Series")`,
    `Mat("n", "n", runtime="numpy.ndarray")`); the value is drawn as
    always and realised as that runtime type before each call. It
    adds a `runtime_types.RuntimeType` marker, the strongest evidence
    of a parameter's runtime type.
    """
    dims = tuple(d for d in items if isinstance(d, (str, int)))
    props = tuple(d for d in items if not isinstance(d, (str, int)))
    markers = (Shape(*dims),) + tuple(
        (m() if isinstance(m, type) else m) for m in props)
    if runtime is not None:
        from .runtime_types import RuntimeType
        markers = markers + (RuntimeType(str(runtime)),)
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


def domain_from_signature(fn, guards: bool = True) -> dict:
    """Per-parameter domain implied by a bound marker (Probability,
    Positive, InRange, UnitBall, ...) on that parameter, ready to merge
    into `domain=` exactly like an explicitly declared one. A parameter
    with no marker is absent. With `guards`, a function
    `enforce_domain()` wraps also declares the domain its guard checks,
    and one `enforce_dimensions()` wraps the space its claims bind for
    each parameter it guards (entries as well as shape), so every draw
    is one the guard admits.

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
    enforced = getattr(fn, "__mathema_enforced_domain__", None) if guards else None
    for name, bound in (enforced or {}).items():
        out[name] = tuple(bound) if isinstance(bound, list) else bound
    shaped = (getattr(fn, "__mathema_enforced_dimensions__", None)
              if guards else None)
    if shaped:
        # the space a claim binds for a parameter enforce_dimensions()
        # guards states its entries too (`[0, 1]^30`)
        from .authoring import _domain_from_declared_claims
        try:
            spaces = _domain_from_declared_claims(fn, None, ".")
        except Exception:
            spaces = {}
        for name in shaped:
            space = spaces.get(name)
            if name not in out and getattr(space, "dims", ()):
                out[name] = space
    return out


def _optional_parts(hint) -> tuple:
    """`(optional, inner)`: whether a union admits `None`, and the one
    other member (or the hint itself when it is no such union)."""
    import types as _types
    origin = typing.get_origin(hint)
    if origin is typing.Union or origin is getattr(_types, "UnionType", None):
        args = typing.get_args(hint)
        present = [a for a in args if a is not type(None)]
        optional = len(present) < len(args)
        return optional, (present[0] if len(present) == 1 else hint)
    return False, hint


def _scalar_slot_type(hint) -> "str | None":
    """The scalar runtime's name for a Python type, `float`, `int`,
    `bool`, `str`, `complex`, `datetime`, or None when it is no scalar
    type the table names."""
    import datetime as _dt
    if not isinstance(hint, type):
        return None
    if issubclass(hint, bool):
        return "bool"
    if issubclass(hint, (_dt.datetime, _dt.date)):
        return "datetime"
    if issubclass(hint, str):
        return "str"
    if issubclass(hint, int):
        return "int"
    if issubclass(hint, float):
        return "float"
    if issubclass(hint, complex):
        return "complex"
    module = getattr(hint, "__module__", "") or ""
    if module.startswith("numpy"):
        name = hint.__name__.lower()
        if name.startswith(("float", "double", "half", "longdouble")):
            return "float"
        if name.startswith(("int", "uint", "long", "short", "byte")):
            return "int"
        if name.startswith("bool"):
            return "bool"
        if name.startswith("complex"):
            return "complex"
        if name.startswith("datetime"):
            return "datetime"
    if module.startswith("pandas") and hint.__name__ == "Timestamp":
        return "datetime"
    return None


def _element_policy(args) -> "tuple[str, tuple] | None":
    """`(slot type suffix, members)` a container's element type states,
    `list[float]` its floats' `nan`, or None when it states none."""
    from .runtime_types import resolve_missing
    if not args:
        return None
    optional, inner = _optional_parts(args[-1] if len(args) > 1 else args[0])
    scalar = _scalar_slot_type(inner)
    if scalar is None:
        return None
    members = (("null",) if optional else ()) + resolve_missing(scalar)
    return scalar, members


def _numpy_dtype_scalar(hint) -> "str | None":
    """The scalar type a subscripted `numpy.ndarray`/`NDArray` states for
    its entries (`NDArray[np.int64]`), or None. A shape argument
    (`ndarray[tuple[int, ...], dtype[...]]`) states no entry type."""
    for arg in typing.get_args(hint):
        if arg is tuple or typing.get_origin(arg) is tuple:
            continue
        for inner in (arg, *typing.get_args(arg)):
            scalar = _scalar_slot_type(inner)
            if scalar is not None:
                return scalar
    return None


def _policy_of_hint(hint, detection):
    """The missing-value defaults of one live annotation."""
    from .domain import NO_ANNOTATION, MissingDefaults
    from .runtime_types import (absence_defined, resolve_absence,
                                resolve_missing)
    if hint is typing.Any:
        return NO_ANNOTATION
    for m in _markers(hint):
        if _marker_interval(m) is not None:
            return MissingDefaults(False, (), type(m).__name__)
    if typing.get_origin(hint) is typing.Annotated:
        hint = typing.get_args(hint)[0]
    optional, inner = _optional_parts(hint)
    if detection is not None and detection.adapter != "list":
        name = detection.adapter
        if name == "numpy.ndarray":
            from .runtime_types._adapters import _alias_value
            scalar = (_numpy_dtype_scalar(inner)
                      or _numpy_dtype_scalar(_alias_value(inner)))
            if scalar is not None and not resolve_missing(scalar):
                return MissingDefaults(optional, (), f"{name}[{scalar}]",
                                       absence=("None",))
        return MissingDefaults(optional or absence_defined(name),
                               resolve_missing(name), name,
                               absence=resolve_absence(name) or ("None",))
    origin = typing.get_origin(inner) or inner
    if origin in (list, tuple):
        element = _element_policy(typing.get_args(inner))
        if element is not None:
            scalar, members = element
            return MissingDefaults(optional, members,
                                   f"{origin.__name__}[{scalar}]")
        return MissingDefaults(optional, resolve_missing("list"), origin.__name__)
    scalar = _scalar_slot_type(inner)
    if scalar is not None:
        return MissingDefaults(optional, resolve_missing(scalar), scalar)
    name = getattr(inner, "__qualname__", None) or str(inner)
    return MissingDefaults(optional, (), name)


def _policy_of_text(text: str):
    """The missing-value defaults of an annotation known only as source
    text (a name the function's module does not bind)."""
    from .analysis import _annotation_base
    from .domain import NO_ANNOTATION, MissingDefaults
    from .runtime_types import resolve_missing
    lowered = text.strip().strip("'\"").lower()
    optional = (lowered.startswith(("optional[", "typing.optional["))
                or "none" in [m.strip() for m in lowered.split("|")])
    base = _annotation_base(lowered)
    if base in ("", "any", "typing.any"):
        return NO_ANNOTATION
    head = base.split("[", 1)[0]
    if head in ("float", "int", "bool", "str", "complex"):
        return MissingDefaults(optional, resolve_missing(head), head)
    if head in ("list", "tuple"):
        inner = base[len(head) + 1:-1] if "[" in base else ""
        if inner in ("float", "int", "bool", "str", "complex"):
            return MissingDefaults(optional, resolve_missing(inner),
                                   f"{head}[{inner}]")
        return MissingDefaults(optional, resolve_missing("list"), head)
    return MissingDefaults(optional, (), text.strip())


def missing_policy_from_signature(fn) -> dict:
    """Intent:
        Each parameter's missing-value defaults, read off its
        annotation, as `{param: domain.MissingDefaults}`: whether the
        object may be absent (an `Optional[...]`/`X | None`, or a
        runtime type whose definition row states an absence) and the
        members of the hole class on its slots. A `float` slot holds
        `nan`, a datetime `NaT`, an `int`, `bool`, `str` or a class
        nothing; a `list` element `null` and `nan`, `list[float]` `nan`,
        `list[int]` nothing; a runtime type (`numpy.ndarray`,
        `pandas.Series`, a registered adapter) the members its adapter
        and the definition rows give. A bound marker (`Probability`)
        admits neither kind, and a parameter with no annotation admits
        both (`domain.NO_ANNOTATION`).
    """
    import inspect

    from .domain import NO_ANNOTATION
    from .runtime_types import detect_parameters
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        return {}
    hints = _hints(fn)
    try:
        detected = detect_parameters(fn)
    except Exception:
        detected = {}
    out: dict = {}
    for p, param in sig.parameters.items():
        hint = hints.get(p)
        found = (detected.get(p) or (None,))[0]
        if hint is not None:
            out[p] = _policy_of_hint(hint, found)
        elif isinstance(param.annotation, str):
            if found is not None and found.adapter != "list":
                out[p] = _policy_of_hint(object, found)
            else:
                out[p] = _policy_of_text(param.annotation)
        elif param.annotation is inspect.Parameter.empty:
            out[p] = NO_ANNOTATION
        else:
            out[p] = _policy_of_hint(param.annotation, found)
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


def shapes_from_signature(fn, guards: bool = True) -> dict[str, Shape]:
    """Every Shape marker for fn's parameters and return, read from the
    signature's Annotated hints; the typing system is the one place
    a type belongs, so there is no docstring spelling for this. With
    `guards`, a function `enforce_dimensions()` wraps also declares the
    dimensions its guard checks (a marker's names with the sizes a claim
    binding fixed), so every draw is one the guard admits."""
    hints = _hints(fn)
    out: dict[str, Shape] = {}
    for name, hint in hints.items():
        dims = _shape_dims(hint)
        if dims is not None:
            out[name] = Shape(*dims)
    enforced = getattr(fn, "__mathema_enforced_dimensions__", None) if guards else None
    for name, dims in (enforced or {}).items():
        out[name] = Shape(*(int(d) if str(d).isdigit() else d for d in dims))
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


def _dimensions_enforced_probe(fn, sig, param_dims: dict, names: set,
                               rng: random.Random,
                               fixed: "dict | None" = None) -> Probe | None:
    """Does the real function guard against mismatched input shapes, the
    same way domain_enforced() checks whether a scalar guard exists,
    not "is the output the right shape for consistent input" (type_probes'
    own `result_dimensions` check, which assumes shape is a pure function of the
    input dims and says nothing about a function whose real output shape
    depends on the data itself, e.g. a converged cluster count), but "does
    it reject or gracefully decline inconsistent input at all". Only
    meaningful for a dim shared by two or more parameters (`Shape("m",
    "n")`/`Shape("n", "p")` sharing `n`, say); there's nothing to
    mismatch a single parameter's own dim against. `None` if no dim is
    shared this way. `fixed` holds the names a claim binding fixes, at
    their sizes."""
    shared = sorted(n for n in names
                    if sum(1 for dims in param_dims.values() if n in dims) > 1)
    if not shared:
        return None

    stmt = (f"{fn.__name__}(" + ", ".join(param_dims) + ") rejects a "
            f"mismatch on {', '.join(shared)}")
    if not _returns_in_shape(fn, sig, param_dims, names, rng, fixed):
        return Probe("dimensions_enforced", stmt, "skipped",
                     note="no evaluable inputs: no call at consistent "
                          "shapes returned")
    rejected, accepted_examples, checked = 0, [], 0
    for dim in shared:
        candidates = [p for p, dims in param_dims.items() if dim in dims]
        for _ in range(_SHAPE_MISMATCH_TRIALS):
            sizes = {n: rng.randint(1, 4) for n in names}
            sizes.update(fixed or {})
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
        return Probe("dimensions_enforced", stmt, "holds", n=checked)
    # one truth, no mode: a declared shared dim the code silently
    # accepts a mismatch on is a witnessed policy violation
    return Probe("dimensions_enforced", stmt, "falsified", n=checked,
                 counterexample="; ".join(accepted_examples[:3]),
                 note="silently accepting a shape mismatch violates the "
                      "declared shared dims")


def _returns_in_shape(fn, sig, param_dims: dict, names: set,
                      rng: random.Random, fixed: "dict | None") -> bool:
    """Whether one call at consistent, in-shape arguments returns: the
    evidence a rejection probe needs before a raise at a wrong shape
    can mean anything. Three draws are tried."""
    for _ in range(3):
        sizes = {n: rng.randint(1, 4) for n in names}
        sizes.update(fixed or {})
        args = {p: _synth_nested(dims, sizes, rng)
                for p, dims in param_dims.items()}
        try:
            _call(fn, sig, args)
        except Exception:
            continue
        return True
    return False


def _shape_words(dims: tuple) -> str:
    """"length n" or "shape m by n" for a parameter's dims, the words a
    statement uses: `a of shape m by n`, `x of length n`."""
    from ._shapes import expected
    text = expected(dims)
    return text if text.startswith(("length", "shape", "a ")) else f"shape {text}"


def _size_enforced_probe(fn, sig, param_dims: dict, names: set,
                         rng: random.Random, marker_dims: dict,
                         fixed: "dict | None" = None) -> Probe | None:
    """Does the real function reject a value of the wrong FIXED size (a
    parameter marked `Mat(30, 15)` called with one axis a little
    larger), the fixed-size counterpart of `_dimensions_enforced_probe`.
    Only a size a MARKER states (`marker_dims`, the signature's own
    shapes) is asked about: a size stated only by a claim's binding is
    the declared `excluded_outside_domain(p)` claim's question. Every
    other argument is drawn at its declared size. `None` when no marker
    fixes an axis."""
    from ._shapes import expected, words
    targets = {p: [k for k, d in enumerate(dims)
                   if isinstance(d, int) and not isinstance(d, bool)]
               for p, dims in marker_dims.items() if p in param_dims}
    targets = {p: axes for p, axes in targets.items() if axes}
    if not targets:
        return None
    stated = ", ".join(f"{p} ({expected(param_dims[p])})" for p in targets)
    stmt = (f"{fn.__name__}(" + ", ".join(param_dims) + ") rejects a "
            f"wrong fixed size on {stated}")
    if not _returns_in_shape(fn, sig, param_dims, names, rng, fixed):
        return Probe("size_enforced", stmt, "skipped",
                     note="no evaluable inputs: no call at consistent "
                          "shapes returned")
    rejected, checked = 0, 0
    # the wrong sizes each parameter accepted, distinct, so the witness
    # shows the smallest and the largest tried
    accepted: dict = {}
    for p, axes in targets.items():
        for axis in axes:
            for _ in range(_SHAPE_MISMATCH_TRIALS):
                sizes = {n: rng.randint(1, 4) for n in names}
                sizes.update(fixed or {})
                bumped = tuple(d + 1 + rng.randint(0, 2) if k == axis else d
                               for k, d in enumerate(param_dims[p]))
                args = {q: _synth_nested(bumped if q == p else dims, sizes, rng)
                        for q, dims in param_dims.items()}
                checked += 1
                try:
                    result = _call(fn, sig, args)
                except Exception:
                    rejected += 1
                    continue
                if result is None:
                    rejected += 1
                    continue
                tried = tuple(sizes[d] if isinstance(d, str) else d
                              for d in bumped)
                accepted.setdefault(p, set()).add(tried)
    if rejected == checked:
        return Probe("size_enforced", stmt, "holds", n=checked)
    examples = []
    for p, sizes_tried in accepted.items():
        ordered = sorted(sizes_tried)
        for tried in dict.fromkeys((ordered[0], ordered[-1])):
            examples.append(
                f"{p} {'is' if len(tried) == 2 else 'has'} {words(tried)} "
                f"where the shape fixes {expected(param_dims[p])}")
    return Probe("size_enforced", stmt, "falsified", n=checked,
                 counterexample="; ".join(examples),
                 note="silently accepting a wrong fixed size violates the "
                      "declared shape")


def type_probes(fn, trials: int = _TYPE_PROBE_TRIALS,
                domain: "dict | None" = None) -> list[Probe]:
    """Structural claims inferred from Shape markers, Annotated hints or
    see shapes_from_signature(), and from the spaces the claims being
    checked bind (`domain`, each parameter's bound: `for A in
    R^(30,15)` names A's axes and fixes their sizes the way a marker
    would, and a fixed size in it fixes a marker's name). Three checks:

    - `result_dimensions`: synthesizes inputs whose declared dims agree on shared
      symbolic names within a trial, calls the real function, and checks
      the real output's shape against what its own declared Shape
      resolves to. This assumes output shape is a pure function of the
      input dims, sound for an elementwise transform, meaningless for
      something like a clustering function whose real output size
      depends on the data (how many clusters it actually converges to),
      not just the input's declared length. Needs a return marker.
    - `dimensions_enforced`: the input-side check that assumption's
      failure mode motivates instead, does the function reject a
      *mismatched* input shape (raise, or return `None`) rather than
      silently proceeding on data its own declared contract says it
      shouldn't accept. Whether the function's real output shape is
      data-dependent or not, this is always well-defined: either it
      guards its input or it doesn't. See _dimensions_enforced_probe().
    - `size_enforced`: does the function reject a value of the wrong
      fixed size, for a parameter whose MARKER fixes an axis. A size a
      claim's binding alone fixes gates nothing here; that question is
      the declared `excluded_outside_domain(p)` claim. See
      _size_enforced_probe().

    Empty if neither the signature nor a binding shapes a parameter;
    this is purely additive, never a claim about a function that never
    opted in."""
    from types import SimpleNamespace

    from . import dimensions as _dims
    from ._shapes import dims_of, expected
    markers = shapes_from_signature(fn)
    shapes = dict(markers)
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        return []
    for p in sig.parameters:
        binding = dims_of((domain or {}).get(p))
        if binding and p not in shapes:
            shapes[p] = Shape(*(int(d) if d.isdigit() else d for d in binding))
    param_dims = {p: shapes[p].dims for p in sig.parameters if p in shapes}
    if not param_dims:
        return []
    # the one dimensional model the sampler uses: a name a binding fixes
    # is pinned there, and one name fixed to two sizes is a conflict the
    # claim itself reports
    try:
        resolver = _dims.resolve(
            SimpleNamespace(params=list(sig.parameters), param_kinds={}),
            markers, claim_domain=domain or {})
    except _dims.DimensionConflict:
        return []
    fixed_by_binding = dict(resolver.fixed)
    return_dims = shapes["return"].dims if "return" in shapes else None
    # each call realises the drawn nested lists as the parameters'
    # runtime types and observes the result as plain nested lists
    from .runtime_types import calling, detect_parameters
    fn = calling(fn, SimpleNamespace(runtime_types=detect_parameters(fn)))

    names = {d for dims in param_dims.values() for d in dims if isinstance(d, str)}
    names |= {d for d in (return_dims or ()) if isinstance(d, str)}
    rng = random.Random(_RNG_SEED)
    probes: list[Probe] = []
    if return_dims is not None:
        call_text = f"{fn.__name__}(" + ", ".join(param_dims) + ")"
        inputs = " and ".join(f"{p} of {_shape_words(dims)}"
                              for p, dims in param_dims.items())
        verb = "is" if len(return_dims) == 2 else "has"
        stmt = f"{call_text} {verb} {expected(return_dims)} for {inputs}"
        checked, cx = 0, None
        for _ in range(trials):
            sizes = {n: rng.randint(1, 4) for n in names}
            sizes.update(fixed_by_binding)
            args = {p: _synth_nested(dims, sizes, rng)
                    for p, dims in param_dims.items()}
            want = tuple(sizes[d] if isinstance(d, str) else d
                         for d in return_dims)
            try:
                result = _call(fn, sig, args)
            except Exception as e:
                # a raise at a consistent input is a counterexample: the
                # row judges the callable the user ships; a guard's exit
                # error already names both shapes, any other raise is
                # named with its type
                checked += 1
                cx = (f"dims={sizes}: {e}" if getattr(e, "at_exit", False)
                      else f"dims={sizes}: raised {type(e).__name__}"
                           + (f": {e}" if str(e) else ""))
                break
            checked += 1
            actual = _actual_shape(result)
            if actual != want:
                cx = f"dims={sizes}: expected shape {want}, got {actual}"
                break
        if cx is not None:
            probes.append(Probe("result_dimensions", stmt, "falsified", n=checked,
                                counterexample=cx))
        elif checked == 0:
            probes.append(Probe("result_dimensions", stmt, "skipped",
                                note="no evaluable inputs"))
        else:
            probes.append(Probe("result_dimensions", stmt, "holds", n=checked))
        enforced = _dimensions_enforced_probe(fn, sig, param_dims, names, rng,
                                              fixed_by_binding)
        if enforced is not None:
            probes.append(enforced)
    # only a size the signature's own marker states is asked about
    own_markers = shapes_from_signature(fn, guards=False)
    sized = _size_enforced_probe(fn, sig, param_dims, names, rng,
                                 {p: m.dims for p, m in own_markers.items()},
                                 fixed_by_binding)
    if sized is not None:
        probes.append(sized)
    return probes
