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
#: argument types a builtin constructor that checks its arguments
#: inspects with no code of the argument's own (no `__iter__`,
#: `__index__` or `__hash__` written outside the builtins)
_PLAIN_ARGUMENTS = _SCALARS | {bytes}


@dataclass(frozen=True)
class ValueKind:
    """What is known of a value where a path runs: `types`, the exact
    Python types it may have (None when it may be any object), and
    `magnitude`, an upper bound on its absolute value when it is a
    number (`math.inf` when unbounded), and `least`, a lower bound on
    that absolute value (0 when the value may be zero), and `sign`, -1
    when every value is a number below zero, 1 when every value is a
    number above zero, 0 when neither is known."""
    types: "frozenset | None"
    magnitude: float = math.inf
    least: float = 0.0
    sign: int = 0


ANY = ValueKind(None)
_BOOL = ValueKind(frozenset({bool}), 1.0)
_STR = ValueKind(frozenset({str}))


def _union(a: ValueKind, b: ValueKind) -> ValueKind:
    """Intent:
        The kind of a value that is one of two kinds: either type set, the
        larger magnitude bound and the smaller lower bound; any object when
        either may be any object.
    """
    if a.types is None or b.types is None:
        return ANY
    sign = b.sign if not a.types else a.sign if not b.types else (
        a.sign if a.sign == b.sign else 0)
    return ValueKind(a.types | b.types, max(a.magnitude, b.magnitude),
                     min(a.least, b.least), sign)


def _up(bound: float) -> float:
    """Intent:
        The next float above a non-negative bound computed in float arithmetic,
        which rounds to nearest: at least the exact result of the operation
        that gave it. Zero and infinity are exact and stay.
    """
    return math.nextafter(bound, math.inf) if 0.0 < bound < math.inf else bound


def _magnitude(value) -> float:
    """Intent:
        An upper bound on `abs(value)` as a float: the float conversion rounds
        an int to nearest, so a conversion below the int is moved up one float;
        `math.inf` when the bound is past the largest float or the value is no
        number.
    """
    try:
        exact = abs(value)
        found = float(exact)
    except (OverflowError, TypeError, ValueError):
        return math.inf
    if found < exact:
        found = math.nextafter(found, math.inf)
    return found if found <= _FLOAT_MAX else math.inf


def _least(value) -> float:
    """Intent:
        A lower bound on `abs(value)` as a float: a conversion above the int is
        moved down one float, and an int past the largest float is at least
        that float; 0 for anything that is no number.
    """
    try:
        exact = abs(value)
    except (TypeError, ValueError):
        return 0.0
    try:
        found = float(exact)
    except OverflowError:
        return _FLOAT_MAX
    except (TypeError, ValueError):
        return 0.0
    if found != found:
        return 0.0
    if found > exact:
        found = math.nextafter(found, 0.0)
    return found


def kind_of_value(value) -> ValueKind:
    """Intent:
        The kind of one known value: its exact type, and its magnitude and
        sign when it is a number.
    """
    if type(value) in _NUMBERS:
        sign = -1 if value < 0 else 1 if value > 0 else 0
        return ValueKind(frozenset({type(value)}), _magnitude(value), _least(value), sign)
    return ValueKind(frozenset({type(value)}))


_EMPTY = ValueKind(frozenset(), 0.0, math.inf)


def _interval_kind(lo, hi) -> ValueKind:
    """Intent:
        The kind of a number drawn from the interval between `lo` and `hi`: an
        int, float or bool of at most the larger end's magnitude, and at least
        the smaller end's, of the ends' sign, when the interval does not
        contain zero.
    """
    least, sign = 0.0, 0
    if type(lo) in _NUMBERS and type(hi) in _NUMBERS and (lo > 0 or hi < 0):
        least = min(_least(lo), _least(hi))
        sign = 1 if lo > 0 else -1
    return ValueKind(_NUMBERS, max(_magnitude(lo), _magnitude(hi)), least, sign)


def kind_of_bound(bound) -> ValueKind:
    """Intent:
        The kind of a value drawn from a declared bound: the members'
        own types for a finite set, a number of at most the larger end's
        magnitude for an interval (unbounded for an infinite end or a
        named number set), ANY for anything else.

    Notes:
        A `ReachInterval` stands in for an unbounded direction, so it
        is read as unbounded. A missing-value sentinel in a finite set,
        and the missing members and absence a `Domain` admits, are left
        out: derive proves a claim over the real points of its domain,
        and the missing points are executed apart.
    """
    from .domain import Domain, Interval, ReachInterval, is_sentinel
    if isinstance(bound, frozenset):
        found = _EMPTY
        for value in bound:
            if not is_sentinel(value):
                found = _union(found, kind_of_value(value))
        return found
    if isinstance(bound, ReachInterval):
        return ValueKind(_NUMBERS)
    if isinstance(bound, Interval) or (isinstance(bound, tuple) and len(bound) == 2
                                       and all(type(e) in _NUMBERS for e in bound)):
        return _interval_kind(bound[0], bound[1])
    if isinstance(bound, str) and bound in ("Z", "N", "R"):
        return ValueKind(_NUMBERS)
    if isinstance(bound, Domain):
        if bound.base_type not in ("R", "Z", "N") or bound.dims or not bound.pieces:
            return ANY
        found = _EMPTY
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


def _stored_globals(code) -> frozenset:
    """Intent:
        The names the code object, or a function or class nested in it, assigns
        or deletes as module globals (through `global`).
    """
    import dis
    found: set = set()
    pending = [code]
    while pending:
        current = pending.pop()
        for instruction in dis.get_instructions(current):
            if instruction.opname in ("STORE_GLOBAL", "DELETE_GLOBAL"):
                found.add(instruction.argval)
        pending += [c for c in current.co_consts if isinstance(c, types.CodeType)]
    return frozenset(found)


class _Namespace:
    """The names a function's body reads: its own locals (from its code
    object), its module's globals and its builtins. A name the function
    assigns as a global (`rebound`) holds whatever the function last
    stored there, so it is not read off the module."""

    def __init__(self, fn) -> None:
        code = getattr(fn, "__code__", None)
        found_globals = getattr(fn, "__globals__", None)
        self.ok = code is not None and isinstance(found_globals, dict)
        self.globals: dict = found_globals if self.ok else {}
        self.locals = (frozenset(code.co_varnames) | frozenset(code.co_cellvars)
                       | frozenset(code.co_freevars)) if code is not None else frozenset()
        self.rebound = _stored_globals(code) if code is not None else frozenset()
        found = getattr(fn, "__builtins__", None)
        if found is None and self.ok:
            found = self.globals.get("__builtins__", builtins)
        self.builtins = vars(found) if isinstance(found, types.ModuleType) else (found or {})
        # locals bound to a known object on the path (a module imported
        # in the body)
        self.objects: dict = {}

    _MISSING = object()

    def lookup(self, name: str):
        """Intent:
            The object `name` reads: a local the path bound to a known object,
            else a global or builtin outside the function's locals, else
            `_MISSING`.
        """
        if name in self.objects:
            return self.objects[name]
        if not self.ok or name in self.locals or name in self.rebound:
            return self._MISSING
        if name in self.globals:
            return self.globals[name]
        return self.builtins.get(name, self._MISSING)

    def resolve(self, node: ast.AST):
        """Intent:
            The object a bare name or a dotted attribute of a module resolves
            to, or `_MISSING`. An attribute is read only off a plain module
            object that holds it in its own namespace, where reading it runs no
            code.
        """
        if isinstance(node, ast.Name):
            return self.lookup(node.id)
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            if type(base) is types.ModuleType and node.attr in vars(base):
                return vars(base)[node.attr]
        return self._MISSING

    def is_builtin(self, node: ast.AST, name: str) -> bool:
        """Intent:
            Whether `node` is the bare name `name` and resolves to the builtin
            of that name itself.
        """
        return isinstance(node, ast.Name) and node.id == name \
            and self.lookup(name) is getattr(builtins, name)


def _is_numeric(kind: ValueKind) -> bool:
    """Intent:
        Whether every value of the kind is an int, float or bool.
    """
    return kind.types is not None and bool(kind.types) and kind.types <= _NUMBERS


def _converts_to_float(kind: ValueKind) -> bool:
    """Intent:
        Whether an int among the kind's values always converts to float.
    """
    return int not in (kind.types or frozenset()) or kind.magnitude <= _FLOAT_MAX


def _text_level(kind: ValueKind) -> int:
    """Intent:
        How surely `str`, `repr` or `format(v, "")` of a value builds its text:
        TOTAL for a float, bool, str or None, and for an int of finite
        magnitude bound, which has at most 309 digits (Python refuses to
        convert an int of more digits than `sys.get_int_max_str_digits()`,
        which is 4300 by default and never set below 640 except to 0 for no
        limit); HALTS for an unbounded int, whose refusal is a ValueError;
        UNKNOWN for any other object, whose own method runs.
    """
    if not kind.types:
        return UNKNOWN
    if kind.types <= _TEXT:
        return TOTAL
    if kind.types <= _TEXT | {int}:
        return TOTAL if math.isfinite(kind.magnitude) else HALTS
    return UNKNOWN


#: the format specifications of a number read as total: a precision of
#: at most two digits followed by one of the float presentation types
_NUMBER_SPEC = __import__("re").compile(r"\.[0-9]{1,2}[eEfFgG%]")


def _spec_level(kind: ValueKind, spec: str) -> int:
    """Intent:
        How surely `format(v, spec)` builds its text for a constant `spec`: the
        empty spec as `str` (`_text_level`); a spec matching `_NUMBER_SPEC`
        TOTAL for an int, float or bool (an int formatted this way is converted
        to float first, so only one of magnitude at most the largest float);
        UNKNOWN for any other spec or value.
    """
    if spec == "":
        return _text_level(kind)
    if _NUMBER_SPEC.fullmatch(spec) and _is_numeric(kind) and _converts_to_float(kind):
        return TOTAL
    return UNKNOWN


def _percent_fields(text: str) -> "int | None":
    """Intent:
        The number of values a `%`-format string takes when its only
        conversions are `%s`, `%r` and `%a` with no flags, width or precision
        (and `%%`), else None.
    """
    count, at = 0, 0
    while True:
        at = text.find("%", at)
        if at < 0:
            return count
        if at + 1 >= len(text):
            return None
        if text[at + 1] in "sra":
            count += 1
        elif text[at + 1] != "%":
            return None
        at += 2


def _brace_fields(text: str) -> "list | None":
    """Intent:
        The positional indexes a `str.format` string reads, in order, when
        every field is `{}` or `{N}` (not both) with no format specification
        and a conversion of none, `!s`, `!r` or `!a`; None for any other string
        or one the parser refuses.
    """
    import string
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError:
        return None
    out: list = []
    automatic = explicit = False
    for _literal, field, spec, conversion in parsed:
        if field is None:
            continue
        if spec or conversion not in (None, "s", "r", "a"):
            return None
        if field == "":
            automatic = True
            out.append(len(out))
        elif field.isdecimal() and field.isascii():
            explicit = True
            out.append(int(field))
        else:
            return None
    return None if automatic and explicit else out


def _truth_level(kind: ValueKind) -> int:
    """Intent:
        TOTAL when taking the truth of a value of the kind cannot fail (a
        builtin scalar or None), UNKNOWN otherwise.
    """
    return TOTAL if kind.types is not None and kind.types <= _SCALARS else UNKNOWN


def _arithmetic(op: ast.AST, a: ValueKind, b: ValueKind, right: ast.AST):
    """Intent:
        The level and kind of `a <op> b` for two numbers.
    """
    ta, tb = a.types or frozenset(), b.types or frozenset()
    either_float = float in ta or float in tb
    both_int = bool(ta - {float}) and bool(tb - {float})
    out_types = frozenset(({float} if either_float else set())
                          | ({int} if both_int else set()))
    mixes = (float in ta and not _converts_to_float(b)) \
        or (float in tb and not _converts_to_float(a))
    if isinstance(op, (ast.Add, ast.Sub)):
        # |a ± b| >= |a| - |b| and >= |b| - |a|: where one operand is
        # always larger in magnitude than the other can be, the result
        # is never zero
        apart = max(a.least - b.magnitude, b.least - a.magnitude)
        least = math.nextafter(apart, 0.0) if 0.0 < apart < math.inf else 0.0  # :draft
        return (HALTS if mixes else TOTAL), ValueKind(out_types,
                                                       _up(a.magnitude + b.magnitude),
                                                       least)
    if isinstance(op, ast.Mult):
        size = 0.0 if 0.0 in (a.magnitude, b.magnitude) else _up(a.magnitude * b.magnitude)
        return (HALTS if mixes else TOTAL), ValueKind(out_types, size)
    if isinstance(op, ast.Div) and b.least > 0 and _converts_to_float(a) \
            and _converts_to_float(b):
        return TOTAL, ValueKind(frozenset({float}),
                                _up(a.magnitude / b.least) if math.isfinite(a.magnitude)
                                else math.inf)
    if isinstance(op, (ast.Div, ast.FloorDiv, ast.Mod)):
        divisor = right.value if isinstance(right, ast.Constant) else None
        if isinstance(right, ast.UnaryOp) and isinstance(right.op, (ast.USub, ast.UAdd)) \
                and isinstance(right.operand, ast.Constant) \
                and type(right.operand.value) in (int, float):
            # a signed literal: `-1.5`
            literal: "int | float" = right.operand.value  # type: ignore[assignment]
            divisor = -literal if isinstance(right.op, ast.USub) else literal  # :draft
        if type(divisor) in (int, float) and abs(divisor) >= 1 \
                and _converts_to_float(a) and math.isfinite(_magnitude(divisor)):
            # |a / c| <= |a| and |a // c| <= |a| + 1 for |c| >= 1, and
            # `a % c` takes the sign of c with |a % c| <= |c|: the
            # remainder of a negative a by a positive c is close to c
            if isinstance(op, ast.Div):
                size = a.magnitude
            elif isinstance(op, ast.FloorDiv):
                size = _up(a.magnitude + 1.0)
            else:
                size = max(a.magnitude, _magnitude(divisor))
            kind = ValueKind(frozenset({float}) if isinstance(op, ast.Div) else out_types,
                             size)
            return TOTAL, kind
        if type(divisor) is float and divisor != 0 and math.isfinite(divisor) \
                and _converts_to_float(a):
            # a float c nearer zero than 1: the other operand converts to
            # float, and a float division, floor division or remainder by
            # a float that is not zero gives a float (an infinity where
            # the quotient is too large) and never raises. |a % c| <= |c|
            least = _least(divisor)  # :draft
            quotient = _up(a.magnitude / least) if math.isfinite(a.magnitude) else math.inf
            if isinstance(op, ast.Div):
                size = quotient
            elif isinstance(op, ast.FloorDiv):
                size = _up(quotient + 1.0)
            else:
                size = _magnitude(divisor)
            return TOTAL, ValueKind(frozenset({float}), size)
        return HALTS, ValueKind(_NUMBERS)
    return UNKNOWN, ANY


#: the math functions of one number a reading accepts, all returning bool
_MATH_TESTS = ("isnan", "isinf", "isfinite")


def _call_level(node: ast.Call, kinds: dict, ns: _Namespace):
    """Intent:
        `(level, kind)` for a call of one positional argument: `str`, `repr`,
        `ascii` and `abs` that resolve to the builtins, and
        `math.isnan`/`isinf`/`isfinite`, `numpy.isnan` and
        `pandas.isna`/`isnull` on a value of a type they take; UNKNOWN for any
        other call.
    """
    if node.keywords or len(node.args) != 1 or isinstance(node.args[0], ast.Starred):
        return UNKNOWN, ANY
    level, kind = read_expression(node.args[0], kinds, ns)
    for name in ("str", "repr", "ascii"):
        if ns.is_builtin(node.func, name):
            return min(level, _text_level(kind)), _STR
    if ns.is_builtin(node.func, "abs"):
        if _is_numeric(kind):
            return level, ValueKind(kind.types - {bool} | ({int} if bool in kind.types
                                                           else set()), kind.magnitude,
                                    kind.least)
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
    """Intent:
        `(level, kind)` for a comparison chain, read link by link as Python
        runs it: identity tests, equality and membership of builtin scalars,
        and ordering of two numbers or two strings are total; ordering of
        other scalars may raise TypeError; anything else is UNKNOWN. A link
        between two numbers that is false on every value they may hold
        (`_never_holds`) ends the chain, and nothing after it is read.
    """
    level, left = read_expression(node.left, kinds, ns)
    for op, right in zip(node.ops, node.comparators):
        found, value = read_expression(right, kinds, ns)
        level = min(level, found)
        a, b, left = left, value, value
        if _never_holds(op, a, b):  # :draft
            return level, _BOOL
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


def _never_holds(op: ast.AST, a: ValueKind, b: ValueKind) -> bool:  # :draft
    """Intent:
        Whether the ordering `a <op> b` of two numbers is false for every
        value the kinds admit, read from their signs: a value of sign 1 is
        above zero, of sign -1 below it, and a magnitude bound of 0 is zero
        itself. Comparing two such numbers cannot fail, so the link runs
        and is false.
    """
    if not (_is_numeric(a) and _is_numeric(b)):
        return False

    def at_least_zero(k):
        return k.sign == 1 or k.magnitude == 0.0

    def at_most_zero(k):
        return k.sign == -1 or k.magnitude == 0.0

    if isinstance(op, (ast.Lt, ast.LtE)):
        return (at_least_zero(a) and b.sign == -1) or (a.sign == 1 and at_most_zero(b))
    if isinstance(op, (ast.Gt, ast.GtE)):
        return (at_most_zero(a) and b.sign == 1) or (a.sign == -1 and at_least_zero(b))
    return False


def _percent_level(node: ast.BinOp, kinds: dict, ns: "_Namespace"):
    """Intent:
        `"..." % values` for a constant string `_percent_fields` reads: TOTAL
        when the values are a tuple display of exactly that many values, or one
        value of a type other than tuple and dict for one field, and the text
        of each is total (`_text_level`).
    """
    count = _percent_fields(node.left.value)
    if count is None:
        return UNKNOWN, _STR
    right = node.right
    values = right.elts if isinstance(right, ast.Tuple) else [right]
    if any(isinstance(v, ast.Starred) for v in values) or len(values) != count:
        return UNKNOWN, _STR
    level = TOTAL
    for value in values:
        found, kind = read_expression(value, kinds, ns)
        level = min(level, found, _text_level(kind))
    return level, _STR


def _format_call_level(node: ast.Call, kinds: dict, ns: "_Namespace"):
    """Intent:
        `"...".format(values)` for a constant string `_brace_fields` reads,
        given positional values only: TOTAL when every index it reads is among
        the values and the text of every value is total.
    """
    fields = _brace_fields(node.func.value.value)
    if fields is None or node.keywords or any(isinstance(a, ast.Starred) for a in node.args) \
            or any(i >= len(node.args) for i in fields):
        return UNKNOWN, _STR
    level = TOTAL
    for value in node.args:
        found, kind = read_expression(value, kinds, ns)
        level = min(level, found, _text_level(kind))
    return level, _STR


#: types whose own type is `type` itself and whose `__name__` is the
#: builtin descriptor's, so `type(v).__name__` runs no code of theirs
_NAMED_TYPES = _SCALARS | {bytes, tuple, list}


def _passed(test: ast.AST, falsy: bool) -> "tuple | None":
    """Intent:
        `(name, NoneType)` when `test` is `name is None` and the next
        operand of an `or` runs only when it was false (`falsy`), or it
        is `name is not None` and the next operand of an `and` runs only
        when it was true: the next operand sees `name` holding anything
        but None. None for any other test.
    """
    if isinstance(test, ast.Compare) and len(test.ops) == 1 \
            and isinstance(test.left, ast.Name) \
            and isinstance(test.comparators[0], ast.Constant) \
            and test.comparators[0].value is None:
        if isinstance(test.ops[0], ast.Is) and falsy:
            return test.left.id, _NONE
        if isinstance(test.ops[0], ast.IsNot) and not falsy:
            return test.left.id, _NONE
    return None


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
                                                             else set()), kind.magnitude,
                                    kind.least)
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
        if isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, str):
            return _percent_level(node, kinds, ns)
        return UNKNOWN, ANY
    if isinstance(node, ast.BoolOp):
        level, kind = TOTAL, _EMPTY
        scope = dict(kinds)
        for value in node.values:
            part, found = read_expression(value, scope, ns)
            level = min(level, part, _truth_level(found))
            kind = _union(kind, found)
            narrowed = _passed(value, isinstance(node.op, ast.Or))
            if narrowed is not None and narrowed[0] in scope:
                name, drop = narrowed
                held = scope[name]
                if held.types is not None:
                    if held.types <= {drop}:
                        # the name holds only None: no run reaches the
                        # operands after this one
                        break
                    scope[name] = ValueKind(held.types - {drop}, held.magnitude, held.least)
        return level, kind
    if isinstance(node, ast.Compare):
        return _compare_level(node, kinds, ns)
    if isinstance(node, ast.JoinedStr):
        level = TOTAL
        for part in node.values:
            if isinstance(part, ast.Constant):
                continue
            if not isinstance(part, ast.FormattedValue):
                return UNKNOWN, _STR
            spec = part.format_spec
            if spec is None:
                text = ""
            elif isinstance(spec, ast.JoinedStr) and all(
                    isinstance(v, ast.Constant) and isinstance(v.value, str)
                    for v in spec.values):
                text = "".join(v.value for v in spec.values)
            else:
                return UNKNOWN, _STR
            inner, kind = read_expression(part.value, kinds, ns)
            if part.conversion != -1:
                level = min(level, inner, _text_level(kind), TOTAL if text == "" else UNKNOWN)
                continue
            level = min(level, inner, _spec_level(kind, text))
        return level, _STR
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "format" \
                and isinstance(node.func.value, ast.Constant) \
                and isinstance(node.func.value.value, str):
            return _format_call_level(node, kinds, ns)
        return _call_level(node, kinds, ns)
    if isinstance(node, ast.Attribute) and node.attr == "__name__" \
            and isinstance(node.value, ast.Call) and ns.is_builtin(node.value.func, "type") \
            and len(node.value.args) == 1 and not node.value.keywords \
            and not isinstance(node.value.args[0], ast.Starred):
        level, kind = read_expression(node.value.args[0], kinds, ns)
        if kind.types and kind.types <= _NAMED_TYPES:
            return level, _STR
        return UNKNOWN, _STR
    if isinstance(node, (ast.Tuple, ast.List)):
        level = TOTAL
        for element in node.elts:
            if isinstance(element, ast.Starred):
                return UNKNOWN, ANY
            level = min(level, read_expression(element, kinds, ns)[0])
        return level, ValueKind(frozenset({tuple if isinstance(node, ast.Tuple) else list}))
    return UNKNOWN, ANY


def _source(node: ast.AST) -> str:
    """Intent:
        The source text of `node`, or its node type's name when it cannot be
        unparsed.
    """
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _where(node: ast.AST) -> str:
    """Intent:
        ` on line N` for a node that carries a line, empty otherwise.
    """
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
        # :draft
        return (f"`{name}` is made by the metaclass `{type(cls).__name__}`, whose call "
                f"may run code of its own")
    for klass in cls.__mro__:
        if klass is object:
            continue
        if klass.__module__ != "builtins":
            if "__init__" in vars(klass) or "__new__" in vars(klass):
                # :draft
                return (f"building a `{name}` runs a constructor written outside the "
                        f"builtins, which is not shown to be unable to raise")
            continue
        if getattr(builtins, klass.__name__, None) is not klass \
                or klass.__name__ not in BUILTIN_CONSTRUCTORS:
            # :draft
            return (f"building `{name}` runs the constructor of `{klass.__name__}`, "
                    f"which checks its arguments and may raise instead")
        if keywords:
            # :draft
            return (f"`{name}` is built with the keyword argument `{keywords[0]}`, and "
                    f"the constructor of `{klass.__name__}` is not read to accept it")
        most = BUILTIN_CONSTRUCTORS[klass.__name__]
        if most is not None and count > most:
            # :draft
            return (f"`{name}` is built from {count} arguments, and the constructor of "
                    f"`{klass.__name__}` is read only with at most {most}")
    return None


#: builtin exception classes whose `__init__` is `BaseException`'s own
#: and so refuses every keyword argument with a TypeError
KEYWORD_REFUSING = frozenset({
    "BaseException", "Exception", "ArithmeticError", "AssertionError", "BufferError",
    "EOFError", "FloatingPointError", "IndexError", "KeyError", "LookupError",
    "NotImplementedError", "OverflowError", "RecursionError", "RuntimeError",
    "TypeError", "ValueError", "ZeroDivisionError"})


def _refuses_keywords(cls: type) -> bool:  # :draft
    """Intent:
        Whether building `cls` with any keyword argument raises
        `TypeError` once the arguments are evaluated: the class is made by
        `type` itself, no class of its MRO outside the builtins defines
        `__init__` or `__new__`, and the nearest builtin class of its MRO
        is one of `KEYWORD_REFUSING`, whose `__init__` refuses every
        keyword ("TypeError() takes no keyword arguments"). `ImportError`,
        `AttributeError`, `NameError`, `OSError` and the other builtins
        that take keywords of their own are not read.
    """
    if type(cls) is not type or not issubclass(cls, BaseException):
        return False
    for klass in cls.__mro__:
        if klass.__module__ != "builtins":
            if "__init__" in vars(klass) or "__new__" in vars(klass):
                return False
            continue
        return klass.__name__ in KEYWORD_REFUSING \
            and getattr(builtins, klass.__name__, None) is klass
    return False


def _is_builtin_import(found) -> bool:
    """Intent:
        Whether `found` is the builtin `__import__` itself.
    """
    return type(found) is types.BuiltinFunctionType and getattr(found, "__self__", None) \
        is builtins and getattr(found, "__name__", None) == "__import__"


def _loaded(name: str):
    """Intent:
        The module `sys.modules` holds under `name` when it is a plain module
        object, every enclosing package is one too and each is held in its
        package's own namespace; None otherwise.
    """
    parts = name.split(".")
    parent = None
    for at in range(1, len(parts) + 1):
        module = sys.modules.get(".".join(parts[:at]))
        if type(module) is not types.ModuleType:
            return None
        if parent is not None and vars(parent).get(parts[at - 1]) is not module:
            return None
        parent = module
    return parent


def _imported(node: ast.AST, ns: "_Namespace") -> "dict | None":
    """Intent:
        For an `import` statement every name of which binds a module
        already in `sys.modules` (or, for `from m import a`, an
        attribute already in such a module's own namespace), the
        objects it binds by local name: running it looks them up and
        cannot fail. None for any other statement, and for any import
        where the function's `__import__` is not the builtin one.
    """
    if isinstance(node, (ast.Import, ast.ImportFrom)) \
            and not _is_builtin_import(ns.builtins.get("__import__")):
        return None
    if isinstance(node, ast.Import):
        out = {}
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            if _loaded(alias.name) is None:
                return None
            out[alias.asname or top] = sys.modules[alias.asname and alias.name or top]
        return out
    if isinstance(node, ast.ImportFrom) and not node.level and node.module:
        module = sys.modules.get(node.module)
        if type(module) is not types.ModuleType:
            return None
        out = {}
        for alias in node.names:
            if alias.name == "*" or alias.name not in vars(module):
                return None
            out[alias.asname or alias.name] = vars(module)[alias.name]
        return out
    return None


def _real_mro(cls) -> tuple:
    """Intent:
        The classes the class `cls` really inherits from, itself first, read
        from the type and never from an attribute the class or its metaclass
        defines under the name `__mro__`.
    """
    return type.__dict__["__mro__"].__get__(cls)


def _cause_is_read(node: ast.AST, ns: "_Namespace") -> bool:  # :draft
    """Intent:
        Whether evaluating the cause of `raise E from <node>` and attaching
        it cannot fail: `node` is a bare name or a module's attribute that
        resolves where the function is defined to an exception instance, or
        to an exception class that `raise` builds with no argument and whose
        construction from no argument is read (`constructor_refusal`).

    Notes:
        `raise ... from` accepts a cause by its real type, so the instance
        and the class are each judged by `type(...)` and the classes that
        type really inherits from. An object that only names an exception
        class as its `__class__` is no exception, and Python refuses it
        with a TypeError.
    """
    if not isinstance(node, (ast.Name, ast.Attribute)):
        return False
    found = ns.resolve(node)
    kind = type(found)
    if BaseException in _real_mro(kind):
        return True
    return type in _real_mro(kind) and BaseException in _real_mro(found) \
        and constructor_refusal(found, 0, []) is None


def _group_is_read(call: ast.Call, kinds: dict, ns: "_Namespace") -> bool:  # :draft
    """Intent:
        Whether `ExceptionGroup(message, [E1(...), ...])` builds an
        `ExceptionGroup` and cannot fail: no keyword and no unpacking, a
        message that is text and cannot fail to evaluate, and a list or tuple
        display of at least one call, each to a name that resolves to a
        subclass of `Exception` whose construction from its arguments is read
        (`constructor_refusal`) and whose arguments cannot fail to evaluate.
    """
    if call.keywords or len(call.args) != 2 \
            or any(isinstance(a, ast.Starred) for a in call.args):
        return False
    level, message = read_expression(call.args[0], kinds, ns)
    if level < TOTAL or not message.types or not message.types <= {str}:
        return False
    members = call.args[1]
    if not isinstance(members, (ast.List, ast.Tuple)) or not members.elts:
        return False
    for member in members.elts:
        if not isinstance(member, ast.Call) or member.keywords \
                or any(isinstance(a, ast.Starred) for a in member.args) \
                or not isinstance(member.func, (ast.Name, ast.Attribute)):
            return False
        cls = ns.resolve(member.func)
        if not (isinstance(cls, type) and issubclass(cls, Exception)) \
                or constructor_refusal(cls, len(member.args), []) is not None:
            return False
        if any(read_expression(a, kinds, ns)[0] < TOTAL for a in member.args):
            return False
    return True


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
        return UnreadRaise("the function has no Python code object to resolve its names in")  # :draft
    kinds = dict(kinds)
    first: "str | None" = None
    level = TOTAL

    def note(found: int, reason: str) -> None:
        """Intent:
            Record a step's level: the first step below TOTAL gives the reason,
            and the path's level is the lowest seen.
        """
        nonlocal first, level
        if found < TOTAL and first is None:
            first = reason
        level = min(level, found)

    for kind_of_step, node in steps:
        if kind_of_step == "test":
            found, value = read_expression(node, kinds, ns)
            note(min(found, _truth_level(value)),
                 # :draft
                 f"the test `{_source(node)}`{_where(node)} is evaluated before the raise "
                 f"and is not shown to be unable to raise")
            continue
        imported = _imported(node, ns)
        if imported is not None:
            for local, module in imported.items():
                ns.objects[local] = module
                kinds[local] = ANY
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            # the name no longer holds a module the path imported
            ns.objects.pop(node.targets[0].id, None)
            if isinstance(node.value, ast.Lambda):
                # building a lambda evaluates its positional and keyword
                # defaults, and nothing of its body
                lam = node.value.args
                for default in [*lam.defaults, *(d for d in lam.kw_defaults if d is not None)]:
                    found, _ = read_expression(default, kinds, ns)
                    # :draft
                    note(found, f"the default `{_source(default)}`{_where(default)} is "
                                f"evaluated before the raise and is not shown to be unable "
                                f"to raise")
                kinds[node.targets[0].id] = ANY
                continue
            found, value = read_expression(node.value, kinds, ns)
            # :draft
            note(found, f"`{_source(node)}`{_where(node)} runs before the raise and is "
                        f"not shown to be unable to raise")
            kinds[node.targets[0].id] = value
            continue
        # :draft
        note(UNKNOWN, f"`{_source(node)}`{_where(node)} runs before the raise and is not "
                      f"read")

    exc = stmt.exc
    if exc is None:
        return UnreadRaise("a bare `raise` re-raises whatever is being handled")  # :draft
    if stmt.cause is not None and not (isinstance(stmt.cause, ast.Constant)
                                       and stmt.cause.value is None) \
            and not _cause_is_read(stmt.cause, ns):  # :draft
        found, _ = read_expression(stmt.cause, kinds, ns)
        # :draft
        note(min(found, HALTS), f"the cause `{_source(stmt.cause)}` is evaluated before "
                                f"the raise")
    called = exc.func if isinstance(exc, ast.Call) else exc
    if not isinstance(called, (ast.Name, ast.Attribute)):
        return UnreadRaise(f"`{_source(called)}` is not a bare exception name")  # :draft
    name = _source(called)
    if isinstance(called, ast.Name) and called.id in ns.locals:
        # :draft
        return UnreadRaise(f"`{name}` is a variable of the function or of an enclosing "
                           f"one, so the class it holds when the raise runs is not known")
    if isinstance(called, ast.Name) and called.id in ns.rebound:
        # :draft
        return UnreadRaise(f"`{name}` is assigned as a module global by the function or a "
                           f"function nested in it, so the class it holds when the raise "
                           f"runs is not known")
    cls = ns.resolve(called)
    if cls is _Namespace._MISSING:
        # :draft
        return UnreadRaise(f"`{name}` does not resolve to an attribute of a module, a "
                           f"global or a builtin where the function is defined")
    if not (isinstance(cls, type) and issubclass(cls, BaseException)):
        # :draft
        return UnreadRaise(f"`{name}` where the function is defined is not an exception "
                           f"class")
    group = cls is getattr(builtins, "ExceptionGroup", None) and isinstance(exc, ast.Call) \
        and _group_is_read(exc, kinds, ns)  # :draft
    if group:
        count, keywords, known = 2, [], True
    elif isinstance(exc, ast.Call):
        arguments = list(exc.args) + [k.value for k in exc.keywords]
        if any(isinstance(a, ast.Starred) for a in exc.args) \
                or any(k.arg is None for k in exc.keywords):
            # :draft
            note(UNKNOWN, f"the exception's arguments `{_source(exc)}` are unpacked "
                          f"before the raise")
        known = True
        for argument in arguments:
            found, value = read_expression(argument, kinds, ns)
            # :draft
            note(found, f"the exception's argument `{_source(argument)}` is evaluated "
                        f"before the raise and is not shown to be unable to raise")
            known = known and bool(value.types) and value.types <= _PLAIN_ARGUMENTS
        count, keywords = len(exc.args), [k.arg for k in exc.keywords if k.arg]
    else:
        count, keywords, known = 0, [], True
    if not group and keywords and _refuses_keywords(cls):  # :draft
        # the constructor raises TypeError for the keyword once the
        # arguments are evaluated, so the statement raises that
        cls, name, keywords = TypeError, "TypeError", []
    refusal = None if group else constructor_refusal(cls, count, keywords)
    if refusal is not None:
        builtin_only = type(cls) is type and not any(
            k.__module__ != "builtins" and ("__init__" in vars(k) or "__new__" in vars(k))
            for k in cls.__mro__)
        note(HALTS if builtin_only and known else UNKNOWN, refusal)
    if first is None:
        return ReadRaise(cls, name, getattr(stmt, "lineno", None))
    ordinary = issubclass(cls, (Exception, SystemExit))
    return UnreadRaise(first, halts=level >= HALTS and ordinary)
