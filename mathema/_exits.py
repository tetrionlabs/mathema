# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `SystemExit` from the function under test, read as the raise it is.

`SystemExit` derives from `BaseException`, not `Exception`, so every
handler that records a raise from the function under test would let it
pass and it would end the caller's process with the function's exit
code. `call` and `exiting_as_raise` turn it into `ExitRaised`, which is
both a `SystemExit` (a `raises(..., SystemExit)` claim matches it, and
it keeps the exit code) and an `Exception` (every handler records it
like any other raise). Any other `BaseException` (`KeyboardInterrupt`,
the wall-clock alarm) passes through unchanged. What the function
writes to `sys.stdout` and `sys.stderr` during a `call` is kept off the
terminal (`_callee_output`).
"""
from __future__ import annotations

import ast
import builtins
import copy
import functools
import inspect
import sys


class ExitRaised(SystemExit, Exception):
    """A `SystemExit` the function under test raised, carrying its exit
    code as `code`. Its class name reads `SystemExit`, so a witness
    names the exception the function raised."""


ExitRaised.__name__ = "SystemExit"
ExitRaised.__qualname__ = "SystemExit"


def as_raise(exc: SystemExit) -> ExitRaised:
    """Intent:
        `exc` as an `ExitRaised` with the same exit code, chained to it
        and carrying its traceback; an `ExitRaised` is returned as it
        is.
    """
    if isinstance(exc, ExitRaised):
        return exc
    out = ExitRaised(exc.code)
    out.__cause__ = exc
    return out.with_traceback(exc.__traceback__)


def call(fn, *args, **kwargs):
    """Intent:
        `fn(*args, **kwargs)`, with a `SystemExit` it raises turned
        into `ExitRaised`, and what it writes to `sys.stdout` and
        `sys.stderr` kept off the terminal
        (`_callee_output.kept_off_terminal`).

    Raises:
        ExitRaised: `fn` raised `SystemExit`.
    """
    from ._callee_output import kept_off_terminal
    try:
        with kept_off_terminal():
            return fn(*args, **kwargs)
    except ExitRaised:
        raise
    except SystemExit as exc:
        raise as_raise(exc) from exc


def exit_code(exc: SystemExit) -> int:
    """Intent:
        The exit status a process ending with `exc` reports: 0 for a
        code of None, the code itself for an int, and 1 for anything
        else (a message string), the way the interpreter reads it.
    """
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int) and not isinstance(code, bool):
        return code
    return 1


def exception_name(exc: BaseException) -> str:
    """Intent:
        The name a record shows for a raise: the exception's class
        name, followed for a `SystemExit` by its exit code
        (`SystemExit (exit code 2)`).
    """
    name = type(exc).__name__
    if isinstance(exc, SystemExit):
        return f"{name} (exit code {exc.code!r})"
    return name


class _ExitsAsRaise:
    """A callable that runs its function through `call`; attributes and
    the signature are the function's own, its `__module__`,
    `__qualname__`, `__name__` and `__doc__` included, so it reads as
    the function wherever a caller compares the two."""

    def __init__(self, fn):
        functools.update_wrapper(self, fn, updated=())

    def __call__(self, *args, **kwargs):
        return call(self.__wrapped__, *args, **kwargs)

    def __getattr__(self, name):
        if name == "__wrapped__":
            raise AttributeError(name)
        return getattr(self.__wrapped__, name)

    def __repr__(self) -> str:
        return repr(self.__wrapped__)


def exiting_as_raise(fn):
    """Intent:
        A callable that behaves as `fn`, except that a `SystemExit` it
        raises arrives as `ExitRaised`; one this already returned is
        passed back unchanged.
    """
    if isinstance(fn, _ExitsAsRaise) or not callable(fn):
        return fn
    return _ExitsAsRaise(fn)


_SYS_EXIT = "sys.exit"


def _import_bindings(fdef) -> dict:
    """Intent:
        The names a top-level statement of `fdef`'s body (one that runs
        before every later top-level statement) binds by importing
        `sys` or `sys.exit`, each mapped to `("sys" | "sys.exit", line
        of the import)`.
    """
    out: dict = {}
    for node in fdef.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sys":
                    out[alias.asname or "sys"] = ("sys", node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "sys" \
                and not node.level:
            for alias in node.names:
                if alias.name == "exit":
                    out[alias.asname or "exit"] = (_SYS_EXIT, node.lineno)
    return out


def _own_scope(fdef):
    """Intent:
        Every node of `fdef`'s body that belongs to its own scope: the
        walk stops at a nested function, lambda or class, whose names
        are bound in a scope of their own.
    """
    stack = list(reversed(fdef.body))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _locally_bound(fdef) -> set:
    """Intent:
        The names `fdef`'s own scope binds other than by a top-level
        import of `sys` or `sys.exit`: its parameters, every name it
        assigns, deletes or binds in a `for`, `with`, `except` or
        walrus, every nested `def` or `class`, and every name any other
        import binds (an import of `sys` inside a branch, loop or `try`
        included).
    """
    args = fdef.args
    out = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
    out |= {a.arg for a in (args.vararg, args.kwarg) if a is not None}
    top = {id(node) for node in fdef.body}
    for node in _own_scope(fdef):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            out.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            out.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                spelled = (alias.name if isinstance(node, ast.Import)
                           else f"{node.module}.{alias.name}")
                if spelled not in ("sys", _SYS_EXIT) or id(node) not in top \
                        or (isinstance(node, ast.ImportFrom) and node.level):
                    out.add(bound)
    return out


_UNBOUND = object()


def _namespace_value(fn, name: str):
    """Intent:
        The value `name` has where `fn`'s body reads it as a free name:
        a closure cell, else `fn`'s module globals, else the builtins
        those globals use; `_UNBOUND` when it has none there or `fn`
        has no namespace to look in.
    """
    try:
        fn = inspect.unwrap(fn)
    except ValueError:
        return _UNBOUND
    fn = getattr(fn, "__func__", fn)
    code = getattr(fn, "__code__", None)
    closure = getattr(fn, "__closure__", None)
    if code is not None and closure and name in code.co_freevars:
        try:
            return closure[code.co_freevars.index(name)].cell_contents
        except ValueError:
            return _UNBOUND
    globs = getattr(fn, "__globals__", None)
    if not isinstance(globs, dict):
        return _UNBOUND
    if name in globs:
        return globs[name]
    found = globs.get("__builtins__", builtins)
    found = found if isinstance(found, dict) else vars(found)
    return found.get(name, _UNBOUND)


def _is_quitter(value) -> bool:
    """Intent:
        Whether `value` is the interpreter's `exit` or `quit` object,
        which raises `SystemExit` with the code it is called with.
    """
    return type(value).__name__ == "Quitter" \
        and type(value).__module__ == "_sitebuiltins"


def exits_as_raises(fdef, fn):
    """Intent:
        `fdef` with every statement that only calls `sys.exit` (any
        import spelling of it, as a module attribute or a name) or the
        interpreter's `exit` or `quit`, with no argument or one
        positional argument, replaced by `raise SystemExit(...)` with
        the same argument and the call's source location. `fdef` itself
        when there is no such statement; otherwise a rewritten copy,
        and `fdef` is left unchanged.

    Notes:
        A name is read as `sys`, `sys.exit` or `exit`/`quit` only where
        it resolves to that object: bound by a top-level import of
        `sys` or `sys.exit` in `fdef`'s body on an earlier line and
        bound nowhere else there, or not bound in `fdef`'s own scope
        and found to be that object in `fn`'s closure, globals or
        builtins. A call inside an
        expression, a call with keywords or a starred argument, and a
        call inside a nested function, lambda or class are left as they
        are. The interpreter's `exit` closes standard input before it
        raises; the rewrite reads only the raise.
    """
    imports = _import_bindings(fdef)
    shadowed = _locally_bound(fdef)

    def resolve(name: str, line: int):
        if name in shadowed:
            return _UNBOUND
        if name in imports:
            target, imported_at = imports[name]
            if imported_at >= line:
                return _UNBOUND
            return sys if target == "sys" else sys.exit
        return _namespace_value(fn, name)

    def is_exit_call(call) -> bool:
        if not isinstance(call, ast.Call) or call.keywords \
                or len(call.args) > 1 \
                or any(isinstance(a, ast.Starred) for a in call.args):
            return False
        func = call.func
        if isinstance(func, ast.Name):
            value = resolve(func.id, call.lineno)
            return value is sys.exit or _is_quitter(value)
        return isinstance(func, ast.Attribute) and func.attr == "exit" \
            and isinstance(func.value, ast.Name) \
            and resolve(func.value.id, call.lineno) is sys

    def exit_statements(tree) -> set:
        return {id(node) for node in _own_scope(tree)
                if isinstance(node, ast.Expr) and is_exit_call(node.value)}

    if not exit_statements(fdef):
        return fdef
    out = copy.deepcopy(fdef)
    wanted = exit_statements(out)

    class _Rewrite(ast.NodeTransformer):
        def visit_Expr(self, node):
            if id(node) not in wanted:
                return node
            call = node.value
            exc = ast.copy_location(
                ast.Call(func=ast.copy_location(
                    ast.Name(id="SystemExit", ctx=ast.Load()), call.func),
                    args=list(call.args), keywords=[]), call)
            return ast.copy_location(ast.Raise(exc=exc, cause=None), node)

    return ast.fix_missing_locations(_Rewrite().visit(out))
