# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Hazard knowledge: where an implementation can diverge from the
mathematics it encodes.

A hazard is a concrete input location (or class of locations) where
the CODE's runtime behaviour is at risk of disagreeing with the
lifted form: a pole, a restricted-builtin domain edge (log's zero,
asin's unit interval), a missing-value input. This module is the one
home for that knowledge, which parameters are exposed to which
hazard kinds, and at which values, shared by every consumer:
the safety claim families' derive routes read it as proof
obligations, the suggestion gates read it as structural relevance,
and the probe route reads it as guaranteed-hit sample points.

One registry of hazard-point generators, keyed by hazard kind.
Registration is a dict entry, matching the registry style of
`mathema.families` and `mathema.routes.ROUTE_CAPABILITIES`: adding a
hazard kind is a registration, never an edit to a conditional.
"""
from __future__ import annotations

import ast
import math
import sys
from dataclasses import dataclass
from typing import Callable, Iterable

from ._math_vocab import _call_name
from .probing import _points_for_probe, _poles_by_var


@dataclass(frozen=True)
class HazardPoint:
    """One concrete hazard location for one parameter.

    `at` is the location as text (a sympy-parsable value, or a class
    description like "non-positive integers"); `value` is the plain
    float when the location evaluates to one, else None. `source`
    names what knowledge produced the point (the builtin's name, the
    critical-point search, the missing policy)."""

    kind: str
    param: str
    at: str
    value: float | None
    source: str


# --- hazard knowledge: restricted-builtin real domains ---------------

# Real math functions whose own domain is narrower than sympy's
# symbolic generalization. Membership here is what makes a call a
# hazard at all; _SAFE_RANGE below carries the accepted ranges for
# the non-factorial names.
_RESTRICTED_DOMAIN_NAMES = frozenset(
    {"factorial", "sqrt", "log", "asin", "acos", "gamma", "lgamma"})

# name -> (lo, lo_inclusive, hi, hi_inclusive) real math function's own
# accepted range. gamma/lgamma are the conservative half of their real
# domain (any real > 0), the real function also accepts most negative
# non-integers (only the non-positive integers are actual poles), but
# that's is_pole_safe's own, more precise job; treating "> 0" as the
# provably-safe range here never risks a false "proven".
_SAFE_RANGE = {
    "sqrt": (0.0, True, math.inf, True),
    "log": (0.0, False, math.inf, True),
    "asin": (-1.0, True, 1.0, True),
    "acos": (-1.0, True, 1.0, True),
    "gamma": (0.0, False, math.inf, True),
    "lgamma": (0.0, False, math.inf, True),
}


def _bare_call_targets(facts, names: frozenset) -> dict:
    """Intent:
        Every real parameter passed as the sole argument to a bare
        `name(param)` call for any name in `names`, mapped to the set
        of such names it's passed to, the one AST scan behind every
        which-parameters-face-this-call detector.

    Notes:
        A source-level scan (mirrors _raise_guard_types's own walk),
        not a symbolic lift; this still works for a function that
        doesn't lift at all (a branch, a loop, ...), the same reason
        suggest_claims()'s other structural detectors avoid requiring
        a successful lift just to decide what to suggest. Only a bare
        `name(param)` call is recognized (the single-argument case
        every relevant name actually takes); an argument that's itself
        an expression is conservatively not attributed to any one
        parameter.
    """
    tree = facts.tree
    if tree is None:
        return {}
    pset = set(facts.params)
    targets: dict = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) != 1:
            continue
        name = _call_name(node)
        if name not in names:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Name) and arg.id in pset:
            targets.setdefault(arg.id, set()).add(name)
    return targets


def _restricted_domain_targets(fn, facts) -> dict:
    """Every real parameter passed bare to a math function with a
    restricted real domain (factorial/sqrt/log/asin/acos/gamma/
    lgamma), mapped to the set of such names it's passed to, the
    is_builtin_safe relevance detector."""
    return _bare_call_targets(facts, _RESTRICTED_DOMAIN_NAMES)


# Real math functions that leave float range at moderate arguments
# (exp overflows near 710, cosh/sinh near 711, gamma near 171.6,
# factorial for any large integer), the is_extremity_safe relevance
# set: a parameter fed bare into one of these is where the
# implementation's representable range ends well before the
# mathematics does.
_OVERFLOW_PRONE_NAMES = frozenset(
    {"exp", "expm1", "cosh", "sinh", "gamma", "factorial"})


def _overflow_prone_params(fn, facts) -> set:
    """Every real parameter passed bare to an overflow-prone math
    function; the set is_extremity_safe[param] is worth suggesting
    for at all."""
    return set(_bare_call_targets(facts, _OVERFLOW_PRONE_NAMES))


# --- hazard knowledge: missing-value guards --------------------------


def _missing_guard_coverage(facts) -> dict:
    """Intent:
        Per real parameter, WHICH missing spellings fn's own body
        guards against with an explicit raising check: "nan" for the
        self-inequality `x != x` or `math.isnan(x)`/`isnan(x)`,
        "none" for `x is None`/`x is not None`, each inside an `if`
        whose body raises. A parameter absent from the dict has no
        recognized missing guard at all.

    Notes:
        A source-level AST scan, the same technique
        _restricted_domain_targets uses; works whether or not fn
        lifts. Only a bare-parameter check is recognized; a compound
        condition still counts for the parts that match (the guard
        rejects those spellings among other things).
    """
    tree = facts.tree
    if tree is None:
        return {}
    pset = set(facts.params)

    def guarded_names(test) -> dict:
        found: dict = {}
        for node in ast.walk(test):
            if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                    and node.left.id in pset):
                if (len(node.ops) == 1 and isinstance(node.ops[0], ast.NotEq)
                        and isinstance(node.comparators[0], ast.Name)
                        and node.comparators[0].id == node.left.id):
                    # x != x, the NaN self-inequality
                    found.setdefault(node.left.id, set()).add("nan")
                if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot))
                        and isinstance(node.comparators[0], ast.Constant)
                        and node.comparators[0].value is None):
                    # x is None / x is not None
                    found.setdefault(node.left.id, set()).add("none")
            if (isinstance(node, ast.Call) and _call_name(node) in ("isnan", "isna")
                    and len(node.args) == 1 and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in pset):
                found.setdefault(node.args[0].id, set()).add("nan")
        return found

    out: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and any(isinstance(s, ast.Raise) for s in node.body):
            for p, spellings in guarded_names(node.test).items():
                out.setdefault(p, set()).update(spellings)
    return out


def _missing_guard_params(facts) -> set:
    """Every real parameter with ANY recognized raising missing-guard
    (whichever spelling), the is_missing_safe suggestion gate."""
    return set(_missing_guard_coverage(facts))


# --- hazard knowledge: poles -----------------------------------------


def _pole_bearing_params(fn, facts) -> set:
    """Intent:
        Every real parameter fn's own fast-path lift finds at least one
        pole for; the set is_pole_safe[param] is worth suggesting for
        at all, the same "only when actually relevant" rule
        _restricted_domain_targets already applies for is_builtin_safe.

    Notes:
        Reuses _points_for_probe's own fast, direct-lift-only search,
        no domain needed to find where a pole *is*, only to later
        decide (in the is_pole_safe derive route, once a claim actually
        adjudicates) whether some declared bound excludes it. Degrades
        to an empty set on any failure, the same as every other
        suggestion detector here.
    """
    try:
        points = _points_for_probe(fn, facts, {}, extensive=False)
    except Exception:
        return set()
    return set(_poles_by_var(points))


# --- the generators --------------------------------------------------


def _pole_hazard_points(fn, facts, domain: dict) -> list[HazardPoint]:
    """Pole locations per parameter, from the fast-path critical-point
    search, the same points the is_pole_safe derive route reasons
    over, as concrete HazardPoints (a pole class like gamma's
    "non-positive integers" carries value None)."""
    try:
        points = _points_for_probe(fn, facts, domain or {}, extensive=False)
    except Exception:
        return []
    out: list[HazardPoint] = []
    for param, poles in _poles_by_var(points).items():
        for h in poles:
            at = str(h["at"])
            try:
                value = float(h["at"])
            except (TypeError, ValueError):
                value = None
            out.append(HazardPoint("pole", param, at, value,
                                   source="critical-point search"))
    return out


def _builtin_edge_points(fn, facts, domain: dict) -> list[HazardPoint]:
    """The domain edges of every restricted builtin a parameter is
    actually passed to: log's zero, asin/acos's unit endpoints, sqrt's
    zero, factorial's negative and non-integer neighbours. These are
    where the implementation's accepted range ends however fine the
    mathematics is on paper."""
    out: list[HazardPoint] = []
    for param, names in _restricted_domain_targets(fn, facts).items():
        for name in sorted(names):
            if name == "factorial":
                # factorial needs a non-negative integer: the nearest
                # violations of each half of that requirement
                out.append(HazardPoint("builtin_domain", param, "-1", -1.0,
                                       source="factorial"))
                out.append(HazardPoint("builtin_domain", param, "0.5", 0.5,
                                       source="factorial"))
                continue
            lo, _lo_incl, hi, _hi_incl = _SAFE_RANGE[name]
            for edge in (lo, hi):
                if math.isinf(edge):
                    continue
                out.append(HazardPoint("builtin_domain", param, str(edge),
                                       float(edge), source=name))
    return out


# the representation ladder: input magnitudes where float behaviour
# changes character, the top of float range, the square-root of it
# (x*x overflows), the exp-overflow threshold, and the denormal band.
_REPRESENTATION_LADDER = (sys.float_info.max, 1e154, 710.0, 1e-308,
                          5e-324)


def _extreme_candidates(bounds, pseudo_infinity=None) -> list[float]:
    """Intent:
        Representation-extreme input candidates a declared bound
        admits: the finite declared endpoints themselves, and (for an
        unbounded side) either the pseudo-infinity cap when one is
        stated or the true representation ladder, the only place in
        the system that ever reaches for float extremes, and it stays
        inside the declared domain.

    Notes:
        `pseudo_infinity` is the resolved (lo, hi) operational range
        or None. Candidates are filtered by domain membership, so an
        excluded endpoint or a bound shape domain_contains rejects
        contributes nothing.
    """
    from .grammar import domain_contains

    def admitted(value: float) -> bool:
        try:
            return domain_contains(value, bounds)
        except Exception:
            return False

    raw: list[float] = []
    lo = hi = None
    if isinstance(bounds, tuple) and not isinstance(bounds, frozenset) \
            and len(bounds) == 2:
        try:
            lo, hi = float(bounds[0]), float(bounds[1])
        except (TypeError, ValueError):
            lo = hi = None
    if lo is not None and abs(lo) != float("inf"):
        raw.append(lo)
    if hi is not None and abs(hi) != float("inf"):
        raw.append(hi)
    unbounded_hi = hi is None or hi == float("inf")
    unbounded_lo = lo is None or lo == -float("inf")
    if unbounded_hi:
        raw.extend([pseudo_infinity[1]] if pseudo_infinity is not None
                   else list(_REPRESENTATION_LADDER))
    if unbounded_lo:
        raw.extend([pseudo_infinity[0]] if pseudo_infinity is not None
                   else [-v for v in _REPRESENTATION_LADDER])
    out: list[float] = []
    for cand in raw:
        if admitted(cand) and cand not in out:
            out.append(cand)
    return out


def _extreme_hazard_points(fn, facts, domain: dict) -> list[HazardPoint]:
    """Representation-extreme candidates per scalar parameter, from
    the declared bounds alone (a claim-level pseudo-infinity range is
    applied by the consumer, not here; the registry sees only the
    function and domain)."""
    out: list[HazardPoint] = []
    for p in facts.params:
        if facts.param_kinds.get(p) not in ("scalar", "unknown"):
            continue
        for value in _extreme_candidates(domain.get(p)):
            out.append(HazardPoint("extreme", p, f"{value:g}", value,
                                   source="representation ladder"))
    return out


_DYNAMIC_WRITE_CALLS = frozenset({"setattr", "delattr", "exec", "eval",
                                  "__import__", "vars", "globals"})


def _state_writes(facts) -> list[dict]:
    """Intent:
        Every syntactic site where the body could write EXTERNAL
        state, as structured records {"kind", "target", "line"}:
        global/nonlocal declarations, mutator-method calls on
        parameters, subscript/attribute assignment rooted at a
        parameter or at a non-local external name (a module attribute,
        os.environ, a class), and the dynamic write escapes
        (setattr/exec/...). The is_state_safe member's derive half
        reads this; empty is necessary for the write-free certificate
        but not sufficient (see _write_free).

    Notes:
        Locals are skipped the same way _effects skips them (a name
        assigned in the body), reads are deliberately NOT here;
        external reads are is_deterministic's territory.
    """
    from ._math_vocab import _call_name as call_name
    tree = facts.tree
    if tree is None:
        return []
    pset = set(facts.params)
    local_names = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   for t in n.targets if isinstance(t, ast.Name)}
    out: list[dict] = []

    def root_of(node):
        while isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        return node.id if isinstance(node, ast.Name) else None

    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                out.append({"kind": type(node).__name__.lower(),
                            "target": name, "line": line})
        elif isinstance(node, ast.Call):
            f = node.func
            name = call_name(node)
            if name in _DYNAMIC_WRITE_CALLS:
                out.append({"kind": "dynamic_write_escape",
                            "target": name, "line": line})
            elif isinstance(f, ast.Attribute):
                root = root_of(f.value)
                if root in pset:
                    # ANY method call on a parameter can mutate it;
                    # the recognized mutator list is a lower bound,
                    # not a completeness proof
                    out.append({"kind": "argument_method_call",
                                "target": root, "line": line})
                elif root is not None and root not in local_names:
                    out.append({"kind": "external_method_call",
                                "target": f"{root}.{f.attr}", "line": line})
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            for t in targets:
                if not isinstance(t, (ast.Subscript, ast.Attribute)):
                    continue
                root = root_of(t)
                if root in pset:
                    out.append({"kind": "argument_write",
                                "target": root, "line": line})
                elif root is not None and root not in local_names:
                    out.append({"kind": "external_write",
                                "target": root, "line": line})
    return out


def _write_free(facts) -> bool:
    """The write-free certificate: no syntactic external-write site at
    all, and every name resolves (an unresolved or global-variable
    read leaves room for state this walk can't see). Sufficient for
    is_state_safe's structural proof."""
    if _state_writes(facts):
        return False
    if getattr(facts, "unresolved", None) or getattr(facts, "global_vars", None):
        return False
    return True


def _admitted_spelling(value: float, bounds):
    """The machine spelling of `value` the bound admits, the int
    spelling first when the value is integral (a value-typed Z/N
    bound admits machine ints only), else the float, or None when
    neither spelling is admitted. The one place trial candidates
    learn which representation to arrive in."""
    from .grammar import domain_contains
    spellings = ((int(value), float(value))
                 if float(value).is_integer() else (float(value),))
    for spelled in spellings:
        try:
            if domain_contains(spelled, bounds):
                return spelled
        except Exception:
            continue
    return None


def _emptiness_guard_params(facts) -> set:
    """Every sequence parameter fn's own body guards against emptiness
    with an explicit raising check, `if not xs: raise` or
    `if len(xs) == 0: raise` (a compound condition counts for the
    part that matches). The is_empty_safe relevance gate and the
    deliberate-rejection signal its derive half reads."""
    tree = facts.tree
    if tree is None:
        return set()
    pset = {p for p in facts.params
            if facts.param_kinds.get(p) == "sequence"}
    if not pset:
        return set()

    def guarded_names(test) -> set:
        found = set()
        for node in ast.walk(test):
            if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)
                    and isinstance(node.operand, ast.Name)
                    and node.operand.id in pset):
                found.add(node.operand.id)      # not xs
            if (isinstance(node, ast.Compare) and len(node.ops) == 1
                    and isinstance(node.ops[0], (ast.Eq, ast.Lt, ast.LtE))
                    and isinstance(node.left, ast.Call)
                    and _call_name(node.left) == "len"
                    and len(node.left.args) == 1
                    and isinstance(node.left.args[0], ast.Name)
                    and node.left.args[0].id in pset
                    and isinstance(node.comparators[0], ast.Constant)
                    and node.comparators[0].value in (0, 1)):
                found.add(node.left.args[0].id)  # len(xs) == 0 / < 1
        return found

    out: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and any(isinstance(s, ast.Raise)
                                            for s in node.body):
            out |= guarded_names(node.test)
    return out


# machine type names a raising type guard can meaningfully name for a
# numeric parameter, the v1 spelling vocabulary
_SPELLING_TYPES = frozenset({"int", "float", "bool", "complex"})


def _annotated_params(facts) -> set:
    """Every parameter carrying an explicit type annotation in the
    source; read off the AST arguments directly (param_kinds can't
    answer this: a "scalar" kind may come from the arithmetic
    fallback, not an annotation)."""
    tree = facts.tree
    if tree is None:
        return set()
    args = tree.args
    out = set()
    for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
        if a.annotation is not None:
            out.add(a.arg)
    return out


def _type_guard_params(facts) -> dict:
    """Intent:
        Per real parameter, what its raising type guards say: a dict
        {"accepts": frozenset | None, "rejects": frozenset}, an
        accepting guard (`if not isinstance(x, int): raise`,
        `if type(x) is not int: raise`) names the machine types the
        body lets THROUGH; a rejecting guard (`if isinstance(x, bool):
        raise`, `if type(x) is float: raise`) names types it turns
        away. A parameter absent from the dict has no recognized type
        guard.

    Notes:
        The same raising-If walk as _missing_guard_coverage. Only
        bare-parameter isinstance/type-is shapes over the numeric
        type names (int/float/bool/complex) are recognized; a class
        tuple contributes each of its names. accepts is None until an
        accepting guard is seen (an empty frozenset would wrongly
        mean "accepts nothing").
    """
    tree = facts.tree
    if tree is None:
        return {}
    pset = set(facts.params)

    def type_names(node) -> frozenset:
        names = []
        for sub in (node.elts if isinstance(node, ast.Tuple) else [node]):
            if isinstance(sub, ast.Name) and sub.id in _SPELLING_TYPES:
                names.append(sub.id)
        return frozenset(names)

    def read(test, out: dict, negated: bool = False) -> None:
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            read(test.operand, out, negated=not negated)
            return
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or) \
                and not negated:
            # `if isinstance(n, bool) or not isinstance(n, int): raise`
            # raises when ANY part is true, so each part contributes
            # its own accept/reject reading on its own
            for part in test.values:
                read(part, out)
            return
        if (isinstance(test, ast.Call) and _call_name(test) == "isinstance"
                and len(test.args) == 2
                and isinstance(test.args[0], ast.Name)
                and test.args[0].id in pset):
            names = type_names(test.args[1])
            if names:
                entry = out.setdefault(test.args[0].id,
                                       {"accepts": None,
                                        "rejects": frozenset()})
                if negated:   # raise unless isinstance -> accepts
                    entry["accepts"] = (names if entry["accepts"] is None
                                        else entry["accepts"] | names)
                else:         # raise when isinstance -> rejects
                    entry["rejects"] = entry["rejects"] | names
            return
        if (isinstance(test, ast.Compare) and len(test.ops) == 1
                and isinstance(test.ops[0], (ast.Is, ast.IsNot, ast.Eq,
                                             ast.NotEq))
                and isinstance(test.left, ast.Call)
                and _call_name(test.left) == "type"
                and len(test.left.args) == 1
                and isinstance(test.left.args[0], ast.Name)
                and test.left.args[0].id in pset):
            names = type_names(test.comparators[0])
            if not names:
                return
            inverted = isinstance(test.ops[0], (ast.IsNot, ast.NotEq))
            entry = out.setdefault(test.left.args[0].id,
                                   {"accepts": None, "rejects": frozenset()})
            if inverted != negated:   # raise when type is NOT T -> accepts T
                entry["accepts"] = (names if entry["accepts"] is None
                                    else entry["accepts"] | names)
            else:                     # raise when type IS T -> rejects T
                entry["rejects"] = entry["rejects"] | names

    out: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and any(isinstance(s, ast.Raise)
                                            for s in node.body):
            read(node.test, out)
    return out


def _type_discipline_params(fn, facts) -> set:
    """The is_representation_safe suggestion gate: every non-sequence
    parameter with an explicit type annotation or a recognized raising
    type guard; representation discipline is only worth claiming
    where the author stated types structurally at all."""
    relevant = _annotated_params(facts) | set(_type_guard_params(facts))
    return {p for p in relevant
            if facts.param_kinds.get(p) != "sequence"}


def _string_input_params(facts) -> set:
    """The is_arbitrary_input_safe suggestion gate: every parameter the
    body treats as a string (a bare `str`-annotated or string-inferred
    parameter). That is exactly the input the algebraic battery declines
    to sample, so it is where fuzzing for an accidental crash is worth
    claiming."""
    return {p for p in facts.params
            if facts.param_kinds.get(p) == "string"}


def _spelling_values(bounds) -> list[int]:
    """The integral mathematical values worth cross-spelling for one
    parameter: small integers and integral finite endpoints inside
    the bound's numeric range (value-level, per-spelling machine
    admittance is the probe's own question)."""
    lo = hi = None
    if isinstance(bounds, tuple) and not isinstance(bounds, frozenset) \
            and len(bounds) == 2:
        try:
            lo, hi = float(bounds[0]), float(bounds[1])
        except (TypeError, ValueError):
            lo = hi = None
    candidates: list[int] = []
    for raw in ([lo, hi] if lo is not None else []) + [0, 1, 2]:
        if raw is None or raw != raw or abs(raw) == float("inf"):
            continue
        if float(raw) != int(raw):
            continue
        v = int(raw)
        if lo is not None and hi is not None and not (lo <= v <= hi):
            continue
        if v not in candidates:
            candidates.append(v)
    return candidates


def _type_hazard_points(fn, facts, domain: dict) -> list[HazardPoint]:
    """Cross-spelling candidates per non-sequence parameter: each is
    an integral mathematical value whose machine spellings (int,
    float, bool where applicable) the representation trials compare."""
    out: list[HazardPoint] = []
    for p in facts.params:
        if facts.param_kinds.get(p) == "sequence":
            continue
        for v in _spelling_values(domain.get(p)):
            out.append(HazardPoint("type", p, str(v), float(v),
                                   source="integral spelling point"))
    return out


def _missing_hazard_points(fn, facts, domain: dict) -> list[HazardPoint]:
    """A literal-NaN input per real scalar parameter, the missing
    sentinel every domain carries a policy for (included by default,
    excluded by an explicit \\ {∅})."""
    return [HazardPoint("missing", p, "nan", float("nan"),
                        source="missing policy")
            for p in facts.params
            if facts.param_kinds.get(p) in ("scalar", "unknown")]


# The registry: hazard kind -> generator(fn, facts, domain) ->
# iterable of HazardPoints. A new kind (representation extremes, type
# variants, ...) joins by registration.
#: The decade sweep: magnitudes a uniform draw over an ordinary
#: declared interval essentially never produces, yet where float
#: behaviour actually changes, denormal, tiny, huge, and near the
#: overflow edge. Both signs are offered per value.
_MAGNITUDE_DECADES = (5e-324, 1e-300, 1e-12, 1e12, 1e300)


def _magnitude_hazard_points(fn, facts, domain: dict) -> list[HazardPoint]:
    """Every numeric parameter, swept across magnitude decades: the
    stress that makes homogeneity, stability, and overflow claims
    honest. Out-of-domain values cost nothing, the sampler's own
    admission check drops them."""
    out = []
    kinds = getattr(facts, "param_kinds", {}) or {}
    for param in getattr(facts, "params", ()):
        if kinds.get(param) == "sequence":
            continue
        for magnitude in _MAGNITUDE_DECADES:
            for value in (magnitude, -magnitude):
                out.append(HazardPoint(
                    kind="magnitude", param=param,
                    at=f"decade sweep {value:g}", value=value,
                    source="magnitude spread"))
    return out


_GENERATORS: dict[str, Callable[..., Iterable[HazardPoint]]] = {
    "pole": _pole_hazard_points,
    "builtin_domain": _builtin_edge_points,
    "missing": _missing_hazard_points,
    "extreme": _extreme_hazard_points,
    "type": _type_hazard_points,
    "magnitude": _magnitude_hazard_points,
}


def register_hazard_generator(kind: str, generator: Callable) -> None:
    """Register a hazard-point generator for `kind`, replacing any
    existing one at that kind, the extension seam an external
    backend (an AD package's conditioning candidates, say) uses."""
    _GENERATORS[kind] = generator


def hazard_points(fn, facts, domain: dict | None = None,
                  kinds: Iterable[str] | None = None) -> list[HazardPoint]:
    """Intent:
        Every known hazard location for fn over the declared domain,
        across all registered kinds (or just `kinds`, when given),
        the one query every consumer asks.

    Notes:
        A generator that fails contributes nothing rather than
        aborting the sweep: hazard discovery is best-effort context,
        and one kind's failure says nothing about another's points.
    """
    wanted = _GENERATORS if kinds is None else {
        k: _GENERATORS[k] for k in kinds if k in _GENERATORS}
    out: list[HazardPoint] = []
    for generator in wanted.values():
        try:
            out.extend(generator(fn, facts, domain or {}))
        except Exception:
            continue
    return out
