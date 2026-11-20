# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Reading a `raise` statement together with the path that reaches it.

A path is what Python evaluates on the way to a `raise`, in order: the
statements before it and the tests of the branches it passes. The path
is read as raising exactly one class only when nothing on it can raise
first: every statement and test is built from operations that cannot
fail on the values the names hold there, the exception's arguments
cannot fail either, the name raised resolves through the function's
own globals and builtins to an exception class, and that class is built
by a constructor whose behaviour on these arguments is known. Anything
else leaves the raise unread, with the reason.

The same reading serves every route that proves something from a
`raise`: derive's `raises(f(x), E)` claims and the missing-value
policies read from a guard.
"""
from __future__ import annotations

import ast
import builtins
import math
import sys
import types
from dataclasses import dataclass

#: the largest finite double: an int of at most this magnitude converts
#: to float, and so has at most 309 decimal digits
_FLOAT_MAX = sys.float_info.max

#: the levels a reading reaches, from strongest: TOTAL, evaluation
#: always finishes with a value; HALTS, evaluation always finishes,
#: with a value or an ordinary `Exception`; UNKNOWN, neither is shown
TOTAL, HALTS, UNKNOWN = 2, 1, 0

_NONE = type(None)
_NUMBERS = frozenset({int, float, bool})
#: types whose `==`, `!=`, hash and truth are the builtin ones, which
#: never raise
_SCALARS = frozenset({int, float, bool, str, _NONE})
#: types whose `str`, `repr`, `ascii` and `format(v, "")` never raise
#: (an int only when it has at most 4300 digits, see `_text_level`)
_TEXT = frozenset({float, bool, str, _NONE})


@dataclass(frozen=True)
class ValueKind:
    """What is known of a value where a path runs: `types`, the exact
    Python types it may have (None when it may be any object), and
    `magnitude`, an upper bound on its absolute value when it is a
    number (`math.inf` when unbounded)."""
    types: "frozenset | None"
    magnitude: float = math.inf


ANY = ValueKind(None)
_BOOL = ValueKind(frozenset({bool}), 1.0)
_STR = ValueKind(frozenset({str}))


def _union(a: ValueKind, b: ValueKind) -> ValueKind:
    if a.types is None or b.types is None:
        return ANY
    return ValueKind(a.types | b.types, max(a.magnitude, b.magnitude))


def _magnitude(value) -> float:
    try:
        found = float(abs(value))
    except (OverflowError, TypeError, ValueError):
        return math.inf
    return found if found <= _FLOAT_MAX else math.inf


def kind_of_value(value) -> ValueKind:
    """The kind of one known value: its exact type, and its magnitude
    when it is a number."""
    if type(value) in _NUMBERS:
        return ValueKind(frozenset({type(value)}), _magnitude(value))
    return ValueKind(frozenset({type(value)}))


def kind_of_bound(bound) -> ValueKind:
    """Intent:
        The kind of a value drawn from a declared bound: the members'
        own types for a finite set, a number of at most the larger end's
        magnitude for an interval (unbounded for an infinite end or a
        named number set), ANY for anything else.

    Notes:
        A `ReachInterval` stands in for an unbounded direction, so it
        is read as unbounded. A `Domain` that admits a missing value or
        a member beside its pieces is ANY.
    """
    from ..domain import Domain, Interval, ReachInterval
    if isinstance(bound, frozenset):
        found = ValueKind(frozenset())
        for value in bound:
            found = _union(found, kind_of_value(value))
        return found
    if isinstance(bound, ReachInterval):
        return ValueKind(_NUMBERS)
    if isinstance(bound, Interval) or (isinstance(bound, tuple) and len(bound) == 2
                                       and all(type(e) in _NUMBERS for e in bound)):
        return ValueKind(_NUMBERS, max(_magnitude(bound[0]), _magnitude(bound[1])))
    if isinstance(bound, str) and bound in ("Z", "N", "R"):
        return ValueKind(_NUMBERS)
    if isinstance(bound, Domain):
        if bound.base_type not in ("R", "Z", "N") or bound.dims or bound.absent \
                or bound.members or not bound.pieces:
            return ANY
        found = ValueKind(frozenset())
        for piece in bound.pieces:
            if not isinstance(piece, (Interval, frozenset)):
                return ANY
            found = _union(found, kind_of_bound(piece))
        return found
    return ANY


#: The builtin exception classes whose constructor is read, each with
#: the most positional arguments it is read to accept (None for any
#: number). Each takes its arguments as `BaseException.__init__` does,
#: storing them in `args` whatever they are, and none accepts a keyword
#: argument as read here. `OSError` and its subclasses map two or more
#: arguments onto `errno`, `strerror` and a subclass chosen by the
#: errno; `SyntaxError` and its subclasses unpack a second argument as
#: a location tuple: so each is read with at most one. The classes left
#: out check their arguments (`UnicodeDecodeError` needs five,
#: `ExceptionGroup` a message and a non-empty sequence of exceptions).
BUILTIN_CONSTRUCTORS: dict = {
    **{name: None for name in (
        "BaseException", "Exception", "ArithmeticError", "AssertionError",
        "AttributeError", "BufferError", "EOFError", "FloatingPointError",
        "GeneratorExit", "ImportError", "ModuleNotFoundError", "IndexError",
        "KeyError", "KeyboardInterrupt", "LookupError", "MemoryError",
        "NameError", "NotImplementedError", "OverflowError", "RecursionError",
        "ReferenceError", "RuntimeError", "StopAsyncIteration", "StopIteration",
        "SystemError", "SystemExit", "TypeError", "UnboundLocalError",
        "UnicodeError", "ValueError", "ZeroDivisionError",
        "PythonFinalizationError", "Warning", "BytesWarning",
        "DeprecationWarning", "EncodingWarning", "FutureWarning",
        "ImportWarning", "PendingDeprecationWarning", "ResourceWarning",
        "RuntimeWarning", "SyntaxWarning", "UnicodeWarning", "UserWarning")},
    **{name: 1 for name in (
        "OSError", "BlockingIOError", "ChildProcessError", "ConnectionError",
        "BrokenPipeError", "ConnectionAbortedError", "ConnectionRefusedError",
        "ConnectionResetError", "FileExistsError", "FileNotFoundError",
        "InterruptedError", "IsADirectoryError", "NotADirectoryError",
        "PermissionError", "ProcessLookupError", "TimeoutError",
        "SyntaxError", "IndentationError", "TabError")},
}


class UnreadRaise:
    """A path ending in `raise` that was not read as raising one class:
    `reason` says which expression stopped the reading, and `halts`
    whether every run of the path still ends in an ordinary exception
    (the class raised, or an `Exception` from something before it)."""

    def __init__(self, reason: str, halts: bool = False) -> None:
        self.reason = reason
        self.halts = halts

    def __repr__(self) -> str:
        return f"UnreadRaise({self.reason!r}, halts={self.halts})"


@dataclass(frozen=True)
class ReadRaise:
    """A path read as raising exactly `cls` on every run: `name` is the
    spelling in the source, `line` the line of the `raise`."""
    cls: type
    name: str
    line: "int | None"


class _Namespace:
    """The names a function's body reads: its own locals (from its code
    object), its module's globals and its builtins."""

    def __init__(self, fn) -> None:
        code = getattr(fn, "__code__", None)
        found_globals = getattr(fn, "__globals__", None)
        self.ok = code is not None and isinstance(found_globals, dict)
        self.globals: dict = found_globals if self.ok else {}
        self.locals = (frozenset(code.co_varnames) | frozenset(code.co_cellvars)
                       | frozenset(code.co_freevars)) if code is not None else frozenset()
        found = getattr(fn, "__builtins__", None)
        if found is None and self.ok:
            found = self.globals.get("__builtins__", builtins)
        self.builtins = vars(found) if isinstance(found, types.ModuleType) else (found or {})

    _MISSING = object()

    def lookup(self, name: str):
        """The object `name` reads outside the function's locals, or
        `_MISSING`."""
        if not self.ok or name in self.locals:
            return self._MISSING
        if name in self.globals:
            return self.globals[name]
        return self.builtins.get(name, self._MISSING)

    def resolve(self, node: ast.AST):
        """The object a bare name or a dotted attribute of a module
        resolves to, or `_MISSING`. An attribute is read only off a
        plain module object that holds it in its own namespace, where
        reading it runs no code."""
        if isinstance(node, ast.Name):
            return self.lookup(node.id)
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            if type(base) is types.ModuleType and node.attr in vars(base):
                return vars(base)[node.attr]
        return self._MISSING

    def is_builtin(self, node: ast.AST, name: str) -> bool:
        """Whether `node` is the bare name `name` and resolves to the
        builtin of that name itself."""
        return isinstance(node, ast.Name) and node.id == name \
            and self.lookup(name) is getattr(builtins, name)


def _is_numeric(kind: ValueKind) -> bool:
    return kind.types is not None and bool(kind.types) and kind.types <= _NUMBERS


def _converts_to_float(kind: ValueKind) -> bool:
    """Whether an int among the kind's values always converts to float."""
    return int not in (kind.types or frozenset()) or kind.magnitude <= _FLOAT_MAX


def _text_level(kind: ValueKind) -> int:
    """How surely `str`, `repr` or `format(v, "")` of a value builds its
    text: TOTAL for a float, bool, str or None, and for an int of finite
    magnitude bound, which has at most 309 digits (Python refuses to
    convert an int of more digits than `sys.get_int_max_str_digits()`,
    which is 4300 by default and never set below 640 except to 0 for no
    limit); HALTS for an unbounded int, whose refusal is a ValueError;
    UNKNOWN for any other object, whose own method runs."""
    if not kind.types:
        return UNKNOWN
    if kind.types <= _TEXT:
        return TOTAL
    if kind.types <= _TEXT | {int}:
        return TOTAL if math.isfinite(kind.magnitude) else HALTS
    return UNKNOWN


def _truth_level(kind: ValueKind) -> int:
    return TOTAL if kind.types is not None and kind.types <= _SCALARS else UNKNOWN


def _arithmetic(op: ast.AST, a: ValueKind, b: ValueKind, right: ast.AST):
    """The level and kind of `a <op> b` for two numbers."""
    ta, tb = a.types or frozenset(), b.types or frozenset()
    either_float = float in ta or float in tb
    both_int = bool(ta - {float}) and bool(tb - {float})
    out_types = frozenset(({float} if either_float else set())
                          | ({int} if both_int else set()))
    mixes = (float in ta and not _converts_to_float(b)) \
        or (float in tb and not _converts_to_float(a))
    if isinstance(op, (ast.Add, ast.Sub)):
        return (HALTS if mixes else TOTAL), ValueKind(out_types, a.magnitude + b.magnitude)
    if isinstance(op, ast.Mult):
        size = 0.0 if 0.0 in (a.magnitude, b.magnitude) else a.magnitude * b.magnitude
        return (HALTS if mixes else TOTAL), ValueKind(out_types, size)
    if isinstance(op, (ast.Div, ast.FloorDiv, ast.Mod)):
        divisor = right.value if isinstance(right, ast.Constant) else None
        if type(divisor) in (int, float) and abs(divisor) >= 1 \
                and _converts_to_float(a) and math.isfinite(divisor):
            kind = ValueKind(frozenset({float}) if isinstance(op, ast.Div) else out_types,
                             a.magnitude)
            return TOTAL, kind
        return HALTS, ValueKind(_NUMBERS)
    return UNKNOWN, ANY


#: the math functions of one number a reading accepts, all returning bool
_MATH_TESTS = ("isnan", "isinf", "isfinite")


def _call_level(node: ast.Call, kinds: dict, ns: _Namespace):
    if node.keywords or len(node.args) != 1 or isinstance(node.args[0], ast.Starred):
        return UNKNOWN, ANY
    level, kind = read_expression(node.args[0], kinds, ns)
    for name in ("str", "repr", "ascii"):
        if ns.is_builtin(node.func, name):
            return min(level, _text_level(kind)), _STR
    if ns.is_builtin(node.func, "abs"):
        if _is_numeric(kind):
            return level, ValueKind(kind.types - {bool} | ({int} if bool in kind.types
                                                           else set()), kind.magnitude)
        return UNKNOWN, ANY
    called = ns.resolve(node.func)
    if any(called is getattr(math, name) for name in _MATH_TESTS):
        if _is_numeric(kind):
            return min(level, TOTAL if _converts_to_float(kind) else HALTS), _BOOL
        return UNKNOWN, _BOOL
    numpy = sys.modules.get("numpy")
    if numpy is not None and called is getattr(numpy, "isnan", None):
        if kind.types is not None and kind.types and kind.types <= {float}:
            return level, _BOOL
        return UNKNOWN, _BOOL
    pandas = sys.modules.get("pandas")
    if pandas is not None and any(called is getattr(pandas, name, None)
                                  for name in ("isna", "isnull")):
        if kind.types is not None and kind.types and kind.types <= {float, _NONE}:
            return level, _BOOL
        return UNKNOWN, _BOOL
    return UNKNOWN, ANY


def _compare_level(node: ast.Compare, kinds: dict, ns: _Namespace):
    operands = [node.left, *node.comparators]
    read = [read_expression(o, kinds, ns) for o in operands]
    level = min(r[0] for r in read)
    for op, (_, a), (_, b), right in zip(node.ops, read, read[1:], node.comparators):
        if isinstance(op, (ast.Is, ast.IsNot)):
            continue
        if isinstance(op, (ast.Eq, ast.NotEq)):
            if _truth_level(a) < TOTAL or _truth_level(b) < TOTAL:
                return UNKNOWN, _BOOL
            continue
        if isinstance(op, (ast.In, ast.NotIn)):
            if not (isinstance(right, (ast.Tuple, ast.List, ast.Set))
                    and all(isinstance(e, ast.Constant) and type(e.value) in _SCALARS
                            for e in right.elts)
                    and _truth_level(a) == TOTAL):
                return UNKNOWN, _BOOL
            continue
        if (_is_numeric(a) and _is_numeric(b)) or (
                a.types is not None and b.types is not None
                and a.types and b.types and a.types | b.types <= {str}):
            continue
        if a.types is not None and b.types is not None and a.types | b.types <= _SCALARS:
            level = min(level, HALTS)
            continue
        return UNKNOWN, _BOOL
    return level, _BOOL


def read_expression(node: ast.AST, kinds: dict, ns: _Namespace):
    """Intent:
        `(level, kind)` for evaluating `node` where each name in `kinds`
        is bound to a value of that kind: TOTAL when evaluation cannot
        fail, HALTS when it always finishes but may raise an ordinary
        `Exception`, UNKNOWN otherwise; `kind` what the value is known
        to be.

    Notes:
        Read: constants, bound names and names of the module or the
        builtins, arithmetic on numbers (`+ - *` total unless a float
        meets an int too large to convert; `/ // %` total only by a
        constant of magnitude at least 1), unary minus and plus on
        numbers, `not`, `and`/`or`, comparisons of builtin scalars,
        `+` of two strings, an f-string with no format specification,
        `str`/`repr`/`ascii`/`abs` that resolve to the builtins, and
        `math.isnan`/`isinf`/`isfinite`, `numpy.isnan` and
        `pandas.isna`/`isnull` of one value whose type makes them total.
        Every other call, attribute, subscript or comprehension is
        UNKNOWN: it may run any code.
    """
    if isinstance(node, ast.Constant):
        return TOTAL, kind_of_value(node.value)
    if isinstance(node, ast.Name):
        if node.id in kinds:
            return TOTAL, kinds[node.id]
        found = ns.lookup(node.id)
        if found is _Namespace._MISSING:
            # an unbound local or an undefined name raises NameError
            return HALTS, ANY
        return TOTAL, kind_of_value(found) if type(found) in _SCALARS else ANY
    if isinstance(node, ast.UnaryOp):
        level, kind = read_expression(node.operand, kinds, ns)
        if isinstance(node.op, ast.Not):
            return min(level, _truth_level(kind)), _BOOL
        if isinstance(node.op, (ast.USub, ast.UAdd)) and _is_numeric(kind):
            return level, ValueKind((kind.types - {bool}) | ({int} if bool in kind.types
                                                             else set()), kind.magnitude)
        return UNKNOWN, ANY
    if isinstance(node, ast.BinOp):
        left, a = read_expression(node.left, kinds, ns)
        right, b = read_expression(node.right, kinds, ns)
        level = min(left, right)
        if _is_numeric(a) and _is_numeric(b):
            own, kind = _arithmetic(node.op, a, b, node.right)
            return min(level, own), kind
        if isinstance(node.op, ast.Add) and a.types is not None and b.types is not None \
                and a.types and b.types and a.types | b.types <= {str}:
            return level, _STR
        return UNKNOWN, ANY
    if isinstance(node, ast.BoolOp):
        level, kind = TOTAL, ValueKind(frozenset())
        for value in node.values:
            part, found = read_expression(value, kinds, ns)
            level = min(level, part, _truth_level(found))
            kind = _union(kind, found)
        return level, kind
    if isinstance(node, ast.Compare):
        return _compare_level(node, kinds, ns)
    if isinstance(node, ast.JoinedStr):
        level = TOTAL
        for part in node.values:
            if isinstance(part, ast.Constant):
                continue
            if not isinstance(part, ast.FormattedValue) or part.format_spec is not None:
                return UNKNOWN, _STR
            inner, kind = read_expression(part.value, kinds, ns)
            level = min(level, inner, _text_level(kind))
        return level, _STR
    if isinstance(node, ast.Call):
        return _call_level(node, kinds, ns)
    if isinstance(node, (ast.Tuple, ast.List)):
        level = TOTAL
        for element in node.elts:
            if isinstance(element, ast.Starred):
                return UNKNOWN, ANY
            level = min(level, read_expression(element, kinds, ns)[0])
        return level, ValueKind(frozenset({tuple if isinstance(node, ast.Tuple) else list}))
    return UNKNOWN, ANY


def _source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _where(node: ast.AST) -> str:
    line = getattr(node, "lineno", None)
    return f" on line {line}" if line is not None else ""


def constructor_refusal(cls: type, count: int, keywords: list) -> "str | None":
    """Intent:
        Why building `cls` from `count` positional arguments and the
        keyword names `keywords` is not read as certainly building a
        `cls`, or None when it is: the class is made by `type` itself,
        no class of its MRO outside the builtins defines `__init__` or
        `__new__`, and every builtin class of its MRO is in
        `BUILTIN_CONSTRUCTORS`, accepting that many positional
        arguments and no keyword.
    """
    name = cls.__name__
    if type(cls) is not type:
        return (f"`{name}` is made by the metaclass `{type(cls).__name__}`, whose call "
                f"may run code of its own")
    for klass in cls.__mro__:
        if klass is object:
            continue
        if klass.__module__ != "builtins":
            if "__init__" in vars(klass) or "__new__" in vars(klass):
                return (f"building a `{name}` runs a constructor written outside the "
                        f"builtins, which may itself raise")
            continue
        if getattr(builtins, klass.__name__, None) is not klass \
                or klass.__name__ not in BUILTIN_CONSTRUCTORS:
            return (f"building `{name}` runs the constructor of `{klass.__name__}`, "
                    f"which checks its arguments and may raise instead")
        if keywords:
            return (f"`{name}` is built with the keyword argument `{keywords[0]}`, and "
                    f"the constructor of `{klass.__name__}` is not read to accept it")
        most = BUILTIN_CONSTRUCTORS[klass.__name__]
        if most is not None and count > most:
            return (f"`{name}` is built from {count} arguments, and the constructor of "
                    f"`{klass.__name__}` is read only with at most {most}")
    return None


def read_raise_path(fn, steps: list, stmt: ast.Raise, kinds: dict) -> "ReadRaise | UnreadRaise":
    """Intent:
        Whether the path `steps` followed by the `raise` statement
        `stmt` raises exactly one class on every run, where `kinds`
        holds the names bound when the path starts and what their values
        are: a `ReadRaise` naming the class, or an `UnreadRaise` with
        the reason. `steps` is `[("stmt", statement) | ("test",
        expression)]` in the order Python runs them; an assignment to a
        name binds it for what follows. `fn` is the live function whose
        body the statements come from: every name is resolved through
        its locals, globals and builtins.

    Notes:
        The raise is `raise E`, `raise E(args)` or either with `from
        None`, with `E` a bare name or a module's attribute that
        resolves to an exception class whose construction is read
        (`constructor_refusal`). An UnreadRaise is `halts` when every
        step and argument still finishes, with a value or an ordinary
        `Exception`, and the class is a subclass of `Exception` or
        `SystemExit`, so the path ends in an exception whatever it is.
    """
    ns = _Namespace(fn)
    if not ns.ok:
        return UnreadRaise("the function has no Python code object to resolve its names in")
    kinds = dict(kinds)
    first: "str | None" = None
    level = TOTAL

    def note(found: int, reason: str) -> None:
        nonlocal first, level
        if found < TOTAL and first is None:
            first = reason
        level = min(level, found)

    for kind_of_step, node in steps:
        if kind_of_step == "test":
            found, value = read_expression(node, kinds, ns)
            note(min(found, _truth_level(value)),
                 f"the test `{_source(node)}`{_where(node)} is evaluated before the raise "
                 f"and may itself raise")
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Lambda):
                kinds[node.targets[0].id] = ANY
                continue
            found, value = read_expression(node.value, kinds, ns)
            note(found, f"`{_source(node)}`{_where(node)} runs before the raise and may "
                        f"itself raise")
            kinds[node.targets[0].id] = value
            continue
        note(UNKNOWN, f"`{_source(node)}`{_where(node)} runs before the raise and is not "
                      f"read")

    exc = stmt.exc
    if exc is None:
        return UnreadRaise("a bare `raise` re-raises whatever is being handled")
    if stmt.cause is not None and not (isinstance(stmt.cause, ast.Constant)
                                       and stmt.cause.value is None):
        found, _ = read_expression(stmt.cause, kinds, ns)
        note(min(found, HALTS), f"the cause `{_source(stmt.cause)}` is evaluated before "
                                f"the raise")
    called = exc.func if isinstance(exc, ast.Call) else exc
    if not isinstance(called, (ast.Name, ast.Attribute)):
        return UnreadRaise(f"`{_source(called)}` is not a bare exception name")
    name = _source(called)
    if isinstance(called, ast.Name) and called.id in ns.locals:
        return UnreadRaise(f"`{name}` is a variable of the function or of an enclosing "
                           f"one, not shown to be the exception class the claim names")
    cls = ns.resolve(called)
    if cls is _Namespace._MISSING:
        return UnreadRaise(f"`{name}` does not resolve to an attribute of a module, a "
                           f"global or a builtin where the function is defined")
    if not (isinstance(cls, type) and issubclass(cls, BaseException)):
        return UnreadRaise(f"`{name}` where the function is defined is not an exception "
                           f"class")
    if isinstance(exc, ast.Call):
        arguments = list(exc.args) + [k.value for k in exc.keywords]
        if any(isinstance(a, ast.Starred) for a in exc.args) \
                or any(k.arg is None for k in exc.keywords):
            note(UNKNOWN, f"the exception's arguments `{_source(exc)}` are unpacked "
                          f"before the raise")
        for argument in arguments:
            found, _ = read_expression(argument, kinds, ns)
            note(found, f"the exception's argument `{_source(argument)}` is evaluated "
                        f"before the raise and may itself raise")
        count, keywords = len(exc.args), [k.arg for k in exc.keywords if k.arg]
    else:
        count, keywords = 0, []
    refusal = constructor_refusal(cls, count, keywords)
    if refusal is not None:
        builtin_only = type(cls) is type and not any(
            k.__module__ != "builtins" and ("__init__" in vars(k) or "__new__" in vars(k))
            for k in cls.__mro__)
        note(HALTS if builtin_only else UNKNOWN, refusal)
    if first is None:
        return ReadRaise(cls, name, getattr(stmt, "lineno", None))
    ordinary = issubclass(cls, (Exception, SystemExit))
    return UnreadRaise(first, halts=level >= HALTS and ordinary)
