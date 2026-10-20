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

from ._abstract import (ELEMENT_TYPES, AbstractMat, AbstractTable,
                        AbstractVec, Labelled, NotMine, abstract_of,
                        element_type, plain)
from ._adapters import (BUILTIN_ADAPTERS, KINDS, BodyUses, Detection,
                        ListAdapter, RuntimeTypeAdapter)
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

def _libraries() -> tuple:
    """Intent:
        The root module of every runtime type adapter other than the
        list adapter, distinct, in detection order: `("pandas",
        "polars", "numpy")` for the built-ins, then each registered
        adapter's.
    """
    seen: list = []
    for found in adapters().values():
        if found.name == ListAdapter.name:
            continue
        root = found.name.split(".", 1)[0]
        if root not in seen:
            seen.append(root)
    return tuple(seen)


def _known_aliases() -> dict:
    """Intent:
        The module aliases an annotation's source text is read through
        when the function's own globals do not bind the name: every
        adapter's `ALIASES` (`np`, `npt`, `pd`, `pl` for the built-ins),
        the first adapter to state an alias keeping it.
    """
    out: dict = {}
    for found in adapters().values():
        for alias, module in (getattr(found, "ALIASES", None) or {}).items():
            out.setdefault(alias, module)
    return out


def _canonical_text(text: str, scope: dict) -> str:
    """An annotation's source text with its leading module alias
    replaced by the module's real name (`pd.Series` to
    `pandas.Series`), read from `scope` (the function's globals) and
    else the aliases the adapters state; a bare class name bound to a
    class of an adapter's library becomes its dotted name."""
    text = text.strip()
    head, dot, rest = text.partition(".")
    if not dot:
        bound = scope.get(head)
        if isinstance(bound, type) and bound.__module__.split(".")[0] in \
                _libraries():
            return f"{bound.__module__.split('.')[0]}.{bound.__qualname__}"\
                + text[len(head):]
        return text
    bound = scope.get(head)
    module = getattr(bound, "__name__", None) if inspect.ismodule(bound) \
        else _known_aliases().get(head)
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


def _owning_class(fn):
    """The class an unbound method is defined on (`pandas.Series` for
    `pandas.Series.corr`), read from its qualified name in its own
    module, or None for a plain function."""
    import sys as _sys
    qual = getattr(fn, "__qualname__", "") or ""
    if "." not in qual or "<locals>" in qual:
        return None
    module = _sys.modules.get(getattr(fn, "__module__", "") or "")
    obj = module
    for part in qual.split(".")[:-1]:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj if isinstance(obj, type) else None


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
    owner = _owning_class(fn)
    for index, (p, param) in enumerate(sig.parameters.items()):
        found: list = []
        live = hints.get(p)
        raw = param.annotation
        if (index == 0 and p == "self" and owner is not None and live is None
                and raw is inspect.Parameter.empty):
            # an unbound method's self is an instance of its own class
            live = owner
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


def _drawable_class(cls) -> bool:
    """Intent:
        Whether mathema has a way to draw an instance of `cls`, or leaves
        the reading of it to the body as before: a class of the standard
        library or of a runtime type adapter's library, a dataclass, an
        Enum, a TypedDict, a NamedTuple, a Protocol, and a subclass of a
        built-in value or container type or of `numbers.Number`.
    """
    import dataclasses
    import enum
    import numbers
    import sys
    root = (getattr(cls, "__module__", "") or "").split(".", 1)[0]
    if root in ("builtins", "__future__", "mathema") \
            or root in sys.stdlib_module_names or root in _libraries():
        return True
    if dataclasses.is_dataclass(cls) or getattr(cls, "_is_protocol", False) \
            or typing.is_typeddict(cls):
        return True
    return issubclass(cls, (enum.Enum, numbers.Number, bool, int, float,
                            complex, str, bytes, list, tuple, dict, set,
                            frozenset))


def _adapts_to_language(cls) -> bool:
    """Whether a `mathema.language_adaptors` adaptor turns `cls` into a
    language, the domain a parameter annotated with it is drawn from."""
    from ..languages import adapt_annotation
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return adapt_annotation(cls) is not None
        except Exception:
            return False


def undrawable_parameters(fn, detected: dict) -> dict:
    """Intent:
        `{param: class name}` for each parameter of `fn` annotated with a
        class mathema has no way to draw (`_drawable_class` false) and
        that no runtime type in `detected` names. An `Optional[...]` or
        `Annotated[...]` is read through to the one class inside; any
        other annotation, a union of several classes among them, names
        no such class.
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
        if p in detected or param.kind in (param.VAR_POSITIONAL,
                                           param.VAR_KEYWORD):
            continue
        live = hints.get(p, param.annotation)
        if live is inspect.Parameter.empty:
            continue
        if isinstance(live, str):
            try:
                live = eval(live, dict(scope))   # noqa: S307
            except Exception:
                continue
        members = _union_members(_strip_annotated(live))
        if len(members) != 1:
            continue
        cls = _strip_annotated(members[0])
        if isinstance(cls, type) and typing.get_origin(cls) is None \
                and not _drawable_class(cls) and not _adapts_to_language(cls):
            out[p] = cls.__name__
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

def realise(value, detection: Detection, options: "dict | None" = None,
            declared: "dict | None" = None):
    """Intent:
        `value` (a drawn plain value) as the object the detection's
        runtime type carries, or `value` unchanged when it is not a
        vector, matrix or table the adapter carries (a scalar, a value
        already of the runtime type). `declared` states the element
        type the claim binds where the values may not show it:
        `{"element": "str"}` for a vector, `{"columns": {"k": "str"}}`
        for a table's columns; a vector or column whose own values
        state no type (holes only, or no rows) takes it.
    """
    found = adapter(detection.adapter)
    if found is None:
        return value
    abstract = abstract_of(value)
    if abstract is None:
        return value
    abstract = _with_declared(abstract, declared or {})
    kind = ("mat" if isinstance(abstract, AbstractMat) else
            "table" if isinstance(abstract, AbstractTable) else "vec")
    if kind not in found.kinds:
        return value
    return found.realise(abstract, dict(options or {}))


def _with_declared(abstract, declared: dict):
    """`abstract` with the element types `declared` states set on each
    vector whose `element` is not stated."""
    from dataclasses import replace

    def typed(vec, element):
        if element is None or not isinstance(vec, AbstractVec) \
                or vec.element is not None:
            return vec
        return replace(vec, element=element)
    if isinstance(abstract, AbstractTable):
        columns = declared.get("columns") or {}
        return AbstractTable({name: typed(col, columns.get(name))
                              for name, col in abstract.columns.items()})
    return typed(abstract, declared.get("element"))


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


# --- tables, read the same whatever their runtime type ---------------

def as_table(obj) -> AbstractTable:
    """Intent:
        `obj` as an `AbstractTable`: itself when it is one, a dict of
        columns read as drawn values, any other object as the
        installed adapter that recognises it observes it (a pandas or
        polars DataFrame, or a table a registered adapter carries).

    Raises:
        TypeError: `obj` is no table.
    """
    if isinstance(obj, AbstractTable):
        return obj
    found = abstract_of(obj) if isinstance(obj, dict) else observe(obj)
    if not isinstance(found, AbstractTable):
        raise TypeError(f"{type(obj).__name__} is not a table")
    return found


def column_names(table) -> tuple:
    """The column names of a table (`as_table`), in order."""
    return as_table(table).column_names()


def column_types(table) -> dict:
    """`{name: type}` for each column of a table (`as_table`), the
    type one of `ELEMENT_TYPES`."""
    return as_table(table).column_types()


def column(table, name: str) -> AbstractVec:
    """Intent:
        The column `name` of a table (`as_table`), as an `AbstractVec`.

    Raises:
        KeyError: the table has no such column; the message names the
            columns it has.
    """
    return as_table(table).column(name)


def row_count(table) -> int:
    """The number of rows of a table (`as_table`)."""
    return as_table(table).row_count()


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
    the function itself. A parameter annotated as a set, a frozenset or
    a tuple is passed as one (`as_annotated`); a function whose only
    such parameters are those has its result returned as it is."""

    def __init__(self, fn, bindings: dict, sig, enums: "dict | None" = None,
                 containers: "dict | None" = None,
                 declared: "dict | None" = None):
        functools.update_wrapper(self, fn)
        self._fn, self._bindings, self._sig = fn, bindings, sig
        self._enums = enums or {}
        self._containers = containers or {}
        self._declared = declared or {}

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
                                                detection,
                                                declared=self._declared.get(name))
        for name, cls in self._enums.items():
            if name in bound.arguments:
                bound.arguments[name] = as_enum_member(bound.arguments[name], cls)
        for name, container in self._containers.items():
            if name in bound.arguments:
                bound.arguments[name] = as_annotated(bound.arguments[name],
                                                     container)
        if not self._bindings and not self._enums:
            return fn(*bound.args, **bound.kwargs)
        return observed_plain(fn(*bound.args, **bound.kwargs))

    def __repr__(self) -> str:
        return f"<realising {self._fn!r}>"


#: the Python container a sequence annotation names, by the last dotted
#: part of its constructor, lowercased; any other sequence is a list
_ANNOTATED_CONTAINERS = {"set": set, "mutableset": set, "abstractset": set,
                         "frozenset": frozenset, "tuple": tuple}


def annotated_container(fn, param: str) -> "type | None":
    """Intent:
        The container type `param`'s annotation names when it is a set,
        a frozenset or a tuple (`set`, `typing.Set[float]`,
        `Optional[frozenset]`), so a sequence drawn as a list is passed
        as a member of that type; None for any other annotation or none.
    """
    from .._signatures import callable_signature
    from ..probing import _annotation_text
    try:
        spec = callable_signature(fn).parameters.get(param)
    except (TypeError, ValueError):
        return None
    if spec is None:
        return None
    text = _annotation_text(spec).replace(" ", "").lower()
    for wrapper in ("optional[", "typing.optional["):
        if text.startswith(wrapper) and text.endswith("]"):
            text = text[len(wrapper):-1]
    parts = [t for t in text.split("|") if t not in ("none", "nonetype")]
    if len(parts) != 1:
        return None
    head = parts[0].split("[", 1)[0].rsplit(".", 1)[-1]
    return _ANNOTATED_CONTAINERS.get(head)


def annotated_containers(fn, facts) -> dict:
    """`{param: container}` for each sequence parameter of `fn` whose
    annotation names a set, a frozenset or a tuple
    (`annotated_container`)."""
    kinds = getattr(facts, "param_kinds", None) or {}
    return {p: made for p, k in kinds.items()
            if k in SEQUENCE_KINDS
            and (made := annotated_container(fn, p)) is not None}


def as_annotated(value, container: "type | None"):
    """Intent:
        `value`, a drawn list or tuple, as a member of `container` (a
        set, a frozenset or a tuple, from `annotated_container`), so
        the function is called inside its parameter's type; `value`
        unchanged when `container` is None, when it is no list or tuple
        (an absence, a value already of the type), or when its elements
        cannot be held in a set.
    """
    if container is None or not isinstance(value, (list, tuple)) \
            or type(value) is container:
        return value
    try:
        return container(value)
    except TypeError:
        return value


def calling(fn, facts, declared: "dict | None" = None):
    """Intent:
        A callable with `fn`'s signature and attributes that calls
        `fn`, with a `SystemExit` it raises arriving as the raise
        `_exits.ExitRaised`. When a parameter has a runtime type other
        than a list, the call first realises each such parameter's
        drawn value through its adapter, and observes the result into
        a plain value. A parameter annotated as a set, a frozenset or a
        tuple is passed as one. `declared`, `{param: declared}` as
        `realise` reads it, states the element types the claim binds
        for a vector or a table's columns.

    Notes:
        A call the signature does not bind is passed to `fn` unchanged,
        so `fn` raises its own TypeError. A callable this already
        returned is returned as it is.
    """
    from .._exits import _ExitsAsRaise, exiting_as_raise
    if isinstance(fn, (_Realising, _ExitsAsRaise)):
        return exiting_as_raise(fn)
    bindings = realised_parameters(facts)
    enums = enum_parameters(fn)
    containers = annotated_containers(fn, facts)
    if not bindings and not enums and not containers:
        return exiting_as_raise(fn)
    sig = _signature(fn)
    if sig is None:
        return exiting_as_raise(fn)
    return exiting_as_raise(_Realising(fn, bindings, sig, enums, containers,
                                       declared))


def enum_parameters(fn) -> dict:
    """Intent:
        `{param: EnumClass}` for every parameter annotated with an
        `Enum` subclass (`Optional[Side]` included): the drawn value of
        such a parameter is one of the Enum's values, and the call
        passes the member it names.
    """
    import enum
    try:
        hints = typing.get_type_hints(inspect.unwrap(fn))
    except Exception:
        return {}
    out: dict = {}
    for name, hint in hints.items():
        if name == "return":
            continue
        args = [a for a in typing.get_args(hint) if a is not type(None)] or [hint]
        if len(args) == 1 and isinstance(args[0], type) \
                and issubclass(args[0], enum.Enum):
            out[name] = args[0]
    return out


def as_enum_member(value, cls):
    """The member of `cls` whose value is `value`, when there is one; a
    member, `None` or any other value is passed on unchanged."""
    import enum
    if value is None or isinstance(value, enum.Enum):
        return value
    try:
        return cls(value)
    except (ValueError, TypeError):
        return value


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

def _suggestions(usage: str) -> list:
    """Intent:
        The runtime types a hint can suggest for one usage, most likely
        first, as `(library, rest of the name)` pairs read from the
        adapters in detection order: a vector use names an adapter
        carrying `vec`, a table use one carrying `table`, and a matrix
        use one carrying `mat` and then one carrying `table`. For the
        built-ins, a vector is a pandas Series, a polars Series or a
        numpy ndarray; a matrix a numpy ndarray, a pandas DataFrame or a
        polars DataFrame; a table a pandas or polars DataFrame.
    """
    wanted = {"vector": ("vec",), "table": ("table",),
              "matrix": ("mat", "table")}[usage]
    out: list = []
    for kind in wanted:
        for found in adapters().values():
            if found.name == ListAdapter.name or kind not in found.kinds:
                continue
            lib, _dot, rest = found.name.partition(".")
            if rest and (lib, rest) not in out:
                out.append((lib, rest))
    return out


def module_imports(scope: dict) -> dict:
    """The libraries with a runtime type adapter that a function's
    module imports, `{library: alias}` (`{"pandas": "pd"}`), read from
    the module's globals."""
    libraries = _libraries()
    out: dict = {}
    for name, value in (scope or {}).items():
        if inspect.ismodule(value):
            root = value.__name__.split(".")[0]
            if root in libraries and value.__name__ == root:
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


#: annotations that say nothing about a parameter's type
_UNDECLARING = frozenset({"any", "typing.any", "object"})


def _annotated(fdef) -> set:
    """The parameters of `fdef` whose annotation names a type, so that
    the signature, not the body's use, decides how each is drawn:
    every annotated parameter except one annotated `Any` or `object`."""
    out: set = set()
    for a in [*fdef.args.posonlyargs, *fdef.args.args,
              *fdef.args.kwonlyargs]:
        if a.annotation is None:
            continue
        text = ast.unparse(a.annotation).strip("\"' ").lower()
        if text not in _UNDECLARING:
            out.add(a.arg)
    return out


def usage_hints(fn, fdef, params: list, param_kinds: dict,
                detected: dict) -> dict:
    """Intent:
        For each parameter the body uses as a vector, matrix or table
        while the signature names no type for it, in a module importing
        a library with a runtime type adapter, the hint that names the
        likely runtime type: `{param: {"usage", "strong", "type",
        "text"}}`. A parameter annotated with any type other than `Any`
        or `object` (`dict`, `Mapping[str, int]`, a class of its own)
        has no hint, whatever attributes the body reads off it. Empty
        when the module imports no library with a runtime type adapter
        (numpy, pandas, polars, or one a package registers).
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
    annotated = _annotated(fdef)
    for p, (usage, strong) in _usages(fdef, params, numpy_aliases).items():
        if p in detected or p in annotated \
                or param_kinds.get(p) in ("int", "bool", "string", "complex"):
            continue
        choice = next(((lib, cls) for lib, cls in _suggestions(usage)
                       if lib in imported), None)
        if choice is None:
            continue
        lib, cls = choice
        spelled = f"{imported[lib]}.{cls}"
        out[p] = {"usage": usage, "strong": strong,
                  "type": f"{lib}.{cls}",
                  "text": f"{p} is used as a {usage}; this module imports "
                          f"{lib}: to sample it as one, annotate: "
                          f"{p}: {spelled}"}
    return out


def _body_uses(fdef, params: list) -> dict:
    """Intent:
        Each parameter's uses in the body as `(form, name)` pairs, the
        vocabulary `BodyUses.supports` reads: `("attr", name)` for an
        attribute read off it, `("call", name)` for a method called on
        it, `("keyed", name)` for one called with a string first
        argument, `("@", "")` for an operand of `@`.
    """
    pset = set(params)
    found: dict = {}
    called = {id(n.func) for n in ast.walk(fdef) if isinstance(n, ast.Call)}

    def note(p, use):
        if p in pset and use not in found.setdefault(p, []):
            found[p].append(use)

    for node in ast.walk(fdef):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name):
            first = node.args[0] if node.args else None
            keyed = isinstance(first, ast.Constant) \
                and isinstance(first.value, str)
            note(node.func.value.id,
                 ("keyed" if keyed else "call", node.func.attr))
        elif isinstance(node, ast.Attribute) and isinstance(node.value,
                                                            ast.Name) \
                and id(node) not in called:
            note(node.value.id, ("attr", node.attr))
        elif isinstance(node, ast.BinOp) and isinstance(node.op,
                                                        ast.MatMult):
            for side in (node.left, node.right):
                if isinstance(side, ast.Name):
                    note(side.id, ("@", ""))
    return found


def _typed_use(use: tuple, declared: list) -> bool:
    """Intent:
        Whether a body use says anything about a runtime type: one a
        list does not support (`.T`, `@`, a vector method or attribute)
        or one some adapter's `USES` declares. Any other attribute
        (`x.weight` on an object of the caller's own) is not.
    """
    form, name = use
    if form == "@" or name == "T" or name in _VECTOR_METHODS \
            or name in _VECTOR_ATTRS:
        return True
    return any(uses.supports(use) for uses in declared)


#: the kinds a body usage asks for, in order of preference
_USAGE_KINDS = {"vector": ("vec",), "table": ("table",),
                "matrix": ("mat", "table")}
#: the usage a hint states for a promoted kind
_KIND_USAGE = {"vec": "vector", "mat": "matrix", "table": "table"}


def _library_choice(candidates: list, usage: "str | None"):
    """Intent:
        The one adapter of a library a body's uses select: the only
        candidate, else the only one carrying the first kind the usage
        asks for that any candidate carries; None when the library's
        candidates stay tied.
    """
    if len(candidates) == 1:
        return candidates[0]
    for kind in _USAGE_KINDS.get(usage or "", ()):
        carrying = [a for a in candidates if kind in a.kinds]
        if len(carrying) == 1:
            return carrying[0]
        if carrying:
            return None
    return None


def _promoted_kind(found, usage: "str | None") -> str:
    """Intent:
        The kind a promoted parameter is drawn with: the adapter's only
        kind, else the first kind the body's usage asks for that the
        adapter carries, else `vec`.
    """
    if len(found.kinds) == 1:
        return next(iter(found.kinds))
    for kind in _USAGE_KINDS.get(usage or "", ()):
        if kind in found.kinds:
            return kind
    return "vec"


def promotions(fn, fdef, params: list, param_kinds: dict,
               detected: dict) -> tuple:
    """Intent:
        The parameters the body's uses draw as a runtime type, and the
        ones whose uses leave the type open, `(promoted, ambiguous)`.
        A parameter qualifies as `usage_hints` reads one: no runtime
        type named, no annotation naming a type, not an `int`, `bool`,
        `string` or `complex` kind, in a module importing a library
        with a runtime type adapter. Its typed uses (`_typed_use`) are
        matched against each adapter's `USES` whose library the module
        imports; an adapter matches when it supports every one of them.
        A library whose adapters match selects one (`_library_choice`).
        `promoted` is `{param: Detection}` when exactly one library
        selects an adapter, its evidence `the body uses it as <the
        adapter's described type>`. `ambiguous` is `{param: hint}`
        when two or more do, the hint (`usage_hints`'s keys, plus
        `types`, the runtime types in detection order) naming each.

    Notes:
        A parameter with no typed use, or whose uses no imported
        library's adapter supports in full, is in neither.
    """
    scope = module_scope(fn)
    imported = module_imports(scope)
    if not imported or fdef is None:
        return {}, {}
    declared = [(a, a.USES) for a in adapters().values()
                if isinstance(getattr(a, "USES", None), BodyUses)]
    numpy_aliases = {alias for lib, alias in imported.items()
                     if lib == "numpy"} | {
        n for n, v in scope.items()
        if inspect.ismodule(v) and v.__name__ == "numpy"}
    usages = _usages(fdef, params, numpy_aliases)
    annotated = _annotated(fdef)
    promoted: dict = {}
    ambiguous: dict = {}
    for p, uses in _body_uses(fdef, params).items():
        if p in detected or p in annotated \
                or param_kinds.get(p) in ("int", "bool", "string", "complex"):
            continue
        typed = [u for u in uses if _typed_use(u, [d for _a, d in declared])]
        if not typed:
            continue
        usage = (usages.get(p) or (None,))[0]
        by_library: dict = {}
        for found, body_uses in declared:
            lib = found.name.split(".", 1)[0]
            if lib in imported and all(body_uses.supports(u) for u in typed):
                by_library.setdefault(lib, []).append(found)
        chosen = [c for c in (_library_choice(cands, usage)
                              for cands in by_library.values())
                  if c is not None]
        if len(chosen) == 1:
            found = chosen[0]
            described = found.USES.described or f"a {found.name}"
            promoted[p] = Detection(found.name, _promoted_kind(found, usage),
                                    f"the body uses it as {described}")
        elif len(chosen) > 1:
            libs = [c.name.split(".", 1)[0] for c in chosen]
            spelled = [f"{p}: {imported[lib]}.{c.name.split('.', 1)[1]}"
                       for lib, c in zip(libs, chosen)]
            stated = usage or _KIND_USAGE[_promoted_kind(chosen[0], usage)]
            both = "both" if len(chosen) == 2 else "each"
            ambiguous[p] = {
                "usage": stated, "strong": True,
                "type": chosen[0].name, "types": [c.name for c in chosen],
                "text": f"{p} is used as a {stated}; this module imports "
                        f"{_listed(libs, 'and')}, whose types {both} "
                        f"support that use: to sample it as one, annotate: "
                        f"{_listed(spelled, 'or')}"}
    return promoted, ambiguous


def _listed(items: list, word: str) -> str:
    """`a`, `a and b`, `a, b and c` (with `word` in place of `and`)."""
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} {word} {items[-1]}"


def strong_hints(facts) -> list:
    """The hint texts a record's notes carry, one per parameter whose
    body use a list does not support."""
    return [h["text"] for h in (getattr(facts, "runtime_hints", None)
                                or {}).values() if h.get("strong")]


__all__ = [
    "AbstractMat", "AbstractTable", "AbstractVec", "Definition", "Detection",
    "ELEMENT_TYPES", "Labelled", "as_table", "column", "column_names",
    "column_types", "element_type", "row_count",
    "ListAdapter", "NotMine", "absence_defined", "definitions", "members",
    "resolve_absence", "resolve_missing", "set_definitions", "spellings",
    "RUNTIME_TYPES_GROUP", "RuntimeType", "SEQUENCE_KINDS", "RuntimeTypeAdapter",
    "abstract_of", "adapter", "adapters", "calling", "descriptor_names",
    "detect_annotation", "detect_parameters", "identity_entries",
    "installed", "library_version", "module_imports", "observe",
    "observed_plain", "plain", "promotions", "realise",
    "realised_parameters", "strong_hints", "usage_hints", "BodyUses",
]
