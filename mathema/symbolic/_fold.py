# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Linear accumulator folds: `lift()` refuses any function with a loop,
unconditionally. The functions here extend that for one specific,
narrow case: a single accumulator updated once per element of one
sequence parameter by an expression affine in that element and the
running accumulator (`acc = A*item + B*acc`, A and B built from the
function's other, scalar parameters only), then returned. Two starting
shapes are recognized; the accumulator can start at the sequence's
own first element (folding over the rest, `seq[1:]`), or at a separate
value entirely, typically another parameter, (folding over the
whole sequence). Both are the same unrolled linear recurrence with a
different starting point and element count, so their closed forms are
written directly, not solved generically. No general loop-folding,
recurrence-solving, or sequence-symbolic machinery is added; only these
two shapes are recognized, and anything else declines (returns None)
rather than guessing.
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field, replace

import sympy

from ..finite_sets import OpaqueRegistry
from ._base import (
    NotSymbolic, _SymbolicArray, _bind_params, _expr_to_sympy,
    _literal_int_index,
)
from ._loop_shapes import (
    bare_seq_name, classify_loop_header, _references_name, seq_one_colon,
    _update_rhs,
)
from ._proof_support import ProofResult
from ._seq_common import _unliftable_result, SeqLiftView, try_prove_seq

# --- linear accumulator folds -----------------------------------------------
#
# lift() above refuses any function with a loop, unconditionally. The
# function below extends that for one specific, narrow case: a single
# accumulator updated once per element of one sequence parameter by an
# expression affine in that element and the running accumulator (`acc =
# A*item + B*acc`, A and B built from the function's other, scalar
# parameters only), then returned. Two starting shapes are recognized;
# the accumulator can start at the sequence's own first element (folding
# over the rest, `seq[1:]`), or at a separate value entirely, typically
# another parameter; (folding over the whole sequence). Both are the
# same unrolled linear recurrence with a different starting point and
# element count, so their closed forms are written directly, not solved
# generically. No general loop-folding, recurrence-solving, or sequence-
# symbolic machinery is added; only these two shapes are recognized, and
# anything else declines (returns None) rather than guessing.


@dataclass
class FoldLift:
    """A recognized linear accumulator fold, lifted to a closed-form sympy
    expression over an indexed sequence `seq` of symbolic length `L`
    (`seq[0]` .. `seq[L-1]`). Two `mode`s:

    `"from_first_element"`, `acc = seq[0]; for item in seq[1:]: acc =
    coeff_item*item + coeff_acc*acc; return acc`. Valid for `L >= 1`
    (matching that `seq[0]` in the real source already assumes a
    nonempty sequence; an empty one is a precondition violation of the
    original function, not a gap in this closed form):

        L == 1:  seq[0]
        L >= 2:  coeff_acc**(L-1) * seq[0] + coeff_item * seq[L-1]
                 + Sum(coeff_item * coeff_acc**(L-1-k) * seq[k], (k, 1, L-2))

    `"external_init"`, `acc = <init_expr>; for item in seq: acc =
    coeff_item*item + coeff_acc*acc; return acc`, where `init_expr`
    doesn't reference `seq` at all (typically a separate scalar
    parameter). Valid for every `L >= 0`; an empty sequence is not a
    precondition violation here, the loop just never runs and the real
    function returns `init_expr` unchanged, exactly as this closes to:

        L == 0:  init_expr
        L >= 1:  coeff_acc**L * init_expr + coeff_item * seq[L-1]
                 + Sum(coeff_item * coeff_acc**(L-1-k) * seq[k], (k, 0, L-2))

    In both modes the last folded term is pulled out of the sum and
    written as a bare `coeff_item * seq[...]` rather than
    `coeff_item * coeff_acc**0 * seq[...]`, so substituting
    `coeff_acc == 0` later, e.g. proving a claim at a specific
    parameter value, never has to resolve sympy's `0**0`.
    `other_params` binds every scalar parameter besides `seq_param` to
    its own symbol, the same role `Lifted.params` plays for `lift()`.

    A third shape needs no sequence at all, `balance = P; for _ in
    range(n): balance = balance*(1+r); return balance` (compound
    interest, a bare fixed-iteration-count fold): always
    `mode="external_init"` (there's no `seq[0]` to start from), `seq`/
    `seq_param` are `None`, and `length` is the loop's own trip-count
    expression itself (`n`, or any liftable expression built from it,
    e.g. `n + 1`) rather than a fresh opaque symbol, referenceable
    directly in claim text the same way any other scalar parameter is,
    no `len(...)`-style indirection needed. Everywhere `seq[k]`/
    `seq[L-1]` appears in the closed forms above, the item's own value
    at position `k`/`L-1` is simply `k`/`L-1` itself in this shape;
    absent a sequence, the loop's own index *is* the item.

    `expr` is the closed form of *what the function returns*, not
    necessarily the accumulator's own value, the two coincide for a
    bare `return acc`, but the function may instead return some
    transformation of it (`return acc / len(seq)`, a mean; `return
    sqrt(acc / len(seq))`, an RMS). `acc_expr`/`acc_sym` are the
    accumulator's own closed form and the bare symbol it's known by in
    `return_template`; the return expression lifted with the
    accumulator bound to `acc_sym` rather than its closed form, kept
    around (rather than only ever substituting once, up front) so
    `_fold_eval_at()`'s zero-collapse rebuild can still rebuild just the
    accumulator's own piece before the transformation is reapplied on
    top, at claim-evaluation time under a specific scalar substitution."""
    expr: "sympy.Expr | tuple"
    mode: str
    seq_param: "str | None"
    seq: "sympy.IndexedBase | None"
    length: "sympy.Expr"
    init_expr: "sympy.Expr"
    coeff_item: "sympy.Expr"
    coeff_acc: "sympy.Expr"
    other_params: dict
    acc_expr: "sympy.Expr" = None
    acc_sym: "sympy.Symbol" = None
    return_template: "sympy.Expr | tuple" = None
    sig_params: list = field(default_factory=list)
    unicode: str = ""
    latex: str = ""
    opaque: "OpaqueRegistry | None" = None
    raise_guards: list = field(default_factory=list)
    # leading `if cond: raise` statements stripped before the fold
    # shape was recognized (each entry the guard's ast condition node):
    # the partiality contract of the function, which try_prove_fold
    # must verify the claim's domain provably avoids before any proof
    # over the closed form stands


_FOLD_LEN_PLACEHOLDER = "__fold_length__"


class _ReplaceFoldLenCall(ast.NodeTransformer):
    """Rewrites `len(<seq_param>)` calls in a fold's own *return*
    expression to a bare reference to `_FOLD_LEN_PLACEHOLDER`, so the
    general-purpose `_expr_to_sympy`, which has no idea what a fold's
    own symbolic length means, that's purely `_fold_law_to_sympy`'s
    *claim*-grammar convention, can still lift a return expression
    that calls it (`return total / len(xs)`, a mean) by binding the
    placeholder to the fold's own length symbol in `env` first. Always
    run against a copy (see lift_fold()), never the real AST in place;
    `facts.tree` is shared with every other analysis over this
    function."""
    def __init__(self, seq_param: str):
        self.seq_param = seq_param

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if isinstance(node.func, ast.Name) and node.func.id == "len" \
                and len(node.args) == 1 and isinstance(node.args[0], ast.Name) \
                and node.args[0].id == self.seq_param and not node.keywords:
            return ast.copy_location(
                ast.Name(id=_FOLD_LEN_PLACEHOLDER, ctx=ast.Load()), node)
        return self.generic_visit(node)


def lift_fold(fn, facts) -> "FoldLift | None":
    """Recognize and lift one of the three loop shapes FoldLift
    describes (two sequence-based, plus a no-sequence bare
    fixed-iteration-count fold, see FoldLift's own docstring). Every
    structural check must hold exactly, any other shape (a guard
    inside the loop, more than one statement in its body, an initial
    value that partly but not fully depends on `seq_param`, an update
    with a nonzero additive constant or a term that mixes the item and
    the accumulator non-affinely) returns None rather than
    approximating it. The function's own `return` doesn't have to be
    the bare accumulator; `return acc / len(seq)` (a mean), `return
    sqrt(acc / len(seq))` (an RMS), or any other expression liftable
    with the accumulator bound to its own bare symbol, resolves too.
    One implementation serves both this and `diagnose_fold()`
    (`_lift_fold_impl`): every decline site returns its own diagnosis,
    so the two can never drift apart."""
    result = _lift_fold_impl(fn, facts)
    return result if isinstance(result, FoldLift) else None


def diagnose_fold(fn, facts) -> dict | None:
    """Why `lift_fold()` declined a loop-shaped function: the exact
    diagnosis the shared implementation produced at the first check
    that failed, `{"reason", "hint", "derive_unlock"}` (`derive_unlock` is
    `"actionable"` or `"limitation"`, stated per site). `None`
    if there's no loop to explain, or `lift_fold()` actually succeeds
    (nothing to diagnose; the caller should use the lift itself)."""
    if not facts.loops:
        return None
    result = _lift_fold_impl(fn, facts)
    return None if isinstance(result, FoldLift) else result


def _lift_fold_impl(fn, facts) -> "FoldLift | dict":
    """Intent:
        The one shared walk behind `lift_fold()` (which keeps a
        successful `FoldLift` and discards diagnoses) and
        `diagnose_fold()` (the reverse): recognize the fold shape,
        building the lift as the checks pass, and return a
        `{"reason", "hint", "derive_unlock"}` diagnosis from the first check
        that fails.

    Notes:
        Check order follows the old `diagnose_fold()`'s user-facing
        order (structural coarse-to-fine), which shapes are accepted is
        identical to the old `lift_fold()`; all checks were
        conjunctive in both, so the order never changed the accept set,
        only which reason a multi-defect function reports first.
    """
    if not facts.loops:
        return {"reason": "no-loop", "hint": "no loop to lift as a fold",
               "derive_unlock": "limitation"}
    if len(facts.loops) > 1:
        return {"reason": "multiple-loops",
               "hint": f"{len(facts.loops)} loops, doesn't match the one "
                      "recognized linear-fold shape (which allows exactly one), "
                      "and the more general 'pure sum' loop recognizer "
                      "(lift_sum(), which does allow multiple sequential "
                      "accumulator loops) doesn't match this specific shape "
                      "either",
               "derive_unlock": "limitation"}
    loop = facts.loops[0]
    if loop.kind != "fold":
        return {"reason": "not-a-fold",
               "hint": f"this loop {loop.kind}s a list rather than folding into "
                      f"a scalar accumulator (`{loop.op_source or '...'}`), only "
                      "an accumulator fold (`acc = <expr involving acc>`) is "
                      "recognized",
               "derive_unlock": "limitation"}
    if loop.guarded:
        return {"reason": "guarded-fold",
               "hint": "the accumulator update sits under an `if` inside the "
                      "loop, only an unconditional update every iteration is "
                      "recognized",
               "derive_unlock": "limitation"}
    # leading `if cond: raise` guards before the fold are the
    # function's partiality contract, not a reason to refuse the fold:
    # they are stripped here, carried on the lift, and try_prove_fold
    # verifies the claim's domain provably avoids each one
    from ._normalize import normalized_body
    body_scan = normalized_body(fn, facts) if facts.tree is not None else []
    lead_guards = []
    while body_scan and _is_lead_raise_guard(body_scan[0]):
        lead_guards.append(_canonical_guard(body_scan[0], facts.params))
        body_scan = body_scan[1:]
    if facts.branch_count > len(lead_guards):
        return {"reason": "branch-elsewhere",
               "hint": "the function has a branch outside the loop (beyond "
                      "any leading raise guards), lift_fold() only attempts "
                      "a body that is exactly [raise guards; accumulator "
                      "init; the fold; return], nothing else",
               "derive_unlock": "limitation"}
    if facts.recursion:
        return {"reason": "recursion",
               "hint": "the function also recurses, not derivable regardless "
                      "of the loop shape",
               "derive_unlock": "limitation"}
    seq_params = [p for p in facts.params if facts.param_kinds.get(p) == "sequence"]
    if len(seq_params) > 1:
        return {"reason": "wrong-sequence-param-count",
               "hint": f"{len(seq_params)} sequence-typed parameters, at most "
                      "one is allowed for this specific linear-fold shape "
                      "(closing a `coeff_acc != 1` recurrence to a closed form "
                      "needs it). A function summing over multiple sequences "
                      "at once, a dot product, e.g. `for i in "
                      "range(len(a)): total += a[i]*b[i]`; may still be "
                      "derivable via the more general 'pure sum' recognizer "
                      "(lift_sum()), which doesn't have this restriction; this "
                      "diagnosis only covers the narrower fold shape",
               "derive_unlock": "limitation"}
    seq_param = seq_params[0] if seq_params else None

    body = body_scan
    if len(body) != 3:
        return {"reason": "extra-statements",
               "hint": f"the function body has {len(body)} statement(s) besides "
                      "the loop, only exactly [accumulator init; the fold; "
                      "return] is recognized (leading raise guards excepted), "
                      "nothing before or after",
               "derive_unlock": "limitation"}
    init_stmt, loop_stmt, return_stmt = body

    if not (isinstance(init_stmt, ast.Assign) and len(init_stmt.targets) == 1
            and isinstance(init_stmt.targets[0], ast.Name)):
        return {"reason": "non-simple-init",
               "hint": "the statement before the loop isn't a plain "
                      "`name = ...` assignment initializing the accumulator",
               "derive_unlock": "limitation"}
    acc_name = init_stmt.targets[0].id

    if not (isinstance(loop_stmt, ast.For) and isinstance(loop_stmt.target, ast.Name)):
        return {"reason": "non-simple-loop-header",
               "hint": "the loop's own target isn't a plain bare name",
               "derive_unlock": "limitation"}
    item_name = loop_stmt.target.id

    trip_count_node = None
    if seq_param is not None:
        starts_at_first_element = (isinstance(init_stmt.value, ast.Subscript)
            and isinstance(init_stmt.value.value, ast.Name)
            and init_stmt.value.value.id == seq_param
            and _literal_int_index(init_stmt.value.slice) == 0)
        references_seq = _references_name(init_stmt.value, seq_param)
        loops_over_rest = seq_one_colon(loop_stmt.iter, seq_param)
        loops_over_all = bare_seq_name(loop_stmt.iter, seq_param)

        if starts_at_first_element and not loops_over_rest:
            return {"reason": "first-element-init-wrong-iteration",
                   "hint": f"the accumulator starts at {seq_param}[0] but the loop "
                          f"iterates {ast.unparse(loop_stmt.iter)!r}, not "
                          f"{seq_param}[1:]; iterating the whole sequence would "
                          f"double-count {seq_param}[0]; change the loop to "
                          f"`for {item_name or 'item'} in {seq_param}[1:]:`",
                   "derive_unlock": "actionable"}
        if references_seq and not starts_at_first_element:
            return {"reason": "partial-seq-init",
                   "hint": f"the accumulator's initial value references "
                          f"{seq_param!r} but isn't exactly {seq_param}[0] (it's "
                          f"`{ast.unparse(init_stmt.value)}`), only 'starts at "
                          f"the sequence's own first element' or 'starts at a "
                          "value that doesn't depend on the sequence at all "
                          "(e.g. a separate parameter)' are recognized",
                   "derive_unlock": "actionable"}
        if not references_seq and not loops_over_all:
            return {"reason": "external-init-wrong-iteration",
                   "hint": f"the accumulator's initial value "
                          f"(`{ast.unparse(init_stmt.value)}`) doesn't depend on "
                          f"{seq_param!r} at all, but the loop iterates "
                          f"{ast.unparse(loop_stmt.iter)!r} instead of the whole "
                          f"sequence, change the loop to "
                          f"`for {item_name or 'item'} in {seq_param}:`, or "
                          f"initialize from {seq_param}[0] instead",
                   "derive_unlock": "actionable"}
        mode = "from_first_element" if starts_at_first_element else "external_init"
    else:
        # no sequence parameter at all, only "external_init" makes
        # sense (there's no seq[0] to start an accumulator from); the
        # loop's own iterable must be the bare fixed-trip-count shape
        # lift_sum()'s own classify_loop_header already recognizes
        # (range(<expr>), <expr> any derivable expression, e.g. n, n+1,
        # 2*n, not just a bare name).
        mode = "external_init"
        classified = classify_loop_header(loop_stmt, set())
        if classified is None or classified[0] != "scalar_index":
            return {"reason": "unrecognized-loop-header",
                   "hint": f"the loop iterates {ast.unparse(loop_stmt.iter)!r}, "
                          "with no sequence-typed parameter in this function, "
                          "only `for i in range(<expr>):` (or `for _ in "
                          "range(<expr>):`, <expr> any derivable expression, e.g. "
                          "a scalar parameter, `n + 1`, `2 * n`) is recognized",
                   "derive_unlock": "actionable"}
        trip_count_node = classified[1]

    if len(loop_stmt.body) != 1:
        return {"reason": "multi-statement-loop-body",
               "hint": f"the loop body has {len(loop_stmt.body)} statements, "
                      "only a single accumulator-update assignment per "
                      "iteration is recognized",
               "derive_unlock": "limitation"}
    upd_rhs = _update_rhs(loop_stmt.body[0], acc_name)
    if upd_rhs is None:
        return {"reason": "non-simple-update",
               "hint": f"the loop body's statement doesn't update {acc_name!r} "
                      "directly (a plain `=` or augmented `+=`-style "
                      "assignment to a different target isn't recognized "
                      "as the same shape)",
               "derive_unlock": "actionable"}
    if not isinstance(return_stmt, ast.Return) or return_stmt.value is None:
        return {"reason": "no-return-value",
               "hint": "the function has no return statement, or a bare "
                      "`return` with no value, nothing to lift",
               "derive_unlock": "limitation"}

    other_params = {p: s for p, s in _bind_params(fn, facts)[0].items()
                    if seq_param is None or (p != seq_param and not p.startswith(f"{seq_param}."))}
    item_sym = sympy.Symbol(item_name, real=True)
    acc_sym = sympy.Symbol(acc_name, real=True)
    opaque = OpaqueRegistry()
    if seq_param is None:
        # the trip count itself, not a fresh opaque symbol; see
        # FoldLift's own docstring for why the no-sequence shape needs
        # no `len(...)`-style indirection at all.
        try:
            length = _expr_to_sympy(trip_count_node, dict(other_params), opaque=opaque)
        except NotSymbolic as e:
            return {"reason": e.category or "unsupported-syntax",
                   "hint": f"the loop's own trip count isn't derivable: {e}",
                   "derive_unlock": "limitation"}
        if isinstance(length, (tuple, _SymbolicArray)):
            return {"reason": "tuple-in-expression",
                   "hint": "the loop's own trip count is a tuple/array, not a "
                          "single scalar value",
                   "derive_unlock": "limitation"}
    else:
        length = sympy.Symbol("L", integer=True, nonnegative=True)

    env = dict(other_params)
    env[item_name] = item_sym
    env[acc_name] = acc_sym
    try:
        rhs = _expr_to_sympy(upd_rhs, env, opaque=opaque)
    except NotSymbolic as e:
        return {"reason": e.category or "unsupported-syntax",
               "hint": f"the update expression itself isn't derivable: {e}",
               "derive_unlock": "limitation"}
    if isinstance(rhs, tuple):
        return {"reason": "tuple-in-expression",
               "hint": "the update produces a tuple, not a single scalar value",
               "derive_unlock": "limitation"}
    try:
        init_expr = env[acc_name] if mode == "from_first_element" \
            else _expr_to_sympy(init_stmt.value, dict(other_params), opaque=opaque)
    except NotSymbolic as e:
        return {"reason": e.category or "unsupported-syntax",
               "hint": f"the accumulator's initial value isn't derivable: {e}",
               "derive_unlock": "limitation"}
    if isinstance(init_expr, tuple):
        return {"reason": "tuple-in-expression",
               "hint": "the accumulator's initial value is a tuple, not a "
                      "single scalar value",
               "derive_unlock": "limitation"}
    return_value = (_ReplaceFoldLenCall(seq_param).visit(copy.deepcopy(return_stmt.value))
                    if seq_param is not None else return_stmt.value)
    try:
        # the return expression, with the accumulator bound to its own
        # bare symbol rather than a closed form yet, see FoldLift's
        # own docstring for why this stays separate from acc_expr below.
        # `len(seq_param)` (see _ReplaceFoldLenCall) resolves to the
        # fold's own symbolic length the same way it does in a claim;
        # moot for the no-sequence shape, which has no `len(...)` call
        # to rewrite in the first place.
        return_template = _expr_to_sympy(
            return_value, {**other_params, acc_name: acc_sym, _FOLD_LEN_PLACEHOLDER: length},
            opaque=opaque)
    except NotSymbolic as e:
        return {"reason": e.category or "unsupported-syntax",
               "hint": f"the accumulator update itself is fine, but the return "
                      f"expression isn't derivable: {e}",
               "derive_unlock": "limitation"}

    a = sympy.diff(rhs, item_sym)
    b = sympy.diff(rhs, acc_sym)
    if a.has(item_sym) or a.has(acc_sym) or b.has(item_sym) or b.has(acc_sym):
        return {"reason": "non-affine-update",
               "hint": f"the update (`{ast.unparse(upd_rhs)}`) isn't affine "
                      f"in the loop item and the accumulator, e.g. it "
                      "multiplies them together, only a linear combination "
                      "(`acc = A*item + B*acc`) is recognized",
               "derive_unlock": "limitation"}
    residual = sympy.expand(rhs - a * item_sym - b * acc_sym)
    if residual != 0:
        return {"reason": "additive-constant-update",
               "hint": f"the update has a nonzero additive term ({residual}), "
                      "only a pure linear combination of the item and the "
                      "accumulator is recognized today, though a constant "
                      "term is mathematically a tractable extension",
               "derive_unlock": "limitation"}

    seq = sympy.IndexedBase(seq_param) if seq_param is not None else None
    # absent a sequence, the item's own value at position k is simply k
    # itself; the loop's own index (see FoldLift's own docstring).
    item_at = (lambda idx: seq[idx]) if seq is not None else (lambda idx: idx)
    k = sympy.Symbol("k", integer=True)
    if mode == "from_first_element":
        rest = sympy.Sum(a * b**(length - 1 - k) * item_at(k), (k, 1, length - 2))
        unrolled = b**(length - 1) * item_at(0) + a * item_at(length - 1) + rest
        acc_expr = sympy.Piecewise((item_at(0), sympy.Eq(length, 1)), (unrolled, True))
    else:
        rest = sympy.Sum(a * b**(length - 1 - k) * item_at(k), (k, 0, length - 2))
        unrolled = b**length * init_expr + a * item_at(length - 1) + rest
        # a scalar trip count can be negative, and range() of one is
        # empty; at zero the unrolled form already reduces to the
        # initial value
        empty = sympy.Eq(length, 0) if seq is not None else length < 0
        acc_expr = sympy.Piecewise((init_expr, empty), (unrolled, True))
    expr = (tuple(t.subs(acc_sym, acc_expr) for t in return_template)
           if isinstance(return_template, tuple) else return_template.subs(acc_sym, acc_expr))
    from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    try:
        # cosmetic simplification of the unrolled fold, capped: the
        # unsimplified expression is exactly as sound to prove against,
        # and a pathological unroll must not hang the lift itself
        expr = _with_timeout(
            lambda: (tuple(sympy.simplify(t) for t in expr)
                     if isinstance(expr, tuple) else sympy.simplify(expr)),
            FAST_TIMEOUT_SECONDS)
    except Exception:
        pass
    from ..grammar import render_canonical
    return FoldLift(raise_guards=lead_guards,
                    expr=expr, mode=mode, seq_param=seq_param, seq=seq, length=length,
                    init_expr=init_expr, coeff_item=a, coeff_acc=b, other_params=other_params,
                    acc_expr=acc_expr, acc_sym=acc_sym, return_template=return_template,
                    sig_params=list(facts.params),
                    unicode=render_canonical(expr)[0], latex=sympy.latex(expr),
                    opaque=opaque)



def _fold_eval_at(fold: "FoldLift", subs: dict):
    """`fold.return_template` (the function's own return expression,
    with the accumulator bound to its bare `acc_sym` rather than a
    closed form, see FoldLift's own docstring for why the two stay
    separate) with `subs` (a substitution for the fold's scalar
    parameters, e.g. `{alpha: 1}`) applied throughout. The accumulator's
    own value is resolved first, with the same zero-collapse rebuild as
    always: sympy can't simplify `Sum(0**(length-1-k) * seq[k], ...)` to
    0 on its own for a *symbolic* `length` (every exponent in that sum
    is a positive integer whenever it's summed at all, so every term
    really is 0, but sympy has no way to see that without `length` being
    a concrete number). Rebuilding the accumulator's closed form
    directly with `coeff_acc == 0` already baked in sidesteps needing
    sympy to discover that identity itself, the whole sum vanishes by
    construction, and only the one non-vanishing term (the fold's last
    element) is left. That resolved accumulator value then substitutes
    for `acc_sym` in the template, and `subs` applies to whatever's left
    over (a scalar parameter the return expression references directly,
    e.g. `return acc + offset`)."""
    # `.subs(subs)` on `fold.length` is a no-op for the sequence-based
    # shapes (a fresh opaque "L" symbol, never one of `subs`'s own
    # keys), but load-bearing for the no-sequence shape, where `length`
    # is built directly from the same parameter symbols `subs` itself
    # substitutes (see FoldLift's own docstring), always applying it
    # is safe either way, not just for the new shape.
    length_at = fold.length.subs(subs, simultaneous=True)
    item_at = (lambda idx: fold.seq[idx]) if fold.seq is not None else (lambda idx: idx)
    b_at = fold.coeff_acc.subs(subs, simultaneous=True)
    if b_at == 0:
        a_at = fold.coeff_item.subs(subs, simultaneous=True)
        last = a_at * item_at(length_at - 1)
        if fold.mode == "from_first_element":
            acc_at = sympy.Piecewise((item_at(0), sympy.Eq(length_at, 1)), (last, True))
        else:
            init_at = fold.init_expr.subs(subs, simultaneous=True)
            acc_at = sympy.Piecewise((init_at, length_at <= 0), (last, True))
    else:
        acc_at = fold.acc_expr.subs(subs, simultaneous=True)
    # `subs` applies to the TEMPLATE first (its own direct scalar
    # references), and only then does the already-substituted
    # accumulator go in, the old order substituted the accumulator
    # first and then ran `subs` over the combined result, hitting the
    # accumulator's scalars a second time: a scaling claim's multiplier
    # came back exactly squared (f(xs, 2g) evaluated with 4**L, a
    # confidently wrong falsification observed across six independent
    # cases in the field).
    template_at = (tuple(t.subs(subs, simultaneous=True) for t in fold.return_template)
                  if isinstance(fold.return_template, tuple)
                  else fold.return_template.subs(subs, simultaneous=True))
    return (tuple(t.subs(fold.acc_sym, acc_at) for t in template_at)
           if isinstance(template_at, tuple)
           else template_at.subs(fold.acc_sym, acc_at))


def _fold_f_call_subs(fold: "FoldLift", node: ast.AST, recurse) -> dict:
    """The fold's own claim-text `f(...)` convention: the folded
    sequence must be the FIRST argument, a bare reference, with the
    remaining arguments mapping to the other signature parameters in
    order; the no-sequence shape maps every argument positionally
    against the whole signature instead (there is no sequence-first
    slot to require)."""
    if node.keywords:
        raise NotSymbolic(f"unsupported call {ast.unparse(node)!r}")
    if fold.seq_param is None:
        if len(node.args) != len(fold.sig_params):
            raise NotSymbolic(f"f() called with {len(node.args)} args, "
                              f"expected {len(fold.sig_params)}")
        return {fold.other_params[p]: recurse(a)
               for p, a in zip(fold.sig_params, node.args)}
    if not node.args:
        raise NotSymbolic(f"unsupported call {ast.unparse(node)!r}")
    first = node.args[0]
    elem_map = None
    if not (isinstance(first, ast.Name) and first.id == fold.seq_param):
        # a registered elementwise transform over the folded sequence
        # (`f(g(xs, c), ...)` with g bound to mathema.f.scale_seq, say)
        # composes through the closed form: the map and its lowered
        # scalar arguments ride the subs under ELEM_MAP_KEY and
        # eval_f substitutes seq[k] -> map(seq[k], c)
        from ._seq_common import _ACTIVE_TRANSFORMS
        active = _ACTIVE_TRANSFORMS.get() or {}
        if (isinstance(first, ast.Call)
                and isinstance(first.func, ast.Name)
                and first.func.id in active
                and first.args and isinstance(first.args[0], ast.Name)
                and first.args[0].id == fold.seq_param
                and not first.keywords):
            mapper = active[first.func.id]
            scalar_args = tuple(recurse(a) for a in first.args[1:])
            elem_map = (mapper, scalar_args)
        else:
            raise NotSymbolic(f"f(...)'s first argument must be a bare "
                              f"reference to {fold.seq_param!r} (or a "
                              f"bound elementwise transform of it): "
                              f"{ast.unparse(node)!r}")
    other_names = [p for p in fold.sig_params if p != fold.seq_param]
    rest = node.args[1:]
    if len(rest) != len(other_names):
        raise NotSymbolic(f"f(...) called with {len(rest)} argument(s) "
                          f"besides {fold.seq_param!r}, expected "
                          f"{len(other_names)}: {ast.unparse(node)!r}")
    subs = {fold.other_params[p]: recurse(a)
            for p, a in zip(other_names, rest)}
    if elem_map is not None:
        from ._seq_common import ELEM_MAP_KEY
        subs[ELEM_MAP_KEY] = elem_map
    return subs


def _fold_eval_mapped(fold: "FoldLift", subs: dict):
    """`_fold_eval_at`, then the elementwise composition when the
    call's subs carry one: every occurrence of the folded sequence's
    elements in the specialized closed form (init `seq[0]`, the pulled
    last term, the Sum body) is replaced by the transform of that
    element. Sound because the fold is linear with element-independent
    coefficients: folding mapped elements IS the mapped closed form."""
    from ._seq_common import ELEM_MAP_KEY
    subs = dict(subs)
    elem_map = subs.pop(ELEM_MAP_KEY, None)
    out = _fold_eval_at(fold, subs)
    if elem_map is None or fold.seq is None:
        return out
    mapper, scalar_args = elem_map

    def is_elem(e):
        return isinstance(e, sympy.Indexed) and e.base == fold.seq

    def mapped(e):
        return mapper(e, *scalar_args)

    if isinstance(out, tuple):
        return tuple(t.replace(is_elem, mapped) for t in out)
    return out.replace(is_elem, mapped)


def _fold_view(fold: "FoldLift") -> SeqLiftView:
    """`try_prove_seq`'s view of a `FoldLift`. `eval_f` goes through
    `_fold_eval_at`'s zero-collapse rebuild (never a plain `.subs`,
    which would leave `0**0` unresolved at a substituted coefficient of
    zero); the no-sequence shape presents an empty `seqs` dict, which
    is exactly what makes the shared quantifier code skip the
    `Seq(ℝ)` clause for it."""
    def with_domain_subs(view, subs, assumed):
        def _sub(v):
            return (tuple(t.subs(subs, simultaneous=True) for t in v)
                   if isinstance(v, tuple) else v.subs(subs, simultaneous=True))
        return _fold_view(replace(fold, other_params=assumed,
                                  expr=_sub(fold.expr), init_expr=fold.init_expr.subs(subs, simultaneous=True),
                                  coeff_item=fold.coeff_item.subs(subs, simultaneous=True),
                                  coeff_acc=fold.coeff_acc.subs(subs, simultaneous=True),
                                  acc_expr=fold.acc_expr.subs(subs, simultaneous=True),
                                  return_template=_sub(fold.return_template)))

    seqs = {fold.seq_param: fold.seq} if fold.seq_param is not None else {}
    lengths = {fold.seq_param: fold.length} if fold.seq_param is not None else {}
    return SeqLiftView(kind="fold", expr=fold.expr, seqs=seqs, lengths=lengths,
                       other_params=fold.other_params, sig_params=fold.sig_params,
                       opaque=fold.opaque,
                       eval_f=lambda subs: _fold_eval_mapped(fold, subs),
                       f_call_subs=lambda view, node, recurse:
                           _fold_f_call_subs(fold, node, recurse),
                       with_domain_subs=with_domain_subs)




def _is_lead_raise_guard(stmt) -> bool:
    """A statement of the exact shape `if cond: raise ...` (single-
    statement body, no else): a partiality guard, strippable ahead of
    the fold recognition."""
    return (isinstance(stmt, ast.If) and not stmt.orelse
            and len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Raise))


def _canonical_guard(stmt, param_names) -> tuple:
    """Intent:
        One stripped `if cond: raise Exc(...)` statement as the
        canonical guard pair `(sympy condition | None, exception name |
        None)`, the same shape lift_piecewise and lift_recurrence
        already emit, so every guard downstream is adjudicated by one
        machinery. A condition outside the converter's vocabulary
        stores None and stays permanently unexcludable (undecided).
    """
    from ._conditioned import _condition_to_sympy
    env = {p: sympy.Symbol(p, real=True) for p in param_names}
    try:
        cond = _condition_to_sympy(stmt.test, env)
    except Exception:
        cond = None
    exc = None
    raised = stmt.body[0].exc
    target = getattr(raised, "func", raised)
    if isinstance(target, ast.Name):
        exc = target.id
    return (cond, exc)


def _guard_avoided(guard, domain: dict, facts) -> "bool | None":
    """Intent:
        Whether the claim's declared domain provably avoids a
        canonical `(condition, exc)` guard: True = provably avoided
        (the condition is False everywhere on the box), False =
        provably reachable everywhere, None = can't tell (the caller
        declines the proof rather than risking one over a raising
        region). And/Or decompose recursively; the leaf decision is
        the shared relational-truth hull, the same tier the raise-
        region verdict runs first.
    """
    cond, _exc = guard
    if cond is None:
        return None
    return _cond_truth_over(cond, domain or {})


def _cond_truth_over(cond, domain: dict) -> "bool | None":
    if cond is sympy.true:
        return False   # fires everywhere: not avoided
    if cond is sympy.false:
        return True
    if isinstance(cond, sympy.Or):
        parts = [_cond_truth_over(a, domain) for a in cond.args]
        if all(p is True for p in parts):
            return True
        if any(p is False for p in parts):
            return False
        return None
    if isinstance(cond, sympy.And):
        parts = [_cond_truth_over(a, domain) for a in cond.args]
        if any(p is True for p in parts):
            return True
        if all(p is False for p in parts):
            return False
        return None
    from ._proof_support import _relational_truth_over_domain
    params = {str(sym): sym for sym in cond.free_symbols}
    try:
        truth = _relational_truth_over_domain(cond, domain, params)
    except TimeoutError:
        raise
    except Exception:
        return None
    if truth is False:
        return True    # provably never fires: avoided
    if truth is True:
        return False   # provably fires everywhere
    return None


def try_prove_fold(fn, facts, lhs_src: str, rhs_src: str, relation: str,
                   domain: dict | None = None, tolerance: float | None = None,
                   assumption=None) -> ProofResult:
    """try_prove()'s own fallback for a claim over a function lift_fold()
    recognizes; tried only after lift()/lift_conditioned() both fail to
    lift the body at all. The proof attempt itself is
    `_seq_common.try_prove_seq`, shared with the dot-product and
    general-sum shapes: domain assumptions on the fold's own scalar
    parameters (claim domain topped up by the docstring `Domain:` block)
    are what let a claim about the fold's coefficients (e.g. a
    sign-dependent bound) resolve when sympy would otherwise have no
    idea whether a scalar parameter like an EMA's `alpha` is positive."""
    fold = lift_fold(fn, facts)
    if fold is None:
        return _unliftable_result(fn, "and does not match the one "
                                      "recognized linear-fold shape either")
    for guard in fold.raise_guards:
        avoided = _guard_avoided(guard, domain or {}, facts)
        if avoided is not True:
            reach = ("provably reaches" if avoided is False
                     else "may reach")
            shown = "a raise guard" if guard[0] is None \
                else f"the raise guard `{guard[0]}`"
            return ProofResult(
                "undecided",
                sketch=f"the declared domain {reach} {shown}, the closed "
                       f"form is only the returning region's story; narrow "
                       f"the domain to exclude the guard, or state the "
                       f"raising region as its own raises(...) claim")
    certified = _convex_combination_certificate(
        fold, lhs_src, rhs_src, relation, domain or {})
    if certified is not None:
        return certified
    return try_prove_seq(_fold_view(fold), fn, lhs_src, rhs_src, relation,
                         domain=domain, tolerance=tolerance,
                         assumption=assumption)


def _min_max_side(src: str, seq_param: str, sig_params: list):
    """`"min"`/`"max"` when `src` is exactly that call over the folded
    sequence, `"f"` when it is the canonical positional f-call with
    every argument the bare signature parameter, else None."""
    import ast as _ast
    try:
        node = _ast.parse(src.strip(), mode="eval").body
    except SyntaxError:
        return None
    if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
            and node.func.id in ("min", "max") and len(node.args) == 1
            and isinstance(node.args[0], _ast.Name)
            and node.args[0].id == seq_param and not node.keywords):
        return node.func.id
    if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
            and node.func.id == "f" and not node.keywords
            and len(node.args) == len(sig_params)
            and all(isinstance(a, _ast.Name) and a.id == p
                    for a, p in zip(node.args, sig_params))):
        return "f"
    return None


def _convex_combination_certificate(fold, lhs_src: str, rhs_src: str,
                                    relation: str,
                                    domain: dict) -> "ProofResult | None":
    """Intent:
        The convex-combination certificate: a from-first-element fold
        whose update is `a*item + b*acc` with `a >= 0`, `b >= 0` and
        `a + b = 1` over the claim's domain keeps every accumulator
        state a convex combination of the elements seen, so
        `min(seq) <= f(...)` and `f(...) <= max(seq)` are proven
        outright, by induction on the fold, no closed-form reasoning
        about the sum required.

    Notes:
        Sound rules only: the weight conditions are checked over the
        declared domain (interval evaluation, then the nonneg
        certificate), and anything short of certainty returns None so
        the general machinery decides. Non-strict relations only; at
        a boundary weight (a = 0) the fold can sit exactly on the
        bound. The external-init mode is out: its states mix in a
        value that is not an element.
    """
    import sympy

    from ._proof_support import _interval_bounds, _nonneg_certificate

    if fold.mode != "from_first_element" or fold.seq_param is None:
        return None
    if relation not in ("<=", ">="):
        return None
    lhs = _min_max_side(lhs_src, fold.seq_param, fold.sig_params)
    rhs = _min_max_side(rhs_src, fold.seq_param, fold.sig_params)
    pair = (lhs, relation, rhs)
    lower = pair in (("min", "<=", "f"), ("f", ">=", "min"))
    upper = pair in (("f", "<=", "max"), ("max", ">=", "f"))
    if not (lower or upper):
        return None

    params = dict(fold.other_params)

    def nonneg(expr) -> bool:
        if expr.is_number:
            return bool(expr >= 0)
        try:
            box = _interval_bounds(expr, domain, params)
        except Exception:
            box = None
        if box is not None:
            lo = box.min if isinstance(box, sympy.AccumBounds) else box
            try:
                if bool(lo >= 0):
                    return True
            except TypeError:
                pass
        try:
            return _nonneg_certificate(expr, domain, params) is not None
        except Exception:
            return False

    a, b = fold.coeff_item, fold.coeff_acc
    if sympy.simplify(a + b - 1) != 0:
        return None
    if not (nonneg(a) and nonneg(b)):
        return None
    bound = "min" if lower else "max"
    side = "<=" if lower else ">="
    return ProofResult(
        "proven",
        sketch=(f"convex-combination certificate: the fold update is "
                f"({a})*item + ({b})*acc with both weights nonnegative "
                f"and summing to 1 on the declared domain, so every "
                f"accumulator state is a convex combination of the "
                f"elements seen and {bound}({fold.seq_param}) {side} "
                f"the result, by induction on the fold"))


class FoldFamily:
    """The `ClaimFamily` wrapper around `lift_fold`/`try_prove_fold`;
    the built-in registration mathema's linear-fold proof strategy goes
    through, same shape as `DotFamily`: a third party can register a
    different family under the same name, or a new one under its own,
    without touching `_prove.py`'s dispatch."""

    def can_handle(self, fn, facts, claim_name: str) -> bool:
        return lift_fold(fn, facts) is not None

    def routes(self) -> dict:
        return {"derive": self._derive}

    def _derive(self, fn, facts, lhs_src: str, rhs_src: str,
               relation: str, domain: dict | None = None,
               tolerance: float | None = None,
               assumption=None) -> ProofResult:
        return try_prove_fold(fn, facts, lhs_src, rhs_src, relation,
                              domain=domain, tolerance=tolerance,
                              assumption=assumption)


def _register_fold_family() -> None:
    """Register `FoldFamily` under "linear_fold", called explicitly by
    the package `__init__` alongside the other built-in family
    registrations, never as an import side effect of this module."""
    from .. import families as _families
    _families.register("linear_fold", FoldFamily())
