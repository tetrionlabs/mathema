# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The shared machinery behind every sequence-shaped lift's proof
attempt. `_fold`/`_dot`/`_sum` each recognize a different loop/body
shape, but from the moment a shape is lifted, everything else is one
algorithm: convert the claim law against the lift's own sequences and
scalars (`_seq_law_to_sympy`), inject domain assumptions, run
`_prove_relation`, and state the quantifier. That algorithm used to
exist as three hand-synchronized copies (byte-identical error strings
included); it lives here once, parameterized by a small `SeqLiftView`
each shape builds from its own lift record.

What stays per-shape, as view hooks:

- `f_call_subs`: the claim-text `f(...)` argument convention (fold
  requires the folded sequence as the first argument; dot/sum match
  positionally against the real signature) and its validation errors.
- `eval_f`: how the closed form is specialized under a scalar
  substitution (fold rebuilds via `_fold_eval_at`'s zero-collapse;
  dot/sum substitute directly).
- `with_domain_subs`: which fields of the underlying lift record the
  domain-assumption substitution must rewrite.
- the shape's own unliftable-statement wording (`kind`).
"""
from __future__ import annotations

import ast
import contextvars
from dataclasses import dataclass, replace
from typing import Callable

import sympy

from ..domain import InvalidDomain

from .._math_vocab import _BINOPS, _SYMPY_FUNCS, _call_name
from ..finite_sets import is_opaque_eligible
from ._base import (NotSymbolic, _exact_numeric_literal, _literal_int_index,
                    _unsupported_call_message)
from ._proof_support import (ProofResult, _domain_assumptions, _free_names,
                             _prove_relation, _quantifier_clause)


#: Elementwise sequence transforms the seq law lowering composes
#: through a fold's closed form, keyed by the bound function's dotted
#: path: `f(g(xs, c))` with g bound to one of these substitutes
#: `seq[k] -> map(seq[k], c)` in the closed form rather than needing
#: g to lift. Index-shuffling helpers (reverse_seq) are NOT here: they
#: move elements between positions, which is a different composition.
ELEMENTWISE_TRANSFORMS: dict = {
    "mathema.f.scale_seq": lambda elem, c: c * elem,
    "mathema.f.shift_seq": lambda elem, c: elem + c,
}

#: The claim's bound-function names that resolved to elementwise
#: transforms, set by try_prove for the duration of its loop-shape
#: fallback: the family route signature is published interface, so
#: this rides call-scoped context instead of a new parameter.
_ACTIVE_TRANSFORMS: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_seq_transforms", default=None)

#: The sentinel key an f_call_subs uses to hand eval_f an elementwise
#: map: value is (mapper, (scalar sympy args...)).
ELEM_MAP_KEY = "__mathema_elem_map__"


def transform_bindings(funcs: dict) -> dict:
    """The subset of a claim's resolved `funcs` that are registered
    elementwise transforms: law name -> mapper. Matching is by the
    callable's own dotted identity, so `let g = mathema.f.scale_seq`
    and a live-callable binding behave identically."""
    out = {}
    for name, gfn in (funcs or {}).items():
        mod = getattr(gfn, "__module__", None)
        qual = getattr(gfn, "__qualname__", None)
        mapper = ELEMENTWISE_TRANSFORMS.get(f"{mod}.{qual}")
        if mapper is not None:
            out[name] = mapper
    return out


@dataclass
class SeqLiftView:
    """One sequence-shaped lift, as `try_prove_seq`/`_seq_law_to_sympy`
    consume it, built by each shape from its own lift record. `seqs`
    maps every folded sequence parameter to its `IndexedBase` and
    `lengths` to its symbolic length (shared symbols allowed: a dot
    product's two sequences map to one `L`)."""
    kind: str                    # "fold" | "dot product" | "sum", for sketch text
    expr: "sympy.Expr | tuple"
    seqs: dict
    lengths: dict
    other_params: dict
    sig_params: list
    opaque: object
    eval_f: Callable             # (subs) -> specialized closed form
    f_call_subs: Callable        # (node, recurse) -> {sympy sym: value}
    with_domain_subs: Callable   # (subs, assumed_params) -> new SeqLiftView
    unliftable_sketch: str = ""


def _unliftable_result(fn, shape_tail: str) -> ProofResult:
    """The shared unliftable ProofResult for the sequence shapes: names
    the LIKELY reason from derivability_report (the first blocking
    construct found; the root cause can sit deeper) with one plain
    help sentence, falling back to the generic four-causes wording when
    no summary is available. Full diagnostic depth stays in
    `mathema audit --deriv-report`."""
    from ..inventory import unliftable_summary
    try:
        summary = unliftable_summary(fn)
    except Exception:
        summary = None
    if summary:
        return ProofResult("unliftable",
                           sketch=f"function body is not derivable, {summary}")
    return ProofResult("unliftable",
                       sketch="function body is not derivable in v1: contains "
                              "a loop, branch, recursion, or a non-scalar "
                              f"parameter, {shape_tail}")


def positional_f_call_subs(view: SeqLiftView, node: ast.Call, recurse) -> dict:
    """The dot/sum `f(...)` convention: positional arguments matched
    against the real signature in order; a sequence parameter's argument
    must be a bare reference to it, a scalar's genuinely substitutes."""
    if node.keywords or len(node.args) != len(view.sig_params):
        raise NotSymbolic(f"f(...) must be called with exactly "
                          f"{len(view.sig_params)} argument(s), matching "
                          f"{view.sig_params}: {ast.unparse(node)!r}")
    subs = {}
    for p, a in zip(view.sig_params, node.args):
        if p in view.seqs:
            if not (isinstance(a, ast.Name) and a.id == p):
                raise NotSymbolic(f"f(...)'s argument for {p!r} must be a "
                                  f"bare reference to it: {ast.unparse(node)!r}")
            continue
        # a scalar (non-sequence) parameter, unlike a sequence arg
        # above, this one genuinely substitutes: f(a1, d, 3) and
        # f(a1, d, n) must differ when n is bound to 3.
        subs[view.other_params[p]] = recurse(a)
    return subs


def subs_eval_f(expr):
    """The dot/sum `eval_f`: specialize the closed form by direct
    substitution (simultaneous, tuple-aware)."""
    def eval_f(subs):
        if not subs:
            return expr
        return (tuple(t.subs(subs, simultaneous=True) for t in expr)
               if isinstance(expr, tuple) else expr.subs(subs, simultaneous=True))
    return eval_f


def _seq_law_to_sympy(node: ast.AST, view: SeqLiftView, aux: dict):
    """Convert one claim-law expression node to sympy against a
    sequence-shaped lift: a deliberately narrow grammar, a literal
    index (`x[0]`, `x[-1]`) or `len(...)` against a named sequence,
    scalars by name, `f(...)` per the view's own argument convention,
    and the ordinary math vocabulary. Anything outside it raises
    `NotSymbolic`, the same convention `_law_to_sympy` uses."""
    def recurse(n):
        return _seq_law_to_sympy(n, view, aux)

    if isinstance(node, ast.Expression):
        return recurse(node.body)
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, bool) and isinstance(node.value, (int, float)):
            return _exact_numeric_literal(node.value)
        if view.opaque is not None and is_opaque_eligible(node.value):
            return view.opaque.register(node.value)
        raise NotSymbolic(f"non-numeric constant {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in view.seqs:
            raise NotSymbolic(f"{node.id!r} (a sequence) has no single scalar "
                              "value outside indexing or an f(...) call")
        if node.id in view.other_params:
            return view.other_params[node.id]
        return aux.setdefault(node.id, sympy.Symbol(node.id, real=True))
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
            and node.value.id in view.seqs:
        ib = view.seqs[node.value.id]
        length = view.lengths[node.value.id]
        idx = _literal_int_index(node.slice)
        if idx == -1:
            return ib[length - 1]
        if idx is not None and idx >= 0:
            return ib[idx]
        raise NotSymbolic(f"index into {node.value.id!r} must be a nonnegative "
                          f"literal or -1: {ast.unparse(node)!r}")
    if isinstance(node, ast.UnaryOp):
        v = recurse(node.operand)
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.UAdd):
            return v
        raise NotSymbolic(f"unsupported unary op in {ast.unparse(node)!r}")
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise NotSymbolic(f"unsupported operator in {ast.unparse(node)!r}")
        return op(recurse(node.left), recurse(node.right))
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "len" \
                and len(node.args) == 1 and isinstance(node.args[0], ast.Name) \
                and node.args[0].id in view.seqs:
            return view.lengths[node.args[0].id]
        if (isinstance(node.func, ast.Name) and node.func.id == "dim"
                and len(node.args) == 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in view.seqs
                and isinstance(node.args[1], ast.Constant)):
            axis = node.args[1].value
            if axis == 0:
                return view.lengths[node.args[0].id]
            raise NotSymbolic(
                f"{node.args[0].id!r} is a one-dimensional sequence; "
                f"axis {axis!r} does not exist ({ast.unparse(node)!r})")
        if isinstance(node.func, ast.Name) and node.func.id in ("Sum", "Prod"):
            # Sum(f(4, j), j, 0, 4): the claim wraps calls to the
            # lifted function in a symbolic sum/product; the index is
            # a fresh integer dummy registered BEFORE the summand
            # recursion, so f's own closed form specializes at the
            # symbolic index (same convention _law_to_sympy uses)
            if len(node.args) != 4:
                raise NotSymbolic(
                    f"{node.func.id}(...) needs exactly (expr, var, lo, hi): "
                    f"{ast.unparse(node)!r}")
            var_node = node.args[1]
            if not isinstance(var_node, ast.Name):
                raise NotSymbolic(
                    f"{node.func.id}(...)'s index must be a bare name: "
                    f"{ast.unparse(node)!r}")
            var_sym = aux.setdefault(var_node.id,
                                     sympy.Symbol(var_node.id, integer=True))
            inner = recurse(node.args[0])
            lo, hi = recurse(node.args[2]), recurse(node.args[3])
            if any(isinstance(v, tuple) for v in (inner, lo, hi)):
                raise NotSymbolic(f"cannot sum a tuple value: "
                                  f"{ast.unparse(node)!r}")
            op = sympy.summation if node.func.id == "Sum" else sympy.product
            return op(inner, (var_sym, lo, hi))
        name = _call_name(node)
        if name == "f":
            subs = view.f_call_subs(view, node, recurse)
            return view.eval_f(subs) if subs else view.expr
        if name in _SYMPY_FUNCS:
            args = [recurse(a) for a in node.args]
            if any(isinstance(a, tuple) for a in args):
                raise NotSymbolic(f"cannot pass a tuple value to a function "
                                  f"call: {ast.unparse(node)!r}")
            return _SYMPY_FUNCS[name](*args)
        raise NotSymbolic(_unsupported_call_message(node))
    raise NotSymbolic(f"unsupported syntax {ast.unparse(node)!r}")


def _termwise_sum_decide(lhs, rhs, relation: str, domain: dict,
                         view: "SeqLiftView") -> "ProofResult | None":
    """Intent:
        The each-term rung for a sign claim over a symbolic-length sum:
        `init + Sum(smnd, (i, 0, L-1)) >= 0` is proven when the
        summand has the required sign for EVERY element value in the
        declared element domain and the non-sum remainder does too;
        sympy cannot see this through a symbolic length, but the
        summand question is an ordinary scalar decision. Strict
        orderings additionally need one provably nonempty sum (a trip
        count with a positive lower bound); `None` when the shape or
        any sub-decision does not settle.

    Notes:
        Each Indexed element is replaced by a fresh real symbol bounded
        by its sequence's own declared element domain, so the summand
        decision runs through the ordinary decider (Piecewise branches
        decided one by one when it stalls). Sound for >=/<=/>/<; an
        equality has no termwise reading here.
    """
    import sympy

    if relation not in (">=", "<=", ">", "<"):
        return None
    diff = sympy.expand(lhs - rhs)
    if relation in ("<=", "<"):
        diff = -diff
        want_strict = relation == "<"
    else:
        want_strict = relation == ">"
    terms = diff.args if isinstance(diff, sympy.Add) else (diff,)
    sums: list = []
    rest: list = []

    def _as_sum(t):
        # a scalar coefficient rides into the summand (2*Sum(a[i]) is
        # Sum(2*a[i])), so a mapped/scaled sum gets the same termwise
        # reading a bare one does
        if isinstance(t, sympy.Sum):
            return t
        if isinstance(t, sympy.Mul):
            sums_in = [f for f in t.args if isinstance(f, sympy.Sum)]
            others = [f for f in t.args if not isinstance(f, sympy.Sum)]
            if len(sums_in) == 1 and all(
                    getattr(f, "is_number", False) for f in others):
                inner = sums_in[0]
                coeff = sympy.Mul(*others) if others else sympy.Integer(1)
                return sympy.Sum(coeff * inner.function, *inner.limits)
        return None

    for t in terms:
        as_sum = _as_sum(t)
        (sums if as_sum is not None else rest).append(
            as_sum if as_sum is not None else t)
    if not sums:
        return None

    def _element_env(expr):
        subs, bounds = {}, {}
        for idx in expr.atoms(sympy.Indexed):
            base = str(idx.base)
            fresh = sympy.Symbol(f"_elt_{base}", real=True)
            subs[idx] = fresh
            bound = domain.get(base)
            if bound is not None:
                bounds[str(fresh)] = bound
        return subs, bounds

    def _nonneg(expr, strict: bool) -> bool:
        subs, bounds = _element_env(expr)
        scalar = expr.subs(subs)
        for s in scalar.free_symbols:
            if str(s) not in bounds and str(s) in domain:
                bounds[str(s)] = domain[str(s)]
        rel = ">" if strict else ">="
        syms = {str(s): s for s in scalar.free_symbols}
        try:
            r = _prove_relation(scalar, sympy.S.Zero, rel, bounds, None, syms)
            if r.status == "proven":
                return True
        except Exception:
            pass
        if isinstance(scalar, sympy.Piecewise):
            # each branch decided UNDER ITS OWN condition (the branch
            # is only ever taken when it holds), a sign condition on
            # one symbol is BAKED into that symbol so sympy's sign
            # algebra can actually use it (`v > 0` making scale*v
            # nonnegative needs v's own positivity, not a side
            # predicate)
            _SIGN_ASSUMPTIONS = {
                sympy.StrictGreaterThan: {"positive": True},
                sympy.GreaterThan: {"nonnegative": True},
                sympy.StrictLessThan: {"negative": True},
                sympy.LessThan: {"nonpositive": True},
            }
            try:
                priors: list = []
                for v, c in scalar.args:
                    # the branch runs only when every EARLIER condition
                    # failed and its own holds: a catch-all else after
                    # `v > 0` really means `v <= 0`
                    negated = [prior.negated for prior in priors
                               if isinstance(prior, sympy.Rel)]
                    own = [] if c is sympy.true else [c]
                    if isinstance(c, sympy.Rel):
                        priors.append(c)
                    effective = negated + own
                    if not v.free_symbols:
                        if not bool(v > 0 if strict else v >= 0):
                            return False
                        continue
                    value = v
                    remaining = []
                    for cnd in effective:
                        if (isinstance(cnd, sympy.Rel)
                                and isinstance(cnd.lhs, sympy.Symbol)
                                and cnd.rhs == 0
                                and type(cnd) in _SIGN_ASSUMPTIONS):
                            assum = _SIGN_ASSUMPTIONS[type(cnd)]
                            baked = sympy.Symbol(cnd.lhs.name, real=True,
                                                 **assum)
                            value = value.subs(cnd.lhs, baked)
                        else:
                            remaining.append(cnd)
                    context = (None if not remaining
                               else remaining[0] if len(remaining) == 1
                               else sympy.And(*remaining))
                    r = _prove_relation(value, sympy.S.Zero, rel, bounds,
                                        context,
                                        {str(x): x
                                         for x in value.free_symbols})
                    if r.status != "proven":
                        return False
                return True
            except Exception:
                return False
        return False

    for t in sums:
        if not _nonneg(t.function, strict=False):
            return None
    remainder = sympy.Add(*rest) if rest else sympy.S.Zero
    rem_ok_strict = False
    if remainder != 0:
        bounds = dict(domain)
        syms = {str(x): x for x in remainder.free_symbols}
        try:
            rel = ">" if want_strict else ">="
            r = _prove_relation(remainder, sympy.S.Zero, rel, bounds, None, syms)
            if r.status != "proven":
                if not want_strict:
                    return None
                r2 = _prove_relation(remainder, sympy.S.Zero, ">=", bounds,
                                     None, syms)
                if r2.status != "proven":
                    return None
            else:
                rem_ok_strict = want_strict
        except Exception:
            return None
    if want_strict and not rem_ok_strict:
        # strictness must come from a provably nonempty sum whose
        # summand is strictly positive
        strict_found = False
        for t in sums:
            limits = t.limits[0] if t.limits else None
            if limits is None:
                continue
            _i, lo, hi = limits
            count = sympy.simplify(hi - lo + 1)
            syms = {str(x): x for x in count.free_symbols}
            try:
                nonempty = _prove_relation(count, sympy.S.Zero, ">", domain,
                                           None, syms).status == "proven"
            except Exception:
                nonempty = False
            if nonempty and _nonneg(t.function, strict=True):
                strict_found = True
                break
        if not strict_found:
            return None
    kind = "strictly positive" if want_strict else "never negative"
    return ProofResult(
        "proven",
        sketch=f"each term of the sum is {kind} over the declared element "
               f"domain, so the whole sum is (termwise sign, exact for any "
               f"length)",
        meta={"mathema.derive_route": "termwise_sum"})


def _length_pins(equalities, length_symbols) -> dict:
    """Intent:
        The substitutions a claim's equality premises pin sequence
        lengths to: a literal (`len(x) == 2` gives `{L_x: 2}`) or each
        other (`len(x) == len(y)` maps one onto the other, so the two
        sums are built over a single symbol the way the probe route's
        `DimResolver` makes them draw a single length).

    Notes:
        Unions are resolved before literals are read, so the result does
        not depend on the order the premises were written in, and a
        chain (`len(x) == len(y)`, `len(y) == 3`) pins every member of
        the chain. Equalities that are not about lengths are ignored
        here; they have already become assumption predicates.

        Contradictory premises (`len(x) == 2` and `len(x) == 3`) pin
        nothing. The region they describe is empty, and the convention
        for an empty region is to say nothing rather than to prove
        everything, matching `_tighten_domain_by_assumption`.
    """
    parent: dict = {}

    def root(s):
        while s in parent:
            s = parent[s]
        return s

    def is_int(e) -> bool:
        # a length is a count, so a negative literal describes no
        # sequence at all. Pinning one would make every Sum over it
        # collapse to the empty sum and prove the claim vacuously.
        return getattr(e, "is_Integer", False) and e >= 0

    for a, b in equalities:
        if a in length_symbols and b in length_symbols:
            ra, rb = root(a), root(b)
            if ra != rb:
                # a stable representative, so premise order cannot
                # change which symbol survives
                lo, hi = sorted((ra, rb), key=str)
                parent[hi] = lo
    literal: dict = {}
    for a, b in equalities:
        for sym, value in ((a, b), (b, a)):
            if sym in length_symbols and is_int(value):
                seen = literal.setdefault(root(sym), value)
                if seen != value:
                    return {}
    pins = {}
    for sym in length_symbols:
        target = literal.get(root(sym), root(sym))
        if target != sym:
            pins[sym] = target
    return pins


def _fold_premises(assumption, build, view, bound_context):
    """Intent:
        `(bound_context, length_pins)` with the claim's own premises
        folded in, or a `ProofResult` when one of them cannot be
        expressed against this lift.

    Notes:
        A premise reaches the sequence route in one of three shapes, and
        only the first is handled before this point. A bound on a scalar
        parameter against a literal (`assuming s >= 0`) has already
        tightened the domain box. A relation between two quantities
        (`assuming a <= b`) is not a box at all, so it normalizes to a
        nonnegative gap and joins the prover's assumption context, the
        same way the scalar route builds it. An equality involving a
        sequence's LENGTH additionally becomes a substitution, because
        sympy cannot expand a `Sum` from an assumption about its limit
        (see `_length_pins`).

        A premise the lift cannot express returns unliftable rather than
        being skipped: proceeding without it would decide the claim over
        a region its author excluded, which is the same class of error
        as a wrong verdict.
    """
    length_equalities: list = []
    for a_lhs_src, a_rel, a_rhs_src in (assumption or []):
        try:
            a_lhs, a_rhs = build(str(a_lhs_src)), build(str(a_rhs_src))
        except NotSymbolic as e:
            return ProofResult("unliftable",
                               sketch=f"assuming clause not derivable against "
                                      f"the recognized {view.kind}: {e}")
        if isinstance(a_lhs, tuple) or isinstance(a_rhs, tuple):
            return ProofResult("unliftable",
                               sketch="assuming clause compares a tuple-valued "
                                      "expression")
        gap = a_lhs - a_rhs
        if a_rel == "==":
            length_equalities.append((a_lhs, a_rhs))
            pred = sympy.Q.zero(gap)
        elif a_rel == "!=":
            pred = sympy.Q.nonzero(gap)
        else:
            if a_rel in ("<=", "<"):
                gap = -gap
            pred = (sympy.Q.positive(gap) if a_rel in (">", "<")
                    else sympy.Q.nonnegative(gap))
        bound_context = pred if bound_context is None \
            else sympy.And(bound_context, pred)
    return bound_context, _length_pins(length_equalities,
                                       set(view.lengths.values()))


def try_prove_seq(view: SeqLiftView, fn, lhs_src: str, rhs_src: str,
                  relation: str, domain: dict | None = None,
                  tolerance: float | None = None,
                  assumption=None) -> ProofResult:
    """The one proof attempt every sequence-shaped lift shares: domain
    assumptions on the lift's scalar parameters (the claim's own domain,
    topped up by whatever the signature markers imply), the claim law
    converted via
    `_seq_law_to_sympy`, `_prove_relation`, and a quantifier naming the
    folded sequences alongside whichever scalars stayed free.

    `assumption` is the claim's own premises as `(lhs, relation, rhs)`
    triples, the same form the scalar route takes: each one narrows the
    domain box, so a claim made under `assuming n >= 3` is adjudicated
    over that region rather than over every `n`."""
    domain = dict(domain or {})
    if view.other_params:
        # the claim's own quantifier wins; the signature's
        # Probability/Positive/Nonnegative markers fill any parameter it
        # left unbounded (the docstring `Domain:` block used to sit here
        # too and was removed; 0 real uses across the corpus)
        from ..types import domain_from_signature
        for name, bound in domain_from_signature(fn).items():
            if name in view.other_params:
                domain.setdefault(name, bound)
    # an `assuming n >= 3` premise is part of the region the claim is
    # made over, so it tightens the box before the symbols are built.
    # Afterwards is too late: a symbol's sign assumptions are fixed at
    # creation, and the interval rung reads the box, not the ask()
    # context. Same ordering, and the same reason, as the scalar route's
    # own use of `_tighten_domain_by_assumption`.
    if assumption:
        from ._prove import _tighten_domain_by_assumption
        domain = _tighten_domain_by_assumption(domain, view.other_params,
                                               assumption)
    try:
        subs, bound_context, assumed_other, pins = _domain_assumptions(view.other_params, domain)
    except InvalidDomain as e:
        return ProofResult("unliftable", sketch=f"declared domain is not "
                           f"projectable: {e}")
    if subs:
        view = view.with_domain_subs(view, subs, assumed_other)
    if pins:
        # pins compose into the f(...) substitution values rather than
        # baking into the lift: `f(xs, alpha)` under `alpha in [1, 1]`
        # substitutes 1 THROUGH eval_f, so the fold's zero-collapse
        # rebuild still fires (a post-hoc alpha->1 would leave
        # 0**(L-1-k) sums sympy can't kill), while `f(xs, 2*g)` under a
        # pinned g still doubles the PINNED value instead of collapsing
        # to a constant before the argument can matter.
        inner_eval = view.eval_f
        def eval_with_pins(arg_subs, _inner=inner_eval):
            pinned_args = {k: (v.subs(pins, simultaneous=True)
                               if hasattr(v, "subs") else v)
                          for k, v in arg_subs.items()}
            return _inner(pinned_args)
        view = replace(view, eval_f=eval_with_pins)

    aux: dict = {}
    from ..conjecture import DEFAULT_TOLERANCE
    eps_val = sympy.Float(tolerance if tolerance is not None
                          else DEFAULT_TOLERANCE)
    aux["eps"] = aux["epsilon"] = aux["ε"] = eps_val

    def build(src: str):
        try:
            tree = ast.parse(src, mode="eval")
            return _seq_law_to_sympy(tree, view, aux)
        except (SyntaxError, NotSymbolic) as e:
            raise NotSymbolic(str(e)) from e

    try:
        lhs = build(lhs_src)
        rhs = build(rhs_src)
    except NotSymbolic as e:
        return ProofResult("unliftable", sketch=f"claim statement not derivable "
                           f"against the recognized {view.kind}: {e}")
    if pins:
        # applied after conversion, never baked into the lift, same
        # ordering rule (and the same false-proof failure mode it
        # prevents) as try_prove's own pin handling.
        lhs = lhs.subs(pins, simultaneous=True) if not isinstance(lhs, tuple)             else tuple(v.subs(pins, simultaneous=True) for v in lhs)
        rhs = rhs.subs(pins, simultaneous=True) if not isinstance(rhs, tuple)             else tuple(v.subs(pins, simultaneous=True) for v in rhs)
    if isinstance(lhs, tuple) or isinstance(rhs, tuple):
        return ProofResult("unliftable", sketch=f"cannot compare a tuple-valued "
                           f"expression against a {view.kind} lift")
    folded = _fold_premises(assumption, build, view, bound_context)
    if isinstance(folded, ProofResult):
        return folded
    bound_context, length_pins = folded
    if length_pins:
        # applied after conversion, never baked into the lift, the same
        # ordering rule as the degenerate domain pins above
        lhs = lhs.subs(length_pins).doit()
        rhs = rhs.subs(length_pins).doit()
    try:
        result = _prove_relation(lhs, rhs, relation, domain, bound_context,
                                 view.other_params, opaque=view.opaque)
    except Exception as e:
        return ProofResult("undecided", sketch=f"{type(e).__name__} during proof: {e}")
    if result.status == "undecided":
        termwise = _termwise_sum_decide(lhs, rhs, relation, domain, view)
        if termwise is not None:
            result = termwise
    if result.status != "proven":
        return result
    # a folded sequence isn't a plain sympy.Symbol (it's an IndexedBase),
    # so it can't go through _free_names/_quantifier_clause the way a
    # scalar can; its clause is prepended by hand, merged with
    # whichever of the lift's own scalar parameters stayed free.
    names = _free_names(lhs) | _free_names(rhs)
    scalar_names = {n for n in names if n in view.other_params}
    if not view.seqs:
        # the no-sequence fold shape: every free name is an ordinary
        # scalar, nothing to prepend.
        return replace(result, quantifier=_quantifier_clause(
            scalar_names, view.sig_params, domain or {}))
    reserved = {n for n in view.seqs if len(n) == 1}
    scalar_clause = _quantifier_clause(scalar_names, view.sig_params, domain or {},
                                       reserved=reserved)
    seq_part = f"{', '.join(view.seqs)} ∈ Seq(ℝ)"
    if scalar_clause is None:
        quantifier = f"∀ {seq_part}"
    elif scalar_clause.startswith("where "):
        legend, _, rest = scalar_clause.partition(": ∀ ")
        quantifier = f"{legend}: ∀ {seq_part}, {rest}"
    else:
        quantifier = scalar_clause.replace("∀ ", f"∀ {seq_part}, ", 1)
    return replace(result, quantifier=quantifier)
