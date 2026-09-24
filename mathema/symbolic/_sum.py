# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""General sum accumulation: nested loops, multiple sequences, no
telescoping needed at all. `.fold` closes the single-accumulator linear-
recurrence case; this module widens loop recognition again, for any
number of independent "pure sum" (coefficient-1) accumulators, each a
possibly-nested `Sum`, combined by the function's own return
expression, nested loops, `enumerate()`-based iteration, and a dot
product recognized directly from loop structure (not only via a literal
`np.dot(...)` call, see `.dot`) are all this shape once expanded.
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field, replace

import sympy

from ..finite_sets import OpaqueRegistry
from ._base import (
    NotSymbolic, _SymbolicArray, _bind_params, _expr_to_sympy,
)
from ._loop_shapes import classify_loop_header, _references_name, _update_rhs
from ._proof_support import ProofResult
from ._seq_common import (_unliftable_result, SeqLiftView,
                          positional_f_call_subs, subs_eval_f,
                          try_prove_seq)

# --- general sum accumulation: nested loops, multiple sequences, no --------
# --- telescoping needed at all ----------------------------------------------
#
# lift_fold() above requires the accumulator's own update to be affine in
# BOTH the loop item and the accumulator, because it needs that to
# telescope a `coeff_acc != 1` recurrence (EMA-style decay) into a closed
# form. But when `coeff_acc` is exactly 1; the update is `acc = acc +
# <anything>`, pure addition, never multiplying the accumulator by
# anything; there is nothing to telescope at all: `acc` after the loop
# is *structurally* `init + Sum(<that anything>, ...)`, true for ANY
# expression in the item/index, however nonlinear (`v*v`, `exp(z)`, a
# genuine dot product `a[i]*b[i]`). The functions below recognize that
# broader, much simpler shape independently of lift_fold(), tried only
# after it declines, never replacing it, and extend it to nested loops
# (a nested Sum, one level per loop) and multiple sequential accumulator
# loops (each independently summed, combined by the return expression,
# the same way lift_fold()'s own transformed-return extension works).

def _len_placeholder(seq_name: str) -> str:
    return f"__len_{seq_name}__"


class _ReplaceLenCalls(ast.NodeTransformer):
    """Rewrites `len(<seq_name>)` calls, for any `seq_name` in
    `seq_params`, to a bare reference to that sequence's own placeholder
    name, the multi-sequence sibling of lift_fold()'s own
    `_ReplaceFoldLenCall` (kept separate rather than shared, since that
    one is already in place and tested for the single-sequence case; no
    reason to risk it for this addition). Always run against a copy, per
    lift_sum()'s own docstring; `facts.tree` is shared with every other
    analysis over this function."""
    def __init__(self, seq_params):
        self.seq_params = set(seq_params)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if isinstance(node.func, ast.Name) and node.func.id == "len" \
                and len(node.args) == 1 and isinstance(node.args[0], ast.Name) \
                and node.args[0].id in self.seq_params and not node.keywords:
            return ast.copy_location(
                ast.Name(id=_len_placeholder(node.args[0].id), ctx=ast.Load()), node)
        return self.generic_visit(node)


@dataclass
class SumLift:
    """N independent "pure sum" accumulators (`acc = acc + <expr>`, never
    multiplying the accumulator by anything), each closed to a
    (possibly nested) `sympy.Sum` with no telescoping needed at all,
    combined by the function's own final return expression the same way
    lift_fold()'s transformed-return extension works. `seqs`/`lengths`
    map every sequence parameter this function's loops actually walk to
    its own `IndexedBase`/symbolic length, shared across every piece
    and every nesting level that touches the same sequence, so a claim
    referencing that sequence's length only ever means one thing.
    `pieces` holds each accumulator's own already-fully-closed value
    (`init + Sum(...)`, keyed by accumulator name), unlike FoldLift,
    there's no separate template/zero-collapse machinery needed here,
    since a coefficient-1 accumulator has no telescoping-related
    pathology to guard against in the first place."""
    expr: "sympy.Expr | tuple"
    pieces: dict            # acc_name -> sympy.Expr (already fully closed)
    seqs: dict               # seq_param name -> sympy.IndexedBase
    lengths: dict             # seq_param name -> sympy.Symbol
    other_params: dict
    sig_params: list = field(default_factory=list)
    unicode: str = ""
    latex: str = ""
    opaque: "OpaqueRegistry | None" = None
    raise_guards: list = field(default_factory=list)



def _recognize_sum_piece(acc_name: str, stmt: ast.AST, env: dict, length_syms: dict,
                         seq_ibs: dict, seq_params: set, opaque: "OpaqueRegistry | None" = None):
    """Recursively recognize one accumulator's own loop nest: `stmt` is
    either a further nested `ast.For` (one level deeper, recurse) or the
    terminal accumulator-update statement. Returns the (possibly nested)
    `Sum` expression for this accumulator's own contribution, not yet
    including its own initial value, see lift_sum(), or `None` if
    anything along the way doesn't match (a loop header shape
    classify_loop_header doesn't recognize, more than one statement at
    any level, an update that isn't purely additive in the accumulator,
    or an update expression that isn't liftable at all)."""
    if isinstance(stmt, ast.For):
        if len(stmt.body) != 1:
            return None
        classified = classify_loop_header(stmt, seq_params)
        if classified is None:
            return None
        kind, seq_name, item_name, idx_name = classified
        if kind == "scalar_index":
            # `seq_name` is the raw trip-count AST node here, not a
            # sequence's name, no IndexedBase, no fresh opaque length
            # symbol; lift it directly against the current env (an
            # ordinary scalar parameter, or an affine/any other
            # expression built from one, e.g. `n + 1`).
            try:
                length = _expr_to_sympy(seq_name, env, opaque=opaque)
            except NotSymbolic:
                return None
            if isinstance(length, (tuple, _SymbolicArray)):
                return None
        else:
            if seq_name not in length_syms:
                length_syms[seq_name] = sympy.Symbol(f"L_{seq_name}", integer=True, nonnegative=True)
            if seq_name not in seq_ibs:
                seq_ibs[seq_name] = sympy.IndexedBase(seq_name)
            length = length_syms[seq_name]
        idx_sym = sympy.Symbol(idx_name or f"_i{id(stmt) % 10000}", integer=True)
        new_env = dict(env)
        if kind in ("item", "enumerate"):
            new_env[item_name] = seq_ibs[seq_name][idx_sym]
        if kind in ("index", "enumerate", "scalar_index"):
            new_env[idx_name] = idx_sym
        inner = _recognize_sum_piece(acc_name, stmt.body[0], new_env, length_syms,
                                     seq_ibs, seq_params, opaque)
        if inner is None:
            return None
        if kind == "scalar_index":
            # range(n) runs max(n, 0) times: a sum up to n - 1 with
            # n < 0 would follow the reversed-range convention instead
            length = sympy.Max(length, 0)
        return sympy.Sum(inner, (idx_sym, 0, length - 1))
    if isinstance(stmt, ast.If) and len(stmt.body) == 1 \
            and len(stmt.orelse) <= 1:
        # a conditional accumulator update sums the exact Piecewise:
        # `if v > 0: total += v` gives ((expr, cond), (0, True)), and
        # a single else-branch update gives ((expr, cond),
        # (else_expr, True)), the absolute-sum shape. Only when the
        # condition never reads the accumulator itself (that is a
        # genuine recurrence, not a sum), and only terminal updates
        # directly under the branches (a nested loop stays out)
        cond_names = {n.id for n in ast.walk(stmt.test)
                      if isinstance(n, ast.Name)}
        if acc_name in cond_names:
            return None
        from ._base import _cond_to_sympy
        try:
            cond = _cond_to_sympy(stmt.test, env, opaque=opaque)
        except NotSymbolic:
            return None
        inner = _recognize_sum_piece(acc_name, stmt.body[0], env,
                                     length_syms, seq_ibs, seq_params,
                                     opaque)
        if inner is None or isinstance(inner, sympy.Sum):
            return None
        otherwise = sympy.S.Zero
        if stmt.orelse:
            otherwise = _recognize_sum_piece(acc_name, stmt.orelse[0], env,
                                             length_syms, seq_ibs,
                                             seq_params, opaque)
            if otherwise is None or isinstance(otherwise, sympy.Sum):
                return None
        return sympy.Piecewise((inner, cond), (otherwise, sympy.true))
    upd_rhs = _update_rhs(stmt, acc_name)
    if upd_rhs is None:
        return None
    acc_sym = sympy.Symbol(acc_name, real=True)
    full_env = dict(env)
    full_env[acc_name] = acc_sym
    try:
        rhs = _expr_to_sympy(upd_rhs, full_env, opaque=opaque)
    except NotSymbolic:
        return None
    if isinstance(rhs, tuple):
        return None
    if sympy.diff(rhs, acc_sym) != 1:
        return None   # not purely additive in the accumulator, e.g. acc*item
    residual = sympy.expand(rhs - acc_sym)
    if residual.has(acc_sym):
        return None   # acc appears somewhere other than the +1 coefficient itself
    return residual


def _safe_simplify(expr: "sympy.Expr") -> "sympy.Expr":
    """`sympy.simplify()`, tolerating a real, confirmed sympy internal
    bug this module's own nested-Sum expressions can trigger: a `Sum`
    whose summand itself contains another, already-simplified `Sum`
    (e.g. a two-pass variance, the second pass's summand references
    the first pass's own `Sum(...)/L` mean) can raise a bare
    `StopIteration` deep inside `sympy.simplify.simplify.sum_combine`'s
    `__refactor` (`next(x for x in args if isinstance(x, Sum))` with no
    matching element) rather than declining to simplify gracefully.
    Simplification is cosmetic here, never required for correctness;
    the unsimplified expression is exactly as sound to prove against,
    so this falls back to it rather than letting a sympy-internal
    exception surface as if lift_sum() itself had failed."""
    from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    try:
        return _with_timeout(lambda: sympy.simplify(expr),
                             FAST_TIMEOUT_SECONDS)
    except Exception:
        return expr


def _lift_sum_scalar(node: ast.AST, env: dict, seq_params: set, length_syms: dict,
                     opaque: "OpaqueRegistry | None" = None):
    """Lift a scalar (non-loop) statement's value against `env`,
    `len(<seq>)` for any of `seq_params` resolves to that sequence's own
    symbolic length first (creating it if this is the first time that
    sequence's length is needed), the same way a fold's own transformed
    return already resolves it (see _ReplaceLenCalls). Used both for an
    accumulator's own initial value and for an ordinary scalar local
    between two accumulator passes (`mean = total / len(xs)`)."""
    rewritten = _ReplaceLenCalls(seq_params).visit(copy.deepcopy(node))
    call_env = dict(env)
    for seq_name in seq_params:
        length_syms.setdefault(seq_name, sympy.Symbol(f"L_{seq_name}", integer=True, nonnegative=True))
        call_env[_len_placeholder(seq_name)] = length_syms[seq_name]
    return _expr_to_sympy(rewritten, call_env, opaque=opaque)


def lift_sum(fn, facts) -> "SumLift | None":
    """Recognize a function whose body is a sequence of statements, each
    either an ordinary scalar local (`mean = total / len(xs)`, lifted
    immediately and made available to whatever follows) or the start of
    an accumulator pass, `acc = <expr not depending on any sequence
    or itself>` immediately followed by a `for` loop (possibly a nested
    chain of them, see the module comment above) whose only statement is
    an additive update to that same accumulator; ending in a `return`
    that combines whatever's in scope by then. This is more flexible
    than a rigid `[init, loop, init, loop, ..., return]` alternation
    specifically so a genuine two-pass shape (a mean computed first,
    then a second pass over the same sequence using it) is recognized:
    the intermediate scalar step is just another statement in the same
    sequential walk, not a special case.

    Declines (returns `None`, never guesses) on a branch outside a
    loop body, recursion, an accumulator initial value that
    depends on any sequence parameter or its own name (only an
    "external" initial value is recognized here, lift_fold() already
    covers "starts at the sequence's own first element" for the
    single-loop case), a loop header shape classify_loop_header
    doesn't recognize, or an update that isn't purely additive in its
    own accumulator."""
    if facts.tree is None or facts.recursion:
        return None
    if not facts.loops:
        return None
    # a guarded loop is not refused up front: a conditional update
    # whose condition reads only the item/index lifts as an exact
    # Piecewise summand (see _recognize_sum_piece); anything else
    # falls out of recognition naturally
    seq_params = {p for p in facts.params if facts.param_kinds.get(p) == "sequence"}
    # a sequence parameter is no longer required at all, a bare
    # `for i in range(n):` loop (n an ordinary scalar parameter, no
    # sequence involved) is exactly classify_loop_header's own
    # "scalar_index" shape, tried the same way as every other loop
    # header below; seq_params staying empty simply means no "item"/
    # "index"/"enumerate" shape can ever match, not that lift_sum()
    # itself should refuse to look.

    from ._fold import _canonical_guard, _is_lead_raise_guard
    from ._normalize import normalized_body
    body = normalized_body(fn, facts)
    # leading `if cond: raise` guards are the partiality contract, not
    # a reason to refuse, stripped here, carried on the lift in the
    # canonical (condition, exc) form, gated by try_prove_sum exactly
    # as the fold shape gates its own
    raise_guards: list = []
    while body and _is_lead_raise_guard(body[0]):
        raise_guards.append(_canonical_guard(body[0], facts.params))
        body = body[1:]
    if any(isinstance(node, ast.If)
           for st in body for node in ast.walk(st)
           if not any(node in ast.walk(loop)
                      for st2 in body for loop in ast.walk(st2)
                      if isinstance(loop, ast.For))):
        # a remaining branch OUTSIDE every loop body refuses; an `if`
        # inside a loop is the conditional-update shape the recognizer
        # itself adjudicates (an exact Piecewise summand, or a decline)
        return None
    if len(body) < 3 or not isinstance(body[-1], ast.Return) or body[-1].value is None:
        return None
    return_stmt = body[-1]
    stmts = body[:-1]

    other_params = {p: s for p, s in _bind_params(fn, facts)[0].items()
                    if p not in seq_params and not any(p.startswith(f"{s}.") for s in seq_params)}
    length_syms: dict = {}
    seq_ibs = {p: sympy.IndexedBase(p) for p in seq_params}
    opaque = OpaqueRegistry()
    # every sequence parameter is bound to its own IndexedBase from the
    # start, in every env this recognizer builds, not just the ones a
    # given loop directly iterates, so an index-bound loop can
    # subscript *any* of them (`a[i]`, `b[i]`), which is exactly what
    # makes a hand-written dot product recognizable at all.
    env = {**other_params, **seq_ibs}

    pieces: dict = {}
    acc_names: list = []
    expr = _walk_sum_statements(stmts, return_stmt, env, other_params,
                                seq_params, seq_ibs, length_syms, opaque,
                                pieces, acc_names)
    if expr is None:
        return None
    from ..grammar import render_canonical
    return SumLift(expr=expr, pieces=pieces, seqs=seq_ibs, lengths=length_syms,
                   other_params=other_params, sig_params=list(facts.params), opaque=opaque,
                   unicode=render_canonical(expr)[0], latex=sympy.latex(expr),
                   raise_guards=raise_guards)




def _walk_sum_statements(stmts, return_stmt, env, other_params, seq_params,
                         seq_ibs, length_syms, opaque, pieces, acc_names):
    """Intent:
        The statement walk shared by `lift_sum` and the piecewise leaf
        lifter: accumulator passes, straight-line locals, epilogue
        updates, and the final return, closed against `env`. Returns
        the closed expression (a tuple for tuple returns), or None on
        any unrecognized statement; with `return_stmt=None` (prefix
        mode) it returns the walked env instead, for a caller that
        continues its own walk past the loops. `pieces`/`acc_names`
        are output lists the caller may inspect.
    """
    def _apply_aug_op(op, current, delta):
        if isinstance(op, ast.Add):
            return current + delta
        if isinstance(op, ast.Sub):
            return current - delta
        if isinstance(op, ast.Mult):
            return current * delta
        if isinstance(op, ast.Div):
            return current / delta
        return None

    i = 0

    while i < len(stmts):
        stmt = stmts[i]
        if (isinstance(stmt, ast.AugAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.target.id in env
                and stmt.target.id not in other_params
                and stmt.target.id not in seq_params):
            # an epilogue update on a completed accumulator or local
            # (`price += face_value / (1 + y)**n` after the coupon
            # loop): plain sequential dataflow, applied to the lifted
            # value it already has
            name = stmt.target.id
            try:
                delta = _lift_sum_scalar(stmt.value, env, seq_params,
                                         length_syms, opaque)
            except NotSymbolic:
                return None
            if isinstance(delta, tuple):
                return None
            updated = _apply_aug_op(stmt.op, env[name], delta)
            if updated is None:
                return None
            env[name] = _safe_simplify(updated)
            if name in pieces:
                pieces[name] = env[name]
            i += 1
            continue
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            return None
        name = stmt.targets[0].id
        if name in seq_params or name in other_params:
            # refuses reassigning a sequence or scalar signature
            # parameter, conservative on purpose, same reasoning
            # _unmodified_params() already applies elsewhere. A
            # completed LOCAL or accumulator may be reassigned: that
            # is ordinary sequential dataflow, lifted against the
            # value it has right here.
            return None
        starts_accumulator = (i + 1 < len(stmts) and isinstance(stmts[i + 1], ast.For)
                              and not _references_name(stmt.value, name)
                              and not any(_references_name(stmt.value, s) for s in seq_params))
        if starts_accumulator:
            try:
                init_expr = _lift_sum_scalar(stmt.value, env, seq_params, length_syms, opaque)
            except NotSymbolic:
                return None
            if isinstance(init_expr, tuple):
                return None
            summed = _recognize_sum_piece(name, stmts[i + 1], env, length_syms,
                                          seq_ibs, seq_params, opaque)
            if summed is None:
                return None
            value = _safe_simplify(init_expr + summed)
            pieces[name] = value
            acc_names.append(name)
            env[name] = value
            i += 2
            continue
        # an ordinary scalar local, not the start of a recognized
        # accumulator pass; lift it immediately and make it available
        # to whatever statement comes next (including a later
        # accumulator's own init/update, or the final return).
        try:
            value = _lift_sum_scalar(stmt.value, env, seq_params, length_syms, opaque)
        except NotSymbolic:
            return None
        if isinstance(value, tuple):
            return None
        env[name] = value
        i += 1


    if not acc_names:   # no accumulator pass recognized at all
        return None
    if return_stmt is None:
        # prefix mode (close_loop_prefix): the caller wants the walked
        # environment itself, to continue its own walk past the loops
        return env
    try:
        expr = _lift_sum_scalar(return_stmt.value, env, seq_params,
                                length_syms, opaque)
    except NotSymbolic:
        return None
    return (tuple(_safe_simplify(t) for t in expr)
            if isinstance(expr, tuple) else _safe_simplify(expr))


def closed_loop_region(fn, facts, stmts, env0: dict):
    """Intent:
        One branch region containing a loop, closed to a scalar
        expression: the piecewise lifter's leaf delegate. `stmts` must
        end in a plain `return`; `env0` carries the scalar parameters
        and any locals accumulated on the path. Scalar shapes only
        (no sequence parameters) in this slice; anything unrecognized
        returns None, never a guess.
    """
    if not stmts or not isinstance(stmts[-1], ast.Return) \
            or stmts[-1].value is None:
        return None
    pieces: dict = {}
    acc_names: list = []
    expr = _walk_sum_statements(list(stmts[:-1]), stmts[-1], dict(env0),
                                dict(env0), set(), {}, {}, OpaqueRegistry(),
                                pieces, acc_names)
    if expr is None or isinstance(expr, tuple):
        return None
    # a scalar region's Sums are all over concrete range bounds, so
    # they evaluate outright; collapsing here keeps the Piecewise
    # arms in plain closed form for the deciders
    try:
        from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
        expr = _with_timeout(lambda: _safe_simplify(expr.doit(deep=True)),
                             FAST_TIMEOUT_SECONDS)
    except Exception:
        pass
    return expr


def close_loop_prefix(fn, facts, stmts, env0: dict) -> "dict | None":
    """Intent:
        A loop-bearing statement prefix (inits, loops, epilogue
        updates, no branching, no return) closed into an updated
        environment, so a caller's own walk continues past the loops:
        the loop-then-branch shape's missing half. Scalar shapes only,
        like closed_loop_region; None on anything unrecognized.
    """
    if not stmts:
        return dict(env0)
    pieces: dict = {}
    acc_names: list = []
    env = _walk_sum_statements(list(stmts), None, dict(env0),
                               dict(env0), set(), {}, {}, OpaqueRegistry(),
                               pieces, acc_names)
    if env is None:
        return None
    from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    for name in acc_names:
        try:
            env[name] = _with_timeout(
                lambda v=env[name]: _safe_simplify(v.doit(deep=True)),
                FAST_TIMEOUT_SECONDS)
        except Exception:
            pass
    return env


def _sum_view(s: "SumLift") -> SeqLiftView:
    """`try_prove_seq`'s view of a `SumLift`, the general case every
    other sequence shape is a specialization of: however many named
    sequences `s.seqs` holds, positional `f(...)` matching, direct
    substitution for `eval_f`."""
    def with_domain_subs(view, subs, assumed):
        def _sub(v):
            return (tuple(t.subs(subs, simultaneous=True) for t in v)
                   if isinstance(v, tuple) else v.subs(subs, simultaneous=True))
        return _sum_view(replace(s, other_params=assumed, expr=_sub(s.expr),
                                 pieces={n: p.subs(subs, simultaneous=True) for n, p in s.pieces.items()}))

    return SeqLiftView(kind="sum", expr=s.expr, seqs=s.seqs, lengths=s.lengths,
                       other_params=s.other_params, sig_params=s.sig_params,
                       opaque=s.opaque, eval_f=subs_eval_f(s.expr),
                       f_call_subs=positional_f_call_subs,
                       with_domain_subs=with_domain_subs)


def try_prove_sum(fn, facts, lhs_src: str, rhs_src: str, relation: str,
                  domain: dict | None = None, tolerance: float | None = None,
                  assumption=None) -> ProofResult:
    """try_prove()'s own fallback for a claim over a function lift_sum()
    recognizes, tried only after lift()/lift_conditioned()/
    try_prove_fold() all fail. The proof attempt itself is
    `_seq_common.try_prove_seq`, shared with the fold and dot-product
    shapes; the quantifier clause names every sequence lift_sum()
    actually used, not a fixed one or two."""
    s = lift_sum(fn, facts)
    if s is None:
        return _unliftable_result(fn, "and does not match the "
                                      "recognized fold, dot-product, or "
                                      "general-sum loop shapes either")
    from ._fold import _guard_avoided
    for guard in s.raise_guards:
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
    return try_prove_seq(_sum_view(s), fn, lhs_src, rhs_src, relation,
                         domain=domain, tolerance=tolerance,
                         assumption=assumption)


class SumFamily:
    """The `ClaimFamily` wrapper around `lift_sum`/`try_prove_sum`,
    the built-in registration for the general-sum proof strategy, same
    extension shape as `DotFamily`/`FoldFamily`."""

    def can_handle(self, fn, facts, claim_name: str) -> bool:
        return lift_sum(fn, facts) is not None

    def routes(self) -> dict:
        return {"derive": self._derive}

    def _derive(self, fn, facts, lhs_src: str, rhs_src: str,
               relation: str, domain: dict | None = None,
               tolerance: float | None = None,
               assumption=None) -> ProofResult:
        return try_prove_sum(fn, facts, lhs_src, rhs_src, relation,
                             domain=domain, tolerance=tolerance,
                             assumption=assumption)


def _register_sum_family() -> None:
    """Register `SumFamily` under "general_sum", called explicitly by
    the package `__init__` alongside the other built-in family
    registrations, never as an import side effect of this module."""
    from .. import families as _families
    _families.register("general_sum", SumFamily())
