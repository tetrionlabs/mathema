# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function body read exactly: the mathematics the code states.

A function run on exact inputs (`_exact_side.wrap` with `exact_calls`)
gives an exact result only while every step of its body keeps the
value exact, and the body as Python runs it does not: a float literal
is a double, `int / int` is a double, `math.sqrt` returns a double.
This module builds the function's exact twin, the same body with those
steps read as mathematics:

- a numeric literal is the number written, `0.5` is 1/2 and `2e-9` is
  2/10^9, the reading derive gives the literals of a claim;
- `/` of two exact numbers is their ratio, `**` with a whole exponent
  is exact and with a fractional exponent an exact sympy power;
- `float()` is the identity on an exact number, `math.fabs` its
  absolute value;
- `math.sqrt`, `math.exp`, `math.log`, the trigonometric and
  hyperbolic functions and `math.pi`, `math.e`, `math.tau` give exact
  sympy values when their arguments are exact, a value the claim's
  comparison then settles symbolically (`_exact_side.decide_symbolic`).

Everything else runs as written. A float the body reads from outside
(a module global, a closure, a value a library returns) is a double
with no exact reading, and the twin's result is then inexact at that
point, as `wrap` reports it. `abs` and `sum` are exact on rationals as
Python defines them and are left alone; `min` and `max` pick an
element, a decision (below).

A decision on a number standing for a float is taken twice. The twin
holds an exact number where the computation held a rounded float, and
a decision on it can go the other way: a loop adding 0.1 until it
reaches 1 runs ten times exactly and eleven times in float. So the
function also runs as its shadow (`_shadow_of`): the same body
rewritten with the same decision sites, every step computed as Python
computes it, on the floats the computation held at the point (the
computation's own arguments when a claim evaluation pairs the calls,
`paired`), each decision recorded with its site and its outcome. The
twin then runs, and each decision it takes is checked against the
shadow's next one (`_event`): the same site, the same outcome. A site
is a node of the source (its file, its place, its role), so a loop
revisiting a decision is checked once per pass, and a Python function
the body calls runs as its own shadow inside the caller's, its
decisions part of the same order. The decisions are: a comparison
(`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `is`, `is not`), its
truth; the test of an `if`, `while`, conditional expression,
comprehension condition, `and`, `or`, `not`, `bool`, `any`, `all` or
`filter`, its truth; a subscript, a dict display's or comprehension's
key, `dict()`, `dict.get` and the dict's other key methods, the entry
the key reaches (a key holding a float by the place of the key it
equals); `sorted`, `min`, `max` and `list.sort`, the order or the place
picked; a list's `index`, `count`, `remove` and `in`, the result;
`math.floor`, `math.ceil`, `math.trunc`, `int()`, `round`, `divmod`,
`//`, `%` and `hash`, the value, a number agreeing only when the float
equals the exact value (3.0 and 3 agree; 0.12 and 3/25 do not); and the
body of a `try` or `with` statement, whether it completes or raises,
and what and where. Where every decision agrees and both runs end
alike (returning, or raising the same class at the same line), the
exact run stands. Where a decision differs, the shadow reaches a
decision the twin does not (or the other way), or one run raises where
the other does not, the point is undecided (`NotExact`). A comparison
with a sympy number is settled by sympy (`_exact_side.decide_symbolic`)
and left undecided where sympy cannot; any other decision on a sympy
number, a set holding a number standing for a float (whose order of
iteration rests on its hashes), a `match` on one, and a decision a
builtin takes on one handed to it as a value (`map(hash, xs)`) are
declined. The same decisions on integers are the computation's own
and always agree. Identity against `None`, `True`, `False` or `...` is
no decision on the number. An `assert`'s test is left as written: the
assert raises or not, and a raise is the end of the run the two runs
are compared on. The twin run on its own (`exact_twin`), with no shadow
beside it, declines every decision on a number standing for a float;
inside the body of a `try` whose handlers catch an arithmetic or math
domain error, or of a `with` statement, it also declines any division,
power, `float()` or `math` function of one, and runs the same step on
integers as the computation runs it first, raising the computation's
own error (`10 ** 400 / 1` overflows).

A float with no exact reading (a finite float or a complex number: a
module global, a closure value, a library's or a builtin's result, or
an exact number mixed with one, `0.1 * ONE` or `complex(0, x)`) is a
double, not the number the code states, so no decision is taken on it
outside a shadow run: a comparison, test, rounding, key or order whose
operand is or holds one makes the point undecided, as does a module's
function or a float's own method called on one returning anything but
floats (`math.isfinite(y)`, `y.is_integer()`), and a builtin turning a
number standing for a float into one (`complex`, `sum` with a float).
A value holding one cannot be the run's exact result either (`wrap`).
An infinity and a nan are not rounded values and are decided as ever.

A function `enforce_domain` wraps with no policy on its result is read
as its domain check, a decision taken on the arguments, then the
function it wraps.

Every call the body makes is read too, so no function written in
Python runs as written on an exact number. A Python function the body
calls (by name, through a module, from a container, or handed to a
builtin such as `map` or `sorted`) runs as its own exact twin: its
source scanned with the same refusals, its body rewritten, its globals
read the same way, built once and used however deep the calls go up to
`_MAX_DEPTH` nested calls. A callee with no faithful twin makes the
point undecided (`NotExact`): a function with no source, a lambda
defined outside the body, a decorated function, a library function
(the standard library's, or one installed in site-packages), a method
on an object, a class other than a builtin or an exception, or any
other callable object. A builtin runs as itself, as does a function a
compiled module provides when no exact number is among its arguments;
with one among them the point is undecided. A body that catches the
`NotExact` of a step it took (`except Exception:`) does not hide it:
the run that caught it is undecided all the same.

A value the computation holds as a float is held by the twin as a
Fraction or a sympy number, never a bare int: `float(3)` is
`Fraction(3)`, `math.sqrt(4)` is `Fraction(2)`, `4 ** 0.5` and
`2 ** 3.0` are Fractions, while an int the body or the claim wrote
stays an int. A question about a number's type is then answered as
the computation would: `isinstance(x, float)`, `type(x)`,
`x.__class__` and `type(x) is float` say `float` of such a value and
`int` of an int, so a body branching on the type takes the branch the
computation took.

The reading is only used on a body it follows faithfully. An exact
number stands in for a float, so a construct whose value depends on
the number's Python type or its text rather than its mathematics
would send the exact run down a path the computation did not take,
and a body holding one is refused on its syntax tree before it runs
(`unfaithful`; `exact_callee` then raises `NotExact`, the point
undecided). Refused: a comparison (`is`, `is not`, `==`, `in`, ...)
against a type reached by any path other than its bare builtin name
(`builtins.float`, a module alias of `float`, an imported class: the
twin cannot tell the real `float` from its exact one), `str`/`repr`/
`format`/`ascii`/`bin`/`hex`/`oct`/`id` calls, f-strings, `%`
formatting with a string, `.format(...)`,
`__str__`/`__repr__`/`__format__`, `.hex()`, `float.fromhex`,
`.as_integer_ratio()`, `isinstance`/`issubclass` against `Fraction`,
`Decimal`,
`numbers.Rational` or a sympy class, `math.isclose`, `math.frexp`,
`math.ldexp`, `math.ulp`, `math.nextafter`, and any use of the
`struct` or `ctypes` modules, under any alias and whether imported at
module level or inside the body. Text turned back into a number
(`float(f"{x:.2f}")`, `float(str(x))`, `Decimal(str(x))`) is refused
with the text. An `import math` inside the body reaches the exact
`math` too. A body with no source to scan (built in, a lambda,
defined by `exec`) or a decorated function is refused the same way:
nothing vouches for it. `Fraction(...)` and `Decimal(...)` built from
exact arguments (an int, a string, a `Decimal`) are exact by
construction and read as the computation builds them, and a `Decimal`
stays exact through the operations that do not round (addition,
subtraction, multiplication, comparison); one that rounds to the
decimal context's precision (a division, a square root) leaves the
point undecided (`_without_decimal_rounding`); built from a
float, or from a `Fraction` (which may stand for one), the point is
undecided when the call runs (`_exact_constructor`).

Text whose only reach is an exception's message is not refused: an
f-string, `"..." % x`, `"...".format(...)`, `str(...)` or `repr(...)`
written directly as an argument of the exception constructed by a
`raise` statement (`raise ValueError(f"negative: {x}")`, the callee
resolving to a class deriving from `BaseException`), or as the message
of an `assert`. The twin raises where the computation raises, with the
stand-in's own text in the message, and the message is never compared.
The text is refused as ever when it is wrapped in anything else on the
way to the exception (`raise ValueError("bad: " + f"{x}")`, `raise
make_error(f"{x}")`, `raise ValueError(float(f"{x:.2f}"))`), or when
the body holds a `try` or `with` statement, under which it could catch
its own exception and read the message back.
"""
from __future__ import annotations

import ast
import builtins
import contextlib
import copy
import functools
import inspect
import math
import sys
import textwrap
import threading
import types
import weakref
from fractions import Fraction
from typing import NoReturn

__all__ = ["NotExact", "exact_callee", "exact_twin", "unfaithful"]

#: the names the rewritten body calls for a literal, a division, a
#: floor division, a power and a `.__class__` read, spelled so no body
#: of its own uses them
_LITERAL, _DIV, _POW = "__mathema_literal__", "__mathema_div__", "__mathema_pow__"
_FLOORDIV, _CLASS = "__mathema_floordiv__", "__mathema_class__"
#: the name the rewritten body calls each callee through (`_callee`),
#: the name `NotExact` is bound to in the twin's globals, and the key
#: marking a dict as a twin's globals
_CALLEE, _NOT_EXACT = "__mathema_callee__", "__mathema_not_exact__"
_TWIN_MARK = "__mathema_twin__"
#: the names the rewritten body calls for a comparison's operand, a
#: test, a key, a remainder, and the guard around a body whose errors a
#: handler catches
_OPERAND, _TEST, _KEY = "__mathema_operand__", "__mathema_test__", "__mathema_key__"
_MEMBER = "__mathema_member__"
_MOD, _GUARD = "__mathema_mod__", "__mathema_guard__"
#: the names the rewritten body calls for a comparison of two operands,
#: any other comparison's result, a subscript's container and a dict
#: display or comprehension, and the key marking a dict as a shadow's
#: globals
_COMPARE, _DECIDED = "__mathema_compare__", "__mathema_decided__"
_SUB, _DICT = "__mathema_sub__", "__mathema_dict__"
_SHADOW_MARK = "__mathema_shadow__"

#: the most calls of other functions' twins nested inside one another
#: before the point is left undecided
_MAX_DEPTH = 64

#: each function's reading, built once: `(twin, None)`, or `(None,
#: reason)` for a body that cannot be read faithfully
_TWINS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
#: each function's shadow (`_shadow_of`), built once, None when there
#: is none
_SHADOWS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
#: the source files of the functions read, by which an exception's
#: line in the body is found (`_where`)
_READ_FILES: set = set()


class NotExact(Exception):
    """A step of the exact reading has no exact value: a floor or a
    rounding sympy cannot settle, a transcendental value that is not a
    finite number, a callee the reading cannot follow."""


class _State(threading.local):
    """The exact reading's state on this thread: `depth`, the calls of
    other functions' twins currently nested; `taint`, the reason of the
    first `NotExact` raised in the current run, kept even when the body
    catches the exception; `guard`, the handlers catching an arithmetic
    error (and `with` statements) the run is currently inside
    (`_Guard`); `mode`, which run is going on: None for a twin run on
    its own (every decision on a stand-in declined), `"float"` for a
    shadow run (`log` gathering its decisions), `"exact"` for a twin
    run checked against a shadow run's decisions (`reference`);
    `session`, the claim evaluation pairing the calls of the
    computation with those of the exact reading (`paired`)."""
    depth = 0
    guard = 0
    taint: "str | None" = None
    mode: "str | None" = None
    log: "list | None" = None
    reference: "_Reference | None" = None
    session: "_Session | None" = None


_STATE = _State()


def _not_exact(reason: str) -> NoReturn:
    """Raise `NotExact` with `reason`, recording it as the run's taint
    so a body that catches it is still undecided."""
    if _STATE.taint is None:
        _STATE.taint = reason
    raise NotExact(reason)


def exact_twin(fn):
    """Intent:
        The exact twin of `fn`, a function of the same signature whose
        body is `fn`'s read exactly (the module docstring), or None when
        the body cannot be read faithfully: `fn` is not a plain Python
        function, has no source (built in, a lambda, defined by `exec`),
        is decorated or wraps another function, holds a construct the
        reading refuses (`unfaithful`), or its rewritten body does not
        compile. Built once per function.

    Notes:
        The twin's globals are a copy of `fn`'s with `float`, `round`
        and `pow` shadowed by their exact readings, the `math` module
        (and any of its functions imported by name) by exact versions,
        and `fn`'s own name bound to the twin, so a recursive call is
        read exactly too. A closure's cells are copied in as globals.
    """
    return _reading(fn)[0]


def exact_callee(fn):
    """Intent:
        `fn` as the exact reading runs it: its exact twin, checked
        decision by decision against the function's own float run at
        the same point (`_shadow_of`, the module docstring), or, when no
        faithful twin exists (`exact_twin` is None), a callable that
        raises `NotExact` with the reason, so a point read through it is
        undecided rather than read through a body the reading cannot
        vouch for. The float run is the one a claim evaluation pairs
        with this call (`paired`), else a run on the arguments as the
        computation holds them (`_as_computed`). A run during which any
        step raised `NotExact` raises it, though the body caught it.

    Raises:
        NotExact: no faithful twin, a step of the reading has no exact
            value, or the two runs differ: a decision taken otherwise,
            a decision one run reaches and the other does not, or one
            run raising where the other returns or raises otherwise.
    """
    twin, reason = _reading(fn)
    if twin is None:
        def refused(*args, **kwargs):
            raise NotExact(reason)
        return refused

    @functools.wraps(twin)
    def run(*args, **kwargs):
        session = _STATE.session
        if session is not None and session.mode == "float":
            return session.computed(fn, args, kwargs)
        if session is not None and session.mode == "exact":
            computation = session.take(fn)
        else:
            try:
                floats = (tuple(_as_computed(a) for a in args),
                          {k: _as_computed(v) for k, v in kwargs.items()})
            except OverflowError:
                _not_exact("an argument has no float the computation "
                           "could hold")
            computation = _computed(fn, *floats)
        return _against(twin, computation, args, kwargs)
    return run


# --- the shadow run --------------------------------------------------------

class _Reference:
    """The decisions of a float run (`log`, `(site, outcome)` in the
    order taken), with `at`, the next one the exact run must take."""

    def __init__(self, log: list):
        self.log = log
        self.at = 0


class _Computed:
    """A shadow run of a function at a point: `log`, its decisions in
    order (None when the function has no shadow, so nothing is known
    of them); `value` returned, or `error` raised with `where`, the
    line of the body it was raised at (`_where`)."""

    def __init__(self, log, value=None, error=None, where=None):
        self.log = log
        self.value = value
        self.error = error
        self.where = where


def _as_computed(value):
    """Intent:
        A value the exact reading holds, as the computation held it: a
        number standing for a float as the float nearest it, an int the
        claim wrote (`ExactInt`) as an int, and the elements of a list,
        tuple, set, frozenset, dict or object array the same way;
        anything else as it is.
    """
    from ._exact_side import ExactInt
    if isinstance(value, bool):
        return value
    if isinstance(value, ExactInt):
        return int(value)
    if _stands_for_float(value):
        return float(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return type(value)(_as_computed(v) for v in value)
    if isinstance(value, dict):
        return {_as_computed(k): _as_computed(v) for k, v in value.items()}
    np = sys.modules.get("numpy")
    if np is not None and isinstance(value, np.ndarray) \
            and value.dtype == object:
        try:
            return value.astype(float)
        except (TypeError, ValueError):
            return value
    return value


def _where(error) -> "tuple | None":
    """The place in a body read (a file of `_READ_FILES`) an exception
    was raised: `(file, line)` of the innermost such frame of its
    traceback, None when it passed through none."""
    found = None
    tb = error.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        if code.co_filename in _READ_FILES and code.co_filename != __file__:
            found = (code.co_filename, tb.tb_lineno)
        tb = tb.tb_next
    return found


def _computed(fn, args: tuple, kwargs: dict) -> _Computed:
    """Intent:
        The shadow run of `fn` (`_shadow_of`) on `args` and `kwargs`,
        the floats the computation held, gathering its decisions. A
        function with no shadow runs as written and its decisions are
        unknown (`log` None). A `SystemExit` it raises is kept as the
        raise it is (`_exits.as_raise`).
    """
    from ._exits import as_raise
    shadow = _shadow_of(fn)
    if shadow is None:
        try:
            return _Computed(None, value=fn(*args, **kwargs))
        except SystemExit as e:
            return _Computed(None, error=as_raise(e))
        except Exception as e:
            return _Computed(None, error=e)
    saved = (_STATE.mode, _STATE.log, _STATE.reference, _STATE.guard)
    _STATE.mode, _STATE.log, _STATE.reference, _STATE.guard = (
        "float", [], None, 0)
    log = _STATE.log
    try:
        return _Computed(log, value=shadow(*args, **kwargs))
    except SystemExit as e:
        error = as_raise(e)
        return _Computed(log, error=error, where=_where(error))
    except Exception as e:
        return _Computed(log, error=e, where=_where(e))
    finally:
        _STATE.mode, _STATE.log, _STATE.reference, _STATE.guard = saved


def _raised_words(error, where) -> str:
    at = f" at line {where[1]}" if where else ""
    return f"raised {type(error).__name__}{at}"


def _without_decimal_rounding(twin, args: tuple, kwargs: dict):
    """Intent:
        `twin(*args, **kwargs)` with the decimal context trapping every
        rounding: a `Decimal` operation that would round to the
        context's precision (a division, a square root, a result with
        more digits than the context keeps) raises `decimal.Inexact` or
        `decimal.Rounded` instead of returning a number the mathematics
        does not have. The computation's own run rounds as ever, so the
        two runs then differ and the point is not read exactly.
    """
    import decimal
    with decimal.localcontext() as context:
        context.traps[decimal.Inexact] = True
        context.traps[decimal.Rounded] = True
        return twin(*args, **kwargs)


def _against(twin, computation: _Computed, args: tuple, kwargs: dict):
    """Intent:
        The twin's run on the exact `args` and `kwargs`, each decision
        it takes checked against `computation`'s (`_event`): the twin's
        value, or the exception both runs raised alike (the same class
        at the same line of the body). A `SystemExit` either run raises
        is compared, and raised, as the raise it is
        (`_exits.as_raise`).

    Raises:
        NotExact: the computation's decisions are unknown, a step of the
            reading has no exact value, a decision differs or one run
            reaches it and the other does not, or one run raises where
            the other returns or raises otherwise.
    """
    if computation.log is None:
        _not_exact("the function's float run cannot be followed decision "
                   "by decision")
    saved = (_STATE.mode, _STATE.log, _STATE.reference, _STATE.taint)
    reference = _Reference(computation.log)
    _STATE.mode, _STATE.log, _STATE.reference, _STATE.taint = (
        "exact", None, reference, None)
    from ._exits import as_raise
    raised = None
    try:
        try:
            out = _without_decimal_rounding(twin, args, kwargs)
        except NotExact:
            raise
        except (Exception, SystemExit) as e:
            if _STATE.taint is not None:
                raise NotExact(_STATE.taint) from None
            raised = as_raise(e) if isinstance(e, SystemExit) else e
        if _STATE.taint is not None:
            raise NotExact(_STATE.taint)
        if reference.at < len(reference.log):
            site = reference.log[reference.at][0]
            _not_exact(f"the computation takes a decision at line "
                       f"{_line(site)} the exact reading does not reach")
        if raised is None and computation.error is None:
            return out
        if raised is None:
            _not_exact(f"the computation {_raised_words(computation.error, computation.where)} "
                       f"where the exact reading returns")
        where = _where(raised)
        if computation.error is None:
            _not_exact(f"the exact reading {_raised_words(raised, where)} "
                       f"where the computation returns")
        if type(raised) is not type(computation.error) \
                or where != computation.where:
            _not_exact(f"the exact reading {_raised_words(raised, where)} "
                       f"where the computation "
                       f"{_raised_words(computation.error, computation.where)}")
        raise raised
    finally:
        taint = _STATE.taint
        _STATE.mode, _STATE.log, _STATE.reference = saved[:3]
        _STATE.taint = saved[3] if saved[3] is not None else taint


class _Session:
    """The calls of the functions read that one claim evaluation makes
    (`paired`): `computation` evaluates the claim as the computation
    does, run once, when the exact evaluation first calls a function
    read exactly; in `"float"` mode each call is the computation's own,
    run as its shadow and kept in order (`records`); in `"exact"` mode
    each call of the exact reading takes the record of the same call in
    the same order."""

    def __init__(self, computation):
        self.computation = computation
        self.mode = "exact"
        self.ran = False
        self.records: list = []

    def computed(self, fn, args: tuple, kwargs: dict):
        record = _computed(fn, args, kwargs)
        self.records.append((fn, record))
        if record.error is not None:
            raise record.error
        return record.value

    def take(self, fn) -> _Computed:
        if not self.ran:
            self.ran = True
            self.mode = "float"
            try:
                self.computation()
            except Exception:
                pass
            finally:
                self.mode = "exact"
        if not self.records:
            _not_exact(f"the exact reading calls {_named(fn)} where the "
                       f"computation makes no further call")
        recorded, record = self.records.pop(0)
        if recorded is not fn:
            _not_exact(f"the exact reading calls {_named(fn)} where the "
                       f"computation calls {_named(recorded)}")
        return record

    def complete(self) -> bool:
        """Whether every call the computation made was made again by the
        exact reading."""
        return not self.records


@contextlib.contextmanager
def paired(computation):
    """Intent:
        Pair the calls one claim evaluation makes of functions read
        exactly (`exact_callee`) with the computation's own: yield a
        session (`_Session`) for the exact evaluation; at its first call
        of a function read exactly, `computation`, the claim evaluated
        on the floats the computation held, runs once, each such call
        in it run as its shadow and kept, and each call of the exact
        evaluation is checked against the computation's call in the
        same order. An exception `computation` raises ends it; the
        calls made before it are kept.

    Notes:
        Sessions nest: the previous one is restored on exit.
    """
    session = _Session(computation)
    saved, _STATE.session = _STATE.session, session
    try:
        yield session
    finally:
        _STATE.session = saved


def _line(site) -> object:
    return site[1] if isinstance(site, tuple) and len(site) > 1 else "?"


#: the outcome no other outcome equals: a value whose agreement between
#: the two runs cannot be judged
class _Unjudged:
    def __eq__(self, other):
        return False

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return "a value that cannot be compared"


def _outcome(value):
    """Intent:
        A decision's result as the two runs are compared on it: a number
        (an int, a float, a Fraction, a rational sympy number, a numpy
        number) as `("n", its exact value)`, so the float 3.0 and the
        int 3 agree and the float 0.1 and the Fraction 1/10 do not; a
        float infinity or nan by its text; an irrational sympy number as
        itself, equal to no float; a bool, None, a string or bytes as
        itself; a tuple, list or array element by element; a class, a
        module, a builtin function or an enum member by identity; any
        other value as `_Unjudged`, so the runs never agree on it.
    """
    import enum
    np = sys.modules.get("numpy")
    if value is None or isinstance(value, (bool, str, bytes)):
        return value
    if isinstance(value, int):
        return ("n", Fraction(value))
    if isinstance(value, float):
        return ("n", Fraction(value)) if math.isfinite(value) \
            else ("f", repr(value))
    if isinstance(value, Fraction):
        return ("n", value)
    sympy = sys.modules.get("sympy")
    if sympy is not None and isinstance(value, sympy.Basic):
        if value is sympy.true or value is sympy.false:
            return bool(value)
        if _symbolic_number(value):
            return (("n", Fraction(int(value.p), int(value.q)))
                    if value.is_Rational else ("x", value))
        return _Unjudged()
    if np is not None and isinstance(value, np.generic):
        return _outcome(value.item())
    if np is not None and isinstance(value, np.ndarray):
        return ("a", value.shape,
                tuple(_outcome(v) for v in value.ravel().tolist()))
    if isinstance(value, (tuple, list)):
        return (type(value).__name__, tuple(_outcome(v) for v in value))
    if isinstance(value, slice):
        return ("slice", _outcome(value.start), _outcome(value.stop),
                _outcome(value.step))
    if isinstance(value, (type, types.ModuleType, types.BuiltinFunctionType,
                          enum.Enum)):
        return ("id", id(value))
    return _Unjudged()


def _shown(outcome) -> str:
    """An outcome (`_outcome`) in words."""
    if isinstance(outcome, tuple) and len(outcome) == 2 \
            and outcome[0] == "n":
        return str(outcome[1])
    if isinstance(outcome, tuple) and outcome and outcome[0] == "raised":
        return f"to raise {outcome[1]}"
    return repr(outcome)


def _event(site, outcome) -> None:
    """Intent:
        A decision taken at `site` with `outcome`: in a shadow run kept
        in order; in an exact run checked against the shadow run's
        decision at the same place in the order; in a twin run on its
        own nothing.

    Raises:
        NotExact: in an exact run, the computation took no further
            decision, took it at another site, or reached another
            outcome there.
    """
    mode = _STATE.mode
    if mode == "float":
        _STATE.log.append((site, outcome))
        return
    if mode != "exact":
        return
    reference = _STATE.reference
    if reference.at >= len(reference.log):
        _not_exact(f"the exact reading takes a decision at line "
                   f"{_line(site)} the computation does not reach")
    expected_site, expected = reference.log[reference.at]
    if expected_site != site:
        _not_exact(f"the exact reading takes a decision at line "
                   f"{_line(site)} where the computation takes one at line "
                   f"{_line(expected_site)}")
    if expected != outcome:
        _not_exact(f"at line {_line(site)} the exact reading decides "
                   f"{_shown(outcome)} where the computation decides "
                   f"{_shown(expected)} in float64")
    reference.at += 1


def _decide(site, compute, judged=None):
    """Intent:
        Take the decision `compute` makes at `site` and record its
        outcome (`_event`): the outcome of the value it returns
        (`_outcome`), or of `judged(value)` when given, or `("raised",
        the exception's class name)` when it raises, the exception then
        raised as ever.
    """
    try:
        value = compute()
    except NotExact:
        raise
    except Exception as e:
        _event(site, ("raised", type(e).__name__))
        raise
    _event(site, _outcome(value) if judged is None else judged(value))
    return value


def unfaithful(fn) -> list:
    """Intent:
        The constructs in `fn`'s body the exact reading refuses (the
        module docstring), each as its source text with its line, in
        order; `[]` when there are none, or when the body has no source
        to scan.
    """
    fn = _plain(fn)
    if not isinstance(fn, types.FunctionType):
        return []
    parsed = _parse(fn)
    if parsed is None:
        return []
    src, node, _first = parsed
    return _Scan(src, fn).found_in(node)


def _reading(fn) -> tuple:
    """`(twin, None)`, or `(None, reason)`: the exact twin of `fn` or
    why there is none, cached per function."""
    fn = _plain(fn)
    if not isinstance(fn, types.FunctionType):
        return None, f"{getattr(fn, '__name__', fn)!s} is not a Python function"
    from .analysis import foreign_body
    if foreign_body(fn):
        return None, (f"{fn.__qualname__} stands for a function another "
                      f"frontend read, and its Python source is a wrapper's")
    try:
        return _TWINS[fn]
    except KeyError:
        pass
    guarded = _domain_guarded(fn)
    if guarded is not None:
        check, inner = guarded
        twin, reason = _build(inner, exact=True, decorated=True)
        reading = ((None, reason) if twin is None
                   else (_checked_first(fn, check, twin), None))
    else:
        reading = _build(fn, exact=True)
    try:
        _TWINS[fn] = reading
    except TypeError:
        pass
    return reading


def _shadow_of(fn):
    """Intent:
        The shadow of `fn`: the same body rewritten as the twin is, with
        the same decision sites (`_Exact` with `exact=False`), but every
        step computed as Python computes it, so a run of it is the
        computation's own run with each decision recorded (`_event`).
        A Python function it calls runs as its own shadow
        (`_shadow_callee`). None when `fn` has no twin. Built once per
        function.
    """
    fn = _plain(fn)
    if not isinstance(fn, types.FunctionType):
        return None
    try:
        return _SHADOWS[fn]
    except KeyError:
        pass
    shadow = None
    guarded = _domain_guarded(fn)
    if guarded is not None:
        check, inner = guarded
        if _reading(fn)[0] is not None:
            inner_shadow = _build(inner, exact=False, decorated=True)[0]
            if inner_shadow is not None:
                shadow = _checked_first(fn, check, inner_shadow)
    elif _reading(fn)[0] is not None:
        shadow = _build(fn, exact=False)[0]
    try:
        _SHADOWS[fn] = shadow
    except TypeError:
        pass
    return shadow


def _domain_guarded(fn) -> "tuple | None":
    """`(check, inner)` for a function `enforce_domain` wraps with no
    policy on its result: `check(args, kwargs)` raises where the
    wrapper raises before calling `inner`, the function it wraps; None
    for any other function."""
    check = getattr(fn, "__mathema_domain_check__", None)
    inner = getattr(fn, "__wrapped__", None)
    if check is None or not isinstance(inner, types.FunctionType):
        return None
    return check, inner


def _checked_first(fn, check, body):
    """Intent:
        `fn`, a function `enforce_domain` wraps, as a reading runs it:
        the domain check on the arguments, a decision (`_decide`) whose
        outcome is that it passes or the exception it raises, then
        `body`, the reading of the function it wraps.

    Raises:
        NotExact: in a twin run on its own, an argument holds a number
            standing for a float, whose membership is a decision.
    """
    site = (fn.__code__.co_filename, 0, 0, 0, 0, f"domain {fn.__qualname__}")

    @functools.wraps(body)
    def checked(*args, **kwargs):
        if _STATE.mode is None and (_holds_stand_in(args)
                                    or _holds_stand_in(kwargs)):
            _not_exact(f"the domain check of {fn.__qualname__} on a number "
                       f"standing for a float is not taken exactly")
        _decide(site, lambda: check(args, kwargs) and None)
        return body(*args, **kwargs)
    return checked


def _parse(fn):
    """`(src, FunctionDef, first line)` of `fn`'s source, dedented, or
    None when there is no source or it is not one plain `def`. A
    statement that only calls `sys.exit` (or the interpreter's `exit`
    or `quit`) reads as the `raise SystemExit(...)` it is
    (`_exits.exits_as_raises`), as it does for every other reader of
    the body."""
    from ._exits import exits_as_raises
    try:
        lines, first = inspect.getsourcelines(fn)
    except (OSError, TypeError):
        return None
    src = textwrap.dedent("".join(lines))
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return None
    return src, exits_as_raises(tree.body[0], fn), first


def _plain(fn):
    """`fn` with mathema's own call adapters taken off (`_exits`'s exit
    adapter, a runtime type's realising adapter), each standing for the
    function it wraps; any other wrapper is left as it is."""
    from ._exits import _ExitsAsRaise
    from .runtime_types import _Realising
    while isinstance(fn, (_ExitsAsRaise, _Realising)):
        inner = getattr(fn, "__wrapped__", None)
        if inner is None:
            return fn
        fn = inner
    return fn


def _build(fn, exact: bool, decorated: bool = False) -> tuple:
    """`(twin, None)`, or `(None, reason)` when `fn` has no faithful
    twin; with `exact` False, `(shadow, None)` (`_shadow_of`) of a
    function that has one. With `decorated`, `fn` is the function an
    `enforce_domain` wrapper calls, the one its `def` made, and its
    decorators, already applied outside it, are left out of the
    reading."""
    name = fn.__qualname__
    if getattr(fn, "__wrapped__", None) is not None:
        return None, f"{name} wraps another function"
    parsed = _parse(fn)
    if parsed is None:
        return None, f"the source of {name} cannot be read as one function"
    src, node, first = parsed
    if node.decorator_list and not decorated:
        return None, f"{name} is decorated"
    node.decorator_list = []
    if node.name != fn.__name__:
        return None, f"the source of {name} defines another name"
    found = _Scan(src, fn).found_in(node)
    if found:
        return None, (f"the body of {name} is not read exactly: {found[0]} "
                      f"depends on the number's Python type or text, not "
                      f"its mathematics")
    filename = fn.__code__.co_filename
    node = _Exact(src, fn.__globals__, exact=exact, filename=filename,
                  first=first).visit(node)
    ast.fix_missing_locations(node)
    ast.increment_lineno(node, first - 1)
    module = ast.Module(body=[node], type_ignores=[])
    try:
        compiled = compile(module, filename, "exec")
    except (SyntaxError, ValueError, TypeError):
        return None, f"the exact reading of {name} does not compile"
    _READ_FILES.add(filename)
    env = _globals_of(fn) if exact else _shadow_globals(fn)
    if env is None:
        return None, f"a closure cell of {name} is empty"
    try:
        exec(compiled, env)
    except Exception:
        return None, f"the exact reading of {name} does not define"
    twin = env.get(node.name)
    if not isinstance(twin, types.FunctionType):
        return None, f"the exact reading of {name} does not define"
    if fn.__globals__.get(fn.__name__) is not fn:
        # the def bound its name in the copy; the body reads that name
        # as the module does
        if fn.__name__ in fn.__globals__:
            env[fn.__name__] = fn.__globals__[fn.__name__]
        else:
            del env[fn.__name__]
    twin.__qualname__ = fn.__qualname__
    twin.__module__ = fn.__module__
    twin.__doc__ = fn.__doc__
    twin.__annotations__ = dict(getattr(fn, "__annotations__", {}) or {})
    return twin, None


# --- the constructs the reading refuses ---------------------------------

#: builtins whose value is a number's text or identity
_TEXT_CALLS = frozenset({"str", "repr", "format", "ascii", "bin", "hex",
                         "oct", "id"})
#: attributes whose value is a number's representation
_TEXT_ATTRS = frozenset({"hex", "fromhex", "as_integer_ratio", "format",
                         "__str__", "__repr__", "__format__"})
_MISSING = object()
#: the statements under which a body could catch an exception it raised
#: itself and read its message back
_CATCHING: tuple = (ast.Try, getattr(ast, "TryStar", ast.Try), ast.With,
                    ast.AsyncWith)


def _refused_callables() -> frozenset:
    """The ids of the callables whose value depends on the float
    representation. `Fraction` and `Decimal` are not among them: called
    on exact arguments they build an exact number, and called on
    anything else the reading declines at run time
    (`_exact_constructor`)."""
    import numbers
    values = [numbers.Rational, math.isclose,
              math.frexp, math.ldexp, math.nextafter, float.fromhex,
              float.hex, float.as_integer_ratio]
    if hasattr(math, "ulp"):
        values.append(math.ulp)
    return frozenset(id(v) for v in values)


def _refused_classes() -> frozenset:
    """The ids of the classes a type check of a number cannot ask in the
    reading: an exact number standing for a float is a `Fraction`, so
    `isinstance(x, Fraction)` would be answered otherwise than the
    computation answers it."""
    import decimal
    return _refused_callables() | frozenset(
        id(v) for v in (Fraction, decimal.Decimal))


def _exact_constructor(func):
    """Intent:
        `Fraction` or `Decimal` as the reading calls it: built as the
        computation builds it when every argument is exact by
        construction (an int, a string, a `Decimal`), in the twin's run
        and in its shadow alike.

    Raises:
        NotExact: in a run of the twin, an argument is anything else: a
            float, which has no exact reading beyond its own value, or a
            `Fraction`, which may stand for one.
    """
    import decimal

    def call(*args, **kwargs):
        if _STATE.mode != "float":
            for arg in (*args, *kwargs.values()):
                if isinstance(arg, (int, str, decimal.Decimal)):
                    continue
                _not_exact(f"{_named(func)} is called on a number it does "
                           f"not read exactly")
        return func(*args, **kwargs)
    return call


def _refused_modules() -> frozenset:
    """The ids of the modules that read a float's bits."""
    import ctypes
    import struct
    return frozenset(id(m) for m in (struct, ctypes))


class _Scan(ast.NodeVisitor):
    """The walk over a body that finds the constructs the reading
    refuses, resolving names through the function's globals and the
    builtins so an alias (`from fractions import Fraction as Q`,
    `import struct as s`) is seen for what it is."""

    def __init__(self, src: str, fn):
        self.src = src
        self.env = fn.__globals__
        # what the body's own `import` statements bind, by name
        self.imported: dict = {}
        self.found: list = []
        self.callables = _refused_callables()
        self.classes = _refused_classes()
        self.modules = _refused_modules()
        # the ids of the text constructs whose only reach is an
        # exception's message (`_message_text`)
        self.message_text: set = set()
        # whether the body holds a `try` or `with` statement, under
        # which an exception it raises could be caught and its message
        # read back by the body itself
        self.catching = False

    def found_in(self, node) -> list:
        self.catching = any(isinstance(n, _CATCHING) for n in ast.walk(node))
        self.visit(node)
        return self.found

    def _refuse(self, node) -> None:
        text = ast.get_source_segment(self.src, node) or type(node).__name__
        self.found.append(f"`{text}` (line {getattr(node, 'lineno', '?')})")

    def visit_Import(self, node):
        import importlib
        for alias in node.names:
            try:
                module = importlib.import_module(alias.name.split(".")[0])
            except Exception:
                continue
            self.imported[alias.asname or alias.name.split(".")[0]] = module

    def visit_ImportFrom(self, node):
        import importlib
        if node.level or not node.module:
            return
        try:
            module = importlib.import_module(node.module)
        except Exception:
            return
        for alias in node.names:
            value = getattr(module, alias.name, _MISSING)
            if value is not _MISSING:
                self.imported[alias.asname or alias.name] = value

    def _resolve(self, node):
        if isinstance(node, ast.Name):
            value = self.imported.get(node.id, _MISSING)
            if value is _MISSING:
                value = self.env.get(node.id, _MISSING)
            if value is _MISSING:
                value = getattr(builtins, node.id, _MISSING)
            return value
        if isinstance(node, ast.Attribute):
            base = self._resolve(node.value)
            if base is _MISSING or not isinstance(base, (types.ModuleType, type)):
                return _MISSING
            return getattr(base, node.attr, _MISSING)
        return _MISSING

    def _is_type(self, node) -> bool:
        value = self._resolve(node)
        return value is not _MISSING and isinstance(value, type)

    def _type_nodes(self, node):
        """The nodes of a comparison's side that name a type, looking
        into a tuple, list or set written out (`(float, int)`)."""
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for elt in node.elts:
                yield from self._type_nodes(elt)
        elif self._is_type(node):
            yield node

    def _builtin_type_name(self, node) -> bool:
        """Whether `node` is the bare name of a builtin type, bound by
        neither the module nor the body: the twin reads `float` as its
        exact `float` and every other such name as the class itself, so
        a comparison against it is answered as the computation's."""
        return (isinstance(node, ast.Name)
                and node.id not in self.imported and node.id not in self.env
                and isinstance(getattr(builtins, node.id, None), type))

    def _refused_class(self, node) -> bool:
        value = self._resolve(node)
        if value is _MISSING or not isinstance(value, type):
            return False
        if id(value) in self.classes:
            return True
        return any((getattr(c, "__module__", "") or "").split(".")[0] == "sympy"
                   for c in value.__mro__)

    def _is_text(self, node) -> bool:
        """Whether `node` is a text construct of the kinds an exception
        message may hold: an f-string, `"..." % x`, `"...".format(...)`,
        `str(...)` or `repr(...)` (the builtins, under their own
        names)."""
        if isinstance(node, ast.JoinedStr):
            return True
        if isinstance(node, ast.BinOp):
            return (isinstance(node.op, ast.Mod)
                    and isinstance(node.left, ast.Constant)
                    and isinstance(node.left.value, str))
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                return (func.attr == "format"
                        and isinstance(func.value, ast.Constant)
                        and isinstance(func.value.value, str))
            if isinstance(func, ast.Name):
                return self._resolve(func) in (str, repr)
        return False

    def _message_text(self, call) -> None:
        """Mark the text constructs among the arguments of `call`, the
        constructor of an exception about to be raised, as reaching
        nothing but that exception's message, so the walk does not
        refuse them. `call` must resolve to a class deriving from
        `BaseException`; a call of anything else, or any text in a body
        that could catch its own exception (`catching`), is left to the
        walk and refused as ever."""
        if self.catching or not isinstance(call, ast.Call):
            return
        cls = self._resolve(call.func)
        if cls is _MISSING or not isinstance(cls, type) \
                or not issubclass(cls, BaseException):
            return
        for arg in (*call.args, *(kw.value for kw in call.keywords)):
            if self._is_text(arg):
                self.message_text.add(id(arg))
                if isinstance(arg, ast.Call):
                    self.message_text.add(id(arg.func))

    def visit_Raise(self, node):
        # `raise E(...)`: text in the arguments becomes the message of
        # the exception raised, which the body never reads back
        if node.exc is not None:
            self._message_text(node.exc)
        self.generic_visit(node)

    def visit_Assert(self, node):
        # `assert test, msg`: the message is read only when the assert
        # fails, as the message of the AssertionError raised
        if node.msg is not None and not self.catching \
                and self._is_text(node.msg):
            self.message_text.add(id(node.msg))
            if isinstance(node.msg, ast.Call):
                self.message_text.add(id(node.msg.func))
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if id(node) in self.message_text:
            pass
        elif isinstance(func, ast.Name) and func.id in _TEXT_CALLS:
            self._refuse(node)
        elif isinstance(func, ast.Attribute) and func.attr in _TEXT_ATTRS:
            self._refuse(node)
        elif id(self._resolve(func)) in self.callables:
            self._refuse(node)
        elif isinstance(func, ast.Name) \
                and func.id in ("isinstance", "issubclass") \
                and len(node.args) == 2:
            classes = (node.args[1].elts if isinstance(node.args[1], ast.Tuple)
                       else [node.args[1]])
            if any(self._refused_class(c) for c in classes):
                self._refuse(node)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if id(node) in self.message_text:
            pass
        elif node.attr in _TEXT_ATTRS and isinstance(node.ctx, ast.Load):
            self._refuse(node)
        elif id(self._resolve(node.value)) in self.modules:
            self._refuse(node)
        self.generic_visit(node)

    def visit_Compare(self, node):
        # a type compared by identity is answered only under its bare
        # builtin name; compared by equality or membership, only the
        # real `float` reached another way is indistinguishable from the
        # twin's exact `float`
        identity = any(isinstance(op, (ast.Is, ast.IsNot)) for op in node.ops)
        for side in (node.left, *node.comparators):
            for typed in self._type_nodes(side):
                if self._builtin_type_name(typed):
                    continue
                if identity or self._resolve(typed) is float:
                    self._refuse(node)
                    break
            else:
                continue
            break
        self.generic_visit(node)

    def visit_JoinedStr(self, node):
        if id(node) in self.message_text:
            # the values formatted are still scanned
            self.generic_visit(node)
            return
        self._refuse(node)

    def visit_BinOp(self, node):
        if id(node) in self.message_text:
            pass
        elif isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, (str, bytes)):
            self._refuse(node)
        self.generic_visit(node)


def _globals_of(fn) -> "dict | None":
    """Intent:
        The twin's globals: `fn`'s, copied, with the exact readings in
        place of `float`, `round`, `pow`, the `math` module and any of
        its functions bound by name, the helper names the rewritten
        body calls, the cells of `fn`'s closure as globals, and the
        mark (`_TWIN_MARK`) by which a function the twin defines is
        known to be read already. None when a closure cell is empty.
    """
    env = dict(fn.__globals__)
    env["__builtins__"] = {**builtins.__dict__, "float": ExactFloat,
                           "round": _round, "pow": _pow, "type": _type,
                           "divmod": _divmod, "__import__": _import}
    for name, value in list(env.items()):
        if name == "__builtins__":
            continue
        exact = _exact_global(value)
        if exact is not None:
            env[name] = exact
    freevars = fn.__code__.co_freevars
    if freevars:
        try:
            cells = {name: cell.cell_contents
                     for name, cell in zip(freevars, fn.__closure__ or ())}
        except ValueError:
            return None
        for name, value in cells.items():
            exact = _exact_global(value)
            env[name] = value if exact is None else exact
    env[_LITERAL] = _literal
    env[_DIV] = _div
    env[_POW] = _pow
    env[_CLASS] = _class
    env[_CALLEE] = _callee
    env.update(_deciding_names())
    env[_TWIN_MARK] = True
    return env


def _deciding_names() -> dict:
    """The helpers the twin and the shadow both call at a decision site,
    by the names the rewritten body calls them by."""
    return {_FLOORDIV: _floordiv, _MOD: _mod, _NOT_EXACT: NotExact,
            _OPERAND: _operand, _MEMBER: _member, _TEST: _test,
            _KEY: _key, _GUARD: _Guard, _COMPARE: _compare,
            _DECIDED: _decided, _SUB: _sub, _DICT: _dict_of}


def _shadow_globals(fn) -> "dict | None":
    """Intent:
        The shadow's globals (`_shadow_of`): `fn`'s, copied, with the
        cells of its closure as globals, Python's own builtins and
        operators, the decision helpers the twin calls, the call of
        each callee through `_shadow_callee`, and the mark
        (`_SHADOW_MARK`) by which a function the shadow defines is known
        to be a shadow already. None when a closure cell is empty.
    """
    env = dict(fn.__globals__)
    env["__builtins__"] = builtins.__dict__
    freevars = fn.__code__.co_freevars
    if freevars:
        try:
            env.update({name: cell.cell_contents for name, cell
                        in zip(freevars, fn.__closure__ or ())})
        except ValueError:
            return None
    env[_DIV] = _plain_div
    env[_POW] = pow
    env[_CALLEE] = _shadow_callee
    env.update(_deciding_names())
    env[_SHADOW_MARK] = True
    return env


def _plain_div(a, b):
    """`a / b` as Python computes it."""
    return a / b


# --- the calls the twin's body makes -----------------------------------

#: the C callable types a module or a builtin type provides, run as
#: themselves when no exact number is among their arguments
_C_CALLABLES: tuple = (types.BuiltinFunctionType, types.MethodDescriptorType,
                       types.WrapperDescriptorType, types.MethodWrapperType,
                       types.ClassMethodDescriptorType)

#: the builtin values whose own methods run as themselves (a string's
#: `.format`, a list's `.append`, a dict's `.get`)
_BUILTIN_VALUES: tuple = (str, bytes, bytearray, int, list, tuple, dict, set,
                          frozenset)

#: each Python function's call as the twin makes it, built once
_HELPERS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _own(func) -> bool:
    """A reading this module provides (`ExactFloat`, `_round`, an exact
    `math` function), called as it is."""
    return getattr(func, "__module__", None) == __name__


def _library(fn) -> bool:
    """Intent:
        Whether the Python function `fn` belongs to a library rather
        than the code under test: a module of the standard library, or
        a file installed under `site-packages` or `dist-packages`.
    """
    module = (getattr(fn, "__module__", None) or "").split(".")[0]
    if module in getattr(sys, "stdlib_module_names", ()):
        return True
    path = getattr(getattr(fn, "__code__", None), "co_filename", "") or ""
    parts = path.replace("\\", "/").split("/")
    return "site-packages" in parts or "dist-packages" in parts


def _refuser(reason: str):
    """A callable that leaves the point undecided with `reason`."""
    def refused(*args, **kwargs):
        _not_exact(reason)
    return refused


def _named(func) -> str:
    return getattr(func, "__qualname__", None) or getattr(
        func, "__name__", None) or type(func).__name__


def _holds(value, standing, depth: int = 0) -> bool:
    """Intent:
        Whether `value` is, or holds, a value `standing` picks out:
        itself, or an element of a list, tuple, set or frozenset, a key
        or value of a dict, or an element of an object array, looked
        into up to six levels deep; a container nested deeper counts as
        holding one.
    """
    if standing(value):
        return True
    if depth >= 6:
        return isinstance(value, (list, tuple, set, frozenset, dict))
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_holds(v, standing, depth + 1) for v in value)
    if isinstance(value, dict):
        return any(_holds(k, standing, depth + 1)
                   or _holds(v, standing, depth + 1)
                   for k, v in value.items())
    if isinstance(value, slice):
        return any(_holds(v, standing, depth + 1)
                   for v in (value.start, value.stop, value.step))
    np = sys.modules.get("numpy")
    if np is not None and isinstance(value, np.ndarray) \
            and value.dtype == object:
        return any(_holds(v, standing, depth + 1) for v in value.ravel())
    return False


def _holds_stand_in(value, depth: int = 0) -> bool:
    """Whether `value` is, or holds (`_holds`), an exact number standing
    where the computation had a float (`_stands_for_float`)."""
    return _holds(value, _stands_for_float, depth)


def _holds_symbolic(value) -> bool:
    """Whether `value` is, or holds (`_holds`), a sympy number: one
    Python's own comparisons, hashing and rounding do not read as the
    number it is."""
    return _holds(value, _symbolic_number)


def _floatish(value) -> bool:
    """Whether `value` is, or holds (`_holds`), a float or a number
    standing for one."""
    return _holds(value, lambda v: isinstance(v, float)
                  or _stands_for_float(v))


def _raw(value) -> bool:
    """Whether `value` is a float with no exact reading: a finite float
    (a numpy one included) or a complex number, the double a module
    global, a closure, a library or a builtin gave, or one an exact
    number became when mixed with such a float (`0.1 * ONE`,
    `complex(0, x)`). An infinity and a nan are no rounded value and
    are not raw."""
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, complex):
        return True
    np = sys.modules.get("numpy")
    if np is not None and isinstance(value, np.generic):
        return isinstance(value, np.complexfloating) or (
            isinstance(value, np.floating) and bool(np.isfinite(value)))
    return False


def _holds_raw(value) -> bool:
    """Whether `value` is, or holds (`_holds`), a float with no exact
    reading (`_raw`), a float or complex numpy array included."""
    np = sys.modules.get("numpy")
    if np is not None and isinstance(value, np.ndarray) \
            and value.dtype.kind in "fc":
        return value.size > 0
    return _holds(value, _raw)


def _raw_declined(value, what: str) -> None:
    """Outside a shadow run, leave the point undecided when `value` holds
    a float with no exact reading (`_holds_raw`): `what` on it is a
    decision on a double, not on the number the code states, though the
    float run takes it alike."""
    if _STATE.mode != "float" and _holds_raw(value):
        _not_exact(f"{what} on {value}, a float with no exact reading, is "
                   f"not taken exactly")


def _held(value, what: str) -> None:
    """Leave the point undecided when `value` holds a number standing
    for a float (`_holds_stand_in`) or a float with no exact reading
    (`_raw_declined`): `what`, a decision the reading does not follow
    decision by decision, is declined on it."""
    if _holds_stand_in(value):
        _not_exact(f"{what} on {value}, which stands for a float, is not "
                   f"taken exactly")
    _raw_declined(value, what)


def _symbolic_declined(value, what: str) -> None:
    """In an exact run, leave the point undecided when `value` holds a
    sympy number (`_holds_symbolic`), on which `what`, as Python takes
    it, is not the mathematics, or a float with no exact reading
    (`_raw_declined`)."""
    if _STATE.mode == "exact" and _holds_symbolic(value):
        _not_exact(f"{what} on {value} is not taken exactly")
    _raw_declined(value, what)


def _run_callee():
    """The call of a Python function in the run going on: its shadow in
    a shadow run (`_shadow_callee`), its twin otherwise (`_callee`)."""
    return _shadow_callee if _STATE.mode == "float" else _callee


def _read_args(args: tuple, kwargs: dict) -> tuple:
    """The arguments of a call to a callable the run does not read: each
    Python function among them (a callback, `map`'s function, `sorted`'s
    key) as the run calls it (`_run_callee`), and in a twin each builtin
    function deciding on its argument (`hash`, `any`, `all`, `filter`,
    `sorted`, `min`, `max`) as the twin's reading of it, declining a
    number standing for a float."""
    call = _run_callee()
    twin = _STATE.mode != "float"

    def read(v):
        if isinstance(v, types.FunctionType):
            return call(v)
        if twin and isinstance(v, types.BuiltinFunctionType) \
                and getattr(v, "__self__", None) is builtins \
                and id(v) in _VALUE_DECIDING:
            return _builtin(v)
        return v
    return (tuple(read(a) for a in args),
            {k: read(v) for k, v in kwargs.items()})


def _helper(fn):
    """Intent:
        A Python function the twin's body calls, as the twin calls it:
        its own exact twin, counted against `_MAX_DEPTH`, or a refuser
        when it has no faithful twin. Built once per function.
    """
    try:
        return _HELPERS[fn]
    except (KeyError, TypeError):
        pass
    twin, reason = _reading(fn)
    if twin is None:
        call = _refuser(reason or f"{_named(fn)} is not read exactly")
    else:
        def call(*args, **kwargs):
            if _STATE.depth >= _MAX_DEPTH:
                _not_exact(f"the calls nest deeper than {_MAX_DEPTH}")
            _STATE.depth += 1
            try:
                return twin(*args, **kwargs)
            finally:
                _STATE.depth -= 1
    try:
        _HELPERS[fn] = call
    except TypeError:
        pass
    return call


def _opaque(func, owner=None):
    """Intent:
        A callable the reading does not look into (a module's C
        function, a method of a value of another kind, an exception
        class), run as itself.

    Raises:
        NotExact: an exact number standing for a float is among its
            arguments; or, outside a shadow run, a float with no exact
            reading (`_raw`) is among its arguments or is `owner`, the
            value whose method it is, and the result is anything but
            such floats (`math.isfinite(y)`, `y.is_integer()`): a
            decision on a double the run does not see. An exception
            class is constructed as ever.
    """
    exception = isinstance(func, type) and issubclass(func, BaseException)

    def call(*args, **kwargs):
        if _holds_stand_in(args) or _holds_stand_in(kwargs):
            _not_exact(f"{_named(func)} is called on an exact number it "
                       f"does not read exactly")
        raw = not exception and _STATE.mode != "float" and (
            _raw(owner) or _holds_raw(args) or _holds_raw(kwargs))
        args, kwargs = _read_args(args, kwargs)
        out = func(*args, **kwargs)
        if raw and not _only_raw(out):
            _not_exact(f"{_named(func)} decides on a float with no exact "
                       f"reading")
        return out
    return call


def _only_raw(value) -> bool:
    """Whether `value` is a float or complex number, or a list or tuple
    of nothing else (a float array included): a result carrying no
    decision taken on its arguments."""
    np = sys.modules.get("numpy")
    if isinstance(value, (list, tuple)):
        return all(_only_raw(v) for v in value)
    if np is not None and isinstance(value, np.ndarray):
        return value.dtype.kind in "fc"
    if np is not None and isinstance(value, np.generic):
        return isinstance(value, (np.floating, np.complexfloating))
    return isinstance(value, (float, complex)) and not isinstance(value, bool)


#: the comparisons of two operands, by the symbol `decide_symbolic`
#: reads
_COMPARISONS: dict = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b,
                      "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
                      ">": lambda a, b: a > b, ">=": lambda a, b: a >= b}


def _compare(site, op: str, a, b):
    """Intent:
        `a op b`, a comparison of two operands at `site`, a decision
        (`_decide`): of two numbers either of them a sympy number, as
        sympy settles it (`_exact_side.decide_symbolic`); else as
        Python compares them.

    Raises:
        NotExact: in a twin run on its own, an operand is, or holds, a
            number standing for a float; in an exact run, sympy cannot
            settle the comparison, or a sympy number is held inside an
            operand.
    """
    mode = _STATE.mode
    if mode is None:
        _held(a, "a comparison")
        _held(b, "a comparison")
    elif mode == "exact":
        _raw_declined(a, "a comparison")
        _raw_declined(b, "a comparison")
    if mode == "exact" and (_holds_symbolic(a) or _holds_symbolic(b)):
        if not (_exact(a) and _exact(b)) or isinstance(a, bool) \
                or isinstance(b, bool):
            _not_exact(f"a comparison of {a} and {b} is not taken exactly")
        from ._exact_side import decide_symbolic
        truth = decide_symbolic(op, a, b, 0)
        if truth is None:
            _not_exact(f"sympy cannot decide {a} {op} {b}")
        _event(site, truth)
        return truth
    return _decide(site, lambda: _COMPARISONS[op](a, b))


def _decided(site, value):
    """The result of a comparison chained, or by `in`, `not in`, `is`
    or `is not`, at `site`, a decision (`_event`), as it is; its
    operands are checked on the way in (`_operand`, `_member`)."""
    _event(site, _outcome(value))
    return value


def _operand(value):
    """An operand of a comparison chained, or by `in`, `is`, ..., as it
    is.

    Raises:
        NotExact: in a twin run on its own, the operand is, or holds, a
            number standing for a float (`_holds_stand_in`): the
            comparison could go the other way from the computation's;
            in an exact run, it holds a sympy number, which Python's
            operators do not compare as the number it is.
    """
    if _STATE.mode is None:
        _held(value, "a comparison")
    _symbolic_declined(value, "a comparison")
    return value


def _member(container):
    """The container of `in` or `not in`, as it is: of a dict or a dict's
    view its keys or elements are compared, of a list, tuple, set or
    array its elements (`_operand`), of a string or a range nothing
    standing for a float. In a shadow run, as it is.

    Raises:
        NotExact: outside a shadow run, the container holds a number
            `_operand` declines, or is one whose elements cannot be
            looked at before a membership test without consuming them
            (an iterator, a generator, an object of another kind).
    """
    import collections.abc as abc
    if _STATE.mode == "float":
        return container
    np = sys.modules.get("numpy")
    if isinstance(container, (str, bytes, bytearray, range)):
        return container
    if isinstance(container, dict):
        _operand(list(container))
    elif isinstance(container, (abc.KeysView, abc.ValuesView,
                                abc.ItemsView)):
        _operand(list(container))
    elif isinstance(container, (list, tuple, set, frozenset)) or (
            np is not None and isinstance(container, np.ndarray)):
        _operand(container)
    else:
        _not_exact(f"the elements of {type(container).__name__} cannot be "
                   f"looked at before a membership test")
    return container


def _test(site, value):
    """Intent:
        The value an `if`, `while`, conditional expression, condition of
        a comprehension, `and`, `or` or `not` tests at `site`, as it is,
        its truth a decision (`_decide`).

    Raises:
        NotExact: in a twin run on its own, the value is a number
            standing for a float, or an array holding one: its truth is
            a comparison with zero; in an exact run, it is a sympy
            number or an array holding one.
    """
    np = sys.modules.get("numpy")
    array = np is not None and isinstance(value, np.ndarray)
    if _raw(value) or (array and _holds_raw(value)):
        _raw_declined(value, "a test")
    if _STATE.mode is None:
        if _stands_for_float(value) or (array and _holds_stand_in(value)):
            _not_exact(f"a test of {value}, which stands for a float, is "
                       f"not taken exactly")
        return value
    if _STATE.mode == "exact" and (_symbolic_number(value) or (
            array and _holds_symbolic(value))):
        _not_exact(f"a test of {value} is not taken exactly")
    _decide(site, lambda: bool(value))
    return value


def _key(value):
    """A key of a set display or comprehension, or the subject of a
    `match`, as it is.

    Raises:
        NotExact: the key is, or holds, a number standing for a float:
            its hash and equality are decisions the reading does not
            follow (a set's order of iteration rests on its hashes).
    """
    _held(value, "a key")
    return value


def _key_outcome(container, key):
    """The outcome of a key looked up in `container` (`_event`): in a
    dict, a key holding a float or a number standing for one by the
    place of the key it equals (None when it equals none), so the two
    runs agree when they reach the same entry; any other key by its
    value (`_outcome`)."""
    if isinstance(container, dict) and _floatish(key):
        for i, k in enumerate(container):
            if k is key or k == key:
                return ("at", i)
        return ("at", None)
    return ("k", _outcome(key))


class _Subscripted:
    """The container of a subscript at `site` (`a[k]`, `a[k] = v`,
    `del a[k]`), whose key is a decision (`_key_outcome`)."""

    __slots__ = ("site", "container")

    def __init__(self, site, container):
        self.site = site
        self.container = container

    def _keyed(self, key) -> None:
        if _STATE.mode is None:
            _held(key, "a subscript")
            return
        _symbolic_declined(key, "a subscript")
        _event(self.site, _key_outcome(self.container, key))

    def __getitem__(self, key):
        self._keyed(key)
        return self.container[key]

    def __setitem__(self, key, value):
        self._keyed(key)
        self.container[key] = value

    def __delitem__(self, key):
        self._keyed(key)
        del self.container[key]


def _sub(site, container):
    """The container of a subscript at `site`, its key a decision
    (`_Subscripted`)."""
    return _Subscripted(site, container)


def _dict_of(site, items):
    """Intent:
        A dict display or comprehension at `site`: `items`, each a
        `(key, value)` pair or a 1-tuple of a mapping unpacked (`**m`),
        entered in order, the outcome of each key (`_key_outcome`
        against the entries before it) one decision.

    Raises:
        NotExact: in a twin run on its own, a key holds a number
            standing for a float; in an exact run, a sympy number.
    """
    out: dict = {}
    keys: list = []
    for item in items:
        if len(item) == 1 and not hasattr(item[0], "keys"):
            raise TypeError(f"'{type(item[0]).__name__}' object is not a "
                            f"mapping")
        pairs = ([(k, item[0][k]) for k in item[0].keys()]
                 if len(item) == 1 else [item])
        for k, v in pairs:
            if _STATE.mode is None:
                _held(k, "a key")
            _symbolic_declined(k, "a key")
            keys.append(_key_outcome(out, k))
            out[k] = v
    _event(site, ("dict", tuple(keys)))
    return out


class _Guard:
    """The body of a `try` or `with` statement at `site`: how it ends
    (completed, or the class of the exception it raised and the line,
    `_where`) is a decision (`_event`), so a body that raises in one run
    and not in the other, or raises otherwise, makes the runs differ.
    With `arithmetic` (a handler catching an arithmetic error, or a
    `with`), a step on a number standing for a float in a twin run on
    its own, which could raise in the computation (an overflow, a
    division by a float rounded to zero) where the exact step does not,
    leaves the point undecided (`_guarded_native`)."""

    def __init__(self, site=None, arithmetic: bool = True):
        self.site = site
        self.arithmetic = arithmetic

    def __enter__(self):
        if self.arithmetic:
            _STATE.guard += 1
        return self

    def __exit__(self, kind, error, tb):
        if self.arithmetic:
            _STATE.guard -= 1
        if self.site is not None and _STATE.mode is not None:
            if error is None:
                _event(self.site, None)
            elif isinstance(error, Exception) \
                    and not isinstance(error, NotExact):
                _event(self.site, ("raised", type(error).__name__,
                                   _where(error)))
        return False


def _keyed_by(key):
    """A `key=` of `sorted`, `min`, `max` or `list.sort` in a twin run on
    its own, read exactly, whose results are compared: each declined on
    a number standing for a float (`_held`)."""
    key = _callee(key) if isinstance(key, types.FunctionType) else key

    def keyed(value):
        out = key(value)
        _held(out, "a comparison")
        return out
    return keyed


def _truths(func):
    """`any` or `all` with no site, testing each element (`_held`)."""
    def call(iterable):
        def tested():
            for v in iterable:
                _held(v, "a test")
                yield v
        return func(tested())
    return call


def _filter(function, iterable):
    """`filter` with no site, each value its function returns declined
    on a number standing for a float (`_held`)."""
    def kept(v):
        _held(v, "a test")
        return v
    if function is None:
        return filter(kept, iterable)
    function = _run_callee()(function) \
        if isinstance(function, types.FunctionType) else function
    return filter(lambda v: kept(function(v)), iterable)


def _keyed_result(func):
    """`set`, `frozenset` or `dict` with no site, its keys declined on a
    number standing for a float (`_held`)."""
    def call(*args, **kwargs):
        args, kwargs = _read_args(args, kwargs)
        out = func(*args, **kwargs)
        _held(list(out), "a key")
        return out
    return call


def _int(*args, **kwargs):
    """`int` with no site, declining a number standing for a float (a
    truncation)."""
    if args:
        _decline(args[0])
    return int(*args, **kwargs)


def _bool(*args):
    """`bool` with no site, declining a number standing for a float (a
    test)."""
    for a in args:
        _held(a, "a test")
    return bool(*args)


def _hash(value):
    """`hash` with no site, declining a value holding a number standing
    for a float."""
    _held(value, "a hash")
    return hash(value)


#: the builtins whose decisions on a number standing for a float are
#: declined when called with no site, as the twin calls them
_DECIDING: dict = {id(int): _int, id(bool): _bool, id(hash): _hash,
                   id(any): _truths(any), id(all): _truths(all),
                   id(filter): _filter, id(set): _keyed_result(set),
                   id(frozenset): _keyed_result(frozenset),
                   id(dict): _keyed_result(dict)}
#: the builtins comparing their elements by a `key=`
_KEYED = frozenset(id(f) for f in (sorted, min, max))
#: the builtin functions read as the twin's own when handed to another
#: callable as a value (`map(hash, xs)`)
_VALUE_DECIDING = frozenset(id(f) for f in (hash, any, all, filter, sorted,
                                            min, max))


def _builtin(func):
    """A builtin, run as itself with any Python function among its
    arguments read as the run reads it (`_read_args`), its decisions on
    a number standing for a float declined (`_DECIDING`, a `key=` of
    `sorted`, `min` or `max`)."""
    deciding = _DECIDING.get(id(func))
    if deciding is not None:
        return deciding
    keyed = id(func) in _KEYED

    def call(*args, **kwargs):
        if keyed:
            # the elements compared, gathered once: a number standing
            # for a float may be compared by value, whose order is the
            # mathematics, but not inside a tuple or list, whose order
            # then decides what else comes first
            items = list(args[0]) if len(args) == 1 else list(args)
            _unordered_inside(items)
            args = (items,) if len(args) == 1 else tuple(items)
            if kwargs.get("key") is not None:
                kwargs = {**kwargs, "key": _keyed_by(kwargs["key"])}
        standing = id(func) not in _PASSING and _STATE.mode != "float" \
            and (_holds_stand_in(args) or _holds_stand_in(kwargs))
        args, kwargs = _read_args(args, kwargs)
        out = func(*args, **kwargs)
        if standing and _holds_raw(out):
            _not_exact(f"{_named(func)} turns an exact number into a float "
                       f"with no exact reading")
        return out
    return call


#: the builtins handing on the values they are given, as they are
_PASSING = frozenset(id(f) for f in (
    list, tuple, zip, enumerate, reversed, iter, next, map, filter, print,
    len, isinstance, issubclass, type, getattr, setattr, hasattr, callable,
    range, slice, object))


def _unordered_inside(items) -> None:
    """Leave the point undecided when an element of `items` compared by
    `sorted`, `min`, `max` or `list.sort` is a container holding a
    number standing for a float."""
    for item in items:
        if not _stands_for_float(item) and _holds_stand_in(item):
            _not_exact("an ordering of containers holding a number "
                       "standing for a float is not taken exactly")
    _raw_declined(items, "an ordering")


def _order(site, items: list, key, reverse) -> list:
    """Intent:
        The order `sorted` gives `items` by `key` (the run's reading of
        it, `_run_callee`), as the places of the items in order, a
        decision at `site` (`_decide`).

    Raises:
        NotExact: in an exact run, an item or a key holds a sympy
            number.
    """
    if key is not None and isinstance(key, types.FunctionType):
        key = _run_callee()(key)
    keyed = [key(v) for v in items] if key is not None else items
    _symbolic_declined(keyed, "an ordering")
    return _decide(site, lambda: sorted(range(len(items)),
                                        key=keyed.__getitem__,
                                        reverse=bool(reverse)),
                   judged=lambda places: ("order", tuple(places)))


def _ordered(func, site):
    """Intent:
        `sorted`, `min` or `max` at `site`: the order of the elements, or
        the place of the one picked, a decision (`_order`, `_decide`). A
        call the builtin itself refuses (no elements given, an unknown
        keyword) is passed to it as it is.
    """
    raw = _builtin(func)
    allowed = {"key", "reverse"} if func is sorted else {"key", "default"}

    def call(*args, **kwargs):
        if _STATE.mode is None:
            return raw(*args, **kwargs)
        if not args or set(kwargs) - allowed or (
                func is sorted and len(args) != 1) or (
                len(args) > 1 and "default" in kwargs):
            return func(*args, **kwargs)
        items = list(args[0]) if len(args) == 1 else list(args)
        key = kwargs.get("key")
        if func is sorted:
            places = _order(site, items, key, kwargs.get("reverse", False))
            return [items[i] for i in places]
        if not items:
            if "default" in kwargs:
                _event(site, ("empty",))
                return kwargs["default"]
            return _decide(site, lambda: func(items))
        if key is not None and isinstance(key, types.FunctionType):
            key = _run_callee()(key)
        keyed = [key(v) for v in items] if key is not None else items
        _symbolic_declined(keyed, "an ordering")
        pick = min if func is min else max
        place = _decide(site, lambda: pick(range(len(items)),
                                           key=keyed.__getitem__),
                        judged=lambda i: ("at", i))
        return items[place]
    return call


def _taken(site, kind: str, compute, *operands):
    """Intent:
        A rounding or a test (`kind`) of `operands` at `site`, computed
        by `compute`, a decision (`_decide`).

    Raises:
        NotExact: in a twin run on its own, an operand stands for a
            float or holds one; in an exact run, an operand holds a
            sympy number.
    """
    if _STATE.mode is None:
        for v in operands:
            _held(v, kind)
        return compute()
    for v in operands:
        _symbolic_declined(v, kind)
    return _decide(site, compute)


def _as_float_kind(value, *operands):
    """`value`, an int a floor or quotient of `operands` gave, as the
    Fraction of it when an operand stands for a float: the computation's
    value there is a float."""
    if isinstance(value, int) and not isinstance(value, bool) \
            and any(_stands_for_float(v) for v in operands):
        return Fraction(value)
    return value


def _sited(func, site):
    """Intent:
        `func`, a builtin or `math` function deciding on its argument
        (or the twin's reading of one, `__mathema_native__`), as a
        decision at `site`: `int`, `bool`, `hash`, `round`, `divmod`,
        `math.floor`, `math.ceil`, `math.trunc`, `any`, `all`, `filter`,
        `sorted`, `min`, `max` and `dict`. None for any other callable.
    """
    native = getattr(func, "__mathema_native__", func) if _own(func) else func
    try:
        kind = _SITED_KINDS.get(id(native))
    except TypeError:
        kind = None
    if kind is None or native is not _SITED_NATIVES.get(id(native)):
        return None
    if kind in ("sorted", "min", "max"):
        return _ordered(native, site)
    if kind in ("any", "all"):
        def truths(iterable):
            if _STATE.mode is None:
                return _truths(native)(iterable)
            return native(_test(site, v) for v in iterable)
        return truths
    if kind == "filter":
        def filtered(function, iterable):
            if _STATE.mode is None:
                return _filter(function, iterable)
            if function is None:
                return filter(lambda v: _test(site, v), iterable)
            if isinstance(function, types.FunctionType):
                function = _run_callee()(function)
            return filter(lambda v: _test(site, function(v)), iterable)
        return filtered
    if kind == "dict":
        def made(*args, **kwargs):
            if _STATE.mode is None:
                return _keyed_result(dict)(*args, **kwargs)
            if len(args) > 1:
                return dict(*args, **kwargs)
            items: list = []
            if args:
                source = args[0]
                items = ([(k, source[k]) for k in source.keys()]
                         if hasattr(source, "keys") else
                         [tuple(pair) for pair in source])
            items += list(kwargs.items())
            return _dict_of(site, items)
        return made
    if kind == "divmod":
        def split(a, b):
            q, r = _taken(site, "a quotient", lambda: divmod(a, b), a, b)
            return _as_float_kind(q, a, b), r
        return split
    if kind == "round":
        def rounded(x, ndigits=None):
            return _taken(site, "a rounding",
                          lambda: round(x) if ndigits is None
                          else round(x, ndigits), x)
        return rounded
    if kind in ("floor", "ceil", "trunc"):
        whole = getattr(math, kind)
        return lambda x: _taken(site, "a rounding", lambda: whole(x), x)
    if kind == "int":
        def truncated(*args, **kwargs):
            return _taken(site, "a truncation",
                          lambda: int(*args, **kwargs), *args[:1])
        return truncated
    if kind == "bool":
        return lambda *args: _taken(site, "a test", lambda: bool(*args),
                                    *args)
    return lambda value: _taken(site, "a hash", lambda: hash(value), value)


#: the natives `_sited` takes as a decision, by kind
_SITED_NATIVES: dict = {id(f): f for f in (
    int, bool, hash, round, divmod, any, all, filter, sorted, min, max, dict,
    math.floor, math.ceil, math.trunc)}
_SITED_KINDS: dict = {id(f): k for f, k in (
    (int, "int"), (bool, "bool"), (hash, "hash"), (round, "round"),
    (divmod, "divmod"), (any, "any"), (all, "all"), (filter, "filter"),
    (sorted, "sorted"), (min, "min"), (max, "max"), (dict, "dict"),
    (math.floor, "floor"), (math.ceil, "ceil"), (math.trunc, "trunc"))}


#: the methods of a dict or set whose first argument is a key, and
#: those that may add keys
_KEY_METHODS = frozenset({"get", "pop", "setdefault", "__contains__",
                          "__getitem__", "__delitem__", "__setitem__",
                          "add", "discard", "remove"})
_KEY_ADDING = frozenset({"update", "setdefault", "__setitem__", "add",
                         "__ior__", "__or__", "union", "intersection",
                         "difference", "symmetric_difference",
                         "intersection_update", "difference_update",
                         "symmetric_difference_update", "copy"})
#: the methods of a dict whose key is a decision the runs are compared
#: on (`_key_outcome`)
_DICT_KEYED = frozenset({"get", "pop", "setdefault", "__contains__",
                         "__getitem__", "__delitem__", "__setitem__"})
#: the methods of a list or tuple comparing its elements
_SEARCHING = frozenset({"index", "count", "remove", "__contains__"})


def _method(func, site=None):
    """Intent:
        A builtin value's own method (`_BUILTIN_VALUES`), run as itself.
        At a site, outside a twin run on its own, a dict's key
        (`_DICT_KEYED`), a list's or tuple's search and `list.sort` are
        decisions (`_key_outcome`, `_decide`, `_order`); otherwise its
        decisions on a number standing for a float are declined: a key
        of a dict or set, a search of a list, a `key=` of `list.sort`.

    Raises:
        NotExact: a declined decision, or in an exact run a sympy number
            in a decision Python does not take as the number it is.
    """
    owner = func.__self__
    name = func.__name__
    keyed = isinstance(owner, (dict, set, frozenset))
    searched = isinstance(owner, (list, tuple)) and name in _SEARCHING

    def call(*args, **kwargs):
        followed = site is not None and _STATE.mode is not None
        if followed and isinstance(owner, dict) and name in _DICT_KEYED \
                and args:
            _symbolic_declined(args[0], "a key")
            _event(site, _key_outcome(owner, args[0]))
            args, kwargs = _read_args(args, kwargs)
            return func(*args, **kwargs)
        if followed and searched:
            _symbolic_declined(args, "a search")
            _symbolic_declined(owner, "a search")
            if name == "remove" and isinstance(owner, list) and args:
                place = _decide(site, lambda: owner.index(*args))
                del owner[place]
                return None
            return _decide(site, lambda: func(*args, **kwargs))
        if followed and name == "sort" and isinstance(owner, list) \
                and not args and not set(kwargs) - {"key", "reverse"}:
            places = _order(site, list(owner), kwargs.get("key"),
                            kwargs.get("reverse", False))
            owner[:] = [owner[i] for i in places]
            return None
        if keyed and name in _KEY_METHODS and args:
            _held(args[0], "a key")
        if searched:
            _held(args, "a search")
            _held(owner, "a search")
        if name == "sort":
            _unordered_inside(owner)
            if kwargs.get("key") is not None:
                kwargs = {**kwargs, "key": _keyed_by(kwargs["key"])}
        args, kwargs = _read_args(args, kwargs)
        out = func(*args, **kwargs)
        if keyed and name in _KEY_ADDING:
            _held(list(owner), "a key")
            if isinstance(out, (dict, set, frozenset)):
                _held(list(out), "a key")
        return out
    return call


def _callee(func, site=None):
    """Intent:
        `func` as the twin's body calls it: at a site, a builtin or
        `math` function deciding on its argument as that decision
        (`_sited`); a reading of this module as itself, a `math`
        function as its exact version, a function the twin defined as
        itself (its code is already the reading), any other Python
        function as its exact twin (`_helper`), a builtin or a builtin
        class as itself (`_builtin`), a builtin value's method as itself
        (`_method`), a C function of a module and an exception class as
        themselves while no exact number is among their arguments
        (`_opaque`). A library function, a bound method, any other class
        or callable object leaves the point undecided when called.
    """
    if site is not None:
        sited = _sited(func, site)
        if sited is not None:
            return sited
    if _own(func):
        return func
    try:
        exact = _MATH_FUNCTIONS.get(id(func))
    except TypeError:
        exact = None
    if exact is not None and _MATH_NATIVE.get(id(func)) is func:
        return exact
    name = _named(func)
    if isinstance(func, types.FunctionType):
        if func.__globals__.get(_TWIN_MARK) is True:
            return func
        if _library(func):
            return _refuser(f"{name} is a library function the reading "
                            f"does not follow")
        return _helper(func)
    if isinstance(func, types.MethodType):
        return _refuser(f"{name} is a method on an object the reading "
                        f"does not follow")
    if isinstance(func, type):
        if func.__module__ == "builtins":
            return _builtin(func)
        if func is Fraction or func.__name__ == "Decimal" \
                and func.__module__ in ("decimal", "_decimal"):
            return _exact_constructor(func)
        if issubclass(func, BaseException):
            return _opaque(func)
        return _refuser(f"{name} is a class the reading does not follow")
    if isinstance(func, types.BuiltinFunctionType) \
            and getattr(func, "__self__", None) is builtins:
        return _builtin(func)
    if isinstance(func, _C_CALLABLES):
        owner = getattr(func, "__self__", None)
        if _stands_for_float(owner):
            return _refuser(f"{name} is a method of an exact number")
        if isinstance(owner, _BUILTIN_VALUES):
            return _method(func, site)
        return _opaque(func, owner)
    return _refuser(f"{name} is a callable object the reading does not "
                    f"follow")


def _shadow_callee(func, site=None):
    """Intent:
        `func` as the shadow's body calls it (`_shadow_of`): at a site, a
        builtin or `math` function deciding on its argument as that
        decision (`_sited`), as in the twin; a Python function the code
        under test defines as its own shadow, so its decisions are part
        of the run; a builtin, a builtin value's method and a module's C
        function as themselves with any Python function among their
        arguments read as shadows (`_builtin`, `_method`, `_opaque`);
        anything else as it is.
    """
    if site is not None:
        sited = _sited(func, site)
        if sited is not None:
            return sited
    if isinstance(func, types.FunctionType):
        if func.__globals__.get(_SHADOW_MARK) is True or _own(func) \
                or _library(func):
            return func
        shadow = _shadow_of(func)
        return func if shadow is None else shadow
    if isinstance(func, type):
        return _builtin(func) if func.__module__ == "builtins" else func
    if isinstance(func, types.BuiltinFunctionType) \
            and getattr(func, "__self__", None) is builtins:
        return _builtin(func)
    if isinstance(func, _C_CALLABLES):
        owner = getattr(func, "__self__", None)
        if isinstance(owner, _BUILTIN_VALUES):
            return _method(func, site)
        return _opaque(func)
    return func


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    """`__import__` as the twin's body sees it: an `import math` (or
    `from math import sqrt`) inside the body reaches the exact `math`
    the globals already hold, every other module itself."""
    module = builtins.__import__(name, globals, locals, fromlist, level)
    return _MATH if module is math else module


def _exact_global(value):
    """The exact reading of a global: the `math` module as `_ExactMath`,
    one of its functions as its exact version; None for anything else."""
    if value is math:
        return _MATH
    try:
        return _MATH_FUNCTIONS.get(id(value)) if callable(value) else None
    except TypeError:
        return None


class _Exact(ast.NodeTransformer):
    """The rewrite of a body into its twin, or with `exact` False into
    its shadow (`_shadow_of`). Both: each `/`, `//`, `%` and `**` (and
    `/=`, `//=`, `%=`, `**=`) a call of the run's operator, each call
    made through the run's callee (`_callee`, `_shadow_callee`) with
    its site, each `try` letting a `NotExact` through its handlers,
    annotations dropped so they are not evaluated. Each decision is a
    call naming its site (the source file, the node's place in it and
    its role), the same in the twin and the shadow, so the two runs'
    decisions are compared in order (`_event`): a comparison of two
    operands (`_compare`), any other comparison's result (`_decided`,
    its operands through `_operand`, the container of `in` through
    `_member`, and no decision for `is` against `None`, `True`, `False`
    or `...`), the value an `if`, `while`, conditional expression,
    comprehension condition, `and`, `or` or `not` tests (`_test`), a
    subscript (`_sub`), a dict display or comprehension (`_dict_of`),
    `//` and `%` (`_floordiv`, `_mod`), and the body of a `try` or
    `with` statement (`_Guard`, marking a handler catching an
    arithmetic error). A set display's or comprehension's keys and a
    `match` subject are declined on a number standing for a float
    (`_key`). The twin only: each float literal a call reading its
    source text, each `.__class__` read a call answering the type as
    the computation would. An `assert`'s test is left as written: it
    raises or not, and a raise leaves the point undecided."""

    def __init__(self, src: str, env: "dict | None" = None,
                 exact: bool = True, filename: str = "<body>",
                 first: int = 1):
        self.src = src
        self.env = env or {}
        self.exact = exact
        self.filename = filename
        self.offset = first - 1
        # inside an assert's test, whose decisions are left as written
        self.asserting = False

    def _wrap(self, name: str, node):
        return ast.copy_location(ast.Call(
            func=ast.Name(name, ast.Load()), args=[node], keywords=[]), node)

    def _call(self, name: str, at, *args):
        return ast.copy_location(ast.Call(
            func=ast.Name(name, ast.Load()), args=list(args), keywords=[]),
            at)

    def _site(self, node, role: str):
        """The constant naming a decision site: the source file, the
        node's first and last line and column, and the role."""
        line = getattr(node, "lineno", 0) or 0
        end = getattr(node, "end_lineno", None) or line
        return ast.Constant((self.filename, line + self.offset,
                             getattr(node, "col_offset", 0) or 0,
                             end + self.offset,
                             getattr(node, "end_col_offset", 0) or 0, role))

    def _decides(self) -> bool:
        return not self.asserting

    def visit_Assert(self, node):
        self.asserting = True
        node.test = self.visit(node.test)
        self.asserting = False
        if node.msg is not None:
            node.msg = self.visit(node.msg)
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if not self._decides():
            return node
        sides = [node.left, *node.comparators]

        def singleton(n) -> bool:
            return isinstance(n, ast.Constant) and (
                n.value is None or n.value is True or n.value is False
                or n.value is Ellipsis)

        def identity_only(i: int) -> bool:
            # every operator beside operand i is `is`/`is not` against
            # a singleton constant
            pairs = []
            if i > 0:
                pairs.append((node.ops[i - 1], sides[i - 1]))
            if i < len(node.ops):
                pairs.append((node.ops[i], sides[i + 1]))
            return all(isinstance(op, (ast.Is, ast.IsNot)) and singleton(o)
                       for op, o in pairs)

        def container_only(i: int) -> bool:
            # operand i is only ever the container of `in`/`not in`
            return i > 0 and isinstance(node.ops[i - 1], (ast.In, ast.NotIn)) \
                and i == len(node.ops)

        if all(singleton(s) or identity_only(i) for i, s in enumerate(sides)):
            return node
        site = self._site(node, "compare")
        if len(node.ops) == 1 and type(node.ops[0]) in _ORDERINGS:
            return self._call(_COMPARE, node, site,
                              ast.Constant(_ORDERINGS[type(node.ops[0])]),
                              node.left, node.comparators[0])
        wrapped = [s if singleton(s) or identity_only(i)
                   else self._wrap(_MEMBER, s) if container_only(i)
                   else self._wrap(_OPERAND, s)
                   for i, s in enumerate(sides)]
        node.left, node.comparators = wrapped[0], wrapped[1:]
        return self._call(_DECIDED, node, site, node)

    def _tested(self, node):
        if not self._decides():
            return node
        return self._call(_TEST, node, self._site(node, "test"), node)

    def visit_If(self, node):
        self.generic_visit(node)
        node.test = self._tested(node.test)
        return node

    visit_While = visit_If
    visit_IfExp = visit_If

    def visit_comprehension(self, node):
        self.generic_visit(node)
        node.ifs = [self._tested(t) for t in node.ifs]
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        node.values = [*(self._tested(v) for v in node.values[:-1]),
                       node.values[-1]]
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not):
            node.operand = self._tested(node.operand)
        return node

    def _keyed(self, node):
        return self._wrap(_KEY, node) if self._decides() else node

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if self._decides():
            node.value = self._call(_SUB, node.value,
                                    self._site(node, "subscript"), node.value)
        return node

    def visit_Dict(self, node):
        self.generic_visit(node)
        if not self._decides():
            return node
        items = [ast.Tuple([v] if k is None else [k, v], ast.Load())
                 for k, v in zip(node.keys, node.values)]
        return self._call(_DICT, node, self._site(node, "dict"),
                          ast.List(items, ast.Load()))

    def visit_Set(self, node):
        self.generic_visit(node)
        node.elts = [self._keyed(e) for e in node.elts]
        return node

    def visit_DictComp(self, node):
        self.generic_visit(node)
        if not self._decides():
            return node
        pairs = ast.copy_location(ast.ListComp(
            elt=ast.Tuple([node.key, node.value], ast.Load()),
            generators=node.generators), node)
        return self._call(_DICT, node, self._site(node, "dict"), pairs)

    def visit_SetComp(self, node):
        self.generic_visit(node)
        node.elt = self._keyed(node.elt)
        return node

    def visit_Match(self, node):
        self.generic_visit(node)
        node.subject = self._wrap(_KEY, node.subject)
        return node

    def _guarded(self, body: list, at, arithmetic: bool) -> list:
        return [ast.copy_location(ast.With(
            items=[ast.withitem(context_expr=self._call(
                _GUARD, at, self._site(at, "guard"),
                ast.Constant(arithmetic)), optional_vars=None)],
            body=body), at)]

    def _catches_arithmetic(self, handler) -> bool:
        """Whether `handler` could catch an arithmetic error or a math
        domain error: a bare `except`, a class those errors derive from,
        or a name the walk cannot resolve."""
        if handler.type is None:
            return True
        kinds = (handler.type.elts if isinstance(handler.type, ast.Tuple)
                 else [handler.type])
        for kind in kinds:
            cls = _resolve_in(kind, self.env)
            if not isinstance(cls, type):
                return True
            if any(issubclass(e, cls) for e in _ARITHMETIC_ERRORS):
                return True
        return False

    def visit_With(self, node):
        self.generic_visit(node)
        node.body = self._guarded(node.body, node, True)
        return node

    visit_AsyncWith = visit_With

    def visit_Call(self, node):
        self.generic_visit(node)
        node.func = self._call(_CALLEE, node.func, node.func,
                               self._site(node, "call"))
        return node

    def visit_Try(self, node):
        self.generic_visit(node)
        arithmetic = any(self._catches_arithmetic(h) for h in node.handlers)
        node.body = self._guarded(node.body, node, arithmetic)
        # `except NotExact: raise` ahead of the body's own handlers
        node.handlers.insert(0, ast.copy_location(ast.ExceptHandler(
            type=ast.Name(_NOT_EXACT, ast.Load()), name=None,
            body=[ast.Raise(exc=None, cause=None)]), node))
        return node

    visit_TryStar = visit_Try

    def visit_Constant(self, node):
        value = node.value
        if self.exact and isinstance(value, float) and math.isfinite(value):
            text = ast.get_source_segment(self.src, node) or repr(value)
            return ast.copy_location(ast.Call(
                func=ast.Name(_LITERAL, ast.Load()),
                args=[ast.Constant(text)], keywords=[]), node)
        if self.exact and isinstance(value, float) and math.isinf(value):
            # a literal written past float range (`1e309`) parses to an
            # infinity; as written it is the finite number it states
            text = ast.get_source_segment(self.src, node)
            try:
                Fraction(text or "")
            except (ValueError, ZeroDivisionError):
                return node
            return ast.copy_location(ast.Call(
                func=ast.Name(_LITERAL, ast.Load()),
                args=[ast.Constant(text)], keywords=[]), node)
        return node

    def _operator(self, op, left, right, at):
        name = _operator_name(op)
        if name is None:
            return None
        args = [left, right]
        if name in (_FLOORDIV, _MOD):
            args.append(self._site(at, "operator"))
        return ast.Call(func=ast.Name(name, ast.Load()), args=args,
                        keywords=[])

    def visit_BinOp(self, node):
        self.generic_visit(node)
        call = self._operator(node.op, node.left, node.right, node)
        return node if call is None else ast.copy_location(call, node)

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        read = copy.deepcopy(node.target)
        read.ctx = ast.Load()
        call = self._operator(node.op, read, node.value, node)
        if call is None:
            return node
        return ast.copy_location(
            ast.Assign(targets=[node.target], value=call), node)

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if not self.exact or node.attr != "__class__" \
                or not isinstance(node.ctx, ast.Load):
            return node
        return ast.copy_location(ast.Call(
            func=ast.Name(_CLASS, ast.Load()),
            args=[node.value], keywords=[]), node)

    def visit_arg(self, node):
        node.annotation = None
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.returns = None
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


#: the comparisons of two operands taken as one decision (`_compare`),
#: by the symbol it reads
_ORDERINGS: dict = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<",
                    ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}


#: the errors a float step raises where its exact step may not (or the
#: other way): an overflow, a division by a float rounded to zero, a
#: math domain error
_ARITHMETIC_ERRORS = (OverflowError, ZeroDivisionError, FloatingPointError,
                      ValueError)


def _resolve_in(node, env: dict):
    """The value an exception name in a handler refers to, through
    `env` and the builtins (a dotted name through its module), or None
    when it cannot be resolved."""
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        return getattr(builtins, node.id, None)
    if isinstance(node, ast.Attribute):
        base = _resolve_in(node.value, env)
        return None if base is None else getattr(base, node.attr, None)
    return None


def _operator_name(op) -> "str | None":
    if isinstance(op, ast.Div):
        return _DIV
    if isinstance(op, ast.FloorDiv):
        return _FLOORDIV
    if isinstance(op, ast.Pow):
        return _POW
    if isinstance(op, ast.Mod):
        return _MOD
    return None


# --- the exact readings the twin's body calls --------------------------

def _sympy():
    import sympy
    return sympy


def _is_rational(value) -> bool:
    """An int (a bool included, as Python's arithmetic reads it) or a
    Fraction."""
    return isinstance(value, (int, Fraction))


def _is_symbolic(value) -> bool:
    """A sympy expression, when sympy has been imported at all (no value
    is one otherwise)."""
    sympy = sys.modules.get("sympy")
    return sympy is not None and isinstance(value, sympy.Basic)


def _symbolic_number(value) -> bool:
    """A sympy expression that is a finite number holding no float."""
    from ._exact_side import symbolic_number
    return symbolic_number(value)


def _exact(value) -> bool:
    return _is_rational(value) or _symbolic_number(value)


def _sympify(value):
    """An exact number as a sympy number."""
    sympy = _sympy()
    if _is_symbolic(value):
        return value
    q = Fraction(int(value) if isinstance(value, bool) else value)
    return sympy.Rational(q.numerator, q.denominator)


def _settled(value):
    """A sympy result of a step the computation returns a float from (a
    root, a power, a transcendental value) as the reading keeps it: a
    Rational, an Integer included, as a Fraction, any other finite
    number as itself.

    Raises:
        NotExact: the result is not a finite number, or holds a float.
    """
    if not _symbolic_number(value):
        _not_exact(f"{value} has no exact value")
    if value.is_Rational:
        return Fraction(int(value.p), int(value.q))
    return value


def _truth(relational) -> bool:
    """A sympy comparison of two numbers as a bool.

    Raises:
        NotExact: sympy left the comparison open.
    """
    sympy = _sympy()
    if relational is sympy.true or relational is True:
        return True
    if relational is sympy.false or relational is False:
        return False
    _not_exact(f"sympy cannot decide {relational}")


def _literal(text: str):
    """A numeric literal as written: an int, or the decimal as a
    Fraction (`0.1` is 1/10, `2e-9` is 2/10^9)."""
    text = text.replace("_", "")
    try:
        return int(text)
    except ValueError:
        return Fraction(text)


def _decline(*operands) -> None:
    """Leave the point undecided when any of `operands` stands for a
    float (`_stands_for_float`): the decision a step makes on it (a
    floor, a remainder, a rounding) could go the other way from the
    computation's, whose float was rounded."""
    for value in operands:
        if _stands_for_float(value):
            _not_exact(f"a decision on {value}, which stands for a float, "
                       f"is not taken exactly")
        _raw_declined(value, "a decision")


def _guarded_native(native, *operands) -> None:
    """Under a handler that catches an arithmetic error (`_Guard`): leave
    the point undecided when an operand stands for a float, and run the
    step on integer operands as the computation does, so it raises the
    computation's own error (an overflow) where the computation does.
    In a run checked against a shadow run, a step on a number standing
    for a float is taken exactly: how the guarded body ends is the
    decision the runs are compared on (`_Guard`)."""
    if not _STATE.guard:
        return
    if _STATE.mode is None:
        _decline(*operands)
    if not any(_stands_for_float(v) for v in operands):
        native(*operands)


def _div(a, b):
    """`a / b`: the ratio of two exact numbers, else Python's division."""
    _guarded_native(lambda x, y: x / y, a, b)
    if _is_rational(a) and _is_rational(b):
        return Fraction(a) / Fraction(b)
    if _exact(a) and _exact(b):
        divisor = _sympify(b)
        if divisor.is_zero:
            raise ZeroDivisionError("division by zero")
        return _settled(_sympify(a) / divisor)
    return a / b


def _floordiv(a, b, site=None):
    """`a // b` at `site`, a decision (`_taken`): Python's floor
    division, of two ints an int, of a number standing for a float the
    Fraction of the whole number, as the computation's is a float.

    Raises:
        NotExact: an operand `_taken` declines.
    """
    return _as_float_kind(
        _taken(site, "a floor division", lambda: a // b, a, b), a, b)


def _mod(a, b, site=None):
    """`a % b` at `site`, a decision (`_taken`): Python's remainder, of
    two ints an int, and text formatting as ever when `a` is a string.

    Raises:
        NotExact: an operand `_taken` declines.
    """
    if isinstance(a, (str, bytes)):
        return a % b
    return _taken(site, "a remainder", lambda: a % b, a, b)


def _divmod(a, b):
    """`divmod(a, b)`: Python's quotient and remainder, of two ints two
    ints.

    Raises:
        NotExact: an operand stands for a float.
    """
    _decline(a, b)
    return divmod(a, b)


def _pow(a, b, mod=None):
    """`a ** b`: exact for an exact base and a whole exponent (an int
    base and a non-negative int exponent stay an int; a Fraction in
    either place gives a Fraction, as the computation's float does), an
    exact sympy power for a fractional exponent, else Python's power."""
    if mod is not None:
        return pow(a, b, mod)
    _guarded_native(lambda x, y: x ** y, a, b)
    if _is_rational(a) and _is_rational(b):
        exponent = Fraction(b)
        if exponent.denominator == 1:
            if isinstance(a, int) and isinstance(b, int) and exponent >= 0:
                return a ** int(exponent)
            return Fraction(a) ** int(exponent)
        if a == 0 and exponent < 0:
            raise ZeroDivisionError("0 cannot be raised to a negative power")
        return _settled(_sympify(a) ** _sympify(exponent))
    if _exact(a) and _exact(b):
        base, exponent = _sympify(a), _sympify(b)
        if base.is_zero and exponent.is_negative:
            raise ZeroDivisionError("0 cannot be raised to a negative power")
        return _settled(base ** exponent)
    return a ** b


def _stands_for_float(value) -> bool:
    """An exact number standing where the computation had a float: a
    Fraction, a sympy number, or an algebraic number with an isolating
    interval (`_exact_witness.Algebraic`, a witness read exactly); an
    int stands for an int."""
    return (isinstance(value, Fraction) or _symbolic_number(value)
            or _algebraic(value))


def _algebraic(value) -> bool:
    """Whether `value` is an `_exact_witness.Algebraic` (none is when
    that module has not been imported)."""
    witness = sys.modules.get(f"{__package__}._exact_witness")
    return witness is not None and isinstance(value, witness.Algebraic)


class _FloatMeta(type):
    """`isinstance(x, float)` in the twin: a float, or an exact number
    standing where the computation had a float (a Fraction, a sympy
    number)."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, float) or _stands_for_float(obj)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, (float, Fraction))


class ExactFloat(metaclass=_FloatMeta):
    """`float` as the exact reading sees it: an int (a bool included)
    as the Fraction of the same value, the identity on a Fraction, a
    sympy number or an algebraic number, Python's `float` on anything
    else (a string, a float, a library's number). Named `float`, as
    `type(x).__name__` reads it in the computation."""

    def __new__(cls, x=0):
        if isinstance(x, bool):
            return Fraction(int(x))
        if _STATE.guard and isinstance(x, int):
            # an int past float range overflows as the computation's does
            float(x)
        if _is_rational(x):
            return Fraction(x)
        if _symbolic_number(x) or _algebraic(x):
            return x
        return float(x)


ExactFloat.__name__ = ExactFloat.__qualname__ = "float"


def _class_of(value, own):
    """The type of a twin's value as the computation had it: `float`
    (the exact `float`) of a number standing in for a float, `int` of
    an int the claim wrote (`_exact_side.ExactInt`), else `own`, the
    type the value reports itself."""
    from ._exact_side import ExactInt
    if _stands_for_float(value):
        return ExactFloat
    if own is ExactInt:
        return int
    return own


def _type(*args):
    """`type` as the twin reads it: of one value, its type as the
    computation had it (`_class_of`); with three arguments, a class as
    ever."""
    if len(args) != 1:
        return type(*args)
    return _class_of(args[0], type(args[0]))


def _class(value):
    """`value.__class__` as the twin reads it (`_class_of`)."""
    return _class_of(value, value.__class__)


def _round(x, ndigits=None):
    """`round`: Python's own, of an int an int.

    Raises:
        NotExact: `x` stands for a float.
    """
    _decline(x)
    return round(x) if ndigits is None else round(x, ndigits)


def _whole(name: str, x):
    """`math.floor`, `math.ceil` or `math.trunc`, of an int the int.

    Raises:
        NotExact: `x` stands for a float.
    """
    _decline(x)
    return getattr(math, name)(x)


def _fabs(x):
    if _is_rational(x):
        return abs(Fraction(x))
    if _symbolic_number(x):
        return _settled(_sympy().Abs(x))
    return math.fabs(x)


def _sqrt(x):
    if not _exact(x):
        return math.sqrt(x)
    s = _sympify(x)
    if not _truth(s >= 0):
        raise ValueError("math domain error")
    return _settled(_sympy().sqrt(s))


def _log(x, base=None):
    if not _exact(x) or (base is not None and not _exact(base)):
        return math.log(x) if base is None else math.log(x, base)
    sympy = _sympy()
    s = _sympify(x)
    if not _truth(s > 0):
        raise ValueError("math domain error")
    if base is None:
        return _settled(sympy.log(s))
    b = _sympify(base)
    if not _truth(b > 0) or b == 1:
        raise ValueError("math domain error")
    return _settled(sympy.log(s) / sympy.log(b))


def _log_base(base: int):
    def word(x):
        return _log(x, base)
    return word


def _log1p(x):
    return _log(1 + x) if _exact(x) else math.log1p(x)


def _expm1(x):
    return _exp(x) - 1 if _exact(x) else math.expm1(x)


def _exp(x):
    if not _exact(x):
        return math.exp(x)
    return _settled(_sympy().exp(_sympify(x)))


def _transcendental(name: str, inside=None):
    """A `math` function of one real argument as its sympy function,
    `inside` the condition (on the sympy argument) for a real value,
    outside which `math` raises `ValueError`."""
    native = getattr(math, name)

    def word(x):
        if not _exact(x):
            return native(x)
        sympy = _sympy()
        s = _sympify(x)
        if inside is not None and not _truth(inside(s)):
            raise ValueError("math domain error")
        return _settled(getattr(sympy, name)(s))
    return word


def _atan2(y, x):
    if not (_exact(y) and _exact(x)):
        return math.atan2(y, x)
    return _settled(_sympy().atan2(_sympify(y), _sympify(x)))


def _unit(s):
    return (s >= -1) & (s <= 1)


_MATH_EXACT: dict = {
    "sqrt": _sqrt, "exp": _exp, "expm1": _expm1, "log": _log,
    "log1p": _log1p, "log2": _log_base(2), "log10": _log_base(10),
    "pow": _pow, "fabs": _fabs,
    "floor": lambda x: _whole("floor", x),
    "ceil": lambda x: _whole("ceil", x),
    "trunc": lambda x: _whole("trunc", x),
    "sin": _transcendental("sin"), "cos": _transcendental("cos"),
    "tan": _transcendental("tan"),
    "asin": _transcendental("asin", _unit),
    "acos": _transcendental("acos", _unit),
    "atan": _transcendental("atan"), "atan2": _atan2,
    "sinh": _transcendental("sinh"), "cosh": _transcendental("cosh"),
    "tanh": _transcendental("tanh"), "asinh": _transcendental("asinh"),
    "acosh": _transcendental("acosh", lambda s: s >= 1),
    "atanh": _transcendental("atanh", lambda s: (s > -1) & (s < 1)),
}


def _guarded_math(name: str, exact):
    """The exact `math` function `exact`, which under a handler catching
    an arithmetic error (`_Guard`) first declines an argument standing
    for a float and runs `math`'s own on integer arguments, raising
    where the computation raises (`_guarded_native`)."""
    native = getattr(math, name, None)

    def word(*args):
        if native is not None:
            _guarded_native(native, *args)
        return exact(*args)
    return word


_MATH_EXACT = {name: (fn if name == "pow" else _guarded_math(name, fn))
               for name, fn in _MATH_EXACT.items()}
# the readings standing for a builtin or `math` function that decides on
# its argument, taken as that decision at a site (`_sited`)
for _name in ("floor", "ceil", "trunc"):
    _MATH_EXACT[_name].__mathema_native__ = getattr(math, _name)
_round.__mathema_native__ = round  # type: ignore[attr-defined]
_divmod.__mathema_native__ = divmod  # type: ignore[attr-defined]
del _name

#: the `math` functions a body may bind by name (`from math import
#: sqrt`), by identity, to their exact versions
_MATH_FUNCTIONS: dict = {id(getattr(math, name)): fn
                         for name, fn in _MATH_EXACT.items()
                         if hasattr(math, name)}
#: those `math` functions themselves, by the same ids
_MATH_NATIVE: dict = {id(getattr(math, name)): getattr(math, name)
                      for name in _MATH_EXACT if hasattr(math, name)}


class _ExactMath:
    """The `math` module as the twin reads it: the functions above by
    their exact versions, `pi`, `e` and `tau` as sympy's constants,
    everything else `math`'s own."""

    def __getattr__(self, name):
        exact = _MATH_EXACT.get(name)
        if exact is not None:
            return exact
        if name in ("pi", "e", "tau"):
            sympy = _sympy()
            return {"pi": sympy.pi, "e": sympy.E, "tau": 2 * sympy.pi}[name]
        return getattr(math, name)


_MATH = _ExactMath()
