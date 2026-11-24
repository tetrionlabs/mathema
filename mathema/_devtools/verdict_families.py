# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Families of claim variants, run against mathema's verdicts and
against what calling the function really does.

A family is a list of cases for one rule area (raises, missing values,
safety, enforced domains, assumptions). A case names a small fixture
function, a claim about it, and tags. For each case this module

1. works out a ground truth by calling the function at points read from
   the claim's own domain, without asking mathema anything;
2. runs `check_conjectures` on the case in one tree and judges the row
   against that ground truth: a `proven` row whose claim fails at a
   point is WRONG, and a `falsified` row whose printed witness does not
   fail when called is WRONG;
3. compares two trees (a base and a head checkout of `mathema/`) and
   sorts each row into unchanged, fixed, lost, newly wrong and the like;
4. searches each row of a marked case for a planted marker value.

A ground truth is only ever "true at every point tried". It can refute
a proof, and it can confirm a falsification whose witness it replays,
but it never confirms a proof: the points are a finite selection.

Every call made to learn ground truth goes through `observe_calls`.
The fixture functions called there write at most module-level values of
their own module, and `observe_calls` restores those values afterwards.

    python -m mathema._devtools.verdict_families raises safety
    python -m mathema._devtools.verdict_families --base /path/to/base/mathema raises

The second form runs every case in a child interpreter with the base
tree first on the path, and again with this tree, and prints the rows
that moved. Budgets are counts: points per claim, cases per family.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import copy
import dataclasses
import importlib
import importlib.util
import inspect
import itertools
import json
import math
import os
import pickle
import random
import re
import subprocess
import sys
import types
import typing
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_PACKAGE = "tests.families"
FAMILIES = ("raises", "missing", "safety", "enforced", "assumptions")

POINT_BUDGET = 240  # :draft at most this many points are tried for one claim
INTEGER_BUDGET = 7  # :draft at most this many integers are taken from each end of an integer range

# The planted marker, matched without regard to case and to the
# characters between its pieces, so a stripped or concatenated copy
# (`ZQXMK7f3a`) is found as well as the whole text.
MARKER_PATTERN = re.compile(r"zqx|7f3a", re.IGNORECASE)

DECISIVE = ("proven", "falsified")
UNDECIDED_VERDICTS = ("unknown", "skipped", "crash")

# Judgement statuses.
RIGHT = "right"
WRONG = "WRONG"
UNDECIDED = "undecided"
UNCONFIRMED = "unconfirmed"
CONTRADICTED = "contradicted holds"
LEAK = "LEAK"
CRASH = "crash"
NOT_RUN = "not run"

# Comparison classes.
UNCHANGED = "unchanged"
FIXED = "fixed"
LOST = "lost"
NEWLY_WRONG = "newly wrong"
STILL_WRONG = "still wrong"
GAINED = "gained"
MOVED = "moved"
CLASSES = (UNCHANGED, FIXED, LOST, NEWLY_WRONG, STILL_WRONG, GAINED, MOVED)


class CannotEvaluate(Exception):
    """The claim, or one point of it, is outside what the ground truth
    reads; the message says why."""


# --------------------------------------------------------------------
# cases

@dataclass(frozen=True)
class Case:
    """One claim about one fixture function.

    `function` is `module:name`. `truth` is the claim's truth when it is
    known by construction (None otherwise). `rule` names a reading that
    `mathema/_rules.py` must list for the case to run on a tree; `issue`
    names an open issue the case reproduces. `marker` marks a case whose
    function writes the planted marker somewhere, so its row is searched.
    `rule_if_false` says the rule is needed only where the claim is
    false, which the ground truth decides.
    `points` gives the points to try for a variable whose domain the
    ground truth cannot enumerate (a language). `setup` is `module:name`
    of a function returning a teardown callable, run around the check."""

    name: str
    function: str
    claim: str
    area: str
    truth: "bool | None" = None
    rule: "str | None" = None
    issue: "int | None" = None
    marker: bool = False
    points: "dict | None" = None
    setup: "str | None" = None
    shows: str = ""
    rule_if_false: bool = False


def resolve(reference: str) -> Any:
    """The object a `module:name` (or `module:name.attr`) reference names."""
    module_name, _, attr = reference.partition(":")
    obj: Any = importlib.import_module(module_name)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def family_cases(family: str) -> list[Case]:
    """The cases of one family, read from `tests/families/<family>.py`."""
    module = importlib.import_module(f"{FAMILY_PACKAGE}.{family}")
    out = []
    for spec in module.CASES:
        spec = dict(spec)
        spec.setdefault("area", family)
        spec["name"] = f"{family}.{spec['name']}"
        if spec.get("points") is not None:
            spec["points"] = {k: tuple(v) for k, v in spec["points"].items()}
        out.append(Case(**spec))
    names = [c.name for c in out]
    if len(set(names)) != len(names):
        raise ValueError(f"family {family} repeats a case name")
    return out


# --------------------------------------------------------------------
# the one place a ground-truth call is made

@dataclass
class Observation:
    """What one call did: the value it returned or the exception it
    raised, and the module-level names of the function's own module
    whose values the calls changed."""

    returned: Any = None
    raised: "BaseException | None" = None
    changed: tuple = ()


def _module_of(fn: Callable) -> "types.ModuleType | None":
    target = inspect.unwrap(fn) if callable(fn) else fn
    return sys.modules.get(getattr(target, "__module__", None) or "")


def _state_names(module: "types.ModuleType | None") -> dict:
    """A deep copy of each module-level value of `module` that is data:
    not a module, function, class or dunder name."""
    if module is None:
        return {}
    out = {}
    for key, value in list(vars(module).items()):
        if key.startswith("__") or isinstance(value, (types.ModuleType, types.FunctionType,
                                                      types.BuiltinFunctionType, type)):
            continue
        if callable(value) and not hasattr(value, "__dict__"):
            continue
        try:
            out[key] = copy.deepcopy(value)
        except Exception:
            continue
    return out


def same_value(a: Any, b: Any) -> bool:
    """Whether two values hold the same data: the same type, and equal
    pickled bytes where both pickle, `==` otherwise. Two nan floats are
    the same value."""
    if type(a) is not type(b):
        return False
    try:
        return pickle.dumps(a) == pickle.dumps(b)
    except Exception:
        pass
    try:
        return bool(a == b)
    except Exception:
        return False


def observe_calls(fn: Callable, calls: Sequence[tuple]) -> list[Observation]:
    """Intent:
        Make each call `(args, kwargs)` of `fn` in turn and return what
        each did. Every call made to learn ground truth comes through
        here, so this is the one function to move behind a contained
        child process.
    Notes:
        Module-level values of `fn`'s own module are copied before the
        first call and restored after the last, so a fixture that writes
        its module state leaves nothing behind. State persists between
        the calls of one sequence, which is what a repeat call reads.
    """
    module = _module_of(fn)
    before = _state_names(module)
    names_before = set(vars(module)) if module is not None else set()
    out = []
    try:
        for args, kwargs in calls:
            seen = _state_names(module)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    value = fn(*args, **kwargs)
                obs = Observation(returned=value)
            except Exception as error:
                obs = Observation(raised=error)
            now = _state_names(module)
            obs.changed = tuple(sorted(k for k in set(seen) | set(now)
                                       if k not in seen or k not in now
                                       or not same_value(seen[k], now[k])))
            out.append(obs)
    finally:
        if module is not None:
            for key in set(vars(module)) - names_before:
                delattr(module, key)
            for key, value in before.items():
                setattr(module, key, value)
    return out


# --------------------------------------------------------------------
# domains, read from the claim text without mathema's parser

MISSING_NAMES = {"None": (None,), "absent": (None,), "nan": (math.nan,),
                 "missing": (None, math.nan)}


def _number(text: str) -> Any:
    t = text.strip().replace("−", "-")
    sign = -1 if t.startswith("-") else 1
    core = t.lstrip("+-").strip()
    if core in ("oo", "inf", "∞"):
        return sign * math.inf
    if core == "pi":
        return sign * math.pi
    if re.fullmatch(r"\d+", core):
        return sign * int(core)
    try:
        return sign * float(core)
    except ValueError:
        raise CannotEvaluate(f"{text!r} is not a number the ground truth reads") from None


def _member(text: str) -> tuple:
    """The values one written member of a finite set stands for."""
    t = text.strip()
    if t in MISSING_NAMES:
        return MISSING_NAMES[t]
    if t in ("float('nan')", 'float("nan")'):
        return (math.nan,)
    if t in ("True", "False"):
        return (t == "True",)
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        return (ast.literal_eval(t),)
    return (_number(t),)


def _is_missing(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _is_real(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isnan(v)


def _inward(v: float, toward: float) -> float:
    return math.nextafter(float(v), float(toward))


@dataclass(frozen=True)
class Interval:
    lo: float
    hi: float
    lo_closed: bool
    hi_closed: bool
    integers: bool = False

    def contains(self, v: Any) -> bool:
        if not _is_real(v):
            return False
        if self.integers and not float(v).is_integer():
            return False
        above = v >= self.lo if self.lo_closed else v > self.lo
        below = v <= self.hi if self.hi_closed else v < self.hi
        return above and below

    def points(self) -> list:
        lo, hi = self.lo, self.hi
        if self.integers:
            first = math.ceil(lo) if math.isfinite(lo) else -10**6
            last = math.floor(hi) if math.isfinite(hi) else 10**6
            if not self.lo_closed and first == lo:
                first += 1
            if not self.hi_closed and last == hi:
                last -= 1
            span = list(range(first, min(last, first + INTEGER_BUDGET - 1) + 1))
            span += list(range(max(first, last - INTEGER_BUDGET + 1), last + 1))
            return sorted(set(span))
        flo = lo if math.isfinite(lo) else -1e300
        fhi = hi if math.isfinite(hi) else 1e300
        pts = []
        if self.lo_closed:
            pts.append(lo)
        if self.hi_closed:
            pts.append(hi)
        if math.isfinite(lo):
            pts.append(_inward(lo, hi))
        else:
            pts.append(-sys.float_info.max)
        if math.isfinite(hi):
            pts.append(_inward(hi, lo))
        else:
            pts.append(sys.float_info.max)
        pts += [flo + (fhi - flo) * q for q in (0.25, 0.5, 0.75)]
        pts += [float(k) for k in range(int(max(flo, -50)), int(min(fhi, 50)) + 1)]
        for z in (0.0, -0.0):
            pts.append(z)
        return _dedupe(p for p in pts if self.contains(p))

    def outside(self) -> list:
        pts: list = [-math.inf, math.inf, -1e300, 1e300]
        for end in (self.lo, self.hi):
            if math.isfinite(end):
                pts += [end, math.nextafter(end, -math.inf), math.nextafter(end, math.inf),
                        end - 1, end + 1, end - 0.5, end + 0.5]
        if self.integers:
            pts += [self.lo + 0.5, self.hi - 0.5, 0.5]
        return _dedupe(p for p in pts if not self.contains(p))


@dataclass(frozen=True)
class Finite:
    values: tuple

    def contains(self, v: Any) -> bool:
        return any(same_value(v, m) or (_is_real(v) and _is_real(m) and v == m)
                   for m in self.values)

    def points(self) -> list:
        return list(self.values)

    def outside(self) -> list:
        pts: list = [-math.inf, math.inf, -1e300, 1e300]
        for m in self.values:
            if _is_real(m) and math.isfinite(m):
                pts += [m - 1, m + 1, m - 0.5, m + 0.5,
                        math.nextafter(float(m), -math.inf), math.nextafter(float(m), math.inf)]
        return _dedupe(p for p in pts if not self.contains(p))


@dataclass(frozen=True)
class Named:
    """`R`, `Z` or `N`. `N` is read as the positive integers, so the
    ground truth never relies on whether 0 belongs to it."""

    name: str

    def contains(self, v: Any) -> bool:
        if not _is_real(v) or not math.isfinite(v):
            return False
        if self.name == "R":
            return True
        if not float(v).is_integer():
            return False
        return self.name == "Z" or v >= 1

    def points(self) -> list:
        if self.name == "R":
            return [-1e300, -2.5, -1.0, -0.0, 0.0, 0.5, 1.0, 3.0, 1e300]
        if self.name == "Z":
            return [-10**6, -3, -2, -1, 0, 1, 2, 3, 10**6]
        return [1, 2, 3, 4, 5, 10**6]

    def outside(self) -> list:
        pts = [-math.inf, math.inf]
        if self.name != "R":
            pts += [0.5, 2.5, -0.5]
        if self.name == "N":
            pts += [-1, -2]
        return pts


@dataclass(frozen=True)
class Listed:
    """A domain the ground truth cannot enumerate, given its points by
    the case (a language)."""

    text: str
    values: tuple = ()

    def contains(self, v: Any) -> bool:
        return True

    def points(self) -> list:
        if not self.values:
            raise CannotEvaluate(f"no points are given for {self.text}")
        return list(self.values)

    def outside(self) -> list:
        raise CannotEvaluate(f"the outside of {self.text} is not read")


@dataclass(frozen=True)
class Domain:
    parts: tuple
    removed: tuple = ()

    def contains(self, v: Any) -> bool:
        if any(same_value(v, r) or (_is_real(v) and _is_real(r) and v == r) for r in self.removed):
            return False
        return any(p.contains(v) for p in self.parts)

    def points(self) -> list:
        return _dedupe(p for part in self.parts for p in part.points() if self.contains(p))

    def outside(self) -> list:
        pts = [p for part in self.parts for p in part.outside()] + list(self.removed)
        return _dedupe(p for p in pts if not _is_missing(p) and not self.contains(p))


def _dedupe(values: Iterable) -> list:
    out: list = []
    for v in values:
        if not any(same_value(v, w) for w in out):
            out.append(v)
    return out


_DOMAIN_END = re.compile(r"\s*(,|$)")


def parse_domain(text: str, start: int, given: "tuple | None" = None) -> tuple:
    """Read one domain starting at `text[start]`; return the domain and
    the index just past it."""
    parts: list = []
    removed: list = []
    i = start

    def skip(i: int) -> int:
        while i < len(text) and text[i] == " ":
            i += 1
        return i

    def one(i: int) -> tuple:
        i = skip(i)
        c = text[i:i + 1]
        if c == "{":
            j = _closing(text, i, "{", "}")
            body = text[i + 1:j]
            if "..." in body:
                raise CannotEvaluate("a set written with '...' is not read")
            values = tuple(v for m in _split_top(body) for v in _member(m))
            return Finite(values), j + 1
        if c in "[(":
            j = i + 1
            while j < len(text) and text[j] not in "])":
                j += 1
            if j >= len(text):
                raise CannotEvaluate("an interval is not closed")
            ends = text[i + 1:j].split(",")
            if len(ends) != 2:
                raise CannotEvaluate(f"{text[i:j + 1]!r} is not an interval of two ends")
            part = Interval(_number(ends[0]), _number(ends[1]), c == "[", text[j] == "]")
            return part, j + 1
        m = re.match(r"(R|Z|N)\b", text[i:])
        if m:
            return Named(m.group(1)), i + 1
        m = re.match(r"L\[[^\]]*\]", text[i:])
        if m:
            return Listed(m.group(0), given or ()), i + m.end()
        raise CannotEvaluate(f"the domain at {text[i:i + 20]!r} is not read")

    part, i = one(i)
    parts.append(part)
    while True:
        i2 = skip(i)
        rest = text[i2:]
        if rest.startswith("subset Z"):
            if not isinstance(parts[-1], Interval):
                raise CannotEvaluate("'subset Z' after a domain that is not an interval")
            parts[-1] = dataclasses.replace(parts[-1], integers=True)
            i = i2 + len("subset Z")
            continue
        m = re.match(r"(∪|U)\s", rest)
        if m:
            part, i = one(i2 + m.end())
            parts.append(part)
            continue
        m = re.match(r"\|\s*(missing|absent|None|nan)\b", rest)
        if m:
            parts.append(Finite(MISSING_NAMES[m.group(1)]))
            i = i2 + m.end()
            continue
        if rest.startswith("\\"):
            part, i = one(i2 + 1)
            if not isinstance(part, Finite):
                raise CannotEvaluate("only a finite set is read after '\\'")
            removed += list(part.values)
            continue
        if rest.startswith(":"):
            raise CannotEvaluate("an annotation on a domain is not read")
        break
    if not _DOMAIN_END.match(text, i):
        raise CannotEvaluate(f"text after a domain is not read: {text[i:i + 20]!r}")
    return Domain(tuple(parts), tuple(removed)), i


def _closing(text: str, i: int, open_: str, close: str) -> int:
    depth = 0
    quote = None
    for j in range(i, len(text)):
        ch = text[j]
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == open_:
            depth += 1
        elif ch == close:
            depth -= 1
            if depth == 0:
                return j
    raise CannotEvaluate(f"no closing {close!r}")


def _split_top(text: str) -> list:
    out, depth, cur, quote = [], 0, "", None
    for ch in text:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


@dataclass
class ParsedClaim:
    lets: dict = field(default_factory=dict)
    bindings: list = field(default_factory=list)
    assuming_defined: bool = False
    body: "ast.expr | None" = None
    body_text: str = ""


def parse_claim(text: str, given: "dict | None" = None) -> ParsedClaim:
    """Read a claim of the forms the families use:
    `let g = mod.fn,` and `let h be DOMAIN,` prefixes, a `for v in
    DOMAIN, ...` prefix, an `assuming f is defined,` clause and a body
    that is a Python expression (`^` read as a power)."""
    given = given or {}
    out = ParsedClaim()
    i = 0
    t = text.strip()
    while True:
        m = re.match(r"let\s+(\w+)\s*=\s*([\w.]+)\s*,\s*", t[i:])
        if m:
            out.lets[m.group(1)] = m.group(2)
            i += m.end()
            continue
        m = re.match(r"let\s+(\w+)\s+be\s+", t[i:])
        if m:
            name = m.group(1)
            dom, j = parse_domain(t, i + m.end(), given.get(name))
            out.bindings.append((name, dom))
            i = _after_comma(t, j)
            continue
        break
    m = re.match(r"for\s+", t[i:])
    if m:
        i += m.end()
        while True:
            m = re.match(r"(\w+)\s+in\s+", t[i:])
            if not m:
                raise CannotEvaluate("a 'for' prefix without 'v in DOMAIN'")
            name = m.group(1)
            dom, j = parse_domain(t, i + m.end(), given.get(name))
            out.bindings.append((name, dom))
            i = _after_comma(t, j)
            if not re.match(r"\w+\s+in\s+", t[i:]):
                break
    m = re.match(r"assuming\s+f\s+is\s+defined\s*,\s*", t[i:])
    if m:
        out.assuming_defined = True
        i += m.end()
    if t[i:].startswith("assuming"):
        raise CannotEvaluate("an 'assuming' clause other than 'f is defined' is not read")
    body = t[i:].replace("≥", ">=").replace("≤", "<=").replace("≠", "!=")
    if "=:=" in body or re.search(r"(?<![=!<>])=(?!=)", body):
        raise CannotEvaluate("a relation other than Python's own is not read")
    try:
        out.body = ast.parse(body, mode="eval").body
    except SyntaxError:
        raise CannotEvaluate(f"the body {body!r} is not a Python expression") from None
    out.body_text = body
    return out


def _after_comma(t: str, j: int) -> int:
    m = re.match(r"\s*,\s*", t[j:])
    if not m:
        raise CannotEvaluate("a domain not followed by a comma")
    return j + m.end()


# --------------------------------------------------------------------
# evaluating a body at a point

FUNCTION_WORDS = ("is_state_safe", "is_deterministic", "is_defined")
SAFE_NAMES: dict = {
    "nan": math.nan, "inf": math.inf, "oo": math.inf, "pi": math.pi, "e": math.e,
    "None": None, "True": True, "False": False,
    **{n: getattr(math, n) for n in ("exp", "log", "sqrt", "sin", "cos", "tan", "floor",
                                     "ceil", "fabs", "isnan", "isinf", "isfinite", "log2", "log10")},
    **{n: getattr(builtins, n)
       for n in ("abs", "min", "max", "len", "sum", "sorted", "str", "int", "float", "round",
                 "divmod", "pow", "chr", "ord", "range", "list", "tuple", "dict", "set",
                 "bool", "type", "isinstance", "repr")},
}


class _Gated(ast.NodeTransformer):
    """Rewrites a body so each call of the subject goes through the
    gate, `raises(A, E)` is evaluated lazily, and `^` is a power."""

    def __init__(self, subjects: set):
        self.subjects = subjects

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.BitXor):
            node.op = ast.Pow()
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "raises" and len(node.args) == 2:
            thunk = ast.Lambda(args=ast.arguments(posonlyargs=[], args=[], vararg=None,
                                                  kwonlyargs=[], kw_defaults=[], kwarg=None,
                                                  defaults=[]),
                               body=node.args[0])
            return ast.Call(func=ast.Name("__raises__", ast.Load()), args=[thunk, node.args[1]],
                            keywords=[])
        if isinstance(node.func, ast.Name) and node.func.id in self.subjects:
            return ast.Call(func=ast.Name("__gate__", ast.Load()),
                            args=[ast.Name(node.func.id, ast.Load()), *node.args],
                            keywords=node.keywords)
        return node


class _RaisedOther(Exception):
    """`raises(A, E)` is false: evaluating A raised something else, or
    returned."""


def _raises(thunk: Callable, kind: Any) -> bool:
    try:
        thunk()
    except Exception as error:
        if isinstance(error, kind):
            return True
        raise _RaisedOther(f"the call raised {type(error).__name__}") from None
    raise _RaisedOther("the call returned")


def _gate_one(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    (obs,) = observe_calls(fn, [(args, kwargs)])
    if obs.raised is not None:
        raise obs.raised
    return obs.returned


@dataclass
class Subject:
    fn: Callable
    names: dict  # the names a body may use for functions


def _subject(case: Case, parsed: ParsedClaim) -> Subject:
    fn = resolve(case.function)
    names = {"f": fn, getattr(fn, "__name__", "f"): fn}
    for key, dotted in parsed.lets.items():
        try:
            module_name, _, attr = dotted.rpartition(".")
            names[key] = getattr(importlib.import_module(module_name), attr)
        except Exception:
            raise CannotEvaluate(f"let {key} = {dotted} does not resolve") from None
    return Subject(fn, names)


def _namespace(subject: Subject, point: dict) -> dict:
    module = _module_of(subject.fn)
    ns: dict = {}
    if module is not None:
        ns.update({k: v for k, v in vars(module).items()
                   if isinstance(v, type) and issubclass(v, BaseException)})
    ns.update({n: v for n, v in vars(builtins).items()
               if isinstance(v, type) and issubclass(v, BaseException)})
    ns.update(SAFE_NAMES)
    ns.update(subject.names)
    ns.update(point)
    ns["__raises__"] = _raises
    ns["__gate__"] = _gate_one
    ns["__builtins__"] = {}
    return ns


def _arguments(fn: Callable, point: dict) -> tuple:
    """The call of `fn` a point stands for: each parameter the point
    names, by name; any other parameter keeps its default."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        raise CannotEvaluate("the function has no signature to bind") from None
    kwargs = {}
    for p in sig.parameters.values():
        if p.name in point:
            kwargs[p.name] = point[p.name]
        elif p.default is inspect.Parameter.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            raise CannotEvaluate(f"the claim binds no value for parameter {p.name}")
    return (), kwargs


def _empty_values(fn: Callable, param: str) -> list:
    """The empty inputs a parameter's annotation admits: one per
    sequence or collection type it names; the empty list and tuple
    when it names none."""
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}
    hint = hints.get(param)
    found: list = []

    def walk(h: Any) -> None:
        origin = typing.get_origin(h) or h
        if origin in (typing.Union, getattr(types, "UnionType", None)):
            for a in typing.get_args(h):
                walk(a)
            return
        import collections
        import collections.abc as abc
        table = [(list, []), (tuple, ()), (str, ""), (bytes, b""), (dict, {}), (set, set()),
                 (frozenset, frozenset()), (range, range(0)), (collections.deque, collections.deque())]
        for kind, empty in table:
            if origin is kind:
                found.append(empty)
                return
        if origin in (abc.Sequence, typing.Sequence):
            found.extend([[], (), "", range(0)])
        elif origin in (abc.Mapping, typing.Mapping):
            found.append({})

    if hint is not None:
        walk(hint)
    return _dedupe(found) or [[], ()]


@dataclass(frozen=True)
class GroundTruth:
    """What calling the function shows about a claim.

    `kind` is one of `true at every point tried` (a universal claim that
    no point refuted: this never confirms a proof), `false at` (a point
    where the claim fails), `true at` (a point that witnesses an
    existential claim, such as a negated safety claim), `no point tried
    shows it` (an existential claim no point witnessed: this refutes
    nothing), and `cannot be evaluated`."""

    kind: str
    point: "dict | None" = None
    detail: str = ""
    tried: int = 0

    @property
    def known(self) -> "bool | None":
        return {"false at": False, "true at": True}.get(self.kind)

    def text(self) -> str:
        if self.kind in ("false at", "true at"):
            where = ", ".join(f"{k} = {v!r}" for k, v in (self.point or {}).items()) or "the call"
            return f"{self.kind} {where}: {self.detail}" if self.detail else f"{self.kind} {where}"
        if self.kind == "cannot be evaluated":
            return f"cannot be evaluated: {self.detail}"
        return f"{self.kind} ({self.tried} points)"


TRUE_EVERYWHERE = "true at every point tried"
FALSE_AT = "false at"
TRUE_AT = "true at"
NOT_WITNESSED = "no point tried shows it"
CANNOT = "cannot be evaluated"


def _points(parsed: ParsedClaim, extra: Sequence[dict] = ()) -> list:
    names = [n for n, _ in parsed.bindings]
    lists = [d.points() for _, d in parsed.bindings]
    combos = list(itertools.product(*lists)) if lists else [()]
    if len(combos) > POINT_BUDGET:
        rng = random.Random(0)
        keep = [combos[0], combos[-1]]
        keep += rng.sample(combos[1:-1], POINT_BUDGET - 2)
        combos = keep
    pts = [dict(zip(names, c)) for c in combos]
    for e in extra:
        if all(n in e for n in names):
            pts.append({n: e[n] for n in names})
    return pts


def _top_word(body: ast.expr) -> tuple:
    """`(negated, word, argument)` when the body is one of the words
    that read the whole function, else `(False, None, None)`."""
    negated = False
    node = body
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        negated, node = True, node.operand
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in FUNCTION_WORDS + ("excluded_outside_domain", "is_empty_safe")
            and len(node.args) == 1 and isinstance(node.args[0], ast.Name)):
        return negated, node.func.id, node.args[0].id
    return False, None, None


def _holds_at(word: str, fn: Callable, point: dict) -> tuple:
    """Whether a whole-function word holds at one point: `(holds, why)`."""
    args, kwargs = _arguments(fn, point)
    if word == "is_deterministic":
        first, second = observe_calls(fn, [(args, kwargs), (args, kwargs)])
        if first.raised is not None or second.raised is not None:
            a, b = (type(o.raised).__name__ if o.raised else "value" for o in (first, second))
            return a == b, f"the two calls gave {a} and {b}"
        return same_value(first.returned, second.returned), "two calls returned different values"
    (obs,) = observe_calls(fn, [(args, kwargs)])
    if word == "is_state_safe":
        return not obs.changed, f"the call changed the module-level {', '.join(obs.changed)}"
    if word == "is_defined":
        return obs.raised is None, f"the call raised {type(obs.raised).__name__}"
    raise CannotEvaluate(f"the word {word} is not read")


def ground_truth(case: Case, extra_points: Sequence[dict] = ()) -> GroundTruth:
    """Intent:
        Evaluate the case's claim at points by calling the function: the
        ends of each interval and the floats beside them, interior
        points, every member of a finite set, and the missing values
        the claim names. `extra_points` (witnesses printed by a checker)
        are tried as well.
    Notes:
        This can refute a proof and can never confirm one: "true at
        every point tried" says only that no point tried refuted it.
    """
    try:
        parsed = parse_claim(case.claim, case.points)
        subject = _subject(case, parsed)
        assert parsed.body is not None
        negated, word, arg = _top_word(parsed.body)
        if word == "is_empty_safe":
            empties = _empty_values(subject.fn, arg)
            for empty in empties:
                (obs,) = observe_calls(subject.fn, [((), {arg: empty})])
                if obs.raised is not None:
                    return GroundTruth(FALSE_AT, {arg: empty},
                                       f"the call raised {type(obs.raised).__name__}", len(empties))
            return GroundTruth(TRUE_EVERYWHERE, tried=len(empties))
        points = _points(parsed, extra_points)
        if word == "excluded_outside_domain":
            dom = dict(parsed.bindings).get(arg)
            if dom is None:
                raise CannotEvaluate(f"{arg} has no domain in the claim")
            tried = 0
            for point in points:
                for outside in dom.outside():
                    p = dict(point, **{arg: outside})
                    args, kwargs = _arguments(subject.fn, p)
                    (obs,) = observe_calls(subject.fn, [(args, kwargs)])
                    tried += 1
                    if obs.raised is None:
                        return GroundTruth(FALSE_AT, p, f"the call returned {obs.returned!r}", tried)
                break
            return GroundTruth(TRUE_EVERYWHERE, tried=tried)
        if word in FUNCTION_WORDS:
            for n, point in enumerate(points, 1):
                holds, why = _holds_at(word, subject.fn, point)
                if negated and not holds:
                    return GroundTruth(TRUE_AT, point, why, n)
                if not negated and not holds:
                    return GroundTruth(FALSE_AT, point, why, n)
            return GroundTruth(NOT_WITNESSED if negated else TRUE_EVERYWHERE, tried=len(points))
        tree = ast.fix_missing_locations(ast.Expression(
            _Gated(set(subject.names)).visit(copy.deepcopy(parsed.body))))
        code = compile(tree, "<claim>", "eval")
        tried = 0
        for point in points:
            tried += 1
            outcome, why = _body_at(code, subject, point)
            if outcome is None:
                continue
            if not outcome:
                if parsed.assuming_defined and why.startswith("raised"):
                    continue
                return GroundTruth(FALSE_AT, point, why, tried)
        return GroundTruth(TRUE_EVERYWHERE, tried=tried)
    except CannotEvaluate as reason:
        return GroundTruth(CANNOT, detail=str(reason))


def _body_at(code: Any, subject: Subject, point: dict) -> tuple:
    """`(True, "")`, `(False, why)`, or `(None, why)` when the point
    cannot be evaluated."""
    try:
        value = eval(code, _namespace(subject, point))
    except NameError as error:
        raise CannotEvaluate(f"the body names something the ground truth does not: {error}") from None
    except _RaisedOther as error:
        return False, str(error)
    except Exception as error:
        return False, f"raised {type(error).__name__}"
    if not isinstance(value, (bool, int)):
        return None, "the body is not a truth value"
    return bool(value), "the relation is false there"


def witness_point(counterexample: "str | None", names: Sequence[str]) -> "dict | None":
    """The point a printed witness `x = 1.0, y = None: ...` names, or
    None when it cannot be read back."""
    if not counterexample:
        return None
    text = counterexample.strip()
    point: dict = {}
    pattern = re.compile(r"(\w+) = ")
    pos = 0
    while True:
        m = pattern.match(text, pos)
        if not m or m.group(1) not in names:
            break
        rest = text[m.end():]
        value, length = _leading_literal(rest)
        if length == 0:
            return None
        point[m.group(1)] = value
        pos = m.end() + length
        sep = re.match(r",\s*", text[pos:])
        if not sep:
            break
        pos += sep.end()
    if set(point) != set(names):
        return None
    return point


def _leading_literal(text: str) -> tuple:
    """The longest prefix of `text` that reads as a literal, and its
    length."""
    best: tuple = (None, 0)
    for end in range(1, min(len(text), 400) + 1):
        if end < len(text) and text[end] not in ",:":
            continue
        chunk = text[:end].strip()
        try:
            if chunk == "nan":
                value: Any = math.nan
            elif chunk in ("inf", "-inf"):
                value = float(chunk)
            else:
                value = ast.literal_eval(chunk)
            best = (value, end)
        except Exception:
            continue
    return best


def witness_fails(case: Case, point: dict) -> "bool | None":
    """Whether the claim fails at a printed witness when called: True,
    False, or None when it cannot be evaluated there. A witness outside
    the claim's domain cannot be replayed (it may name the function's
    parameters rather than the claim's variables), so it gives None."""
    try:
        parsed = parse_claim(case.claim, case.points)
        for name, dom in parsed.bindings:
            if not dom.contains(point.get(name)):
                return None
        subject = _subject(case, parsed)
        assert parsed.body is not None
        negated, word, _arg = _top_word(parsed.body)
        if word is not None:
            if word in FUNCTION_WORDS and not negated:
                holds, _ = _holds_at(word, subject.fn, point)
                return not holds
            return None
        tree = ast.fix_missing_locations(ast.Expression(
            _Gated(set(subject.names)).visit(copy.deepcopy(parsed.body))))
        outcome, why = _body_at(compile(tree, "<claim>", "eval"), subject, point)
        if outcome is None:
            return None
        if not outcome and parsed.assuming_defined and why.startswith("raised"):
            return False
        return not outcome
    except CannotEvaluate:
        return None


# --------------------------------------------------------------------
# a tree's verdicts

def rules_in_tree() -> str:
    """The text of the reasoning-version table of the `mathema` this
    interpreter imports: the readings it carries, by name."""
    try:
        from mathema import _rules
        return _rules.__doc__ or ""
    except Exception:
        return ""


@dataclass
class Outcome:
    """What one tree's checker said about a case."""

    case: str
    verdict: str
    route: "str | None" = None
    counterexample: "str | None" = None
    sketch: "str | None" = None
    note: "str | None" = None
    marker_hits: list = field(default_factory=list)
    skipped_for: str = ""


def marker_hits(rows: Sequence[Any]) -> list:
    """Every place the planted marker shows in a row: its texts, its
    meta, its `repr`, its attributes. Empty when it shows nowhere."""
    hits = []
    for row in rows:
        surfaces = {"repr": repr(row)}
        for key, value in vars(row).items() if hasattr(row, "__dict__") else ():
            try:
                surfaces[key] = json.dumps(value, default=repr) if not isinstance(value, str) else value
            except Exception:
                surfaces[key] = repr(value)
        for where, text in surfaces.items():
            m = MARKER_PATTERN.search(text or "")
            if m:
                hits.append(f"{where}: ...{text[max(0, m.start() - 60):m.end() + 20]}...")
    return hits


def check_case(case: Case, rules_text: "str | None" = None, honour_rules: bool = True,
               checker: "Callable | None" = None) -> Outcome:
    """Run `check_conjectures` on one case in this interpreter's tree
    (or `checker(fn, text)`, which returns the rows, in its place).
    A case whose rule the tree lacks is not run, and says so, unless
    `honour_rules` is False."""
    rules: str = rules_in_tree() if rules_text is None else rules_text
    needs_rule = bool(case.rule) and (not case.rule_if_false
                                      or known_truth(case, ground_truth(case)) is False)
    if honour_rules and needs_rule and str(case.rule) not in rules:
        return Outcome(case.name, NOT_RUN, skipped_for=f"the tree lacks {case.rule}")
    if checker is None:
        from mathema.conjecture import check_conjectures, claim

        def checker(fn: Callable, text: str) -> list:
            return check_conjectures(fn, [claim(text)])
    teardown = resolve(case.setup)() if case.setup else None
    try:
        fn = resolve(case.function)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rows = checker(fn, case.claim)
    except Exception as error:
        return Outcome(case.name, "crash", note=f"{type(error).__name__}: {error}"[:300])
    finally:
        if teardown is not None:
            teardown()
    main = [r for r in rows if not r.name.endswith("[float]")] or list(rows)
    row = main[0]
    return Outcome(case.name, str(row.verdict).split(":", 1)[0], row.route, row.counterexample,
                   row.sketch, row.note, marker_hits(rows) if case.marker else [])


# --------------------------------------------------------------------
# judgement

@dataclass
class Judgement:
    case: str
    area: str
    verdict: str
    route: "str | None"
    status: str
    reason: str
    truth: "bool | None"
    ground: str
    issue: "int | None" = None
    rule: "str | None" = None
    texts: dict = field(default_factory=dict)

    @property
    def wrong(self) -> bool:
        return self.status in (WRONG, LEAK)


def known_truth(case: Case, ground: GroundTruth) -> "bool | None":
    """The claim's truth where it is known: from a call that refutes or
    witnesses it, else from the case's construction. A case whose stated
    truth a call contradicts is a defect in the case."""
    if ground.known is not None:
        if case.truth is not None and case.truth != ground.known:
            raise ValueError(f"case {case.name} states truth {case.truth}, "
                             f"but the call shows {ground.text()}")
        return ground.known
    return case.truth


def judge(case: Case, outcome: Outcome, ground: GroundTruth) -> Judgement:
    """Intent:
        Compare one tree's verdict with the ground truth: a `proven`
        verdict on a false claim is WRONG, a `falsified` verdict whose
        printed witness does not fail when called is WRONG, and a planted
        marker shown anywhere in the row is a LEAK.
    """
    truth = known_truth(case, ground)
    texts = {"counterexample": outcome.counterexample, "sketch": outcome.sketch, "note": outcome.note}

    def made(status: str, reason: str) -> Judgement:
        return Judgement(case.name, case.area, outcome.verdict, outcome.route, status, reason,
                         truth, ground.text(), case.issue, case.rule, texts)

    if outcome.verdict == NOT_RUN:
        return made(NOT_RUN, outcome.skipped_for)
    if outcome.verdict == "crash":
        return made(CRASH, f"check_conjectures raised {outcome.note}")
    if outcome.marker_hits:
        return made(LEAK, "the planted marker shows in " + "; ".join(outcome.marker_hits))
    if outcome.verdict == "proven":
        if truth is False:
            return made(WRONG, f"proven, but {ground.text() if ground.known is False else 'false by construction'}")
        return made(RIGHT, "proven, and no call refutes it")
    if outcome.verdict == "falsified":
        names = []
        try:
            names = [n for n, _ in parse_claim(case.claim, case.points).bindings]
        except CannotEvaluate:
            pass
        point = witness_point(outcome.counterexample, names) if names else None
        if point is not None:
            fails = witness_fails(case, point)
            if fails is False:
                return made(WRONG, f"falsified, but the witness {point!r} does not fail when called")
            if fails is True:
                return made(RIGHT, "falsified, and the witness fails when called")
        if truth is True:
            return made(WRONG, "falsified, but the claim is true"
                        + (f" ({ground.text()})" if ground.known else " by construction"))
        if truth is False:
            return made(RIGHT, "falsified, and the claim is false")
        return made(UNCONFIRMED, "falsified, and the witness could not be replayed")
    if outcome.verdict == "holds" and truth is False:
        return made(CONTRADICTED, f"holds, but {ground.text() if ground.known is False else 'false by construction'}")
    return made(UNDECIDED, outcome.verdict + (f": {outcome.note[:160]}" if outcome.note else ""))


def classify(base_verdict: str, base_wrong: bool, head_verdict: str, head_wrong: bool,
             truth: "bool | None") -> str:
    """Intent:
        The class of one row of a base-against-head table:
        `fixed` (wrong on base, not on head), `newly wrong` (wrong on
        head, not on base), `unchanged` (the same verdict), `still wrong`
        (wrong on both, verdicts differ), `lost` (a proof of a claim not
        known false, or a falsification of a claim not known true, that
        head no longer gives), `gained` (head decisive, or `holds`
        where base was undecided, neither wrong), `moved` (anything else).
    """
    if base_wrong and not head_wrong:
        return FIXED
    if head_wrong and not base_wrong:
        return NEWLY_WRONG
    if base_verdict == head_verdict:
        return UNCHANGED
    if base_wrong and head_wrong:
        return STILL_WRONG
    if base_verdict == "proven" and truth is not False:
        return LOST
    if base_verdict == "falsified" and truth is not True:
        return LOST
    if head_verdict in DECISIVE or (head_verdict == "holds" and base_verdict in UNDECIDED_VERDICTS):
        return GAINED
    return MOVED


def weaker(recorded: str, found: str) -> bool:
    """Whether a verdict says less than the one recorded: a decisive
    verdict (`proven`, `falsified`) become anything else, or `holds`
    become `unknown` or `skipped`."""
    if recorded in DECISIVE:
        return found != recorded
    return recorded == "holds" and found in UNDECIDED_VERDICTS


# --------------------------------------------------------------------
# running families, in this tree or another one

def cases_of(families: Sequence[str]) -> list[Case]:
    return [c for fam in families for c in family_cases(fam)]


def _ensure_importable_children() -> None:
    """Put the repository root on PYTHONPATH, so a child process the
    checker starts can import the fixture modules."""
    paths = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if str(REPO_ROOT) not in paths:
        os.environ["PYTHONPATH"] = os.pathsep.join([*paths, str(REPO_ROOT)])


def outcomes_here(cases: Sequence[Case], honour_rules: bool = True) -> list[Outcome]:
    _ensure_importable_children()
    rules = rules_in_tree()
    return [check_case(c, rules, honour_rules) for c in cases]


_CHILD = """
import importlib.util, json, sys
tree, root, runner, names, honour = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4]), sys.argv[5] == "1"
sys.path[:0] = [p for p in (tree, root) if p]
import mathema
if tree and not mathema.__file__.startswith(tree):
    raise SystemExit("mathema resolved to " + mathema.__file__ + ", not under " + tree)
spec = importlib.util.spec_from_file_location("verdict_families_runner", runner)
mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
mod._child_main(names, honour)
"""


def _child_main(names: Sequence[str], honour_rules: bool = True) -> None:
    import dataclasses as dc
    wanted = set(names)
    families = sorted({n.split(".", 1)[0] for n in names})
    cases = [c for c in cases_of(families) if c.name in wanted]
    for outcome in outcomes_here(cases, honour_rules):
        print("OUTCOME " + json.dumps(dc.asdict(outcome), default=repr), flush=True)


def outcomes_in_tree(tree: "str | None", cases: Sequence[Case], workers: int = 1,
                     honour_rules: bool = True) -> list[Outcome]:
    """Run the cases in child interpreters with `tree` (a checkout's
    `mathema/` package; None for this one) first on the path."""
    tree_dir = str(Path(tree).resolve().parent) if tree else ""
    if tree and Path(tree).name != "mathema":
        raise ValueError("give the path of a checkout's mathema/ package")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (tree_dir, str(REPO_ROOT)) if p)
    chunks = [list(cases[i::workers]) for i in range(max(1, workers))]
    procs = []
    for chunk in chunks:
        if not chunk:
            continue
        procs.append(subprocess.Popen(
            [sys.executable, "-c", _CHILD, tree_dir, str(REPO_ROOT), str(Path(__file__).resolve()),
             json.dumps([c.name for c in chunk]), "1" if honour_rules else "0"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=str(REPO_ROOT)))
    found: dict = {}
    for proc in procs:
        out, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"a child run failed: {err[-2000:]}")
        for line in out.splitlines():
            if line.startswith("OUTCOME "):
                o = Outcome(**json.loads(line[len("OUTCOME "):]))
                found[o.case] = o
    return [found.get(c.name, Outcome(c.name, "crash", note="no outcome from the child")) for c in cases]


def _witness_points(case: Case, outcomes: Iterable[Outcome]) -> list:
    """The printed witnesses of falsified rows that read back as points
    inside the claim's domain."""
    try:
        bindings = parse_claim(case.claim, case.points).bindings
    except CannotEvaluate:
        return []
    names = [n for n, _ in bindings]
    pts = []
    for o in outcomes:
        if o.verdict == "falsified" and names:
            p = witness_point(o.counterexample, names)
            if p is not None and all(d.contains(p[n]) for n, d in bindings):
                pts.append(p)
    return pts


def judge_tree(cases: Sequence[Case], outcomes: Sequence[Outcome]) -> list[Judgement]:
    out = []
    for case, outcome in zip(cases, outcomes):
        gt = ground_truth(case, _witness_points(case, [outcome]))
        out.append(judge(case, outcome, gt))
    return out


@dataclass
class Row:
    case: str
    area: str
    cls: str
    base: Judgement
    head: Judgement


def compare(cases: Sequence[Case], base: Sequence[Outcome], head: Sequence[Outcome]) -> list[Row]:
    """Judge both trees against one ground truth (with the witnesses
    of both trees tried) and classify each row."""
    rows = []
    for case, b, h in zip(cases, base, head):
        gt = ground_truth(case, _witness_points(case, [b, h]))
        jb, jh = judge(case, b, gt), judge(case, h, gt)
        if NOT_RUN in (jb.status, jh.status):
            cls = NOT_RUN
        else:
            cls = classify(jb.verdict, jb.wrong, jh.verdict, jh.wrong, known_truth(case, gt))
        rows.append(Row(case.name, case.area, cls, jb, jh))
    return rows


# --------------------------------------------------------------------
# output

def judgement_line(j: Judgement) -> str:
    return json.dumps(dataclasses.asdict(j), default=repr)


def summary(judgements: Sequence[Judgement]) -> str:
    """Counts per status and per rule area, then each WRONG, LEAK and
    not-run row in one line."""
    lines = []
    statuses = sorted({j.status for j in judgements})
    lines.append(f"{len(judgements)} cases: " + ", ".join(
        f"{sum(j.status == s for j in judgements)} {s}" for s in statuses))
    for area in sorted({j.area for j in judgements}):
        mine = [j for j in judgements if j.area == area]
        lines.append(f"  {area}: " + ", ".join(
            f"{sum(j.status == s for j in mine)} {s}" for s in statuses if any(j.status == s for j in mine)))
    for j in judgements:
        if j.status in (WRONG, LEAK, CRASH, NOT_RUN):
            tag = f" (issue {j.issue})" if j.issue else ""
            lines.append(f"{j.status} {j.case}{tag}: {j.reason}")
    return "\n".join(lines)


def comparison_summary(rows: Sequence[Row]) -> str:
    lines = [f"{len(rows)} rows: " + ", ".join(
        f"{sum(r.cls == c for r in rows)} {c}" for c in (*CLASSES, NOT_RUN) if any(r.cls == c for r in rows))]
    for area in sorted({r.area for r in rows}):
        mine = [r for r in rows if r.area == area]
        lines.append(f"  {area}: " + ", ".join(
            f"{sum(r.cls == c for r in mine)} {c}" for c in (*CLASSES, NOT_RUN) if any(r.cls == c for r in mine)))
    for r in rows:
        if r.cls not in (UNCHANGED, NOT_RUN):
            lines.append(f"{r.cls} {r.case}: {r.base.verdict} -> {r.head.verdict} ({r.head.reason})")
    return "\n".join(lines)


def main(argv: "Sequence[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mathema._devtools.verdict_families",
                                     description="Run families of claim variants against calls.")
    parser.add_argument("families", nargs="*", default=list(FAMILIES))
    parser.add_argument("--base", help="a base checkout's mathema/ package, compared with this tree")
    parser.add_argument("--head", help="another checkout's mathema/ package to stand for this tree")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--json", help="write the table as JSON lines here")
    parser.add_argument("--only", help="run only cases whose name contains this text")
    parser.add_argument("--record", help="write each case's verdict and status here, as the "
                        "expectations a later run is compared with")
    parser.add_argument("--all-rules", action="store_true",
                        help="run cases whose rule the tree lacks as well")
    args = parser.parse_args(argv)
    cases = cases_of(args.families)
    if args.only:
        cases = [c for c in cases if args.only in c.name]
    head = outcomes_in_tree(args.head, cases, args.workers, honour_rules=not args.all_rules)
    if args.base:
        # a case whose rule the head carries also runs on a base that lacks it
        ran = [c for c, o in zip(cases, head) if o.verdict != NOT_RUN]
        found = {o.case: o for o in outcomes_in_tree(args.base, ran, args.workers, honour_rules=False)}
        base = [found.get(c.name, o) for c, o in zip(cases, head)]
        rows = compare(cases, base, head)
        lines = [json.dumps({"case": r.case, "area": r.area, "class": r.cls,
                             "base": dataclasses.asdict(r.base), "head": dataclasses.asdict(r.head)},
                            default=repr) for r in rows]
        text = comparison_summary(rows)
    else:
        judgements = judge_tree(cases, head)
        lines = [judgement_line(j) for j in judgements]
        text = summary(judgements)
        if args.record:
            Path(args.record).write_text(json.dumps(
                {j.case: {"verdict": j.verdict, "status": j.status, "issue": j.issue}
                 for j in judgements}, indent=1, sort_keys=True) + "\n")
    if args.json:
        Path(args.json).write_text("\n".join(lines) + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
