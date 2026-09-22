# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Dot products: `lift()`'s own gate refuses any function with a
sequence-typed parameter outright, unconditionally, `.fold` widens
that for one specific loop shape folding a *single* sequence. This
module widens it again, independently, for a different narrow shape
entirely: a whole function body that's nothing but a dot product
between exactly two of its own sequence parameters (`return np.dot(a,
b)`), lifted directly to `Sum(a[k]*b[k], (k, 0, L-1))` over one shared
symbolic length, no loop in the real source at all, so this is tried
independently of `.fold`, not as a further extension of it. Deliberately
narrow: no loop version of a hand-written dot product (`total +=
a[i]*b[i]`) is recognized here, only the literal `np.dot(...)` call,
see `.sum` for that still-open, harder generalization recognized
directly from loop structure. The one cluster with no dependency on
`._loop_shapes` at all; it pattern-matches a bare call, never walks a
loop header.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace

import sympy

from .._math_vocab import _call_name
from ..finite_sets import OpaqueRegistry
from ._base import _bind_params
from ._proof_support import ProofResult
from ._seq_common import (_unliftable_result, SeqLiftView,
                          positional_f_call_subs, subs_eval_f,
                          try_prove_seq)

# --- dot products: two sequence parameters reduced to one scalar -----------
#
# lift()'s own gate refuses any function with a sequence-typed parameter
# outright, unconditionally, lift_fold() widens that for one specific
# loop shape folding a *single* sequence. The function below widens it
# again, independently, for a different narrow shape entirely: a whole
# function body that's nothing but a dot product between exactly two of
# its own sequence parameters (`return np.dot(a, b)`), lifted directly to
# `Sum(a[k]*b[k], (k, 0, L-1))` over one shared symbolic length, no loop
# in the real source at all, so this is tried independently of lift_fold(),
# not as a further extension of it. Deliberately narrow: no loop version
# of a hand-written dot product (`total += a[i]*b[i]`) is recognized here,
# only the literal `np.dot(...)` call, see the real-world catalog's own
# `dot_product`/`polygon_area_shoelace` skips for that still-open, harder
# generalization (a shared-index fold over multiple sequences at once).

@dataclass
class DotLift:
    """A whole function body recognized as a dot product between exactly
    two of its own sequence parameters, lifted to `Sum(seq_a[k]*seq_b[k],
    (k, 0, length-1))`. `length` implicitly assumes `len(seq_a) ==
    len(seq_b)`, never verified symbolically (a real call with
    mismatched lengths raises before any claim about it is even checked,
    so this isn't a soundness gap in practice, just a disclosed
    assumption). Any other, non-sequence signature parameters bind
    ordinarily via `other_params`, the same role as `FoldLift`'s own."""
    expr: "sympy.Expr"
    seq_a: str
    seq_b: str
    ib_a: "sympy.IndexedBase"
    ib_b: "sympy.IndexedBase"
    length: "sympy.Symbol"
    other_params: dict
    sig_params: list = field(default_factory=list)
    unicode: str = ""
    latex: str = ""
    opaque: "OpaqueRegistry | None" = None


def _unwrap_scalar_cast(node: ast.AST) -> ast.AST:
    """`float(<expr>)`/`int(<expr>)` wrapping an already-numeric
    expression is a defensive return-type annotation in real code, not a
    mathematical operation, the same reasoning `_SYMPY_FUNCS["float"]`
    already applies inside an ordinary expression (see its own comment);
    this is the statement-level counterpart, unwrapping a single bare
    cast around `<expr>` before pattern-matching what's underneath it."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in ("float", "int") and len(node.args) == 1 and not node.keywords:
        return node.args[0]
    return node


def lift_dot(fn, facts) -> "DotLift | None":
    """Recognize a function whose entire body is `return np.dot(a, b)`
    (optionally wrapped in a bare `float(...)`/`int(...)` cast), where
    `a`/`b` are exactly the function's own two sequence-typed parameters,
    lifted directly to a symbolic `Sum`, no loop-recognition machinery
    involved at all. Any other body shape (a loop, a branch, extra
    statements, `np.dot` combined with something else, more or fewer
    than two sequence parameters) declines rather than guessing."""
    if facts.tree is None or facts.loops or facts.branch_count or facts.recursion:
        return None
    seq_params = [p for p in facts.params if facts.param_kinds.get(p) == "sequence"]
    if len(seq_params) != 2:
        return None
    from ._normalize import normalized_body
    body = normalized_body(fn, facts)
    if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
        return None
    call = _unwrap_scalar_cast(body[0].value)
    if not (isinstance(call, ast.Call) and _call_name(call) == "dot" and not call.keywords
            and len(call.args) == 2 and all(isinstance(a, ast.Name) for a in call.args)):
        return None
    arg_names = {a.id for a in call.args}
    if arg_names != set(seq_params):
        return None
    seq_a_name, seq_b_name = (a.id for a in call.args)

    other_params = {p: s for p, s in _bind_params(fn, facts)[0].items()
                    if p not in seq_params and not any(p.startswith(f"{s}.") for s in seq_params)}
    length = sympy.Symbol("L", integer=True, nonnegative=True)
    k = sympy.Symbol("k", integer=True)
    ib_a, ib_b = sympy.IndexedBase(seq_a_name), sympy.IndexedBase(seq_b_name)
    expr = sympy.Sum(ib_a[k] * ib_b[k], (k, 0, length - 1))
    from ..grammar import render_canonical
    return DotLift(expr=expr, seq_a=seq_a_name, seq_b=seq_b_name, ib_a=ib_a, ib_b=ib_b,
                   length=length, other_params=other_params, sig_params=list(facts.params),
                   unicode=render_canonical(expr)[0], latex=sympy.latex(expr),
                   opaque=OpaqueRegistry())


def _dot_view(dot: "DotLift") -> SeqLiftView:
    """`try_prove_seq`'s view of a `DotLift`: two named sequences
    sharing one symbolic length, positional `f(...)` matching, direct
    substitution for `eval_f`."""
    def with_domain_subs(view, subs, assumed):
        return _dot_view(replace(dot, other_params=assumed, expr=dot.expr.subs(subs, simultaneous=True)))

    return SeqLiftView(kind="dot product", expr=dot.expr,
                       seqs={dot.seq_a: dot.ib_a, dot.seq_b: dot.ib_b},
                       lengths={dot.seq_a: dot.length, dot.seq_b: dot.length},
                       other_params=dot.other_params, sig_params=dot.sig_params,
                       opaque=dot.opaque, eval_f=subs_eval_f(dot.expr),
                       f_call_subs=positional_f_call_subs,
                       with_domain_subs=with_domain_subs)


def try_prove_dot(fn, facts, lhs_src: str, rhs_src: str, relation: str,
                  domain: dict | None = None, tolerance: float | None = None,
                  assumption=None) -> ProofResult:
    """try_prove()'s own fallback for a claim over a function lift_dot()
    recognizes, tried only after lift()/lift_conditioned()/
    try_prove_fold() all fail to lift the body. The proof attempt itself
    is `_seq_common.try_prove_seq`, shared with the fold and general-sum
    shapes; the quantifier clause names both sequences."""
    dot = lift_dot(fn, facts)
    if dot is None:
        return _unliftable_result(fn, "and does not match the one "
                                      "recognized dot-product shape either")
    return try_prove_seq(_dot_view(dot), fn, lhs_src, rhs_src, relation,
                         domain=domain, tolerance=tolerance,
                         assumption=assumption)



class DotFamily:
    """The `ClaimFamily` wrapper around `lift_dot`/`try_prove_dot`,
    the built-in registration mathema's own dot-product proof strategy
    goes through, and the proof case for the claim-family extension
    point itself (`mathema.families`): a third party can register a
    different family under the same name, or an entirely new one under
    its own, without touching `_prove.py`'s dispatch."""

    def can_handle(self, fn, facts, claim_name: str) -> bool:
        return lift_dot(fn, facts) is not None

    def routes(self) -> dict:
        return {"derive": self._derive}

    def _derive(self, fn, facts, lhs_src: str, rhs_src: str,
               relation: str, domain: dict | None = None,
               tolerance: float | None = None,
               assumption=None) -> ProofResult:
        return try_prove_dot(fn, facts, lhs_src, rhs_src, relation,
                             domain=domain, tolerance=tolerance,
                             assumption=assumption)


def _register_dot_family() -> None:
    """Register `DotFamily` under "dot_product", called explicitly by
    the package `__init__` alongside the other built-in family
    registrations, never as an import side effect of this module."""
    from .. import families as _families
    _families.register("dot_product", DotFamily())

