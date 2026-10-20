# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Reads that can raise: subscripts and attribute reads in a body.

`d["a"]` raises KeyError where the mapping lacks the key, `xs[0]`
raises IndexError where the sequence or string is shorter, and
`p.rate` raises AttributeError where the object lacks the attribute.
None of these is a raise statement or a partial math call, so the
raise-region walk states no region for them; this module says which
reads can raise on some input, so the definedness walk can report them
as a region it does not know.

A read cannot raise where the parameter's declared type guarantees it:
a dataclass or NamedTuple field, a required TypedDict key, an index
inside a fixed-length tuple annotation, an attribute a class body
defines or `__init__` assigns before anything else can happen, a slice
of a list, tuple or string. A read off a module, a class or a
module-level container is read against the object as it is now.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import types
import typing

_MISSING = object()


def _init_assigned(cls) -> frozenset:
    """Intent:
        The attribute names `cls.__init__` assigns as `self.<name> =
        ...` in statements at the top level of its body, before any
        statement that could leave it early (a return, a raise, a
        branch, a loop, a try).
    """
    init = cls.__dict__.get("__init__")
    if init is None:
        return frozenset()
    try:
        from ..analysis import get_tree
        _src, tree = get_tree(init)
    except Exception:
        return frozenset()
    if not isinstance(tree, (ast.FunctionDef, ast.AsyncFunctionDef)) \
            or not tree.args.args:
        return frozenset()
    me = tree.args.args[0].arg
    names: set = set()
    for stmt in tree.body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) \
                else [stmt.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                        and t.value.id == me:
                    names.add(t.attr)
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        break
    return frozenset(names)


def _hints(cls) -> dict:
    try:
        return typing.get_type_hints(cls)
    except Exception:
        return dict(getattr(cls, "__annotations__", {}) or {})


def _is_named_tuple(cls) -> bool:
    return inspect.isclass(cls) and issubclass(cls, tuple) \
        and hasattr(cls, "_fields")


def _is_typed_dict(cls) -> bool:
    return inspect.isclass(cls) and issubclass(cls, dict) \
        and hasattr(cls, "__required_keys__")


def attribute_type(owner, attr: str):
    """Intent:
        `(present, type)` for reading `attr` off a value of type
        `owner`: whether every value of that type has the attribute,
        and the attribute's declared type where one is known (None
        otherwise).
    """
    if owner is None or not inspect.isclass(owner):
        return False, None
    if dataclasses.is_dataclass(owner):
        for f in dataclasses.fields(owner):
            if f.name == attr:
                set_by_init = f.init or f.default is not dataclasses.MISSING \
                    or f.default_factory is not dataclasses.MISSING
                return set_by_init, _hints(owner).get(attr)
    if _is_named_tuple(owner) and attr in owner._fields:
        return True, _hints(owner).get(attr)
    found = inspect.getattr_static(owner, attr, _MISSING)
    if found is not _MISSING:
        if isinstance(found, (property, types.MemberDescriptorType)):
            return False, None
        if isinstance(found, types.GetSetDescriptorType) \
                and owner.__module__ != "builtins":
            return False, None
        return True, None
    if attr in _init_assigned(owner):
        return True, _hints(owner).get(attr)
    return False, None


def _constant_index(node: ast.AST):
    if isinstance(node, ast.Constant) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
            and isinstance(node.operand, ast.Constant) \
            and isinstance(node.operand.value, int) \
            and not isinstance(node.operand.value, bool):
        return -node.operand.value
    return _MISSING


def _index_inside(index, length: int) -> bool:
    return isinstance(index, int) and -length <= index < length


def subscript_type(owner, slice_node: ast.AST):
    """Intent:
        `(present, type)` for subscripting a value of type `owner`
        with `slice_node`: whether the subscript succeeds on every
        value of that type, and the element's declared type where one
        is known.
    """
    if owner is None:
        return False, None
    origin = typing.get_origin(owner) or owner
    if isinstance(slice_node, ast.Slice):
        sliceable = (list, tuple, str, bytes)
        return (inspect.isclass(origin) and issubclass(origin, sliceable)
                and not _is_typed_dict(origin)), owner
    index = _constant_index(slice_node)
    if index is _MISSING:
        return False, None
    if _is_typed_dict(owner):
        if isinstance(index, str) and index in owner.__required_keys__:
            return True, _hints(owner).get(index)
        return False, None
    if _is_named_tuple(owner):
        if _index_inside(index, len(owner._fields)):
            return True, _hints(owner).get(owner._fields[index])
        return False, None
    if origin is tuple:
        args = typing.get_args(owner)
        if args and Ellipsis not in args and _index_inside(index, len(args)):
            return True, args[index]
    return False, None


def _literal_read_succeeds(node: ast.Subscript) -> bool:
    """Whether a constant subscript of a literal display succeeds."""
    index = _constant_index(node.slice)
    if index is _MISSING:
        return False
    base = node.value
    if isinstance(base, (ast.Tuple, ast.List)):
        return not any(isinstance(e, ast.Starred) for e in base.elts) \
            and _index_inside(index, len(base.elts))
    if isinstance(base, ast.Constant) and isinstance(base.value, (str, bytes)):
        return _index_inside(index, len(base.value))
    if isinstance(base, ast.Dict):
        keys = [_constant_index(k) if k is not None else _MISSING
                for k in base.keys]
        return any(k is not _MISSING and k == index for k in keys)
    return False


def _held_read_succeeds(obj, node: ast.AST) -> bool:
    """Whether reading `node` (an attribute or a constant subscript) off
    the object a module-level name holds now succeeds, read without
    running any of the object's own code."""
    if isinstance(node, ast.Attribute):
        found = inspect.getattr_static(obj, node.attr, _MISSING)
        return found is not _MISSING and not isinstance(found, property) \
            and not (isinstance(found, types.MemberDescriptorType)
                     and not inspect.isclass(obj))
    index = _constant_index(node.slice)
    if index is _MISSING:
        return False
    if type(obj) is dict:
        try:
            return index in obj
        except TypeError:
            return False
    if type(obj) in (list, tuple, str, bytes):
        return _index_inside(index, len(obj))
    return False


def read_checker(fn, facts, scope: dict):
    """Intent:
        A function of one subscript or attribute-read node that returns
        how the read can raise on some input (a short description), or
        None where it cannot.

    Notes:
        A name the body assigns is a local whose type is not known, and
        a parameter the body reassigns is one too. A parameter's type
        is its annotation; a method's first parameter with no
        annotation is the enclosing class. A name that is neither is
        looked up in `scope`.
    """
    from ._base import _enclosing_class
    params = list(getattr(facts, "params", ()) or ())
    assigned = {n.id for n in ast.walk(facts.tree)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    for n in ast.walk(facts.tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.Lambda)) and n is not facts.tree:
            assigned |= {a.arg for a in n.args.args}
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        try:
            hints = {name: p.annotation for name, p in
                     inspect.signature(fn).parameters.items()
                     if p.annotation is not inspect.Parameter.empty}
        except (TypeError, ValueError):
            hints = {}
    types_of: dict = {}
    for i, p in enumerate(params):
        if p in assigned:
            continue
        if p in hints:
            types_of[p] = hints[p]
        elif i == 0 and p in ("self", "cls"):
            cls = _enclosing_class(fn)
            if cls is not None:
                types_of[p] = cls if p == "self" else type(cls)

    def static_type(node: ast.AST):
        if isinstance(node, ast.Name):
            return types_of.get(node.id)
        if isinstance(node, ast.Attribute):
            present, kind = attribute_type(static_type(node.value), node.attr)
            return kind if present else None
        if isinstance(node, ast.Subscript):
            present, kind = subscript_type(static_type(node.value), node.slice)
            return kind if present else None
        return None

    def held(node: ast.AST):
        base = node.value
        if isinstance(base, ast.Name) and base.id not in params \
                and base.id not in assigned:
            if base.id in scope:
                return True, scope[base.id]
            import builtins
            if hasattr(builtins, base.id):
                return True, getattr(builtins, base.id)
        return False, None

    def check(node: ast.AST) -> "str | None":
        text = ast.unparse(node)
        if isinstance(node, ast.Attribute):
            is_held, obj = held(node)
            if is_held:
                if _held_read_succeeds(obj, node):
                    return None
            elif attribute_type(static_type(node.value), node.attr)[0]:
                return None
            return (f"a read of {text}, which raises AttributeError where "
                    f"the attribute is absent")
        if isinstance(node, ast.Subscript):
            if _literal_read_succeeds(node):
                return None
            is_held, obj = held(node)
            if is_held:
                if _held_read_succeeds(obj, node):
                    return None
            elif subscript_type(static_type(node.value), node.slice)[0]:
                return None
            return (f"a read of {text}, which raises where the key or "
                    f"index is absent")
        return None

    return check
