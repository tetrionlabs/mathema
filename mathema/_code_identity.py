# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The identity of the code behind a language's membership.

A verdict that rests on a language's stated definition also rests on
the language's own `contains()`, since the definition was checked
against it. `membership_identity(language)` is a hash of everything
that answer is computed from, as far as it can be read: the language's
class and its methods, the values the object holds, and for each
Python function reached its source (or its bytecode, when no source
is available), its defaults, its closure and the module-level names it
reads. A record stamped with it goes stale when any of these is
edited.

What it cannot read is left out: a C function counts by its name, a
module by its name, and an object of a class defined in the standard
library or a compiled extension by its type's name. A function or class
of mathema itself counts by its source, without the module-level names
it reads, since those are versioned with mathema. The walk stops at
`_DEPTH` levels and never enters the same object twice.

Stdlib only.
"""
from __future__ import annotations

import ast
import functools
import hashlib
import inspect
import re
import sys
import textwrap
import types

#: how many levels of reference the walk follows from the language
_DEPTH = 6

#: the modules whose classes and functions are read by name only
_OPAQUE = frozenset(sys.stdlib_module_names) | {"builtins"}

_PLAIN = (str, int, float, complex, bool, bytes, type(None), type(Ellipsis))


def _opaque(obj) -> bool:
    module = getattr(obj, "__module__", None) or ""
    return module.split(".")[0] in _OPAQUE


def _source(fn) -> "str | None":
    """The source of `fn` with comments and layout normalised away
    when it parses on its own, else as written; None when there is
    none."""
    try:
        text = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):
        return None
    try:
        return ast.dump(ast.parse(text))
    except SyntaxError:
        return text.strip()


def _own(obj) -> bool:
    module = getattr(obj, "__module__", None) or ""
    return module == "mathema" or module.startswith("mathema.")


def _const(value) -> str:
    """A constant as text that is the same in every process: a set's
    members in sorted order."""
    if isinstance(value, types.CodeType):
        return _code(value)
    if isinstance(value, (frozenset, set)):
        return "{" + ", ".join(sorted(_const(v) for v in value)) + "}"
    if isinstance(value, tuple):
        return "(" + ", ".join(_const(v) for v in value) + ")"
    return repr(value)


def _names(code: types.CodeType) -> list:
    out = list(code.co_names)
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            out.extend(_names(const))
    return out


def _code(code: types.CodeType) -> str:
    """Bytecode, names and constants of `code`, without its file or
    line numbers."""
    consts = [_const(c) for c in code.co_consts]
    return repr((sys.version_info[:2], code.co_code, code.co_names, code.co_varnames,
                 code.co_freevars, consts))


class _Walk:
    def __init__(self) -> None:
        self.parts: list = []
        self.seen: set = set()

    def add(self, *parts) -> None:
        self.parts.append(repr(parts))

    def value(self, obj, depth: int) -> None:
        if isinstance(obj, _PLAIN):
            self.add("v", type(obj).__name__, repr(obj))
            return
        if isinstance(obj, re.Pattern):
            self.add("re", obj.pattern, obj.flags)
            return
        if depth <= 0:
            self.add("deep", type(obj).__qualname__)
            return
        if id(obj) in self.seen:
            self.add("seen", type(obj).__qualname__)
            return
        self.seen.add(id(obj))
        if isinstance(obj, (tuple, list)):
            self.add("seq", type(obj).__name__, len(obj))
            for item in obj:
                self.value(item, depth - 1)
        elif isinstance(obj, (set, frozenset)):
            self.add("set", sorted(_const(v) for v in obj if isinstance(v, _PLAIN)))
            for item in obj:
                if not isinstance(item, _PLAIN):
                    self.value(item, depth - 1)
        elif isinstance(obj, dict):
            self.add("dict", len(obj))
            for key, item in obj.items():
                self.value(key, depth - 1)
                self.value(item, depth - 1)
        elif isinstance(obj, types.ModuleType):
            self.add("module", obj.__name__)
        elif isinstance(obj, (types.MethodType,)):
            self.value(obj.__func__, depth)
            self.value(obj.__self__, depth - 1)
        elif isinstance(obj, types.FunctionType):
            self.function(obj, depth)
        elif isinstance(obj, functools.partial):
            self.add("partial")
            self.value(obj.func, depth - 1)
            self.value(obj.args, depth - 1)
            self.value(obj.keywords, depth - 1)
        elif isinstance(obj, (staticmethod, classmethod)):
            self.value(obj.__func__, depth)
        elif isinstance(obj, property):
            for part in (obj.fget, obj.fset, obj.fdel):
                if part is not None:
                    self.value(part, depth - 1)
        elif isinstance(obj, type):
            self.cls(obj, depth)
        elif isinstance(obj, (types.BuiltinFunctionType, types.BuiltinMethodType)) \
                or callable(obj) and _opaque(type(obj)) and not hasattr(obj, "__dict__"):
            self.add("builtin", getattr(obj, "__module__", None),
                     getattr(obj, "__qualname__", type(obj).__qualname__))
        else:
            self.instance(obj, depth)

    def function(self, fn: types.FunctionType, depth: int) -> None:
        if _opaque(fn):
            self.add("fn", fn.__module__, fn.__qualname__)
            return
        source = _source(fn)
        # a lambda's source is its whole line, so its bytecode is read too
        self.add("fn", source if source is not None and fn.__name__ != "<lambda>"
                 else _code(fn.__code__))
        self.value(fn.__defaults__, depth - 1)
        self.value(fn.__kwdefaults__, depth - 1)
        for cell in fn.__closure__ or ():
            try:
                self.value(cell.cell_contents, depth - 1)
            except ValueError:
                self.add("empty cell")
        if _own(fn):
            return
        module_globals = fn.__globals__
        for name in dict.fromkeys(_names(fn.__code__)):
            if name in module_globals:
                self.add("global", name)
                self.value(module_globals[name], depth - 1)

    def cls(self, cls: type, depth: int) -> None:
        if _opaque(cls):
            self.add("class", cls.__module__, cls.__qualname__)
            return
        self.add("class", cls.__qualname__)
        for base in cls.__mro__:
            if base is object or _opaque(base):
                self.add("base", base.__module__, base.__qualname__)
                continue
            for name, member in base.__dict__.items():
                if name in ("__dict__", "__weakref__", "__doc__", "__module__",
                            "__qualname__", "__firstlineno__", "__static_attributes__"):
                    continue
                self.add("attr", base.__qualname__, name)
                self.value(member, depth - 1)

    def instance(self, obj, depth: int) -> None:
        self.value(type(obj), depth - 1)
        state = getattr(obj, "__dict__", None)
        if isinstance(state, dict):
            self.value(state, depth - 1)
        for name in getattr(type(obj), "__slots__", ()) or ():
            if isinstance(name, str) and hasattr(obj, name):
                self.add("slot", name)
                self.value(getattr(obj, name), depth - 1)


def membership_identity(language) -> str:
    """Intent:
        `cd:<sha>`, a 12-hex-char hash of the code and values a
        language object's membership is computed from, read as the
        module docstring describes. The same object, imported from the
        same source, gives the same identity in any process on the
        same Python.
    """
    walk = _Walk()
    walk.value(language, _DEPTH)
    digest = hashlib.sha256("\n".join(walk.parts).encode("utf-8", "surrogatepass"))
    return f"cd:{digest.hexdigest()[:12]}"
