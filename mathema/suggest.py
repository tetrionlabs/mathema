# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Claim suggestion: propose candidate claims for a function from its
own structure, without running or proving anything.

`suggest_claims()` is the whole public surface, the battery of
structural detectors behind `mathema.check()`'s default claim set and
the CLI's suggestions, plus the YAML writer that appends suggestions to
the declared layer (`write=True`). Declares, never verifies: every
suggestion is a `Conjecture` a later adjudication pass gets to settle.
"""
from __future__ import annotations

import ast
import os

from . import families as _families
from .analysis import analyze_source
from .conjecture import claim
from .records import _EXC_TYPES
from .spec import declare, merge_entries, write_yaml


def _fmt_num(v: float) -> str:
    """A bound endpoint as short claim text: an integer-valued float
    drops its `.0` (`0`, `-1`), everything else keeps its repr."""
    return str(int(v)) if float(v).is_integer() else repr(v)


def _bound_claim_text(call: str, lo, hi, closed_lo, closed_hi) -> str:
    """Render a return-bound marker as claim text: a two-sided chain
    (`0 <= f(x) <= 1`) when both ends are finite, a one-sided inequality
    (`f(x) > 0`) when the marker leaves a side unbounded. `<=`/`>=` for a
    closed end, `<`/`>` for an open one."""
    if lo is not None and hi is not None:
        return (f"{_fmt_num(lo)} {'<=' if closed_lo else '<'} {call} "
                f"{'<=' if closed_hi else '<'} {_fmt_num(hi)}")
    if lo is not None:
        return f"{call} {'>=' if closed_lo else '>'} {_fmt_num(lo)}"
    if hi is not None:
        return f"{call} {'<=' if closed_hi else '<'} {_fmt_num(hi)}"
    return ""


def _numeric_const(node):
    """The float value of a numeric-literal AST node (an int/float
    Constant, or its unary minus), else None. A bool is not numeric
    here."""
    if (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _numeric_const(node.operand)
        return -inner if inner is not None else None
    return None


def _clamp_bounds(node) -> tuple | None:
    """`(lo, hi)` when node is a two-sided numeric clamp, `min(hi,
    max(lo, x))` or `max(lo, min(hi, x))`, with literal bounds, else
    None. This is the code itself pinning its output to an interval, read
    structurally, nothing inferred beyond the literals present."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("min", "max") and len(node.args) == 2):
        return None
    outer = node.func.id
    outer_lits = [c for c in (_numeric_const(a) for a in node.args)
                  if c is not None]
    inners = [a for a in node.args if _numeric_const(a) is None]
    if len(outer_lits) != 1 or len(inners) != 1:
        return None
    inner = inners[0]
    if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            and inner.func.id in ("min", "max") and inner.func.id != outer
            and len(inner.args) == 2):
        return None
    inner_lits = [c for c in (_numeric_const(a) for a in inner.args)
                  if c is not None]
    if len(inner_lits) != 1:
        return None
    a, b = outer_lits[0], inner_lits[0]
    return (min(a, b), max(a, b))


def bound_annotation_hint(fn, facts=None) -> str | None:
    """A hedged nudge to annotate a bounded-looking return, or None. When
    the body clamps its result to a literal `[lo, hi]` but the return
    carries no bound marker, annotating it (`-> InRange(lo, hi)`) lets
    mathema state and check the bound (the `returns_in_range` suggestion
    fires once the marker is there). No prose is read and nothing is
    guessed beyond the literal clamp the code itself performs, so this is
    a direction to annotate, never a claim mathema invents."""
    if facts is None:
        try:
            facts = analyze_source(fn)
        except Exception:
            return None
    if facts.tree is None:
        return None
    from .types import return_bound
    if return_bound(fn) is not None:
        return None                                    # already annotated
    for node in ast.walk(facts.tree):
        if isinstance(node, ast.Return) and node.value is not None:
            bounds = _clamp_bounds(node.value)
            if bounds is not None:
                lo, hi = _fmt_num(bounds[0]), _fmt_num(bounds[1])
                return (f"the return is clamped to [{lo}, {hi}] but is not "
                        f"annotated; annotate it `-> InRange({lo}, {hi})` "
                        "so mathema can state and check the output bound")
    return None


def _raise_guard_types(fdef, params: list[str]) -> dict[str, str]:
    """Intent:
        Per parameter, the exception class name raised by its own
        `if ...: raise ExcType(...)` guard, when one exists and the
        type is in records._EXC_TYPES's known vocabulary.

    Notes:
        Mirrors analysis._guards()'s own If/Raise walk, but captures
        the exception type name instead of just "raise"/"assert"/
        "clamp"/"none". Only the first guard found per parameter is
        used, matching _guards()'s own first-wins behavior.
    """
    pset = set(params)
    out: dict[str, str] = {}

    def names_in(node):
        return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} & pset

    for node in ast.walk(fdef):
        if isinstance(node, ast.If):
            for stmt in node.body:
                if isinstance(stmt, ast.Raise) and stmt.exc is not None:
                    exc = stmt.exc
                    name = (exc.func.id if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
                           else exc.id if isinstance(exc, ast.Name) else None)
                    if name in _EXC_TYPES:
                        for p in names_in(node.test):
                            out.setdefault(p, name)
    return out



def _resolvable(ref: str) -> bool:
    """Whether a dotted function reference imports here, so a
    suggestion never names a binding the machine cannot honor."""
    try:
        from .conjecture import _resolve_func_ref
        return _resolve_func_ref(ref) is not None
    except Exception:
        return False


def _sole_delegation(fn, facts) -> str | None:
    """The dotted key of the one project function fn is EQUIVALENT to,
    when fn's whole body is a single `return core(<its own params>)` to
    exactly one project function, passing its parameters straight through
    in order, else None. This is the cross-implementation family authors
    write by hand (`let g = pkg.mod.core, f =:= g`) but the shape battery
    never proposes: a vectorised wrapper delegating to a scalar core is
    pinned to the core it was built on, via mathema's own function-
    equivalence relation. A body that reshapes, reorders, or partially
    applies its arguments, or does more than the one call, is not
    matched, so the equivalence it would suggest cannot be a false
    lead."""
    from .inventory import function_dependencies
    deps = [d for d in function_dependencies(fn, facts)
            if d.get("kind") == "function" and d.get("key") and d.get("form")]
    if len(deps) != 1:
        return None
    key, name = deps[0]["key"], deps[0].get("name")
    stmts = list(facts.tree.body)
    if (stmts and isinstance(stmts[0], ast.Expr)
            and isinstance(getattr(stmts[0], "value", None), ast.Constant)):
        stmts = stmts[1:]                              # drop a docstring
    if len(stmts) != 1 or not isinstance(stmts[0], ast.Return):
        return None
    call = stmts[0].value
    if not isinstance(call, ast.Call) or call.keywords:
        return None
    func = call.func
    called = (func.id if isinstance(func, ast.Name)
              else func.attr if isinstance(func, ast.Attribute) else None)
    arg_names = ([a.id for a in call.args]
                 if all(isinstance(a, ast.Name) for a in call.args) else None)
    if called != name or arg_names != facts.params:
        return None
    return key


# inverse-pair naming: a function whose name is one of these has a mate
# whose function would invert it. Bidirectional pairs are listed both
# ways; a few (parse) have several plausible mates. The to_X/from_X
# prefix pair is handled by _inverse_mate_names, not the table.
_INVERSE_MATES = {
    "encode": ("decode",), "decode": ("encode",),
    "dumps": ("loads",), "loads": ("dumps",),
    "dump": ("load",), "load": ("dump",),
    "serialize": ("deserialize",), "deserialize": ("serialize",),
    "marshal": ("unmarshal",), "unmarshal": ("marshal",),
    "pack": ("unpack",), "unpack": ("pack",),
    "compress": ("decompress",), "decompress": ("compress",),
    "escape": ("unescape",), "unescape": ("escape",),
    "quote": ("unquote",), "unquote": ("quote",),
    "zip": ("unzip",), "unzip": ("zip",),
    "format": ("parse",), "render": ("parse",), "unparse": ("parse",),
    "parse": ("format", "render", "unparse"),
}


def _inverse_mate_names(name: str) -> set:
    """Candidate names whose function would invert `name`: the naming
    table plus the `to_X`/`from_X` prefix pair."""
    mates = set(_INVERSE_MATES.get(name, ()))
    if name.startswith("to_"):
        mates.add("from_" + name[len("to_"):])
    if name.startswith("from_"):
        mates.add("to_" + name[len("from_"):])
    return mates


def _inverse_sibling(fn, facts) -> str | None:
    """The dotted key of a sibling function whose name inverts fn's
    (encode/decode, dumps/loads, to_X/from_X, ...), found in fn's own
    module, else None. This is the round-trip pair the shape battery
    never proposes: the inverse is not a callee, so function_dependencies
    does not reach it, and it is enumerated from the module directly."""
    import inspect
    import sys
    mates = _inverse_mate_names(getattr(fn, "__name__", ""))
    if not mates:
        return None
    mod = sys.modules.get(getattr(fn, "__module__", None))
    if mod is None:
        return None
    for name in sorted(mates):
        obj = getattr(mod, name, None)
        if (inspect.isfunction(obj)
                and getattr(obj, "__module__", None) == mod.__name__
                and obj is not fn):
            return f"{obj.__module__}.{obj.__qualname__}"
    return None


def _sum_like_fold(fn, facts):
    """The fold lift when the function is a plain accumulation (both
    update weights identically 1), else None: the gate for the
    order-insensitive suggestions, whose claims are only worth asking
    about a fold that treats every element alike."""
    try:
        import sympy

        from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
        from .symbolic._fold import lift_fold
        fold = _with_timeout(lambda: lift_fold(fn, facts),
                             FAST_TIMEOUT_SECONDS)
        if fold is None or fold.seq_param is None:
            return None
        if sympy.simplify(fold.coeff_item - 1) != 0:
            return None
        if sympy.simplify(fold.coeff_acc - 1) != 0:
            return None
        return fold
    except TimeoutError:
        return None
    except Exception:
        return None


def _loop_closed_form(fn, facts) -> "str | None":
    """The compact closed form of a pure-sum scalar loop, as claim
    text, or None. This is where the well-known series land: the sum
    of the first n integers suggests `f(n) == n*(n + 1)/2`, squares
    suggest the cubic, a constant body suggests the product, each
    proven by the same machinery that closed it. Only a SMALL closed
    form is suggested; a page of algebra teaches nothing."""
    if not getattr(facts, "loops", None):
        return None
    if any(k == "sequence" for k in facts.param_kinds.values()):
        return None
    try:
        import sympy

        from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
        from .symbolic._sum import lift_sum

        def build():
            sl = lift_sum(fn, facts)
            if sl is None or isinstance(sl.expr, tuple):
                return None
            closed = sympy.simplify(sl.expr.doit())
            if closed.has(sympy.Sum) or closed.has(sympy.Piecewise):
                return None
            names = {sym.name for sym in closed.free_symbols}
            if not names <= set(facts.params):
                return None
            if sympy.count_ops(closed) > 12:
                return None
            return str(closed).replace("**", "^")
        return _with_timeout(build, FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    except Exception:
        return None


def _homogeneous_degree_one(fn, facts) -> bool:
    """Whether the lift satisfies f(c*x, ...) == c*f(x, ...)
    symbolically, checked under the fast wall-clock cap. False on any
    doubt (no lift, tuple return, timeout, sympy stall): the caller
    only SUGGESTS the equivariance claim when adjudication will land
    it as a proof, so the battery adds signal, never noise."""
    try:
        import sympy

        from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
        from .symbolic import lift
        lifted = lift(fn, facts)
        if lifted is None or isinstance(lifted.expr, tuple):
            return False
        syms = [sy for sy in lifted.expr.free_symbols
                if sy.name in facts.params]
        if not syms:
            return False
        c = sympy.Symbol("_mathema_scale", positive=True)
        scaled = lifted.expr.subs({sy: c * sy for sy in syms},
                                  simultaneous=True)
        return _with_timeout(
            lambda: sympy.simplify(scaled - c * lifted.expr) == 0,
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return False
    except Exception:
        return False


def suggest_claims(fn, facts=None, extensive: bool = False, write: bool = False,
                   key: str | None = None, root: str = ".") -> list:
    """Intent:
        Suggest candidate claims for fn: monotonicity, affine-ness, and
        convexity per real scalar parameter; symmetry (even/odd) and
        idempotence per real scalar parameter when the return value is
        also scalar; commutativity and associativity when fn takes
        exactly two real scalar parameters and returns one;
        determinism (and seeded reproducibility where randomness is detected); numerical stability; is_pole_safe[param]/
        is_builtin_safe[param] when fn's own body actually calls
        something whose real domain a declared bound could be checked
        against; and, for a function whose first parameter is a
        sequence and the rest are scalar, a lower and upper bound
        against min/max(xs), permutation-invariance, scale-equivariance,
        and translation-equivariance; a raises(...) claim per guarded
        parameter.

    Notes:
        Declares, never verifies. Nothing here is run or proven.
        Monotonicity/affine-ness/convexity/numerical-stability all use
        route="best": check_conjectures() attempts a proof first and
        falls back to an empirical route only when derive can't decide,
        rather than this function pre-guessing a route from fn's own
        liftability at suggestion time. The registered claim families
        for these names (mathema.claim_families.
        _register_builtin_claim_families) are what a fallback actually
        reaches, a
        probe:algorithmic pairwise/finite-difference technique for the
        first four, a domain_hazards-based derive check for numerical
        stability, so extensive= no longer changes which route these
        five get suggested under; it still reaches check_conjectures()'s
        own derive attempt at adjudication time, the same as for any
        other route="best" claim, once a caller actually runs check().
        The safety predicates are suggested under the route their own
        registered family supports: every member with an empirical
        half cascades (route="best").
        Permutation-invariance, scale- and translation-equivariance
        have no symbolic form at all; each is expressed in the same
        claim grammar via Conjecture's own funcs={} extension point,
        binding an extra function letter to a plain Python closure over
        fn, rather than a new grammar primitive (probe and derive share
        one grammar; only how a claim gets proved differs). A
        derive-routed raises(...) suggestion may itself come back
        unliftable later without a narrow enough domain. That is fine,
        it is declared, not verified, the same as any hand-authored
        claim. write=True appends to <root>/claims/<key>.claims.yaml,
        the declared layer load_declared() actually scans, not
        .mathema/declared/..., which load_declared() skips.
    """
    if facts is None:
        try:
            facts = analyze_source(fn)
        except Exception:
            return []
    if facts.tree is None:
        # a doc-only Facts (no real source available, e.g. a C builtin
        # like math.atan) has nothing raises(...)-guard detection or a
        # lift attempt could read, caller-supplied facts skip the
        # analyze_source() call above entirely, so this can't rely on
        # that try/except alone.
        return []
    scalar_params = [p for p in facts.params if facts.param_kinds.get(p) == "scalar"]
    call = f"f({', '.join(facts.params)})"
    out = []
    for p in scalar_params:
        out.append(claim(f"d({call}, {p}) >= 0", name=f"monotonic_increasing[{p}]",
                         source="mathema", route="best"))
        out.append(claim(f"d({call}, {p}) <= 0", name=f"monotonic_decreasing[{p}]",
                         source="mathema", route="best"))
        out.append(claim(f"d({call}, {p}, {p}) == 0", name=f"affine[{p}]",
                         source="mathema", route="best"))
        out.append(claim(f"d({call}, {p}, {p}) >= 0", name=f"convex[{p}]",
                         source="mathema", route="best"))
        out.append(claim(f"d({call}, {p}, {p}) <= 0", name=f"concave[{p}]",
                         source="mathema", route="best"))

    # Bound from a return-type marker: an annotated return
    # (`-> Probability`, `-> InRange(0, 1)`, `-> UnitBall`) states the
    # output bound directly, the value/bound family authors write by
    # hand. The input domain a parameter marker implies is applied
    # separately by check()'s type_probes, so this claim carries only the
    # output bound; because a bound falsifies on a missing (nan) return,
    # it is also the explicit "the output is present" statement.
    from .types import return_bound
    rb = return_bound(fn)
    if rb is not None:
        bound_text = _bound_claim_text(call, *rb)
        if bound_text:
            out.append(claim(bound_text, name="returns_in_range",
                             source="mathema", route="best"))

    numeric_return = facts.returns_kind == "scalar"
    if len(facts.params) == 1 and scalar_params and numeric_return:
        p = scalar_params[0]
        out.append(claim(f"f(-{p}) == f({p})", name="even", source="mathema", route="best"))
        out.append(claim(f"f(-{p}) == -f({p})", name="odd", source="mathema", route="best"))
        out.append(claim(f"f(f({p})) == f({p})", name="idempotent",
                         source="mathema", route="best"))
    closed_form = (_loop_closed_form(fn, facts)
                   if facts.params
                   and facts.returns_kind in ("scalar", "int")
                   and all(facts.param_kinds.get(q) in ("scalar", "int")
                           for q in facts.params) else None)
    if closed_form is not None:
        out.append(claim(f"{call} == {closed_form}",
                         name="closed_form", source="mathema",
                         route="best"))
    if (scalar_params and len(scalar_params) == len(facts.params)
            and numeric_return and _homogeneous_degree_one(fn, facts)):
        aux = "c" if "c" not in facts.params else "aux_c"
        args = ", ".join(facts.params)
        scaled_args = ", ".join(f"{aux}*{q}" for q in facts.params)
        out.append(claim(
            f"let {aux} be [0.1, 10], f({scaled_args}) == {aux}*f({args})",
            name="scale_equivariant", source="mathema", route="best"))
    if len(facts.params) == 2 and len(scalar_params) == 2 and numeric_return:
        p1, p2 = facts.params
        out.append(claim(f"f({p1}, {p2}) == f({p2}, {p1})", name="commutative",
                         source="mathema", route="best"))
        aux = "c" if "c" not in facts.params else "aux_c"
        out.append(claim(f"f(f({p1}, {p2}), {aux}) == f({p1}, f({p2}, {aux}))",
                         name="associative", source="mathema", route="best"))

    # f(...) == f(...) genuinely re-evaluates fn twice with the same
    # synthesized arguments on the probe route (check_conjectures shares
    # one env per trial), the same non-determinism check probe()'s old
    # hardcoded battery ran unconditionally. On the derive route a
    # lifted function proves this trivially, honestly: lifting already
    # assumes purity.
    out.append(claim(f"{call} == {call}", name="is_deterministic",
                     source="mathema", route="best"))
    # the mutation member rides the same ceremonial law (the family's
    # own halves adjudicate; the law text never compiles): does calling
    # the function mutate an argument, a global, or module state?
    out.append(claim(f"{call} == {call}", name="is_state_safe",
                     source="mathema", route="best"))
    if any("randomness" in e for e in facts.effects):
        # the weaker stateless member is only worth asking where
        # randomness structurally exists: reproducible up to the seed
        out.append(claim(f"{call} == {call}", name="is_reproducible",
                         source="mathema", route="best"))

    # no symbolic form for the probe fallback (whether a call raises or
    # returns non-finite isn't a relation sympy adjudicates),
    # expressed inside the same claim grammar via a bound extra
    # function (mathema.f.finite_no_error, referenced by dotted path so
    # this claim survives declare()/entry_claims()'s round trip),
    # boolean-as-int, rather than a new predicate. `f` is a plain
    # allowed name here, not a call, passed to the bound function so
    # it can invoke fn itself under a try/except a symbolic comparison
    # could never express. route="best": the registered
    # is_numerically_stable family (above) gets a real derive attempt
    # first (proving pole-avoidance when a domain is declared, via
    # domain_hazards()), falling back to this funcs-bound probe check
    # when no domain is declared or the family can't decide.
    out.append(claim(f"g(f, {', '.join(facts.params)}) == 1", name="is_numerically_stable",
                     source="mathema", route="best", funcs={"g": "mathema.f.finite_no_error"}))

    # the definedness region as its own named claim: adjudicated by
    # region equivalence against the current body (the is_defined
    # family), and referenceable from other claims via `assuming
    # is_defined`. Only single-conjunct regions are suggested, a
    # claim statement is one relation.
    from .conjecture import _definedness_region
    try:
        region = _definedness_region(fn, facts)
    except Exception:
        region = []
    for i, conjunct in enumerate(region):
        # one claim per conjunct: a single-piece region is plain
        # `is_defined`; a multi-piece region numbers its parts
        # (`is_defined[1]`, ...), each adjudicated by membership in
        # the freshly computed region
        name = "is_defined" if len(region) == 1 else f"is_defined[{i + 1}]"
        try:
            out.append(claim(conjunct, name=name, source="mathema",
                             route="derive"))
        except Exception:
            # a region claim() can't state simply isn't suggested
            pass

    # The implementation-safety predicates, gated per registered
    # family: each SafetyFamily names the parameters it is
    # structurally relevant for (is_builtin_safe only where the body
    # passes the parameter to a restricted-domain builtin,
    # is_pole_safe only where the fast-path lift finds a pole,
    # is_missing_safe only where an explicit raising missing-guard
    # exists), and the suggested route is read off what the family
    # actually registers, a member with an empirical half cascades
    # (route="best"), a derive-only member never pretends a fallback
    # exists (route="derive"). Registration order fixes the
    # suggestion order.
    for family_name, family in _families.families().items():
        gate = getattr(family, "suggest_targets", None)
        if gate is None:
            continue
        for p in gate(fn, facts):
            out.append(claim(f"{family_name}({p})",
                             name=f"{family_name}[{p}]",
                             source="mathema",
                             route=family.suggested_route()))

    # Structure predicate from a shape marker: a square-matrix return
    # (`-> Mat("n", "n")`) makes `is_symmetric(f(...))` worth offering,
    # the value/structure family the shape battery cannot state. Only the
    # canonical property is proposed, not the whole matrix-property cross-
    # product, and only when a matrix parameter exists to feed it.
    from .types import matrix_param_names, shapes_from_signature
    ret_shape = shapes_from_signature(fn).get("return")
    mat_params = [p for p in facts.params if p in matrix_param_names(fn)]
    if (mat_params and ret_shape is not None and len(ret_shape.dims) == 2
            and ret_shape.dims[0] == ret_shape.dims[1]):
        try:
            out.append(claim(f"is_symmetric({call})", name="is_symmetric",
                             source="mathema", route="best"))
        except Exception:
            pass

    # Single-delegate core: a wrapper whose whole body is `return
    # core(<its own params>)` to exactly one project function is pinned
    # to that core with `let g = pkg.mod.core, f =:= g`, mathema's own
    # function-equivalence relation, the cross-implementation family the
    # shape battery never proposes.
    core_key = _sole_delegation(fn, facts)
    if core_key is not None and _resolvable(core_key):
        g = next((c for c in "ghk" if c not in facts.params), "g")
        try:
            out.append(claim(f"let {g} = {core_key}, f =:= {g}",
                             name="equivalent_to_core", source="mathema",
                             route="best"))
        except Exception:
            pass

    # Round-trip / inverse: a function with an inverse sibling
    # (encode/decode, dumps/loads, to_X/from_X) earns `g(f(x)) == x`, the
    # most-used property-based-testing pattern, which the shape battery
    # never proposes. Restricted to a single parameter, since g(f(x)) == x
    # recovers exactly one argument.
    if len(facts.params) == 1:
        inv_key = _inverse_sibling(fn, facts)
        if inv_key is not None and _resolvable(inv_key):
            x = facts.params[0]
            g = next((c for c in "ghk" if c not in facts.params), "g")
            try:
                out.append(claim(f"let {g} = {inv_key}, {g}(f({x})) == {x}",
                                 name="roundtrips_with", source="mathema",
                                 route="best"))
            except Exception:
                pass

    scalar_ish = {"scalar", "int", "unknown"}
    if (facts.params and facts.param_kinds.get(facts.params[0]) == "sequence"
            and all(facts.param_kinds.get(p) in scalar_ish for p in facts.params[1:])
            and numeric_return):
        xs = facts.params[0]
        rest = facts.params[1:]
        rest_str = (", " + ", ".join(rest)) if rest else ""

        out.append(claim(f"min({xs}) <= {call}", name="bounded_lower",
                         source="mathema", route="best"))
        out.append(claim(f"{call} <= max({xs})", name="bounded_upper",
                         source="mathema", route="best"))

        # a fixed reversal, not a random shuffle: necessary but not
        # sufficient for true permutation-invariance (invariant under
        # every permutation implies invariant under reversal, not the
        # converse), traded for a pure, stateless, by-name-referenceable
        # transform.
        out.append(claim(f"{call} == f(g({xs}){rest_str})", name="permutation_invariant",
                         source="mathema", route="probe",
                         funcs={"g": "mathema.f.reverse_seq"}))

        aux = "c" if "c" not in facts.params else "aux_c"
        # route best: the derive route composes these elementwise
        # transforms through a recognized fold's closed form, so a
        # linear fold's equivariance is proven rather than sampled
        out.append(claim(f"{aux}*{call} == f(g({xs}, {aux}){rest_str})",
                         name="scale_equivariant", source="mathema", route="best",
                         funcs={"g": "mathema.f.scale_seq"}))

        out.append(claim(f"{call} + {aux} == f(g({xs}, {aux}){rest_str})",
                         name="translation_equivariant", source="mathema", route="best",
                         funcs={"g": "mathema.f.shift_seq"}))

        if _sum_like_fold(fn, facts) is not None:
            # a plain accumulation treats every element alike, so the
            # order-insensitive family applies and, being a linear
            # fold, mostly proves
            out.append(claim(
                f"f(g({xs}, {xs}){rest_str}) == {call} + {call}",
                name="self_concat_additive", source="mathema",
                route="best", funcs={"g": "mathema.f.concat_seq"}))
            out.append(claim(
                f"f(g({xs}){rest_str}) == {call}",
                name="order_invariant", source="mathema", route="best",
                funcs={"g": "mathema.f.sort_seq"}))
            if not rest and _resolvable("numpy.sum"):
                # the call form, not `=:=`: numpy.sum's own signature
                # carries seven optional parameters, so positional
                # equivalence is not meaningful, but the one-argument
                # call is
                out.append(claim(
                    f"{call} == g({xs})", name="sum_like",
                    source="mathema", route="best",
                    funcs={"g": "numpy.sum"}))

    # Output-contract invariants for a SEQUENCE-returning function whose
    # first argument is also a sequence: length, permutation, and type
    # preservation, the property-based-testing "some things never change"
    # invariants the shape battery never proposes. All three are probe-
    # only (dim/sorted/type have no symbolic form).
    if (facts.params and facts.returns_kind == "sequence"
            and facts.param_kinds.get(facts.params[0]) == "sequence"):
        seq = facts.params[0]
        out.append(claim(f"len({call}) == len({seq})",
                         name="preserves_length", source="mathema",
                         route="probe"))
        out.append(claim(f"sorted({call}) == sorted({seq})",
                         name="is_permutation_of_input", source="mathema",
                         route="probe"))
        out.append(claim(f"type({call}) == type({seq})",
                         name="preserves_type", source="mathema",
                         route="probe"))
        out.append(claim(f"is_sorted_output({call})",
                         name="is_sorted_output", source="mathema",
                         route="probe"))

    # output_never_none: only where the body actually has a path that
    # returns None (a bare `return` or `return None`), so it is a real
    # risk worth pinning, not noise on every function.
    if any(isinstance(n, ast.Return)
           and (n.value is None
                or (isinstance(n.value, ast.Constant) and n.value.value is None))
           for n in ast.walk(facts.tree)):
        out.append(claim(f"output_never_none({call})",
                         name="output_never_none", source="mathema",
                         route="probe"))

    guard_types = _raise_guard_types(facts.tree, facts.params)
    for p, exc_name in guard_types.items():
        out.append(claim(f"raises({call}, {exc_name})", name=f"raises[{p}]",
                         source="mathema", route="best"))

    if write:
        _write_suggested_claims(fn, out, key=key, root=root)
    return out


def _write_suggested_claims(fn, suggestions: list, key: str | None, root: str) -> str:
    """Intent:
        Append suggested claims to <root>/claims/<key>.claims.yaml, the
        declared layer load_declared() actually scans.

    Notes:
        Merges by claim name via spec.merge_entries. An existing claim
        at that name wins; a suggestion never clobbers an already-
        declared claim. key defaults the same way write_spec()'s own key
        does.
    """
    if key is None:
        from .authoring import _fn_key
        key = _fn_key(fn)
    path = os.path.join(root, "claims", f"{key}.claims.yaml")
    existing: dict = {}
    if os.path.exists(path):
        import yaml
        existing = yaml.safe_load(open(path)) or {}
    new_entry = {"claims": [declare(cj) for cj in suggestions]}
    merged_entry = merge_entries(existing.get(key, {}), new_entry)
    existing[key] = merged_entry
    return write_yaml(path, existing)
