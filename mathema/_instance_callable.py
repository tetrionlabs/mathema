# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The function an object with `__call__` stands for, when its call is
read and shown to hand over unchanged.

A decorator written as a class (`Logged(fn)`, an instance holding the
function it wraps) has no function source of its own. Its mathematics is
the wrapped function's only when calling the instance is the same as
calling the wrapped function.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any, Callable

_MAX_DEPTH = 8


def read_through(fn: Any) -> "tuple[Any, str | None]":
    """Intent:
        `(target, refusal)` for `fn`, an object with `__call__`.

        `(fn, None)` when `fn` is a function, method, class or builtin,
        when it already links its wrapped function as `__wrapped__`, or
        when its `__call__` is its own body (it holds no callable that
        `__call__` uses): nothing is read through.

        `(inner, None)` when `fn.__call__` is, after its docstring, the
        single statement `return self.<attr>(<its own parameters>)`: it
        passes every parameter on in order and by name, has no defaults of
        its own, and returns what comes back as it is, and `<attr>` is an
        attribute of the instance holding a callable. `inner` is that
        callable, read through again in turn (a stack of such decorators).

        `(None, reason)` when `fn.__call__` uses a callable the instance
        holds in any other way (it changes an argument or the result,
        adds a default, calls it conditionally, calls anything else):
        what the call computes is not what the held function computes,
        so nothing is adjudicated.

    Notes:
        Only `fn.__call__`'s own source is read. An instance whose
        `__call__` source cannot be retrieved is returned as it is.
    """
    for _ in range(_MAX_DEPTH):
        if not _is_plain_instance(fn):
            return fn, None
        held = _held_callables(fn)
        parsed = _parse_call(type(fn).__call__)
        if parsed is None or not held:
            return fn, None
        fdef, self_name = parsed
        attr = _hands_over_unchanged(fdef, self_name, held)
        if attr is not None:
            fn = held[attr]
            continue
        used = sorted(a for a in held if _uses_attribute(fdef, self_name, a))
        if not used:
            return fn, None
        return None, (
            f"{type(fn).__name__} wraps a function ({', '.join(used)}), "
            "but its __call__ is not read through: it does not hand its "
            "arguments to the wrapped function and return the result "
            "unchanged, so what the wrapped function computes is not what "
            "a call computes, and nothing was adjudicated")
    return fn, None


def _is_plain_instance(fn: Any) -> bool:
    if (inspect.isroutine(fn) or inspect.isclass(fn)
            or getattr(fn, "__wrapped__", None) is not None):
        return False
    if any(k.startswith("__mathema") for k in getattr(fn, "__dict__", {})):
        return False
    return inspect.isfunction(getattr(type(fn), "__call__", None))


_MISSING = object()


def hands_over_to_wrapped(fn: Any) -> bool:  # :draft
    """Intent:
        Whether `fn`, an instance that links a function as
        `__wrapped__` (as `functools.update_wrapper` does), has a
        `__call__` whose source is `return self.<attr>(<its own
        parameters>)` with `<attr>` holding that same function: the call
        hands every argument to it and returns what comes back as it is.
        `self.<attr>` is read as the instance's own attribute only when
        the class keeps the default attribute lookup and defines nothing
        of that name (a property or other descriptor would decide it).
    """
    if inspect.isroutine(fn) or inspect.isclass(fn) \
            or not inspect.isfunction(getattr(type(fn), "__call__", None)):
        return False
    held = _held_callables(fn)
    parsed = _parse_call(type(fn).__call__)
    if parsed is None or not held:
        return False
    attr = _hands_over_unchanged(parsed[0], parsed[1], held)
    if attr is None or type(fn).__getattribute__ is not object.__getattribute__ \
            or inspect.getattr_static(type(fn), attr, _MISSING) is not _MISSING:
        return False
    return held[attr] is getattr(fn, "__wrapped__", None)


def _held_callables(fn: Any) -> "dict[str, Callable[..., Any]]":
    return {k: v for k, v in getattr(fn, "__dict__", {}).items()
            if callable(v)}


def _parse_call(call: Any) -> "tuple[ast.FunctionDef, str] | None":
    try:
        src = textwrap.dedent(inspect.getsource(call))
        fdef = next(n for n in ast.parse(src).body
                    if isinstance(n, ast.FunctionDef))
    except (OSError, TypeError, SyntaxError, StopIteration):
        return None
    positional = [*fdef.args.posonlyargs, *fdef.args.args]
    if not positional:
        return None
    return fdef, positional[0].arg


def _hands_over_unchanged(fdef: ast.FunctionDef, self_name: str,
                          held: "dict[str, Any]") -> "str | None":
    args = fdef.args
    if args.defaults or any(d is not None for d in args.kw_defaults):
        return None
    body = list(fdef.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return None
    call = body[0].value
    if not (isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == self_name
            and call.func.attr in held):
        return None
    own = [*args.posonlyargs, *args.args][1:]
    expect_args = [ast.dump(ast.Name(a.arg, ast.Load())) for a in own]
    if args.vararg:
        expect_args.append(ast.dump(
            ast.Starred(ast.Name(args.vararg.arg, ast.Load()), ast.Load())))
    expect_kw = [(a.arg, ast.dump(ast.Name(a.arg, ast.Load())))
                 for a in args.kwonlyargs]
    if args.kwarg:
        expect_kw.append((None, ast.dump(
            ast.Name(args.kwarg.arg, ast.Load()))))
    if [ast.dump(a) for a in call.args] != expect_args:
        return None
    if [(k.arg, ast.dump(k.value)) for k in call.keywords] != expect_kw:
        return None
    return call.func.attr


def _uses_attribute(fdef: ast.FunctionDef, self_name: str, attr: str) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr == attr
               and isinstance(n.value, ast.Name) and n.value.id == self_name
               for n in ast.walk(fdef))
