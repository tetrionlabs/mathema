# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Reading a function as a pattern validator: a function of one text
parameter whose whole behaviour is the truth of one regular-expression
match on that parameter.

Two shapes are read. A refusing validator raises when the match fails
and returns its argument otherwise (`if not PAT.fullmatch(x): raise
ValueError(x)` then `return x`, the test also written `is None`). A
predicate returns the truth of the match (`return bool(PAT.search(x))`,
`return PAT.match(x) is not None`, or `is None` for its negation).

The match is `PAT.fullmatch(x)`, `PAT.match(x)` or `PAT.search(x)` on a
compiled pattern, `re.compile(P[, flags]).fullmatch(x)`, or
`re.fullmatch(P, x[, flags])` and its two siblings. Nothing is read by
its name: `PAT` must be bound, in the function's globals, to a compiled
`re.Pattern`; `re` must be bound there to the standard `re` module; and
neither name may be a parameter or assigned in the body. A pattern
written inline is a string literal and its flags are `re` constants
joined by `|`, compiled here with `re.compile`.

A function that does anything else (transforms the text, tests it
twice, matches something other than the bare parameter) is not read,
and `read_validator` says which part stopped it.
"""
from __future__ import annotations

import ast
import builtins
import inspect
import re
import textwrap
from dataclasses import dataclass

MODES = ("fullmatch", "match", "search")


@dataclass(frozen=True)
class Validator:
    """A function read as a pattern validator: the text parameter
    `param`; `accepts`, the bound method of the compiled pattern the
    function calls on it (`PAT.fullmatch`), whose truth is acceptance;
    `raises`, the exception class a refusing validator raises (None for
    a predicate); and `negated`, set for a predicate that returns the
    match's failure."""
    param: str
    accepts: object
    raises: "type | None" = None
    negated: bool = False

    @property
    def pattern(self) -> "re.Pattern":
        return self.accepts.__self__  # type: ignore[attr-defined]

    @property
    def mode(self) -> str:
        return self.accepts.__name__  # type: ignore[attr-defined]

    def described(self) -> str:
        """`re.compile('[a-z]+').fullmatch`, with the flags when any."""
        flags = self.pattern.flags & ~re.UNICODE
        said = f", {re.RegexFlag(flags)!s}" if flags else ""
        return f"re.compile({self.pattern.pattern!r}{said}).{self.mode}"


class _Declined(Exception):
    """Why a function is not read as a validator."""


def _stored_names(tree: ast.AST) -> set:
    """Every name the function binds: its parameters and anything it
    assigns, imports, deletes or declares global or nonlocal."""
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return names


class _Reader:
    """One function's source read against the objects its names are
    bound to."""

    def __init__(self, fn, tree: ast.FunctionDef) -> None:
        self.fn = fn
        self.globals = getattr(fn, "__globals__", {})
        self.local = _stored_names(tree)

    def _global(self, name: str):
        """The object a free name is bound to in the function's globals
        or the builtins."""
        if name in self.local:
            raise _Declined(f"{name!r} is a parameter or is assigned in the function")
        if name in self.globals:
            return self.globals[name]
        if hasattr(builtins, name):
            return getattr(builtins, name)
        raise _Declined(f"{name!r} is not bound where the function is defined")

    def value(self, node: ast.AST):
        """The object a name or a dotted name is bound to."""
        if isinstance(node, ast.Name):
            return self._global(node.id)
        if isinstance(node, ast.Attribute):
            owner = self.value(node.value)
            if not inspect.ismodule(owner):
                raise _Declined(f"{ast.unparse(node)} is not a name in a module")
            try:
                return getattr(owner, node.attr)
            except AttributeError:
                raise _Declined(f"{ast.unparse(node)} is not bound") from None
        raise _Declined(f"{ast.unparse(node)} is not a name")

    def _text(self, node: ast.AST) -> str:
        """A pattern written as a string literal, or a name bound to a
        string."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, (ast.Name, ast.Attribute)):
            bound = self.value(node)
            if isinstance(bound, str):
                return bound
        raise _Declined(f"the pattern {ast.unparse(node)} is not a string literal")

    def _flags(self, node: ast.AST) -> int:
        """Flags written as `re` constants joined by `|`."""
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self._flags(node.left) | self._flags(node.right)
        if isinstance(node, ast.Attribute):
            bound = self.value(node)
            if isinstance(bound, re.RegexFlag) and self.value(node.value) is re:
                return int(bound)
        raise _Declined(f"the flags {ast.unparse(node)} are not `re` constants joined by `|`")

    def _compiled(self, node: ast.AST) -> "re.Pattern":
        """The compiled pattern an expression is: a name bound to one,
        or a call of `re.compile` on a literal."""
        if isinstance(node, ast.Call):
            if self.value(node.func) is not re.compile or node.keywords \
                    or not 1 <= len(node.args) <= 2:
                raise _Declined(f"{ast.unparse(node)} is not a call of re.compile "
                                f"on a pattern and flags")
            flags = self._flags(node.args[1]) if len(node.args) == 2 else 0
            return self._compile(self._text(node.args[0]), flags)
        bound = self.value(node)
        if not isinstance(bound, re.Pattern):
            raise _Declined(f"{ast.unparse(node)} is not a compiled re.Pattern")
        return bound

    @staticmethod
    def _compile(pattern: str, flags: int) -> "re.Pattern":
        try:
            return re.compile(pattern, flags)
        except re.error as e:
            raise _Declined(f"the pattern {pattern!r} does not compile ({e})") from None

    def match(self, node: ast.AST, param: str):
        """The bound method `PAT.<mode>` a match expression on the bare
        parameter calls."""
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) \
                or node.func.attr not in MODES or node.keywords:
            raise _Declined(f"{ast.unparse(node)} is not a fullmatch, match or search")
        mode, owner = node.func.attr, node.func.value

        def on_param(arg: ast.AST) -> None:
            if not (isinstance(arg, ast.Name) and arg.id == param):
                raise _Declined(f"the match is on {ast.unparse(arg)}, not on the "
                                f"parameter {param!r} as passed")
        module_call = False
        if isinstance(owner, (ast.Name, ast.Attribute)):
            module_call = self.value(owner) is re
        if module_call:
            if self.value(node.func) is not getattr(re, mode) or not 2 <= len(node.args) <= 3:
                raise _Declined(f"{ast.unparse(node)} is not re.{mode}(pattern, text[, flags])")
            on_param(node.args[1])
            flags = self._flags(node.args[2]) if len(node.args) == 3 else 0
            compiled = self._compile(self._text(node.args[0]), flags)
        else:
            if len(node.args) != 1:
                raise _Declined(f"{ast.unparse(node)} passes a position or an end, "
                                f"so it does not match the whole parameter")
            on_param(node.args[0])
            compiled = self._compiled(owner)
        return getattr(compiled, mode)

    def test(self, node: ast.AST, param: str) -> tuple:
        """`(bound method, truth)` for a test of a match: `truth` is
        True when the expression is true exactly when the match
        succeeds (`m`, `bool(m)`, `m is not None`), False when it is
        true exactly when the match fails (`not m`, `m is None`)."""
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            method, truth = self.test(node.operand, param)
            return method, not truth
        if isinstance(node, ast.Compare) and len(node.ops) == 1 \
                and isinstance(node.ops[0], (ast.Is, ast.IsNot)) \
                and isinstance(node.comparators[0], ast.Constant) \
                and node.comparators[0].value is None:
            return self.match(node.left, param), isinstance(node.ops[0], ast.IsNot)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "bool" and len(node.args) == 1 and not node.keywords \
                and self._global("bool") is bool:
            return self.match(node.args[0], param), True
        return self.match(node, param), True

    def raised(self, node: ast.Raise) -> type:
        """The exception class a `raise` statement raises."""
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if exc is None or node.cause is not None:
            raise _Declined("the raise is a re-raise or has a cause")
        bound = self.value(exc)
        if not (isinstance(bound, type) and issubclass(bound, Exception)):
            raise _Declined(f"{ast.unparse(exc)} is not an exception class")
        return bound


def _function_tree(fn) -> ast.FunctionDef:
    try:
        source = textwrap.dedent(inspect.getsource(fn))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        raise _Declined("its source is not available") from None
    found = tree.body[0] if tree.body else None
    if not isinstance(found, ast.FunctionDef) or found.decorator_list:
        raise _Declined("it is not a plain, undecorated function")
    return found


def _read(fn) -> Validator:
    tree = _function_tree(fn)
    args = tree.args
    if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs or args.defaults \
            or len(args.args) != 1:
        raise _Declined("it does not take exactly one parameter")
    param = args.args[0].arg
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    reader = _Reader(fn, tree)
    if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is not None:
        value = body[0].value
        bare = isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
        if bare:
            raise _Declined("it returns the match object, not its truth")
        method, truth = reader.test(value, param)
        return Validator(param, method, None, negated=not truth)
    if len(body) == 2 and isinstance(body[0], ast.If) and not body[0].orelse \
            and len(body[0].body) == 1 and isinstance(body[0].body[0], ast.Raise) \
            and isinstance(body[1], ast.Return) \
            and isinstance(body[1].value, ast.Name) and body[1].value.id == param:
        method, truth = reader.test(body[0].test, param)
        if truth:
            raise _Declined("it raises when the match succeeds")
        return Validator(param, method, reader.raised(body[0].body[0]))
    raise _Declined("its body is more than one test of one match on the parameter")


def read_validator(fn) -> "Validator | str":
    """Intent:
        `fn` read as a pattern validator, or the reason it is not one,
        as a phrase that completes "the function is not read as a
        pattern validator: ...".
    """
    try:
        return _read(fn)
    except _Declined as e:
        return str(e)


__all__ = ["MODES", "Validator", "read_validator"]
