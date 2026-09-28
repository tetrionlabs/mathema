# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Runtime types: what a library hands a function as a vector, a
matrix or a table (a `list`, a `numpy.ndarray`, a `pandas.Series` or
`DataFrame`, a `polars.Series` or `DataFrame`), and the runtime type
adapters that realise mathema's abstract values as them.

A claim's sampler draws an abstract value (today still spelled as a
plain list or a list of lists); before each call of the function, the
parameter's runtime type adapter realises it as the object the
function expects, and what the function returns is observed back into
a plain value before anything compares it. A parameter's runtime type
is read from the function's signature only:

1. a marker, `Vec("n", runtime="pandas.Series")` or `Mat(..., runtime=)`;
2. the live annotation (`typing.get_type_hints`): `np.ndarray`,
   `npt.NDArray[...]`, `pd.Series`, `pd.DataFrame`, `pl.Series`,
   `pl.DataFrame`; a union gives one detection per member and the
   first is sampled;
3. the annotation's source text, when the hints do not resolve;
4. for code that cannot be annotated, a claims-file entry's
   `runtime_types: {param: pandas.Series}`.

A parameter no adapter claims is sampled as a list, exactly as before.
Adapters beyond the built-ins register under the entry-point group
`mathema.runtime_types`; a built-in wins a name clash, and an adapter
that fails to load is skipped with a warning.
"""
from __future__ import annotations

from .._signatures import module_scope
import ast
import functools
import importlib.util
import inspect
import typing
import warnings
from dataclasses import dataclass
from importlib.metadata import entry_points

from ._abstract import (AbstractMat, AbstractTable, AbstractVec, NotMine,
                        abstract_of, plain)
from ._adapters import (BUILTIN_ADAPTERS, KINDS, Detection, ListAdapter,
                        RuntimeTypeAdapter)
from ._missing import (Definition, absence_defined, definitions, members,
                       resolve_absence, resolve_missing, set_definitions,
                       spellings)

#: the parameter kinds (`analysis.Facts.param_kinds`) sampled as a
#: sequence: a plain sequence, and a vector or matrix whose runtime type
#: the signature names
SEQUENCE_KINDS = frozenset({"sequence", "vec", "mat"})

#: the entry-point group third-party runtime type adapters register under
RUNTIME_TYPES_GROUP = "mathema.runtime_types"


@dataclass(frozen=True)
class RuntimeType:
    """The marker `Vec(..., runtime=...)` and `Mat(..., runtime=...)`
    attach: the parameter's runtime type, by its dotted name
    (`"pandas.Series"`)."""
    name: str


@functools.lru_cache(maxsize=1)
def _discovered() -> tuple:
    found = []
    for ep in entry_points(group=RUNTIME_TYPES_GROUP):
        try:
            obj = ep.load()
            found.append(obj() if isinstance(obj, type) else obj)
        except Exception as e:
            warnings.warn(f"mathema: runtime type adapter {ep.value!r} "
                          f"registered under {ep.name!r} failed to load "
                          f"({e!r}), skipping it", stacklevel=2)
    return tuple(found)


def adapters() -> dict:
    """Every runtime type adapter by name, in detection order: the
    built-ins (the list adapter last), then any registered under
    `mathema.runtime_types` whose name no built-in uses, placed before
    the list adapter."""
    builtin = {a.name: a for a in BUILTIN_ADAPTERS}
    external: dict = {}
    for a in _discovered():
        name = getattr(a, "name", None)
        if not isinstance(name, str) or not isinstance(a, RuntimeTypeAdapter):
            warnings.warn(f"mathema: runtime type adapter {a!r} does not "
                          f"provide name, kinds, requires, detect, "
                          f"realise and observe, skipping it",
                          stacklevel=2)
            continue
        if name in builtin:
            warnings.warn(f"mathema: external runtime type adapter "
                          f"{name!r} ignored because a built-in adapter "
                          f"already uses that name", stacklevel=2)
            continue
        external.setdefault(name, a)
    ordered = {n: a for n, a in builtin.items() if n != ListAdapter.name}
    ordered.update(external)
    ordered[ListAdapter.name] = builtin[ListAdapter.name]
    return ordered


def adapter(name: str):
    """The adapter registered under `name`, or None."""
    return adapters().get(name)


def installed(found) -> bool:
    """Whether every module an adapter requires is importable."""
    return all(importlib.util.find_spec(m) is not None
               for m in getattr(found, "requires", ()))


def library_version(found) -> "str | None":
    """`"<library>==<version>"` for the first module an adapter
    requires, as installed, or None for an adapter that requires none
    (the list adapter)."""
    from importlib.metadata import PackageNotFoundError, version
    for module in getattr(found, "requires", ()):
        try:
            return f"{module}=={version(module)}"
        except PackageNotFoundError:
            return None
    return None


def _signature(fn) -> "inspect.Signature | None":
    """`fn`'s signature (a numpy ufunc's documented one where
    `inspect.signature` cannot read it), or None when it has none."""
    from .._signatures import callable_signature
    try:
        return callable_signature(fn)
    except (TypeError, ValueError):
        return None


# --- detection -------------------------------------------------------

#: module aliases an annotation's source text is read through when the
#: function's own globals do not bind the name
_KNOWN_ALIASES = {"np": "numpy", "npt": "numpy.typing", "pd": "pandas",
                  "pl": "polars"}


def _canonical_text(text: str, scope: dict) -> str:
    """An annotation's source text with its leading module alias
    replaced by the module's real name (`pd.Series` to
    `pandas.Series`), read from `scope` (the function's globals) and
    else the usual aliases."""
    text = text.strip()
    head, dot, rest = text.partition(".")
    if not dot:
        bound = scope.get(head)
        if isinstance(bound, type) and bound.__module__.split(".")[0] in (
                "numpy", "pandas", "polars"):
            return f"{bound.__module__.split('.')[0]}.{bound.__qualname__}"\
                + text[len(head):]
        return text
    bound = scope.get(head)
    module = getattr(bound, "__name__", None) if inspect.ismodule(bound) \
        else _KNOWN_ALIASES.get(head)
    return f"{module}.{rest}" if module else text


def _split_union_text(text: str) -> list:
    """The members of a union written as text: `A | B`, `Union[A, B]`,
    `Optional[A]`; any other text is its own single member."""
    text = text.strip()
    for head in ("Union[", "typing.Union[", "Optional[", "typing.Optional["):
        if text.startswith(head) and text.endswith("]"):
            return _split_top(text[len(head):-1], ",")
    parts = _split_top(text, "|")
    return parts if len(parts) > 1 else [text]


def _split_top(text: str, sep: str) -> list:
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if ch == sep and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _union_members(annotation) -> list:
    origin = typing.get_origin(annotation)
    import types as _types
    if origin is typing.Union or origin is getattr(_types, "UnionType",
                                                   None):
        return [a for a in typing.get_args(annotation) if a is not type(None)]
    return [annotation]


def _strip_annotated(annotation):
    if typing.get_origin(annotation) is typing.Annotated:
        return typing.get_args(annotation)[0]
    return annotation


def _marker_of(annotation) -> "RuntimeType | None":
    for m in getattr(annotation, "__metadata__", ()) or ():
        if isinstance(m, RuntimeType):
            return m
        nested = _marker_of(m) if getattr(m, "__metadata__", None) else None
        if nested is not None:
            return nested
    return None


def _marker_kind(annotation, found) -> str:
    """The kind a marker states: `mat` for a two-axis `Shape`, a
    table adapter's own kind, else `vec`."""
    from ..types import _shape_dims
    kinds = getattr(found, "kinds", KINDS)
    if kinds == frozenset({"table"}):
        return "table"
    dims = _shape_dims(annotation)
    return "mat" if dims is not None and len(dims) >= 2 else "vec"


def detect_annotation(annotation, scope: "dict | None" = None) -> list:
    """Intent:
        The detections one annotation gives, one per union member, in
        the order the members are written: each member goes to the
        installed adapters in detection order and the first to claim
        it answers. A live annotation is read as a type, a string as
        source text (its module alias resolved through `scope`).
    """
    scope = scope or {}
    if isinstance(annotation, str):
        members = [_canonical_text(m, scope)
                   for m in _split_union_text(annotation)]
    else:
        members = _union_members(_strip_annotated(annotation))
    out = []
    for member in members:
        for found in adapters().values():
            if not installed(found):
                continue
            try:
                hit = found.detect(member)
            except Exception:
                hit = None
            if hit is not None:
                out.append(hit)
                break
    return out


def detect_parameters(fn, declared: "dict | None" = None) -> dict:
    """Intent:
        Each parameter's runtime type detections, from the signature
        only, as `{param: (Detection, ...)}`: a `RuntimeType` marker
        first, then the live annotation, then the annotation's source
        text when the hints do not resolve, and for a parameter the
        signature says nothing about, `declared` (a claims-file entry's
        `runtime_types: {param: name}`). A parameter nothing names is
        absent.
    """
    sig = _signature(fn)
    if sig is None:
        return {}
    scope = module_scope(fn)
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception:
        hints = {}
    out: dict = {}
    for p, param in sig.parameters.items():
        found: list = []
        live = hints.get(p)
        raw = param.annotation
        if live is None and isinstance(raw, str):
            try:
                live = eval(raw, dict(scope))   # noqa: S307
            except Exception:
                live = None
        if live is None and raw is not inspect.Parameter.empty \
                and not isinstance(raw, str):
            live = raw
        marker = _marker_of(live) if live is not None else None
        if marker is not None:
            named = adapter(marker.name)
            if named is not None and installed(named):
                found = [Detection(named.name, _marker_kind(live, named),
                                   f"marker: {named.name}")]
        elif live is not None:
            found = detect_annotation(live, scope)
        elif isinstance(raw, str):
            found = detect_annotation(raw, scope)
        if not found and (declared or {}).get(p):
            named = adapter(str(declared[p]))
            if named is not None and installed(named):
                kind = "table" if named.kinds == frozenset({"table"}) \
                    else "vec"
                found = [Detection(named.name, kind,
                                   f"claims file: {named.name}")]
        if found:
            out[p] = tuple(found)
    return out


def realised_parameters(facts) -> dict:
    """The parameters whose first detection names a runtime type other
    than a list, `{param: Detection}`: the ones whose drawn values are
    realised before each call."""
    return {p: ds[0] for p, ds in
            (getattr(facts, "runtime_types", None) or {}).items()
            if ds and ds[0].adapter != ListAdapter.name}


def identity_entries(facts) -> dict:
    """Intent:
        What a record's identity states about runtime types: for each
        parameter realised as something other than a list, the runtime
        type, the evidence it was read from and the library version,
        `{param: {"type", "evidence", "library"}}`. Empty for a
        function whose sequences are all lists.
    """
    out = {}
    for p, d in realised_parameters(facts).items():
        entry = {"type": d.adapter, "evidence": d.evidence}
        version = library_version(adapter(d.adapter))
        if version:
            entry["library"] = version
        out[p] = entry
    return out


def descriptor_names(facts) -> list:
    """The runtime types a computation descriptor names after its
    number representation, distinct, in parameter order: `["pandas.Series"]`
    for a Series parameter, empty when every sequence is a list."""
    seen: list = []
    for d in realised_parameters(facts).values():
        if d.adapter not in seen:
            seen.append(d.adapter)
    return seen


# --- realise and observe ---------------------------------------------

def realise(value, detection: Detection, options: "dict | None" = None):
    """Intent:
        `value` (a drawn plain value) as the object the detection's
        runtime type carries, or `value` unchanged when it is not a
        vector, matrix or table the adapter carries (a scalar, a value
        already of the runtime type).
    """
    found = adapter(detection.adapter)
    if found is None:
        return value
    abstract = abstract_of(value)
    if abstract is None:
        return value
    kind = ("mat" if isinstance(abstract, AbstractMat) else
            "table" if isinstance(abstract, AbstractTable) else "vec")
    if kind not in found.kinds:
        return value
    return found.realise(abstract, dict(options or {}))


def observe(obj):
    """Intent:
        What a function returned, as an abstract value or a plain
        number: the first installed adapter whose `observe` recognises
        it answers, the list adapter last. An object no adapter
        recognises is returned unchanged.
    """
    for found in adapters().values():
        if found.name == ListAdapter.name or not installed(found):
            continue
        if _root_module_of(obj) not in (*found.requires, "builtins") \
                and found.requires:
            continue
        try:
            seen = found.observe(obj)
        except Exception:
            continue
        if seen is not NotMine:
            return seen
    return obj


def _root_module_of(obj) -> str:
    return (type(obj).__module__ or "").split(".", 1)[0]


def observed_plain(obj):
    """`observe(obj)` as the plain value comparisons read: a list for a
    vector (NaN at each missing position), a list of rows for a matrix,
    a dict of column lists for a table, a Python number for a numpy
    scalar."""
    return plain(observe(obj))


class _Realising:
    """A callable standing in for a function whose parameters have
    runtime types: each call realises those parameters' drawn values
    through their adapters, calls the function, and observes the
    result as a plain value. Every attribute it does not define is the
    function's own (`__globals__`, `__code__`, `__defaults__`), and
    `__wrapped__` is the function, so signature and source readers see
    the function itself."""

    def __init__(self, fn, bindings: dict, sig):
        functools.update_wrapper(self, fn)
        self._fn, self._bindings, self._sig = fn, bindings, sig

    def __getattr__(self, name):
        return getattr(self.__dict__["_fn"], name)

    def __call__(self, *args, **kwargs):
        fn = self._fn
        try:
            bound = self._sig.bind(*args, **kwargs)
        except TypeError:
            return fn(*args, **kwargs)
        for name, detection in self._bindings.items():
            if name in bound.arguments:
                bound.arguments[name] = realise(bound.arguments[name],
                                                detection)
        return observed_plain(fn(*bound.args, **bound.kwargs))

    def __repr__(self) -> str:
        return f"<realising {self._fn!r}>"


def calling(fn, facts):
    """Intent:
        `fn` itself when no parameter has a runtime type other than a
        list; otherwise a callable with `fn`'s signature that realises
        each such parameter's drawn value through its adapter before
        calling `fn`, and observes the result into a plain value.

    Notes:
        A call the signature does not bind is passed to `fn` unchanged,
        so `fn` raises its own TypeError. A callable already realising
        is returned as it is.
    """
    if isinstance(fn, _Realising):
        return fn
    bindings = realised_parameters(facts)
    if not bindings:
        return fn
    sig = _signature(fn)
    if sig is None:
        return fn
    return _Realising(fn, bindings, sig)


# --- the hint for an undeclared vector parameter ------------------------

#: methods a list does not have and a vector runtime type does
_VECTOR_METHODS = frozenset({
    "mean", "std", "var", "sum", "prod", "min", "max", "median", "cumsum",
    "cumprod", "cummax", "cummin", "pct_change", "dropna", "fillna",
    "rolling", "expanding", "ewm", "shift", "diff", "quantile", "skew",
    "kurt", "kurtosis", "abs", "clip", "round", "to_numpy", "tolist",
    "argmax", "argmin", "idxmax", "idxmin", "any", "all", "dot",
    "nunique", "unique", "value_counts", "rank", "sem", "cov", "corr",
    "isna", "notna", "isnull", "notnull", "astype", "apply", "reshape",
    "flatten", "ravel", "resample"})
#: attributes a list does not have and a vector runtime type does
_VECTOR_ATTRS = frozenset({"iloc", "loc", "values", "index", "shape",
                           "ndim", "size", "dtype"})
#: reductions called as `np.<name>(x)`
_NUMPY_REDUCTIONS = frozenset({
    "mean", "std", "var", "sum", "prod", "min", "max", "median",
    "cumsum", "cumprod", "nanmean", "nanstd", "nanvar", "nansum",
    "nanmin", "nanmax", "average", "ptp", "percentile", "quantile",
    "diff", "sort", "argmax", "argmin", "dot", "linalg"})

#: the runtime type a hint suggests for each usage, most likely first
_SUGGESTIONS = {
    "vector": (("pandas", "Series"), ("polars", "Series"),
               ("numpy", "ndarray")),
    "matrix": (("numpy", "ndarray"), ("pandas", "DataFrame"),
               ("polars", "DataFrame")),
    "table": (("pandas", "DataFrame"), ("polars", "DataFrame")),
}


def module_imports(scope: dict) -> dict:
    """The libraries with a built-in runtime type adapter that a
    function's module imports, `{library: alias}` (`{"pandas": "pd"}`),
    read from the module's globals."""
    out: dict = {}
    for name, value in (scope or {}).items():
        if inspect.ismodule(value):
            root = value.__name__.split(".")[0]
            if root in ("numpy", "pandas", "polars") \
                    and value.__name__ == root:
                out.setdefault(root, name)
    return out


def _usages(fdef, params: list, numpy_aliases: set) -> dict:
    """Intent:
        How the body uses each parameter as a vector, a matrix or a
        table, `{param: (usage, strong)}`: `strong` when the use is one
        a list does not support (a vector method such as `.mean()`, an
        array attribute, `.T`, `@`), otherwise a use a list survives
        (`np.mean(x)`, `x[i]`, `x["col"]`).
    """
    found: dict = {}

    def note(p, usage, strong):
        if p not in params:
            return
        old = found.get(p)
        rank = {"matrix": 2, "table": 1, "vector": 0}
        if old is None or (strong, rank[usage]) > (old[1], rank[old[0]]):
            found[p] = (usage, strong)

    for node in ast.walk(fdef):
        if isinstance(node, ast.Attribute) and isinstance(node.value,
                                                          ast.Name):
            p = node.value.id
            if node.attr == "T":
                note(p, "matrix", True)
            elif node.attr in _VECTOR_METHODS or node.attr in _VECTOR_ATTRS:
                note(p, "vector", True)
        elif isinstance(node, ast.BinOp) and isinstance(node.op,
                                                        ast.MatMult):
            for side in (node.left, node.right):
                if isinstance(side, ast.Name):
                    note(side.id, "matrix", True)
        elif isinstance(node, ast.Call) and isinstance(node.func,
                                                       ast.Attribute):
            root = node.func.value
            if isinstance(root, ast.Name) and root.id in numpy_aliases \
                    and node.func.attr in _NUMPY_REDUCTIONS:
                for a in node.args:
                    if isinstance(a, ast.Name):
                        note(a.id, "vector", False)
        elif isinstance(node, ast.Subscript) and isinstance(node.value,
                                                            ast.Name):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                note(node.value.id, "table", False)
            else:
                note(node.value.id, "vector", False)
    return found


def usage_hints(fn, fdef, params: list, param_kinds: dict,
                detected: dict) -> dict:
    """Intent:
        For each parameter the body uses as a vector, matrix or table
        while the signature names no runtime type for it, in a module
        importing a library with a runtime type adapter, the hint that
        names the likely runtime type: `{param: {"usage", "strong",
        "type", "text"}}`. Empty when the module imports none of
        numpy, pandas or polars.
    """
    scope = module_scope(fn)
    imported = module_imports(scope)
    if not imported or fdef is None:
        return {}
    numpy_aliases = {alias for lib, alias in imported.items()
                     if lib == "numpy"} | {
        n for n, v in scope.items()
        if inspect.ismodule(v) and v.__name__ == "numpy"}
    out: dict = {}
    for p, (usage, strong) in _usages(fdef, params, numpy_aliases).items():
        if p in detected or param_kinds.get(p) in ("int", "bool", "string",
                                                    "complex"):
            continue
        choice = next(((lib, cls) for lib, cls in _SUGGESTIONS[usage]
                       if lib in imported), None)
        if choice is None:
            continue
        lib, cls = choice
        spelled = f"{imported[lib]}.{cls}"
        out[p] = {"usage": usage, "strong": strong,
                  "type": f"{lib}.{cls}",
                  "text": f"{p} is used as a {usage}; this module imports "
                          f"{lib}: annotate `{p}: {spelled}` to sample it "
                          f"as one"}
    return out


def strong_hints(facts) -> list:
    """The hint texts a record's notes carry, one per parameter whose
    body use a list does not support."""
    return [h["text"] for h in (getattr(facts, "runtime_hints", None)
                                or {}).values() if h.get("strong")]


__all__ = [
    "AbstractMat", "AbstractTable", "AbstractVec", "Definition", "Detection",
    "ListAdapter", "NotMine", "absence_defined", "definitions", "members",
    "resolve_absence", "resolve_missing", "set_definitions", "spellings",
    "RUNTIME_TYPES_GROUP", "RuntimeType", "SEQUENCE_KINDS", "RuntimeTypeAdapter",
    "abstract_of", "adapter", "adapters", "calling", "descriptor_names",
    "detect_annotation", "detect_parameters", "identity_entries",
    "installed", "library_version", "module_imports", "observe",
    "observed_plain", "plain", "realise", "realised_parameters",
    "strong_hints", "usage_hints",
]
