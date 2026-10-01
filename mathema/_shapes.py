# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Shapes of container values against a declared space or shape marker.

A space binding (`R^(30,15)`, `[0, 1]^30`, `R^(n,15)`) and a `Shape`,
`Vec` or `Mat` marker each state a value's dimensions, one token per
axis: an integer fixes the axis at that size, a name is one dimension
wherever it appears. This module reads a value's shape (nested lists
directly, a runtime type through its adapter), decides whether that
shape fits a declared one, and words a mismatch the way a caller can
act on it.
"""
from __future__ import annotations

import ast
import dataclasses
import random


def dims_of(bound) -> tuple:
    """The dimension tokens a domain carries, each as text: `("30",
    "15")` for `R^(30,15)`, `("n", "15")` for `R^(n,15)`, `()` for a
    scalar domain or no domain."""
    dims = getattr(bound, "dims", ()) or ()
    return tuple(str(d) for d in dims)


def fixed_size(dim) -> "int | None":
    """The size a dimension token fixes (`30`, `"30"`), or None for a
    dimension name."""
    if isinstance(dim, bool):
        return None
    if isinstance(dim, int):
        return dim
    text = str(dim)
    return int(text) if text.isdigit() else None


def _is_number(v) -> bool:
    return (isinstance(v, (int, float, complex)) and not isinstance(v, bool)
            or (type(v).__module__ == "numpy" and hasattr(v, "item")
                and getattr(v, "ndim", 0) == 0))


def _nested_shape(value) -> "tuple | None":
    """The shape of nested lists, read down the first elements; None
    for ragged rows."""
    shape: list = []
    v = value
    while isinstance(v, (list, tuple)):
        shape.append(len(v))
        if not v:
            break
        widths = {len(r) if isinstance(r, (list, tuple)) else -1 for r in v}
        if len(widths) > 1:
            return None
        v = v[0]
    return tuple(shape)


def observed_shape(value) -> "tuple | None":
    """Intent:
        The shape of a container value: `(n,)` for a vector, `(rows,
        cols)` for a matrix, `(rows,)` for a table of equal-length
        columns. Nested lists are read down their first elements; a
        runtime type is read through `runtime_types.observe`, so a
        numpy array, a pandas or polars Series or DataFrame reports
        the shape its adapter gives it. `()` for a number or a missing
        scalar; None for a value with no shape reading (a string, a
        mapping that is not a table, ragged rows).
    """
    from .domain import is_missing
    from .runtime_types import AbstractMat, AbstractTable, AbstractVec, observe
    if isinstance(value, (str, bytes)):
        return None
    if _is_number(value) or is_missing(value):
        return ()
    if type(value).__module__.split(".", 1)[0] == "numpy":
        shape = getattr(value, "shape", None)
        if isinstance(shape, tuple) and all(isinstance(n, int) for n in shape):
            return tuple(shape)
    seen = observe(value)
    if isinstance(seen, AbstractVec):
        return (len(seen),)
    if isinstance(seen, AbstractMat):
        return seen.shape
    if isinstance(seen, AbstractTable):
        lengths = {len(c) for c in seen.columns.values()}
        return (lengths.pop(),) if len(lengths) == 1 else None
    if _is_number(seen):
        return ()
    shape = getattr(value, "shape", None)
    if isinstance(shape, tuple) and all(isinstance(n, int) for n in shape):
        return tuple(shape)
    if isinstance(value, (list, tuple)):
        return _nested_shape(value)
    if isinstance(value, dict):
        lengths = set()
        for col in value.values():
            s = observed_shape(col)
            if s is None or len(s) != 1:
                return None
            lengths.add(s[0])
        return (lengths.pop(),) if len(lengths) == 1 else None
    return None


def leaves(value):
    """Every element of a container value, in order: a vector's
    values, a matrix's entries row by row, a table's cells column by
    column, a nested list's leaves; a runtime type through its
    adapter. A number is its own one leaf."""
    from .runtime_types import AbstractMat, AbstractTable, AbstractVec, observe
    if _is_number(value):
        yield value
        return
    seen = observe(value)
    if isinstance(seen, AbstractVec):
        yield from seen.values
        return
    if isinstance(seen, AbstractMat):
        for row in seen.rows:
            yield from row
        return
    if isinstance(seen, AbstractTable):
        for col in seen.columns.values():
            yield from col.values
        return
    if isinstance(value, dict):
        for col in value.values():
            yield from leaves(col)
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            yield from leaves(v)
        return
    if hasattr(value, "tolist"):
        yield from leaves(value.tolist())
        return
    yield value


def fits(shape: tuple, dims: tuple, sizes: "dict | None" = None) -> bool:
    """Whether a value of `shape` fits `dims`: the same rank, every
    fixed axis at its size, every named axis at least 1 (`R^n` is never
    empty) and, where `sizes` binds the name, exactly that size."""
    if len(shape) != len(dims):
        return False
    sizes = sizes or {}
    for n, d in zip(shape, dims):
        size = fixed_size(d)
        if size is None:
            size = sizes.get(str(d))
        if size is None:
            if n < 1:
                return False
        elif n != size:
            return False
    return True


def _is_container(value) -> bool:
    return (isinstance(value, (list, tuple, dict))
            or (hasattr(value, "shape") and hasattr(value, "__len__")))


def contains_shaped(value, dom) -> "bool | None":
    """Intent:
        Membership of a container `value` in a space domain: its shape
        fits the domain's dims and every element is in the element
        domain. A container with no shape reading (ragged rows) is
        outside. None when `value` is not a container (a number, a
        missing scalar, a string), which the caller then judges as an
        element.
    """
    from .domain import domain_contains
    shape = observed_shape(value)
    if shape is None:
        return False if _is_container(value) else None
    if shape == ():
        return None
    if not fits(shape, dims_of(dom)):
        return False
    element = dataclasses.replace(dom, dims=())
    return all(domain_contains(v, element) for v in leaves(value))


def in_space(value, bound, sizes: "dict | None" = None) -> bool:
    """Membership of a value read as a whole against a domain: a
    container by its shape and its elements, a number only in a scalar
    domain (a number is not a member of `R^(3,4)`). A named axis takes
    the size `sizes` binds to the name, when it binds one. A leaf that
    is not a member of the element domain, a missing value included,
    makes the container not a member, the container form of the scalar
    rule that a missing value is a member of nothing."""
    from .domain import domain_contains, is_missing
    dims = dims_of(bound)
    if not dims:
        return domain_contains(value, bound)
    shape = observed_shape(value)
    if shape is None or shape == () or not fits(shape, dims, sizes):
        return False
    element = dataclasses.replace(bound, dims=())
    return all(not is_missing(v) and domain_contains(v, element)
               for v in leaves(value))


def axis_sizes(domain: dict, values: dict) -> dict:
    """The size each dimension name is bound to by the actual values,
    `{name: size}`: every named axis of a parameter whose binding
    states a space, measured off the value passed for it. A name two
    parameters bind to different sizes is left out."""
    out: dict = {}
    clash: set = set()
    for p, bound in (domain or {}).items():
        dims = dims_of(bound)
        if not dims or p not in values:
            continue
        shape = observed_shape(values[p])
        if shape is None or len(shape) != len(dims):
            continue
        for n, d in zip(shape, dims):
            if fixed_size(d) is not None:
                continue
            if d in out and out[d] != n:
                clash.add(d)
            out.setdefault(d, n)
    return {k: v for k, v in out.items() if k not in clash}


# --- wording ----------------------------------------------------------

def shape_text(shape: tuple) -> str:
    """A shape as it is written: `(2, 3)`, `(30,)`."""
    return "(" + ", ".join(str(n) for n in shape) + ("," if len(shape) == 1 else "") + ")"


_ABSENT = object()


def words(shape: "tuple | None", value=_ABSENT) -> str:
    """A shape in words: "length 5", "3 by 4", "shape (2, 3, 4)", "a
    number" for `()`, "no shape" for None. Given the value, a missing
    scalar is named ("None", "NaN") rather than called a number."""
    if shape is None:
        return "no shape"
    if shape == ():
        if value is None:
            return "None"
        if isinstance(value, float) and value != value:
            return "NaN"
        return "a number"
    if len(shape) == 1:
        return f"length {shape[0]}"
    if len(shape) == 2:
        return f"{shape[0]} by {shape[1]}"
    return f"shape {shape_text(shape)}"


def describe(shape: "tuple | None", value=_ABSENT) -> str:
    """A value's shape as a predicate: "has length 5", "is 3 by 4",
    "has shape (2, 3, 4)", "is a number", "is None", "has no shape"."""
    verb = "is" if shape == () or (shape is not None and len(shape) == 2) else "has"
    return f"{verb} {words(shape, value)}"


def must(dims: tuple, sizes: "dict | None" = None) -> str:
    """What a value of `dims` must be, after "so x must": "have length
    4", "be 4 by p", "have shape (2, 3, 4)"."""
    verb = "be" if len(dims) == 2 else "have"
    return f"{verb} {expected(dims, sizes)}"


def marker_text(dims: tuple) -> str:
    """A shape as a marker is written: `Vec("n")`, `Mat("m", "n")`,
    `Mat(30, 15)`, `Shape("a", "b", "c")`."""
    shown = ", ".join(str(d) if fixed_size(d) is not None else f'"{d}"'
                      for d in dims)
    if len(dims) == 1:
        return f"Vec({shown})"
    if len(dims) == 2:
        return f"Mat({shown})"
    return f"Shape({shown})"


def expected(dims: tuple, sizes: "dict | None" = None) -> str:
    """The shape `dims` calls for, in words, a name replaced by the
    size bound to it in `sizes` where one is: "length 30", "30 by 15",
    "n by 15", "shape (2, 3, 4)", "a number"."""
    sizes = sizes or {}
    shown = [str(sizes.get(str(d), d)) for d in dims]
    if not shown:
        return "a number"
    if len(shown) == 1:
        return f"length {shown[0]}"
    if len(shown) == 2:
        return f"{shown[0]} by {shown[1]}"
    return "shape (" + ", ".join(shown) + ")"


def axis_text(axis: int, size: int, ndim: int) -> str:
    """One fixed axis in words: "has length 30" for a vector, "has 30
    rows" or "has 15 columns" for a matrix, "has size 30 on axis 2"
    beyond."""
    if ndim == 1:
        return f"has length {size}"
    if ndim == 2 and axis == 0:
        return f"has {size} rows"
    if ndim == 2 and axis == 1:
        return f"has {size} columns"
    return f"has size {size} on axis {axis}"


def space_text(bound) -> str:
    """A space domain as a claim writes it, in ascii: `R^(30,15)`,
    `[0.0, 1.0]^30`."""
    from .domain import render_domain
    text = render_domain(bound, show_missing=False, ascii_mode=True)
    return text.split(":", 1)[0] if text.startswith(("[", "(")) else text


def domain_text(bound) -> str:
    """A domain as `enforce_domain` renders it in its own messages, so a
    stack of the two guards names one domain one way: `[0.0, 1.0]³⁰ ⊂ ℝ
    ∪ {∅}` in unicode."""
    from .domain import render_domain
    return render_domain(bound, show_missing=True)


def outside_space(name: str, value, bound) -> "str | None":
    """"A has shape (2, 3); the domain is R^(30,15)" when `value`'s
    shape does not fit the space `bound` names; None when it does, or
    when `bound` names no space."""
    dims = dims_of(bound)
    if not dims:
        return None
    shape = observed_shape(value)
    if shape is not None and shape != () and fits(shape, dims):
        return None
    found = ("has no shape" if shape is None else "is a number" if shape == ()
             else f"has shape {shape_text(shape)}")
    return f"{name} {found}; the domain is {space_text(bound)}"


# --- draws in and outside the space -----------------------------------------

def _size_or(dim, default: int) -> int:
    size = fixed_size(dim)
    return default if size is None else size


def shaped(bound, rng: random.Random, element) -> list:
    """A nested list of the space `bound` names, every fixed axis at its
    size and every named axis at 3, each leaf drawn by `element`."""
    sizes = [_size_or(d, 3) for d in dims_of(bound)]

    def build(axis):
        if axis == len(sizes):
            return element()
        return [build(axis + 1) for _ in range(sizes[axis])]

    return build(0)


def outside_shapes(bound) -> list:
    """Every shape just outside the space `bound` names, as size
    tuples, a named axis at 3: each fixed axis one larger, each fixed
    axis above 1 one smaller, one rank higher, and one rank lower for a
    matrix or deeper. Empty when `bound` names no space."""
    dims = dims_of(bound)
    if not dims:
        return []
    base = [_size_or(d, 3) for d in dims]
    out: list = []
    for k, d in enumerate(dims):
        if fixed_size(d) is None:
            continue
        up = list(base)
        up[k] += 1
        out.append(tuple(up))
        if base[k] > 1:
            down = list(base)
            down[k] -= 1
            out.append(tuple(down))
    out.append(tuple(base) + (2,))
    if len(dims) >= 2:
        out.append(tuple(base[:-1]))
    return out


def build_shape(shape: tuple, element) -> list:
    """A nested list of `shape`, each leaf drawn by `element`."""
    def build(axis):
        if axis == len(shape):
            return element()
        return [build(axis + 1) for _ in range(shape[axis])]
    return build(0)


def wrong_shaped(bound, rng: random.Random, element) -> "tuple | None":
    """`(value, shape)`: the first outside of the space `bound` names,
    built with in-domain elements; None when `bound` names no space."""
    shapes = outside_shapes(bound)
    if not shapes:
        return None
    return build_shape(shapes[0], element), shapes[0]


# --- a large container witness ---------------------------------------------

#: a container with more entries than this prints its shape, its first
#: few entries and a count, never every entry; a 4 by 4 matrix or a
#: 16-vector still prints in full
WITNESS_ENTRIES = 16


def witness_text(value) -> "str | None":
    """Intent:
        A short rendering for a large container witness: "30 by 15,
        every entry -1.79769e+308" when the entries agree, else "30 by
        15, first row [-8.77, -2.73, ...] (450 entries)"; for a vector
        "length 30, first entries [...] (30 entries)". None for a
        number, a string, or a container of at most `WITNESS_ENTRIES`
        entries, which prints in full.
    """
    if isinstance(value, (str, bytes)) or _is_number(value):
        return None
    shape = observed_shape(value)
    if shape is None or shape == ():
        return None
    entries = list(leaves(value))
    if len(entries) <= WITNESS_ENTRIES:
        return None

    def one(v) -> str:
        return f"{v:.6g}" if isinstance(v, float) else repr(v)

    same = all(v == entries[0] or (isinstance(v, float) and isinstance(entries[0], float)
                                   and v != v and entries[0] != entries[0])
               for v in entries)
    if same:
        return f"{words(shape)}, every entry {one(entries[0])}"
    if len(shape) == 1:
        head = ", ".join(one(v) for v in entries[:6])
        return f"{words(shape)}, first entries [{head}, ...] ({len(entries)} entries)"
    first_row = entries[:shape[-1]] if len(shape) == 2 else entries[:6]
    head = ", ".join(one(v) for v in first_row[:6])
    tail = ", ..." if len(first_row) > 6 else ""
    return f"{words(shape)}, first row [{head}{tail}] ({len(entries)} entries)"


def fixed_clause(name: str, dims: tuple) -> str:
    """The one clause a sketch adds for a binding that fixes a size:
    "the binding fixes xs at length 30", "the binding fixes A at 30 by
    15"; a fixed axis beside a name reads "the binding fixes A at n by
    15"."""
    return f"the binding fixes {name} at {expected(dims)}"


# --- a literal dimension against a premise -------------------------------

_RELATIONS = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b,
              ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
              ">": lambda a, b: a > b, "<": lambda a, b: a < b}
_FLIPPED = {"==": "==", "!=": "!=", ">=": "<=", "<=": ">=", ">": "<", "<": ">"}


def _dim_ref(text: str) -> "tuple | None":
    """`(param, axis)` for `dim(param, axis)` or `dim(param)`, else
    None."""
    try:
        node = ast.parse(str(text).strip(), mode="eval").body
    except SyntaxError:
        return None
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "dim" and node.args
            and isinstance(node.args[0], ast.Name) and not node.keywords):
        return None
    if len(node.args) == 1:
        return node.args[0].id, 0
    if len(node.args) == 2 and isinstance(node.args[1], ast.Constant) \
            and isinstance(node.args[1].value, int):
        return node.args[0].id, int(node.args[1].value)
    return None


def _constant(text: str) -> "float | None":
    try:
        v = ast.literal_eval(str(text).strip())
    except Exception:
        return None
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def premise_against_fixed_dim(premises, domain: dict) -> "tuple | None":
    """Intent:
        The first premise that bounds a dimension a binding fixes to a
        size the premise refuses (`assuming len(xs) == 5` over
        `[0, 1]^30`), as `(param, premise_text, axis_words)`, or None
        when no premise contradicts a fixed dimension. `premises` are
        `(lhs, relation, rhs)` triples in the grammar's canonical
        spelling (`dim(xs, 0)`).
    """
    for lhs, rel, rhs in premises or ():
        ref, const, relation = _dim_ref(lhs), _constant(rhs), rel
        if ref is None:
            ref, const = _dim_ref(rhs), _constant(lhs)
            relation = _FLIPPED.get(rel, rel)
        if ref is None or const is None or relation not in _RELATIONS:
            continue
        param, axis = ref
        dims = dims_of(domain.get(param))
        if axis >= len(dims):
            continue
        size = fixed_size(dims[axis])
        if size is None or _RELATIONS[relation](size, const):
            continue
        shown = const if isinstance(const, int) or not float(const).is_integer() else int(const)
        return (param, f"dim({param}, {axis}) {relation} {shown}",
                axis_text(axis, size, len(dims)))
    return None


# --- a function's dimensions, enforced at entry and at exit ----------------

@dataclasses.dataclass(frozen=True)
class DimensionPlan:
    """The dimensions a function declares: per parameter its dimension
    tokens and the words naming where they come from (`the shape
    Mat("m", "n")`, `the domain R^(30,15)`), and the return marker's
    tokens, when there is one."""
    params: dict
    result: "tuple | None" = None
    result_source: "str | None" = None
    elements: dict = dataclasses.field(default_factory=dict)
    numbers_judged_elsewhere: frozenset = frozenset()


def dimension_plan(shapes: dict, domains: dict) -> DimensionPlan:
    """Intent:
        The plan for a function from its `Shape` markers (`shapes`,
        keyed by parameter and `"return"`) and the spaces its declared
        claims bind (`domains`, keyed by parameter). A marker names the
        axes; a binding on the same parameter fixes any axis it writes
        as a number; a binding alone names the axes itself.

    Raises:
        ValueError when a marker and a binding disagree on a
        parameter's rank.
    """
    params: dict = {}
    pinned: dict = {}
    pinned_by: dict = {}
    for name in sorted(set(shapes) | set(domains)):
        if name == "return":
            continue
        marker = (tuple(str(d) for d in shapes[name].dims)
                  if name in shapes else ())
        binding = dims_of(domains.get(name))
        if marker and binding:
            if len(marker) != len(binding):
                raise ValueError(
                    f"{name}: the claim gives it {len(binding)} dimension"
                    f"{'s' if len(binding) != 1 else ''} "
                    f"({space_text(domains[name])}) but its shape marker "
                    f"declares {len(marker)} ({marker_text(marker)})")
            for m, b in zip(marker, binding):
                size = fixed_size(b)
                if size is None or fixed_size(m) is not None:
                    continue
                if m in pinned and pinned[m] != size:
                    raise ValueError(
                        f"{m} is fixed to two sizes: {pinned[m]} by "
                        f"{pinned_by[m]}'s binding and {size} by {name}'s "
                        f"binding; one shared dimension has one size")
                pinned[m] = size
                pinned_by[m] = name
            dims = tuple(b if fixed_size(b) is not None else m
                         for m, b in zip(marker, binding))
            source = (f"the shape {marker_text(marker)} with the domain "
                      f"{domain_text(domains[name])}")
        elif marker:
            dims, source = marker, f"the shape {marker_text(marker)}"
        elif binding:
            dims, source = binding, f"the domain {domain_text(domains[name])}"
        else:
            continue
        params[name] = (dims, source)
    if pinned:
        # a name one binding fixes is that size wherever the marker
        # names it
        params = {p: (tuple(str(pinned.get(d, d)) for d in dims), source)
                  for p, (dims, source) in params.items()}
    result = (tuple(str(d) for d in shapes["return"].dims)
              if "return" in shapes else None)
    # a space a claim binds states its entries as well as its shape
    elements = {p: dataclasses.replace(domains[p], dims=())
                for p in params
                if dims_of(domains.get(p)) and dataclasses.is_dataclass(
                    domains[p])}
    return DimensionPlan(params, result,
                         marker_text(result) if result is not None else None,
                         elements)


def _table_as_matrix(value, rank: int) -> "tuple | None":
    """Intent:
        The `(rows, columns)` shape of a table whose columns are all of
        one length, read as the matrix it holds when the declared rank
        is two; None for anything else.
    """
    from .runtime_types import AbstractTable, observe
    if rank != 2:
        return None
    seen = observe(value)
    if not isinstance(seen, AbstractTable) or not seen.columns:
        return None
    lengths = {len(c) for c in seen.columns.values()}
    if len(lengths) != 1:
        return None
    return (lengths.pop(), len(seen.columns))


def _entry_outside(value, element,
                   numbers_judged_elsewhere: bool = False) -> "tuple | None":
    """Intent:
        `(entry,)` for the first entry of a container value outside the
        element domain, or None when every entry is a member. A missing
        entry is judged by the element domain's own missing rule; any
        other entry must be a number of the element domain
        (`domain.number_member`), so text, a bool, an imaginary number
        and an infinity in a bare real set are outside.
        With `numbers_judged_elsewhere` (an `enforce_domain` guard on
        the same parameter judges every number), only an entry that is
        not a number is reported here.
    """
    from .domain import domain_contains, is_missing, number_member
    kind = getattr(getattr(value, "dtype", None), "kind", None)
    if (numbers_judged_elsewhere and kind in ("i", "u", "f", "c", "b")
            and type(value).__module__ == "numpy"):
        return None
    if (kind in ("i", "u", "f") and type(value).__module__ == "numpy"
            and getattr(element, "base_type", None) == "R"
            and not element.pieces and not element.excluded):
        # a numeric array against the bare reals: only an infinity is
        # outside, found without visiting every entry in Python
        flat = value.ravel()
        if kind != "f":
            return None
        import numpy
        hits = numpy.flatnonzero(numpy.isinf(flat))
        return (flat[hits[0]].item(),) if hits.size else None
    entries = leaves(value)
    if (kind == "f" and type(value).__module__ == "numpy"
            and str(getattr(value, "dtype", "")) != "float64"):
        # a narrower or wider float keeps its own type, so each entry
        # meets an endpoint parsed in that type
        entries = iter(value.ravel())
    for leaf in entries:
        if is_missing(leaf):
            if not numbers_judged_elsewhere and not domain_contains(
                    leaf, element):
                return (leaf,)
            continue
        member = number_member(leaf, element)
        if member is None or (not member and not numbers_judged_elsewhere):
            return (leaf,)
    return None


def entry_problem(plan: DimensionPlan, arguments: dict) -> tuple:
    """Intent:
        `(problem, bound)`: the first argument whose shape breaks the
        plan, worded for the caller ("x has length 5; a is 3 by 4, so x
        must have length 4"; "A is 2 by 3; the shape Mat(30, 15)
        expects 30 by 15"), or None; and the sizes this call bound to
        each dimension name, `{name: (size, param, shape)}`.
    """
    bound: dict = {}
    for p, (dims, source) in plan.params.items():
        if p not in arguments:
            continue
        value = arguments[p]
        shape = observed_shape(value)
        if shape is None or len(shape) != len(dims):
            shape = _table_as_matrix(value, len(dims)) or shape
        if shape is None or len(shape) != len(dims):
            return (f"{p} {describe(shape, value)}; {source} expects "
                    f"{expected(dims)}", bound)
        for n, d in zip(shape, dims):
            size = fixed_size(d)
            if size is not None:
                if n != size:
                    return (f"{p} {describe(shape)}; {source} expects "
                            f"{expected(dims)}", bound)
                continue
            if d in bound and bound[d][0] != n:
                other_n, other_p, other_shape = bound[d]
                sizes = {k: v[0] for k, v in bound.items()}
                return (f"{p} {describe(shape)}; {other_p} "
                        f"{describe(other_shape)}, so {p} must "
                        f"{must(dims, sizes)}", bound)
            bound.setdefault(d, (n, p, shape))
        element = plan.elements.get(p)
        if element is not None:
            outside = _entry_outside(
                value, element, p in plan.numbers_judged_elsewhere)
            if outside is not None:
                return (f"{p} has the entry {outside[0]!r}, outside "
                        f"{domain_text(element)}; {source} expects every "
                        f"entry in it", bound)
    return None, bound


def exit_problem(plan: DimensionPlan, bound: dict, result,
                 fn_name: str) -> "str | None":
    """Intent:
        The words for a result whose shape breaks the return marker with
        the names this call bound ("matvec returned length 4; the return
        shape Vec("m") with m = 3 expects length 3"), or None when the
        result fits or there is no return marker. A name no argument
        bound is not checked.
    """
    if plan.result is None:
        return None
    dims = plan.result
    sizes = {d: bound[d][0] for d in dims if d in bound}
    shape = observed_shape(result)
    if shape is not None and len(shape) == len(dims):
        fits_all = True
        for n, d in zip(shape, dims):
            want = fixed_size(d) if fixed_size(d) is not None else sizes.get(d)
            if want is not None and want != n:
                fits_all = False
        if fits_all:
            return None
    with_text = ", ".join(f"{d} = {sizes[d]}" for d in dims if d in sizes)
    source = f"the return shape {plan.result_source}"
    if with_text:
        source += f" with {with_text}"
    return (f"{fn_name} returned {words(shape, result)}; {source} expects "
            f"{expected(dims, sizes)}")
