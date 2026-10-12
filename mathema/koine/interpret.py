# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The reference interpreter: what a KOINE document means at a point.

`interpret(document, point)` evaluates the body and returns one of
three outcomes: a `Value`; a `NoValue` naming its class
(`nonvalue::mathematical::singular`, `nonvalue::mathematical::domain`,
`nonvalue::machine::overflow`); or a `Refusal`, the body's own
`statement::require` or `statement::fail`, with the neutral kind and
the failure's type name. The document's `manifest` lines play no part
here: how a runtime shows a non-value is a separate question.

Arithmetic is Python's: exact integers, binary64 reals, the operator
and function realisations in `functions`. Representations narrower
than that (`f32`, fixed-width integers) are not modelled and make a
document not runnable. A point the interpreter cannot run (an index
past the end, an unresolved call, a non-finite operand, loops running
past `MAX_ITERATIONS`) raises
`InterpretError`, a fourth state: nothing to say, rather than "no
value".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from .document import Document
from .functions import IMPLEMENTATIONS
from .syntax import Bool, Int, Name, Real, Str, Term


@dataclass(frozen=True)
class Value:
    value: Any


@dataclass(frozen=True)
class NoValue:
    cls: str
    detail: str = ""


@dataclass(frozen=True)
class Refusal:
    kind: str
    type: str
    message: str = ""


class InterpretError(Exception):
    """The document cannot be evaluated at this point; not an outcome."""


SINGULAR = "nonvalue::mathematical::singular"
DOMAIN = "nonvalue::mathematical::domain"
OVERFLOW = "nonvalue::machine::overflow"

RUNNABLE_REPRS = frozenset(f"representation::{r}" for r in
                           ("f64", "f64int", "bigint", "c128", "bool", "str"))


def interpret(doc: Document, point, calls: dict[str, Callable] | None = None):
    """Intent:
        The outcome of `doc`'s body at `point`: a mapping from
        parameter name to value, or a positional list in parameter
        order. `calls` resolves `call::function` and `call::library`
        keys to callables.

    Raises:
        InterpretError: the document is not runnable at this point.
    """
    for p in doc.parameters:
        for r in list(p.args[2:3]) + [p.get("element")]:
            if isinstance(r, Term) and r.head not in RUNNABLE_REPRS:
                raise InterpretError(f"{r.head} is not modelled")
    names = doc.parameter_names
    if isinstance(point, dict):
        missing = [n for n in names if n not in point]
        if missing:
            raise InterpretError(f"point is missing {missing}")
        env = {n: point[n] for n in names}
    else:
        values = list(point)
        if len(values) != len(names):
            raise InterpretError(f"point has {len(values)} values for {len(names)} parameters")
        env = dict(zip(names, values))
    machine = _Machine(calls or {})
    try:
        machine.block(doc.body, env)
    except _Return as r:
        return Value(r.value)
    except _NoValueSignal as nv:
        return NoValue(nv.cls, nv.detail)
    except _RefusalSignal as rf:
        return rf.refusal
    raise InterpretError("the body ended without a return")


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class _NoValueSignal(Exception):
    def __init__(self, cls: str, detail: str = ""):
        self.cls, self.detail = cls, detail


class _RefusalSignal(Exception):
    def __init__(self, refusal: Refusal):
        self.refusal = refusal


@dataclass
class _Local:
    params: list
    value: Any


def _refusal(failure: Term) -> Refusal:
    kind = failure.head.rpartition("::")[2]
    type_name = failure.args[0].value if failure.args and isinstance(failure.args[0], Str) else ""
    message = failure.get("message")
    return Refusal(kind, type_name, message.value if isinstance(message, Str) else "")


#: loop iterations one interpretation may run, across all its loops;
#: a point needing more is one the interpreter does not run
MAX_ITERATIONS = 100_000


class _Machine:
    def __init__(self, calls: dict):
        self.calls = calls
        self.iterations = 0

    def _spend(self, count: int) -> None:
        self.iterations += count
        if self.iterations > MAX_ITERATIONS:
            raise InterpretError(f"the loops need more than {MAX_ITERATIONS} iterations")

    def block(self, stmts, env: dict) -> None:
        for st in stmts:
            self.statement(st, env)

    def statement(self, st: Term, env: dict) -> None:
        h, a = st.head, st.args
        if h == "statement::bind":
            env[a[0].id] = self.expr(a[1], env)
        elif h == "statement::bind_many":
            values = [self.expr(v, env) for v in a[1].items]
            for n, v in zip(a[0].items, values):
                env[n.id] = v
        elif h == "statement::update":
            env[a[0].id] = self.apply(a[1].head, [env[a[0].id], self.expr(a[2], env)])
        elif h == "statement::define":
            env[a[0].id] = _Local([p.id for p in a[1].items], a[2])
        elif h == "statement::branch":
            chosen = a[1] if _truth(self.expr(a[0], env)) else a[2]
            self.block(chosen.items, env)
        elif h == "statement::loop::range":
            start = _integral(self.expr(a[1], env), "start")
            stop = _integral(self.expr(a[2], env), "stop")
            steps = range(start, stop, a[3].value)
            self._spend(len(steps))
            for i in steps:
                env[a[0].id] = i
                self.block(a[4].items, env)
        elif h == "statement::loop::each":
            seq = _sequence(self.sequence(a[1], env))
            index = st.get("index")
            self._spend(max(0, len(seq) - a[2].value))
            for i in range(a[2].value, len(seq)):
                env[a[0].id] = seq[i]
                if index is not None:
                    env[index.id] = i
                self.block(a[3].items, env)
        elif h == "statement::require":
            if not _truth(self.expr(a[0], env)):
                raise _RefusalSignal(_refusal(a[1]))
        elif h == "statement::fail":
            raise _RefusalSignal(_refusal(a[0]))
        elif h == "statement::return":
            raise _Return(self.expr(a[0], env))
        elif h == "statement::evaluate":
            self.expr(a[0], env)
        else:
            raise InterpretError(f"unknown statement {h}")

    def sequence(self, node, env: dict):
        if isinstance(node, Name):
            return env[node.id]
        return self.expr(node, env)

    def apply(self, head: str, args: list):
        fn = IMPLEMENTATIONS.get(head)
        if fn is None:
            raise InterpretError(f"no implementation of {head}")
        for x in args:
            _number(x)
            if isinstance(x, float) and not math.isfinite(x):
                raise InterpretError(f"{head} of a non-finite operand")
        try:
            result = fn(*args)
        except ZeroDivisionError:
            raise _NoValueSignal(SINGULAR, head) from None
        except OverflowError:
            raise _NoValueSignal(OVERFLOW, head) from None
        except ValueError:
            raise _NoValueSignal(DOMAIN, head) from None
        except TypeError as e:
            raise InterpretError(f"{head}: {e}") from None
        if isinstance(result, float) and math.isinf(result):
            raise _NoValueSignal(OVERFLOW, head)
        if isinstance(result, float) and math.isnan(result):
            raise _NoValueSignal(DOMAIN, head)
        return result

    def expr(self, node, env: dict):
        if isinstance(node, Int):
            return node.value
        if isinstance(node, Real):
            return float(node.text)
        if isinstance(node, (Bool, Str)):
            return node.value
        if isinstance(node, Name):
            if node.id not in env:
                raise InterpretError(f"{node.id} is unbound")
            return env[node.id]
        if not isinstance(node, Term):
            raise InterpretError(f"not an expression: {node!r}")
        h, a = node.head, node.args
        if h in IMPLEMENTATIONS:
            return self.apply(h, [self.expr(x, env) for x in a])
        if h == "constant::pi":
            return math.pi
        if h == "constant::e":
            return math.e
        if h == "constant::infinity":
            return math.inf
        if h == "value::absent":
            return None
        if h == "value::field":
            value = env.get(a[0].id)
            for member in a[1:]:
                value = _field(value, member.id)
            return value
        if h == "value::index":
            seq = _sequence(self.sequence(a[0], env))
            i = _integral(self.expr(a[1], env), "index")
            if not -len(seq) <= i < len(seq):
                raise InterpretError(f"index {i} is outside a sequence of {len(seq)}")
            return seq[i]
        if h == "value::length":
            return len(_sequence(self.sequence(a[0], env)))
        if h == "value::tuple":
            return tuple(self.expr(x, env) for x in a)
        if h == "value::item":
            of = self.expr(a[0], env)
            if not isinstance(of, tuple):
                raise InterpretError("item of a non-tuple")
            try:
                return of[a[1].value]
            except IndexError:
                raise InterpretError(f"tuple item {a[1].value} of {len(of)}") from None
        if h == "value::conditional":
            return self.expr(a[1] if _truth(self.expr(a[0], env)) else a[2], env)
        if h.startswith("operator::comparison::"):
            return _compare(h.rpartition("::")[2], self.expr(a[0], env), self.expr(a[1], env))
        if h == "operator::logic::not":
            return not _truth(self.expr(a[0], env))
        if h in ("operator::logic::and", "operator::logic::or"):
            stop_on = h.endswith("::or")
            for operand in a:
                if _truth(self.expr(operand, env)) == stop_on:
                    return stop_on
            return not stop_on
        if h in ("operator::membership::in", "operator::membership::not_in"):
            item = self.expr(a[0], env)
            found = any(_compare("equal", item, self.expr(m, env)) for m in a[1].items)
            return found if h.endswith("::in") else not found
        if h == "call::local":
            local = env.get(a[0].id)
            if not isinstance(local, _Local):
                raise InterpretError(f"{a[0].id} is not a local function")
            inner = dict(env)
            inner.update(zip(local.params, [self.expr(x, env) for x in a[1:]]))
            return self.expr(local.value, inner)
        if h in ("call::function", "call::library"):
            key = a[0].value
            target = self.calls.get(key)
            if target is None:
                raise InterpretError(f"no callable resolves {key!r}")
            args = [self.expr(x, env) for x in a[1:]]
            pins = {k: self.expr(v, env) for k, v in node.named}
            try:
                return target(*args, **pins)
            except ZeroDivisionError:
                raise _NoValueSignal(SINGULAR, key) from None
            except OverflowError:
                raise _NoValueSignal(OVERFLOW, key) from None
            except Exception as e:
                raise _RefusalSignal(Refusal("raise", type(e).__name__, str(e))) from None
        raise InterpretError(f"unknown expression {h}")


def _truth(v) -> bool:
    if isinstance(v, bool):
        return v
    raise InterpretError(f"a boolean was expected, got {type(v).__name__}")


def _number(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, complex)):
        raise InterpretError(f"a number was expected, got {type(v).__name__}")
    return v


def _integral(v, what: str) -> int:
    if isinstance(v, bool):
        raise InterpretError(f"{what} must be an integer")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    raise InterpretError(f"{what} must be an integer, got {v!r}")


def _sequence(v):
    if isinstance(v, (list, tuple)):
        return v
    try:
        return list(v)
    except TypeError:
        raise InterpretError(f"a sequence was expected, got {type(v).__name__}") from None


def _field(value, name: str):
    if isinstance(value, dict) and name in value:
        return value[name]
    if not isinstance(value, dict) and hasattr(value, name):
        return getattr(value, name)
    raise InterpretError(f"no field {name!r}")


def _compare(op: str, a, b) -> bool:
    if op == "equal":
        return a == b
    if op == "not_equal":
        return a != b
    _number(a)
    _number(b)
    return {"less": a < b, "less_equal": a <= b,
            "greater": a > b, "greater_equal": a >= b}[op]

