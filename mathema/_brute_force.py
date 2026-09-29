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
    for combo in itertools.product(*(grid[n] for n in names)):
        point = dict(zip(names, combo))
        env = {**_SAFE_FUNCS, **MATH_CONSTANTS, **(bound_funcs or {}),
               "f": fn, **point}
        where = _fmt_point(point, names)
        try:
            value = eval(code, {"__builtins__": {}}, env)
        except Exception:
            raised = _raised_at(fn, facts, point)
            if raised is None:
                return None
            return ProofResult(
                "disproven", sketch=f"at {where} the function raised {raised}",
                counterexample=f"{where}: raised {raised}", witness=dict(point),
                meta={"mathema.derive_route": "brute_force", **_tried(grid),
                      "mathema.witness_executed": True})
        if _membership_member(value, cj.rhs_bound) != wanted:
            return ProofResult(
                "disproven",
                sketch=f"at {where} the value {value!r} is "
                       f"{'not ' if wanted else ''}in {cj.rhs}",
                counterexample=f"{where}: {value!r} is "
                               f"{'not ' if wanted else ''}in {cj.rhs}",
                witness=dict(point),
                meta={"mathema.derive_route": "brute_force", **_tried(grid),
                      "mathema.witness_executed": True})
        checked += 1
    if checked == 0:
        return None
    plural = "point" if checked == 1 else "points"
    return ProofResult(
        "proven",
        sketch=f"the declared domain admits {checked} {plural}, and the "
               f"value at every one is {'' if wanted else 'not '}in {cj.rhs}",
        quantifier=f"∀ {', '.join(names)} in the declared finite domain "
                   f"({checked} {plural})",
        meta={"mathema.derive_route": "brute_force", **_tried(grid)})


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
    for combo in itertools.product(*(grid[n] for n in names)):
        point = dict(zip(names, combo))
        raised: list = []

        def tagged(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                raised.append(e)
                raise

        env = {**_SAFE_FUNCS, **MATH_CONSTANTS, **(bound_funcs or {}),
               "f": tagged, **point}
        where = _fmt_point(point, names)
        try:
            value = eval(code, {"__builtins__": {}}, env)
        except Exception:
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
                    meta={"mathema.derive_route": "brute_force", **_tried(grid)})
            checked += 1
            continue
        return ProofResult(
            "disproven",
            sketch=f"at {where} the call returned {value!r} instead of raising",
            counterexample=f"{where}: returned {value!r} instead of raising",
            witness=dict(point),
            meta={"mathema.derive_route": "brute_force", **_tried(grid)})
    if checked == 0:
        return None
    plural = "point" if checked == 1 else "points"
    return ProofResult(
        "proven",
        sketch=f"the declared domain admits {checked} {plural}, and the "
               f"call raises at every one",
        quantifier=f"∀ {', '.join(names)} in the declared finite domain "
                   f"({checked} {plural})",
        meta={"mathema.derive_route": "brute_force", **_tried(grid)})


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
    for combo in itertools.product(*(grid[n] for n in names)):
        point = dict(zip(names, combo))
        if not admits(point):
            # outside the region the claim covers (an exclusion, or a
            # premise this point fails), so it is not ours to decide
            continue
        verdict = evaluate(point)
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
                meta={"mathema.derive_route": "brute_force", **_tried(grid),
                      # a value a listed sentinel stands for is only
                      # reproduced by calling with that same value
                      **({"mathema.witness_executed": True}
                         if _lists_a_sentinel(cj_domain, names) else {})})
        checked += 1
    if checked == 0:
        # every point was excluded: nothing was actually verified, and a
        # clean pass over no points proves nothing while looking like a
        # proof
        return None
    plural = "point" if checked == 1 else "points"
    return ProofResult(
        "proven",
        sketch=("the declared domain admits exactly 1 point, and the claim "
                "holds there" if checked == 1 else
                f"the declared domain admits {checked} points, and the claim "
                f"holds at every one"),
        quantifier=f"∀ {', '.join(names)} in the declared finite domain "
                   f"({checked} {plural})",
        meta={"mathema.derive_route": "brute_force", **_tried(grid)})
