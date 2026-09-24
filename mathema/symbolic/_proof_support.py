# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Proof-adjudication infrastructure shared by all four `try_prove_*`
variants (`.prove`'s `try_prove`, and `.fold`/`.dot`/`.sum`'s own
`try_prove_fold`/`try_prove_dot`/`try_prove_sum`), not `try_prove`-
exclusive, despite each of those living in a different module.
Factoring these out here (rather than bundling them with `.prove`) is
what lets `.fold`/`.dot`/`.sum` import the adjudication machinery they
need without importing from the module that itself imports their own
`try_prove_fold`/`try_prove_dot`/`try_prove_sum` back, a real cycle a
naive "everything proof-related lives with try_prove" grouping would
create. Leaf-level with respect to the rest of the package too: the
only sibling imports are `.._timeout`, `.._sampling`, `..domain`, and
`._base` (for `_exact_numeric_literal` alone), all dependency-free
leaves, so nothing here can create a cycle back through
`diagnostics.py` (which imports the `symbolic` package, which imports
this module) or through `_base.py` itself (which sits below this
module and imports neither it nor anything that does). `.._sampling`
is the same seeded scalar sampler `probing.py`'s own probes are built
on, reused here (not reimplemented) for `_corroborate_disproof`'s
numeric counterexample search; `..domain` is the shared domain model,
whose `render_domain` is the one renderer of a declared bound (this
module used to carry its own near-copy, which had already drifted in
formatting).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import sympy

from .._sampling import _RNG_SEED, _synth_scalar
from .._timeout import FAST_TIMEOUT_SECONDS, EXTENSIVE_TIMEOUT_SECONDS, _with_timeout
from ..domain import (Interval,
                      bound_assumptions as domain_bound_assumptions,
                      bound_context as domain_bound_context,
                      bound_pin as domain_bound_pin, render_domain)
from ._base import _exact_numeric_literal

if TYPE_CHECKING:
    # type-checking only, never imported at runtime; this module's own
    # leaf-level design (see the module docstring) holds at runtime
    # regardless of what a static checker needs to resolve the
    # "OpaqueRegistry | None" annotation below.
    from ..finite_sets import OpaqueRegistry


def _affine_sign_by_corners(target, domain: dict, params: dict) -> bool | None:
    """For a `target` that's affine (degree <= 1) in every domain-
    bounded symbol it contains, its sign over the domain's hyperrectangle
    is fully determined by its sign at the corners, an affine
    functional's extrema over a box are always attained at a vertex, an
    exact fact, not a heuristic, and one that doesn't depend on sympy's
    own (here, incomplete, see _resolve_clamps) inequality reasoning
    at all. `None` if target isn't affine in its bounded symbols, or too
    many are bounded to enumerate corners cheaply (2**n of them)."""
    import itertools

    bounded = {p: domain[p] for p, sym in params.items()
              if sym in target.free_symbols and isinstance(domain.get(p), tuple)}
    if not bounded or len(bounded) > 6:
        return None
    syms = [params[p] for p in bounded]
    if not target.free_symbols <= set(syms):
        # a free symbol outside `syms` (unbounded, or not one of the
        # function's own parameters at all) makes `Poly(target, *syms)`
        # silently treat it as a fixed coefficient rather than a real
        # variable; `total_degree()` can then read <= 1 even though
        # `target` isn't actually affine in everything it depends on,
        # and the corner loop below would leave that symbol unsubstituted,
        # crashing `float()` on a still-symbolic result. Bail rather than
        # risk either.
        return None
    try:
        if sympy.Poly(target, *syms).total_degree() > 1:
            return None
    except sympy.PolynomialError:
        return None
    signs = set()
    for corner in itertools.product(*bounded.values()):
        signs.add(float(target.subs(dict(zip(syms, corner)))) >= 0)
    return signs.pop() if len(signs) == 1 else None


def _provably_signed(expr, domain: dict, params: dict, bound_context) -> bool | None:
    """`True` if `expr` is provably nonnegative under the declared
    domain, `False` if provably negative, `None` if undetermined,
    tries the cheapest check first, each one strictly more powerful than
    the last:

    1. `expr.is_positive`/`.is_negative`, free, catches what sympy
       already knows about the expression's own structure.
    2. `ask(Q.positive/negative(expr))` under `bound_context`, combines
       the domain's dynamic facts with sympy's inference, but doesn't
       reliably derive a *product's* sign from a *linear* bound on one of
       its factors (confirmed directly: `ask(Q.positive(A*(e-1)))` stays
       `None` even under `e >= 1.5`, since that's a step of algebra
       `ask()` doesn't take on its own), steps 3/4 close that gap.
    3. `_affine_sign_by_corners`, already exact for anything affine in
       its bounded symbols (`e - 1`, `1 - a`, ...).
    4. For a `Mul`, the sign of each factor determined recursively and
       combined (an even count of negative factors is positive), what
       actually resolves a compound base like `A*(e-1)` or `-I*(a-1)`:
       neither is affine as a whole (both are products, degree 2), but
       each of their factors is either a plain positive symbol or an
       affine sub-expression corners can decide."""
    if expr.is_positive:
        return True
    if expr.is_negative:
        return False
    if bound_context is not None:
        try:
            with sympy.assuming(bound_context):
                if sympy.ask(sympy.Q.nonnegative(expr)) is True:
                    return True
                if sympy.ask(sympy.Q.negative(expr)) is True:
                    return False
        except TimeoutError:
            raise
        except Exception:
            # sympy's ask() machinery has internal failure modes of its
            # own (an AssertionError deep in the LRA solver, observed on
            # log(x)/log(10) shapes); an ask() crash is an undecided,
            # never a crashed proof.
            pass
    corners = _affine_sign_by_corners(expr, domain, params)
    if corners is not None:
        return corners
    if expr.is_Mul:
        negatives = 0
        may_vanish = False
        for factor in expr.args:
            sign = _provably_signed(factor, domain, params, bound_context)
            if sign is None:
                return None
            if sign is False:
                negatives += 1
            else:
                # nonnegative includes zero, so the product may be zero
                may_vanish = True
        if negatives % 2 == 0:
            return True
        return None if may_vanish else False
    return None


def _atomize_positive_power_bases(expr, domain: dict, params: dict, bound_context):
    """Replace every compound (non-atomic, non-`Pow`) `Pow` base in
    `expr` that's provably nonnegative under the declared domain
    (`_provably_signed`) with a fresh `Dummy(positive=True, real=True)`.

    sympy's own power-collecting simplification (`powdenest`/`simplify`)
    works reliably when a power's base is a single atomic symbol, but
    not when the base is a compound sub-expression, confirmed directly:
    `powdenest((X**e)**((e-1)/e), force=True)` collapses to `X**(e-1)`
    immediately when `X` is a plain symbol, but stalls one step short
    when `X` is itself `A*(e-1)` (a real expression this shape shows up
    in: an isoelastic monopoly's or Cobb-Douglas demand curve's FOC).
    Only the base's *positivity* is used by the power laws being
    resolved here (`X**a * X**b == X**(a+b)` for positive real `X`), so
    swapping in a fresh symbol carrying exactly that one fact, nothing
    more, nothing the domain doesn't already prove, changes nothing
    about what's true, only what sympy's own simplifier can see. Bases
    that aren't a `Pow` are excluded on purpose: this targets leaf
    compound bases (`A*(e-1)`), not an intermediate power result
    (`(A*(e-1))**e`) that would otherwise also match and produce a
    useless double substitution."""
    bases = {p.base for p in expr.atoms(sympy.Pow)
            if not p.base.is_Atom and not p.base.is_Pow}
    subs = {base: sympy.Dummy(positive=True, real=True) for base in bases
           if _provably_signed(base, domain, params, bound_context) is True}
    return expr.subs(subs) if subs else expr


def _resolve_clamps(expr, domain: dict, params: dict):
    """Collapse a two-argument `Min`/`Max` node directly against each
    side's own declared `(lo, hi)` domain bound (a numeric literal
    counts as its own degenerate `(c, c)` bound), a very common
    real-code shape (`min(1.0, x)`/`np.clip(...)`-style clamping, or
    `min(v, v_max)` between two independently bounded parameters) that
    sympy's own assumption engine can't reliably resolve on its own
    even when told the bounds: ask()/refine() have a real, documented-
    by-behavior gap for a *non-strict* boundary-touching inequality
    (e.g. `ask(Symbol('r', real=True) >= 1)` stays undecided even under
    `assuming(Q.le(r, 1))`, while the strict form `ask(r > 1)` resolves
    correctly), exactly the closed-interval case `[lo, hi]` domains
    normally are. Reasoning about it directly from the domain dict
    sidesteps that gap rather than depending on ask()/refine() to close
    it. Only ever collapses when one side's whole range provably never
    overlaps the other's, an overlapping or partially-declared pair
    is left alone, never guessed at."""
    bounds = {}
    for p, sym in params.items():
        lo_hi = domain.get(p)
        if isinstance(lo_hi, tuple) and len(lo_hi) == 2:
            bounds[sym] = (float(lo_hi[0]), float(lo_hi[1]))

    def bound_of(node):
        if node.is_number:
            c = float(node)
            return c, c
        if node in bounds:
            return bounds[node]
        # a compound side (`n - 1`, the trip count of a range loop) is
        # bounded by its interval hull, which contains its true range
        try:
            hull = _interval_bounds(node, domain, params)
        except TimeoutError:
            raise
        except Exception:
            return None
        if isinstance(hull, sympy.AccumBounds):
            lo, hi = hull.min, hull.max
        elif hull is not None and getattr(hull, "is_number", False):
            lo = hi = hull
        else:
            return None
        if not (lo.is_finite and hi.is_finite):
            return None
        return float(lo), float(hi)

    subs = {}
    for node in expr.atoms(sympy.Min, sympy.Max):
        args = node.args
        if len(args) != 2:
            continue
        a, b = args
        bound_a, bound_b = bound_of(a), bound_of(b)
        if bound_a is None or bound_b is None:
            continue
        lo_a, hi_a = bound_a
        lo_b, hi_b = bound_b
        if isinstance(node, sympy.Min):
            if hi_a <= lo_b:
                subs[node] = a
            elif hi_b <= lo_a:
                subs[node] = b
        else:
            if hi_a <= lo_b:
                subs[node] = b
            elif hi_b <= lo_a:
                subs[node] = a
    return expr.subs(subs) if subs else expr


#: the most integer-part nodes one expression's relaxation will
#: introduce auxiliaries for. Each one widens the box the interval rung
#: then has to decide, so past a handful the relaxation stops being
#: worth attempting rather than being attempted badly.
_MAX_INT_PART_AUX = 6


def _resolve_int_parts(expr, domain: dict, params: dict):
    """Intent:
        `(expr, domain, params)` with every `floor`/`ceiling`/`Mod` node
        replaced by a fresh auxiliary parameter carrying the exact
        bounds that integer part is known to satisfy, so a sign question
        containing one becomes an ordinary bounded question the interval
        rung can decide. Returns the three unchanged when there is
        nothing to relax.

    Notes:
        The facts, each exact: `floor(u) = u - t` for some `t` in
        `[0, 1)`; `ceiling(u) = u + t` for the same range; and, for a
        positive modulus `n`, `Mod(a, n) = n * s` for some `s` in
        `[0, 1)`, tightened to `(n - 1) * s` with `s` in `[0, 1]` when
        both `a` and `n` are integers (only then is `n - 1` the largest
        remainder).

        `Mod` is expressed as a fraction of its own SYMBOLIC bound
        rather than as a free auxiliary with a numeric box, because the
        useful claims about it relate the remainder to the modulus
        (`Mod(k, n) / n <= (n - 1) / n`). A free auxiliary bounded by
        the modulus's largest possible value loses that coupling and
        decides nothing.

        Every occurrence of the same node shares one auxiliary, so
        `floor(u) - floor(u)` still cancels. Distinct nodes get distinct
        auxiliaries, which is what makes this an over-approximation: the
        real integer parts move together with their arguments, and these
        auxiliaries move independently. The relaxed expression's range
        CONTAINS the true range, so a proof over the relaxation holds
        of the original, while a disproof over it does not (a relaxed
        point need not be a real one); `_prove_relation` reads a
        relaxed disproof as undecided.

        `_resolve_mod` runs before this and collapses the narrow case it
        can do EXACTLY. This is the lossy fallback for everything else.
    """
    nodes: list = []
    for node in expr.atoms(sympy.floor, sympy.ceiling, sympy.Mod):
        if isinstance(node, sympy.Mod):
            modulus = node.args[1]
            hull = _interval_bounds(modulus, domain, params)
            lo = hull.min if isinstance(hull, sympy.AccumBounds) else hull
            if lo is None or _verified_sign(lo) != 1:
                # a modulus that is not provably positive has no
                # remainder range to state
                continue
        nodes.append(node)
    if not nodes or len(nodes) > _MAX_INT_PART_AUX:
        return expr, domain, params

    from ..domain import Interval
    out, new_domain, new_params = expr, dict(domain), dict(params)
    for i, node in enumerate(sorted(nodes, key=sympy.default_sort_key)):
        name = f"_intpart{i}"
        aux = sympy.Symbol(name, nonnegative=True)
        new_params[name] = aux
        if isinstance(node, sympy.Mod):
            dividend, modulus = node.args
            if dividend.is_integer and modulus.is_integer:
                new_domain[name] = Interval(0.0, 1.0, True, True)
                out = out.subs(node, (modulus - 1) * aux)
            else:
                new_domain[name] = Interval(0.0, 1.0, True, False)
                out = out.subs(node, modulus * aux)
        else:
            new_domain[name] = Interval(0.0, 1.0, True, False)
            out = out.subs(node, node.args[0] - aux
                           if node.func is sympy.floor else node.args[0] + aux)
    return out, new_domain, new_params


def _resolve_mod(expr, domain: dict, params: dict):
    """Collapse `Mod(sym, m)` to plain `sym` when the declared domain
    provably confines `sym` to `[0, m)`; `Mod(x, m) == x` holds for
    any real `x` in that half-open range and is false the moment `x`
    reaches `m` (`Mod(m, m) == 0`), so the upper bound must be strictly
    below `m`, or exactly `m` with the domain itself open there.

    sympy's own `.equals()` has no way to see this: `Mod(hour, 12) -
    hour` is genuinely nonzero for an unbounded `hour` (any value at or
    past 12 is a real counterexample), so `.equals()` falls back to its
    own internal random sampling to decide, and gets a different answer
    depending on where it happens to sample, proving nothing about
    the declared domain, which is the only thing that actually settles
    the question here. Resolving the domain-safe collapse directly, the
    same way `_resolve_clamps` already does for `Min`/`Max`, removes
    `Mod` from the expression entirely for a domain this narrow, so the
    question `.equals()` ends up answering is a plain, honestly
    decidable one."""
    subs = {}
    for p, sym in params.items():
        lo_hi = domain.get(p)
        if not isinstance(lo_hi, tuple):
            continue
        lo, hi = lo_hi
        if lo < 0:
            continue
        closed_hi = getattr(lo_hi, "closed_hi", True)
        for node in expr.atoms(sympy.Mod):
            base, modulus = node.args
            if base != sym or not modulus.is_number:
                continue
            m = float(modulus)
            if hi < m or (hi == m and not closed_hi):
                subs[node] = sym
    return expr.subs(subs) if subs else expr


def _free_names(expr) -> set:
    """The plain-Symbol free variable names of a (possibly tuple-valued)
    sympy expression; names, not Symbol objects, so a caller can test
    membership against an ordinary parameter dict without worrying
    about two Symbols with the same name but different assumptions
    comparing unequal."""
    if isinstance(expr, tuple):
        names = set()
        for e in expr:
            names |= _free_names(e)
        return names
    return {s.name for s in expr.free_symbols if isinstance(s, sympy.Symbol)}


_QUANTIFIER_LETTER_POOL = "xyzwuvabcdefghijklmnopqrst"


def _quantifier_clause(names: set, order: list, domain: dict,
                       reserved: set = frozenset()) -> str | None:
    """A closed-form '∀ x, y ∈ ℝ, a ∈ [0, 1] ⊂ ℝ' clause for a proof's
    own free variables, real by default and narrowed by whatever domain
    the claim actually declared; `None` if nothing in `names` is left
    free (a fully pinned claim, e.g. every parameter replaced by a
    literal). `order` fixes the parameter order considered (the
    function's own signature order, not set-iteration order).

    Reads like ordinary math notation regardless of how verbose the
    real parameter names are: an already single-character name (`x`)
    stays itself, but a longer one (`learning_rate`) is assigned the
    next unused short letter instead, with a `where a=learning_rate`
    legend prefixed so the mapping back to the real signature is never
    lost. Variables that end up sharing the same domain are grouped
    into one clause (`x, y, z ∈ ℝ`), not repeated once each. `reserved`
    is a set of short letters this call must not assign, even if
    otherwise free, for a caller (try_prove_fold) merging this
    clause's own short names with a separate, already-decided one for
    a variable outside `names`/`order` entirely (the folded sequence
    parameter, which isn't a plain Symbol and so never goes through
    this function itself)."""
    free = [n for n in order if n in names]
    if not free:
        return None

    used = {n for n in free if len(n) == 1} | set(reserved)
    pool = iter(c for c in _QUANTIFIER_LETTER_POOL if c not in used)
    short = {n: (n if len(n) == 1 and n not in reserved else next(pool, n)) for n in free}

    def domain_desc(n: str) -> str:
        # `render_domain` handles every bound shape a claim can declare
        # (`Domain`, `Interval`/tuple, frozenset, bare "Z"/"N"), always
        # stating the resolved type and missing-value policy explicitly;
        # the same renderer the claim text itself uses, so a proof's
        # quantifier clause and the rendered claim can never drift
        # apart. A parameter with no declared bound at all stays a bare
        # "ℝ" (the default assumption, not a declared domain).
        bounds = domain.get(n)
        if bounds is None:
            return "ℝ"
        return render_domain(bounds, ascii_mode=False)

    groups: dict = {}
    for n in free:
        groups.setdefault(domain_desc(n), []).append(short[n])
    clause = "∀ " + ", ".join(f"{', '.join(syms)} ∈ {desc}" for desc, syms in groups.items())

    legend = [f"{short[n]}={n}" for n in free if short[n] != n]
    return f"where {', '.join(legend)}: {clause}" if legend else clause


@dataclass
class ProofResult:
    """The outcome of a single derive-route decision: `try_prove()`/
    `try_prove_raises()`'s return type. `sketch` is a short, human-
    readable explanation of how the status was reached (which
    expressions simplified to what, or why a sign/equality couldn't be
    settled), always present except when `status` is `"unliftable"`
    for a reason obvious from context. `quantifier` is only ever set
    alongside `status == "proven"`: a closed-form '∀ x ∈ ℝ, ...' clause
    naming exactly the variables the proof actually holds over (see
    _quantifier_clause); a proof has no trial count the way a probe
    does, so this is what stands in its place."""
    status: str   # "proven" | "disproven" | "undecided" | "unliftable"
    sketch: str | None = None
    counterexample: str | None = None
    quantifier: str | None = None
    meta: dict = field(default_factory=dict)
    witness: dict | None = None
    # a concrete counterexample point behind a "disproven" (free-var
    # name -> sympy/number value), seeding the corroboration engine so
    # it re-checks the disproof against the ORIGINAL function, not the
    # internal (possibly corrupted) residual. `None` when the decider
    # had no point (the engine then searches).
    disproof_hint: "sympy.Expr | None" = None
    # the offending expression whose sign/value flipped, machine-
    # readable "where/why", so corroboration can perturb around its own
    # critical points rather than sampling blind.
    intermediates: "tuple | None" = None
    # on an UNDECIDED result: (lhs_expr, rhs_expr, params), the
    # resolved symbolic sides of the comparison (calculus operators
    # already evaluated at lowering), so the numeric fallback can
    # lambdify and sample the exact intermediate the proof stalled on.
    # Never serialized; internal to the adjudication seam.


def _humanize(expr) -> str:
    """A sympy expression for a sketch string, not a sympy REPL: a
    Piecewise reads as plain "case; case; ...; otherwise case" language
    instead of a nested tuple of (value, condition) pairs, `Eq(a, b)`
    reads as `a = b`, and everything else falls back to sympy's own
    string form with `**` swapped for `^` (still single-line-safe,
    unlike sympy.pretty()'s stacked fractions/Sum glyphs, but closer to
    how the exponent would actually be written by hand)."""
    if isinstance(expr, sympy.Piecewise):
        parts = []
        for value, cond in expr.args:
            parts.append(f"otherwise {_humanize(value)}" if cond is sympy.true
                         else f"when {_humanize(cond)}: {_humanize(value)}")
        return "; ".join(parts)
    if isinstance(expr, sympy.Eq):
        return f"{_humanize(expr.lhs)} = {_humanize(expr.rhs)}"
    return str(expr).replace("**", "^")


def _domain_assumptions(params: dict, domain: dict) -> tuple[dict, "sympy.Basic | None", dict, dict]:
    """For each name in `params` with a bound in `domain`, a substitution
    from the original bare symbol to a fresh one carrying the matching
    sympy assumption (`positive`/`nonnegative`/`integer`), needed
    *before* a law is parsed, not after, since an operation like
    integrate()/lim()/d() needs the assumption while it's computing (see
    try_prove()'s own use of this, the original site this was factored
    out of). `bound_context` additionally expresses any *upper* bound as
    a `sympy.And` of `Q.ge`/`Q.gt`/`Q.le`/`Q.lt` predicates (for
    `sympy.refine()`); a fixed assumption keyword has nothing for
    `<= hi`. Returns `(subs, bound_context, updated_params, pins)`;
    `subs` maps the ORIGINAL symbol -> its assumption-carrying
    replacement, ready for `.subs(subs, simultaneous=True)` on whatever
    expression `params` came from. `pins` maps a degenerately-bounded
    parameter's symbol -> its exact literal, kept SEPARATE from `subs`
    deliberately: a pin must be applied AFTER the claim law is
    converted, never baked into the lifted expression first, baking
    it in collapses the expression to a constant before an `f(q, p)`
    call's argument order can mean anything, which once made
    `f(q, p) == f(p, q)` "prove" under two pinned parameters (a false
    proof, observed in the field). Shared between try_prove()'s
    own domain handling and try_prove_fold()'s (fold.other_params),
    same assumption vocabulary, same reason it's needed before parsing,
    just a different params dict to apply it to.

    A *degenerate* domain (`lo == hi`, both bounds closed, a genuine
    single point, e.g. `[0, 0]`, not merely a narrow range) is pinned
    (via `pins` and `_exact_numeric_literal`, so a
    float bound like `1e-7` becomes an exact `Rational` rather than a
    binary `sympy.Float`, a `Float` substituted into a transcendental
    call like `log(h)` evaluates eagerly to another `Float` instead of
    staying a symbolic expression sympy can later prove equal to
    something, the same imprecision `_exact_numeric_literal` already
    exists to avoid for a literal written directly in claim text)
    rather than only ever getting a `nonnegative`-style sign assumption
    the way
    an ordinary range does, `for c in [0, 0]: f(a, b, c) == 0` now
    actually substitutes `c = 0` into the body before the claim is
    decided, matching what the syntax looks like it should do (this used
    to be a real, confusing gap: the claim came back `falsified` against
    the *unsubstituted* symbol, not `skipped`, with no signal that a
    degenerate domain range never pinned anything). `updated[p]` is
    deliberately left as the *original* symbol in this case, never
    renamed to the literal; `updated`/`assumed_params` becomes the new
    `lifted.params`, which claim-text `f(...)` call substitution
    (`_law_to_sympy`'s `f` case) keys off of; a literal used there as a
    `.subs()` key would match every occurrence of that literal value
    anywhere in the expression, not just the pinned parameter, a real
    correctness risk rather than a hypothetical one."""
    updated = dict(params)
    subs: dict[sympy.Symbol, sympy.Expr] = {}
    pins: dict[sympy.Symbol, sympy.Expr] = {}
    pinned: set = set()
    for p, sym in params.items():
        lo_hi = domain.get(p)
        if lo_hi is None:
            continue
        # every bound shape (`Interval`/tuple, "Z"/"N", frozenset,
        # `Domain`) is interpreted by the domain model's own symbolic
        # projection, what a bound pins, what symbol-level assumption
        # keywords it soundly entails, and (below) what Q-predicate
        # context it states, all read from one place instead of
        # re-derived shape-by-shape here.
        is_pinned, value = domain_bound_pin(lo_hi)
        if is_pinned:
            pins[sym] = _exact_numeric_literal(value)
            pinned.add(p)
            continue
        kwargs = domain_bound_assumptions(lo_hi)
        if kwargs is not None:
            new_sym = sympy.Symbol(p, **kwargs)
            updated[p] = new_sym
            subs[sym] = new_sym

    # The substitution above only ever expresses a *lower* bound (sympy's
    # symbol-level assumptions (positive/nonnegative/integer) are a
    # fixed vocabulary with nothing for "<= hi" at all) and must stay that
    # way: some operations need the assumption baked into the symbol
    # *while they're computing*, and only pick up symbol-level
    # assumptions, not the dynamic context below. An upper bound is
    # expressed a different way instead, additively: sympy's relational-
    # predicate system (Q.le/Q.ge, used inside `assuming()`) can state a
    # bound no fixed symbol-assumption keyword can, without touching how
    # the symbol itself was built above.
    bounds = []
    for p, sym in updated.items():
        if p in pinned:
            continue   # already a literal in `subs`; no symbol-level bound left to state
        ctx = domain_bound_context(sym, domain.get(p))
        if ctx is not None:
            bounds.append(ctx)
    bound_context = sympy.And(*bounds) if bounds else None
    return subs, bound_context, updated, pins


def _interval_predicate(sym, piece) -> "sympy.Basic":
    """`sym`'s membership in one interval piece, as an `And` of `Q.ge`/
    `Q.gt`/`Q.le`/`Q.lt`, the same boundary logic `_domain_assumptions`'
    own plain-`Interval` path already uses, factored out so a `Domain`'s
    own pieces (below) can reuse it, whether there's one piece or several
    to `Or` together."""
    lo, hi = piece
    lo_pred = sympy.Q.gt(sym, lo) if not getattr(piece, "closed_lo", True) else sympy.Q.ge(sym, lo)
    hi_pred = sympy.Q.lt(sym, hi) if not getattr(piece, "closed_hi", True) else sympy.Q.le(sym, hi)
    return sympy.And(lo_pred, hi_pred)


_DISPROOF_CORROBORATION_TRIALS = 25


def _point_satisfies_context(point: dict, bound_context, tol: float = 1e-9) -> bool:
    """Intent:
        Whether a concrete candidate point satisfies every checkable
        predicate in the proof's bound context, crucially including
        the `assuming` clause's own constraints (Q.zero for an assumed
        equality, Q.nonnegative/positive for an assumed ordering). A
        disproof witness hunted OFF the assumed surface refutes
        nothing, so every sampled candidate is filtered here first.

    Notes:
        A predicate whose argument cannot be evaluated numerically at
        the point does not block (domain membership is checked
        separately by the callers); an evaluable predicate that fails
        does. Binary relational predicates (Q.ge/gt/le/lt) and the
        unary sign/zero predicates are all handled.
    """
    if bound_context is None:
        return True
    from sympy.assumptions import AppliedPredicate
    for atom in bound_context.atoms(AppliedPredicate):
        name = atom.function.name
        try:
            args = [complex(a.subs(point).evalf()).real for a in atom.arguments]
        except (TypeError, ValueError, AttributeError):
            continue
        if any(v != v for v in args):
            continue
        if len(args) == 1:
            v = args[0]
            ok = {"zero": abs(v) <= tol, "nonzero": abs(v) > tol,
                  "nonnegative": v >= -tol, "positive": v > tol,
                  "nonpositive": v <= tol, "negative": v < -tol,
                  }.get(name, True)
        elif len(args) == 2:
            a, b = args
            ok = {"ge": a >= b - tol, "gt": a > b + tol,
                  "le": a <= b + tol, "lt": a < b - tol,
                  "eq": abs(a - b) <= tol, "ne": abs(a - b) > tol,
                  }.get(name, True)
        else:
            ok = True
        if not ok:
            return False
    return True


def _has_equality_constraint(bound_context) -> bool:
    """Whether the bound context carries an assumed EQUALITY (a Q.zero
    predicate from an `assuming A == B` conjunct): the feasible set is
    then a measure-zero surface, and any region- or interval-based
    disproof that never produced a concrete on-surface point is
    unsound to trust."""
    if bound_context is None:
        return False
    from sympy.assumptions import AppliedPredicate
    return any(atom.function.name == "zero"
               for atom in bound_context.atoms(AppliedPredicate))


def _piecewise_seed_points(diff, free: list, bounds: dict) -> list[dict]:
    """Intent:
        Points on the switching surfaces of `diff`'s Piecewise
        conditions, one coordinate per symbol in `free`: the surface
        solved for one symbol, the rest at the midpoint and ends of
        their sampling hull (0, 1 and -1 when unbounded). An integer
        symbol keeps only integer values. Empty when `diff` has no
        Piecewise, or the solve outruns the fast wall-clock cap.
    """
    if not diff.has(sympy.Piecewise):
        return []
    from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from ._guard_points import diff_surfaces, surface_points

    candidates: dict = {}
    for sym in free:
        hull = bounds.get(sym)
        values = ([(hull[0] + hull[1]) / 2, hull[0], hull[1]]
                  if hull is not None else [0.0, 1.0, -1.0])
        if getattr(sym, "is_integer", False):
            values = [round(v) for v in values]
        candidates[str(sym)] = list(dict.fromkeys(values))
    symbols = {str(sym): sym for sym in free}
    try:
        found = _with_timeout(
            lambda: surface_points(diff_surfaces(diff), symbols, candidates),
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return []
    out = []
    for point in found:
        full = {sym: point.get(str(sym), candidates[str(sym)][0])
                for sym in free}
        if all(not getattr(sym, "is_integer", False)
               or float(v).is_integer() for sym, v in full.items()):
            out.append(full)
    return out


def _corroborate_disproof(diff, domain: dict, params: dict,
                          bound_context=None, tolerance: float = 1e-9,
                          exact: bool = False):
    """A concrete counterexample point for `diff != 0`, found by the
    same seeded scalar sampler `probing.py`'s own probes use
    (`_synth_scalar`, `.._sampling`), `None` if none of
    `_DISPROOF_CORROBORATION_TRIALS` tries lands on one.

    `sympy.Expr.equals()` can return `False` via its own internal
    random sampling (`Expr._random()`), using a source of randomness
    this module doesn't control and can't reproduce: calling
    `diff.equals(0)` on the same `diff` several times in the same
    process can legitimately return `False` sometimes and `None`
    (undecided) other times, entirely independent of the declared
    domain. A "disproven" verdict reported to a caller should be
    reproducible, not a coin flip, so a claimed disproof is only
    trusted once this function finds an actual point where the
    difference is genuinely, numerically nonzero, sampled with a fixed
    seed inside the declared domain (or the same unbounded default
    `_synth_scalar` itself falls back to for a free symbol with no
    declared bound). If no such point turns up, the caller reports
    `undecided`, not `disproven`, the same conservative direction
    `_prove_relation`'s wall-clock cap already takes for a decision
    procedure that ran out of budget. A `diff` with no free symbols
    left (domain pinning or branch pruning already substituted every
    parameter to a concrete value) needs no sampling at all; it's
    already a plain number, and `equal is False` for it came from
    `diff.is_number`/`is_constant` deciding a genuine, unconditional
    nonzero value, not from `_random()`; confirmed directly by
    evaluating it, not treated as an un-corroborated guess the way an
    empty search would otherwise read.

    With `exact=True` a point qualifies when `diff`, evaluated in exact
    arithmetic at the sampled floats' own exact values, is provably
    nonzero there, however small; `tolerance` is then unused."""
    free = sorted(diff.free_symbols, key=str)
    if not free:
        if exact:
            return {} if diff.is_zero is False else None
        try:
            value = complex(diff.evalf())
        except (TypeError, ValueError):
            return None
        return {} if abs(value) > tolerance else None
    # an equality-shaped `assuming` clause makes the feasible set a
    # measure-zero surface: random draws essentially never land on it,
    # so rather than sampling blind, solve ONE variable out of one
    # equality constraint and sample the rest, every candidate then
    # sits exactly on the surface by construction
    solved_var = None
    if bound_context is not None and _has_equality_constraint(bound_context):
        from sympy.assumptions import AppliedPredicate
        for atom in bound_context.atoms(AppliedPredicate):
            if atom.function.name != "zero":
                continue
            surface = atom.arguments[0]
            for sym in sorted(surface.free_symbols & set(free), key=str):
                try:
                    sols = sympy.solve(sympy.Eq(surface, 0), sym)
                except Exception:
                    continue
                if len(sols) == 1:
                    solved_var = (sym, sols[0])
                    break
            if solved_var is not None:
                break
        if solved_var is not None:
            sym, expr = solved_var
            diff = diff.subs(sym, expr)
            free = sorted(diff.free_symbols, key=str)
    from ..domain import bound_to_sympy_set, domain_contains

    name_by_symbol = {sym: name for name, sym in params.items()}
    bounds = {}
    member_of = {}
    for sym in free:
        # a free symbol that isn't a parameter (a let-declared free
        # variable, a lim/Sum bound name) still carries its declared
        # domain under its own name; a counterexample must respect
        # every declared bound, not just the parameters'
        bound = domain.get(name_by_symbol.get(sym, str(sym)))
        member_of[sym] = bound
        if isinstance(bound, tuple):
            bounds[sym] = (float(bound[0]), float(bound[1]))
            continue
        bounds[sym] = None
        if bound is not None:
            # a richer bound (a typed Domain, a piece union): its hull
            # still confines the sampler, and exact membership is
            # re-checked point by point below
            try:
                sset = bound_to_sympy_set(bound)
                lo, hi = float(sset.inf), float(sset.sup)
                if math.isfinite(lo) and math.isfinite(hi):
                    bounds[sym] = (lo, hi)
            except (TypeError, ValueError, NotImplementedError):
                pass
    rng = random.Random(_RNG_SEED)

    def _drawn():
        point = {}
        for sym in free:
            v = _synth_scalar(rng, bounds[sym])
            if getattr(sym, "is_integer", False):
                v = round(v)
            point[sym] = v
        return point

    # a case-split difference can be nonzero only where one of its
    # Piecewise conditions switches arm (`Eq(x*y, 0)`), a set random
    # draws never land on: the solutions of those conditions inside the
    # domain are tried first
    seeds = _piecewise_seed_points(diff, free, bounds)
    for trial in range(len(seeds) + _DISPROOF_CORROBORATION_TRIALS):
        point = seeds[trial] if trial < len(seeds) else _drawn()
        if any(member_of[sym] is not None and not domain_contains(v, member_of[sym])
               for sym, v in point.items()):
            continue
        full_point = point
        if solved_var is not None:
            # reconstruct the solved-out coordinate so the witness is a
            # complete on-surface point, and hold it to its own bound
            sym, expr = solved_var
            try:
                sv = complex(expr.subs(point).evalf())
            except (TypeError, ValueError):
                continue
            if abs(sv.imag) > 1e-9:
                continue
            bound = domain.get(name_by_symbol.get(sym, str(sym)))
            if bound is not None and not domain_contains(sv.real, bound):
                continue
            full_point = {**point, sym: sv.real}
        if not _point_satisfies_context(full_point, bound_context):
            continue
        if exact:
            try:
                at = diff.subs({sym: sympy.Rational(v)
                                for sym, v in point.items()})
            except (TypeError, ValueError):
                continue
            if at.is_zero is False:
                return full_point
            continue
        try:
            value = complex(diff.subs(point).evalf())
        except (TypeError, ValueError):
            continue
        if abs(value) > tolerance:
            return full_point
    return None


def _representative_point(expr, domain: dict, params: dict,
                          bound_context=None) -> "dict | None":
    """Intent:
        One seeded in-domain point for every parameter and every free
        symbol of `expr`, respecting each declared bound and the
        assuming clause: the witness of a disproof that holds at every
        point of the domain, such as an ordering whose interval hull
        is negative throughout. Keys are the symbol names.

    Notes:
        The same seeded sampler `_corroborate_disproof` draws from,
        with a negative tolerance so the first admissible point
        qualifies. None when no admissible point turns up.
    """
    symbols = set(params.values()) | set(expr.free_symbols)
    if not symbols:
        return None
    point = _corroborate_disproof(sympy.Add(*symbols), domain, params,
                                  bound_context, tolerance=-1.0)
    if not point:
        return None
    return {str(sym): v for sym, v in point.items()}


def _prove_relation(lhs, rhs, relation: str, domain: dict, bound_context,
                    params: dict, opaque: "OpaqueRegistry | None" = None,
                    extensive: bool = False,
                    tolerance: float = 1e-9) -> ProofResult:
    """Decide `lhs <relation> rhs` for a single pair of (already-built)
    sympy expressions, the core of try_prove's proof procedure, factored
    out so a claim against a tuple-valued f(...) (a function returning more
    than one value) can apply it elementwise, once per position, rather
    than duplicating the logic. `domain`/`bound_context`/`params` are
    exactly try_prove's own, unchanged by the tuple case. `opaque`, when
    given, refuses an ordering relation (`<=`/`>=`) outright the moment
    either side touches a registered opaque (non-numeric) value; see
    OpaqueRegistry.is_opaque_symbol's own docstring for why this can't
    just be left to the generic sign-decidability machinery below (it
    would "prove" the degenerate same-value case via reflexivity, which
    is misleading: ordering was never meaningful to claim about a
    string or `None` in the first place, proven or not). Equality
    (`==`/`~=`) needs no such guard; it's already well-defined for an
    opaque value regardless.

    `extensive` sets the wall-clock cap on the whole decision procedure
    below (`simplify()`, `.equals()`, `factor()`, `ask()`, and everything
    else sympy might spend unbounded time on): 1 second by default, 15
    seconds when the caller opted into the wider search. A plain
    `.equals()` call in particular has no closed-form fallback of its
    own and can run unbounded on an equation sympy can't resolve. The
    cap wraps the whole procedure as one unit, not each sympy call
    individually, so nothing inside it runs unguarded."""
    if relation in ("<=", ">=", "<", ">") and opaque is not None \
            and any(opaque.is_opaque_symbol(s) for s in lhs.free_symbols | rhs.free_symbols):
        return ProofResult("undecided", sketch="ordering (<=/>=) isn't meaningful "
                           "for a non-numeric value")
    has_deferred = lhs.has(sympy.Integral) or rhs.has(sympy.Integral)
    timeout = (EXTENSIVE_TIMEOUT_SECONDS if (extensive or has_deferred)
               else FAST_TIMEOUT_SECONDS)
    # a deferred definite integral gets the wider cap even on the fast
    # path: its evaluation used to happen unbounded at parse time, and
    # a 3-second budget cut off real integrals that always closed.
    try:
        return _with_timeout(lambda: _decide_relation(
            lhs, rhs, relation, domain, bound_context, params, tolerance),
            timeout)
    except TimeoutError:
        return ProofResult("undecided", sketch=f"sympy could not settle "
                           f"{_humanize(lhs)} {relation} {_humanize(rhs)} "
                           "within the wall-clock cap",
                           meta={"mathema.timeout": "extensive" if extensive else "fast"})


def _decide_relation(lhs, rhs, relation: str, domain: dict, bound_context,
                     params: dict, tolerance: float = 1e-9) -> ProofResult:
    """The actual simplify/equals/ask decision procedure `_prove_relation`
    runs under a wall-clock cap; split out so the whole thing can be
    handed to `_with_timeout` as a single unit rather than guarding each
    sympy call inside it separately. The shared preamble below resolves
    the difference under the declared domain once; the per-relation
    decision lives in `_RELATION_DECIDERS` (equality, disequality,
    ordering), each independently testable."""
    deferred_diff = None
    if lhs.has(sympy.Integral) or rhs.has(sympy.Integral):
        # a deferred definite integral (see _law_to_sympy's integrate
        # branch) evaluates here, inside _prove_relation's wall-clock
        # cap; an integral sympy can't close stays an Integral atom and
        # the ladder's residue machinery gets its turn. The pre-
        # evaluation difference is kept: symbolic integration is known
        # to be wrong on some shapes (a discontinuous antiderivative
        # across the integration range), so a disproof that rests on
        # the evaluated form must survive numeric quadrature of the
        # original before it stands.
        deferred_diff = lhs - rhs
        try:
            lhs, rhs = _resolve_pv(lhs), _resolve_pv(rhs)
            lhs, rhs = lhs.doit(deep=True), rhs.doit(deep=True)
            lhs, rhs = _collapse_pv(lhs), _collapse_pv(rhs)
        except TimeoutError:
            raise
        except Exception:
            pass
    for side, other in ((lhs, rhs), (rhs, lhs)):
        if side in (sympy.oo, -sympy.oo):
            # an infinite side never survives subtraction (oo - oo is
            # nan), so equality decides structurally: the same infinity
            # is equal, a provably finite (or opposite-infinite) other
            # side is not, anything unresolved stays undecided.
            same = other == side
            other_finite = getattr(other, "is_finite", None)
            opposite = other in (sympy.oo, -sympy.oo) and other != side
            if relation in ("==", "~="):
                if same:
                    return ProofResult("proven", sketch=f"both sides are "
                                       f"{_humanize(side)}")
                if other_finite is True or opposite:
                    return ProofResult("disproven",
                                       sketch=f"{_humanize(lhs)} ≠ {_humanize(rhs)}: "
                                              "one side is infinite, the other is not "
                                              "that infinity")
                return ProofResult("undecided", sketch=f"cannot settle whether "
                                   f"{_humanize(other)} is {_humanize(side)}")
            if relation == "!=":
                if same:
                    return ProofResult("disproven", sketch=f"both sides are "
                                       f"{_humanize(side)}")
                if other_finite is True or opposite:
                    return ProofResult("proven",
                                       sketch=f"one side is {_humanize(side)}, the "
                                              "other provably is not")
                return ProofResult("undecided", sketch=f"cannot settle whether "
                                   f"{_humanize(other)} is {_humanize(side)}")
            return ProofResult("undecided", sketch="an infinite side has no "
                               "toleranced ordering to decide")
    diff = sympy.simplify(lhs - rhs)
    if bound_context is not None:
        # refine(), not simplify(): this specifically rewrites pieces
        # using the *assumed* facts, which plain simplify() has no
        # reason to attempt on its own since it doesn't know the
        # domain restricts anything at all. Handles what ask()'s own
        # relational inference does resolve (e.g. strict inequalities).
        diff = sympy.refine(diff, bound_context)
    # Min/Max clamps and Mod both need the direct domain-dict check
    # instead (see _resolve_clamps/_resolve_mod), ask()/refine() alone
    # don't reliably close a non-strict boundary-touching case, and
    # have no domain awareness for Mod at all.
    diff = _resolve_clamps(diff, domain, params)
    diff = _resolve_mod(diff, domain, params)
    # the exact collapses above first, then the lossy relaxation for the
    # integer parts they could not remove. It augments domain/params
    # with the auxiliaries it introduces, so the deciders below (and the
    # interval rung in particular) can see their bounds.
    unrelaxed_params = len(params)
    diff, domain, params = _resolve_int_parts(diff, domain, params)
    relaxed = len(params) != unrelaxed_params
    diff = _resolve_piecewise(diff, domain, params)
    diff = _resolve_zero_powers(diff, domain, params)
    diff = sympy.simplify(diff)
    decider = _RELATION_DECIDERS.get(relation)
    if decider is None:
        return ProofResult("undecided", sketch=f"relation {relation!r} not supported "
                           "by the derive route")
    result = decider(lhs, rhs, diff, relation, domain, bound_context, params,
                     tolerance)
    if relaxed and result.status == "disproven":
        return ProofResult(
            "undecided",
            sketch=f"{result.sketch}, but only over the relaxed integer "
                   f"parts (each floor, ceiling and remainder replaced by "
                   f"an independent bounded value), which is no disproof "
                   f"of the original")
    if deferred_diff is not None and result.status == "disproven":
        quad = _quadrature_confirms_nonzero(deferred_diff, domain, params)
        if quad is False:
            return ProofResult(
                "undecided",
                sketch="symbolic integration disagrees with numeric "
                       "quadrature of the same integral (a known sympy "
                       "failure shape: a discontinuous antiderivative "
                       "evaluated across the range), so the symbolic "
                       f"disproof does not stand; symbolic value gave "
                       f"{_humanize(diff)}")
        if quad is None:
            return ProofResult(
                "undecided",
                sketch="a disproof resting on symbolic integration needs "
                       "independent confirmation, and numeric quadrature "
                       "of the original integral could not evaluate here "
                       f"-- left undecided; symbolic value gave "
                       f"{_humanize(diff)}")
    return result


def _is_pv_application(e) -> bool:
    return (isinstance(e, sympy.core.function.AppliedUndef)
            and e.func.__name__ == "P.V." and len(e.args) == 1)


def _resolve_pv(expr):
    """Intent:
        Evaluate each `PV(Integral(...))` marker through sympy's own
        `Integral.principal_value()`, leaving unresolvable ones in
        place for the residue machinery.
    """
    if not expr.has(sympy.core.function.AppliedUndef):
        return expr

    def swap(app):
        (arg,) = app.args
        if isinstance(arg, sympy.Integral):
            try:
                value = arg.principal_value()
            except TimeoutError:
                raise
            except Exception:
                return app
            if value is not None and not value.has(sympy.Integral, sympy.nan):
                return value
        return app

    return expr.replace(_is_pv_application, swap)


def _collapse_pv(expr):
    """Intent:
        Strip a `PV(...)` marker whose inner integral already evaluated
        to a closed form: a convergent integral's principal value IS
        its value, so the wrapper carries no further information.
    """
    if not expr.has(sympy.core.function.AppliedUndef):
        return expr
    return expr.replace(
        lambda e: _is_pv_application(e) and not e.args[0].has(sympy.Integral),
        lambda e: e.args[0])


def _quadrature_confirms_nonzero(deferred_diff, domain: dict, params: dict) -> "bool | None":
    """Intent:
        Does direct numeric quadrature of the pre-evaluation difference
        (its `Integral` atoms integrated numerically, never through an
        antiderivative) agree that it is nonzero at sampled points of
        the declared domain?

    Notes:
        `True` only when every point that evaluates cleanly comes out
        decisively nonzero and at least one did; `False` when any point
        evaluates decisively to zero (the claim holds there, so a
        symbolic disproof is contradicted); `None` when nothing
        evaluates (no verdict either way, the caller treats that as
        unconfirmed). Values within 1e-6 of zero count as zero:
        quadrature error is larger than the usual 1e-9 comparison
        slack.
    """
    free = sorted(deferred_diff.free_symbols, key=str)
    name_by_symbol = {sym: name for name, sym in params.items()}
    bounds = {}
    for sym in free:
        lo_hi = domain.get(name_by_symbol.get(sym))
        bounds[sym] = ((float(lo_hi[0]), float(lo_hi[1]))
                       if isinstance(lo_hi, tuple) else None)
    rng = random.Random(_RNG_SEED)
    confirmed = 0
    for _ in range(_DISPROOF_CORROBORATION_TRIALS):
        point = {sym: _synth_scalar(rng, bounds[sym]) for sym in free}
        try:
            value = complex(deferred_diff.subs(point).evalf())
        except TimeoutError:
            raise
        except Exception:
            continue
        if abs(value) < 1e-6:
            return False
        confirmed += 1
    if not free:
        try:
            value = complex(deferred_diff.evalf())
            return abs(value) >= 1e-6
        except TimeoutError:
            raise
        except Exception:
            return None
    return True if confirmed else None


_BOUNDED_FUNCTION_RANGES = {
    # global ranges over the reals, used when sympy's own AccumBounds
    # propagation leaves a call unevaluated: replacing f(<anything
    # real>) by f's whole range is a sound over-approximation for
    # interval evaluation (the true range of the composite is contained
    # in what the replacement yields). Non-strict endpoints are fine:
    # the pass only ever proves non-strict relations.
    sympy.erf: (-1, 1),
    sympy.erfc: (0, 2),
    sympy.tanh: (-1, 1),
    sympy.sin: (-1, 1),
    sympy.cos: (-1, 1),
    sympy.atan: (-sympy.pi / 2, sympy.pi / 2),
}


def _collapse_accumbounds(e):
    """Explicit interval arithmetic over an expression tree containing
    `AccumBounds` leaves: Add sums endpoints, Mul takes the min/max of
    the four endpoint products (a comparable constant factor keeps its
    sign-directed short form), an integer Pow goes through repeated
    products. Returns an `AccumBounds` (or a plain comparable constant),
    or `None` for any shape this doesn't cover, never a guess: every
    combination rule here is the textbook interval-arithmetic hull, so
    the result always CONTAINS the true range."""
    def as_bounds(v):
        if isinstance(v, sympy.AccumBounds):
            return v.min, v.max
        return v, v

    def comparable(v):
        try:
            return bool(v.is_comparable)
        except TimeoutError:
            raise
        except Exception:
            return False

    def walk(node):
        if isinstance(node, sympy.AccumBounds):
            return node if comparable(node.min) and comparable(node.max) else None
        if not node.has(sympy.AccumBounds):
            return node if comparable(node) else None
        if isinstance(node, sympy.Add):
            lo = sympy.Integer(0)
            hi = sympy.Integer(0)
            for arg in node.args:
                part = walk(arg)
                if part is None:
                    return None
                p_lo, p_hi = as_bounds(part)
                lo, hi = lo + p_lo, hi + p_hi
            return sympy.AccumBounds(lo, hi) if lo != hi else lo
        if isinstance(node, sympy.Mul):
            lo, hi = sympy.Integer(1), sympy.Integer(1)
            for arg in node.args:
                part = walk(arg)
                if part is None:
                    return None
                p_lo, p_hi = as_bounds(part)
                products = [lo * p_lo, lo * p_hi, hi * p_lo, hi * p_hi]
                try:
                    lo, hi = sympy.Min(*products), sympy.Max(*products)
                    if not (comparable(lo) and comparable(hi)):
                        return None
                except TimeoutError:
                    raise
                except Exception:
                    return None
            return sympy.AccumBounds(lo, hi) if lo != hi else lo
        if (isinstance(node, sympy.Pow) and not node.base.has(sympy.AccumBounds)
                and node.exp.has(sympy.AccumBounds)):
            # c**[lo, hi] for a comparable base: monotone in the
            # exponent, increasing for c > 1, decreasing for 0 < c < 1.
            exp_part = walk(node.exp)
            if exp_part is None or not comparable(node.base):
                return None
            e_lo, e_hi = as_bounds(exp_part)
            try:
                if bool(node.base > 1):
                    return sympy.AccumBounds(node.base ** e_lo, node.base ** e_hi)
                if bool(node.base > 0) and bool(node.base < 1):
                    return sympy.AccumBounds(node.base ** e_hi, node.base ** e_lo)
            except TypeError:
                return None
            return None
        if isinstance(node, sympy.Pow) and node.exp.is_Integer and node.exp > 0:
            base = walk(node.base)
            if base is None:
                return None
            acc = base
            for _ in range(int(node.exp) - 1):
                b_lo, b_hi = as_bounds(base)
                a_lo, a_hi = as_bounds(acc)
                products = [a_lo * b_lo, a_lo * b_hi, a_hi * b_lo, a_hi * b_hi]
                acc = sympy.AccumBounds(sympy.Min(*products), sympy.Max(*products))
            return acc
        return None

    try:
        return walk(e)
    except TimeoutError:
        raise
    except Exception:
        return None


def _exact_endpoint(v):
    """Intent:
        The decimal reading of an interval endpoint: a `sympy.Float`
        becomes the exact rational its decimal spelling names.

    Notes:
        A declared bound arrives as a float (2.0, 0.1); the number the
        claim names is its decimal reading. Rationalizing it keeps
        endpoint arithmetic exact, so an attained bound collapses to a
        true zero (log(2)/log(2) - 1 == 0) instead of float noise the
        sign check can't call. Anything that is not a Float passes
        through unchanged.
    """
    if isinstance(v, sympy.Float):
        try:
            return sympy.nsimplify(v, rational=True)
        except TimeoutError:
            raise
        except Exception:
            return v
    return v


def _has_sequence_structure(expr) -> bool:
    """Whether `expr` carries sequence structure a real-interval box
    cannot soundly stand in for: an indexed element, a sequence base
    label, or a Sum/Product over one. See `_interval_bounds`'s own
    decline for why this is not a scalar question."""
    if expr.has(sympy.Indexed, sympy.IndexedBase, sympy.Sum, sympy.Product):
        return True
    # a base label reaches free_symbols as a plain Symbol (IndexedBase
    # ('a').free_symbols is {Symbol('a')}), so a tree that mentions any
    # base is caught by name even where the Indexed itself was rewritten
    bases = {b.label for b in expr.atoms(sympy.IndexedBase)}
    bases |= {i.base.label for i in expr.atoms(sympy.Indexed)}
    return bool(bases & expr.free_symbols)


def _sound_interval_result(result) -> bool:
    """Intent:
        Whether an interval evaluation produced a genuine numeric hull,
        as opposed to a corrupted tree that merely answers `is_number`.

    Notes:
        `is_number`/`is_comparable` are not proxies for "this is a real
        interval": `Sum(0, (i, 0, AccumBounds(-oo, oo)))` answers True
        to both and evaluates to 0, which is the maximally wrong hull
        (it reads as "identically zero", proving a claim and its
        negation together). Structure that must never survive into a
        hull: a Sum/Product (a range is not a quantity), an Indexed, or
        an AccumBounds sitting in a summation limit.

        Belt and braces beside `_interval_bounds`'s own decline,
        because nothing backstops a wrong PROOF in this class: the
        corroboration gate only re-checks disproofs, and a proof's
        `[float]` companion tests the implementation rather than the
        proof, so a wrong proof here reaches the record with nothing to
        catch it.
    """
    if result is None:
        return False
    if result.has(sympy.Sum, sympy.Product, sympy.Indexed, sympy.IndexedBase):
        return False
    for s in result.atoms(sympy.Sum, sympy.Product):
        for limit in getattr(s, "limits", ()):
            if any(part.has(sympy.AccumBounds) for part in limit[1:]):
                return False
    return True


def _interval_bounds(expr, domain: dict, params: dict):
    """Rigorous interval evaluation of `expr` over the declared domain
    box: every parameter substituted with the `AccumBounds` hull of its
    declared bound ((-oo, oo) when nothing is declared), bounded
    functions sympy can't propagate through (erf, tanh, ...) replaced
    by their global ranges. Returns an `AccumBounds` (or an exact
    number, when the box collapses) whose interval CONTAINS the
    expression's true range over the domain, so `min >= 0` proves
    nonnegativity everywhere and `max < 0` proves negativity
    everywhere, while an interval straddling zero decides nothing
    (interval arithmetic over-approximates; the dependency problem
    only ever widens the answer, never narrows it). `None` when the
    evaluation doesn't produce a clean bound at all."""
    from ..domain import bound_to_sympy_set
    _exact = _exact_endpoint

    if expr.has(sympy.Piecewise):
        # a box substituted into a Piecewise CONDITION is meaningless
        # (Eq(AccumBounds, 0) collapses to an arbitrary branch, a
        # false proof observed live); condition resolution belongs to
        # _resolve_piecewise, which runs before the deciders. Anything
        # still conditional here has an undecidable guard: decline.
        return None

    box = {}
    for p, sym in params.items():
        bound = domain.get(p)
        if bound == "C" or getattr(bound, "base_type", None) == "C":
            # a complex parameter has no real hull at all: substituting
            # a real AccumBounds for it would assert a real range it
            # doesn't have. The whole evaluation declines.
            return None
        if bound is None:
            lo, hi = -sympy.oo, sympy.oo
        else:
            try:
                sset = bound_to_sympy_set(bound)
                lo, hi = _exact(sset.inf), _exact(sset.sup)
            except TimeoutError:
                raise
            except Exception:
                lo, hi = -sympy.oo, sympy.oo
        box[sym] = sympy.AccumBounds(lo, hi) if lo != hi else lo
    if _has_sequence_structure(expr):
        # interval evaluation is a SCALAR technique: it bounds an
        # expression by substituting a real interval for each real
        # quantity. A sequence is not a real quantity, and its base
        # label denotes a function from indices to reals, so boxing it
        # asserts something meaningless. Worse, two different sequences
        # boxed with the same interval become the same object, and
        # `a[i] - b[i]` cancels to a literal 0: a hull of exactly zero,
        # which reads downstream as "this difference is identically
        # zero" and proves a claim and its negation at once. Sequence
        # claims are decided termwise instead (`_termwise_sum_decide`),
        # where each element gets its own bounded symbol.
        return None

    # aux symbols (free variables the claim introduced) have no declared
    # box here; treat them as unbounded so the answer stays sound.
    for s in expr.free_symbols:
        if s not in box:
            box[s] = sympy.AccumBounds(-sympy.oo, sympy.oo)
    return _interval_hull(expr, box)


def _min_max_hull(e):
    """Intent:
        The interval hull of a `Min`/`Max` whose arguments are each an
        `AccumBounds` [lo_k, hi_k] or a comparable real number (the
        interval [c, c]): `Min` lies in [min lo_k, min hi_k], `Max` in
        [max lo_k, max hi_k].

    Notes:
        Both ends are attained (every argument at its low end gives the
        low end, every argument at its high end the high end), so the
        hull is exact for independent arguments and contains the true
        range otherwise. `None` when an argument is neither, an
        unevaluated function of an interval, say, which bounds nothing.
    """
    lows, highs = [], []
    for arg in e.args:
        if isinstance(arg, sympy.AccumBounds):
            lo, hi = arg.min, arg.max
        else:
            lo = hi = arg
        for end in (lo, hi):
            if not (end.is_comparable or end in (-sympy.oo, sympy.oo)):
                return None
        lows.append(lo)
        highs.append(hi)
    pick = sympy.Min if isinstance(e, sympy.Min) else sympy.Max
    lo, hi = pick(*lows), pick(*highs)
    return sympy.AccumBounds(lo, hi) if lo != hi else lo


def _interval_hull(expr, box: dict):
    """Intent:
        The AccumBounds hull of `expr` over an explicit box of
        `{symbol: AccumBounds-or-value}`, the evaluation half of
        `_interval_bounds`, reusable on a sub-box during interval
        refinement.

    Notes:
        Same contract as `_interval_bounds`: the returned interval
        CONTAINS the true range (or is an exact number when the box
        collapses); `None` when evaluation produces nothing clean.
        Declines outright on a Piecewise (same reasoning as
        `_interval_bounds`: a box in a condition collapses to an
        arbitrary branch) and on an expression too large to evaluate
        within a deterministic operation budget, the multi-term
        radical shapes whose per-cell substitution otherwise runs
        unbounded during interval refinement.
    """
    if expr.has(sympy.Piecewise):
        return None
    try:
        if sympy.count_ops(expr) > 400:
            return None
    except Exception:
        return None
    try:
        result = expr.subs(box, simultaneous=True)
        if result.has(sympy.AccumBounds) and not isinstance(result, sympy.AccumBounds):
            # Abs, Min and Max propagate by hand (sympy leaves them
            # unevaluated over an AccumBounds), innermost first. Abs is
            # the image of [lo, hi] under |.| exactly; Min and Max are
            # `_min_max_hull`.
            def _abs_swap(e):
                ab = e.args[0]
                lo, hi = ab.min, ab.max
                if lo >= 0:
                    return sympy.AccumBounds(lo, hi)
                if hi <= 0:
                    return sympy.AccumBounds(-hi, -lo)
                return sympy.AccumBounds(0, sympy.Max(-lo, hi))

            def _swap_one(e):
                if isinstance(e, sympy.Abs):
                    return _abs_swap(e)
                hull = _min_max_hull(e)
                return e if hull is None else hull
            result = result.replace(
                lambda e: (isinstance(e, sympy.Abs)
                           and isinstance(e.args[0], sympy.AccumBounds))
                or (isinstance(e, (sympy.Min, sympy.Max))
                    and e.has(sympy.AccumBounds)), _swap_one)
        if result.has(sympy.AccumBounds) and not isinstance(result, sympy.AccumBounds):
            # a bounded call sympy left unevaluated (erf(AccumBounds(...))
            # and friends): swap in the function's global range and let
            # the surrounding arithmetic re-propagate.
            def _swap(e):
                lo, hi = _BOUNDED_FUNCTION_RANGES[e.func]
                return sympy.AccumBounds(lo, hi)
            result = result.replace(
                lambda e: getattr(e, "func", None) in _BOUNDED_FUNCTION_RANGES
                and e.has(sympy.AccumBounds), _swap)
        if result.has(sympy.AccumBounds) and not isinstance(result, sympy.AccumBounds):
            # a subs-produced tree can freeze (`AccumBounds(...)/log(10)
            # - 1` stays an unevaluated Add), and sympy's own AccumBounds
            # algebra doesn't reliably re-propagate through it, collapse
            # the common Add/Mul/Pow shapes with explicit, rigorous
            # endpoint arithmetic instead.
            collapsed = _collapse_accumbounds(result)
            if collapsed is not None:
                result = collapsed
    except TimeoutError:
        raise
    except Exception:
        return None
    if not _sound_interval_result(result):
        # the result answers is_number but is not a real hull; see
        # `_sound_interval_result`. Declining here costs nothing (the
        # caller treats None as "decided nothing") and is the only
        # thing standing between a corrupted hull and a verdict.
        return None
    if isinstance(result, sympy.AccumBounds):
        if result.min.is_comparable and result.max.is_comparable:
            return result
        return None
    if getattr(result, "is_number", False) and result.is_comparable:
        return result
    return None


def _constant_by_derivative(diff, domain: dict, params: dict):
    """Intent:
        Decide `diff == 0` for a differentiable expression over a
        connected interval box by the classic argument: if every
        partial derivative simplifies to zero, `diff` is constant
        there, and one exact evaluation at an interior rational point
        settles which constant.

    Notes:
        `True`/`False` only when everything discharges exactly (all
        free symbols interval-bounded, all partials provably zero, the
        point value exactly zero or exactly not); `None` otherwise;
        in particular for a nonzero derivative, which says nothing
        about equality at any single point.
    """
    from ..domain import bound_to_sympy_set

    point = {}
    ranges = {}
    for name, sym in params.items():
        if sym not in diff.free_symbols:
            continue
        bound = domain.get(name)
        if bound is None:
            return None
        try:
            sset = bound_to_sympy_set(bound)
            lo, hi = _exact_endpoint(sset.inf), _exact_endpoint(sset.sup)
        except TimeoutError:
            raise
        except Exception:
            return None
        if not (getattr(lo, "is_finite", False) and getattr(hi, "is_finite", False)):
            return None
        mid = (lo + hi) / 2
        if not getattr(mid, "is_rational", False):
            return None
        point[sym] = mid
        ranges[sym] = (lo, hi)
    if any(s not in point for s in diff.free_symbols):
        return None
    for sym in point:
        try:
            partial = sympy.simplify(sympy.diff(diff, sym))
        except TimeoutError:
            raise
        except Exception:
            return None
        if not partial.is_zero:
            return None
    # constant established: one exact evaluation decides which
    # constant. Landmark values (1, 0, -1, 1/2) go first, inverse
    # trig evaluates exactly there (atan(1) = pi/4) where a midpoint
    # gives only an unresolvable transcendental sum.
    candidates = [point]
    for landmark in (sympy.Integer(1), sympy.Integer(0),
                     sympy.Integer(-1), sympy.Rational(1, 2)):
        alt = {}
        for sym, (lo, hi) in ranges.items():
            inside = False
            try:
                inside = bool(lo <= landmark) and bool(landmark <= hi)
            except TypeError:
                pass
            alt[sym] = landmark if inside else point[sym]
        candidates.insert(0, alt)
    for at in candidates:
        try:
            value = sympy.simplify(diff.subs(at))
        except TimeoutError:
            raise
        except Exception:
            continue
        if value.is_zero:
            return True
        sign = _verified_sign(value)
        if sign in (1, -1):
            return False
    return None


def _verified_sign(value):
    """Intent:
        The sign of a constant sympy expression (1, 0, -1, or None),
        never trusting sympy's boolean relationals or sign assumptions
        for a transcendental value.

    Notes:
        sympy's `bool(v >= 0)`/`.is_negative` machinery evaluates at
        fixed low precision internally and can report the WRONG sign
        with full confidence near a cancellation (observed live:
        tan(theta) a hair below pi/2; evalf(30) says +5.1e16,
        `is_negative` says True). Exact zero and rational values decide
        structurally; everything else must agree at two working
        precisions (30 and 50 digits) or the answer is None, an
        undecided, never a confidently wrong verdict.
    """
    if value.is_zero:
        return 0
    if getattr(value, "is_rational", False):
        return 1 if value > 0 else -1
    try:
        a, b = value.evalf(30), value.evalf(50)
        if a.is_comparable and b.is_comparable:
            fa, fb = float(a), float(b)
            if fa > 0 and fb > 0:
                return 1
            if fa < 0 and fb < 0:
                return -1
            if fa == 0 and fb == 0:
                return 0
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _relational_truth_over_domain(cond, domain: dict, params: dict):
    """Intent:
        Decide one sympy relational (or And/Or of them) over the
        declared domain box: True when it holds everywhere, False when
        it holds nowhere, None when the box doesn't settle it.

    Notes:
        The workhorse for resolving a piecewise lift's conditions: each
        f(...) call substituted its OWN argument into the guards, so
        deciding `2*x >= 0` over x's declared domain selects that
        call's branch correctly, branch selection following the
        argument, which a single-branch lift cannot do.
    """
    if cond is sympy.true:
        return True
    if cond is sympy.false:
        return False
    if isinstance(cond, sympy.And):
        parts = [_relational_truth_over_domain(a, domain, params) for a in cond.args]
        if any(p is False for p in parts):
            return False
        return True if all(p is True for p in parts) else None
    if isinstance(cond, sympy.Or):
        parts = [_relational_truth_over_domain(a, domain, params) for a in cond.args]
        if any(p is True for p in parts):
            return True
        return False if all(p is False for p in parts) else None
    if isinstance(cond, sympy.Not):
        inner = _relational_truth_over_domain(cond.args[0], domain, params)
        return None if inner is None else not inner
    if not isinstance(cond, sympy.core.relational.Relational):
        return None
    gap = cond.lhs - cond.rhs
    bounds = _interval_bounds(gap, domain, params)
    if bounds is None:
        return None
    lo = bounds.min if isinstance(bounds, sympy.AccumBounds) else bounds
    hi = bounds.max if isinstance(bounds, sympy.AccumBounds) else bounds
    lo_sign, hi_sign = _verified_sign(lo), _verified_sign(hi)
    if isinstance(cond, sympy.Eq):
        # equality holds nowhere when the gap's hull excludes zero, and
        # everywhere only when the gap is identically zero
        if lo_sign == 1 or hi_sign == -1:
            return False
        if lo == hi and lo_sign == 0:
            return True
        return None
    if isinstance(cond, sympy.Ne):
        if lo_sign == 1 or hi_sign == -1:
            return True
        if lo == hi and lo_sign == 0:
            return False
        return None
    if isinstance(cond, sympy.Ge):
        if lo_sign in (0, 1):
            return True
        if hi_sign == -1:
            return False
    elif isinstance(cond, sympy.Gt):
        if lo_sign == 1:
            return True
        if hi_sign in (0, -1):
            # the hull's max is <= 0, so the strict `> 0` holds nowhere
            return False
    elif isinstance(cond, sympy.Le):
        if hi_sign in (0, -1):
            return True
        if lo_sign == 1:
            return False
    elif isinstance(cond, sympy.Lt):
        if hi_sign == -1:
            return True
        if lo_sign in (0, 1):
            # the hull's min is >= 0, so the strict `< 0` holds nowhere
            return False
    return None


def _resolve_zero_powers(diff, domain: dict, params: dict):
    """Intent:
        Collapse `0**e` to 0 when the declared domain proves the
        exponent strictly positive, sympy leaves the power
        unevaluated on a bare positivity assumption (`0**(shape - 1)`
        with shape merely positive), and `.equals()` then wrongly
        insists the whole product is nonzero.
    """
    zero_pows = [p for p in diff.atoms(sympy.Pow)
                 if p.base is sympy.S.Zero]
    if not zero_pows:
        return diff
    subs = {}
    for p in zero_pows:
        bounds = _interval_bounds(p.exp, domain, params)
        if bounds is None:
            continue
        lo = bounds.min if isinstance(bounds, sympy.AccumBounds) else bounds
        if _verified_sign(lo) == 1:
            subs[p] = sympy.S.Zero
    return diff.xreplace(subs) if subs else diff


def _resolve_piecewise(diff, domain: dict, params: dict):
    """Intent:
        Collapse every `Piecewise` whose conditions the declared domain
        decides, the decision-time completion of the piecewise lift:
        conditions carry each call's own substituted argument, so this
        is where the right branch per call gets selected.

    Notes:
        A condition the domain can't settle stays symbolic (sympy keeps
        the piece); soundness never depends on collapsing.
    """
    if not diff.has(sympy.Piecewise):
        return diff

    def swap(pw):
        pieces = []
        for value, cond in pw.args:
            truth = _relational_truth_over_domain(cond, domain, params)
            if truth is True:
                pieces.append((value, sympy.true))
                break
            if truth is False:
                continue
            pieces.append((value, cond))
        if not pieces:
            return pw
        try:
            return sympy.Piecewise(*pieces)
        except TimeoutError:
            raise
        except Exception:
            return pw

    try:
        return diff.replace(lambda e: isinstance(e, sympy.Piecewise), swap)
    except TimeoutError:
        raise
    except Exception:
        return diff


def _interval_sign(expr, domain: dict, params: dict) -> bool | None:
    """`True` when interval evaluation proves `expr >= 0` everywhere on
    the declared box, `False` when it proves `expr < 0` everywhere,
    `None` when the interval straddles zero or evaluation failed."""
    bounds = _interval_bounds(expr, domain, params)
    if bounds is None:
        return None
    lo = bounds.min if isinstance(bounds, sympy.AccumBounds) else bounds
    hi = bounds.max if isinstance(bounds, sympy.AccumBounds) else bounds
    lo_sign, hi_sign = _verified_sign(lo), _verified_sign(hi)
    if lo_sign in (0, 1):
        return True
    if hi_sign == -1:
        return False
    return None


def _assumption_rewrites(bound_context) -> list:
    """Intent:
        Substitutions an `assuming` clause licenses, read back off the
        Q-predicates try_prove folded into bound_context: for
        `Q.nonnegative(E - k)` the subtree E may be replaced by
        `t + k` with t a nonnegative dummy (positive for Q.positive),
        and `Q.zero(E - k)` pins E to k exactly, turning an
        assumption the hull machinery can't see into structure it can.

    Notes:
        Each pair is (subtree, replacement); substituting is sound
        because the replacement ranges over a SUPERSET of the values
        the assumption allows the subtree, independent of the other
        variables.
    """
    out: list = []
    if bound_context is None:
        return out
    try:
        atoms = bound_context.atoms(sympy.AppliedPredicate)
    except TimeoutError:
        raise
    except Exception:
        return out
    for ap in atoms:
        try:
            pred, args = ap.function, ap.arguments
        except TimeoutError:
            raise
        except Exception:
            continue
        if len(args) != 1:
            continue
        (arg,) = args
        if pred not in (sympy.Q.nonnegative, sympy.Q.positive, sympy.Q.zero):
            continue
        try:
            const, rest = arg.as_coeff_Add()
        except TimeoutError:
            raise
        except Exception:
            continue
        if rest == 0:
            continue
        if pred == sympy.Q.zero:
            out.append((rest, -const))
        else:
            t = sympy.Dummy("assumed",
                            positive=(pred == sympy.Q.positive),
                            nonnegative=True)
            out.append((rest, t - const))
    return out


def _positive_certificate(expr, domain: dict, params: dict,
                          _depth: int = 0) -> "str | None":
    """Intent:
        A rigorous STRICT positivity certificate: proof that `expr > 0`
        everywhere on the declared box, for the shapes the plain hull
        straddles. The strict sibling of `_nonneg_certificate`, needed
        wherever a zero must be excluded outright, an `Eq(G, 0)`
        raise guard, a strict `>` claim.

    Notes:
        Sound rules only, each with every side condition verified:
        a hull whose min is strictly positive; a sum of nonnegative
        terms at least one of which is strictly positive
        ((k - m*w^2)^2 + (c*w)^2 with c bounded away from 0); a
        product of strictly positive factors; a quadratic in one
        variable with strictly positive leading coefficient and
        strictly negative discriminant. Returns the certificate text
        or None, never a "probably".
    """
    if _depth > 2:
        return None
    try:
        bounds = _interval_bounds(expr, domain, params)
    except TimeoutError:
        raise
    except Exception:
        bounds = None
    if bounds is not None:
        lo = bounds.min if isinstance(bounds, sympy.AccumBounds) else bounds
        if _verified_sign(lo) == 1:
            return (f"{_humanize(expr)} has a strictly positive interval "
                    f"hull over the declared domain")

    if isinstance(expr, sympy.Add):
        # note: one strictly positive term plus nonnegative company is
        # strictly positive, the common sum-of-squares-with-a-margin
        # shape
        positive_term = None
        for term in expr.args:
            if positive_term is None \
                    and _positive_certificate(term, domain, params,
                                              _depth + 1) is not None:
                positive_term = term
                continue
            if _interval_sign(term, domain, params) is not True \
                    and _nonneg_certificate(term, domain, params,
                                            _depth + 1) is None:
                return None
        if positive_term is not None:
            return (f"{_humanize(expr)} is a sum of nonnegative terms with "
                    f"{_humanize(positive_term)} strictly positive")
        return None

    if isinstance(expr, sympy.Mul):
        for factor in expr.args:
            if _positive_certificate(factor, domain, params,
                                     _depth + 1) is None:
                return None
        return f"{_humanize(expr)} is a product of strictly positive factors"

    for v in sorted(expr.free_symbols, key=str):
        try:
            poly = sympy.Poly(expr, v)
        except TimeoutError:
            raise
        except Exception:
            continue
        if poly.degree() != 2:
            continue
        a, b, c = poly.all_coeffs()
        disc = sympy.expand(b * b - 4 * a * c)
        try:
            disc_bounds = _interval_bounds(disc, domain, params)
        except TimeoutError:
            raise
        except Exception:
            continue
        if disc_bounds is None:
            continue
        disc_hi = disc_bounds.max if isinstance(disc_bounds, sympy.AccumBounds) \
            else disc_bounds
        if _positive_certificate(a, domain, params, _depth + 1) is not None \
                and _verified_sign(disc_hi) == -1:
            return (f"strictly positive as a quadratic in {v}: leading "
                    f"coefficient {_humanize(a)} > 0 and discriminant "
                    f"{_humanize(disc)} < 0 over the declared domain")
    return None


def _nonneg_certificate(expr, domain: dict, params: dict,
                        _depth: int = 0) -> str | None:
    """Intent:
        A rigorous nonnegativity certificate for an expression the
        plain interval hull can't settle (the dependency problem: the
        same variable appearing in terms of both signs). Two classical
        mechanisms, both built on the interval machinery so every side
        condition is verified, never assumed:

        1. Quadratic certificate: viewed as a quadratic a*v^2+b*v+c in
           one of its variables, the expression is nonnegative for ALL
           real v, bounded domain or not, when a >= 0, c >= 0, and
           the discriminant b^2-4ac <= 0 hold over the rest of the box
           (a positive-semidefinite form: 2*s1^2+2*s2^2-4*rho*s1*s2
           with |rho| <= 1 is the motivating shape).
        2. Monotone endpoint pinning: a variable whose partial
           derivative is verified one-signed over the whole box takes
           its minimizing endpoint, shrinking the problem; the hull
           and the quadratic certificate then retry on the smaller
           expression.

    Notes:
        Returns the human-readable certificate text when nonnegativity
        is proven, `None` otherwise, never a "probably". Every sign
        used (leading coefficient, discriminant, partial derivative)
        is decided by `_interval_sign`, so an undecidable side
        condition just declines. Purely algebraic and bounded: no
        `solve`/`simplify` calls, so no wall-clock hazard beyond the
        caller's own cap.

        Sound under a case-split call, which narrows the domain via
        bound_context only: every mechanism here proves nonnegativity
        over the FULL declared box, a superset of any piece. That
        superset argument is also why pinning demands the expression be
        polynomial in the pinned variable, the endpoint-minimum
        inference needs continuity on the closed interval, which a pole
        inside the box breaks even though the derivative is one-signed
        at every point where it exists.
    """
    from ..domain import bound_to_sympy_set

    def side_nonneg(e):
        # a side condition (leading coefficient, constant term, negated
        # discriminant) may itself be a form only this certificate can
        # settle; one level of bounded recursion, hull first
        if _interval_sign(e, domain, params) is True:
            return True
        return (_depth < 2
                and _nonneg_certificate(e, domain, params, _depth + 1) is not None)

    def quadratic(e):
        for v in sorted(e.free_symbols, key=str):
            try:
                poly = sympy.Poly(e, v)
            except TimeoutError:
                raise
            except Exception:
                continue
            if poly.degree() != 2:
                continue
            a, b, c = poly.all_coeffs()
            disc = sympy.expand(b * b - 4 * a * c)
            if side_nonneg(a) and side_nonneg(c) and side_nonneg(-disc):
                return (f"nonnegative as a quadratic in {v}: leading "
                        f"coefficient {_humanize(a)} >= 0 and discriminant "
                        f"{_humanize(disc)} <= 0 over the declared domain, "
                        f"so the form has no real root to cross zero at")
        return None

    found = quadratic(expr)
    if found is not None:
        return found

    current = expr
    pinned = []
    changed = True
    while changed:
        changed = False
        for name, sym in params.items():
            if sym not in current.free_symbols:
                continue
            bound = domain.get(name)
            if bound is None:
                continue
            try:
                sset = bound_to_sympy_set(bound)
                lo, hi = _exact_endpoint(sset.inf), _exact_endpoint(sset.sup)
            except TimeoutError:
                raise
            except Exception:
                continue
            if not (getattr(lo, "is_finite", False)
                    and getattr(hi, "is_finite", False)):
                continue
            try:
                if current.as_poly(sym) is None:
                    # "one-signed derivative => minimum at an endpoint"
                    # needs continuity on the CLOSED interval, which a
                    # pole inside the box silently breaks (1/x has
                    # -1/x^2 <= 0 everywhere it exists, yet no minimum
                    # at the right endpoint, a false proof caught in
                    # dev). Polynomial in the pinned variable is the
                    # cheap sufficient condition, and it also keeps the
                    # endpoint substitution finite.
                    continue
            except TimeoutError:
                raise
            except Exception:
                continue
            try:
                dv = sympy.diff(current, sym)
            except TimeoutError:
                raise
            except Exception:
                continue
            if _interval_sign(dv, domain, params) is True:
                at = lo      # nondecreasing in sym: minimum at the low end
            elif _interval_sign(-dv, domain, params) is True:
                at = hi      # nonincreasing: minimum at the high end
            else:
                continue
            current = current.subs(sym, at)
            pinned.append(f"{name} = {at}")
            changed = True
    if not pinned:
        return None
    prefix = (f"minimized by monotonicity at {', '.join(pinned)}: ")
    if _interval_sign(current, domain, params) is True:
        box = _interval_bounds(current, domain, params)
        return (f"{prefix}the remaining expression {_humanize(current)} "
                f"∈ {box}, never negative")
    found = quadratic(current)
    if found is not None:
        return prefix + found
    return None


def _decide_equality(lhs, rhs, diff, relation, domain, bound_context, params,
                     tolerance: float = 1e-9) -> ProofResult:
    """`==`/`~=`: is the resolved difference identically zero over the
    declared domain?"""
    # diff.is_zero, not `diff == 0`: sympy.Float's `==` is precision-
    # aware, not value-aware; Float(0.0) == 0 is False in sympy, so
    # a domain-resolved diff that lands on a literal Float(0.0) (e.g.
    # via _resolve_clamps collapsing a Min/Max clamp) would silently
    # fall through to the .equals() fallback below instead of being
    # recognized here.
    if diff.is_zero:
        return ProofResult("proven",
                           sketch=f"{_humanize(lhs)} and {_humanize(rhs)} "
                                  "simplify identically")
    # diff, not the original (lhs - rhs): diff has already had the
    # domain's refine()/resolve_clamps() applied, so the fallback
    # benefits from that resolution too, instead of re-asking .equals()
    # a domain-ignorant, unconditional-equality question it may
    # correctly (but unhelpfully) answer False to.
    if diff.has(sympy.Sum):
        # an unevaluated Sum makes the generic ladder below burn the
        # whole wall-clock cap; the closed-form rung is cheap and
        # decisive when it applies, so it goes first
        if _sum_closed_zero(diff) is True:
            return ProofResult(
                "proven",
                sketch="proven with Sum evaluated in closed form, every "
                       "piecewise branch zero under its own condition")
    equal = None
    if diff.has(sympy.asin, sympy.acos, sympy.atan, sympy.acot):
        # inverse-trig complements (acos = pi/2 - asin) only close
        # after an explicit rewrite; and when even that fails, the
        # constant-by-derivative test decides identities like
        # atan(x) + atan(1/x) = pi/2 exactly: every partial derivative
        # vanishing over the connected box plus one exact interior
        # evaluation IS the identity. Both run BEFORE .equals(), whose
        # internal sampling is known to claim a wrong False on exactly
        # these shapes.
        try:
            if sympy.simplify(diff.rewrite(sympy.asin)).is_zero:
                equal = True
        except TimeoutError:
            raise
        except Exception:
            pass
        if equal is None:
            equal = _constant_by_derivative(diff, domain, params)
    if equal is None:
        # an Abs the declared domain settles the sign of: resolve it
        # before asking .equals(), which cannot see the domain and
        # answers for the whole real line
        resolved = _abs_resolved(diff, domain, params)
        if resolved is not None:
            if resolved.is_zero:
                return ProofResult(
                    "proven",
                    sketch=f"{_humanize(lhs)} and {_humanize(rhs)} agree over "
                           f"the declared domain: {_humanize(diff)} resolves to "
                           f"zero once each absolute value takes the sign the "
                           f"domain fixes")
            equal = resolved.equals(0)
    if equal is None:
        equal = diff.equals(0)
    if equal is None and diff.has(sympy.erf, sympy.erfc):
        # erf/erfc's defining relation (erfc(x) = 1 - erf(x)) isn't
        # something plain simplify()/.equals() applies on its own;
        # confirmed directly: erf(x) + erfc(x) - 1 stays unsimplified
        # under both, but .rewrite(erf) expands erfc to 1 - erf first,
        # after which the same identity closes immediately. Cheap,
        # narrowly scoped to expressions that actually contain one of
        # these two, and strictly additional decidability, never a
        # false proof, since it's still the same .equals(0) check on
        # an equivalent, just differently-expressed, difference.
        equal = diff.rewrite(sympy.erf).equals(0)
    if equal is None:
        # A power-tower shape (a fractional power raised to another
        # expression sharing its own symbolic exponent, e.g. an
        # isoelastic-demand or Cobb-Douglas FOC) whose base is a
        # compound expression rather than a plain symbol; see
        # _atomize_positive_power_bases's own docstring for why
        # sympy's own simplification stalls on exactly this shape.
        # A no-op (same diff back) when nothing qualifies, so this
        # costs nothing beyond the sign check when it doesn't apply.
        atomized = _atomize_positive_power_bases(diff, domain, params, bound_context)
        if atomized is not diff:
            equal = sympy.powdenest(atomized, force=True).equals(0)
    if equal is True:
        return ProofResult("proven", sketch="verified equal by sympy .equals()")
    # `.equals()` reaching `None` here isn't distinguished from `False`
    # below: both mean sympy couldn't certify equality on its own, and
    # `.equals()`'s own internal random sampling makes which of the two
    # it lands on vary across process runs (observed directly: the
    # same Mod expression flips between `False` and `None` run to run,
    # since Python's hash randomization perturbs the term order sympy
    # explores). The seeded numeric search below doesn't depend on
    # sympy's internal choice, so running it either way makes the
    # final verdict reproducible regardless of which one `.equals()`
    # happened to return this run.
    if equal is not True:
        counterexample = _corroborate_disproof(diff, domain, params,
                                               bound_context, tolerance)
        if counterexample is not None:
            detail = (", confirmed nonzero at "
                     + ", ".join(f"{s}={v:.6g}" for s, v in counterexample.items())
                     if counterexample else "")
            return ProofResult("disproven", sketch=f"{_humanize(lhs)} ≠ {_humanize(rhs)}: "
                               f"difference simplifies to {_humanize(diff)}{detail}",
                               witness={str(s): v for s, v in counterexample.items()},
                               disproof_hint=diff)
    if relation == "==":
        exact_point = _exact_disproof_witness(diff, domain, params,
                                              bound_context)
        if exact_point is not None:
            return ProofResult(
                "disproven",
                sketch=f"{_humanize(lhs)} ≠ {_humanize(rhs)}: the difference "
                       f"{_humanize(diff)} is nonzero in exact arithmetic, "
                       f"by less than the tolerance",
                witness=exact_point, disproof_hint=diff,
                meta={"mathema.exact_disproof": True})
    if equal is False:
        return ProofResult("undecided",
                           sketch=f"sympy's .equals() claimed {_humanize(diff)} != 0, "
                                 "but a seeded numeric check inside the declared domain "
                                 "could not reproduce a counterexample, so this is not "
                                 "reported as disproven")
    return ProofResult("undecided",
                       sketch=f"sympy could not simplify {_humanize(diff)} to 0")


def _exact_disproof_witness(diff, domain: dict, params: dict,
                            bound_context=None) -> "dict | None":
    """Intent:
        A complete in-domain point where `diff` is provably nonzero in
        exact arithmetic, keyed by symbol name, or None. A difference
        that is a nonzero constant is nonzero everywhere, so any
        admissible point is its witness.

    Notes:
        Reached only after the tolerance-bounded search found nothing:
        whatever this returns differs by less than that tolerance, so
        the result is marked `mathema.exact_disproof` and stands only
        once the real code, compared exactly at this point, differs
        too.
    """
    point = _corroborate_disproof(diff, domain, params, bound_context,
                                  exact=True)
    if point is None:
        return None
    if not point:
        return _representative_point(diff, domain, params, bound_context)
    return {str(sym): v for sym, v in point.items()}


def _sum_closed_zero(diff) -> "bool | None":
    """Intent:
        Whether `diff` is identically zero once its Sums evaluate to
        closed form: 0 outright, or a Piecewise whose every branch is
        zero, checking a branch guarded by an equality at that
        equality's own solutions.

    Notes:
        True only on a complete proof; None on any doubt (an
        unsolvable branch condition, a branch that will not simplify),
        never False: this rung only ever proves, disproof stays with
        the corroborated path.
    """
    def zero(expr, depth: int = 0) -> bool:
        if depth > 3:
            return False
        try:
            closed = sympy.simplify(expr.doit())
        except Exception:
            return False
        if closed == 0:
            return True
        if not isinstance(closed, sympy.Piecewise):
            return False
        for branch_expr, branch_cond in closed.args:
            if zero(branch_expr, depth + 1):
                continue
            if branch_cond is sympy.true:
                return False
            try:
                solutions = sympy.solve(branch_cond, dict=True)
            except Exception:
                return False
            if not solutions:
                return False
            for sol in solutions:
                if not zero(branch_expr.subs(sol), depth + 1):
                    return False
        return True

    return True if zero(diff) else None


def _decide_disequality(lhs, rhs, diff, relation, domain, bound_context, params,
                        tolerance: float = 1e-9) -> ProofResult:
    # A universal claim over the whole domain, same as every other
    # relation here: proven when diff is never zero anywhere in it,
    # disproven when diff is identically zero (they're always
    # equal), undecided otherwise, never a guess either way.
    if diff.is_zero:
        return ProofResult("disproven", sketch=f"{_humanize(lhs)} and "
                           f"{_humanize(rhs)} simplify identically, so "
                           "they're never different")
    box = _interval_bounds(diff, domain, params)
    if box is not None:
        lo = box.min if isinstance(box, sympy.AccumBounds) else box
        hi = box.max if isinstance(box, sympy.AccumBounds) else box
        if _verified_sign(lo) == 1 or _verified_sign(hi) == -1:
            return ProofResult("proven",
                               sketch=f"interval evaluation over the declared "
                                      f"domain: {_humanize(diff)} ∈ {box}, "
                                      "never zero")
    # _provably_signed's own "True" (nonnegative) can still touch
    # zero at a domain corner, only its "False" (provably
    # negative, confirmed strict: a zero-touching corner would make
    # the result ambiguous instead) proves nonzero here. Checking
    # both diff and -diff catches "provably positive" too (the
    # negation of a provably-positive expression is provably
    # negative), without ever trusting the ambiguous "True" case.
    if (_provably_signed(diff, domain, params, bound_context) is False
            or _provably_signed(-diff, domain, params, bound_context) is False):
        return ProofResult("proven", sketch=f"{_humanize(diff)} is provably "
                           "one-signed (never zero) under the declared domain")
    if diff.equals(0) is True:
        return ProofResult("disproven", sketch=f"{_humanize(lhs)} and "
                           f"{_humanize(rhs)} are equal (sympy .equals()), "
                           "so they're never different")
    return ProofResult("undecided",
                       sketch=f"sympy could not settle whether {_humanize(diff)} "
                             "is ever zero under the declared domain")


def _decide_ordering(lhs, rhs, diff, relation, domain, bound_context, params,
                     tolerance: float = 1e-9) -> ProofResult:
    # lhs <= rhs  <=>  rhs - lhs >= 0; lhs >= rhs  <=>  lhs - rhs >= 0
    target = -diff if relation == "<=" else diff

    # Interval evaluation over the declared domain box, tried FIRST: it
    # is cheap, rigorous, and decides the single biggest class of
    # otherwise-undecided sign questions (a bounded domain or a
    # function's known range as a sign fact, cos(θ)/2 on a small box,
    # erf(x) <= 1, a bare rational on [10, 1000], none of which
    # sympy's ask()/is_nonnegative machinery uses on its own).
    box_sign = _interval_sign(target, domain, params)
    if box_sign is not None:
        box = _interval_bounds(target, domain, params)
        if box_sign:
            return ProofResult("proven",
                               sketch=f"interval evaluation over the declared "
                                      f"domain: {_humanize(target)} ∈ {box}, "
                                      "never negative")
        return ProofResult("disproven",
                           sketch=f"interval evaluation over the declared "
                                  f"domain: {_humanize(target)} ∈ {box}, "
                                  "always negative",
                           witness=_representative_point(
                               target, domain, params, bound_context))

    def _is_nonneg(expr):
        # .is_nonnegative only ever consults assumptions baked
        # into a Symbol at creation time; it does not see
        # bound_context's Q predicates at all (a real sympy
        # gotcha: assuming() only affects ask(), never the plain
        # .is_xxx attributes). ask() is what actually combines
        # both a symbol's own assumptions and the dynamic
        # context, so it's strictly more decidable, not just an
        # alternate spelling of the same check.
        if bound_context is not None:
            try:
                with sympy.assuming(bound_context):
                    decided = sympy.ask(sympy.Q.nonnegative(expr))
            except TimeoutError:
                raise
            except Exception:
                decided = None   # ask()'s own internal crash: undecided
            if decided is not None:
                return decided
            # ask() didn't close it, try the exact corner check
            # before falling back to the plain, assumption-free
            # .is_nonnegative (see _affine_sign_by_corners)
            corners = _affine_sign_by_corners(expr, domain, params)
            if corners is not None:
                return corners
        return expr.is_nonnegative

    is_nonneg = _is_nonneg(target)
    if is_nonneg is None:
        # simplify() doesn't always find a factored form even when
        # one exists (e.g. Lagrange's identity: an expanded
        # Cauchy-Schwarz difference is a sum-of-squares in
        # disguise, invisible to .is_nonnegative until factored).
        # Worth trying before giving up: cheap, and strictly
        # additional decidability, never a false proof.
        factored = sympy.factor(target)
        if factored != target:
            is_nonneg = _is_nonneg(factored)
            if is_nonneg is not None:
                target = factored
            else:
                # the interval rung too, not only ask(): factoring is
                # exactly what lets interval arithmetic escape the
                # dependency problem, since a repeated variable inside
                # one product is bounded once rather than once per
                # occurrence. `(1 - s)*(n - 1)/n` decides where the
                # expanded form of the same expression straddles zero.
                factored_sign = _interval_sign(factored, domain, params)
                if factored_sign is not None:
                    box = _interval_bounds(factored, domain, params)
                    verdict = "proven" if factored_sign else "disproven"
                    return ProofResult(
                        verdict,
                        sketch=f"interval evaluation over the declared domain, "
                               f"after factoring: {_humanize(factored)} ∈ "
                               f"{box}, "
                               f"{'never' if factored_sign else 'always'} "
                               f"negative")
    if is_nonneg is True:
        return ProofResult("proven", sketch=f"{_humanize(target)} is nonnegative "
                           "under the declared domain")
    if is_nonneg is False:
        # sympy.is_nonnegative/ask can be WRONG (the false-falsified
        # bug family: interval rounding, Abs under substitution). Carry
        # the offending target as a machine-readable hint and a witness
        # if the seeded search finds one, so the corroboration gate
        # re-checks this against the real function before trusting it.
        witness = _corroborate_disproof(-target, domain, params,
                                        bound_context, tolerance)
        if witness is not None or not _has_equality_constraint(bound_context):
            # under an assumed EQUALITY the sign fact was computed over
            # the whole box, not the feasible surface, without an
            # on-surface witness it proves nothing, so fall through
            return ProofResult(
                "disproven", sketch=f"{_humanize(target)} can be negative",
                witness=({str(s): v for s, v in witness.items()}
                         if witness else None),
                disproof_hint=target)
    certificate = _nonneg_certificate(sympy.expand(target), domain, params)
    if certificate is not None:
        return ProofResult("proven", sketch=certificate)
    for subtree, replacement in _assumption_rewrites(bound_context):
        try:
            rewritten = target.subs(subtree, replacement)
        except TimeoutError:
            raise
        except Exception:
            continue
        if rewritten == target:
            continue
        settled = (rewritten.is_nonnegative is True
                   or _interval_sign(rewritten, domain, params) is True)
        if not settled:
            certificate = _nonneg_certificate(sympy.expand(rewritten),
                                              domain, params)
            settled = certificate is not None
        if settled:
            return ProofResult(
                "proven",
                sketch=f"nonnegative given the assuming clause: with "
                       f"{_humanize(subtree)} = {_humanize(replacement)} "
                       f"(assumed), {_humanize(target)} becomes "
                       f"{_humanize(rewritten)}, which is never negative")
    # a target that is a nonnegative MULTIPLE of an assumed gap is
    # nonnegative outright: (b-a)/2 under `assuming a <= b` is half the
    # assumed gap, and -2x+2y+2z under `assuming y+z >= x` is twice it.
    # The subtree rewrite above misses these (auto-expansion destroys
    # the literal gap subexpression), so the ratio is checked directly.
    for gap_expr in _assumed_gap_exprs(bound_context):
        try:
            ratio = sympy.simplify(target / gap_expr)
        except TimeoutError:
            raise
        except Exception:
            continue
        if ratio.is_nonnegative is True:
            return ProofResult(
                "proven",
                sketch=f"nonnegative given the assuming clause: "
                       f"{_humanize(target)} is ({_humanize(ratio)}) times "
                       f"the assumed-nonnegative gap {_humanize(gap_expr)}")
    return ProofResult("undecided",
                       sketch=f"sympy could not settle the sign of {_humanize(target)}")


def _assumed_gap_exprs(bound_context, *, strict_only: bool = False) -> list:
    """The gap expressions the `assuming` clause established as
    nonnegative or strictly positive (the Q.nonnegative/Q.positive
    atoms of the bound context), for the ratio checks. Bound-
    derived predicates over a bare symbol are excluded, a plain
    `x >= 0` domain fact is already a symbol assumption, and dividing
    by a bare symbol adds nothing the sign engine doesn't know.

    `strict_only` keeps just the strictly-positive ones, which is what
    a strict conclusion needs: `a < b` licenses `b - a > 0`, while
    `a <= b` licenses only `b - a >= 0`, and the weaker premise must
    never be read as the stronger one."""
    if bound_context is None:
        return []
    from sympy.assumptions import AppliedPredicate
    wanted = ("positive",) if strict_only else ("nonnegative", "positive")
    out = []
    for atom in bound_context.atoms(AppliedPredicate):
        if atom.function.name in wanted:
            (arg,) = atom.arguments
            if not arg.is_Symbol:
                out.append(arg)
    return out


# per-relation decision procedures over the domain-resolved difference;
# an unlisted relation stays undecided at the dispatch site above.
def _abs_resolved(diff, domain: dict, params: dict):
    """Intent:
        `diff` with every `Abs(...)` whose argument keeps one sign over
        the declared domain rewritten to that sign, or None when
        nothing could be resolved.

    Notes:
        `Abs(lag) - Abs(lag + 1) + 1` is identically zero for
        `lag >= 0` and nonzero below it, so sympy's `.equals()` is
        right to answer False for a plain symbol. The domain is what
        settles it, but a claim applying a *transformed* call
        argument (`f(n, lag + 1)`) deliberately turns the sign bake
        off, because pre-collapsing the body under it produces false
        disproofs. The sign then never reaches `Abs` and the two
        guards work against each other: the symbolic answer is wrong
        for this region, the numeric check contradicts it, and the
        corroboration guard correctly refuses the disproof, leaving a
        real identity undecided.

        Resolving here instead is safe for the same reason baking is
        not: the difference has already been formed, so nothing can be
        collapsed before the law's own argument order means something.
        Each `Abs` argument is evaluated over the domain's own interval
        hull, and only a hull that stays wholly on one side of zero
        licenses a rewrite.
    """
    nodes = diff.atoms(sympy.Abs)
    if not nodes:
        return None
    predicates = []
    for node in nodes:
        (arg,) = node.args
        try:
            bounds = _interval_bounds(arg, domain, params)
        except TimeoutError:
            raise
        except Exception:
            continue
        if bounds is None:
            continue
        low = bounds.min if isinstance(bounds, sympy.AccumBounds) else bounds
        high = bounds.max if isinstance(bounds, sympy.AccumBounds) else bounds
        if _verified_sign(low) in (0, 1):
            predicates.append(sympy.Q.nonnegative(arg))
        elif _verified_sign(high) in (0, -1):
            predicates.append(sympy.Q.nonpositive(arg))
    if not predicates:
        return None
    try:
        with sympy.assuming(sympy.And(*predicates)):
            resolved = sympy.refine(diff)
    except TimeoutError:
        raise
    except Exception:
        return None
    return None if resolved == diff else resolved

def _decide_strict_ordering(lhs, rhs, diff, relation, domain, bound_context,
                            params, tolerance: float = 1e-9) -> ProofResult:
    """Intent:
        `<`/`>`: is the resolved difference strictly one-signed over
        the declared domain? Proven only on a strict certificate (a
        hull bounded away from zero, or the positive certificate);
        disproven when the OPPOSITE weak ordering holds everywhere
        (the claim is then false at every point); undecided otherwise;
        a claim touching zero anywhere is never rounded up to
        proven.
    """
    target = diff if relation == ">" else -diff
    certificate = _positive_certificate(sympy.expand(target), domain, params)
    if certificate is not None:
        return ProofResult("proven", sketch=certificate)
    # a target that is a POSITIVE multiple of a strictly positive
    # assumed gap is strictly positive outright, the strict twin of
    # the nonnegative ratio check. `assuming a < b` licenses
    # `b - a > 0` and `(b - a)/2 > 0`; `assuming a <= b` licenses
    # neither, which is why only the strict gaps are consulted here.
    for gap_expr in _assumed_gap_exprs(bound_context, strict_only=True):
        try:
            ratio = sympy.simplify(target / gap_expr)
        except TimeoutError:
            raise
        except Exception:
            continue
        if ratio.is_positive is True:
            return ProofResult(
                "proven",
                sketch=f"strictly positive given the assuming clause: "
                       f"{_humanize(target)} is ({_humanize(ratio)}) times "
                       f"the assumed-positive gap {_humanize(gap_expr)}")
    try:
        bounds = _interval_bounds(target, domain, params)
    except TimeoutError:
        raise
    except Exception:
        bounds = None
    if bounds is not None:
        hi = bounds.max if isinstance(bounds, sympy.AccumBounds) else bounds
        if _verified_sign(hi) in (0, -1):
            # target <= 0 everywhere: the strict claim holds nowhere.
            # Under an assumed equality the hull spans the whole box,
            # so only an on-surface witness licenses the disproof.
            witness = _corroborate_disproof(-target, domain, params,
                                            bound_context, tolerance) \
                if _verified_sign(hi) == -1 else None
            if witness is not None or not _has_equality_constraint(bound_context):
                return ProofResult(
                    "disproven",
                    sketch=f"interval evaluation over the declared domain: "
                           f"{_humanize(target)} ∈ {bounds}, never strictly "
                           f"positive",
                    witness=({str(s): v for s, v in witness.items()}
                             if witness else None),
                    disproof_hint=target)
    root = _attained_zero(target, domain, params, bound_context)
    if root is not None:
        return ProofResult(
            "disproven",
            sketch=f"{_humanize(target)} attains zero inside the declared "
                   f"domain (at {', '.join(f'{k} = {v}' for k, v in root.items())}), "
                   f"so the strict inequality fails there; the non-strict "
                   f"form may still hold",
            witness={k: float(v) for k, v in root.items()},
            disproof_hint=target)
    return ProofResult("undecided",
                       sketch=f"sympy could not settle strict positivity "
                              f"of {_humanize(target)}")


def _attained_zero(target, domain: dict, params: dict,
                   bound_context=None) -> "dict | None":
    """Intent:
        An in-domain point where `target` is exactly zero, a strict
        inequality is false at such a point no matter what the sign
        does elsewhere (`0 > 0` never holds), so any root of the
        difference inside the declared domain is a complete disproof
        witness for `<`/`>`.

    Notes:
        Returns `{name: value}` with plain numeric values, or `None`
        when no root is found (which proves nothing: solve() missing a
        root leaves the claim undecided, never proven). The root is
        verified by exact substitution before being trusted.
    """
    from ..domain import domain_contains
    syms = list(params.values())
    if not syms:
        return None
    try:
        solutions = _with_timeout(
            lambda: sympy.solve(sympy.Eq(target, 0), syms, dict=True),
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        raise
    except Exception:
        return None
    name_of = {s: n for n, s in params.items()}
    for sol in solutions or ():
        if set(sol) != set(syms):
            continue   # an under-determined solution family, not a point
        point = {}
        ok = True
        for s, v in sol.items():
            if not getattr(v, "is_number", False) or not getattr(v, "is_real", False):
                ok = False
                break
            bound = domain.get(name_of[s])
            try:
                if bound is not None and not domain_contains(float(v), bound):
                    ok = False
                    break
            except Exception:
                ok = False
                break
            point[name_of[s]] = v
        if not ok:
            continue
        if not _point_satisfies_context({s: v for s, v in sol.items()},
                                        bound_context):
            continue   # a root off the assumed surface disproves nothing
        try:
            if sympy.simplify(target.subs(sol)) == 0:
                return point
        except Exception:
            continue
    return None


_RELATION_DECIDERS = {
    "==": _decide_equality,
    "~=": _decide_equality,
    "<": _decide_strict_ordering,
    ">": _decide_strict_ordering,
    "!=": _decide_disequality,
    "<=": _decide_ordering,
    ">=": _decide_ordering,
}


def _exact(v):
    """Intent:
        Snap a float to an exact Integer or Rational when the round
        trip is lossless. Falls back to the original value otherwise.

    Notes:
        sympy.refine's Abs-sign handler only fires when every bound in
        an assumption set is exact. One Float anywhere in the
        conjunction disables it. Upcasting everything to Float instead
        of downcasting to exact does not help either, both confirmed
        directly against sympy.
    """
    if not isinstance(v, float):
        return v
    exact = sympy.nsimplify(v, rational=False)
    try:
        return exact if abs(float(exact) - v) < 1e-9 else v
    except TypeError:
        return v


def _split_domain_pieces(lo, hi, closed_lo: bool, closed_hi: bool, split_points):
    """Intent:
        Sub-intervals of (lo, hi) split at every interior point.

    Notes:
        Each new boundary is open on that side. None when nothing in
        split_points is strictly interior.
    """
    interior = sorted({p for p in split_points if lo < p < hi})
    if not interior:
        return None
    edges = [lo, *interior, hi]
    return [(edges[i], edges[i + 1], closed_lo if i == 0 else False,
            closed_hi if i == len(edges) - 2 else False)
           for i in range(len(edges) - 1)]


def _prove_relation_case_split(lhs, rhs, relation: str, domain: dict, bound_context,
                               params: dict, split_param: str, split_points, kind: str,
                               opaque=None, extensive: bool = False) -> "ProofResult | None":
    """Intent:
        Retry an undecided proof by splitting split_param's own domain
        at split_points and re-proving on each piece.

    Notes:
        Every piece, plus a direct substitution check at the split
        point for a non-pole kind, must prove. A single disproven
        piece falsifies the whole claim immediately. Anything else,
        including one lingering undecided piece, keeps the combined
        result undecided. A pole is excluded from both pieces and
        never separately checked; the function is undefined there.
        None when there is nothing to split (no plain interval domain
        for split_param).
    """
    sym = params.get(split_param)
    lo_hi = domain.get(split_param)
    if sym is None or not isinstance(lo_hi, tuple):
        return None
    lo, hi = lo_hi
    closed_lo = getattr(lo_hi, "closed_lo", True)
    closed_hi = getattr(lo_hi, "closed_hi", True)
    pieces = _split_domain_pieces(lo, hi, closed_lo, closed_hi, split_points)
    if pieces is None:
        return None
    exact_pieces = [(_exact(p[0]), _exact(p[1]), p[2], p[3]) for p in pieces]
    sketches = []
    for piece_lo, piece_hi, p_closed_lo, p_closed_hi in exact_pieces:
        # the piece predicate alone, not ANDed with the original
        # bound_context: a piece is already a full, tighter restatement
        # of the domain, and the original bound_context carries the
        # domain's own un-exact Float bounds, which would silently
        # reintroduce the exact Float-mixing problem _exact() exists
        # to avoid (confirmed directly by testing both ways).
        ctx = _interval_predicate(sym, Interval(piece_lo, piece_hi, p_closed_lo, p_closed_hi))
        result = _prove_relation(lhs, rhs, relation, domain, ctx, params,
                                 opaque=opaque, extensive=extensive)
        if result.status == "disproven":
            return result
        if result.status != "proven":
            return None
        sketches.append(result.sketch)
    interior = sorted({_exact(p) for p in split_points if lo < p < hi})
    points_str = ', '.join(str(p) for p in interior)
    case_split_meta = {"mathema.derive_route": "case_split"}
    if kind == "pole":
        note = (f"split at {split_param} = {points_str} "
               f"({sym} is undefined at {split_param} = {points_str}, excluded)")
        return ProofResult("proven", sketch=f"proven piecewise, {note}: " + "; ".join(sketches),
                           meta=case_split_meta)
    if len(interior) != 1:
        return None   # multiple interior points, non-pole kind: at-point check not attempted for V1
    at = interior[0]
    at_result = _prove_relation(lhs.subs(sym, at), rhs.subs(sym, at), relation, domain,
                                None, params, opaque=opaque, extensive=extensive)
    if at_result.status != "proven":
        return at_result if at_result.status == "disproven" else None
    sketches.append(at_result.sketch)
    note = f"split at {split_param} = {at}"
    return ProofResult("proven", sketch=f"proven piecewise, {note}: " + "; ".join(sketches),
                       meta=case_split_meta)


