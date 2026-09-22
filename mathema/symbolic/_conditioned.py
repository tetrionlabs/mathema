# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Domain-conditioned branch pruning: `lift()` refuses any function with
a branch, unconditionally. The functions here extend that for one
specific, narrower case: a branch whose condition compares an
*unmodified signature parameter* (or a local affine in one) against a
literal, where the claim's own *declared domain* for that parameter
settles the condition's truth value throughout, in which case the
branch isn't ambiguous for this claim's domain at all, and lifting can
proceed into whichever side is actually taken. Anything `lift()` already
handles (branch-free bodies) is untouched; this only ever adds a second
attempt, tried when the first one fails specifically because of a
branch.
"""
from __future__ import annotations

import ast
import operator
from dataclasses import dataclass, field

import sympy

from ._base import (
    NotSymbolic, _LiftCtx, _bind_params, _expr_to_sympy, _simplify_maybe_array,
    strip_docstring, _unmodified_params, _walk_lift_body,
)
from ..domain import bound_to_sympy_set
from ..finite_sets import OpaqueRegistry

# --- domain-conditioned branch pruning ------------------------------------
#
# lift() above refuses any function with a branch, unconditionally. The
# functions below extend that for one specific, narrower case: a branch
# whose condition compares an *unmodified signature parameter* against a
# literal, where the claim's own *declared domain* for that parameter
# settles the condition's truth value throughout, in which case the
# branch isn't ambiguous for this claim's domain at all, and lifting can
# proceed into whichever side is actually taken. Anything lift() already
# handles (branch-free bodies) is untouched; this only ever adds a second
# attempt, tried when the first one fails specifically because of a branch.

_MAX_PRUNED_BRANCHES = 32   # a straight-line resolution budget, not a
                           # combinatorial search


@dataclass
class ConditionedLift:
    """The result of lift_conditioned(): either an ordinary lifted
    expression (`kind="value"`, same shape lift() itself produces), or;
    a path can end in `raise` instead of `return`, a resolved
    exception (`kind="raises"`, `exc_type` the class name if it could be
    determined from the raise statement, else None)."""
    kind: str                              # "value" | "raises"
    expr: "sympy.Expr | None" = None
    exc_type: str | None = None
    params: dict = field(default_factory=dict)
    sig_params: list = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)
    opaque: "OpaqueRegistry | None" = None
    raise_guards: list = field(default_factory=list)
    recurrence: "dict | None" = None
    # `recurrence` is set only by lift_recurrence: {"min_shift": int,
    # "top": int, "closed": Expr, "valid_from": int}, the smallest
    # per-call index decrease and the largest base-case index (enough
    # to bound the runtime recursion depth a call at a given index
    # needs), plus the bare closed form and the first index it agrees
    # with the function from (see _recurrence_domain_gate).
    #
    # raise_guards, each entry: (condition, exc_name | None), the
    # symbolic path condition under which the function RAISES instead
    # of returning.
    # A value claim is FALSE wherever one of these holds for any of
    # its calls (a raise is not a value, pedantically), so the prover
    # must either exhibit such a point (falsified) or prove every
    # call's arguments avoid them all (only then does the value
    # expression stand).


def _literal_value(node: ast.AST):
    """(True, value) for a plain literal (Constant, or a Set/List/Tuple
    of constants, for `in`/`not in`); (False, None) for anything else,
    branch pruning only ever compares a parameter against a literal,
    never against another expression.

    A negative numeric literal (`-1`) parses as `UnaryOp(USub,
    Constant(1))`, not a single negative `Constant`, recognized here
    so `x <= -1` resolves the same way `x <= 1` already does."""
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        ok, v = _literal_value(node.operand)
        if not ok or isinstance(v, bool) or not isinstance(v, (int, float)):
            return False, None
        return True, (-v if isinstance(node.op, ast.USub) else v)
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        values = []
        for elt in node.elts:
            ok, v = _literal_value(elt)
            if not ok:
                return False, None
            values.append(v)
        return True, values
    return False, None


_COMPARE_OPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}
_FLIPPED_OP = {operator.lt: operator.gt, operator.gt: operator.lt,
              operator.le: operator.ge, operator.ge: operator.le,
              operator.eq: operator.eq, operator.ne: operator.ne}


def _branch_condition_truth(test: ast.AST, domain: dict, unmodified: set,
                            affine_locals: dict | None = None,
                            params: dict | None = None) -> bool | None:
    """Is `test` provably always-true or always-false, given the
    declared domain of whichever unmodified parameter(s) it involves?
    `None` (undecided) whenever the domain doesn't settle it, never a
    guess. Recognizes, recursively:

    - `and`/`or` of any number of sub-conditions this function can
      itself decide, combined with Python's own short-circuit truth
      tables (an `and` is `False` the moment one operand is, `True`
      only once every operand is; an `or` is the mirror image), so
      e.g. `a and b` can be decided `False` even if only `a` (not `b`)
      is individually decidable, exactly like Python's own evaluation.
    - `not <cond>`: the negation of whatever `<cond>` decides to.
    - a bare `param` reference (`if flag:`), decided by its truthiness
      the same way any other comparison is, only for a *discrete*
      domain (a numeric interval's bare truthiness isn't attempted,
      since 0 may or may not be excluded and this doesn't try to
      reason about that).
    - a single `param <op> literal` comparison (see _compare_truth);
      `param` may also be an *affine local* (`affine_locals`, see
      _affine_locals): a local variable whose value is traceable to
      unmodified parameters via a straight-line chain of assignments,
      not just a bare signature parameter itself.

    Two decision paths for the comparison/truthiness cases, matching
    the two domain shapes that can appear: a *discrete* domain
    (`frozenset`, string/numeric/boolean values, see grammar.py's
    `_set_value`) is decided by direct Python comparison against every
    element; a *numeric interval* domain is decided by checking both
    endpoints agree, which is exact for a bare `param <op> constant`
    comparison (linear/monotonic in param by construction; there is
    no more complex expression on either side, since only a bare Name
    is accepted) rather than an approximation. An affine-local
    comparison is decided differently (_decide_affine_condition,
    corner-evaluation over the domain box) since the compared quantity
    is a real expression, not a single monotonic parameter."""
    if isinstance(test, ast.BoolOp):
        results = [_branch_condition_truth(v, domain, unmodified, affine_locals, params)
                  for v in test.values]
        if isinstance(test.op, ast.And):
            if any(r is False for r in results):
                return False
            return True if all(r is True for r in results) else None
        if any(r is True for r in results):
            return True
        return False if all(r is False for r in results) else None
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _branch_condition_truth(test.operand, domain, unmodified, affine_locals, params)
        return None if inner is None else not inner
    if isinstance(test, ast.Name) and test.id in unmodified:
        dom = domain.get(test.id)
        if not isinstance(dom, frozenset):
            return None   # a numeric interval's bare truthiness: not attempted
        results = {bool(v) for v in dom}
        return results.pop() if len(results) == 1 else None
    return _compare_truth(test, domain, unmodified, affine_locals, params)


def _inline_expr_env(unmodified: set, affine_locals: dict, params: dict) -> dict:
    """The lookup env for lifting an *inline* branch-condition expression
    (`if r1 + r2 <= 0:`, the sum written directly in the condition,
    never bound to a name first), unmodified parameters' own symbols,
    plus any already-resolved affine local (so an inline expression can
    also reference one by name, e.g. `if total_r + 1 <= 0:`). Exactly
    the same construction `_affine_locals()` itself builds internally
    for the identical purpose, one level earlier (resolving each
    straight-line *assignment*'s own RHS), reused here so a condition
    written inline is resolved via the identical mechanism, not a
    second, parallel one."""
    env = {k: sym for k, sym in params.items() if k.split(".", 1)[0] in unmodified}
    env.update(affine_locals)
    return env


def _compare_truth(test: ast.AST, domain: dict, unmodified: set,
                   affine_locals: dict | None = None,
                   params: dict | None = None) -> bool | None:
    """The single-comparison case `_branch_condition_truth` falls
    through to: `param <op> literal`, `param in {...}`, `local <op>
    literal` for a local variable traceable to unmodified parameters
    (given `affine_locals`/`params`), or, the same reasoning applied
    to an expression written directly in the condition rather than
    bound to a name first (`if r1 + r2 <= 0:`, not `total_r = r1 + r2;
    if total_r <= 0:`), `<inline expression> <op> literal`, lifted via
    _inline_expr_env/_expr_to_sympy and decided the same
    corner-evaluation way _compare_truth_affine already decides a named
    affine local. `_affine_locals()` itself already proves the
    underlying machinery doesn't care whether an expression came from a
    named local or not; it just lifts a straight-line-reachable
    local's own defining expression the same way; this closes the one
    remaining asymmetry, an inline expression never getting the same
    treatment purely because of where it was written.

    A comparison between two *unmodified parameters* (`x1 == x2`, no
    literal on either side at all) used to commit to the "param vs
    literal" branch as soon as one side was a recognized param name,
    regardless of whether the other side was actually a literal;
    `_literal_value` on a bare Name correctly fails, and the whole
    comparison decided `None` right there, never reaching the general
    inline-expression path below even though `x1 - x2 == 0` is exactly
    the affine shape that path already handles. Falling through instead
    closes that gap: `x1 == x2` now gets the same treatment
    `x1 - x2 == 0` already did, since they're the same expression."""
    affine_locals = affine_locals or {}
    if isinstance(test, ast.Compare) and len(test.ops) > 1:
        # a chained comparison (`0 < x < 1`) is the conjunction of its
        # adjacent pairs, decide each pair with this same machinery:
        # any pair provably False falsifies the chain, all pairs
        # provably True prove it, anything else stays undecided.
        results = []
        for i, op in enumerate(test.ops):
            left_i = test.left if i == 0 else test.comparators[i - 1]
            pair = ast.fix_missing_locations(ast.copy_location(
                ast.Compare(left=left_i, ops=[op],
                            comparators=[test.comparators[i]]), test))
            r = _compare_truth(pair, domain, unmodified, affine_locals, params)
            if r is False:
                return False
            results.append(r)
        return True if all(r is True for r in results) else None
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    op = test.ops[0]
    left, right = test.left, test.comparators[0]

    # every case below is left/right symmetric: `flipped` records which
    # side the subject sat on, so a single loop over both orientations
    # replaces four hand-mirrored blocks that had to stay in lockstep.
    sides = ((left, right, False), (right, left, True))

    for subject, other, flipped in sides:
        if isinstance(subject, ast.Name) and subject.id in unmodified:
            result = _compare_truth_literal(subject.id, op, other, domain, flipped)
            if result is not None:
                return result
            break   # a recognized param name commits this case, either way

    for subject, other, flipped in sides:
        if isinstance(subject, ast.Name) and subject.id in affine_locals \
                and params is not None:
            return _compare_truth_affine(affine_locals[subject.id], op, other,
                                         domain, params, flipped)
    if params is not None:
        env = _inline_expr_env(unmodified, affine_locals, params)
        exprs: dict[bool, "sympy.Expr | tuple | None"] = {}
        for subject, other, flipped in sides:
            try:
                exprs[flipped] = _expr_to_sympy(subject, env)
            except NotSymbolic:
                exprs[flipped] = None
            if exprs[flipped] is not None and not isinstance(exprs[flipped], tuple):
                result = _compare_truth_affine(exprs[flipped], op, other,
                                               domain, params, flipped)
                if result is not None:
                    return result
        left_expr, right_expr = exprs[False], exprs[True]
        # Neither side alone is a literal (`x1 == x2`: both sides are
        # themselves param-referencing expressions, not `expr <op>
        # literal`), decide the whole comparison directly as
        # `(left_expr - right_expr) <op> 0`, the same affine-degree/
        # corner-evaluation reasoning _decide_affine_condition already
        # applies to a single expression against a literal, just fed
        # the difference of two instead of one side pre-split from a
        # literal.
        if (left_expr is not None and right_expr is not None
                and not isinstance(left_expr, tuple) and not isinstance(right_expr, tuple)):
            py_op = _COMPARE_OPS.get(type(op))
            if py_op is not None:
                return _decide_affine_condition(left_expr - right_expr, py_op, 0.0, domain, params)
    return None


def _compare_truth_literal(param: str, op: ast.AST, lit_node: ast.AST,
                           domain: dict, flipped: bool) -> bool | None:
    """`_compare_truth`'s original "unmodified param vs literal" case,
    factored out so it can be tried first and *declined* (returning
    `None`) without deciding the whole comparison, `_compare_truth`
    itself falls through to its more general affine-local/inline-
    expression handling when this returns `None`, rather than this
    function's own failure being the final word."""
    ok, lit = _literal_value(lit_node)
    if not ok:
        return None
    dom = domain.get(param)
    if dom is None:
        return None

    if isinstance(op, (ast.In, ast.NotIn)):
        if not isinstance(lit, list) or not isinstance(dom, frozenset):
            return None
        results = {v in lit for v in dom}
        if len(results) != 1:
            return None
        truth = results.pop()
        return truth if isinstance(op, ast.In) else not truth

    if isinstance(op, (ast.Is, ast.IsNot)):
        # identity is decidable EXACTLY over a discrete domain: evaluate
        # `v is lit` for every stated value (True/False/None are
        # singletons, so identity on real domain values is real Python
        # semantics, not an equality approximation; `1 is True` and
        # `True is True` genuinely differ, and a bool parameter's
        # stated set carries the real False/True objects). An interval
        # domain is left undecided: identity over synthesized numerics
        # is not a fact about the code.
        if not isinstance(dom, frozenset):
            return None
        results = {v is lit for v in dom}
        if len(results) != 1:
            return None
        truth = results.pop()
        return truth if isinstance(op, ast.Is) else not truth

    py_op = _COMPARE_OPS.get(type(op))
    if py_op is None:
        return None
    if flipped:
        py_op = _FLIPPED_OP[py_op]

    if isinstance(dom, frozenset):
        try:
            results = {py_op(v, lit) for v in dom}
        except TypeError:
            return None   # e.g. comparing a string domain with < /<=
        return results.pop() if len(results) == 1 else None

    if isinstance(dom, tuple) and isinstance(lit, (int, float)):
        lo, hi = dom
        try:
            # bool() normalizes sympy's BooleanTrue/BooleanFalse (exact
            # Rational endpoints produce those) to Python's, which the
            # `is True`/`is False` combinators upstream require; an
            # unevaluable comparison falls through to the set-theoretic
            # decision below.
            lo_val, hi_val = bool(py_op(lo, lit)), bool(py_op(hi, lit))
        except TypeError:
            lo_val, hi_val = None, object()
        if lo_val == hi_val:
            return lo_val
        # endpoints disagree, but an open endpoint can still decide a
        # strict comparison the closed-endpoint check can't (`x > -1`
        # holds on all of `(-1, 10]`): fall through to the exact
        # set-theoretic decision below.

    if isinstance(lit, (int, float)) and not isinstance(lit, bool):
        # exact decision over the declared set itself: the comparison's
        # solution region either contains the whole domain (guard always
        # true), is disjoint from it (always false), or genuinely splits
        # it (None). Openness, integer lattices, unions, and exclusions
        # all carry through bound_to_sympy_set.
        region = _COMPARISON_REGIONS.get(py_op)
        if region is None:
            return None
        try:
            dset = bound_to_sympy_set(dom)
            if dset is sympy.S.Reals:
                return None   # unrecognized bound shape, nothing declared
            if dset.is_subset(region(lit)):
                return True
            if dset.is_subset(region(lit).complement(sympy.S.Reals)):
                return False
        except Exception:
            return None
    return None   # "Z"/"N"/an unrestricted param: not specific enough


_COMPARISON_REGIONS = {
    # for each comparison op, the set of reals v where `v <op> lit`
    operator.gt: lambda lit: sympy.Interval.open(lit, sympy.oo),
    operator.ge: lambda lit: sympy.Interval(lit, sympy.oo),
    operator.lt: lambda lit: sympy.Interval.open(-sympy.oo, lit),
    operator.le: lambda lit: sympy.Interval(-sympy.oo, lit),
    operator.eq: lambda lit: sympy.FiniteSet(lit),
    operator.ne: lambda lit: sympy.Complement(sympy.S.Reals, sympy.FiniteSet(lit)),
}


def _compare_truth_affine(expr, op: ast.AST, lit_node: ast.AST, domain: dict,
                          params: dict, flipped: bool) -> bool | None:
    """`_compare_truth`'s affine-local case: decide `expr <op> lit_node`
    (or the flipped form, if the local appeared on the comparison's
    right side) via _decide_affine_condition. `in`/`not in` against a
    derived expression isn't attempted; that's only ever meaningful
    for a bare parameter's own discrete domain."""
    if isinstance(op, (ast.In, ast.NotIn)):
        return None
    ok, lit = _literal_value(lit_node)
    if not ok or not isinstance(lit, (int, float)) or isinstance(lit, bool):
        return None
    py_op = _COMPARE_OPS.get(type(op))
    if py_op is None:
        return None
    if flipped:
        py_op = _FLIPPED_OP[py_op]
    return _decide_affine_condition(expr, py_op, lit, domain, params)


def _decide_affine_condition(expr, py_op, lit: float, domain: dict, params: dict) -> bool | None:
    """Decide `expr <py_op> lit` (`py_op` one of operator.eq/ne/lt/le/
    gt/ge; `lit` a plain number) for `expr` an affine sympy expression
    over parameter symbols with declared interval domains, the same
    corner-evaluation fact _affine_sign_by_corners relies on (an affine
    functional's extrema over a box are always attained at a vertex),
    generalized from a single ">=0" sign question to any of the six
    comparison operators, and to equality/inequality via the
    expression's full corner-computed range (an affine map is
    continuous over a convex box, so its range is exactly [min, max] of
    the corner values; `lit` strictly inside that range means some
    point in the domain equals it and some doesn't, genuinely undecided
    for both == and !=, not a gap in this reasoning).

    `None` (undecided, never a guess) if `expr` isn't affine in its
    domain-bounded symbols, too many symbols are bounded to enumerate
    cheaply, some free symbol in `expr` has no declared interval domain
    at all (a corner can't be evaluated without one), or the corners
    don't settle it. Never raises; every numeric conversion is
    guarded, since this is reached with no enclosing try/except between
    it and try_prove's own top level (lift_conditioned has none)."""
    import itertools

    bounded = {p: domain[p] for p, sym in params.items()
              if sym in expr.free_symbols and isinstance(domain.get(p), tuple)}
    if not bounded or len(bounded) > 6:
        return _interval_condition(expr, py_op, lit, domain, params)
    if expr.free_symbols - {params[p] for p in bounded}:
        # some free symbol has no plain interval domain, the interval
        # fallback still handles a composite Domain bound (or a known
        # bounded function of an unbounded symbol) via its hull.
        return _interval_condition(expr, py_op, lit, domain, params)
    syms = [params[p] for p in bounded]
    try:
        if sympy.Poly(expr, *syms).total_degree() > 1:
            return _interval_condition(expr, py_op, lit, domain, params)
    except sympy.PolynomialError:
        return _interval_condition(expr, py_op, lit, domain, params)
    try:
        values = [float(expr.subs(dict(zip(syms, corner))))
                 for corner in itertools.product(*bounded.values())]
    except (TypeError, ValueError):
        return None
    lo, hi = min(values), max(values)
    if py_op in (operator.eq, operator.ne):
        if lo == hi == lit:
            return py_op is operator.eq
        if not (lo <= lit <= hi):
            return py_op is operator.ne
        return None
    try:
        results = {py_op(v, lit) for v in values}
    except TypeError:
        return None
    return results.pop() if len(results) == 1 else None


def _interval_condition(expr, py_op, lit: float, domain: dict,
                        params: dict) -> bool | None:
    """The interval-arithmetic fallback for a branch condition the
    affine corner machinery can't decide: `expr <py_op> lit` over the
    domain box, using the same rigorous `_interval_bounds` hull the
    sign-decidability pass runs on. Sound in both directions (the hull
    CONTAINS the true range, so all-of-range facts transfer); anything
    the hull doesn't settle stays `None`. This is what resolves an
    `abs(x) > 3` guard on `[0, 1]`, or a plain `n > 5` guard whose
    bound is a composite `Domain` (`[0, 100] ⊂ Z`) rather than a bare
    interval tuple."""
    from ._proof_support import _interval_bounds

    box = _interval_bounds(expr, domain, params)
    if box is None:
        return None
    lo = box.min if isinstance(box, sympy.AccumBounds) else box
    hi = box.max if isinstance(box, sympy.AccumBounds) else box
    try:
        if py_op is operator.gt:
            return True if bool(lo > lit) else (False if bool(hi <= lit) else None)
        if py_op is operator.ge:
            return True if bool(lo >= lit) else (False if bool(hi < lit) else None)
        if py_op is operator.lt:
            return True if bool(hi < lit) else (False if bool(lo >= lit) else None)
        if py_op is operator.le:
            return True if bool(hi <= lit) else (False if bool(lo > lit) else None)
        if py_op is operator.eq:
            if bool(lo == lit) and bool(hi == lit):
                return True
            return False if (bool(lit < lo) or bool(lit > hi)) else None
        if py_op is operator.ne:
            if bool(lit < lo) or bool(lit > hi):
                return True
            return False if (bool(lo == lit) and bool(hi == lit)) else None
    except TypeError:
        return None
    return None


def _affine_locals(tree: ast.FunctionDef, unmodified: set, params: dict) -> dict:
    """Local variables resolvable to a sympy expression purely in terms
    of `unmodified` parameters (including an unmodified aggregate
    parameter's own composite-keyed fields, e.g. `cfg.a`; see
    _bind_params), via a straight-line chain of simple assignments
    reachable unconditionally before the function's first branch/loop.
    Lets a branch condition over a *derived* quantity (`denom = x + y;
    if denom == 0:`) be decided the same way one over a bare parameter
    already is.

    Conservative by the same construction as _unmodified_params: a name
    assigned more than once anywhere in the whole function (even inside
    a branch never taken for this domain) is excluded outright, no
    reachability analysis attempted. A local depending on anything
    outside unmodified parameters/earlier resolved locals (a modified
    parameter, a loop variable, an unsupported expression) simply
    doesn't appear in the result, never a guess, and never lets one
    unresolvable local block a later, independent one from resolving."""
    assign_counts: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assign_counts[t.id] = assign_counts.get(t.id, 0) + 1
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and isinstance(node.target, ast.Name):
            assign_counts[node.target.id] = assign_counts.get(node.target.id, 0) + 2

    env = {k: sym for k, sym in params.items() if k.split(".", 1)[0] in unmodified}
    resolved: dict = {}
    for stmt in strip_docstring(tree.body):
        if (isinstance(stmt, ast.If) and not stmt.orelse
                and all(isinstance(b, ast.Raise) for b in stmt.body)):
            # a pure raise guard binds nothing on the fall-through
            # path: any statement after it still executes with every
            # earlier assignment intact, so resolution continues;
            # this is what lets a computed guard quantity assigned
            # AFTER the function's input guards (`re = rho*v*d/mu`
            # below four `if: raise` checks) resolve at all
            continue
        if isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try)):
            break
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            continue
        name = stmt.targets[0].id
        if assign_counts.get(name, 0) != 1 or name in unmodified:
            continue
        try:
            value = _expr_to_sympy(stmt.value, env)
        except NotSymbolic:
            continue
        if isinstance(value, tuple):
            continue
        resolved[name] = value
        env[name] = value
    return resolved


def _explain_branch(test: ast.AST, unmodified: set, affine_locals: dict | None = None,
                    params: dict | None = None) -> dict:
    """Underivability diagnostics only (`mathema audit --deriv-report`):
    classify *why* a branch condition can or can't be pruned, independent
    of any particular claim's declared domain, unlike
    _branch_condition_truth (which decides a condition's truth value
    given one), this only ever answers "is this condition shape and
    these names even *eligible* for pruning, and if so which parameters
    would a claim need to declare a domain for", the exact question an
    agentic caller trying to make a function derivable needs answered,
    since it has no claim/domain to test against yet.

    `{"kind": "resolvable", "needs_domain_for": [...]}`; pruning would
    settle this branch given a specific-enough domain for the named
    parameters (which may still turn out to not be specific enough for a
    given domain; this only establishes eligibility, same as
    _branch_condition_truth would still need to be asked with a real
    domain to know for sure). `needs_domain_for` always names *signature
    parameters* even when the condition is over a local variable (see
    _affine_locals); a claim can't declare a domain for a local
    directly, only for the parameters it's built from.

    `{"kind": "blocked", "reason": "..."}`, structurally ineligible no
    matter what domain is declared; `reason` names why (a local variable
    (or inline expression) not traceable to unmodified parameters (or a
    reassigned parameter), comparing two names to each other, a
    non-literal comparand, or a condition shape outside
    and/or/not/name/single-comparison).

    An expression written directly in the condition (`if r1 + r2 <= 0:`)
    is resolved the same way a *named* affine local is (`total_r = r1 +
    r2; if total_r <= 0:`), via `_inline_expr_env`/`_expr_to_sympy`,
    mirroring `_compare_truth`'s own identical fallback; this diagnostic
    must recognize exactly what the real decision path (`_compare_truth`)
    now does, or it would keep reporting "blocked" for a condition that
    actually resolves."""
    affine_locals = affine_locals or {}
    if isinstance(test, ast.BoolOp):
        parts = [_explain_branch(v, unmodified, affine_locals, params) for v in test.values]
        blocked = [p for p in parts if p["kind"] == "blocked"]
        if blocked:
            code = (blocked[0]["code"] if len(blocked) == 1
                    else "composite")
            return {"kind": "blocked", "code": code,
                    "reason": "; ".join(p["reason"] for p in blocked)}
        needs = sorted({p for part in parts for p in part["needs_domain_for"]})
        return {"kind": "resolvable", "code": "needs-domain",
                "needs_domain_for": needs}
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _explain_branch(test.operand, unmodified, affine_locals, params)
    if isinstance(test, ast.Name):
        if test.id in unmodified:
            return {"kind": "resolvable", "code": "needs-domain",
                    "needs_domain_for": [test.id]}
        return {"kind": "blocked", "code": "bare-local-name",
                "reason": f"{test.id!r} is a local variable "
               "(or a reassigned parameter), not an unmodified signature "
               "parameter, a bare name's truthiness isn't traced through "
               "affine locals, only a comparison is (see below)"}
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        left, right = test.left, test.comparators[0]
        left_name = left.id if isinstance(left, ast.Name) else None
        right_name = right.id if isinstance(right, ast.Name) else None
        if left_name and right_name and left_name in unmodified and right_name in unmodified:
            # x1 == x2 is algebraically x1 - x2 == 0, degree 1, the same
            # affine shape an inline expression vs a literal already
            # resolves, just with both params free instead of one
            # absorbed into a literal. Matches _compare_truth's own
            # fallback for exactly this case; this diagnostic must
            # agree with what the real decision path now does, or it
            # would keep reporting "blocked" for a condition that
            # actually resolves.
            return {"kind": "resolvable", "code": "needs-domain",
                    "needs_domain_for": sorted({left_name, right_name})}
        if left_name and right_name:
            return {"kind": "blocked", "code": "two-names-compare",
                    "reason": "compares two names to each "
                   "other, and at least one isn't an unmodified signature "
                   "parameter. Branch pruning only supports 'param <op> "
                   "literal', or 'param <op> param' between two unmodified "
                   "parameters"}
        name, lit_node = (left_name, right) if left_name else (right_name, left)
        if name is not None and name in unmodified:
            if not _literal_value(lit_node)[0]:
                return {"kind": "blocked", "code": "non-literal-compare",
                        "reason": f"the other side "
                        f"({ast.unparse(lit_node)!r}) isn't a literal value"}
            return {"kind": "resolvable", "code": "needs-domain",
                    "needs_domain_for": [name]}

        # Not a bare unmodified parameter on either side, either a
        # *named* affine local, or (same fallback _compare_truth itself
        # applies) an inline expression written directly in the
        # condition, never bound to a name first. Both resolve the same
        # way from here: the expression's own free (unmodified-
        # parameter) symbols and degree.
        expr, other, source_label = None, None, None
        if name is not None and name in affine_locals and params is not None:
            expr, other, source_label = affine_locals[name], lit_node, repr(name)
        elif params is not None:
            env = _inline_expr_env(unmodified, affine_locals, params)
            for side, opposite in ((left, right), (right, left)):
                try:
                    candidate = _expr_to_sympy(side, env)
                except NotSymbolic:
                    continue
                if not isinstance(candidate, tuple):
                    expr, other = candidate, opposite
                    break
        if expr is None:
            if name is not None:
                return {"kind": "blocked", "code": "untraceable-local",
                        "reason": f"{name!r} is a local "
                       "variable not traceable to unmodified parameters via "
                       "a straight-line chain of assignments before the "
                       "first branch (or is itself a reassigned parameter) "
                       "-- branch pruning only resolves conditions over "
                       "unmodified parameters or expressions built from them"}
            return {"kind": "blocked", "code": "opaque-expression",
                    "reason": f"neither side of "
                    f"{ast.unparse(test)!r} is a bare name, an affine local, "
                   "or an expression built purely from unmodified "
                   "parameters"}

        needs = sorted(p for p, sym in params.items() if sym in expr.free_symbols)
        if not needs:
            return {"kind": "blocked", "code": "no-parameter-dependence",
                    "reason": f"the traced form of {ast.unparse(test)!r} "
                   "contains no unmodified parameter; the trace, not the "
                   "source, is what pruning can see, so a dependence the "
                   "trace lost reads the same as none"}
        try:
            is_affine = sympy.Poly(expr, *(params[p] for p in needs)).total_degree() <= 1
            essential = False
        except sympy.PolynomialError:
            # not a polynomial in these parameters at all (a
            # transcendental function, sin/cos/exp/log/...), not just
            # a polynomial of too-high degree. No algebraic
            # reparameterization linearizes a transcendental function,
            # unlike a genuine bilinear/multilinear polynomial (a
            # product of parameters), where combining them into one
            # variable (spread/ratio/tau) can still work; these two
            # cases need different advice, not the same generic
            # "isn't affine" message.
            is_affine = False
            essential = True
        if not is_affine:
            workaround = ("This nonlinearity is essential: it's not a "
                         "polynomial in these parameters at all, so no "
                         "reparameterization fixes it. A domain whose "
                         "interval evaluation settles the guard outright "
                         "can still work." if essential else
                         "Corner evaluation decides only affine "
                         "expressions, and interval evaluation over the "
                         "declared domain didn't settle it either. "
                         "Reparameterizing to one combined variable might "
                         "still linearize it, or a tighter domain might "
                         "settle the guard.")
            code = ("non-affine-essential" if essential
                    else "non-affine-refinable")
            if source_label:
                return {"kind": "blocked", "code": code,
                        "reason": f"{source_label} traces "
                       f"back to unmodified parameters ({', '.join(needs)}), "
                       f"but its defining expression ({expr}) isn't affine "
                       f"in them. {workaround}"}
            return {"kind": "blocked", "code": code,
                    "reason": f"the expression "
                    f"{ast.unparse(test)!r} traces back to unmodified "
                   f"parameters ({', '.join(needs)}), but ({expr}) isn't "
                   f"affine in them. {workaround}"}
        if not _literal_value(other)[0]:
            return {"kind": "blocked", "code": "non-literal-compare",
                    "reason": f"the other side "
                    f"({ast.unparse(other)!r}) isn't a literal value"}
        return {"kind": "resolvable", "code": "needs-domain",
                "needs_domain_for": needs}
    return {"kind": "blocked", "code": "unrecognized-shape",
            "reason": f"condition shape {ast.unparse(test)!r} "
           "isn't recognized (only and/or/not, a bare name, or a single "
           "'param <op> literal' comparison are)"}


def _prune_body(body: list, domain: dict, unmodified: set, budget: list,
                affine_locals: dict | None = None, params: dict | None = None) -> list | None:
    """Resolve every `if` in `body` (recursively; an `elif` chain is
    nested `If`s in `orelse`, handled the same way) whose condition
    _branch_condition_truth() can decide, replacing it with whichever
    side is actually taken. `None` if any `if` can't be decided, or a
    loop/while/try is encountered (still refused outright, same as
    lift(); this only ever extends the branch case)."""
    out = []
    for stmt in body:
        if isinstance(stmt, ast.If):
            truth = _branch_condition_truth(stmt.test, domain, unmodified,
                                            affine_locals, params)
            if truth is None:
                return None
            budget[0] -= 1
            if budget[0] < 0:
                return None
            pruned = _prune_body(stmt.body if truth else stmt.orelse,
                                 domain, unmodified, budget, affine_locals, params)
            if pruned is None:
                return None
            out.extend(pruned)
        elif isinstance(stmt, (ast.For, ast.While, ast.Try)):
            return None
        else:
            out.append(stmt)
    return out


_PIECEWISE_COMPARE_OPS = {ast.GtE: sympy.Ge, ast.Gt: sympy.Gt,
                          ast.LtE: sympy.Le, ast.Lt: sympy.Lt,
                          ast.Eq: sympy.Eq, ast.NotEq: sympy.Ne}


def _condition_to_sympy(test: ast.AST, env: dict):
    """Intent:
        A branch guard as a symbolic sympy Boolean over the parameter
        symbols, the piecewise lift's condition side, as opposed to
        `_branch_condition_truth`, which decides a guard's truth under
        one concrete domain.

    Notes:
        Comparisons (chains decompose pairwise), and/or/not. `None`
        for any shape outside that vocabulary, the piecewise lift
        declines rather than approximating a guard.
    """
    if isinstance(test, ast.BoolOp):
        parts = [_condition_to_sympy(v, env) for v in test.values]
        if any(p is None for p in parts):
            return None
        op = sympy.And if isinstance(test.op, ast.And) else sympy.Or
        return op(*parts)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _condition_to_sympy(test.operand, env)
        return None if inner is None else sympy.Not(inner)
    if isinstance(test, ast.Compare):
        operands = [test.left, *test.comparators]
        try:
            lifted = [_expr_to_sympy(o, dict(env)) for o in operands]
        except NotSymbolic:
            return None
        clauses = []
        for a, op, b in zip(lifted, test.ops, lifted[1:]):
            builder = _PIECEWISE_COMPARE_OPS.get(type(op))
            if builder is None or isinstance(a, tuple) or isinstance(b, tuple):
                return None
            clauses.append(builder(a, b))
        return sympy.And(*clauses) if len(clauses) > 1 else clauses[0]
    return None


def lift_piecewise(fn, facts) -> "ConditionedLift | None":
    """Intent:
        The whole branched function as one sympy `Piecewise`, every
        branch's value paired with its own symbolic guard, valid at
        ANY argument, unlike the domain-pruned lift, which bakes in one
        branch and is only sound for calls whose arguments stay inside
        the pruning domain (the f(-x)-on-abs trap).

    Notes:
        The recognized shape: a body of `if`/`elif`/`else`, `return`,
        straight-line assignments, and raises whose guards
        `_condition_to_sympy` covers, plus, as a LEAF, a whole
        branch region that is itself a recognizable loop body (an
        accumulator pass over `range(...)`, epilogue statements
        included), closed by the sum machinery and paired with its
        own path condition: the branches-around-loops shape. A region
        mixing a loop WITH further branching, a sequence-typed
        parameter, and recursion all decline. An `if` without an
        `else` takes the statements after it as the fallthrough arm.
    """
    if facts.tree is None or facts.recursion:
        return None
    if not facts.branch_count:
        return None
    if not facts.params or any(k == "sequence" for k in facts.param_kinds.values()):
        return None
    params, aggregate = _bind_params(fn, facts)
    from ._normalize import normalized_body
    body = normalized_body(fn, facts)
    raise_guards: list = []
    _RAISED = object()   # sentinel: this path raises rather than returns

    def exc_name(raise_stmt):
        exc = raise_stmt.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            return exc.func.id
        if isinstance(exc, ast.Name):
            return exc.id
        return None

    def walk(stmts, path_cond, env):
        if not stmts:
            return None
        has_for = any(isinstance(n, ast.For)
                      for st in stmts for n in ast.walk(st))
        if has_for:
            # an If INSIDE a loop body belongs to the loop closer (the
            # conditional-update Piecewise summand), never to this
            # walk's own branching, only branching OUTSIDE every
            # loop counts here
            in_loop = {id(n) for st in stmts
                       for f in ast.walk(st) if isinstance(f, ast.For)
                       for n in ast.walk(f)}
            has_outer_if = any(isinstance(n, ast.If) and id(n) not in in_loop
                               for st in stmts for n in ast.walk(st))
            if not has_outer_if:
                # a pure loop region is a LEAF: one recognizable loop
                # body (epilogue statements included), closed by the
                # sum machinery against this path's own environment
                from ._sum import closed_loop_region
                return closed_loop_region(fn, facts, stmts, env)
            first_if = next((i for i, st in enumerate(stmts)
                             if isinstance(st, ast.If)), len(stmts))
            first_for = next((i for i, st in enumerate(stmts)
                              if any(isinstance(n, ast.For)
                                     for n in ast.walk(st))), len(stmts))
            if first_for < first_if:
                # loops BEFORE the region's branching: close the loop
                # prefix into the environment and continue this same
                # walk on the tail, the loop's closed value then
                # flows through the branches like any other local
                from ._sum import close_loop_prefix
                env2 = close_loop_prefix(fn, facts, stmts[:first_if], env)
                if env2 is None:
                    return None
                return walk(stmts[first_if:], path_cond, env2)
            # branching (or plain locals) first: the ordinary dispatch
            # below consumes statements until each arm is loop-free or
            # a pure loop leaf
        head, tail = stmts[0], list(stmts[1:])
        if isinstance(head, ast.Raise):
            raise_guards.append((path_cond, exc_name(head)))
            return _RAISED
        if isinstance(head, ast.Return):
            if head.value is None:
                return None
            try:
                value = _expr_to_sympy(head.value, dict(env))
            except NotSymbolic:
                return None
            return None if isinstance(value, tuple) else value
        if isinstance(head, ast.Assign) and len(head.targets) == 1 \
                and isinstance(head.targets[0], ast.Name):
            # a straight-line local: its defining expression joins the
            # environment for everything downstream on this path
            try:
                value = _expr_to_sympy(head.value, dict(env))
            except NotSymbolic:
                return None
            if isinstance(value, tuple):
                return None
            extended = dict(env)
            extended[head.targets[0].id] = value
            return walk(tail, path_cond, extended)
        if isinstance(head, ast.If):
            cond = _condition_to_sympy(head.test, env)
            if cond is None:
                return None
            then = walk(head.body, sympy.And(path_cond, cond), env)
            other_cond = sympy.And(path_cond, sympy.Not(cond))
            other = walk(head.orelse if head.orelse else tail, other_cond, env)
            if then is None or other is None:
                return None
            if then is _RAISED and other is _RAISED:
                return _RAISED
            if then is _RAISED:
                return other
            if other is _RAISED:
                return then
            return sympy.Piecewise((then, cond), (other, sympy.true))
        return None

    expr = walk(body, sympy.true, dict(params))
    if expr is None or expr is _RAISED:
        return None
    # piecewise_fold pulls a summand's own Piecewise condition out
    # THROUGH a Sum, leaving the bound dummy free in a top-level arm
    # condition (observed live: `(i > 2) & (u > 0)` beside
    # Sum(i, (i, 0, n-1))), never fold across a Sum/Product
    if not expr.has(sympy.Sum, sympy.Product):
        try:
            expr = sympy.piecewise_fold(expr)
        except Exception:
            pass
    guards = []
    from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    for cond, name in raise_guards:
        try:
            guards.append((_with_timeout(lambda c=cond: sympy.simplify(c),
                                         FAST_TIMEOUT_SECONDS), name))
        except Exception:
            guards.append((cond, name))
    return ConditionedLift(kind="value", expr=expr, params=params,
                           sig_params=list(facts.params), aggregate=aggregate,
                           opaque=OpaqueRegistry(), raise_guards=guards)


def lift_conditioned(fn, facts, domain: dict, max_callee_depth: int = 3,
                     _ctx: "_LiftCtx | None" = None,
                     _opaque: "OpaqueRegistry | None" = None) -> "ConditionedLift | None":
    """Like lift(), but for a function whose branches resolve under the
    given domain (see _branch_condition_truth/_prune_body), still
    refuses loops/recursion/non-scalar parameters outright, unchanged
    from lift(); this only ever widens what counts as branch-free for
    *this specific domain*. `None` if there's nothing to prune (lift()
    already covers that), the domain doesn't settle enough branches, or
    the resolution budget (_MAX_PRUNED_BRANCHES) runs out. `max_callee_depth`
    is the same callee-inlining budget lift() itself takes, see there,
    applied here to the pruned body's own final walk, which also
    carries `domain` itself through so a callee this pruned body calls
    can attempt its own domain-derived conditioning in turn (see
    _try_inline_callee/_derive_passthrough_domain). `_ctx`/`_opaque` are
    private, same role as lift()'s own, only a recursive call from
    _try_inline_callee (inlining a callee that itself needs
    conditioning) passes them."""
    if facts.tree is None or facts.loops or facts.recursion:
        return None
    if not facts.branch_count:
        return None
    if not facts.params or any(k == "sequence" for k in facts.param_kinds.values()):
        return None

    unmodified = _unmodified_params(facts.tree, set(facts.params))
    body = strip_docstring(facts.tree.body)

    # params/aggregate must exist before pruning, not just before the
    # final body-walk below: a branch condition over an *affine local*
    # (see _affine_locals) needs the unmodified parameters' own symbols
    # to lift that local's defining expression, which is exactly what
    # _prune_body -> _branch_condition_truth -> _compare_truth needs to
    # decide such a condition against the domain.
    params, aggregate = _bind_params(fn, facts)
    affine_locals = _affine_locals(facts.tree, unmodified, params)

    pruned = _prune_body(body, domain, unmodified, [_MAX_PRUNED_BRANCHES],
                         affine_locals, params)
    if pruned is None:
        return None

    from ._base import _method_ctx_fields
    _sp, _sc = _method_ctx_fields(fn, facts)
    ctx = _ctx or _LiftCtx(globals_ns=getattr(fn, "__globals__", {}),
                           depth=max_callee_depth, seen=frozenset({id(fn)}),
                           domain=domain, unmodified=frozenset(unmodified),
                           self_param=_sp, self_class=_sc)
    opaque = _opaque if _opaque is not None else OpaqueRegistry()
    env = dict(params)
    sig_params = list(facts.params)
    kind, result, _failure = _walk_lift_body(pruned, env, ctx, allow_raise=True, opaque=opaque)
    if kind == "value":
        result = (tuple(_simplify_maybe_array(r) for r in result)
                 if isinstance(result, tuple) else _simplify_maybe_array(result))
        return ConditionedLift(kind="value", expr=result, params=params,
                               sig_params=sig_params, aggregate=aggregate, opaque=opaque)
    if kind == "raises":
        return ConditionedLift(kind="raises", exc_type=result, params=params,
                               sig_params=sig_params, aggregate=aggregate, opaque=opaque)
    return None
