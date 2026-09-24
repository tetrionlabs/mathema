# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The top-level derive-route dispatcher: `try_prove()`/`try_prove_raises()`,
and `_law_to_sympy()`, the claim-law-expression-to-sympy walker
(`f(...)` substitution, `d`/`lim`/`integrate`/`Sum`/`Prod`, dataclass/
dict field access, tuple/array indexing) against an ordinary `Lifted`
result. `try_prove()` tries `lift()`, then domain-conditioned branch
pruning, then falls back through the fold/dot/sum clusters in turn,
each already tried its own `lift_X()` internally, so this only reaches
into `.fold`/`.dot`/`.sum` for their own `try_prove_X()` entry points,
never their lifters directly (the one exception: a cheap `lift_fold()`
boolean check, to decide whether the fold or the more general sum
fallback applies).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace

import sympy

from .._math_vocab import (_BINOPS, _D_AT_SENTINEL, _MATH_ATTRS, _PV_FUNC,
                           _SYMPY_FUNCS, _call_name)
from ..grammar import is_reserved
from .. import families
from ..finite_sets import is_opaque_eligible
from ._base import (
    Lifted, NotSymbolic, _SymbolicArray, _bind_params, _display_value,
    _exact_numeric_literal, _literal_int_index, _unmodified_params,
    _unsupported_call_message, lift,
)
from ._conditioned import (_affine_locals, _explain_branch, _literal_value,
                           lift_conditioned, lift_piecewise)
from ..domain import InvalidDomain, render_domain_bound, split_bound_at
from ._dot import try_prove_dot
from ._fold import lift_fold, try_prove_fold
from ._proof_support import (
    ProofResult, _domain_assumptions, _free_names, _prove_relation,
    _prove_relation_case_split, _quantifier_clause,
)
from ._sum import try_prove_sum

# private aux-dict key carrying {name: Lifted} for a claim's bound
# auxiliary functions; a dunder so it can never collide with a law's
# own free-variable names (those are rejected at validation)
_AUX_FUNCS_KEY = "__aux_funcs__"

_LIM_NOTE_KEY = "__mathema_lim_note__"


def _one_sided_lim_rescue(inner, var_sym, point, direction, aux, node):
    """Intent:
        The two-sided finite-point limit failed or came back undefined:
        when exactly one side yields a real, defined limit and the
        other leaves the reals (the Lorentz-gamma shape, where the
        function's own domain ends at the point), the valid side IS
        the honest reading, adopt it, and record the resolved
        direction in aux so the verdict's sketch states it explicitly.
        None when neither or both sides are real-valid (a genuine
        two-sided disagreement stays a decline).
    """
    from .._timeout import _with_timeout, lowering_cap
    if direction != "+-" or not getattr(point, "is_number", False) \
            or point.is_infinite:
        return None
    sides = {}
    for d in ("-", "+"):
        try:
            sides[d] = _with_timeout(
                lambda d=d: sympy.limit(inner, var_sym, point, dir=d),
                lowering_cap())
        except TimeoutError:
            raise
        except Exception:
            sides[d] = None

    def _real_valid(v):
        if v is None or v is sympy.zoo or v.has(sympy.zoo, sympy.nan):
            return False
        if v.has(sympy.I):
            return False
        return v.is_extended_real is not False

    valid = {d: v for d, v in sides.items() if _real_valid(v)}
    if len(valid) != 1:
        return None
    (d, v), = valid.items()
    aux[_LIM_NOTE_KEY] = (
        f"lim at {point} resolved one-sided from "
        f"{'below' if d == '-' else 'above'} ({var_sym} -> {point}{d}): "
        f"the other side leaves the reals")
    return v




_KINKS_KEY = "__mathema_kinks__"


def _near_sign(g, eps) -> "int | None":
    """The sign of `g` for every small enough positive `eps`: -1, 0 or
    1, or None when it cannot be settled."""
    from .._timeout import _with_timeout, lowering_cap
    if g.has(sympy.Piecewise):
        return None
    try:
        value = _with_timeout(lambda: sympy.limit(sympy.sign(g), eps, 0,
                                                  dir="+"),
                              lowering_cap())
    except TimeoutError:
        raise
    except Exception:
        return None
    if value in (-1, 0, 1):
        return int(value)
    return None


def _near_truth(cond, eps) -> "bool | None":
    """Whether a branch condition holds for every small enough
    positive `eps` (True), for none of them (False), or neither is
    settled (None)."""
    if cond is sympy.true or cond is sympy.false:
        return bool(cond)
    if isinstance(cond, (sympy.And, sympy.Or)):
        parts = [_near_truth(a, eps) for a in cond.args]
        if isinstance(cond, sympy.And):
            if any(p is False for p in parts):
                return False
            return True if all(p is True for p in parts) else None
        if any(p is True for p in parts):
            return True
        return False if all(p is False for p in parts) else None
    if isinstance(cond, sympy.Not):
        inner = _near_truth(cond.args[0], eps)
        return None if inner is None else not inner
    if not isinstance(cond, sympy.core.relational.Relational):
        return None
    sign = _near_sign(cond.lhs - cond.rhs, eps)
    if sign is None:
        return None
    return {sympy.Gt: sign > 0, sympy.Ge: sign >= 0, sympy.Lt: sign < 0,
            sympy.Le: sign <= 0, sympy.Eq: sign == 0,
            sympy.Ne: sign != 0}.get(type(cond))


def _branch_limit(inner, var_sym, point, direction: str):
    """Intent:
        The one-sided limit of an expression holding a `Piecewise` in
        `var_sym`, with each branch chosen by where the approach
        actually runs: `var_sym = point + eps` from above, `point -
        eps` from below, `1/eps` towards `oo`, all with `eps -> 0+`.
        None when a branch condition cannot be settled near the point.

    Notes:
        sympy's own `limit` of a Piecewise evaluates the branch that
        holds AT the point, so a jump there reads as either side's
        value regardless of the direction asked for.
    """
    from .._timeout import _with_timeout, lowering_cap
    eps = sympy.Dummy("eps", positive=True)
    if point is sympy.oo:
        approach = 1 / eps
    elif point is sympy.S.NegativeInfinity:
        approach = -1 / eps
    else:
        approach = point + eps if direction == "+" else point - eps
    near = inner.subs(var_sym, approach)
    undecided = []

    def choose(pw):
        for value, cond in pw.args:
            truth = _near_truth(cond, eps)
            if truth is True:
                return value
            if truth is None:
                undecided.append(cond)
                return pw
        undecided.append(pw)
        return pw

    near = near.replace(lambda e: isinstance(e, sympy.Piecewise), choose)
    if undecided or near.has(sympy.Piecewise):
        return None
    return _with_timeout(lambda: sympy.limit(near, eps, 0, dir="+"),
                         lowering_cap())


def _branch_aware_limit(inner, var_sym, point, direction: str, node):
    """`sympy.limit`, except that a Piecewise in the limit variable goes
    through `_branch_limit`, side by side for a two-sided limit (the
    sides must agree). Raises NotSymbolic when the limit does not
    exist or cannot be settled."""
    if point.is_infinite:
        sides = ["+"]
    else:
        sides = ["+", "-"] if direction == "+-" else [direction]
    values = []
    for d in sides:
        try:
            value = _branch_limit(inner, var_sym, point, d)
        except TimeoutError as e:
            raise NotSymbolic(f"the limit computation exceeded the wall "
                              f"clock: {ast.unparse(node)!r}") from e
        except Exception:
            value = None
        if value is None or value is sympy.zoo or value.has(sympy.nan):
            raise NotSymbolic(f"could not settle the branch the limit "
                              f"approaches through: {ast.unparse(node)!r}")
        values.append(value)
    if len(values) == 2 and sympy.simplify(values[0] - values[1]) != 0:
        raise NotSymbolic(
            f"the two-sided limit does not exist (left and right limits "
            f"differ, {values[1]} and {values[0]}; state a one-sided "
            f"point, e.g. 0+ or 0-, to claim one side): "
            f"{ast.unparse(node)!r}")
    return values[0]


def _kink_loci(expr, var_syms) -> list:
    """Intent:
        Where `expr` may fail to be differentiable in `var_syms`: one
        condition per non-smooth node (the zero of an `Abs`/`sign`/
        `Heaviside` argument, the tie of a `Max`/`Min`, the boundary of
        a Piecewise condition, the whole-number points of a floor,
        ceiling or remainder), each an equality over the parameters.
    """
    wanted = set(var_syms)
    loci: list = []

    def touches(e) -> bool:
        return bool(getattr(e, "free_symbols", set()) & wanted)

    for node in sympy.preorder_traversal(expr):
        if isinstance(node, (sympy.Abs, sympy.sign, sympy.Heaviside)):
            if touches(node.args[0]):
                loci.append(sympy.Eq(node.args[0], 0))
        elif isinstance(node, (sympy.Max, sympy.Min)):
            if touches(node):
                args = list(node.args)
                loci.extend(sympy.Eq(a - b, 0) for i, a in enumerate(args)
                            for b in args[i + 1:])
        elif isinstance(node, sympy.Piecewise):
            for _value, cond in node.args:
                for rel in cond.atoms(sympy.core.relational.Relational):
                    if touches(rel):
                        loci.append(sympy.Eq(rel.lhs - rel.rhs, 0))
        elif isinstance(node, (sympy.floor, sympy.ceiling, sympy.frac)):
            if touches(node.args[0]):
                loci.append(sympy.Eq(sympy.frac(node.args[0]), 0))
        elif isinstance(node, sympy.Mod):
            if touches(node):
                loci.append(sympy.Eq(sympy.frac(node.args[0] / node.args[1]), 0))
    return loci


def _derivative_at(inner, var_syms, subs, node):
    """Intent:
        `d(inner, var)` at the point `subs`, for an `inner` with
        non-smooth nodes: the symbolic derivative where the point is
        clear of every kink, else the one-sided difference quotients,
        which must agree. Raises NotSymbolic where the derivative does
        not exist or cannot be settled.
    """
    loci = _kink_loci(inner, var_syms)
    at_loci = [locus.lhs.subs(subs, simultaneous=True) for locus in loci]
    if all(v.is_number and v != 0 for v in at_loci):
        return sympy.diff(inner, *var_syms).subs(subs, simultaneous=True)
    if len(var_syms) != 1 or var_syms[0] not in subs:
        raise NotSymbolic(f"not differentiable at the evaluation point, or "
                          f"it cannot be settled there: {ast.unparse(node)!r}")
    var = var_syms[0]
    point = subs[var]
    h = sympy.Dummy("h", real=True)
    at_point = inner.subs(subs, simultaneous=True)
    moved = inner.subs({**subs, var: point + h}, simultaneous=True)
    quotient = (moved - at_point) / h
    values = []
    for d in ("+", "-"):
        try:
            value = _branch_limit(quotient, h, sympy.Integer(0), d)
        except TimeoutError:
            raise
        except Exception:
            value = None
        if value is None or not value.is_finite:
            raise NotSymbolic(f"not differentiable at the evaluation point "
                              f"(a one-sided difference quotient has no "
                              f"finite limit): {ast.unparse(node)!r}")
        values.append(value)
    if sympy.simplify(values[0] - values[1]) != 0:
        raise NotSymbolic(f"not differentiable at the evaluation point (the "
                          f"one-sided derivatives are {values[1]} and "
                          f"{values[0]}): {ast.unparse(node)!r}")
    return values[0]


def _law_to_sympy(node: ast.AST, lifted: Lifted, param_names: set, aux: dict):
    """Convert one claim-law expression node to sympy. `f(...)` calls
    substitute into the lifted body at the given (positional) arguments;
    any free name that isn't a parameter is an auxiliary real variable,
    same convention as conjecture.py's probe-route evaluator.

    `d(<expr>, var[, var2, ...])` is the one other special form: a partial
    derivative of `<expr>` (itself any law-expression, recursively parsed)
    with respect to the named parameter(s); `d(f(t, x), t)` is dV/dt,
    `d(f(t, x), x, x)` is the second partial d^2V/dx^2, `d(f(t, x), t, x)`
    the mixed partial. This single primitive is what turns ordinary
    equality/inequality claims into calculus claims (monotonicity via
    `d(f(x), x) >= 0`) and PDE claims (`d(f(t,x), t) == d(f(t,x), x, x)`,
    the heat equation) without any new relation grammar; a PDE is just an
    algebraic identity over partial derivatives, checked the same way
    every other derive-route claim is. The same primitive also covers
    Itô's-lemma coefficient matching for a claimed SDE drift/diffusion:
    true stochastic-process reasoning is out of reach here, but "does
    this claimed closed-form drift equal what Ito's lemma implies for
    this V" reduces to an
    ordinary equality claim over `d(...)` terms and free (aux) drift/
    diffusion symbols, ordinary machinery, not a new stochastic engine.

    `lim(<expr>, var, point)` (point a constant or `oo`/`-oo`) and
    `integrate(<expr>, var)` / `integrate(<expr>, var, lo, hi)` follow the
    same pattern: a special call form, `<expr>` recursively parsed like
    any other law expression, handed straight to sympy. `lim` raises
    NotSymbolic on a nonexistent limit (sympy's zoo/nan) rather than
    quietly returning nonsense."""
    if isinstance(node, ast.Expression):
        return _law_to_sympy(node.body, lifted, param_names, aux)
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, bool) and isinstance(node.value, (int, float, complex)):
            return _exact_numeric_literal(node.value)
        if lifted.opaque is not None and is_opaque_eligible(node.value):
            # registers into the *same* registry the function body
            # itself used, see Lifted's own docstring, so
            # `f(x) == "positive"` compares against the identical
            # symbol a `return "positive"` in the body would have
            # produced, not an unrelated fresh one.
            return lifted.opaque.register(node.value)
        raise NotSymbolic(f"non-numeric constant {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in param_names:
            return lifted.params[node.id]
        if is_reserved(node.id):
            raise NotSymbolic(f"{node.id!r} is reserved for its call form "
                              f"({node.id}(...)), not usable as a plain variable")
        if lifted.aggregate.get(node.id):
            raise NotSymbolic(
                f"{node.id!r} bundles multiple fields "
                f"({', '.join(lifted.aggregate[node.id])}), reference its "
                f"own fields directly ({node.id}.<field> or "
                f"{node.id}['<key>']), a bare {node.id!r} has no single "
                f"scalar value")
        if node.id in _MATH_ATTRS:
            return _MATH_ATTRS[node.id]
        return aux.setdefault(node.id, sympy.Symbol(node.id, real=True))
    if isinstance(node, ast.Attribute):
        # a dataclass-typed parameter's own field (`cfg.a`); see
        # _bind_params/Lifted's docstring. Only ever a composite-keyed
        # lookup into lifted.params, never a math constant here (that's
        # _MATH_ATTRS, handled via bare-name lookups in _expr_to_sympy's
        # body-lifting, not in claim-law text).
        if isinstance(node.value, ast.Name):
            composite = f"{node.value.id}.{node.attr}"
            if composite in lifted.params:
                return lifted.params[composite]
        raise NotSymbolic(f"unsupported attribute {ast.unparse(node)!r}")
    if isinstance(node, ast.Tuple):
        # a tuple literal in claim text (`f(x) == (a, b)`), compared
        # elementwise against a tuple-valued `f(...)`, see Lifted's
        # docstring and try_prove's tuple dispatch.
        return tuple(_law_to_sympy(e, lifted, param_names, aux) for e in node.elts)
    if isinstance(node, ast.Subscript):
        # a named-dict-style field (`params["a"]`), same composite-key
        # convention as the Attribute case above, just spelled with
        # subscript syntax (see _bind_params). Checked before the tuple-
        # index path since a string key is never a valid tuple index.
        if isinstance(node.value, ast.Name) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            composite = f"{node.value.id}.{node.slice.value}"
            if composite in lifted.params:
                return lifted.params[composite]
            raise NotSymbolic(f"unknown dict key {ast.unparse(node)!r}; this "
                              "key was never referenced in the function body, "
                              "so no symbol exists for it")
        value = _law_to_sympy(node.value, lifted, param_names, aux)
        if isinstance(value, _SymbolicArray):
            # f(...)[i] against an array-valued f (see _SymbolicArray),
            # either a literal int (a boundary claim, `f(...)[0] == ...`)
            # or a bare name, bound as a fresh aux real variable exactly
            # like lim(...)'s own bound variable above, substituted for
            # this array's own index. Either way the result is an
            # ordinary sympy.Expr from here on, nothing downstream
            # needs to know a _SymbolicArray was ever involved.
            idx = _literal_int_index(node.slice)
            if idx is not None:
                return value.expr.subs(value.index, sympy.Integer(idx))
            if isinstance(node.slice, ast.Name):
                idx_sym = aux.setdefault(node.slice.id, sympy.Symbol(node.slice.id, real=True))
                return value.expr.subs(value.index, idx_sym)
            raise NotSymbolic(f"array index must be a literal int or a bare "
                              f"name: {ast.unparse(node)!r}")
        if not isinstance(value, tuple):
            raise NotSymbolic(f"subscript on a non-tuple-valued expression: "
                              f"{ast.unparse(node)!r}")
        idx = _literal_int_index(node.slice)
        if idx is None or not (-len(value) <= idx < len(value)):
            raise NotSymbolic(f"tuple index out of range or not a literal "
                              f"int: {ast.unparse(node)!r}")
        return value[idx]
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ast.Not):
            v = _law_to_sympy(node.operand, lifted, param_names, aux)
            if isinstance(v, tuple):
                raise NotSymbolic(f"cannot use a tuple value in a unary "
                                  f"operation: {ast.unparse(node)!r}")
            if isinstance(node.op, ast.USub):
                return -v
            if isinstance(node.op, ast.UAdd):
                return v
            raise NotSymbolic(
                f"unsupported unary op in {ast.unparse(node)!r}")
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise NotSymbolic(f"unsupported operator in {ast.unparse(node)!r}")
        left = _law_to_sympy(node.left, lifted, param_names, aux)
        right = _law_to_sympy(node.right, lifted, param_names, aux)
        if isinstance(left, tuple) or isinstance(right, tuple):
            raise NotSymbolic(f"cannot use a tuple value in an arithmetic "
                              f"operation: {ast.unparse(node)!r}")
        return op(left, right)
    if isinstance(node, ast.Call):
        if node.keywords:
            raise NotSymbolic(f"keyword arguments not supported: {ast.unparse(node)!r}")
        if isinstance(node.func, ast.Name) and node.func.id == "d":
            if len(node.args) < 2:
                raise NotSymbolic(
                    f"d(...) needs an expression and at least one variable "
                    f"to differentiate with respect to: {ast.unparse(node)!r}")
            inner = _law_to_sympy(node.args[0], lifted, param_names, aux)
            rest = node.args[1:]
            # grammar.py's `_expand_d_at` rewrites `d(...)@{v=val, ...}`
            # (an evaluation-bar, "differentiate, then substitute") into
            # this same call with a private `__at__` sentinel name
            # separating the differentiation variables from the trailing
            # (var, value) substitution pairs, never user-facing, only
            # that expansion ever produces it.
            at_idx = next((i for i, a in enumerate(rest)
                          if isinstance(a, ast.Name) and a.id == _D_AT_SENTINEL), None)
            diff_args = rest[:at_idx] if at_idx is not None else rest
            if not diff_args:
                raise NotSymbolic(
                    f"d(...) needs at least one variable to differentiate "
                    f"with respect to: {ast.unparse(node)!r}")
            var_syms = []
            for a in diff_args:
                if not (isinstance(a, ast.Name) and a.id in param_names):
                    raise NotSymbolic(
                        f"d(...) can only differentiate with respect to a "
                        f"parameter name: {ast.unparse(node)!r}")
                var_syms.append(lifted.params[a.id])
            derivative = sympy.diff(inner, *var_syms)
            if at_idx is None:
                aux.setdefault(_KINKS_KEY, []).extend(
                    _kink_loci(inner, var_syms))
                return derivative
            sub_args = rest[at_idx + 1:]
            if not sub_args or len(sub_args) % 2 != 0:
                raise NotSymbolic(
                    f"d(...)'s evaluation point needs (var, value) pairs: "
                    f"{ast.unparse(node)!r}")
            subs = {}
            for i in range(0, len(sub_args), 2):
                var_node, val_node = sub_args[i], sub_args[i + 1]
                if not (isinstance(var_node, ast.Name) and var_node.id in param_names):
                    raise NotSymbolic(
                        f"d(...)'s evaluation point can only substitute a "
                        f"parameter name: {ast.unparse(node)!r}")
                subs[lifted.params[var_node.id]] = _law_to_sympy(val_node, lifted, param_names, aux)
            if _kink_loci(inner, var_syms):
                return _derivative_at(inner, var_syms, subs, node)
            return derivative.subs(subs, simultaneous=True)
        if isinstance(node.func, ast.Name) and node.func.id == "lim":
            if len(node.args) not in (3, 4):
                raise NotSymbolic(
                    f"lim(...) needs (expr, var, point) or "
                    f"(expr, var, point, '+'/'-'): {ast.unparse(node)!r}")
            direction = None
            if len(node.args) == 4:
                d_node = node.args[3]
                if not (isinstance(d_node, ast.Constant)
                        and d_node.value in ("+", "-")):
                    raise NotSymbolic(
                        f"lim(...)'s direction must be '+' or '-': "
                        f"{ast.unparse(node)!r}")
                direction = d_node.value
            var_node = node.args[1]
            if not isinstance(var_node, ast.Name):
                raise NotSymbolic(
                    f"lim(...)'s variable must be a bare name: "
                    f"{ast.unparse(node)!r}")
            # the limit variable need not be one of the function's own
            # parameters, e.g. a power-signal claim's outer
            # lim(integrate(f(t)^2, t, -T, T) / (2*T), T, oo) binds T
            # fresh, only inside the nested integrate. Registered in aux
            # (like Sum/Prod's index) *before* lifting `inner`, so a free
            # occurrence of the same name there resolves to this same
            # symbol rather than a separately-created duplicate.
            var_sym = (lifted.params[var_node.id] if var_node.id in param_names
                      else aux.setdefault(var_node.id, sympy.Symbol(var_node.id, real=True)))
            inner = _law_to_sympy(node.args[0], lifted, param_names, aux)
            point = _law_to_sympy(node.args[2], lifted, param_names, aux)
            if inner.has(sympy.Integral):
                # a nested integrate(...) arrives deferred (see the
                # integrate branch below); the limit computation needs
                # the closed form, so evaluate it here, an integral
                # sympy can't close leaves the limit unliftable, which
                # the NotSymbolic below reports.
                from .._timeout import _with_timeout, lowering_cap
                try:
                    inner = _with_timeout(lambda: inner.doit(deep=True),
                                          lowering_cap())
                except TimeoutError as e:
                    raise NotSymbolic(f"evaluating the integral inside "
                                      f"lim(...) exceeded the wall clock: "
                                      f"{ast.unparse(node)!r}") from e
                except Exception as e:
                    raise NotSymbolic(f"could not evaluate the integral inside "
                                      f"lim(...): {ast.unparse(node)!r}") from e
            if direction is None:
                # no explicit direction: at an infinite point direction
                # is meaningless (sympy's default applies); at a finite
                # point the honest reading is the TWO-SIDED limit,
                # unless the variable's own domain assumptions place it
                # entirely on one side of the point, in which case the
                # limit is taken from inside the domain (x in [0.1, 10]
                # approaching 0 means from the right)
                if point.is_infinite:
                    direction = "+"
                elif (var_sym.is_nonnegative and point.is_number
                        and point.is_nonpositive):
                    direction = "+"
                elif (var_sym.is_nonpositive and point.is_number
                        and point.is_nonnegative):
                    direction = "-"
                else:
                    direction = "+-"
            if any(var_sym in pw.free_symbols
                   for pw in inner.atoms(sympy.Piecewise)):
                return _branch_aware_limit(inner, var_sym, point, direction,
                                           node)
            from .._timeout import _with_timeout, lowering_cap
            try:
                result = _with_timeout(
                    lambda: sympy.limit(inner, var_sym, point, dir=direction),
                    lowering_cap())
            except TimeoutError as e:
                raise NotSymbolic(
                    f"the limit computation exceeded the wall clock: "
                    f"{ast.unparse(node)!r}") from e
            except Exception as first:
                # rescue: sympy's limit internals can fail on a form a
                # light rewrite fixes (a free-symbolic power base, an
                # uncancelled ratio), retry on reduced forms before
                # declaring the claim unliftable
                result = None
                for reducer in (sympy.cancel, sympy.together, sympy.simplify):
                    try:
                        result = _with_timeout(
                            lambda r=reducer: sympy.limit(r(inner), var_sym,
                                                          point, dir=direction),
                            lowering_cap())
                        break
                    except Exception:
                        continue
                if result is None:
                    result = _one_sided_lim_rescue(inner, var_sym, point,
                                                   direction, aux, node)
                if result is None:
                    if (isinstance(first, ValueError)
                            and "does not exist" in str(first)):
                        raise NotSymbolic(
                            f"the two-sided limit does not exist (left and "
                            f"right limits differ; state a one-sided point, "
                            f"e.g. 0+ or 0-, to claim one side): "
                            f"{ast.unparse(node)!r}") from first
                    raise NotSymbolic(
                        f"sympy could not evaluate this limit "
                        f"({type(first).__name__}): "
                        f"{ast.unparse(node)!r}") from first
            if result is sympy.zoo or result.has(sympy.nan) \
                    or result.has(sympy.I):
                rescued = _one_sided_lim_rescue(inner, var_sym, point,
                                                direction, aux, node)
                if rescued is None:
                    raise NotSymbolic(f"limit does not exist: {ast.unparse(node)!r}")
                result = rescued
            return result
        if isinstance(node.func, ast.Name) and node.func.id == "cauchy_pv":
            if len(node.args) != 1 or not (
                    isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == "integrate"):
                raise NotSymbolic(
                    f"P.V.(...) takes exactly one definite integrate(...) form: "
                    f"{ast.unparse(node)!r}")
            inner = _law_to_sympy(node.args[0], lifted, param_names, aux)
            if not isinstance(inner, sympy.Integral):
                raise NotSymbolic(
                    f"P.V.(...) needs a definite integral (with bounds), not an "
                    f"antiderivative: {ast.unparse(node)!r}")
            return _PV_FUNC(inner)
        if isinstance(node.func, ast.Name) and node.func.id == "integrate":
            nargs = len(node.args)
            if nargs == 2:
                inner = _law_to_sympy(node.args[0], lifted, param_names, aux)
                var_node = node.args[1]
                if not (isinstance(var_node, ast.Name) and var_node.id in param_names):
                    raise NotSymbolic(
                        f"integrate(...)'s variable must be a parameter name: "
                        f"{ast.unparse(node)!r}")
                from .._timeout import _with_timeout, lowering_cap
                try:
                    return _with_timeout(
                        lambda: sympy.integrate(inner, lifted.params[var_node.id]),
                        lowering_cap())
                except TimeoutError as e:
                    raise NotSymbolic(
                        f"the antiderivative computation exceeded the wall "
                        f"clock: {ast.unparse(node)!r}") from e
            if nargs < 4 or (nargs - 1) % 3 != 0:
                raise NotSymbolic(
                    f"integrate(...) needs (expr, var), (expr, var, lo, hi), "
                    f"or (expr, var, lo, hi, var2, lo2, hi2, ...): "
                    f"{ast.unparse(node)!r}")
            inner = _law_to_sympy(node.args[0], lifted, param_names, aux)
            # sympy's own integrate() natively accepts multiple (var, lo,
            # hi) tuples and evaluates them as nested integration in the
            # order given, grammar.py's own bracket-free multivariable
            # sugar (`integral f(x,y) dx|_b^a dy|_b2^a2`) already
            # produces exactly this flat, repeating-triple shape, so no
            # manual nesting is needed here.
            rest = node.args[1:]
            triples = []
            for k in range(0, len(rest), 3):
                var_node, lo_node, hi_node = rest[k], rest[k + 1], rest[k + 2]
                if not isinstance(var_node, ast.Name):
                    raise NotSymbolic(
                        f"integrate(...)'s variable must be a bare name: "
                        f"{ast.unparse(node)!r}")
                # a definite integral's variable is bound, so it need
                # not be one of the function's own parameters, a dummy
                # (`integrate(1/(a + b*cos(theta)), theta, 0, 2*pi)`)
                # registers in aux exactly like lim's variable above,
                # before the inner expression lifts, so free occurrences
                # there resolve to this same symbol.
                var_sym = (lifted.params[var_node.id] if var_node.id in param_names
                          else aux.setdefault(var_node.id,
                                              sympy.Symbol(var_node.id, real=True)))
                lo = _law_to_sympy(lo_node, lifted, param_names, aux)
                hi = _law_to_sympy(hi_node, lifted, param_names, aux)
                triples.append((var_sym, lo, hi))
            # deferred, not evaluated here: the decision procedure
            # evaluates under its wall-clock cap, and the residue
            # machinery needs the true Integral object, an eager
            # sympy.integrate() would hand it only sympy's answer,
            # which is known to be wrong for some discontinuous-
            # antiderivative shapes.
            return sympy.Integral(inner, *triples)
        if isinstance(node.func, ast.Name) and node.func.id in ("Sum", "Prod"):
            if len(node.args) != 4:
                raise NotSymbolic(
                    f"{node.func.id}(...) needs exactly (expr, var, lo, hi): "
                    f"{ast.unparse(node)!r}")
            var_node = node.args[1]
            if not isinstance(var_node, ast.Name):
                raise NotSymbolic(
                    f"{node.func.id}(...)'s index must be a bare name: "
                    f"{ast.unparse(node)!r}")
            # unlike d/lim/integrate, the index need not be one of the
            # function's own parameters; it's a fresh dummy variable, so
            # it's registered in aux (like any other free name) rather
            # than looked up in lifted.params. Known sharp edge: if the
            # index name happens to coincide with an actual parameter,
            # the parameter binding wins (ast.Name resolves param_names
            # first), the same collision already documented for the `n=`
            # domain-intensity modifier.
            var_sym = aux.setdefault(var_node.id, sympy.Symbol(var_node.id, integer=True))
            inner = _law_to_sympy(node.args[0], lifted, param_names, aux)
            lo = _law_to_sympy(node.args[2], lifted, param_names, aux)
            hi = _law_to_sympy(node.args[3], lifted, param_names, aux)
            op = sympy.summation if node.func.id == "Sum" else sympy.product
            # sympy's symbolic summation can recurse without bound (its
            # hypergeometric evaluator on a factorial-ratio summand ran
            # 150s+ live), cap the lowering like the limit/integrate
            # sites, and keep the unevaluated Sum on a timeout so the
            # claim declines honestly instead of hanging
            from .._timeout import _with_timeout, lowering_cap
            try:
                return _with_timeout(lambda: op(inner, (var_sym, lo, hi)),
                                     lowering_cap())
            except (TimeoutError, RecursionError):
                cls = sympy.Sum if node.func.id == "Sum" else sympy.Product
                return cls(inner, (var_sym, lo, hi))
        if isinstance(node.func, ast.Name) and node.func.id == "f":
            # positional over the *real signature* (sig_params), not
            # lifted.params, an aggregate-typed parameter (dataclass/
            # named-dict, see _bind_params) expands into several entries
            # in lifted.params for one actual positional slot, so arg
            # count/order must track sig_params, never len(lifted.params).
            if len(node.args) != len(lifted.sig_params):
                raise NotSymbolic(
                    f"f() called with {len(node.args)} args, expected "
                    f"{len(lifted.sig_params)}")
            subs = {}
            for sig_p, arg_node in zip(lifted.sig_params, node.args):
                keys = lifted.aggregate.get(sig_p)
                if keys:
                    # cannot substitute a *different* value for a bundled
                    # parameter; there's no way to spell "a different
                    # Config instance" in this grammar. Only referencing
                    # it as itself (so its own field symbols are exactly
                    # the free variables the claim's law can use, e.g.
                    # `cfg.a`) is supported.
                    if not (isinstance(arg_node, ast.Name) and arg_node.id == sig_p):
                        raise NotSymbolic(
                            f"cannot substitute a different value for "
                            f"{sig_p!r}; it bundles multiple fields "
                            f"({', '.join(keys)}); only a bare {sig_p!r} "
                            f"(referencing its own fields directly) is "
                            f"supported: {ast.unparse(node)!r}")
                    continue
                val = _law_to_sympy(arg_node, lifted, param_names, aux)
                subs[lifted.params[sig_p]] = val

            def _subs_one(e):
                if isinstance(e, _SymbolicArray):
                    return _SymbolicArray(e.expr.subs(subs, simultaneous=True), e.index,
                                          e.length.subs(subs, simultaneous=True))
                return e.subs(subs, simultaneous=True)

            if isinstance(lifted.expr, tuple):
                return tuple(_subs_one(e) for e in lifted.expr)
            return _subs_one(lifted.expr)
        name = _call_name(node)
        if name in _SYMPY_FUNCS:
            return _SYMPY_FUNCS[name](*[_law_to_sympy(a, lifted, param_names, aux)
                                        for a in node.args])
        bound = (aux.get(_AUX_FUNCS_KEY) or {}).get(name)
        if bound is not None:
            # a claim-bound auxiliary function (g, budget_line, ...):
            # substitute into ITS lifted body at the given positional
            # arguments, each argument parsed against the claim's own
            # context, the same mechanism as the f(...) branch above,
            # aimed at a different lifted target.
            if any(bound.aggregate.get(p) for p in bound.sig_params):
                raise NotSymbolic(
                    f"{name!r} has a dataclass/dict-bundled parameter, "
                    f"not supported for a bound function in claim text")
            if len(node.args) != len(bound.sig_params):
                raise NotSymbolic(
                    f"{name}() called with {len(node.args)} args, expected "
                    f"{len(bound.sig_params)}")
            subs = {}
            for sig_p, arg_node in zip(bound.sig_params, node.args):
                val = _law_to_sympy(arg_node, lifted, param_names, aux)
                if isinstance(val, (tuple, _SymbolicArray)):
                    raise NotSymbolic(
                        f"cannot pass a tuple- or array-valued expression "
                        f"as an argument: {ast.unparse(node)!r}")
                subs[bound.params[sig_p]] = val
            if isinstance(bound.expr, tuple):
                return tuple(e.subs(subs, simultaneous=True) for e in bound.expr)
            if isinstance(bound.expr, _SymbolicArray):
                raise NotSymbolic(
                    f"{name!r} returns an array, not supported for a "
                    f"bound function in claim text")
            return bound.expr.subs(subs, simultaneous=True)
        if name in ("sum", "prod"):
            # lowercase sum/prod is only ever the probe route's sequence
            # aggregate (conjecture.py's _SAFE_FUNCS); it's not
            # registered here at all, on any arity, so a claim reaching
            # this branch is far more likely to be a typo'd Sum/Prod
            # (the derive-route indexed form) than a genuine attempt to
            # symbolically sum a sequence.
            want = "Sum" if name == "sum" else "Prod"
            raise NotSymbolic(
                f"{name!r} is not available on the derive route; did you "
                f"mean {want}(expr, var, lo, hi)? {ast.unparse(node)!r}")
        raise NotSymbolic(
            f"{_unsupported_call_message(node)}, not a known math "
            f"function; a function of that name defined in f's module or "
            f"the calling scope binds automatically, or bind one "
            f"explicitly with funcs={{{name!r}: <function>}}")
    if isinstance(node, (ast.Compare, ast.BoolOp)) or (
            isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
        # a truth-valued law expression (`f(mi, chance) == (mi <=
        # chance)`): lowered to the 0/1 indicator of the condition,
        # mirroring what the body lift does for `return mi <= chance`,
        # so a boolean function and the boolean law it satisfies meet
        # as the same Piecewise shape. Sides recurse through this
        # function, so `f(a) <= f(b)` inside the condition substitutes
        # the lifted body like any other law expression.
        from ._base import _SYMPY_RELOPS

        def cond_of(n: ast.AST):
            if isinstance(n, ast.BoolOp):
                parts = [cond_of(v) for v in n.values]
                return (sympy.And(*parts) if isinstance(n.op, ast.And)
                        else sympy.Or(*parts))
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
                return sympy.Not(cond_of(n.operand))
            if isinstance(n, ast.Compare) and len(n.ops) == 1:
                relop = _SYMPY_RELOPS.get(type(n.ops[0]))
                if relop is not None:
                    return relop(
                        _law_to_sympy(n.left, lifted, param_names, aux),
                        _law_to_sympy(n.comparators[0], lifted,
                                      param_names, aux))
            raise NotSymbolic(f"unsupported condition inside a "
                              f"truth-valued law expression: "
                              f"{ast.unparse(n)!r}")
        return sympy.Piecewise((sympy.Integer(1), cond_of(node)),
                               (sympy.Integer(0), True))
    raise NotSymbolic(f"unsupported syntax {ast.unparse(node)!r}")


def _branch_pruning_sketch(fn, facts) -> str | None:
    """A specific reason `lift_conditioned()` failed for `fn`, one clause
    per `ast.If` reachable in its body, reuses the exact same
    diagnosis `mathema audit --deriv-report` already computes
    (`_explain_branch()`, `inventory.derivability_report()`'s own data
    source) so a *live claim's* own failure sketch names the real
    reason (a condition shape branch-pruning doesn't recognize at all,
    vs. a recognized shape whose declared domain just isn't specific
    enough for the parameters it names) instead of one generic
    catch-all every unliftable branchy function got before this. `None`
    when there's genuinely nothing branch-specific to say, no branch
    at all, no source, or (matching `lift_conditioned()`'s own gate
    exactly) a loop or recursion is ALSO present, in which case the
    real blocker may not be the branch shape at all and the generic
    composite message stays honest instead of pointing at the wrong
    cause."""
    if not facts.branch_count or facts.tree is None or facts.loops or facts.recursion:
        return None
    unmodified = _unmodified_params(facts.tree, set(facts.params))
    params, _aggregate = _bind_params(fn, facts)
    affine_locals = _affine_locals(facts.tree, unmodified, params)
    clauses = []
    for node in ast.walk(facts.tree):
        if isinstance(node, ast.If):
            info = _explain_branch(node.test, unmodified, affine_locals, params)
            cond = ast.unparse(node.test)
            if info["kind"] == "resolvable":
                clauses.append(f"line {node.lineno} ({cond!r}) needs a domain "
                               f"specific enough for {', '.join(info['needs_domain_for'])}")
            else:
                clauses.append(f"line {node.lineno} ({cond!r}): {info['reason']}")
    return "; ".join(clauses) if clauses else None


def _try_case_split(lhs, rhs, relation: str, domain: dict, bound_context,
                    params: dict, opaque=None, extensive: bool = False) -> "ProofResult | None":
    """Intent:
        Fallback retry for an undecided proof: find a pole/stationary/
        domain-transition point in lhs - rhs and re-attempt
        _prove_relation on each side of it.

    Notes:
        Only reached when the ordinary single-context attempt already
        returned undecided, never a first attempt. Excludes inflection
        points: no validated case adds decidability. Wall-clock capped
        (1s, 15s when extensive), matching probing.py's own two-tier
        cap. Degrades to None on any failure, leaving the original
        undecided result as it was.
    """
    try:
        from .. import diagnostics
        from .._timeout import (EXTENSIVE_TIMEOUT_SECONDS,
                                FAST_TIMEOUT_SECONDS, _with_timeout)
        timeout = EXTENSIVE_TIMEOUT_SECONDS if extensive else FAST_TIMEOUT_SECONDS
        points = _with_timeout(
            lambda: diagnostics._critical_points_over_expr(lhs - rhs), timeout)
    except TimeoutError:
        raise
    except Exception:
        return None
    free = _free_names(lhs) | _free_names(rhs)
    by_var: dict[str, list] = {}
    kind_by_var: dict[str, str] = {}
    for p in points:
        if p["kind"] not in ("pole", "stationary", "domain_transition") or p["variable"] not in free:
            continue
        try:
            v = float(sympy.sympify(p["at"]).evalf())
        except TimeoutError:
            raise
        except Exception:
            continue
        if v != v or abs(v) == float("inf"):
            continue
        by_var.setdefault(p["variable"], []).append(v)
        kind_by_var.setdefault(p["variable"], p["kind"])
    for var, split_points in by_var.items():
        result = _prove_relation_case_split(lhs, rhs, relation, domain, bound_context,
                                            params, var, split_points, kind_by_var[var],
                                            opaque=opaque, extensive=extensive)
        if result is not None:
            return result
    return None


def _augment_domain_from_calls(fn, facts, lhs_src: str, rhs_src: str,
                               domain: dict) -> "dict | None":
    """Intent:
        A widened domain for parameters the claim leaves unbound but
        its own calls constrain: the hull of every argument passed at
        an unbound slot, unioned across calls; `f(a, a)` gives the
        second slot the first parameter's range.

    Notes:
        `None` when nothing augments (no unbound slot, or a hull that
        can't be computed). Only ever ADDS bounds for absent keys;
        declared bounds are never touched.
    """
    from ._base import _bind_params
    from ._proof_support import _interval_bounds
    from ..domain import Interval

    sig_params = list(facts.params)
    missing = [p for p in sig_params if p not in domain]
    if not missing:
        return None
    params, _aggregate = _bind_params(fn, facts)
    ext_params = dict(params)
    for name in domain:
        if name not in ext_params:
            ext_params[name] = sympy.Symbol(name, real=True)
    from ._base import _expr_to_sympy
    hulls: dict = {}
    for src in (lhs_src, rhs_src):
        if not src:
            continue
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError:
            return None
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "f"):
                continue
            for p, arg in zip(sig_params, node.args):
                if p not in missing:
                    continue
                if arg is None:
                    return None
                try:
                    arg_expr = _expr_to_sympy(arg, dict(ext_params))
                except NotSymbolic:
                    return None
                if isinstance(arg_expr, tuple):
                    return None
                hull = _interval_bounds(arg_expr, domain, ext_params)
                if hull is None:
                    return None
                lo = hull.min if isinstance(hull, sympy.AccumBounds) else hull
                hi = hull.max if isinstance(hull, sympy.AccumBounds) else hull
                if p in hulls:
                    old_lo, old_hi = hulls[p]
                    lo = sympy.Min(old_lo, lo)
                    hi = sympy.Max(old_hi, hi)
                hulls[p] = (lo, hi)
    if not hulls:
        return None
    augmented = dict(domain)
    for p, (lo, hi) in hulls.items():
        augmented[p] = Interval(lo, hi)
    return augmented
def _recurrence_domain_gate(lhs_src: str, rhs_src: str, rec,
                            domain: dict) -> "tuple[ProofResult | None, bool]":
    """Intent:
        The soundness gate for a recurrence closed form, which is exact
        only at integer arguments: the recursed parameter's declared
        domain must be an integer subset, every argument the claim
        passes to `f` must be provably integer-valued under it, and the
        runtime recursion depth the domain's top demands must fit the
        interpreter's stack: the closed form settles the mathematics,
        but the implementation still recurses one frame per step, and a
        call whose depth exceeds `sys.getrecursionlimit()` raises
        RecursionError however true the formula is.

    Notes:
        Returns `(verdict, closed_only)`. `verdict` is None when the
        gate passes; otherwise an undecided ProofResult whose sketch
        names the exact repair (declare the domain `subset Z`), never a
        guess at non-integer behavior, the runtime recursion on a
        non-integer walks a different lattice than the closed form
        entirely. `closed_only` is True when every call argument
        provably stays at or above the closed form's first valid index,
        so the bare closed form can substitute in place of the full
        piecewise object (which keeps boundary-branch conditions out of
        expressions the deciders then can't settle).
    """
    from ._base import _expr_to_sympy
    from ._proof_support import _interval_bounds, _verified_sign

    (param,) = rec.sig_params
    bound = domain.get(param)
    if getattr(bound, "base_type", "R") not in ("Z", "N"):
        return ProofResult(
            "undecided",
            sketch=f"f is recursive and its closed form is only valid at "
                   f"integer arguments, declare {param}'s domain as an "
                   f"integer subset (e.g. `for {param} in [0, 20] subset Z, "
                   f"...`) to decide this claim"), False
    info = rec.recurrence or {}
    if info:
        import sys
        from ..domain import bound_to_sympy_set
        limit = sys.getrecursionlimit()
        budget = limit // 2   # headroom for frames already on the stack
        try:
            hi = bound_to_sympy_set(bound).sup
            hi_val = float(hi) if getattr(hi, "is_finite", False) else None
        except TimeoutError:
            raise
        except Exception:
            hi_val = None
        min_shift, top = info["min_shift"], info["top"]
        depth = None if hi_val is None else (hi_val - top) / min_shift
        if depth is None or depth > budget:
            safe_hi = top + budget * min_shift
            at = f"{param} = {int(hi_val)}" if hi_val is not None \
                else f"large {param}"
            return ProofResult(
                "undecided",
                sketch=f"the recurrence closed form settles the mathematics, "
                       f"but the implementation recurses about one stack "
                       f"frame per index step: at {at} it needs "
                       f"~{'unbounded' if depth is None else int(depth)} "
                       f"frames against an interpreter recursion limit of "
                       f"{limit}, so the call raises RecursionError inside "
                       f"this domain, narrow the domain (about "
                       f"{param} <= {safe_hi} is safe here), rewrite the "
                       f"function iteratively, or state the machine limit "
                       f"as its own raises(...) claim"), False
    n_sym = rec.params[param]
    valid_from = info.get("valid_from")
    closed_only = valid_from is not None
    for src in (lhs_src, rhs_src):
        if not src:
            continue
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError:
            return None, False
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "f"):
                continue
            for arg in node.args:
                try:
                    arg_expr = _expr_to_sympy(arg, {param: n_sym})
                except NotSymbolic:
                    return ProofResult(
                        "undecided",
                        sketch="a call argument in this claim isn't "
                               "expressible over the recursed parameter, so "
                               "the recurrence closed form can't be applied"), False
                if isinstance(arg_expr, tuple) or arg_expr.is_integer is not True:
                    return ProofResult(
                        "undecided",
                        sketch=f"the call argument `{ast.unparse(arg)}` isn't "
                               f"provably integer-valued, and f's recurrence "
                               f"closed form is only exact at integers"), False
                if closed_only:
                    hull = _interval_bounds(
                        arg_expr - sympy.Integer(valid_from), domain,
                        {param: n_sym})
                    if hull is None:
                        closed_only = False
                    else:
                        lo = hull.min if isinstance(hull, sympy.AccumBounds) \
                            else hull
                        if _verified_sign(lo) not in (0, 1):
                            closed_only = False
    return None, closed_only


from ._base import NEGATED_REL as _NEGATED_REL  # noqa: E402


@dataclass
class _AssumptionContext:
    """Intent:
        The algebraic content of a claim's `assuming` clause, in the
        two shapes the guard machinery consumes: `gaps` holds
        (expr, strict) pairs meaning expr >= 0 (or > 0 when strict)
        everywhere the claim quantifies, `nonzero` holds expressions
        assumed != 0.

    Notes:
        Injected into the guard adjudication below rather than read
        from shared state, so the same rules serve an explicit
        `assuming` clause, the negated-guard assumptions of
        `is_defined(f)`, and (empty) the unassuming default.
    """
    gaps: list = field(default_factory=list)
    nonzero: list = field(default_factory=list)

    def excludes_guard(self, cond, domain: dict, params: dict) -> bool:
        """Intent:
            True when the assumed region provably avoids the guard
            region, so the guard can never fire inside the quantified
            domain. Sound rules only: G >= gap >= 0 kills `G < 0`;
            strict positivity kills `G <= 0` and `G == 0`; an equality
            guard whose factored product is nonzero factor-by-factor
            (each matching an assumed-nonzero or strictly-positive
            expression) never fires either.
        """
        from ._proof_support import _interval_bounds, _verified_sign
        if not isinstance(cond, (sympy.Lt, sympy.Le, sympy.Eq)):
            return False
        big_g = cond.lhs - cond.rhs
        for gap, strict in self.gaps:
            # note: hull of (G - gap) >= 0 means G >= gap everywhere,
            # and gap >= 0 is assumed, so G >= 0 follows
            try:
                hull = _interval_bounds(big_g - gap, domain, params)
            except TimeoutError:
                raise
            except Exception:
                hull = None
            if hull is None:
                continue
            lo = hull.min if isinstance(hull, sympy.AccumBounds) else hull
            lo_sign = _verified_sign(lo)
            if lo_sign not in (0, 1):
                continue
            if isinstance(cond, sympy.Lt):
                return True
            if lo_sign == 1 or strict:
                return True
        if isinstance(cond, sympy.Eq):
            try:
                factors = sympy.Mul.make_args(sympy.factor(big_g))
            except TimeoutError:
                raise
            except Exception:
                factors = (big_g,)
            if all(self._factor_nonzero(fct) for fct in factors):
                return True
        return False

    def _factor_nonzero(self, factor) -> bool:
        if factor.is_number:
            return bool(factor != 0)
        candidates = list(self.nonzero) + [gap for gap, strict in self.gaps
                                           if strict]
        for expr in candidates:
            try:
                if sympy.simplify(factor - expr) == 0 \
                        or sympy.simplify(factor + expr) == 0:
                    return True
            except TimeoutError:
                raise
            except Exception:
                continue
        return False

    def admits_point(self, at: dict) -> bool:
        """Intent:
            Does this exact candidate point satisfy every assumed
            conjunct? A witness must live inside the assumed region or
            it witnesses nothing.
        """
        for gap, strict in self.gaps:
            try:
                v = complex(gap.subs(at).evalf())
            except TimeoutError:
                raise
            except Exception:
                return False
            if abs(v.imag) > 1e-12 or v.real < 0 or (strict and v.real == 0):
                return False
        for nz in self.nonzero:
            try:
                if abs(complex(nz.subs(at).evalf())) < 1e-12:
                    return False
            except TimeoutError:
                raise
            except Exception:
                return False
        return True


def _binding_operator_exempt_calls(tree) -> set:
    """Intent:
        id()s of every call sitting under a variable-binding operator
        (lim/integrate/Sum/Prod/cauchy_pv) whose arguments mention that
        operator's own bound variable: those calls don't quantify over
        the claim's domain pointwise, `lim(f(x), x, oo)` never
        evaluates f at x = 0 however wide x's domain is, so the
        pointwise raise-region reading must not touch them.
    """
    exempt: set = set()

    def visit(node, bound_names):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fname = node.func.id
            if fname in ("lim", "integrate", "Sum", "Prod", "cauchy_pv") \
                    and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Name):
                bound_names = bound_names | {node.args[1].id}
            elif bound_names:
                arg_names = {n.id for a in node.args
                             for n in ast.walk(a)
                             if isinstance(n, ast.Name)}
                if arg_names & bound_names:
                    exempt.add(id(node))
        for child in ast.iter_child_nodes(node):
            visit(child, bound_names)

    visit(tree, frozenset())
    return exempt


def _evaluation_points(tree, lifted, param_names: set, aux: dict) -> dict:
    """Intent:
        For every call nested inside a `d(...)` evaluated at a point
        (`d(<expr>, <vars>, __at__, v, val, ...)`, the expansion of
        `@{v=val, ...}`), the substitution that point fixes: id() of
        the call node -> {parameter symbol: value}. Inner points win
        over outer ones on the same parameter.

    Notes:
        A call outside any evaluation point is absent from the map. A
        pair whose value doesn't convert is left out, so that
        parameter stays free.
    """
    points: dict = {}

    def visit(node, fixed):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "d" and node.args:
                rest = node.args[1:]
                at_idx = next((i for i, a in enumerate(rest)
                               if isinstance(a, ast.Name)
                               and a.id == _D_AT_SENTINEL), None)
                if at_idx is not None:
                    pairs = rest[at_idx + 1:]
                    inner = dict(fixed)
                    for i in range(0, len(pairs) - 1, 2):
                        var_node, val_node = pairs[i], pairs[i + 1]
                        if not (isinstance(var_node, ast.Name)
                                and var_node.id in param_names):
                            continue
                        try:
                            inner[lifted.params[var_node.id]] = \
                                _law_to_sympy(val_node, lifted,
                                              param_names, aux)
                        except TimeoutError:
                            raise
                        except Exception:
                            continue
                    visit(node.args[0], inner)
                    for child in rest:
                        visit(child, fixed)
                    return
            if fixed:
                points[id(node)] = dict(fixed)
        for child in ast.iter_child_nodes(node):
            visit(child, fixed)

    visit(tree, {})
    return points


def _call_guard_conditions(lhs_src: str, rhs_src: str, lifted,
                           guards: list, bound_funcs: dict | None = None,
                           aux_guards: dict | None = None) -> "list | None":
    """Intent:
        Every raise-guard condition, substituted with the arguments of
        every claim call it applies to: f's guards at each f(...) call,
        a bound function's guards at each of ITS calls. The single
        source both the raise-region verdict and `is_defined(f)`'s
        assumption builder walk; one reading of which guard fires
        where, never two.

    Notes:
        Entries are (condition, exception name, call text, target
        name, substituted argument expressions, evaluation point), the
        argument expressions feed witness corroboration, which
        executes the real call at a candidate witness. A call inside
        `d(...)@{v=val}` has v fixed at val in its arguments, so a
        guard is read only where the claim evaluates the call; the
        last entry is that {symbol: value} map (empty elsewhere).
        `None` declines the whole analysis (an unparseable law, a
        tuple-valued argument), the caller MUST treat that as
        unexcludable (undecided), never as "no guards".
    """
    param_names = set(lifted.params)
    aux: dict = {_AUX_FUNCS_KEY: bound_funcs} if bound_funcs else {}
    out: list = []
    for src in (lhs_src, rhs_src):
        if not src:
            continue
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError:
            return None
        exempt = _binding_operator_exempt_calls(tree)
        try:
            at_points = _evaluation_points(tree, lifted, param_names, aux)
        except TimeoutError:
            raise
        except Exception:
            return None
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)):
                continue
            name = node.func.id
            if name == "f":
                target, target_guards = lifted, guards
            elif aux_guards and name in aux_guards \
                    and bound_funcs and name in bound_funcs:
                target, target_guards = bound_funcs[name], aux_guards[name]
            else:
                continue
            if id(node) in exempt or not target_guards:
                continue
            fixed = at_points.get(id(node), {})
            try:
                args = [_law_to_sympy(a, lifted, param_names, aux)
                        for a in node.args]
                if fixed:
                    args = [a if isinstance(a, (tuple, _SymbolicArray))
                            else sympy.sympify(a).subs(fixed,
                                                       simultaneous=True)
                            for a in args]
            except TimeoutError:
                raise
            except Exception:
                return None
            subs = {}
            for p, arg in zip(target.sig_params, args):
                sym = target.params.get(p)
                if sym is None or isinstance(arg, (tuple, _SymbolicArray)):
                    return None
                subs[sym] = arg
            for cond, exc in target_guards:
                try:
                    out.append((cond.subs(subs, simultaneous=True), exc,
                                ast.unparse(node), name, list(args),
                                fixed))
                except TimeoutError:
                    raise
                except Exception:
                    return None
    return out


def _extended_params(lifted_params: dict, sub_conds: list) -> dict:
    """Intent:
        The full name -> symbol map the guard conditions range over:
        the claim's real parameters plus every other free symbol (a
        let-declared free variable, an aux name) under its own name,
        so a `let py be [0.5, 20]` bound confines py's guard exactly
        like a parameter's bound confines the parameter's.
    """
    ext = dict(lifted_params)
    known = set(ext.values())
    for cond, *_rest in sub_conds:
        for sym in cond.free_symbols:
            if sym not in known:
                ext[str(sym)] = sym
                known.add(sym)
    return ext


def _witness_candidates(ext_params: dict, domain: dict) -> "tuple | None":
    """Intent:
        Exact candidate witness points over the declared box: the
        midpoint, then the all-low and all-high corners; an unbounded
        name sits at 1. Returns (points, base) or None when a bound's
        endpoints can't be read at all.
    """
    from ._proof_support import _exact_endpoint
    from ..domain import bound_to_sympy_set

    base: dict = {}
    ranges: dict = {}
    for name, sym in ext_params.items():
        bound = domain.get(name)
        if bound is None:
            base[sym] = sympy.Integer(1)
            continue
        try:
            sset = bound_to_sympy_set(bound)
            lo, hi = _exact_endpoint(sset.inf), _exact_endpoint(sset.sup)
        except TimeoutError:
            raise
        except Exception:
            return None
        if not (getattr(lo, "is_finite", False)
                and getattr(hi, "is_finite", False)):
            base[sym] = sympy.Integer(1)
            continue
        base[sym] = (lo + hi) / 2
        ranges[sym] = (lo, hi)
    points = [base]
    for pick in (0, 1):
        alt = dict(base)
        for sym, (lo, hi) in ranges.items():
            alt[sym] = (lo, hi)[pick]
        points.append(alt)
    return points, base


def _point_in_domain(at: dict, ext_params: dict, domain: dict) -> bool:
    """Intent:
        Exact membership of a candidate point, exclusions and open
        endpoints included: a domain spelled [-1, 1] minus {1} never
        contains r = 1, so a guard holding only there is no witness.
    """
    from ..domain import domain_contains
    for name, sym in ext_params.items():
        bound = domain.get(name)
        if bound is None or sym not in at:
            continue
        try:
            value = float(sympy.Float(at[sym]))
            if value.is_integer():
                value = int(value)
        except TimeoutError:
            raise
        except Exception:
            continue
        if not domain_contains(value, bound):
            return False
    return True


def _find_guard_witness(cond, points: list, base: dict, ext_params: dict,
                        domain: dict, assumptions: "_AssumptionContext"):
    """Intent:
        An exact in-domain, assumption-admitted point where the guard
        condition holds, candidate points first, then a solved
        one-symbol region intersected with that symbol's own bound.
    """
    for at in points:
        if not assumptions.admits_point(at) \
                or not _point_in_domain(at, ext_params, domain):
            continue
        try:
            hit = sympy.simplify(cond.subs(at))
        except TimeoutError:
            raise
        except Exception:
            continue
        if hit is sympy.true:
            return at
    if len(cond.free_symbols) == 1:
        (sym,) = cond.free_symbols
        name = next((n for n, s in ext_params.items() if s == sym), None)
        point = _solved_witness(cond, sym,
                                domain.get(name) if name else None)
        if point is not None:
            candidate = dict(base)
            candidate[sym] = point
            if assumptions.admits_point(candidate) \
                    and _point_in_domain(candidate, ext_params, domain):
                return candidate
    return None


def _defined_assumptions(sub_conds: list) -> "tuple[list, list, list]":
    """Intent:
        The negation of each substituted raise region, in the shapes
        the decision machinery consumes: nonnegative gaps
        ((expr, strict) meaning expr >= 0 / > 0), assumed-nonzero
        expressions, and Q predicates for ask()'s context.

    Notes:
        A guard whose condition isn't a plain relational contributes
        nothing, `assuming is_defined(f)` still excludes its region
        (that is what the quantifier MEANS), the proof machinery just
        gains no algebraic handle from it.
    """
    gaps: list = []
    nonzero: list = []
    preds: list = []
    for cond in sub_conds:
        if not isinstance(cond, sympy.core.relational.Relational):
            continue
        neg = _NEGATED_REL.get(type(cond))
        if neg is None:
            continue
        flipped = neg(cond.lhs, cond.rhs)
        gap = flipped.lhs - flipped.rhs
        if isinstance(flipped, sympy.Ge):
            gaps.append((gap, False))
            preds.append(sympy.Q.nonnegative(gap))
        elif isinstance(flipped, sympy.Gt):
            gaps.append((gap, True))
            preds.append(sympy.Q.positive(gap))
        elif isinstance(flipped, sympy.Le):
            gaps.append((-gap, False))
            preds.append(sympy.Q.nonnegative(-gap))
        elif isinstance(flipped, sympy.Lt):
            gaps.append((-gap, True))
            preds.append(sympy.Q.positive(-gap))
        elif isinstance(flipped, sympy.Ne):
            nonzero.append(gap)
            preds.append(sympy.Q.nonzero(gap))
    return gaps, nonzero, preds


def _witness_corroborated(callable_target, arg_exprs: list,
                          witness: dict) -> bool:
    """Intent:
        True only when the real call, executed at the candidate
        witness point, actually raises, the executed-witness bar a
        guard disproof must clear. Evaluates each substituted argument
        expression at the witness numerically; any evaluation failure,
        or a call that returns a value, refuses corroboration.
    """
    import inspect
    try:
        annotations = [prm.annotation for prm in
                       inspect.signature(callable_target).parameters.values()]
    except (TypeError, ValueError):
        annotations = []
    vals = []
    for i, expr in enumerate(arg_exprs):
        try:
            e = sympy.sympify(expr).subs(witness)
            # an argument symbol the guard never constrained has no
            # witness coordinate: any concrete value serves, since the
            # claim leaves it free at this point
            e = e.subs({s: sympy.Integer(1) for s in e.free_symbols})
            v = complex(sympy.N(e))
        except TimeoutError:
            raise
        except Exception:
            return False
        if abs(v.imag) > 1e-12:
            return False
        # a float-annotated parameter always gets a float; otherwise an
        # integral value is passed as int, since a float where the code
        # expects an int (a range() bound) would raise a TypeError that
        # has nothing to do with the guard under test
        annotation = annotations[i] if i < len(annotations) else None
        if annotation is float or annotation == "float":
            vals.append(float(v.real))
        else:
            vals.append(int(v.real) if float(v.real).is_integer() else v.real)
    try:
        callable_target(*vals)
    except TimeoutError:
        raise
    except Exception:
        return True
    return False


def _raise_region_verdict(lhs_src: str, rhs_src: str, lifted,
                          guards: list, domain: dict,
                          bound_funcs: dict | None = None,
                          assumed_gaps: list | None = None,
                          assumed_nonzero: list | None = None,
                          aux_guards: dict | None = None,
                          callables: dict | None = None) -> "ProofResult | None":
    """Intent:
        The pedantic reading of a value claim against functions that
        can raise: at any point of the declared domain where one of
        the claim's calls (to f OR to a bound function) hits a raise
        guard, that call has no value and the claim is FALSE there.
        Exhibit such a point (disproven, with the remedy named), or
        prove every call avoids every guard (None: the value
        expressions stand); anything in between is undecided, never
        assumed away.

    Notes:
        Orchestration only, the walk, the extended symbol map, the
        witness candidates, and the assumption rules each live in
        their own helper above. Exclusion, in order per guard: the
        relational-truth hull over the domain, the assumption context,
        then (for `G < 0` guards) the nonnegativity certificate. The
        caller wall-clocks this whole function; every internal broad
        except re-raises TimeoutError so the alarm is never swallowed.
    """
    from ._proof_support import (_nonneg_certificate,
                                 _relational_truth_over_domain)

    sub_conds = _call_guard_conditions(lhs_src, rhs_src, lifted, guards,
                                       bound_funcs, aux_guards)
    if sub_conds is None:
        # the analysis itself declined (an unliftable argument, an
        # unparseable law): the guards stand UNEXCLUDED, never read
        # a failed analysis as "no guards"
        return ProofResult(
            "undecided",
            sketch="a call's arguments could not be analyzed against the "
                   "raise guards, narrow the domain to where every call "
                   "returns, or state the raising region as its own "
                   "raises(...) claim")
    if not sub_conds:
        return None
    ext_params = _extended_params(lifted.params, sub_conds)
    candidates = _witness_candidates(ext_params, domain)
    if candidates is None:
        return None
    points, base = candidates
    assumptions = _AssumptionContext(gaps=list(assumed_gaps or []),
                                     nonzero=list(assumed_nonzero or []))

    undecided = False
    uncorroborated = False
    for cond, exc, call_text, target_name, arg_exprs, fixed in sub_conds:
        # note: three exclusion tiers, cheapest first, domain hull,
        # assumed region, then the PSD certificate for sqrt-style
        # `G < 0` guards the hull straddles
        truth = _relational_truth_over_domain(cond, domain, ext_params)
        if truth is False:
            continue
        if assumptions.excludes_guard(cond, domain, ext_params):
            continue
        if isinstance(cond, sympy.Lt):
            try:
                certified = _nonneg_certificate(
                    sympy.expand(cond.lhs - cond.rhs), domain, ext_params)
            except TimeoutError:
                raise
            except Exception:
                certified = None
            if certified is not None:
                continue
        if isinstance(cond, (sympy.Eq, sympy.Le)):
            # an equality (or `G <= 0`) guard is provably empty when G
            # is STRICTLY one-signed; the strict certificate sees a
            # denominator like (k - m*w^2)^2 + (c*w)^2 with c bounded
            # away from zero, which the hull straddles
            from ._proof_support import _positive_certificate
            big_g = sympy.expand(cond.lhs - cond.rhs)
            try:
                certified = (_positive_certificate(big_g, domain, ext_params)
                             or (_positive_certificate(-big_g, domain,
                                                       ext_params)
                                 if isinstance(cond, sympy.Eq) else None))
            except TimeoutError:
                raise
            except Exception:
                certified = None
            if certified is not None:
                continue
        witness = _find_guard_witness(cond, points, base, ext_params,
                                      domain, assumptions)
        if witness is not None:
            # a disproof requires an EXECUTED witness: the real call,
            # run at this point, must actually raise. A symbolic
            # witness the execution refutes is an engine artifact
            # (the false-falsified family), never a counterexample.
            target = (callables or {}).get(target_name)
            if target is None or not _witness_corroborated(
                    target, arg_exprs, witness):
                uncorroborated = True
                undecided = True
                continue
            # a coordinate the claim's evaluation point fixes is named
            # at that value, the one the executed call used
            at_witness = {**witness, **fixed}
            where = ", ".join(f"{name} = {_witness_value_text(at_witness[sym])}"
                              for name, sym in ext_params.items()
                              if sym in at_witness)
            exc_text = exc or "an exception"
            return ProofResult(
                "disproven",
                sketch=f"{call_text} raises {exc_text} inside the declared "
                       f"domain (guard {_cond_text(cond)} holds at {where}), "
                       "so the claim has no value there, narrow the claim's "
                       "domain to where every call returns, or state the "
                       "raising region as its own raises(...) claim",
                counterexample=where,
                meta={"mathema.witness_executed": True})
        undecided = True
    if undecided:
        meta = ({"mathema.engine": "guard-witness-uncorroborated"}
                if uncorroborated else {})
        return ProofResult(
            "undecided",
            sketch="a call's arguments may reach a raise guard inside the "
                   "declared domain and neither a witness nor an exclusion "
                   "could be established, narrow the domain to where every "
                   "call returns, or state the raising region as its own "
                   "raises(...) claim", meta=meta)
    return None


def _witness_value_text(value) -> str:
    """A witness coordinate as a reader would type it: a sympy float in
    Python's own spelling (`2.68e+154`), anything else as sympy prints it."""
    if isinstance(value, sympy.Float):
        return repr(float(value))
    return str(value)


def _clear_of_edge(edge, direction: int):
    """A point a whole magnitude past `edge` in `direction` (+1 above,
    -1 below): an integer while that is short to state, a float beyond
    1e15, where an exact integer would run to hundreds of digits."""
    step = sympy.Max(1, abs(edge))
    point = edge + direction * step
    if abs(point) > 10**15:
        return sympy.Float(float(point), 3)
    return sympy.ceiling(point) if direction > 0 else sympy.floor(point)


def _solved_witness(cond, sym, bound):
    """Intent:
        An exact point satisfying a one-symbol relational guard inside
        the declared bound (the whole line when unbounded), via
        solveset, or None when the region is empty or has no
        pickable point.
    """
    from ..domain import bound_to_sympy_set
    try:
        region = sympy.solveset(cond, sym, sympy.S.Reals)
        dom_set = bound_to_sympy_set(bound) if bound is not None else sympy.S.Reals
        hit = sympy.Intersection(region, dom_set)
    except TimeoutError:
        raise
    except Exception:
        return None
    pieces = hit.args if isinstance(hit, sympy.Union) else (hit,)
    for piece in pieces:
        if isinstance(piece, sympy.Interval):
            lo, hi = piece.start, piece.end
            if lo.is_finite and hi.is_finite:
                return (lo + hi) / 2
            # past a single finite edge, step a whole magnitude beyond it
            # and round to an integer, so the point stays clear of the
            # edge once converted to a float
            if lo.is_finite:
                return _clear_of_edge(lo, 1)
            if hi.is_finite:
                return _clear_of_edge(hi, -1)
            return sympy.Integer(0)
        if isinstance(piece, sympy.FiniteSet) and piece.args:
            return piece.args[0]
    return None


def _cond_text(cond) -> str:
    try:
        return str(cond)
    except TimeoutError:
        raise
    except Exception:
        return "<condition>"


def _guard_relevant_params(facts, params: dict) -> "set | None":
    """Intent:
        The signature parameters whose values the function's branch
        guards actually depend on, directly by name, or through an
        affine local traceable to them. `None` when a guard involves
        something untraceable (then every parameter must be treated as
        relevant).
    """
    if facts.tree is None:
        return None
    relevant: set = set()
    locals_map = _affine_locals(facts.tree,
                                _unmodified_params(facts.tree, set(facts.params)),
                                params)
    symbol_names = {str(sym): name for name, sym in params.items()}
    for node in ast.walk(facts.tree):
        if not isinstance(node, ast.If):
            continue
        for name_node in ast.walk(node.test):
            if not isinstance(name_node, ast.Name):
                continue
            name = name_node.id
            if name in facts.params:
                relevant.add(name)
            elif name in locals_map:
                for sym in locals_map[name].free_symbols:
                    mapped = symbol_names.get(str(sym))
                    if mapped is None:
                        return None
                    relevant.add(mapped)
            else:
                return None   # an untraceable guard input
    return relevant


def _pruned_lift_valid_for_calls(fn, facts, lhs_src: str, rhs_src: str,
                                 domain: dict, conditioned,
                                 max_callee_depth: int,
                                 relevant: "set | None") -> bool:
    """Intent:
        Is the domain-pruned (single-branch) lift valid for every
        `f(...)` call in the claim? A call's argument may range
        elsewhere than the bare parameter (`f(1-p)`, `f(2*x)`), and
        the pruned body is only sound there if the pruning decides the
        SAME way over the argument's own range, so for each
        transformed call this re-runs the pruning over the argument
        hulls and requires the identical resolved body.

    Notes:
        Guard-irrelevant parameters (`f(dh + c, t, ds)` when only `t`
        is guarded) never constrain anything. A hull that can't be
        computed, or a re-pruning that resolves differently (`f(-x)`
        on an x-guarded abs), answers False; the caller must then
        use a lift that is valid everywhere.
    """
    from ._proof_support import _interval_bounds
    from ..domain import Interval

    ext_params = dict(conditioned.params)
    for name in domain:
        if name not in ext_params:
            ext_params[name] = sympy.Symbol(name, real=True)
    temp_lifted = Lifted(expr=conditioned.expr, params=dict(conditioned.params),
                         sig_params=list(conditioned.sig_params),
                         aggregate=dict(conditioned.aggregate),
                         opaque=conditioned.opaque)
    aux: dict = {name: sym for name, sym in ext_params.items()
                 if name not in conditioned.params}
    seen: set = set()
    for src in (lhs_src, rhs_src):
        if not src:
            continue
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError:
            return False
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "f"):
                continue
            per_call = dict(domain)
            transformed = False
            for p, arg in zip(conditioned.sig_params, node.args):
                if relevant is not None and p not in relevant:
                    continue
                if isinstance(arg, ast.Name) and arg.id == p:
                    continue
                ok, lit = _literal_value(arg)
                if (ok and isinstance(lit, (int, float))
                        and not isinstance(lit, bool)):
                    per_call[p] = (float(lit), float(lit))
                    transformed = True
                    continue
                try:
                    # the claim walker, not the body lifter: an argument
                    # may itself contain f(...) (nested application) or a
                    # claim-level free variable, both of which resolve
                    # here exactly as they would in the law itself. Every
                    # nested call is separately validated by this same
                    # loop, since ast.walk visits it as its own node.
                    arg_expr = _law_to_sympy(arg, temp_lifted,
                                             set(conditioned.params), aux)
                except (NotSymbolic, Exception):
                    return False
                if isinstance(arg_expr, tuple) or isinstance(arg_expr, _SymbolicArray):
                    return False
                hull = _interval_bounds(arg_expr, domain, ext_params)
                if hull is None:
                    return False
                lo = hull.min if isinstance(hull, sympy.AccumBounds) else hull
                hi = hull.max if isinstance(hull, sympy.AccumBounds) else hull
                per_call[p] = Interval(lo, hi)
                transformed = True
            if not transformed:
                continue
            key = tuple(sorted((p, repr(b)) for p, b in per_call.items()))
            if key in seen:
                continue
            try:
                repruned = lift_conditioned(fn, facts, per_call,
                                            max_callee_depth=max_callee_depth)
            except TimeoutError:
                raise
            except Exception:
                return False
            if (repruned is None or repruned.kind != conditioned.kind
                    or repruned.expr != conditioned.expr):
                return False
            seen.add(key)
    return True


def _guard_cut_points(facts) -> dict:
    """Intent:
        The literal values a function's own branch guards compare an
        unmodified parameter against, per parameter, the natural
        places to split a declared domain so every guard decides on
        each piece.

    Notes:
        Only bare-name-vs-literal comparisons contribute (either side
        of any op in a chained comparison); a guard over a derived
        expression or between two parameters has no single cut value on
        one parameter's axis. Returns `{param_name: {cut, ...}}`,
        empty when the body has no such guard.
    """
    if facts.tree is None:
        return {}
    unmodified = _unmodified_params(facts.tree, set(facts.params))
    cuts: dict = {}
    for node in ast.walk(facts.tree):
        if not isinstance(node, ast.If):
            continue
        for cmp_node in ast.walk(node.test):
            if not isinstance(cmp_node, ast.Compare):
                continue
            operands = [cmp_node.left, *cmp_node.comparators]
            for left, right in zip(operands, operands[1:]):
                for name_node, lit_node in ((left, right), (right, left)):
                    if not isinstance(name_node, ast.Name):
                        continue
                    if name_node.id not in unmodified:
                        continue
                    ok, lit = _literal_value(lit_node)
                    if ok and isinstance(lit, (int, float)) and not isinstance(lit, bool):
                        cuts.setdefault(name_node.id, set()).add(float(lit))
    return cuts



def _guard_condition_params(facts) -> set:
    """Intent:
        The unmodified signature parameters a branch guard mentions at
        all, comparison or not; a bare `if flag:`, an `is True`, a
        `not flag and x > 0` all count. _guard_cut_points only sees
        name-vs-literal comparisons, so it can never nominate the
        parameter of a truthiness or identity guard for a domain
        split; this is the wider net for the finite-set split, where
        no cut value is needed.
    """
    if facts.tree is None:
        return set()
    unmodified = _unmodified_params(facts.tree, set(facts.params))
    named: set = set()
    for node in ast.walk(facts.tree):
        if not isinstance(node, ast.If):
            continue
        for sub in ast.walk(node.test):
            if isinstance(sub, ast.Name) and sub.id in unmodified:
                named.add(sub.id)
    return named

def _piece_point(piece):
    """One point of a split piece: its single value when it has one,
    else the midpoint of a finite interval, else a point one unit in
    from its finite end. None for a piece with no such point."""
    if isinstance(piece, frozenset):
        return next(iter(piece)) if len(piece) == 1 else None
    if isinstance(piece, tuple) and len(piece) == 2:
        lo, hi = float(piece[0]), float(piece[1])
        inf = float("inf")
        if lo == hi:
            return lo
        if abs(lo) != inf and abs(hi) != inf:
            return (lo + hi) / 2
        if abs(lo) != inf:
            return lo + 1.0
        if abs(hi) != inf:
            return hi - 1.0
        return 0.0
    return None


def _has_calculus_call(src: str) -> bool:
    """Whether claim text calls `d`, `lim` or `integrate`."""
    try:
        tree = ast.parse(src or "", mode="eval")
    except SyntaxError:
        return False
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id in ("d", "lim", "integrate")
               for n in ast.walk(tree))


def _try_domain_split(fn, facts, lhs_src: str, rhs_src: str, relation: str,
                      domain: dict, tolerance, max_callee_depth: int,
                      extensive: bool, depth: int) -> ProofResult | None:
    """Intent:
        Marginalize a relation claim over a branch guard the declared
        domain doesn't settle: split one guarded parameter's domain at
        the guard's own comparison literals, prove the claim separately
        on every piece, and combine; proven on every piece is proven
        over the whole domain (the pieces cover it exactly), and a
        disproven piece is a counterexample to the whole claim.

    Notes:
        The multi-line-definition reading of a branched function: each
        piece of the split domain sees a single live definition. One
        parameter is split at a time; a second straddling guard is
        handled by the piece's own recursive attempt, capped at two
        split levels so the number of sub-proofs stays small (each
        level is at most seven pieces). `None` when no guard yields a
        usable split or some piece stays undecided, the caller falls
        back to its ordinary unliftable report.
    """
    if depth >= 2 or not domain:
        return None
    if _has_calculus_call(lhs_src) or _has_calculus_call(rhs_src):
        # a derivative, limit or integral reads the function around a
        # point or across an interval, which a piece's pruned lift
        # (one branch, fixed by the piece) no longer describes
        return None
    cuts = _guard_cut_points(facts)
    guard_named = _guard_condition_params(facts)
    for p in facts.params:
        b = domain.get(p)
        if (isinstance(b, frozenset) and 1 < len(b) <= 8
                and p in guard_named):
            # a finite domain splits exactly into its own values, the
            # natural pieces for a guard the whole set doesn't settle
            # (a bool parameter's {False, True}, a Literal's cases);
            # capped so the sub-proof count stays small
            pieces = [frozenset({v}) for v in sorted(b, key=repr)]
        elif p not in cuts or p not in domain:
            continue
        else:
            pieces = split_bound_at(domain[p], cuts[p])
            if pieces is None:
                continue
        results = []
        for piece in pieces:
            sub_domain = dict(domain)
            sub_domain[p] = piece
            result = try_prove(fn, facts, lhs_src, rhs_src, relation,
                               domain=sub_domain, tolerance=tolerance,
                               max_callee_depth=max_callee_depth,
                               extensive=extensive, _split_depth=depth + 1)
            if result.status == "disproven":
                piece_text = render_domain_bound(piece)
                witness = dict(result.witness or {})
                if p not in witness:
                    # the piece fixed or narrowed p, so the sub-proof's
                    # witness may not name it; a point of the piece does
                    point = _piece_point(piece)
                    if point is not None:
                        witness[p] = point
                return replace(result, sketch=f"on the sub-domain {p} in "
                               f"{piece_text}: {result.sketch}",
                               witness=witness or result.witness)
            if result.status != "proven":
                return None
            results.append((piece, result))
        piece_list = ", ".join(render_domain_bound(piece) for piece, _ in results)
        how = ("into its stated values" if isinstance(domain.get(p), frozenset)
               else "at its guard boundaries into")
        return ProofResult(
            "proven",
            sketch=f"proven piecewise: {p}'s domain split {how} "
                   f"{piece_list}, each piece proven "
                   f"separately",
            quantifier=_quantifier_clause(set(facts.params),
                                          list(facts.params), domain),
            meta={"mathema.derive_route": "domain_split"})
    return None



def _adopt_piecewise(pw) -> "Lifted":
    """Intent:
        One ConditionedLift piecewise result as a full Lifted: every
        branch rides with its own symbolic guard (branch_complete, so
        domain assumptions never bake into its symbols), and the raise
        regions come along as canonical guards. The single constructor
        behind every adoption site in try_prove.
    """
    from ..grammar import render_canonical
    _display = _display_value(pw.expr)
    return Lifted(expr=pw.expr, params=pw.params,
                  sig_params=pw.sig_params, aggregate=pw.aggregate,
                  unicode=render_canonical(_display)[0],
                  latex=sympy.latex(_display), opaque=pw.opaque,
                  branch_complete=True)

def _tighten_domain_by_assumption(domain: dict, params: dict, assumption) -> dict:
    """Intent:
        `domain`, narrowed by any assumed constraint that bounds a
        single parameter against a constant (`assuming x > 0`).

    Notes:
        A claim is quantified only where its premise holds, so the
        premise is part of the region, and the region has to be as
        tight as everything known about it, or a proof is refused for
        points the claim never covered. `for x in (0,10], f(x) > 0`
        proves on a reciprocal; `assuming x > 0, for x in [-10,10],
        f(x) > 0` states the same region and, without this, only
        reached `holds`, because the interval rung still saw
        [-10, 10].

        Only the shape it can be exact about: one bare parameter
        against a numeric literal. Anything relating two parameters
        (`a <= b`) already reaches the prover as an assumed gap, and
        narrowing a box by it would be wrong; the region is not a
        box. A strict bound tightens to an open endpoint, so `x > 0`
        and `(0, ...]` are the same region rather than nearly the same.
    """
    if not assumption:
        return domain
    from ..domain import Interval
    tightened = dict(domain)
    for lhs_src, rel, rhs_src in assumption:
        name, bound_text, flip = str(lhs_src).strip(), str(rhs_src).strip(), False
        if name not in params:
            name, bound_text, flip = bound_text, name, True
        if name not in params:
            continue
        try:
            value = float(bound_text)
        except (TypeError, ValueError):
            continue
        if rel in ("==", "!="):
            continue
        lower = rel in (">=", ">") if not flip else rel in ("<=", "<")
        strict = rel in (">", "<")
        current = tightened.get(name)
        if isinstance(current, Interval) or (isinstance(current, tuple)
                                             and len(current) == 2
                                             and not isinstance(current, frozenset)):
            lo, hi = current[0], current[1]
            closed_lo = getattr(current, "closed_lo", True)
            closed_hi = getattr(current, "closed_hi", True)
        elif current is None:
            lo, hi, closed_lo, closed_hi = float("-inf"), float("inf"), True, True
        else:
            continue          # a named set, discrete set or Domain: leave it alone
        if lower:
            if value > lo or (value == lo and strict):
                lo, closed_lo = value, not strict
        else:
            if value < hi or (value == hi and strict):
                hi, closed_hi = value, not strict
        if lo > hi:
            return domain     # the premise empties the region, say nothing here
        tightened[name] = Interval(lo, hi, closed_lo, closed_hi)
    return tightened

def _kink_in_domain(loci: list, domain: dict) -> "str | None":
    """The first non-differentiability condition the declared domain
    does not provably exclude, as text, or None when every one is
    excluded."""
    from ._fold import _cond_truth_over
    for locus in loci:
        if locus is sympy.false:
            continue
        if _cond_truth_over(locus, domain or {}) is True:
            continue
        if _roots_outside_domain(locus, domain or {}):
            continue
        return _cond_text(locus)
    return None


def _roots_outside_domain(locus, domain: dict) -> bool:
    """Whether an equality over a single declared parameter has finitely
    many real roots, none of them inside that parameter's declared
    bound."""
    from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from ..domain import domain_contains
    if not isinstance(locus, sympy.Eq) or len(locus.free_symbols) != 1:
        return False
    (sym,) = locus.free_symbols
    bound = domain.get(str(sym))
    if bound is None:
        return False
    try:
        roots = _with_timeout(
            lambda: sympy.solveset(locus.lhs - locus.rhs, sym,
                                   domain=sympy.S.Reals),
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return False
    except Exception:
        return False
    if not isinstance(roots, sympy.FiniteSet):
        return False
    try:
        return not any(domain_contains(float(r), bound) for r in roots)
    except Exception:
        return False


def _loop_proof_raise_gate(fn, facts, domain, proof: ProofResult) -> ProofResult:
    """Intent:
        A loop-shape proof, kept only when every implicit raise region
        the raise-region walk found (a non-integer `range()` argument,
        a division) provably misses the declared domain; otherwise the
        proof becomes undecided, since the closed form is silent about
        the points where the code raises.
    """
    from ._fold import _cond_truth_over
    from ._partiality import partiality_walk
    try:
        guards, _unread = partiality_walk(fn, facts, domain or {})
    except TimeoutError:
        raise
    except Exception:
        return proof
    for cond, exc in guards:
        if _cond_truth_over(cond, domain or {}) is True:
            continue
        return ProofResult(
            "undecided",
            sketch=f"{proof.sketch}; not kept as a proof: the code may "
                   f"raise {exc} inside the declared domain (where "
                   f"{_cond_text(cond)}), narrow the domain to where every "
                   f"call returns, or state the raising region as its own "
                   f"raises(...) claim",
            meta=dict(proof.meta))
    return proof


def try_prove(fn, facts, lhs_src: str, rhs_src: str, relation: str,
             domain: dict | None = None, tolerance: float | None = None,
             max_callee_depth: int = 3, extensive: bool = False,
             _split_depth: int = 0, funcs: dict | None = None,
             assumption: "list | None" = None,
             assume_defined: bool = False) -> ProofResult:
    """See `_try_prove`. A proof is kept only when every raise region
    of the functions it reads was read too: a statement the raise-region
    pass stops at could hide a raise in the domain, and a value claim is
    false wherever the code raises."""
    notes: dict = {}
    result = _try_prove(fn, facts, lhs_src, rhs_src, relation, domain,
                        tolerance, max_callee_depth, extensive, _split_depth,
                        funcs, assumption, assume_defined, _walk_notes=notes)
    if result.status == "proven" and notes.get("unread") and not assume_defined:
        return ProofResult(
            "undecided",
            sketch=(f"{result.sketch}; not kept as a proof: the raise-region "
                    f"pass stops at {notes['unread']}, so a raise inside the "
                    "domain is not ruled out"),
            meta=dict(result.meta))
    empty = _empty_sequence_raise(fn, facts, lhs_src, rhs_src, domain,
                                  assumption)
    if empty is not None:
        return empty
    if result.status == "proven":
        region = _complex_value_region(fn, facts, lhs_src, rhs_src, domain)
        if region is not None:
            return ProofResult(
                "undecided",
                sketch=(f"{result.sketch}; not kept as a proof: f returns a "
                        f"complex number where {region} (a fractional power "
                        f"of a negative base), which the declared domain "
                        f"does not exclude, and the proof reads f as real"),
                meta=dict(result.meta))
        kink = _derivative_kink(fn, facts, lhs_src, rhs_src, domain)
        if kink is not None:
            return ProofResult(
                "undecided",
                sketch=(f"{result.sketch}; not kept as a proof: f is not "
                        f"differentiable where {kink}, which the declared "
                        f"domain does not exclude"),
                meta=dict(result.meta))
    return result


def _calls_f_at_its_parameters(facts, lhs_src: str, rhs_src: str) -> bool:
    """Whether every call to f in the claim passes f's own parameters,
    in order."""
    for src in (lhs_src, rhs_src):
        try:
            tree = ast.parse(src or "0", mode="eval")
        except SyntaxError:
            return False
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == "f" and [getattr(a, "id", None)
                                              for a in n.args] != list(facts.params):
                return False
    return True


def _complex_value_region(fn, facts, lhs_src: str, rhs_src: str,
                          domain) -> "str | None":
    """The first region where f returns a complex number (a fractional
    power of a negative base) that the declared domain does not
    exclude, as text; None when there is none."""
    from ._partiality import partiality_walk
    regions: list = []
    try:
        partiality_walk(fn, facts, domain or {}, complex_out=regions)
    except TimeoutError:
        raise
    except Exception:
        return None
    regions = [r for r in regions if r is not sympy.false]
    if not regions:
        return None
    if not _calls_f_at_its_parameters(facts, lhs_src, rhs_src):
        return _cond_text(regions[0])
    from ._fold import _cond_truth_over
    for region in regions:
        if _cond_truth_over(region, domain or {}) is not True:
            return _cond_text(region)
    return None


def _first_axis_length(seq, axis):
    """`dim(seq, 0)` of a plain list, its length."""
    if axis != 0:
        raise ValueError("only the first axis of a list has a length")
    return len(seq)


def _premises_admit_empty(name: str, assumption) -> bool:
    """Whether the `assuming` conjuncts put the empty list in `name`'s
    domain: at least one of them reads `len(name)` (canonically
    `dim(name, 0)`), and every one that reads it holds at length
    zero."""
    import re
    pattern = re.compile(rf"\b(?:len\(\s*{re.escape(name)}\s*\)"
                         rf"|dim\(\s*{re.escape(name)}\s*,\s*0\s*\))")
    ops = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b,
           "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
           "<": lambda a, b: a < b, ">": lambda a, b: a > b}
    mentioned = False
    for lhs, rel, rhs in assumption or ():
        text = f"{lhs} {rhs}"
        if not pattern.search(text):
            continue
        mentioned = True
        try:
            env = {"len": len, "dim": _first_axis_length, name: []}
            lv = eval(compile(str(lhs), "<premise>", "eval"),
                      {"__builtins__": {}}, env)
            rv = eval(compile(str(rhs), "<premise>", "eval"),
                      {"__builtins__": {}}, env)
            holds = ops[rel](lv, rv)
        except Exception:
            continue
        if not holds:
            return False
    return mentioned


def _empty_sequence_raise(fn, facts, lhs_src: str, rhs_src: str, domain,
                          assumption) -> "ProofResult | None":
    """Intent:
        A disproof with an executed witness when the claim's premises
        admit the empty list for a sequence parameter, the claim calls
        f at its own parameters, and f raises when called with the
        empty list there; an undecided result when f raises but the
        claim calls it at other arguments; None otherwise.

    Notes:
        A fold's closed form has a value at length zero (the initial
        value, or a sum over nothing), while the code may read
        `xs[0]` or divide by `len(xs)` and raise. The other arguments
        are drawn from the declared domain.
    """
    import random

    from ..probing import _synth
    seqs = [p for p in facts.params
            if facts.param_kinds.get(p) == "sequence"]
    targets = [p for p in seqs if _premises_admit_empty(p, assumption)]
    if not targets:
        return None
    identity = True
    for src in (lhs_src, rhs_src):
        try:
            tree = ast.parse(src or "0", mode="eval")
        except SyntaxError:
            return None
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == "f" and [getattr(a, "id", None)
                                              for a in n.args] != list(facts.params):
                identity = False
    rng = random.Random(0)
    for target in targets:
        args = []
        for p in facts.params:
            if p == target:
                args.append([])
                continue
            kind = facts.param_kinds.get(p, "float")
            try:
                args.append(_synth(kind, rng, (domain or {}).get(p)))
            except Exception:
                return None
        try:
            fn(*args)
        except Exception as e:
            exc = type(e).__name__
        else:
            continue
        where = ", ".join(f"{p} = {a!r}" for p, a in zip(facts.params, args))
        if not identity:
            return ProofResult(
                "undecided",
                sketch=f"f raises {exc} on the empty list the premises admit "
                       f"for {target} ({where}), and the claim calls f at "
                       f"other arguments")
        return ProofResult(
            "disproven",
            sketch=f"f raises {exc} at {where}, an empty list the premises "
                   f"admit, so the claim has no value there; narrow the "
                   f"premise to len({target}) >= 1, or state the raising "
                   f"case as its own raises(...) claim",
            counterexample=where,
            meta={"mathema.witness_executed": True})
    return None


def _derivative_kink(fn, facts, lhs_src: str, rhs_src: str,
                     domain) -> "str | None":
    """Intent:
        For a claim that differentiates f over its domain (a `d(...)`
        with no evaluation point), the first point where f itself may
        not be differentiable that the declared domain does not
        exclude, as text; None when there is none or the claim has no
        such derivative.

    Notes:
        Read off f's unpruned lift over plain real symbols: the lift a
        proof uses can be pruned to one branch by the domain, or have
        the domain's sign facts baked into its symbols (`Abs(x)` read
        as `-x` on `[-1, 0]`), and either hides a kink on the domain's
        boundary. When f is called at anything but its own parameters,
        a kink anywhere is enough to decline.
    """
    free_d, identity_calls = False, True
    for src in (lhs_src, rhs_src):
        try:
            tree = ast.parse(src or "0", mode="eval")
        except SyntaxError:
            return None
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
                continue
            if n.func.id == "d" and not any(
                    isinstance(a, ast.Name) and a.id == _D_AT_SENTINEL
                    for a in n.args):
                free_d = True
            if n.func.id == "f" and [getattr(a, "id", None)
                                     for a in n.args] != list(facts.params):
                identity_calls = False
    if not free_d:
        return None
    try:
        raw = lift(fn, facts)
        if raw is None and facts.branch_count:
            raw = lift_piecewise(fn, facts)
            if raw is not None and raw.kind != "value":
                raw = None
    except TimeoutError:
        raise
    except Exception:
        raw = None
    if raw is None or isinstance(raw.expr, tuple) \
            or not hasattr(raw.expr, "free_symbols"):
        return None
    loci = _kink_loci(raw.expr, list(raw.params.values()))
    if not loci:
        return None
    if not identity_calls:
        return _cond_text(loci[0])
    return _kink_in_domain(loci, domain or {})


def _try_prove(fn, facts, lhs_src: str, rhs_src: str, relation: str,
               domain: dict | None = None, tolerance: float | None = None,
               max_callee_depth: int = 3, extensive: bool = False,
               _split_depth: int = 0, funcs: dict | None = None,
               assumption: "list | None" = None,
               assume_defined: bool = False,
               _walk_notes: dict | None = None) -> ProofResult:
    """Attempt a symbolic proof of `lhs <relation> rhs` over the function's
    lifted body, honoring a declared domain as sympy assumptions.

    `==` (or its `~=` alias, see grammar.py: `≈`/`\approx` normalize to
    `~=` rather than `==` only so to_latex() can still render `\approx`;
    proof-wise they are the same claim) is decided by simplifying the
    difference to 0 (falling back to sympy's `.equals()`, which also
    tries numeric sampling internally for cases plain simplification
    can't close). `<=`/`>=` are decided by the sign of the difference
    under the domain's assumptions. Anything sympy can't settle comes
    back `undecided`, never a false `proven`. `!=` is not attempted here
    at all, conjecture.py's derive dispatch reports it `skipped`
    before try_prove is ever called.

    `ε`/`eps`/`epsilon`, if they appear anywhere in the law text, resolve
    to the claim's own declared `tolerance` rather than becoming a free
    variable; `abs(f(x) - g(x)) <= ε` then reads exactly like the
    mathematical convention it's borrowed from.

    `max_callee_depth` is forwarded to lift()/lift_conditioned(); see
    lift()'s own docstring for what it controls (inlining a call to a
    plain function this one calls, e.g. a small local helper). `domain`
    is also forwarded to lift() itself now, not just lift_conditioned()
   ; lift()'s own gate for *this* function is unaffected by it; it
    only lets a callee's own branch resolve via a domain derived from
    this claim's domain (see lift()'s docstring).

    `extensive` widens the case-split fallback's own wall-clock cap
    (see `_try_case_split`) when an ordinary proof attempt comes back
    undecided. Default `False`.

    `funcs` binds a multi-function claim's auxiliary callables
    ({"g": <function>, ...}): each is lifted to its own closed form up
    front, and the law's calls to it substitute positionally exactly
    like `f(...)` does. A bound function that doesn't lift makes the
    whole claim unliftable, with the blocking function named.

    `assumption` is an interpreted `assuming` clause as a list of
    (lhs_src, relation, rhs_src) conjuncts: each strengthens ask()'s
    context and lets a raise guard be excluded when the assumed region
    provably avoids it, the claim then quantifies only where every
    conjunct holds."""
    lifted = lift(fn, facts, max_callee_depth=max_callee_depth, domain=domain)
    piecewise_hint = None
    piecewise_guards: list = []
    route_mechanism: str | None = None
    aux_funcs_lifted: dict = {}
    aux_funcs_guards: dict = {}
    seq_transforms: dict = {}
    if funcs:
        # a multi-function claim: every bound function (g, budget_line,
        # ...) lifts to its own closed form up front, so the law's
        # calls to it substitute exactly like f's own do. Any one of
        # them refusing names itself specifically, the claim's
        # verdict must say which function blocked it and why.
        from ..analysis import analyze_source
        from ._seq_common import transform_bindings
        seq_transforms = transform_bindings(funcs)
        for gname in sorted(funcs):
            if gname in seq_transforms:
                # a registered elementwise transform composes through
                # a fold's closed form structurally; it never needs a
                # lift of its own
                continue
            gfn = funcs[gname]
            gqual = getattr(gfn, "__qualname__", None) or repr(gfn)
            try:
                gfacts = analyze_source(gfn)
            except TimeoutError:
                raise
            except Exception as e:
                return ProofResult("unliftable", sketch=f"bound function "
                                   f"{gname} ({gqual}): {e}")
            glift = lift(gfn, gfacts, max_callee_depth=max_callee_depth)
            conditioned_guards: list = []
            if glift is None:
                # a guarded (or branchy, or loopy-and-branchy) bound
                # function: the full piecewise lift is valid at ANY
                # argument, exactly what a call site with a computed
                # argument needs, and its raise regions gate the
                # claim through the same reachability machinery f's
                # own do. The domain-pruned conditioned lift remains
                # the fallback for shapes the piecewise walk declines.
                try:
                    g_pw = lift_piecewise(gfn, gfacts)
                except TimeoutError:
                    raise
                except Exception:
                    g_pw = None
                if g_pw is not None and g_pw.kind == "value":
                    glift = _adopt_piecewise(g_pw)
                    conditioned_guards = list(g_pw.raise_guards or [])
            if glift is None and gfacts.loops and not gfacts.recursion \
                    and not any(k == "sequence"
                                for k in gfacts.param_kinds.values()):
                # a branch-free scalar loop body closes through the sum
                # machinery to a plain expression; what lets a
                # Sum(...) in the claim wrap a loop-lifted bound call
                from ._normalize import normalized_body
                from ._sum import closed_loop_region
                try:
                    g_params, g_aggregate = _bind_params(gfn, gfacts)
                    g_expr = closed_loop_region(
                        gfn, gfacts, normalized_body(gfn, gfacts),
                        dict(g_params))
                except TimeoutError:
                    raise
                except Exception:
                    g_expr = None
                if g_expr is not None and not isinstance(g_expr, tuple):
                    glift = Lifted(expr=g_expr, params=g_params,
                                   sig_params=list(gfacts.params),
                                   aggregate=g_aggregate)
            if glift is None:
                g_domain = {gp: (domain or {})[gp] for gp in gfacts.params
                            if gp in (domain or {})}
                try:
                    g_cond = lift_conditioned(gfn, gfacts, g_domain,
                                              max_callee_depth=max_callee_depth)
                except TimeoutError:
                    raise
                except Exception:
                    g_cond = None
                if g_cond is not None and g_cond.kind == "value" \
                        and g_cond.expr is not None:
                    glift = Lifted(expr=g_cond.expr, params=g_cond.params,
                                   sig_params=g_cond.sig_params,
                                   aggregate=g_cond.aggregate,
                                   opaque=g_cond.opaque)
                    conditioned_guards = list(g_cond.raise_guards or [])
            if glift is None:
                from ..inventory import unliftable_summary
                try:
                    summary = unliftable_summary(gfn)
                except TimeoutError:
                    raise
                except Exception:
                    summary = None
                return ProofResult("unliftable", sketch=f"bound function "
                                   f"{gname} ({gqual}) is not derivable"
                                   + (f", {summary}" if summary else
                                      " in v1: contains a loop, branch, "
                                      "recursion, or a non-scalar parameter"))
            aux_funcs_lifted[gname] = glift
            # a bound function's own raise regions gate the claim
            # exactly like f's do; without this, derive could prove
            # an identity probe falsifies at g's first raising sample
            from ._partiality import partiality_walk as _pwalk
            try:
                g_guards, g_unread = _pwalk(gfn, gfacts)
                g_guards = list(g_guards)
            except TimeoutError:
                raise
            except Exception:
                g_guards, g_unread = [], "raise-region pass failed"
            if g_unread and _walk_notes is not None:
                _walk_notes.setdefault("unread", f"{gname} {g_unread}")
            g_guards.extend(conditioned_guards)
            if g_guards:
                aux_funcs_guards[gname] = g_guards
    if lifted is None and facts.branch_count:
        # branch-free lifting failed specifically because of a branch,
        # see if the declared domain settles which side is taken. Only a
        # "value" result is usable for a relation claim; "raises" (the
        # domain-determined path doesn't return at all) leaves `lifted`
        # None, same unliftable report as today.
        conditioned = lift_conditioned(fn, facts, domain or {}, max_callee_depth=max_callee_depth)
        if conditioned is None:
            # an UNDECLARED parameter can still be pinned down by the
            # claim's own calls: f(a, a) bounds the second slot by the
            # first parameter's declared range. Augment and retry; the
            # per-call gate below still validates every call against
            # the augmented pruning.
            augmented = _augment_domain_from_calls(fn, facts, lhs_src, rhs_src,
                                                   domain or {})
            if augmented is not None:
                conditioned = lift_conditioned(fn, facts, augmented,
                                               max_callee_depth=max_callee_depth)
                if conditioned is not None:
                    domain = dict(domain or {})
                    for name, bound in augmented.items():
                        domain.setdefault(name, bound)
        if conditioned is not None and conditioned.kind == "value" \
                and not _pruned_lift_valid_for_calls(
                    fn, facts, lhs_src, rhs_src, domain or {}, conditioned,
                    max_callee_depth,
                    _guard_relevant_params(facts, conditioned.params)):
            # the pruned body baked in ONE branch, chosen for the
            # declared domain, substituting it into a call whose
            # argument may leave that domain (f(-x), f(x + c)) would
            # evaluate the wrong branch, a confidently wrong verdict.
            # The full piecewise lift, valid at any argument, takes
            # over when the body's shape allows it.
            conditioned = lift_piecewise(fn, facts)
            piecewise_lift = conditioned is not None
            if conditioned is not None:
                piecewise_guards = conditioned.raise_guards
        else:
            piecewise_lift = False
        if conditioned is not None and conditioned.kind == "value":
            _display = _display_value(conditioned.expr)
            from ..grammar import render_canonical
            lifted = Lifted(expr=conditioned.expr, params=conditioned.params,
                            sig_params=conditioned.sig_params,
                            aggregate=conditioned.aggregate,
                            unicode=render_canonical(_display)[0],
                            latex=sympy.latex(_display), opaque=conditioned.opaque,
                            branch_complete=piecewise_lift)
    if lifted is None and facts.recursion and not facts.loops:
        # a self-recursive body: see if it's a linear recurrence rsolve
        # can close exactly (fibonacci, doubling, an additive
        # accumulator). The lift is the full piecewise closed form,
        # exact at every integer where the function terminates, so
        # the same raise-region and branch-complete machinery as the
        # piecewise lift applies unchanged.
        from ._recurrence import lift_recurrence
        rec = lift_recurrence(fn, facts)
        if rec is not None:
            gate, closed_only = _recurrence_domain_gate(lhs_src, rhs_src, rec,
                                                        domain or {})
            if gate is not None:
                return gate
            if closed_only:
                # every call argument provably stays at or above the
                # closed form's first valid index, so the bare closed
                # form substitutes; the boundary branches would only
                # leave conditions the deciders can't settle
                rec = replace(rec, expr=rec.recurrence["closed"])
            piecewise_guards = rec.raise_guards
            route_mechanism = "recurrence:rsolve"
            _display = _display_value(rec.expr)
            from ..grammar import render_canonical
            lifted = Lifted(expr=rec.expr, params=rec.params,
                            sig_params=rec.sig_params, aggregate=rec.aggregate,
                            unicode=render_canonical(_display)[0],
                            latex=sympy.latex(_display), opaque=rec.opaque,
                            branch_complete=True)
    if lifted is None and facts.loops:
        # branch-free/loop-free lifting failed specifically because of a
        # loop, see if it's the one recognized linear-fold shape
        # instead. Only tried once lift()/lift_conditioned() have both
        # already failed, same "widen, never replace" pattern as the
        # branch-pruning fallback above. If the fold shape declines
        # (not just its own claim-parsing), fall further to the more
        # general "pure sum" recognizer, nested loops, multiple
        # sequential accumulator loops, non-affine-but-purely-additive
        # updates, and a dot product recognized directly from loop
        # structure, not only via a literal np.dot(...) call. Both are
        # routed through the claim-family registry (mathema.families),
        # exactly like the dot-product shape below, so a registered
        # replacement family takes over automatically; the direct
        # try_prove_* calls are the safety-net default if nothing is
        # registered.
        def _loop_shape_result():
            from ._seq_common import _ACTIVE_TRANSFORMS
            token = _ACTIVE_TRANSFORMS.set(seq_transforms or None)
            try:
                return _loop_shape_dispatch()
            finally:
                _ACTIVE_TRANSFORMS.reset(token)

        def _loop_shape_dispatch():
            fold_family = families.families().get("linear_fold")
            if fold_family is not None and fold_family.can_handle(fn, facts, ""):
                derive_route = fold_family.routes().get("derive")
                if derive_route is not None:
                    return families.call_route(
                        derive_route, fn, facts, lhs_src, rhs_src, relation,
                        domain=domain, tolerance=tolerance,
                        assumption=assumption)
            elif fold_family is None and lift_fold(fn, facts) is not None:
                return try_prove_fold(fn, facts, lhs_src, rhs_src, relation,
                                      domain=domain, tolerance=tolerance,
                                      assumption=assumption)
            sum_family = families.families().get("general_sum")
            if sum_family is not None and sum_family.can_handle(fn, facts, ""):
                derive_route = sum_family.routes().get("derive")
                if derive_route is not None:
                    return families.call_route(
                        derive_route, fn, facts, lhs_src, rhs_src, relation,
                        domain=domain, tolerance=tolerance,
                        assumption=assumption)
            return try_prove_sum(fn, facts, lhs_src, rhs_src, relation,
                                 domain=domain, tolerance=tolerance,
                                 assumption=assumption)

        from ._coupled import lift_coupled
        coupled = lift_coupled(fn, facts)
        if coupled is not None:
            # two linearly coupled accumulators closed to exact
            # algebra: from here the ordinary proof path treats it
            # like any lift
            lifted = coupled
        else:
            seq_result = _loop_shape_result()
            if seq_result.status == "proven":
                seq_result = _loop_proof_raise_gate(fn, facts, domain,
                                                    seq_result)
            if seq_result.status not in ("unliftable", "undecided") \
                    or not facts.branch_count:
                return seq_result
            # every loop shape declined AND the body has real branches:
            # the branches-around-loops read, each branch region
            # closed by the loop machinery, the whole function one
            # ordered Piecewise, plain symbols (branch_complete), raise
            # regions gated like any other guard. Falls back to the
            # loop shapes' own diagnosis when the piecewise read
            # declines too.
            pw = lift_piecewise(fn, facts)
            if pw is None or pw.kind != "value":
                return seq_result
            piecewise_guards = pw.raise_guards
            lifted = _adopt_piecewise(pw)
    if lifted is None and not facts.loops and sum(
            1 for k in facts.param_kinds.values() if k == "sequence") == 2:
        # no loop at all, but exactly two sequence-typed parameters,
        # see if the whole body is the one recognized dot-product shape.
        # Independent of the loop-fold fallback above (this function has
        # no loop in the first place), not a further extension of it.
        # Routed through the claim-family registry (mathema.families)
        # rather than calling try_prove_dot directly, so a registered
        # replacement family takes over automatically; try_prove_dot
        # itself is the safety-net default if nothing is registered.
        dot_family = families.families().get("dot_product")
        if dot_family is not None and dot_family.can_handle(fn, facts, ""):
            derive_route = dot_family.routes().get("derive")
            if derive_route is not None:
                return families.call_route(
                    derive_route, fn, facts, lhs_src, rhs_src, relation,
                    domain=domain, tolerance=tolerance,
                    assumption=assumption)
        return try_prove_dot(fn, facts, lhs_src, rhs_src, relation,
                             domain=domain, tolerance=tolerance,
                             assumption=assumption)
    if lifted is None:
        branch_sketch = _branch_pruning_sketch(fn, facts)
        if branch_sketch is not None:
            # before reporting the undecided guard, try the multi-line-
            # definition reading: split the domain at the guard's own
            # boundaries and prove each piece separately.
            split = _try_domain_split(fn, facts, lhs_src, rhs_src, relation,
                                      domain or {}, tolerance,
                                      max_callee_depth, extensive, _split_depth)
            if split is not None:
                return split
            # the last lifting resort: the full piecewise form, every
            # branch with its own symbolic guard, decidable when the
            # claim's own structure (a pin, a call argument) resolves
            # the conditions the domain alone couldn't.
            pw = lift_piecewise(fn, facts)
            if pw is not None and pw.kind == "value":
                piecewise_hint = branch_sketch
                piecewise_guards = pw.raise_guards
                lifted = _adopt_piecewise(pw)
            else:
                return ProofResult("unliftable", sketch=f"branch pruning couldn't "
                                   f"settle this under the declared domain: {branch_sketch}")
        # the generic catch-all used to name four possible causes in one
        # breath; derivability_report() knows which one actually fired,
        # so the sketch says so, as the LIKELY reason (the first
        # blocking construct found; the root cause can sit deeper), with
        # one plain help sentence. Full depth stays in --deriv-report.
        pw = lift_piecewise(fn, facts) if facts.branch_count else None
        if pw is not None and pw.kind == "value":
            piecewise_guards = pw.raise_guards
            lifted = _adopt_piecewise(pw)
        else:
            from ..inventory import unliftable_summary
            try:
                summary = unliftable_summary(fn)
            except TimeoutError:
                raise
            except Exception:
                summary = None
            sketch = "function body is not derivable"
            if summary:
                sketch = f"{sketch}, {summary}"
            else:
                sketch = (f"{sketch} in v1: contains a loop, branch, recursion, "
                          "or a non-scalar parameter")
            return ProofResult("unliftable", sketch=sketch)

    # implicit raise regions, math.sqrt of a negative, division by
    # zero, join whatever explicit guards the lift itself found: the
    # standard library's partiality is a raise like any other, and the
    # same pedantic raise-region verdict below adjudicates both
    from ._partiality import partiality_walk
    try:
        implicit, unread = partiality_walk(fn, facts, domain or {})
    except TimeoutError:
        raise
    except Exception:
        implicit, unread = [], "raise-region pass failed"
    if unread and _walk_notes is not None:
        _walk_notes.setdefault("unread", f"{fn.__name__} {unread}")
    if implicit:
        piecewise_guards = list(piecewise_guards) + implicit

    # Domain assumptions (e.g. sigma declared nonnegative) must be baked
    # into the symbols *before* the law is parsed, not substituted into
    # the result afterward: an operation like integrate()/lim()/d() needs
    # the assumption while it's computing, not just at the final
    # comparison; substituting only at the end is too late for sympy to
    # e.g. resolve sign(sigma) mid-integration, and can surface as an
    # opaque internal error rather than a clean proof or "undecided".
    # A strictly positive lower bound gets the strictly-positive assumption,
    # not merely nonnegative: `nonnegative=True` still admits 0, which is
    # enough ambiguity that some operations (a Gaussian's normalizing
    # integral, notably) can't resolve internally and fall back to an
    # unevaluated Piecewise instead of the clean closed form a declared
    # `sigma in [1e-6, ...]` domain actually promises. See
    # _domain_assumptions() for the actual construction (shared with
    # try_prove_fold()'s own use of it).
    domain = domain or {}
    # the premise is part of the region, so it tightens the box before
    # the symbols are built; afterwards is too late, since a symbol's
    # sign assumptions are fixed at creation and the interval rung
    # reads the box, not the ask() context
    domain = _tighten_domain_by_assumption(domain, lifted.params, assumption)
    try:
        subs, bound_context, assumed_params, pins = _domain_assumptions(lifted.params, domain)
    except InvalidDomain as e:
        return ProofResult("unliftable", sketch=f"declared domain is not "
                           f"projectable: {e}")

    def _subs_one_maybe_array(e, subs):
        if isinstance(e, _SymbolicArray):
            return _SymbolicArray(e.expr.subs(subs, simultaneous=True), e.index,
                                  e.length.subs(subs, simultaneous=True))
        return e.subs(subs, simultaneous=True)

    def _subs_maybe_tuple(expr, subs):
        if not subs:
            return expr
        return (tuple(_subs_one_maybe_array(e, subs) for e in expr) if isinstance(expr, tuple)
               else _subs_one_maybe_array(expr, subs))

    def _nonidentity_call_args(src: str) -> bool:
        # does the law call f itself with anything other than a bare
        # parameter name? `f(-partial, sigma)` substitutes a
        # transformed argument into f's PRE-BAKED body, whose sign
        # resolution belonged to the original argument, the false-
        # disproof hazard. Two argument shapes cannot trigger it: a
        # numeric LITERAL inside the parameter's own declared domain
        # (it satisfies every assumption the bake derives from that
        # domain), and any argument to a funcs= BOUND function (a
        # bound function's body is lifted with plain symbols, so the
        # composite argument substitutes in carrying its own true
        # assumptions; there is no pre-collapsed sign to contradict).
        from ..domain import domain_contains
        param_order = list(lifted.params)
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError:
            return False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "f":
                for i, a in enumerate(node.args):
                    if isinstance(a, ast.Name) and a.id in lifted.params:
                        continue
                    if i >= len(param_order):
                        return True
                    try:
                        value = ast.literal_eval(a)
                    except (ValueError, SyntaxError):
                        return True
                    if not isinstance(value, (int, float)) \
                            or isinstance(value, bool):
                        return True
                    bound = domain.get(param_order[i])
                    if bound is None:
                        # no bound means no assumption is baked for
                        # this parameter, nothing to contradict
                        continue
                    try:
                        if not domain_contains(float(value), bound):
                            return True
                    except Exception:
                        return True
        return False

    def _sign_sensitive(expr) -> bool:
        parts = expr if isinstance(expr, tuple) else (expr,)
        for e in parts:
            base = e.expr if isinstance(e, _SymbolicArray) else e
            if hasattr(base, "has") and base.has(sympy.Abs, sympy.sign,
                                                 sympy.Max, sympy.Min):
                return True
        return False

    keep_plain = lifted.branch_complete or (
        _sign_sensitive(lifted.expr)
        and (_nonidentity_call_args(lhs_src)
             or (bool(rhs_src) and _nonidentity_call_args(rhs_src))))
    if keep_plain and subs:
        # a piecewise lift keeps its plain symbols: baking a sign
        # assumption in would collapse the branches the declared domain
        # doesn't select, which is only sound for bare-parameter calls.
        # The same applies to a sign-SENSITIVE body (Abs/sign/Min/Max)
        # when the law substitutes a transformed argument: sympy
        # collapses Abs(positive_sym) to the symbol at bake time, so a
        # later f(-partial, ...) substitution lands in a body whose
        # sign resolution belonged to the ORIGINAL argument (the
        # Abs-under-negated-argument false falsification). The domain
        # still acts, through bound_context and pins, both remapped
        # back onto the original symbols here.
        inverse = {new_sym: old_sym for old_sym, new_sym in subs.items()}
        if bound_context is not None:
            bound_context = bound_context.subs(inverse)
        pins = {inverse.get(sym, sym): value for sym, value in pins.items()}
        subs, assumed_params = {}, lifted.params
    lifted = replace(lifted, expr=_subs_maybe_tuple(lifted.expr, subs),
                     params=assumed_params)
    if subs and piecewise_guards:
        # raise guards were collected over the plain parameter symbols;
        # the assumption bake just renamed those in the lift, and the
        # guard machinery below matches symbols by object, remap, or
        # every guard silently stops resolving against the domain
        piecewise_guards = [(cond.subs(subs, simultaneous=True), exc)
                            for cond, exc in piecewise_guards]

    def build(src: str, aux: dict):
        # lowering under the tier's own budget: an extensive attempt
        # gives the limit/antiderivative evaluation the extensive cap,
        # not just the strategy ladder (a hard asymptotic limit that
        # outruns the fast cap gets its real chance before the claim
        # reports unliftable)
        from .._timeout import (EXTENSIVE_TIMEOUT_SECONDS,
                                FAST_TIMEOUT_SECONDS, tier_budget)
        cap = EXTENSIVE_TIMEOUT_SECONDS if extensive else FAST_TIMEOUT_SECONDS
        try:
            tree = ast.parse(src, mode="eval")
            with tier_budget(cap):
                return _law_to_sympy(tree, lifted, set(lifted.params), aux)
        except (SyntaxError, NotSymbolic) as e:
            raise NotSymbolic(str(e)) from e

    from ..conjecture import DEFAULT_TOLERANCE
    aux: dict = {}
    eps_val = sympy.Float(tolerance if tolerance is not None
                          else DEFAULT_TOLERANCE)
    aux["eps"] = aux["epsilon"] = aux["ε"] = eps_val
    if aux_funcs_lifted:
        aux[_AUX_FUNCS_KEY] = aux_funcs_lifted
    # ONE variable pipeline: a `let`-declared free variable with a
    # declared bound gets exactly the treatment a real parameter gets,
    # an assumption-carrying symbol (so sign facts reach every
    # simplification) and, below, membership in the params handed to
    # the deciders (so the interval machinery bounds it). Without this,
    # `let wa be [0,20]` proved strictly less than `for wa in [0,20]`
    # over the identical mathematics.
    from ..domain import bound_assumptions as _bound_assumptions
    from ..domain import bound_context as _bound_ctx
    let_symbols: dict = {}
    for let_name, let_bound in domain.items():
        if let_name in lifted.params or let_name in aux:
            continue
        try:
            kwargs = _bound_assumptions(let_bound)
        except Exception:
            kwargs = None
        sym = sympy.Symbol(let_name, **(kwargs or {"real": True}))
        aux[let_name] = sym
        let_symbols[let_name] = sym
        try:
            pred = _bound_ctx(sym, let_bound)
        except Exception:
            pred = None
        if pred is not None:
            bound_context = pred if bound_context is None \
                else sympy.And(bound_context, pred)
    try:
        lhs = build(lhs_src, aux)
        rhs = build(rhs_src, aux)
    except NotSymbolic as e:
        return ProofResult("unliftable", sketch=f"claim statement not derivable: {e}")
    if let_symbols:
        # the deciders' interval/hull machinery works off `params`;
        # bound let-variables join it so their declared ranges bound
        # them exactly like parameter domains do
        lifted = replace(lifted, params={**lifted.params, **let_symbols})
    assumed_gaps: list = []
    assumed_nonzero: list = []
    for a_lhs_src, a_rel, a_rhs_src in (assumption or []):
        # normalize each `A <rel> B` conjunct to a nonnegative gap:
        # gap >= 0 (or > 0 when strict), usable both as an ask()
        # predicate and for excluding raise guards the assumed region
        # provably avoids
        try:
            a_lhs, a_rhs = build(a_lhs_src, aux), build(a_rhs_src, aux)
        except NotSymbolic as e:
            return ProofResult("unliftable",
                               sketch=f"assuming clause not derivable: {e}")
        if a_rel == "==":
            gap = a_lhs - a_rhs
            assumed_gaps.append((gap, False))
            assumed_gaps.append((-gap, False))
            pred = sympy.Q.zero(gap)
        elif a_rel == "!=":
            gap = a_lhs - a_rhs
            assumed_nonzero.append(gap)
            pred = sympy.Q.nonzero(gap)
        else:
            gap = (a_lhs - a_rhs) if a_rel in (">=", ">") else (a_rhs - a_lhs)
            strict = a_rel in (">", "<")
            assumed_gaps.append((gap, strict))
            pred = sympy.Q.positive(gap) if strict else sympy.Q.nonnegative(gap)
        bound_context = pred if bound_context is None \
            else sympy.And(bound_context, pred)

    # degenerate-domain pins apply HERE, after the law is converted,
    # never baked into the lifted expression first, which would collapse
    # it to a constant before f(q, p)-style argument order can mean
    # anything (see _domain_assumptions' own docstring: a pre-baked pin
    # once made f(q, p) == f(p, q) falsely "prove" under two pins).
    if pins:
        def _pin(e):
            if isinstance(e, tuple):
                return tuple(_pin(v) for v in e)
            if isinstance(e, _SymbolicArray):
                return _SymbolicArray(e.expr.subs(pins, simultaneous=True), e.index,
                                      e.length.subs(pins, simultaneous=True))
            return e.subs(pins, simultaneous=True)
        lhs, rhs = _pin(lhs), _pin(rhs)

    if isinstance(lhs, _SymbolicArray) or isinstance(rhs, _SymbolicArray):
        return ProofResult("unliftable", sketch="an array-valued expression must "
                           "be indexed, e.g. f(...)[i], before it can be compared")

    lhs_tuple, rhs_tuple = isinstance(lhs, tuple), isinstance(rhs, tuple)
    if lhs_tuple != rhs_tuple:
        return ProofResult("unliftable", sketch="cannot compare a tuple-valued "
                           "expression (a function that returns more than one "
                           "value) against a single scalar expression")
    if lhs_tuple and len(lhs) != len(rhs):
        return ProofResult("unliftable", sketch=f"tuple length mismatch: "
                           f"{len(lhs)}-tuple vs {len(rhs)}-tuple")

    def _mechanized(result: ProofResult) -> ProofResult:
        if route_mechanism and result.status in ("proven", "disproven"):
            return replace(result, meta={**result.meta,
                                         "mathema.derive_route": route_mechanism})
        return result

    def _quantified(result: ProofResult) -> ProofResult:
        result = _mechanized(result)
        if result.status != "proven":
            return result
        kink = _kink_in_domain(aux.get(_KINKS_KEY) or [], domain)
        if kink is not None:
            return ProofResult(
                "undecided",
                sketch=f"{result.sketch}; not kept as a proof: a derivative "
                       f"in the claim does not exist where {kink}, which the "
                       f"declared domain does not exclude",
                meta=dict(result.meta))
        names = (_free_names(lhs) | _free_names(rhs)) if not lhs_tuple else \
            set().union(*(_free_names(lv) | _free_names(rv) for lv, rv in zip(lhs, rhs)))
        return replace(result, quantifier=_quantifier_clause(
            names, list(lifted.params), domain))

    if piecewise_guards and assume_defined:
        # `assuming defined(f)` quantifies over exactly the region
        # where every call returns: the raise regions are excluded by
        # the quantifier itself, and their negations feed the decision
        # machinery as algebraic assumptions
        triples = _call_guard_conditions(lhs_src, rhs_src, lifted,
                                         piecewise_guards,
                                         bound_funcs=aux_funcs_lifted)
        if triples:
            d_gaps, d_nonzero, d_preds = _defined_assumptions(
                [t[0] for t in triples])
            assumed_gaps.extend(d_gaps)
            assumed_nonzero.extend(d_nonzero)
            for pred in d_preds:
                bound_context = pred if bound_context is None \
                    else sympy.And(bound_context, pred)
    verdict_guards = [] if assume_defined else piecewise_guards
    if verdict_guards or aux_funcs_guards:
        from .._timeout import (EXTENSIVE_TIMEOUT_SECONDS,
                                FAST_TIMEOUT_SECONDS, _with_timeout)
        guard_clock = EXTENSIVE_TIMEOUT_SECONDS if extensive \
            else FAST_TIMEOUT_SECONDS
        try:
            raise_verdict = _with_timeout(
                lambda: _raise_region_verdict(
                    lhs_src, rhs_src, lifted, verdict_guards, domain,
                    bound_funcs=aux_funcs_lifted,
                    assumed_gaps=assumed_gaps,
                    assumed_nonzero=assumed_nonzero,
                    aux_guards=aux_funcs_guards,
                    callables={"f": fn, **(funcs or {})}),
                guard_clock)
        except TimeoutError:
            # ran out of clock neither witnessing nor excluding: the
            # same honest resting place as an undecidable guard
            raise_verdict = ProofResult(
                "undecided",
                sketch="raise-region analysis exceeded its wall clock, "
                       "narrow the domain to where every call returns, or "
                       "state the raising region as its own raises(...) "
                       "claim", meta={"mathema.timeout": "fast"})
        if raise_verdict is not None:
            if raise_verdict.status == "undecided" and piecewise_hint:
                raise_verdict = replace(raise_verdict,
                                        sketch=f"{raise_verdict.sketch}; "
                                               f"{piecewise_hint}")
            return _mechanized(raise_verdict)
    try:
        if lhs_tuple:
            # a claim against a tuple-valued f(...) (a function returning
            # more than one value, e.g. `return x, y`) is elementwise: each
            # position gets its own _prove_relation call, combined below;
            # proven only if every element is, disproven if any is (that's
            # already a counterexample to the whole claim), else undecided.
            results = [_prove_relation(lv, rv, relation, domain, bound_context, lifted.params,
                                  opaque=lifted.opaque, extensive=extensive,
                                  tolerance=tolerance if tolerance is not None else 1e-9)
                      for lv, rv in zip(lhs, rhs)]
            sketch = "; ".join(f"[{i}] {r.sketch}" for i, r in enumerate(results) if r.sketch)
            statuses = {r.status for r in results}
            if statuses == {"proven"}:
                return _quantified(ProofResult("proven", sketch=sketch))
            if "disproven" in statuses:
                return ProofResult("disproven", sketch=sketch)
            return ProofResult("undecided", sketch=sketch)
        result = _prove_relation(lhs, rhs, relation, domain, bound_context, lifted.params,
                                 opaque=lifted.opaque,
                                 tolerance=tolerance if tolerance is not None else 1e-9)
        if result.status == "undecided" and _split_depth == 0:
            # the fast-pass rescue rungs: squaring for radical
            # comparisons, loggamma canonicalization, and the
            # nonnegative-gap WLOG substitution. Each is gated by a
            # near-free structural precheck and capped at the fast wall
            # clock (see _extensive.fast_rescue_attempts). Not behind
            # extensive; cheap on exactly the claims that can use
            # them, free on the rest.
            from ._strategies import fast_rescue_attempts
            rescue = fast_rescue_attempts(lhs, rhs, relation, domain,
                                          lifted.params)
            if rescue is not None:
                result = rescue
        if result.status == "undecided" and extensive:
            # the strategy ladder, not just a longer leash: root
            # isolation, interval refinement, the rewrite gallery, the
            # substitution library, then one widened-cap retry of the
            # base procedure (see _extensive).
            from ._extensive import extensive_ladder
            ladder_result, attempted = extensive_ladder(
                lhs, rhs, relation, domain, bound_context, lifted.params,
                opaque=lifted.opaque)
            if ladder_result is not None:
                result = ladder_result
            elif attempted:
                result = replace(result, sketch=f"{result.sketch}; extensive "
                                 "attempts did not settle it either: "
                                 + ", ".join(attempted))
        if result.status == "undecided":
            result = _try_case_split(lhs, rhs, relation, domain, bound_context, lifted.params,
                                     opaque=lifted.opaque, extensive=extensive) or result
        if result.status == "undecided" and piecewise_hint:
            # the branch-pruning diagnosis stays actionable even though
            # the piecewise lift got further than pruning did
            result = replace(result, sketch=f"{result.sketch}; {piecewise_hint}")
        if result.status == "undecided":
            # hand the resolved symbolic sides to the caller: the
            # numeric fallback can lambdify and sample the exact
            # intermediate the proof stalled on (a d()/integrate() law
            # the probe route cannot evaluate lives on through it)
            result = replace(result, intermediates=(lhs, rhs,
                                                    dict(lifted.params),
                                                    lifted.opaque))
        if aux.get(_LIM_NOTE_KEY):
            # terse input, explicit output: the direction the engine
            # resolved for an undirected finite-point limit is stated
            # in the record, never silently applied
            note = aux.pop(_LIM_NOTE_KEY)
            result = replace(result, sketch=f"{result.sketch}; {note}"
                             if result.sketch else note)
        return _quantified(result)
    except TimeoutError:
        result = ProofResult("undecided",
                             sketch="proof attempt exceeded its wall clock",
                             meta={"mathema.timeout": "fast"})
        try:
            if not isinstance(lhs, tuple) and not isinstance(rhs, tuple):
                result = replace(result,
                                 intermediates=(lhs, rhs, dict(lifted.params),
                                                lifted.opaque))
        except NameError:
            pass   # the clock expired before the sides were even built
        return result
    except Exception as e:
        return ProofResult("undecided", sketch=f"{type(e).__name__} during proof: {e}")


def try_prove_raises(fn, facts, call_src: str, exc_name: str | None,
                     domain: dict | None = None, max_callee_depth: int = 3) -> ProofResult:
    """A raises(...) claim on the derive route, only ever reachable via
    domain-conditioned branch pruning: a raises claim with no declared
    domain specific enough to determine which branch runs stays
    unliftable, the same as any other derive claim would with an
    unresolvable branch. `call_src` must be a bare `f(...)` call (no
    multi-function claims here, same restriction check_conjectures()
    already applies before this is ever called). `max_callee_depth` is
    forwarded to lift_conditioned(), see lift()'s own docstring."""
    try:
        tree = ast.parse(call_src, mode="eval")
    except SyntaxError as e:
        return ProofResult("unliftable", sketch=f"unparseable call: {e}")
    if not (isinstance(tree.body, ast.Call) and isinstance(tree.body.func, ast.Name)
            and tree.body.func.id == "f"):
        return ProofResult("unliftable", sketch="raises(...) needs a bare f(...) call")

    if facts.tree is not None and not any(isinstance(n, ast.Raise) for n in ast.walk(facts.tree)):
        return ProofResult("unliftable", sketch="no explicit raise statement "
                           "anywhere in this function, an exception implicit "
                           "in an arithmetic operation (division, sqrt of a "
                           "negative, ...) can't be proven this way; only an "
                           "explicit `if cond: raise ...` guard can")

    conditioned = lift_conditioned(fn, facts, domain or {}, max_callee_depth=max_callee_depth)
    if conditioned is None:
        branch_sketch = _branch_pruning_sketch(fn, facts)
        if branch_sketch is not None:
            return ProofResult("unliftable", sketch=f"branch pruning couldn't "
                               f"settle which side runs under this domain: "
                               f"{branch_sketch}")
        return ProofResult("unliftable", sketch="function body is not derivable "
                           "in v1 even with branch pruning: contains a loop, "
                           "recursion, a non-scalar parameter, or the declared "
                           "domain doesn't settle which branch runs")
    if conditioned.kind == "value":
        return ProofResult("disproven", sketch="the function returns a value "
                           "under this domain rather than raising")
    if exc_name is None or conditioned.exc_type == exc_name:
        return ProofResult("proven", sketch=f"raises {conditioned.exc_type or '(unknown type)'} "
                           "under this domain")
    if conditioned.exc_type is None:
        return ProofResult("undecided", sketch="raises under this domain, but the "
                           "exception type couldn't be determined")
    return ProofResult("disproven", sketch=f"raises {conditioned.exc_type}, "
                       f"not the claimed {exc_name}")
