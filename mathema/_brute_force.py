# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Adjudication by visiting every point a finite domain admits.

A claim quantified over a finite declared domain does not need a
symbolic argument at all. `for n in [30,30] subset Z, f(n) == 0` states
one fact about one input; `for r1 in [0,2] subset Z, r2 in [0,4]
subset Z, ...` states fifteen. Enumerating those points and evaluating
the claim at each is not sampling, it is a complete argument over the
whole region the author declared, so it earns `proven` rather than
`holds`.

A proof is about the mathematics, so each point is decided exactly:
the function run on the point's exact value (the number as written),
the claim's literals exact, `==` as equality and `~=` within ε. The
float computation's allowance belongs to the computation line, so a
point where the float result passes within it while the exact value
misses is a falsification, and a point where the function gives no
exact value (a float it computed) leaves the sweep at holds.

That distinction is the entire point of this module, and it rests on
three things being true at once: the domain is genuinely finite (an
integer-typed interval or a discrete set, never a real interval), the
sweep visits all of it (never a prefix), and the function is pure, so
one evaluation per point is the whole story. Any of the three failing
means declining, because a sweep that is partial, or over a region
larger than it thinks, is a sampling loop wearing a proof label.

The evaluation itself is the corroboration gate's own point evaluator
(`gates._point_evaluator`), which calls the real function and decides
the claim's relation at a concrete point. Reusing it means a verdict
here rests on exactly the same machinery a falsification's witness
does, rather than a second, subtly different reading of the claim.
"""
from __future__ import annotations

import itertools

from ._exact_side import holds_number
from ._exits import call, exception_name
from .domain import _as_domain, _set_sentinels, finite_members
from .probing import ExecutedMissing, LastCall, executed_missing, with_executed
from .symbolic import ProofResult

__all__ = ["BRUTE_FORCE_POINT_BUDGET", "brute_force_proof", "ground_proof"]

#: the most points one claim's sweep will visit. A domain larger than
#: this declines rather than being truncated: the budget bounds the work
#: mathema will do, never the region a verdict covers.
BRUTE_FORCE_POINT_BUDGET = 100_000
#: the wall-clock seconds the sweep may spend, judged from a timed
#: estimate of one point; past it the sweep runs the discontinuities and
#: a seeded sample instead, and says so
_SWEEP_SECONDS = 8.0
#: the points a partial sweep executes beyond the discontinuities
_PARTIAL_SAMPLE = 2000


def _sweep_grid(params: list, cj_domain: dict, budget: int,
                resolution: "dict | None" = None):
    """Intent:
        `{param: (value, ...)}` for every parameter, when each one's
        declared domain is finite and their product is within `budget`.
        `None` when any parameter is unbounded, real-typed, or the grid
        is too large. A finite set's listed sentinels are visited as the
        real values they stand for, read from `resolution` (`{param:
        domain.MissingDefaults}`): `None` for absence, one value per
        member of the hole class.

    Notes:
        The product is checked as it grows rather than after, so a
        domain built from several wide integer ranges declines without
        first materialising the members of all of them.
    """
    grid: dict = {}
    total = 1
    for p in params:
        bound = cj_domain.get(p)
        if bound is None:
            return None            # undeclared, so unbounded
        policy = (resolution or {}).get(p)
        members = finite_members(bound, budget,
                                 members=policy.members if policy else None,
                                 absence=policy.absence if policy else ())
        if members is None:
            return None
        total *= len(members)
        if total > budget:
            return None
        grid[p] = members
    return grid


def _within_path_bindings(grid: dict, cj_domain: dict) -> tuple:
    """Intent:
        `(grid, no_value)`: the grid with each parameter's members kept
        only where the claim's path bindings on it hold (a binding is a
        filter on a language's members), and how many members were
        left out because a path reached no value (an index past the
        end, a field holding None) the bound does not admit.
    """
    from .domain import path_bindings_verdict
    no_value = 0
    out = dict(grid)
    for p, members in grid.items():
        if not any(k.startswith(p + ".") or k.startswith(p + "[")
                   for k in cj_domain):
            continue
        kept = []
        for v in members:
            said = path_bindings_verdict(v, p, cj_domain)
            if said is None:
                kept.append(v)
            elif said == "no value":
                no_value += 1
        out[p] = tuple(kept)
    return out, no_value


def _tried(grid: dict) -> dict:
    """`{"mathema.missing": {"tried": {param: [value, ...]}}}` for the
    missing values a sweep executes, empty when it executes none."""
    from .domain import is_missing
    tried = {p: [repr(v) for v in values if is_missing(v)]
             for p, values in grid.items()}
    tried = {p: v for p, v in tried.items() if v}
    return {"mathema.missing": {"tried": tried}} if tried else {}


def _points(n: int) -> str:
    return "one point" if n == 1 else f"{n} points"


def _point_words(point: dict) -> str:
    from ._missing_words import point_shown
    return point_shown(point)


def _membership_words(rhs: str, wanted: bool) -> str:
    """`is missing`, `is absent`, `is in {0, 1}`, or their negations."""
    text = (rhs or "").strip()
    word = {"{missing}": "missing", "{∅}": "missing", "{absent}": "absent",
            "{None}": "absent"}.get(text.replace(" ", ""))
    if word:
        return f"is {word}" if wanted else f"is not {word}"
    return f"is {'' if wanted else 'not '}in {text}"


class _Scope:
    """Where a sweep's finite points came from, in words: the claim's
    own binding (`the claim ranges over 3 points`), the function's
    domain (`the function's domain has 3 points`: its annotation, a
    guard to a set, or a domain the check was given), or the two
    together for a claim binding some parameters and not others."""

    def __init__(self, cj, names: list):
        bound = set(getattr(cj, "domain", None) or {})
        claimed = [n for n in names if n in bound]
        if len(claimed) == len(names):
            self.kind = "claim"
        elif not claimed:
            self.kind = "function"
        else:
            self.kind = "both"

    def has(self, n: int) -> str:
        """How many points the sweep covers, named by their source:
        `the claim ranges over 3 points`, `the function's domain has 3
        points`."""
        if self.kind == "claim":
            return f"the claim ranges over {_points(n)}"
        if self.kind == "function":
            return f"the function's domain has {_points(n)}"
        return (f"the claim's binding with the function's domain gives "
                f"{_points(n)}")

    def holds(self) -> str:
        """The subject a holding claim is then named by."""
        return "it" if self.kind == "claim" else "the claim"

    def quantifier(self, names: list, n: int) -> str:
        """The `∀` line of a proof over the swept points."""
        where = {"claim": "the claim's finite scope",
                 "function": "the function's finite domain",
                 "both": "the claim's binding with the function's finite "
                         "domain"}[self.kind]
        return f"∀ {', '.join(names)} in {where} ({_points(n)})"


def _holds_at(total: int, judged: list, scope: _Scope) -> str:
    """The proof sketch of a claim checked at every point of a finite
    set, counting the points where the function gave no value to
    compare apart from the ones the claim was compared at."""
    others = total - len(judged)
    if others == 0:
        if total == 1:
            return (f"{scope.has(1)}, {_point_words(judged[0])}, "
                    f"and {scope.holds()} holds there")
        return f"{scope.has(total)}, and {scope.holds()} holds at every one"
    where = (_point_words(judged[0]) if len(judged) == 1
             else f"the {len(judged)} points where f returns a value")
    rest = ("the other point gives no value, so it is recorded, not compared"
            if others == 1 else
            f"the other {others} give no value, so they are recorded, not compared")
    return f"{scope.has(total)}; {scope.holds()} holds at {where}, and {rest}"


def _lists_a_sentinel(cj_domain: dict, names: list) -> bool:
    """Whether any swept parameter's finite set lists a sentinel."""
    return any(cj_domain.get(n) is not None
               and _set_sentinels(_as_domain(cj_domain[n])) for n in names)


def _raised_at(fn, facts, point: dict) -> "str | None":
    """The exception type the function raises when called with `point`
    as its arguments, or None when it returns (or the point does not
    name every parameter)."""
    if any(p not in point for p in facts.params):
        return None
    try:
        call(fn, *[point[p] for p in facts.params])
    except Exception as e:
        return type(e).__name__
    return None


def _exactly_at(cj, evaluate, point: dict) -> tuple:
    """Intent:
        `(holds, sides)`: the claim at `point` decided in exact
        arithmetic (`conjecture._exact_relation`), its coordinates read
        as written and the function run on those exact values
        (`evaluate.exact_as_written`), under the fast wall-clock cap.
        `(None, None)` when a side has no exact value there (a float
        the function computed, a square root, a value that is not a
        number) or the cap fires.
    """
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .conjecture import _exact_relation
    written = getattr(evaluate, "exact_as_written", None)
    if written is None:
        return None, None
    try:
        sides = _with_timeout(lambda: written(point), FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None, None
    if sides is None:
        return None, None
    try:
        held = _exact_relation(cj, sides[0], sides[1])
    except (TypeError, ValueError, ArithmeticError):
        return None, None
    return held, (sides if held is not None else None)


class _Precision:
    """How far the floats of an exhaustive sweep missed the relation:
    the largest miss over the points compared and the allowance applied
    at that point (`gates` evaluate's `last_precision`, from
    `_allowance.float_miss`), as the `mathema.sweep_precision` record:
    `points` compared, `largest_miss`, `allowance`, `at` (the point of
    the largest miss) and `representation` (`float64`)."""

    def __init__(self):
        self.points = 0
        self.miss = None
        self.allowance = None
        self.at = None

    def add(self, measured, where) -> None:
        """Count a point's `(miss, allowance)`, `where` its text or a
        callable giving it; None (no numbers compared) counts nothing."""
        if measured is None:
            return
        gap, allowance = measured
        self.points += 1
        if self.miss is None or gap > self.miss:
            self.miss, self.allowance = gap, allowance
            self.at = where() if callable(where) else where

    def meta(self) -> dict:
        if self.points == 0:
            return {}
        return {"mathema.sweep_precision": {
            "points": self.points, "largest_miss": self.miss,
            "allowance": self.allowance, "at": self.at,
            "representation": "float64"}}


def _exact_text(value) -> str:
    """An exact value as text: an integer or a ratio (`1/2`), a list
    of them in brackets, a bool as itself."""
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_exact_text(v) for v in value) + "]"
    return str(value)


def _exact_witness_words(at: str, sides, computed) -> dict:
    """Intent:
        The record of a point where the claim is false in exact
        arithmetic: `at` (the point), `reading` (`mathematics`: the
        function run on the point's exact values), `exact` (the two
        sides exactly, `20000001/40000000 vs 1/2`) and `computed` (the
        two sides the float computation gave there).
    """
    from .probing import _fmt_coordinate, _fmt_value

    def shown(v):
        # every digit a float holds: the two sides may differ in the
        # last of them
        return _fmt_coordinate(v) if isinstance(v, float) else _fmt_value(v)
    left, right = computed if computed is not None else (None, None)
    return {"at": at, "reading": "mathematics",
            "exact": f"{_exact_text(sides[0])} vs {_exact_text(sides[1])}",
            "computed": f"{shown(left)} vs {shown(right)}"}


def _inexact_words(inexact: list, names: list) -> str:
    """Where the claim could not be decided exactly, in words: `at x =
    1 the function's value cannot be computed exactly`, with a count of
    the other such points."""
    from .gates import _fmt_point
    first = _fmt_point(inexact[0], names)
    others = len(inexact) - 1
    more = ("" if others == 0 else
            f" (nor at {others} other point{'s' if others != 1 else ''})")
    return f"at {first} the claim's value cannot be computed exactly{more}"


def _exact_lhs(code, point: dict, fn, bound: dict):
    """Intent:
        The membership claim's left side at `point` in exact arithmetic:
        the point's coordinates read as written, f and the claim's bound
        functions run on those exact values, under the fast wall-clock
        cap. None when the value is not exact there or the cap fires.
    """
    from ._exact_side import exact_sides
    from ._exact_body import exact_twin
    from ._math_vocab import MATH_CONSTANTS
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .conjecture import _SAFE_FUNCS
    from .gates import _written_exactly
    env = {**_SAFE_FUNCS, **MATH_CONSTANTS, **bound,
           **{n: _written_exactly(v) for n, v in point.items()}}
    # each body read exactly, the function itself where it cannot be
    callees = {"f": exact_twin(fn) or fn,
               **{n: exact_twin(v) or v for n, v in bound.items()}}
    try:
        sides = _with_timeout(
            lambda: exact_sides(code, None, env, callees,
                                exact_calls=True, opaque_results=True),
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    return None if sides is None else sides[0]


def _exact_member(value, bound) -> "bool | None":
    """Intent:
        Whether the exact `value` (an int or Fraction, or a nested list
        of them for a space) is a member of the domain `bound`, each
        listed member and interval end read as written: a finite set
        by equality, an interval by its ends, a `Z` or `N` type by
        integrality (and sign), an excluded value never. None when the
        membership cannot be decided exactly (a value that is not a
        real number, a complex, language or string domain, a piece that
        is not a set or an interval).
    """
    import dataclasses
    import math
    from fractions import Fraction

    from ._exact_witness import Undecided, in_bound
    from .domain import _as_domain, _sentinel_piece
    dom = _as_domain(bound)
    if dom.dims:
        leaves: list = []

        def collect(v):
            if isinstance(v, (list, tuple)):
                for u in v:
                    collect(u)
            else:
                leaves.append(v)
        collect(value)
        element = dataclasses.replace(dom, dims=())
        said = [_exact_member(v, element) for v in leaves]
        return None if any(s is None for s in said) else all(said)
    if dom.base_type not in ("R", "Z", "N"):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
        return None
    q = Fraction(value)

    def written(m):
        if isinstance(m, bool) or not isinstance(m, (int, float)):
            return None
        if isinstance(m, float):
            return Fraction(repr(m)) if math.isfinite(m) else None
        return Fraction(m)
    if any(written(m) == q for m in dom.excluded):
        return False
    if dom.base_type in ("Z", "N") and q.denominator != 1:
        return False
    if dom.base_type == "N" and q < 0:
        return False
    if not dom.pieces:
        return True
    pieces = [p for p in dom.pieces if not _sentinel_piece(p)]
    if not pieces:
        return None
    for piece in pieces:
        if isinstance(piece, frozenset):
            if any(isinstance(m, complex) for m in piece):
                return None
            if any(written(m) == q for m in piece):
                return True
        elif isinstance(piece, tuple) and len(piece) == 2:
            try:
                if in_bound(q, piece):
                    return True
            except Undecided:
                return None
        else:
            return None
    return False


def _membership_proof(cj, fn, facts, cj_domain, bound_funcs, budget: int,
                      resolution: "dict | None"):
    """Intent:
        The sweep of a membership claim (`f(x) in {missing}`) over a
        finite domain: the value at every point is tested against the
        right-hand side, a missing value by its kind, a number by its
        float value and then by its exact value (`_exact_lhs`,
        `_exact_member`). `proven` when each point agrees with the
        relation exactly, `disproven` at the first that does not in
        floats, or else at the first whose exact value answers the
        other way (`mathema.exact_witness`); `undecided` with
        `mathema.sweep_holds` and `mathema.sweep_inexact` when the
        floats agree but some value has no exact reading; None when the
        domain is not finite or a point's value cannot be computed.
    """
    from .conjecture import _SAFE_FUNCS, _membership_member
    from ._math_vocab import MATH_CONSTANTS
    from .gates import _fmt_point
    names = [p for p in facts.params if p in cj_domain]
    if not names or any(p not in cj_domain for p in facts.params):
        return None
    grid = _sweep_grid(names, cj_domain, budget, resolution)
    if grid is None:
        return None
    try:
        code = compile(cj.lhs, "<membership>", "eval")
    except SyntaxError:
        return None
    from .probing import holds_nan
    wanted = cj.relation == "in"
    checked = 0
    # the points whose value could not be computed exactly, and the
    # first point whose exact value answers the membership the other
    # way from its float value
    inexact: list = []
    exact_miss = None
    # a float value is a member by exact equality: the floats miss by
    # nothing, under no allowance
    precision = _Precision()
    executed, f_call = ExecutedMissing(), LastCall()
    from .probing import parameter_defaults
    f_call.defaults = parameter_defaults(fn)
    recorded = f_call.wrap(fn)
    bound = dict(bound_funcs or {})
    for combo in itertools.product(*(grid[n] for n in names)):
        point = dict(zip(names, combo))
        env = {**_SAFE_FUNCS, **MATH_CONSTANTS, **bound,
               "f": recorded, **point}
        where = _fmt_point(point, names)
        try:
            value = eval(code, {"__builtins__": {}}, env)
        except Exception:
            f_call.record(executed, point)
            raised = _raised_at(fn, facts, point)
            if raised is None:
                return None
            return ProofResult(
                "disproven", sketch=f"at {where} the function raised {raised}",
                counterexample=f"{where}: raised {raised}", witness=dict(point),
                meta=with_executed({"mathema.derive_route": "brute_force",
                                    **_tried(grid),
                                    "mathema.witness_executed": True}, executed))
        f_call.record(executed, point)
        if _membership_member(value, cj.rhs_bound) != wanted:
            return ProofResult(
                "disproven",
                sketch=f"at {where} the value {value!r} is "
                       f"{'not ' if wanted else ''}in {cj.rhs}",
                counterexample=f"{where}: {value!r} is "
                               f"{'not ' if wanted else ''}in {cj.rhs}",
                witness=dict(point),
                meta=with_executed({"mathema.derive_route": "brute_force",
                                    **_tried(grid),
                                    "mathema.witness_executed": True}, executed))
        checked += 1
        last = point
        if not holds_number(value) or holds_nan(value):
            # a missing value is tested by its kind, a value that is not
            # a number by its own equality: both exact
            continue
        precision.add((0.0, 0.0), where)
        # the float value agrees; the claim is decided at the point's
        # exact value
        exact = _exact_lhs(code, point, fn, bound)
        member = None if exact is None else _exact_member(exact, cj.rhs_bound)
        if member is None:
            inexact.append(point)
        elif member != wanted and exact_miss is None:
            exact_miss = (point, exact, value)
    if checked == 0:
        return None
    is_in = _membership_words(cj.rhs, wanted)
    if exact_miss is not None:
        point, exact, value = exact_miss
        where = _fmt_point(point, names)
        exact_is = (f"{_exact_text(exact)} is {'not ' if wanted else ''}"
                    f"in {cj.rhs}")
        return ProofResult(
            "disproven",
            sketch=(f"at {where} the value is {_exact_text(exact)} in exact "
                    f"arithmetic, which is {'not ' if wanted else ''}in "
                    f"{cj.rhs}; the float computation's value {value!r} "
                    f"{is_in}"),
            counterexample=(f"{where}: {value!r} {is_in} in float, but "
                            f"false here in exact arithmetic ({exact_is})"),
            witness=dict(point),
            meta=with_executed({"mathema.derive_route": "brute_force",
                                **_tried(grid),
                                "mathema.witness_executed": True,
                                "mathema.exact_witness": {
                                    "at": where, "reading": "mathematics",
                                    "exact": exact_is,
                                    "computed": f"{value!r} {is_in}",
                                    "computation":
                                        "holds within its allowance"}},
                               executed))
    if inexact:
        return ProofResult(
            "undecided",
            sketch=(f"{_Scope(cj, names).has(checked)}, and at every one the "
                    f"float value {is_in}; proven needs the claim decided "
                    f"exactly at every point, and "
                    f"{_inexact_words(inexact, names)}"),
            meta=with_executed({"mathema.derive_route": "brute_force",
                                "mathema.sweep_holds": True, **_tried(grid),
                                "mathema.sweep_inexact": {
                                    "points": len(inexact),
                                    "first": _fmt_point(inexact[0], names)},
                                **precision.meta()},
                               executed))
    return ProofResult(
        "proven",
        sketch=(f"at the only point, {_point_words(last)}, f({names[0]}) {is_in}"
                if checked == 1 and len(names) == 1 else
                f"{_Scope(cj, names).has(checked)}, and at every one "
                f"the value {is_in}"),
        quantifier=_Scope(cj, names).quantifier(names, checked),
        meta=with_executed({"mathema.derive_route": "brute_force", **_tried(grid)},
                           executed))


def _raises_proof(cj, fn, facts, cj_domain, bound_funcs, budget: int,
                  resolution: "dict | None"):
    """Intent:
        The sweep of a `raises(...)` claim over a finite domain: every
        point must make the function raise (the stated exception, when
        one is named). `proven` when each does, `disproven` at the first
        point where the call returns or raises another exception, None
        when the domain is not finite or a point's call fails before
        reaching the function.
    """
    from .conjecture import _SAFE_FUNCS, _resolve_exception_type
    from ._math_vocab import MATH_CONSTANTS
    from .gates import _fmt_point
    names = [p for p in facts.params if p in cj_domain]
    if not names or any(p not in cj_domain for p in facts.params):
        return None
    grid = _sweep_grid(names, cj_domain, budget, resolution)
    if grid is None:
        return None
    wanted = _resolve_exception_type(cj.rhs, fn) if cj.rhs else None
    if cj.rhs and wanted is None:
        return None
    try:
        code = compile(cj.lhs, "<raises>", "eval")
    except SyntaxError:
        return None
    checked = 0
    executed, f_call = ExecutedMissing(), LastCall()
    from .probing import parameter_defaults
    f_call.defaults = parameter_defaults(fn)
    bound = dict(bound_funcs or {})
    for combo in itertools.product(*(grid[n] for n in names)):
        point = dict(zip(names, combo))
        raised: list = []

        def tagged(*args, **kwargs):
            try:
                return call(fn, *args, **kwargs)
            except Exception as e:
                raised.append(e)
                raise

        env = {**_SAFE_FUNCS, **MATH_CONSTANTS, **bound,
               "f": f_call.wrap(tagged), **point}
        where = _fmt_point(point, names)
        try:
            value = eval(code, {"__builtins__": {}}, env)
        except Exception:
            f_call.record(executed, point)
            if not raised:
                return None
            if wanted is not None and not isinstance(raised[0], wanted):
                return ProofResult(
                    "disproven",
                    sketch=f"at {where} the call raised "
                           f"{exception_name(raised[0])}, not {cj.rhs}",
                    counterexample=f"{where}: raised "
                                   f"{exception_name(raised[0])}, claimed {cj.rhs}",
                    witness=dict(point),
                    meta=with_executed({"mathema.derive_route": "brute_force",
                                        **_tried(grid)}, executed))
            checked += 1
            last = point
            continue
        f_call.record(executed, point)
        return ProofResult(
            "disproven",
            sketch=f"at {where} the call returned {value!r} instead of raising",
            counterexample=f"{where}: returned {value!r} instead of raising",
            witness=dict(point),
            meta=with_executed({"mathema.derive_route": "brute_force",
                                **_tried(grid)}, executed))
    if checked == 0:
        return None
    return ProofResult(
        "proven",
        sketch=(f"the only point, {_point_words(last)}, raises"
                if checked == 1 else
                f"{_Scope(cj, names).has(checked)}, and the call "
                f"raises at every one"),
        quantifier=_Scope(cj, names).quantifier(names, checked),
        meta=with_executed({"mathema.derive_route": "brute_force", **_tried(grid)},
                           executed))


def brute_force_proof(cj, fn, facts, cj_domain, bound_funcs, assumption=(),
                      budget: int | None = None,
                      resolution: "dict | None" = None):
    """Intent:
        A `ProofResult` for a claim whose declared domain is finite and
        small enough to visit entirely, or `None` when the claim is not
        a candidate for this route at all.

        `proven` when every admitted point satisfies the claim exactly:
        the float evaluation agrees there, and so does the claim decided
        in exact arithmetic (`_exactly_at`: the point read as written,
        the function run on its exact values), unless neither side holds
        a number. `disproven` with the witnessing point when the float
        evaluation fails at one, or when one is false in exact
        arithmetic while the float computation agrees there within its
        allowance (`mathema.exact_witness` records it). `undecided` with
        `mathema.sweep_holds` and `mathema.sweep_inexact` when every
        point agrees in floats but some point has no exact value, a
        float the function computed for one: the computation holds,
        and nothing proves the mathematics.

    Raises:
        Nothing. A claim this route cannot decide comes back `None` and
        the caller carries on with the symbolic routes.

    Notes:
        Declines, each for its own reason:

        - `facts.is_pure is not True`, or the strict examination
          (`_examine.examine`) of the body and every project function it
          reaches finds a write, a hidden input, an order-sensitive
          reduction or anything it cannot read. Note the spelling: `None` means
          purity could not be established, which is not the same as
          pure, and treating it as pure would rest a proof on an
          unexamined function.
        - any parameter whose domain is not finite, or a grid over
          `budget` (`_sweep_grid`).
        - `gates._point_evaluator` declining, which it does for a
          sequence parameter, a non-value relation, or a law it cannot
          compile.
        - any admitted point the evaluator cannot decide. One such
          point means the sweep is incomplete, and an incomplete sweep
          is not a proof of anything.

        A point the domain admits at which the function RAISES is a
        falsification, not a decline: a value claim is a claim that the
        function returns a value there. That is the pedantic-verdict
        rule the rest of the engine follows, and the point evaluator
        already reports such a point as a genuine counterexample.
    """
    if facts.is_pure is not True:
        return None
    # a counterexample the sweep executes falsifies though a callee is
    # unreadable; only a clean sweep's proof needs the strict
    # examination to find nothing. A detected write or hidden read
    # declines the sweep: there a point's result depends on the calls
    # before it
    unexamined = _examination_obstacle(fn)
    if unexamined is _STATEFUL:
        return None
    # read at call time, not bound as a default, so the budget stays one
    # knob rather than a value frozen when this module was imported
    budget = BRUTE_FORCE_POINT_BUDGET if budget is None else budget
    if unexamined is not None and (
            cj.relation == "raises" or (cj.relation in ("in", "not in") and
                                        getattr(cj, "rhs_bound", None) is not None)):
        return None
    if cj.relation == "raises":
        return None if assumption else _raises_proof(
            cj, fn, facts, cj_domain, bound_funcs, budget, resolution)
    if cj.relation in ("in", "not in") and getattr(cj, "rhs_bound", None) is not None:
        return None if assumption else _membership_proof(
            cj, fn, facts, cj_domain, bound_funcs, budget, resolution)
    from .gates import _fmt_point, _point_evaluator
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assumption)
    if deps is None:
        return None
    names = list(deps["names"])
    grid = _sweep_grid(names, cj_domain, budget, resolution)
    if grid is None:
        return None
    grid, no_value = _within_path_bindings(grid, cj_domain)
    outside = (f"; {no_value} member{'s' if no_value != 1 else ''} outside "
               f"the binding: the path has no value" if no_value else "")
    counted = {"mathema.path_no_value": no_value} if no_value else {}
    evaluate, admits = deps["evaluate"], deps["admits"]

    plan = _sweep_plan(cj, fn, facts, names, grid, deps)
    checked = 0
    total = 0
    judged: list = []
    # the points the claim could not be decided at exactly, and the
    # first point it is false at exactly while the float computation
    # agrees within its allowance
    inexact: list = []
    exact_miss = None
    # how far the floats missed over the points compared
    precision = _Precision()
    for point in (plan.points if plan is not None else
                  (dict(zip(names, combo))
                   for combo in itertools.product(*(grid[n] for n in names)))):
        if not admits(point):
            # outside the region the claim covers (an exclusion, or a
            # premise this point fails), so it is not ours to decide
            continue
        total += 1
        verdict = evaluate(point)
        executed = executed_missing(deps)
        if verdict is None and executed is not None and executed.last_classified:
            # a raise or a missing output at a missing input: classified
            # into the executed, not judged
            continue
        if verdict is None:
            return None
        if verdict is False:
            raised = _raised_at(fn, facts, point)
            also: dict = ({"mathema.exact_witness": {
                **exact_miss[2], "computation":
                    f"fails at {_fmt_point(point, names)}"}}
                    if exact_miss is not None else {})
            return ProofResult(
                "disproven",
                sketch=f"the claim fails at {_fmt_point(point, names)}"
                       + (f", where the function raised {raised}" if raised else "")
                       + (", found by checking every point of a finite domain"
                          if plan is None else
                          f", found among the points run "
                          f"{plan.coverage.words(checked + 1)}"),
                counterexample=_fmt_point(point, names),
                witness=dict(point),
                # the witness is a call of the real function at a point
                # the domain admits: an executed witness, which the
                # corroboration gate keeps as it is
                meta=with_executed(
                    {"mathema.derive_route": "brute_force",
                     "mathema.witness_executed": True, **_tried(grid),
                     **counted, **also,
                     # a value a listed sentinel stands for is only
                     # reproduced by calling with that same value
                     **({"mathema.witness_executed": True}
                        if _lists_a_sentinel(cj_domain, names)
                        or unexamined is not None else {})},
                    executed_missing(deps)))
        checked += 1
        judged.append(point)
        precision.add(evaluate.last_precision(),
                      lambda: _fmt_point(point, names))
        if not holds_number(evaluate.sides()):
            # sides with no number in them (a string, a bool, a missing
            # value) were compared by their own equality, which is exact
            continue
        said, sides = _exactly_at(cj, evaluate, point)
        if said is None:
            inexact.append(point)
        elif said is False and exact_miss is None:
            exact_miss = (point, sides, _exact_witness_words(
                _fmt_point(point, names), sides, evaluate.sides()))
    if exact_miss is not None:
        point, _sides, witness = exact_miss
        where = ("found by checking every point of a finite domain"
                 if plan is None else
                 f"found among the points run {plan.coverage.words(checked)}")
        return ProofResult(
            "disproven",
            sketch=(f"the claim is false at {witness['at']} in exact "
                    f"arithmetic ({witness['exact']}), {where}; the float "
                    f"computation agrees at every point run, within its "
                    f"allowance"),
            counterexample=(f"{witness['at']}: {witness['computed']}, within "
                            f"the float tolerance but false here in exact "
                            f"arithmetic ({witness['exact']})"),
            witness=dict(point),
            meta=with_executed(
                {"mathema.derive_route": "brute_force",
                 "mathema.witness_executed": True, **_tried(grid),
                 **counted,
                 "mathema.exact_witness": {
                     **witness, "computation": "holds within its allowance"}},
                executed_missing(deps)))
    if checked == 0:
        # every point was excluded: nothing was actually verified, and a
        # clean pass over no points proves nothing while looking like a
        # proof
        return None
    if plan is not None:
        # part of the domain ran: no proof, and the record says how much
        return ProofResult(
            "undecided",
            sketch=f"the domain sweep ran part of the domain "
                   f"{plan.coverage.words(checked)}",
            meta={"mathema.sweep_partial": plan.coverage.words(checked)})
    no_exact = ({"mathema.sweep_inexact": {
        "points": len(inexact), "first": _fmt_point(inexact[0], names)},
        **precision.meta()} if inexact else {})
    if unexamined is not None:
        return ProofResult(
            "undecided",
            sketch=(f"{_holds_at(total, judged, _Scope(cj, names))}{outside}; every point "
                    f"executed; proven needs the function to be shown "
                    f"pure: {unexamined}"),
            meta=with_executed({"mathema.derive_route": "brute_force",
                                "mathema.sweep_holds": True, **_tried(grid),
                                **counted, **no_exact},
                               executed_missing(deps)))
    if inexact:
        return ProofResult(
            "undecided",
            sketch=(f"{_holds_at(total, judged, _Scope(cj, names))}{outside}, "
                    f"within the computation allowance; proven needs the "
                    f"claim decided exactly at every point, and "
                    f"{_inexact_words(inexact, names)}"),
            meta=with_executed({"mathema.derive_route": "brute_force",
                                "mathema.sweep_holds": True, **_tried(grid),
                                **counted, **no_exact},
                               executed_missing(deps)))
    return ProofResult(
        "proven",
        sketch=_holds_at(total, judged, _Scope(cj, names)) + outside,
        quantifier=_Scope(cj, names).quantifier(names, total),
        meta=with_executed({"mathema.derive_route": "brute_force", **_tried(grid),
                            **counted},
                           executed_missing(deps)))


_STATEFUL = object()

#: the relations a ground claim is evaluated for: a value relation the
#: point evaluator decides
_GROUND_RELATIONS = frozenset({"==", "~=", "!=", "<=", ">=", "<", ">"})


def _calls_f(cj) -> bool:
    """Whether either side of the claim calls f."""
    import ast
    for side in (cj.lhs, cj.rhs):
        try:
            tree = ast.parse(side or "0", mode="eval")
        except SyntaxError:
            return False
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "f" for n in ast.walk(tree)):
            return True
    return False


def _call_text(fn, facts, args: tuple, kwargs: dict) -> str:
    """One call's arguments as a point, `x = nan, k = 2`, each named by
    the parameter it binds; the arguments as written, `f(nan, 2)`, when
    they do not bind by name."""
    from .gates import _fmt_point
    params = list(facts.params)
    if len(args) <= len(params) and all(k in params for k in kwargs):
        point = {**dict(zip(params, args)), **kwargs}
        return _fmt_point(point, [p for p in params if p in point])
    return _written_call(args, kwargs)


def _written_call(args: tuple, kwargs: dict) -> str:
    """A call as written, `f(1, k=2)`."""
    from .probing import _fmt_coordinate, _fmt_value

    def shown(v):
        return _fmt_coordinate(v) if isinstance(v, float) else _fmt_value(v)
    parts = [shown(a) for a in args] + [
        f"{k}={shown(v)}" for k, v in kwargs.items()]
    return f"f({', '.join(parts)})"


def _ground_witness(fn, facts, calls: list) -> str:
    """Intent:
        The calls a ground claim's evaluation made, as its witness: the
        raising call when one raised, else the one call made (`xs =
        []`), else every distinct call as written (`f(1), f(2)`).
    """
    raised = [c for c in calls if c[0] == "raised"]
    shown = raised[-1:] if raised else calls
    distinct: list = []
    for _kind, _out, args, kwargs in shown:
        key = (repr(args), repr(sorted(kwargs.items())))
        if key not in [k for k, _a, _kw in distinct]:
            distinct.append((key, args, kwargs))
    if len(distinct) == 1:
        _key, args, kwargs = distinct[0]
        return _call_text(fn, facts, args, kwargs)
    return ", ".join(_written_call(args, kwargs)
                     for _key, args, kwargs in distinct)


def ground_proof(cj, fn, facts, bound_funcs):
    """Intent:
        A `ProofResult` for a ground claim, one that names no variable
        and calls f only at literal arguments (`f(nan) == 0`, `f([]) ==
        0`): the claim evaluated once, at its own calls. `disproven`
        when it fails there, the calls as the witness (`x = nan: raised
        ValueError`, `xs = []: 0.0 vs 1`), or when it is false there in
        exact arithmetic while the float computation agrees
        (`mathema.exact_witness`); `proven` when it holds exactly and
        the function is shown pure; `undecided` with
        `mathema.sweep_holds` when it holds but purity is not shown, or
        when its value has no exact reading (`mathema.sweep_inexact`).
        None when the claim is not ground or the evaluation cannot
        decide it.

    Notes:
        The relation is decided by the corroboration gate's point
        evaluator (`gates._point_evaluator`) at the empty point, so the
        computation allowance, the raise rule and the no-value rule are
        the ones every executed witness is judged by. A parameter the
        claim never reads is no coordinate of that point: each call
        binds what the claim passes it, and nothing is drawn.
    """
    if cj.relation not in _GROUND_RELATIONS or cj.links or cj.free_vars \
            or cj.domain or cj.assuming or not _calls_f(cj):
        return None
    from .gates import _point_evaluator
    deps = _point_evaluator(cj, fn, facts, {}, bound_funcs, sequences=True)
    if deps is None or deps["names"]:
        return None
    evaluate = deps["evaluate"]
    verdict = evaluate({})
    calls = evaluate.calls()
    if verdict is None or not calls:
        return None
    witness = _ground_witness(fn, facts, calls)
    if verdict is False:
        raised = [c for c in calls if c[0] == "raised"]
        sides = evaluate.sides()
        if raised:
            detail = f"raised {raised[-1][1]}"
        elif sides is not None:
            from .probing import holds_nan
            detail = f"{sides[0]!r} vs {sides[1]!r}" + (
                ", and a nan is no value" if any(holds_nan(v) for v in sides)
                else "")
        else:
            found = deps["probe_finite"]({})
            detail = found if isinstance(found, str) else "the claim fails"
        return ProofResult(
            "disproven",
            sketch=f"the claim fails at its own call, {witness}",
            counterexample=f"{witness}: {detail}",
            witness={},
            meta=with_executed({"mathema.derive_route": "brute_force",
                                "mathema.witness_executed": True},
                               executed_missing(deps)))
    computed = evaluate.sides()
    said, sides = ((None, None) if not holds_number(computed)
                   else _exactly_at(cj, evaluate, {}))
    if said is False:
        found = _exact_witness_words(witness, sides, computed)
        return ProofResult(
            "disproven",
            sketch=(f"the claim is false at its own call, {witness}, in "
                    f"exact arithmetic ({found['exact']}); the float "
                    f"computation agrees there within its allowance"),
            counterexample=(f"{witness}: {found['computed']}, within the "
                            f"float tolerance but false here in exact "
                            f"arithmetic ({found['exact']})"),
            witness={},
            meta=with_executed({"mathema.derive_route": "brute_force",
                                "mathema.witness_executed": True,
                                "mathema.exact_witness": {
                                    **found, "computation":
                                        "holds within its allowance"}},
                               executed_missing(deps)))
    sketch = f"the claim holds at its own call, {witness}"
    if said is None and holds_number(computed):
        precision = _Precision()
        precision.add(evaluate.last_precision(), witness)
        return ProofResult(
            "undecided",
            sketch=(f"{sketch}, within the computation allowance; proven "
                    f"needs the claim decided exactly there, and its value "
                    f"cannot be computed exactly"),
            meta=with_executed({"mathema.derive_route": "brute_force",
                                "mathema.sweep_holds": True,
                                "mathema.sweep_inexact": {
                                    "points": 1, "first": witness},
                                **precision.meta()},
                               executed_missing(deps)))
    if facts.is_pure is not True or _examination_obstacle(fn) is not None:
        return ProofResult(
            "undecided",
            sketch=(f"{sketch}; proven needs the function to be shown "
                    f"pure, and one call says nothing about the next"),
            meta=with_executed({"mathema.derive_route": "brute_force",
                                "mathema.sweep_holds": True},
                               executed_missing(deps)))
    return ProofResult(
        "proven", sketch=sketch,
        meta=with_executed({"mathema.derive_route": "brute_force"},
                           executed_missing(deps)))


def _examination_obstacle(fn):
    """Intent:
        What stands between a clean sweep of `fn` and a proof: None when
        the strict examination finds nothing (`_examined_clean`), the
        text of the first site it cannot read when that is all it finds,
        and `_STATEFUL` when it finds a write, a hidden read or an
        order-sensitive reduction, where a call's result can depend on
        the calls before it and no point of the sweep stands alone.
    """
    from ._examine import examine
    effects = examine(fn)
    if (effects.writes or effects.hidden_reads or effects.order_sensitive
            or effects.unknown_writes):
        return _STATEFUL
    fixed = {text for _module, _name, text in effects.module_reads}
    for site in effects.unknowns:
        if site.text not in fixed:
            return str(site.text)
    return None


def _sweep_plan(cj, fn, facts, names, grid, deps):
    """Intent:
        None when every point of the grid fits `_SWEEP_SECONDS` by a
        timed estimate of one point; otherwise the partial plan
        (`gates._FinitePlan`): every point at a discontinuity
        (`_discontinuities`), then a seeded sample of `_PARTIAL_SAMPLE`
        admitted points.
    """
    import random
    import time

    from . import _discontinuities as D
    from ._sampling import _RNG_SEED
    from .gates import _FinitePlan
    admits = deps["admits"]
    points = [pt for pt in D.grid_points(names, grid) if admits(pt)]
    if not points:
        return None
    trial = points[::max(1, len(points) // 5)][:5]
    started = time.perf_counter()
    for pt in trial:
        # a point's cost is its float evaluation and its exact one
        try:
            deps["evaluate"](pt)
        except Exception:
            pass
        _exactly_at(cj, deps["evaluate"], pt)
    per_point = (time.perf_counter() - started) / max(1, len(trial))
    if per_point * len(points) <= _SWEEP_SECONDS:
        return None
    found = D.discontinuities(cj, fn, facts)
    hits = D.on_grid(found, points)
    rng = random.Random(_RNG_SEED)
    sample = rng.sample(points, min(_PARTIAL_SAMPLE, len(points)))
    return _FinitePlan(hits + sample, len(sample), D.Coverage(
        total=len(points), at_discontinuities=len(hits),
        discontinuity_words=D.words_of(found), random=len(sample)))


def _examined_clean(fn) -> bool:
    """Whether the strict examination of `fn` finds nothing that could
    make two calls at one point differ or leave something behind.

    Notes:
        A read of a module-level value the call itself never writes is
        no obstacle: nothing but the sweep runs while it lasts, so that
        value is the same at every point it visits."""
    from ._examine import examine
    effects = examine(fn)
    fixed = {text for _module, _name, text in effects.module_reads}
    return not (effects.writes or effects.hidden_reads
                or effects.order_sensitive
                or effects.unknown_writes
                or any(site.text not in fixed for site in effects.unknowns))
