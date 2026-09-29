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

from .domain import _as_domain, _set_sentinels, finite_members
from .probing import ExecutedMissing, LastCall, executed_missing, with_executed
from .symbolic import ProofResult

__all__ = ["BRUTE_FORCE_POINT_BUDGET", "brute_force_proof"]

#: the most points one claim's sweep will visit. A domain larger than
#: this declines rather than being truncated: the budget bounds the work
#: mathema will do, never the region a verdict covers.
BRUTE_FORCE_POINT_BUDGET = 100_000


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


def _holds_at(total: int, judged: list) -> str:
    """The proof sketch of a claim checked at every point of a finite
    domain, counting the points where the function gave no value to
    compare apart from the ones the claim was compared at."""
    others = total - len(judged)
    if others == 0:
        if total == 1:
            return (f"the declared domain has one point, {_point_words(judged[0])}, "
                    f"and the claim holds there")
        return f"the declared domain has {total} points, and the claim holds at every one"
    where = (_point_words(judged[0]) if len(judged) == 1
             else f"the {len(judged)} points where f returns a value")
    rest = ("the other point gives no value, so it is recorded, not compared"
            if others == 1 else
            f"the other {others} give no value, so they are recorded, not compared")
    return (f"the declared domain has {total} points; the claim holds at {where}, "
            f"and {rest}")


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
        fn(*[point[p] for p in facts.params])
    except Exception as e:
        return type(e).__name__
    return None


def _membership_proof(cj, fn, facts, cj_domain, bound_funcs, budget: int,
                      resolution: "dict | None"):
    """Intent:
        The sweep of a membership claim (`f(x) in {missing}`) over a
        finite domain: the value at every point is tested against the
        right-hand side, a missing value by its kind. `proven` when each
        point agrees with the relation, `disproven` at the first that
        does not, None when the domain is not finite or a point's value
        cannot be computed.
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
    wanted = cj.relation == "in"
    checked = 0
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
    if checked == 0:
        return None
    is_in = _membership_words(cj.rhs, wanted)
    return ProofResult(
        "proven",
        sketch=(f"at the only point, {_point_words(last)}, f({names[0]}) {is_in}"
                if checked == 1 and len(names) == 1 else
                f"the declared domain has {_points(checked)}, and at every one "
                f"the value {is_in}"),
        quantifier=f"∀ {', '.join(names)} in the declared finite domain "
                   f"({_points(checked)})",
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
                return fn(*args, **kwargs)
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
                           f"{type(raised[0]).__name__}, not {cj.rhs}",
                    counterexample=f"{where}: raised "
                                   f"{type(raised[0]).__name__}, claimed {cj.rhs}",
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
                f"the declared domain has {_points(checked)}, and the call "
                f"raises at every one"),
        quantifier=f"∀ {', '.join(names)} in the declared finite domain "
                   f"({_points(checked)})",
        meta=with_executed({"mathema.derive_route": "brute_force", **_tried(grid)},
                           executed))


def brute_force_proof(cj, fn, facts, cj_domain, bound_funcs, assumption=(),
                      budget: int | None = None,
                      resolution: "dict | None" = None):
    """Intent:
        A `ProofResult` for a claim whose declared domain is finite and
        small enough to visit entirely, or `None` when the claim is not
        a candidate for this route at all.

        `proven` when every admitted point satisfies the claim,
        `disproven` with the witnessing point when one does not.

    Raises:
        Nothing. A claim this route cannot decide comes back `None` and
        the caller carries on with the symbolic routes.

    Notes:
        Declines, each for its own reason:

        - `facts.is_pure is not True`. Note the spelling: `None` means
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
    # read at call time, not bound as a default, so the budget stays one
    # knob rather than a value frozen when this module was imported
    budget = BRUTE_FORCE_POINT_BUDGET if budget is None else budget
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
    evaluate, admits = deps["evaluate"], deps["admits"]

    checked = 0
    total = 0
    judged: list = []
    for combo in itertools.product(*(grid[n] for n in names)):
        point = dict(zip(names, combo))
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
            return ProofResult(
                "disproven",
                sketch=f"the claim fails at {_fmt_point(point, names)}"
                       + (f", where the function raised {raised}" if raised else "")
                       + ", found by checking every point of a finite domain",
                counterexample=_fmt_point(point, names),
                witness=dict(point),
                meta=with_executed(
                    {"mathema.derive_route": "brute_force", **_tried(grid),
                     # a value a listed sentinel stands for is only
                     # reproduced by calling with that same value
                     **({"mathema.witness_executed": True}
                        if _lists_a_sentinel(cj_domain, names) else {})},
                    executed_missing(deps)))
        checked += 1
        judged.append(point)
    if checked == 0:
        # every point was excluded: nothing was actually verified, and a
        # clean pass over no points proves nothing while looking like a
        # proof
        return None
    return ProofResult(
        "proven",
        sketch=_holds_at(total, judged),
        quantifier=f"∀ {', '.join(names)} in the declared finite domain "
                   f"({_points(total)})",
        meta=with_executed({"mathema.derive_route": "brute_force", **_tried(grid)},
                           executed_missing(deps)))
