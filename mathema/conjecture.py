# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The conjecture pipeline: externally proposed claims, machine-adjudicated.

A conjecture is a claim stated by someone other than the analyzer: a human in
a review, or a model acting as a hypothesis generator. It enters as
`conjectured`, and the verifier decides what it becomes: `holds (n=…)` with
seeded probing, or `falsified` with the counterexample kept. The proposer
never adjudicates its own claims.

Laws are written over the function name `f` and its parameter names, with any
extra free names treated as auxiliary real variables (sampled alongside the
inputs):

    Conjecture("odd", lhs="f(-x)", rhs="-f(x)", relation="==")
    Conjecture("bounded", lhs="min(x)", rhs="f(x, alpha)", relation="<=")
    Conjecture("shift", lhs="f(x + c)", rhs="f(x) + c", relation="==")

Expressions are validated against an AST whitelist before evaluation:
arithmetic, the comparisons the relation handles, the grammar's own
functions, and calls to the functions the claim names. A dotted name in
a claim (`let g = numpy.mean`) resolves to that function, which runs in
the same way as importing it and calling it directly would, except that
a name reaching a refused module (os, subprocess, builtins and the
others `_claim_reach` lists) is refused. A binding into third-party code
whose effects mathema cannot establish runs and carries a warning
naming it.
"""
from __future__ import annotations

from ._signatures import module_scope
import ast
import contextvars
import cmath as _cmath
import inspect
import math
import os
import re
import sys
from dataclasses import dataclass, field
from dataclasses import replace as _dc_replace

from . import _shapes, families, routes
from ._math_vocab import _D_AT_SENTINEL, MATH_CONSTANTS
from .analysis import analyze_source
from .grammar import (Domain, InvalidDomain, NoRelation,
                      is_missing, extract_assuming_clause,
                      extract_diff_fraction_sugar, extract_let_bindings,
                      extract_outcome_clause, _split_top_level,
                      is_reserved, normalize,
                      parse_domain_safety, parse_raises, split_quantifier,
                      split_membership, split_relation_chain,
                      unexpanded_prime_message,
                      UnreadableSpelling)
from . import linalg
from ._scan import _split_commas, blank_strings
from ._float_text import exact_literal_text, overlong_literals
from .domain import DuplicateBinding
from .domain import operational_domain as _operational_domain
from . import _conditioning
from ._allowance import (ABSOLUTE, exact_side_at, largest_miss, reference_side,
                         relation_within)
from ._exact_side import exact_sides
from .probing import (ComplexResult, _close, _fmt, _prepare_sampling, string_domain_hint,
                      _probe_density, _sampling_shorthand, _synth,
                      _synth_dict, complex_is_a_raise, holds_inf,
                      classified, holds_nan, inputs_missing, missing_class,
                      same_infinity,
                      is_complex_value, ordering_shortfall,
                      quiet_while_probing, relation_holds_elementwise,
                      values_differ)
from .records import (_EXC_TYPES, Probe, PseudoInfinity, classify_verdict,
                      statement_text)
from .symbolic import (mentions_matrix_ops, try_prove, try_prove_matrix,
                       try_prove_raises)
from .runtime_types import SEQUENCE_KINDS
from ._signatures import callable_signature


def _numeric_literal(node: ast.AST):
    """(True, value) for a bare numeric literal or its negation ("-1"
    parses as UnaryOp(USub, Constant(1)), not a single negative
    Constant); (False, None) for anything else."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        ok, v = _numeric_literal(node.operand)
        if not ok:
            return False, None
        return True, (-v if isinstance(node.op, ast.USub) else v)
    if (isinstance(node, ast.Constant) and not isinstance(node.value, bool)
            and isinstance(node.value, (int, float))):
        return True, node.value
    return False, None   # a complex literal never pins a real domain


def _inferred_literal_domain(text: str, sig_params: list) -> dict:
    """Every f(...) call anywhere in text (a claim's own lhs/rhs, or a
    raises() call source) whose argument at a real parameter's own
    position is a plain numeric literal, mapped to a degenerate single-
    point domain for that parameter. Lets a claim like f(x, 0), a
    literal substituted directly into a guarded parameter's position,
    inform branch pruning about that parameter without a separate
    quantifier (for code in [0, 0], ...). An explicit domain always
    wins over an inferred one, applied by the caller."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return {}
    inferred: dict = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "f"):
            continue
        for p, arg in zip(sig_params, node.args):
            ok, lit = _numeric_literal(arg)
            if ok:
                inferred[p] = (float(lit), float(lit))
    return inferred


def _names_in_text(text: str) -> set:
    """The bare names a claim expression reads (its variables, not the
    functions it calls)."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return set()
    called = {id(node.func) for node in ast.walk(tree)
              if isinstance(node, ast.Call)}
    return {node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name) and id(node) not in called}


def _literal_call_args(text: str, sig_params: list,
                       varied: "set | None" = None) -> dict:
    """`{param: value}` for every `f(...)` call argument that is a plain
    literal at a real parameter's position: the call passes that value
    verbatim, so the parameter is FIXED to it, not synthesized. Unlike
    `_inferred_literal_domain` (numeric only, for branch pruning), this
    keeps every literal kind (a string `"nope"`, a `True`, a number, a
    list such as the empty `[]`) and its actual value, so both the sample and the counterexample witness
    show what the call really passed rather than a synthesized
    placeholder in a literal's slot. A parameter some other call passes
    as anything but a literal (`f(xs, y0) == f(xs, 0) + y0`) is still
    drawn: its name is added to `varied` when given, and left out of
    the result."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return {}
    fixed: dict = {}
    moving: set = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "f"):
            continue
        for p, arg in zip(sig_params, node.args):
            if isinstance(arg, ast.Constant):
                fixed[p] = arg.value
            elif isinstance(arg, (ast.List, ast.Tuple)):
                # a literal container (`f([])`, `f([1.0, 2.0])`) passes
                # that container verbatim
                try:
                    fixed[p] = ast.literal_eval(arg)
                except (ValueError, SyntaxError):
                    moving.add(p)
            else:
                moving.add(p)
    if varied is not None:
        varied.update(moving)
    return {p: v for p, v in fixed.items() if p not in moving}


def _yaml_safe_args(args) -> list:
    """Intent:
        A falsifying argument tuple as YAML-safe values a later run can
        replay exactly: numbers pass through, a complex value becomes
        its coordinate spelling, sequences recurse.
    """
    out = []
    for v in args:
        if isinstance(v, complex) and not isinstance(v, (int, float)):
            # tagged, so a string witness that reads as a complex
            # number (`"j"`) can never be mistaken for one
            out.append({"complex": f"{v.real:g}{v.imag:+g}j"})
        elif isinstance(v, (list, tuple)):
            out.append(_yaml_safe_args(v))
        else:
            out.append(v)
    return out


_MAX_CORNERS = 64


def _box_corner_arrays(bound) -> list:
    """Intent:
        For a vector or matrix of fixed size whose elements lie in one
        closed finite interval (`[-0.1, 0.1]^13`, `[-1, 1]^(4,4)`), the
        array with every element at the lower end and the one with
        every element at the upper end, as nested lists; [] for any
        other bound. A linear quantity of the elements, such as their
        sum, is least and greatest at these two arrays.
    """
    import dataclasses

    from .domain import Domain, domain_contains
    if not isinstance(bound, Domain) or not bound.dims:
        return []
    try:
        sizes = [int(d) for d in bound.dims]
    except (TypeError, ValueError):
        return []
    if len(bound.pieces) != 1 or any(n < 1 for n in sizes):
        return []
    piece = bound.pieces[0]
    if not (isinstance(piece, tuple) and len(piece) == 2) \
            or getattr(piece, "bare", False):
        return []
    lo, hi = piece
    try:
        if not (math.isfinite(lo) and math.isfinite(hi)):
            return []
    except TypeError:
        return []
    element = dataclasses.replace(bound, dims=())
    ends = [v for v, closed in ((lo, getattr(piece, "closed_lo", True)),
                                (hi, getattr(piece, "closed_hi", True)))
            if closed and domain_contains(v, element)]

    def filled(value, axes):
        if len(axes) == 1:
            return [value] * axes[0]
        return [filled(value, axes[1:]) for _ in range(axes[0])]
    return [filled(v, sizes) for v in dict.fromkeys(ends)]


def _domain_corners(kinds: dict, domain: dict, literal_args: dict) -> list:
    """Intent:
        The corners of a claim's bounded domain box as argument lists,
        in `kinds` order: every combination of each parameter's included
        endpoints, with a literal argument held at its literal, and a
        fixed-size vector or matrix at its all-lower and all-upper
        arrays (`_box_corner_arrays`). Empty unless every parameter is a
        real or integer scalar with a finite interval domain, such a
        vector or matrix, or fixed by a literal, and when the box has
        more than `_MAX_CORNERS` corners.

    Notes:
        Only an endpoint the domain includes is used; an open end is not
        in the domain, so a point there is never tried. A value the
        domain excludes is dropped. A raise that needs two parameters at
        their extremes together is invisible to per-parameter sampling
        and found here.
    """
    import itertools

    from .domain import Domain, domain_contains

    choices = []
    for p, k in kinds.items():
        if p in literal_args:
            choices.append([literal_args[p]])
            continue
        bound = domain.get(p)
        if k in SEQUENCE_KINDS:
            filled = _box_corner_arrays(bound)
            if not filled:
                return []
            choices.append(filled)
            continue
        if k not in ("scalar", "int"):
            return []
        pieces = (bound.pieces if isinstance(bound, Domain) else (bound,))
        ends: list = []
        for piece in pieces:
            if not (isinstance(piece, tuple) and not isinstance(piece, frozenset)
                    and len(piece) == 2):
                return []
            lo, hi = piece
            try:
                if not (math.isfinite(lo) and math.isfinite(hi)):
                    return []
            except TypeError:
                return []
            if getattr(piece, "bare", False):
                # an undeclared direction has no corner: its reach is
                # visited by the sampler's far draws
                return []
            if getattr(piece, "closed_lo", True):
                ends.append(lo)
            if getattr(piece, "closed_hi", True):
                ends.append(hi)
        ends = [v for v in dict.fromkeys(ends) if domain_contains(v, bound)]
        if k == "int":
            ends = [int(v) for v in ends if float(v).is_integer()]
        if not ends:
            return []
        choices.append(ends)
    total = 1
    for c in choices:
        total *= len(c)
    if not choices or total > _MAX_CORNERS:
        return []
    return [list(combo) for combo in itertools.product(*choices)]


def _representative_values(kind: str, bound) -> list:
    """Intent:
        A few in-domain values for one scalar parameter: the midpoint
        and the included finite endpoints of each piece of its bound,
        or 0, 1 and -1 when it is unbounded. An integer parameter keeps
        only integer values. Empty for a bound shape with no interval
        pieces.
    """
    from .domain import Domain, domain_contains

    if bound is None or isinstance(bound, str):
        raw = [0.0, 1.0, -1.0]
    else:
        pieces = bound.pieces if isinstance(bound, Domain) else (bound,)
        raw = []
        for piece in pieces:
            if not (isinstance(piece, tuple) and len(piece) == 2):
                continue
            lo, hi = piece
            try:
                finite_lo, finite_hi = math.isfinite(lo), math.isfinite(hi)
            except TypeError:
                continue
            if finite_lo and finite_hi:
                raw.append((lo + hi) / 2)
            if finite_lo and getattr(piece, "closed_lo", True):
                raw.append(lo)
            if finite_hi and getattr(piece, "closed_hi", True):
                raw.append(hi)
            if not (finite_lo or finite_hi):
                raw.extend([0.0, 1.0, -1.0])
    if kind == "int":
        raw = [int(round(v)) for v in raw]
    return [v for v in dict.fromkeys(raw)
            if bound is None or domain_contains(v, bound)]


def _guard_points(fn, facts, kinds: dict, domain: dict,
                  literal_args: dict) -> list:
    """Intent:
        Argument lists, in `kinds` order, that sit on the switching
        surfaces of the function's own guards inside the claim's
        domain: `if x * y == 0.0:` over `x in [-1, 2]` yields points
        with `x = 0`. A coordinate the surface does not fix takes its
        parameter's midpoint (or first representative value), a literal
        argument its literal. Empty unless every parameter is a real or
        integer scalar (or fixed by a literal).

    Notes:
        An equality guard holds on a set of measure zero, which random
        sampling never lands on, so these points are pinned the way the
        domain's corners are. Wall-clock capped at the fast budget; a
        cap that fires yields no points.
    """
    from . import _timeout as _timeout_mod
    from ._timeout import _with_timeout
    from .domain import domain_contains
    from .symbolic._guard_points import guard_surfaces, surface_points

    if facts.tree is None or not (
            facts.branch_count
            or any(isinstance(n, ast.IfExp) for n in ast.walk(facts.tree))):
        return []
    candidates: dict = {}
    for p, k in kinds.items():
        if p in literal_args:
            continue
        if k not in ("scalar", "int"):
            return []
        values = _representative_values(k, domain.get(p))
        if not values:
            return []
        candidates[p] = values

    def compute():
        surfaces, symbols = guard_surfaces(fn, facts)
        if not surfaces:
            return []
        fixed = {symbols[p]: v for p, v in literal_args.items()
                 if p in symbols and isinstance(v, (int, float))
                 and not isinstance(v, bool)}
        if fixed:
            surfaces = [sf.subs(fixed) for sf in surfaces]
        return surface_points(surfaces, symbols, candidates)

    try:
        points = _with_timeout(compute, _timeout_mod.FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return []
    out: list = []
    for point in points:
        args = []
        for p, k in kinds.items():
            if p in literal_args:
                args.append(literal_args[p])
                continue
            v = point.get(p, candidates[p][0])
            if k == "int":
                if not float(v).is_integer():
                    break
                v = int(v)
            bound = domain.get(p)
            if bound is not None and not domain_contains(v, bound):
                break
            args.append(v)
        else:
            if args not in out:
                out.append(args)
    return out


def _sample_in_domain(value, bound) -> bool:
    """Intent:
        Whether one sampled value lies inside its parameter's declared
        bound, for the probe route's per-trial check. A language domain
        judges every value; otherwise only a real number is judged
        here: a sequence, mapping, string or complex value has its own
        sampler, and a missing value is the missing-value policy's to
        decide. A whole float counts as the integer it
        equals, and an infinity is inside exactly when the bound is
        unbounded in its direction.
    """
    from .domain import domain_contains
    if bound is None:
        return True
    if getattr(bound, "base_type", None) == "L":
        # a language domain judges its own members, strings and
        # structured values included
        try:
            return bool(domain_contains(value, bound))
        except Exception:
            return True
    if isinstance(value, bool) \
            or not isinstance(value, (int, float)) or value != value:
        return True
    try:
        if math.isinf(value):
            far = math.copysign(sys.float_info.max, value)
            return bool(domain_contains(far, bound)
                        or domain_contains(int(far), bound))
        if domain_contains(value, bound):
            return True
        return (isinstance(value, float) and value.is_integer()
                and bool(domain_contains(int(value), bound)))
    except Exception:
        return True


def _pinned_arg_sets(cj, arity: int, kinds: "list | None" = None) -> list:
    """Intent:
        The claim's recorded counterexamples (`Conjecture.pins`) as
        replayable argument tuples, restored from their YAML-safe
        spellings; entries with the wrong arity are skipped rather
        than misapplied.

    Notes:
        A complex witness is stored tagged, `{"complex": "1+2j"}`. An
        older record stored it as a bare string, which is read as a
        complex number only where the parameter's kind can hold one:
        a string parameter's `"j"` stays the string it was.
    """
    out = []
    for pin in cj.pins or []:
        stored = pin.get("args") if isinstance(pin, dict) else None
        if not isinstance(stored, list) or len(stored) != arity:
            continue
        restored = []
        for i, v in enumerate(stored):
            kind = kinds[i] if kinds is not None and i < len(kinds) else None
            if isinstance(v, dict) and set(v) == {"complex"}:
                restored.append(complex(v["complex"]))
                continue
            if (isinstance(v, str) and ("j" in v or "J" in v)
                    and kind not in ("string", "dict", "bool", "table")
                    and kind not in SEQUENCE_KINDS):
                try:
                    restored.append(complex(v))
                    continue
                except ValueError:
                    pass
            restored.append(v)
        out.append(restored)
    return out


def _claim_family(cj, fn, facts):
    """The registered ClaimFamily for the claim's own base name (the
    part before "[param]"), or None, the same lookup-by-name-then-
    confirm pattern _prove.py's own shape-based dispatch already uses,
    just keyed by claim name instead of function shape. A safety
    predicate additionally dispatches by its relation (the structured
    field the grammar parsed) when the display name doesn't match,
    a renamed predicate claim still reaches its family."""
    base = families.claim_base_name(cj.name)
    family = families.families().get(base)
    if family is not None and family.can_handle(fn, facts, cj.name) \
            and _statement_is_family_claim(cj, base, family, facts):
        return family
    if cj.relation in routes.examine_predicates():
        family = families.families().get(cj.relation)
        if family is not None:
            return family
    return None


#: the families whose routes read a claim's name rather than its text,
#: with the statement each adjudicates: derivative order and relation,
#: against zero, in the parameter the name brackets
_DERIVATIVE_FAMILY_FORMS = {
    "monotonic_increasing": (1, ">="),
    "monotonic_decreasing": (1, "<="),
    "affine": (2, "=="),
    "convex": (2, ">="),
    "concave": (2, "<="),
}

_ACCURATE = "mathema.f.accurate"

_COMPARISON_RELATIONS = frozenset({"==", "~=", "!=", "<=", ">=", "<", ">"})

#: the families stated as `f(<params>) == f(<params>)`, the call agreeing
#: with itself, each examining one way it could fail to
_SELF_AGREEMENT_FAMILIES = frozenset({"is_deterministic", "is_reproducible",
                                      "is_state_safe"})

#: the families whose claim states a REGION under the family's name (the
#: restriction form, `{name: is_defined, statement: "x >= 0"}`), each
#: with the stratum its region belongs to (P9): `is_defined` is
#: mathematics (the region where the function has a value, a derive
#: guard and a probe), `is_overflow_safe` is computation (the region
#: where one implementation does not overflow, adjudicated by execution
#: only)
REGION_ROW_STRATA = {"is_defined": "mathematics",
                     "is_overflow_safe": "computation"}


def region_row_kind(name) -> "str | None":
    """The region family a claim name belongs to (`is_defined` for
    `is_defined`, `is_defined[2]` and `is_defined@axis=0`, `is_overflow_safe` for
    `is_overflow_safe` and `is_overflow_safe[x]`), or None for any
    other name."""
    base = families.claim_base_name(name)
    return base if base in REGION_ROW_STRATA else None


def _squash(text) -> str:
    """Claim text with all whitespace removed, for comparing two
    spellings of the same expression."""
    return "".join((text or "").split())


def _statement_is_family_claim(cj, base: str, family, facts) -> bool:
    """Intent:
        Whether the claim's statement is the one the family registered
        under its name adjudicates, so a name alone never swaps the
        question being asked.

    Notes:
        A predicate statement (`is_pole_safe(x)`, `is_symmetric(f(A))`)
        matches the family of the same name. The derivative-sign
        families match `d(f(<params>), p) >= 0` and its siblings, with
        `p` the bracketed parameter. `is_numerically_stable` matches
        `g(f, <params>) == 1` with `g` bound to `mathema.f.accurate`. `is_deterministic`, `is_reproducible` and
        `is_state_safe` match `f(<params>) == f(<params>)`. `is_defined` states a region under its name (the
        restriction form in docs/conditional-claims.md) and so accepts
        any comparison. A family that dispatches on the function's
        shape and reads the claim's own text (the dot-product, sum and
        fold lifters) accepts any statement.
    """
    from .claim_families import (MatrixPropertyFamily, OutputPredicateFamily,
                                 _NamedClaimFamily)
    if cj.relation in routes.examine_predicates() \
            or cj.relation not in _COMPARISON_RELATIONS:
        return cj.relation == base
    if region_row_kind(base):
        return True
    call = f"f({', '.join(facts.params)})"
    form = _DERIVATIVE_FAMILY_FORMS.get(base)
    if form is not None:
        order, relation = form
        param = cj.name[len(base):]
        if not (param.startswith("[") and param.endswith("]")):
            return False
        param = param[1:-1]
        expected = f"d({call}, {', '.join([param] * order)})"
        return (cj.relation == relation and _squash(cj.rhs) == "0"
                and _squash(cj.lhs) == _squash(expected))
    if base in _SELF_AGREEMENT_FAMILIES:
        return (cj.relation == "==" and _squash(cj.lhs) == _squash(call)
                and _squash(cj.rhs) == _squash(call))
    if base == "is_numerically_stable":
        bound = (cj.funcs or {}).get("g")
        from .f import accurate
        return (cj.relation == "==" and _squash(cj.rhs) == "1"
                and _squash(cj.lhs) == _squash(
                    f"g(f, {', '.join(facts.params)})")
                and (bound == _ACCURATE or bound is accurate))
    return not isinstance(family, (_NamedClaimFamily, MatrixPropertyFamily,
                                   OutputPredicateFamily))


def _lengths_scope(cj, family, facts):
    """Intent:
        The context a derive attempt runs in: a family claim that asks
        whether calls agree with each other (`is_deterministic`,
        `is_reproducible`, `is_state_safe`) or how accurate they are
        (`is_numerically_stable`) is not judged at the sequence lengths
        where the call raises, which say nothing about agreement or
        accuracy; every other claim is.
    """
    import contextlib

    from .symbolic._prove import lengths_unjudged
    base = families.claim_base_name(cj.name)
    try:
        agreement = (base in _SELF_AGREEMENT_FAMILIES
                     or base == "is_numerically_stable") \
            and _statement_is_family_claim(cj, base, family, facts)
    except Exception:
        agreement = False
    return lengths_unjudged() if agreement else contextlib.nullcontext()


def _resolve_func_ref(ref: str, *, root: str = "."):
    """A dotted `module.qualname` string (a mathema-internal helper, or
    any other importable function, the same shape a spec key already
    uses) resolved to the live callable it names, including a method
    key like `pkg.mod.Class.method` (the longest importable prefix is
    the module, the rest is walked as attributes). A language-tagged
    key (`ts:src/ema.ts#ema`) resolves through its registered target
    resolver instead, so a store sweep reaches foreign implementations
    the same way it reaches Python ones. `None` if nothing importable
    or the name isn't found there. A method or attribute of a runtime
    type's class (`pandas.Series.std`, `numpy.ndarray.T`) resolves to
    its receiver form, a function of the receiver `a`
    (`runtime_types._receivers.receiver_form`)."""
    from .targets import _prefix_walk

    if ":" in ref:
        from ._target_resolvers import get_resolver
        resolver = get_resolver(ref.partition(":")[0])
        if resolver is not None:
            try:
                resolved = resolver(ref, root)
            except Exception:
                return None
            if resolved is not None:
                return resolved.functions.get(ref)
        return None
    if "." not in ref:
        return None
    from .runtime_types._receivers import receiver_form
    receiver = receiver_form(ref)
    if receiver is not None:
        return receiver
    walked = _prefix_walk(ref, root)
    if walked is None:
        return None
    obj = walked[2]
    return obj if callable(obj) else None

# what parameter kind (analysis.py's _param_kinds vocabulary) a stated
# domain base type corresponds to, for reconciling a let-declared type
# against the real parameter's own annotation.
_BASE_TYPE_KIND = {"Z": "int", "N": "int", "R": "scalar", "C": "complex"}


# which real parameter kinds (analysis.param_kinds' vocabulary) a
# language's member kind is compatible with: a row is a mapping the body
# reads as a dict, a table is a table parameter or one iterated or
# subscripted, an object is anything the body does not pin down; a
# sequence is any of the runtime types' sequence kinds (a list, a
# vector, a matrix)
_KIND_COMPATIBLE = {
    "string": {"string"},
    "mapping": {"dict"},
    "sequence": set(SEQUENCE_KINDS),
    "object": {"dict", "unknown"} | SEQUENCE_KINDS,
    "row": {"dict"},
    "table": {"table", "dict"} | SEQUENCE_KINDS,
}


def _kind_compatible(stated: str, real: "str | None") -> bool:
    """Intent:
        Whether a real parameter of kind `real` can take members of
        a domain whose stated kind is `stated`. An unknown real kind
        is compatible with anything; otherwise the table above, and
        equality for a kind outside it.
    """
    if real in (None, "unknown"):
        return True
    return real in _KIND_COMPATIBLE.get(stated, {stated})


def _stated_kind(bound) -> str:
    """Intent:
        The parameter kind a stated domain type corresponds to: the
        table above for a number set, and for a language domain the
        kind of the language itself (a string language is `"string"`,
        a schema language `"mapping"` or `"object"`), read from the
        resolved language and falling back to `"string"` when it does
        not resolve (validation reports that separately).
    """
    base_type = getattr(bound, "base_type", None)
    if base_type == "L":
        from .domain import LanguageRef
        from .languages import resolve_language
        for piece in getattr(bound, "pieces", ()):
            if isinstance(piece, LanguageRef):
                try:
                    return resolve_language(piece).kind
                except Exception:
                    return "string"
        return "string"
    return _BASE_TYPE_KIND.get(base_type, str(base_type).lower())


def _language_field_bounds(cj_domain: dict) -> dict:
    """Intent:
        `{param: {field: bound}}` for every parameter bound to a
        single schema language, from the one-deep field domains its
        `fields()` states: a numeric field keeps its bound (an
        `Interval`, one side open or both, a named number set, a
        numeric `Domain`), a text field stated as a language keeps that
        `LanguageRef`, and a field with no reading (a categorical,
        None) is present with the bound None. A union of languages or
        a language without fields leaves the parameter out.
    """
    from .domain import LanguageRef
    from .languages import resolve_language
    out: dict = {}
    for p, b in cj_domain.items():
        if getattr(b, "base_type", None) != "L":
            continue
        refs = [piece for piece in b.pieces if isinstance(piece, LanguageRef)]
        if len(refs) != 1 or len(b.pieces) != 1:
            continue
        try:
            fields = resolve_language(refs[0]).fields()
        except Exception:
            continue
        if fields:
            out[p] = dict(fields)
    return out


def _is_numeric_bound(bound) -> bool:
    from .domain import Domain
    if isinstance(bound, Domain):
        return bound.base_type in ("R", "Z", "N")
    return bound in ("Z", "N", "R") or isinstance(bound, tuple)


def _length_domain(bound):
    """Intent:
        The domain of `len(p.field)` for a text field: its language's
        length bound as a whole-number interval, or N.
    """
    from .domain import Domain, Interval, LanguageRef
    length = bound.refinement("len") if isinstance(bound, LanguageRef) else None
    if length is None:
        return "N"
    from .domain import refinement_range
    lo, hi = refinement_range(length)
    return Domain(base_type="N" if hi is None else "Z",
                  pieces=() if hi is None else (Interval(float(lo), float(hi)),),
                  explicit_type=True)


def _path_bound(p: str, path: str, fields: dict, cj_domain: dict):
    """Intent:
        The bound of the field `path` reads off parameter `p`: the
        claim's own binding of that path, or of the same path with every
        index read as `[*]`, else the language's, found by walking its
        `fields()`: a nested mapping for a record, and the elements of
        a list field under `"[*]"`, as a one-item list, as the element
        record stated under the field's own name, or under the field's
        starred name (`lines[*]`). None when neither states one.
    """
    import re as _re
    from .domain import path_steps
    for key in (f"{p}.{path}", _re.sub(r"\[\d+\]", "[*]", f"{p}.{path}")):
        if key in cj_domain:
            return cj_domain[key]
    steps = path_steps(f".{path}")
    node = fields
    i = 0
    while i < len(steps):
        step = steps[i]
        indexed = isinstance(step, int) or step == "*"
        if isinstance(node, list):
            # a list field stated as a one-item list of its element (a
            # tuple is a bound, an interval's two ends)
            if len(node) != 1:
                return None
            node = node[0]
            if indexed:
                i += 1
            continue
        if not isinstance(node, dict):
            return None
        if indexed:
            # the elements of a list field: under `"[*]"`, or the
            # mapping is the element record itself
            node = node.get("[*]", node)
            i += 1
            continue
        if step in node:
            node = node[step]
        elif f"{step}[*]" in node and i + 1 < len(steps) and (
                isinstance(steps[i + 1], int) or steps[i + 1] == "*"):
            # the elements stated under the field's starred name
            node = node[f"{step}[*]"]
            i += 1
        else:
            return None
        i += 1
    return None if isinstance(node, (dict, list)) else node


def _row_lift_domain(fn, facts, cj_domain: dict) -> "tuple[dict | None, str]":
    """Intent:
        `(field_domain, reason)`: the `p.field` and `p.field.len`
        bounds the lift binds for every language-bound parameter, from
        the fields the body reads, or `(None, reason)` naming the first
        parameter or field with no symbolic reading: a parameter whose
        language states no fields, or a field read as a value that is
        not a number (a categorical, text read as text).
    """
    from .domain import LanguageRef
    from .symbolic._base import field_reads
    schema = _language_field_bounds(cj_domain)
    out: dict = {}
    for p, b in cj_domain.items():
        if getattr(b, "base_type", None) != "L":
            continue
        if p not in schema or facts.tree is None:
            return None, (f"{p} is quantified over a language with no "
                          "field reading")
        plain, length_only = field_reads(facts.tree, p)
        if not (plain or length_only):
            return None, (f"derive cannot read the function, which reads "
                          f"no field of {p}, so the claim is decided by "
                          "running the code")
        for f in plain:
            bound = _path_bound(p, f, schema[p], cj_domain)
            if not _is_numeric_bound(bound):
                return None, (f"derive cannot read the function's field "
                              f"{p}.{f}, which is not a number, so the "
                              "claim is decided by running the code")
            out[f"{p}.{f}"] = bound
        for f in length_only:
            bound = _path_bound(p, f, schema[p], cj_domain)
            if not isinstance(bound, LanguageRef):
                return None, (f"the body reads len({p}.{f}), and {p}.{f} "
                              "is not a text field")
            out[f"{p}.{f}.len"] = _length_domain(bound)
    return out, ""


def _ref_resolves(ref, resolve) -> bool:
    try:
        resolve(ref)
    except Exception:
        return False
    return True


def _adaptor_inferred_domains(fn, facts, cj_domain: dict) -> dict:
    """Intent:
        `{param: (language domain, adaptor name, annotation text)}` for
        every parameter no binding names whose annotation a registered
        language adaptor turns into a language. The domain names the
        language by its own name when that resolves, else by the
        annotation's dotted path when the annotation is a class the
        adaptors accept again; an annotation whose language can be
        named neither way infers nothing, since a record must be able
        to resolve what it states.
    """
    if fn is None:
        return {}
    from ._annotation_text import annotation_text
    from .domain import Domain, LanguageRef, language_ref
    from .languages import adapt_annotation, resolve, resolves
    from .types import _hints, _optional_parts
    hints = _hints(fn)
    out: dict = {}
    for p in facts.params:
        hint = hints.get(p)
        if p in cj_domain or hint is None:
            continue
        # the adaptor reads the type without its None; the absence an
        # Optional annotation admits is added to the language domain
        optional, inner = _optional_parts(hint)
        found = adapt_annotation(inner)
        if found is None:
            continue
        language, adaptor = found
        named = language_ref(language.name)
        if named is not None and _ref_resolves(named, resolve):
            ref = named
        elif isinstance(inner, type) and resolves(
                f"{inner.__module__}.{inner.__qualname__}"):
            ref = LanguageRef(f"{inner.__module__}.{inner.__qualname__}")
        else:
            continue
        out[p] = (Domain(base_type="L", pieces=(ref,), explicit_type=True,
                         absent=optional),
                  adaptor, annotation_text(hint))
    return out


def parameter_domain_facts(fn, facts) -> dict:
    """Intent:
        The domain each parameter's own annotation, default or guard
        states, `{param: (bound, category, detail)}`, the one reading
        every route and the clarity score start from. An `int`
        annotation gives the integers (`int`); a `Literal`, an `Enum`
        or a `bool` its stated values (`stated_values`); an unannotated
        parameter defaulting to a bool the two flags (`flag`, the
        default as detail); a guard refusing every value outside a set
        of strings that set, the working domain it leaves (`guard`); a
        registered language adaptor its language (`adaptor`, detail
        `(adaptor name, annotation text)`); a `str` annotation the type
        of strings (`text`, the annotation text as detail). An
        `Optional` annotation adds the absence of the object to a
        language or text domain. A parameter nothing states is left
        out.
    """
    from ._annotation_text import annotation_text
    from .domain import Domain
    from .hazards import finite_guard_sets
    from .types import _hints, missing_policy_from_signature
    if facts is None:
        return {}
    out: dict = {}
    kinds = facts.param_kinds or {}
    for p in facts.params:
        if kinds.get(p) == "int":
            out[p] = ("Z", "int", None)
    for p, vals in (getattr(facts, "finite_domains", {}) or {}).items():
        out.setdefault(p, (frozenset(vals), "stated_values", None))
    try:
        signature = inspect.signature(fn).parameters if fn is not None else {}
    except (TypeError, ValueError):
        signature = {}
    for p in facts.params:
        param = signature.get(p)
        if (param is not None and p not in out
                and param.annotation is inspect.Parameter.empty
                and isinstance(param.default, bool)):
            out[p] = (frozenset({False, True}), "flag", param.default)
    for p, values in finite_guard_sets(facts).items():
        if p not in out:
            out[p] = (values, "guard", None)
    try:
        adapted = _adaptor_inferred_domains(fn, facts, out)
    except Exception:
        adapted = {}
    for p, (bound, adaptor, hint_text) in adapted.items():
        out[p] = (bound, "adaptor", (adaptor, hint_text))
    hints = _hints(fn) if fn is not None else {}
    policy = missing_policy_from_signature(fn) if fn is not None else {}
    for p in facts.params:
        if p in out or kinds.get(p) != "string" or p not in hints:
            continue
        defaults = policy.get(p)
        optional = bool(defaults is not None and defaults.annotated and defaults.absent)
        out[p] = (Domain(base_type="S", explicit_type=True, absent=optional,
                         clause=True),
                  "text", annotation_text(hints[p]))
    return out


def parameter_domains(fn, facts=None) -> dict:
    """Intent:
        `{param: bound}` for every parameter whose annotation, default
        or guard states its domain (`parameter_domain_facts`), each
        completed from the annotation's missing-value defaults
        (`domain.complete`) exactly as a claim's resolved domain is:
        the completed domain the checks use and the clarity score
        reads.
    """
    from .domain import NO_ANNOTATION, complete
    from .types import missing_policy_from_signature
    if facts is None:
        try:
            facts = analyze_source(fn)
        except Exception:
            return {}
    policy = missing_policy_from_signature(fn)
    out: dict = {}
    for p, (bound, _category, _detail) in parameter_domain_facts(fn, facts).items():
        try:
            out[p] = complete(bound, policy.get(p, NO_ANNOTATION))
        except Exception:
            out[p] = bound
    return out


def _language_meta(bounds: dict) -> dict:
    """Intent:
        The record's statement of every language a claim was
        adjudicated over: per parameter, one description per language
        piece (name, source, level, kind, persisted form), so a reader
        of the record sees what `L[ascii]` resolved to. A language that
        does not resolve is left out; validation has already reported
        it.
    """
    from .domain import LanguageRef
    from .languages import describe_language
    out: dict = {}
    for p, b in sorted(bounds.items()):
        if getattr(b, "base_type", None) != "L":
            continue
        described = []
        for piece in b.pieces:
            if isinstance(piece, LanguageRef):
                try:
                    described.append(describe_language(piece))
                except Exception:
                    continue
        if described:
            out[p] = described
    return out

GRAMMAR = "mathema"

# the closeness default: what an equality (or slack on an inequality)
# claim uses when it states no tolerance of its own. A claim narrows or
# widens it per claim (a `tolerance:` field, or an explicit epsilon
# written into the law); the verified record states this default once,
# record-level, so the resolved value is always visible.
DEFAULT_TOLERANCE = 1e-9    # this module's own statement dialect (record-schema.md's
                       # `grammar` field), see mathema.data.grammar.GRAMMAR for
                       # the one other grammar in the codebase today.

def _declared_rel_tol(cj) -> float:
    """Intent:
        The relative allowance an equality gets on the probe route: none
        when the claim declared its tolerance, which is then the whole
        allowance, and the default relative tolerance otherwise.
    """
    from .probing import DEFAULT_RELATIVE_TOLERANCE
    return 0.0 if cj.tolerance is not None else DEFAULT_RELATIVE_TOLERANCE


def _runtime_dim(value, axis=0):
    """`dim(value, axis)` at evaluation time: the size of the axis-th
    dimension of a nested-sequence value, descending first elements;
    `dim(value)` is the first axis. Raises IndexError past the value's
    depth, the same honest failure an over-indexed axis deserves."""
    v = value
    for _ in range(int(axis)):
        v = v[0]
    return len(v)


def _runtime_det(value) -> float:
    """`det(value)` at evaluation time: the determinant of a square
    matrix value (nested lists or an array), through numpy. Raises
    ValueError when numpy is not importable, and numpy's own error for
    a value that is not a square matrix."""
    from .matrices import _numpy
    np = _numpy()
    if np is None:
        raise ValueError("det needs numpy")
    return float(np.linalg.det(np.asarray(value, dtype=float)))


class _NoRealValue(ValueError):
    """A function in the claim's own expression has no real value at the
    argument it was given (`sqrt(-0.5)`, `log(0)`, `gamma(-1)`)."""


def claim_side_has_no_value(exc: BaseException) -> bool:
    """Intent:
        Whether an exception from evaluating the claim's own expression
        (not the function under test) means the claim has no real value
        at that point: one of its functions left its real domain, or it
        divided by zero.
    """
    return isinstance(exc, (_NoRealValue, ZeroDivisionError))


def _real_only(real_fn):
    """A law function whose domain error is raised as `_NoRealValue`."""
    def call(v):
        try:
            return real_fn(v)
        except ValueError as e:
            name = getattr(real_fn, "__name__", "call")
            raise _NoRealValue(f"{name}({v!r}) has no real value") from e
    call.__name__ = getattr(real_fn, "__name__", "call")
    return call


def _linalg_eval_words():
    """The module holding the claim words' exact arithmetic."""
    from . import _linalg_eval
    return _linalg_eval


def _real_or_complex(real_fn, complex_fn, exact_fn=None):
    """A law function that computes a complex argument (a Python or
    numpy complex) with its `cmath` counterpart and anything else with
    its `math` one; a real argument outside the real domain raises
    `_NoRealValue`, and an exact rational beyond float range (the value
    a claim word keeps there) is computed with `exact_fn`, when given."""
    from fractions import Fraction
    real_call = _real_only(real_fn)

    def call(v):
        if isinstance(v, complex):
            return complex_fn(complex(v))
        if exact_fn is not None and isinstance(v, Fraction):
            try:
                return real_call(v)
            except OverflowError:
                return exact_fn(v)
        return real_call(v)
    call.__name__ = getattr(real_fn, "__name__", "call")
    return call


_SAFE_FUNCS = {
    "abs": abs, "min": min, "max": max, "len": len, "sum": sum,
    "dim": _runtime_dim, "det": _runtime_det,
    # output-shape builtins for the output-contract invariants
    # (preserves_type, is_permutation_of_input): probe-only, harmless,
    # not sympy functions (the derive route reports them unsupported and
    # the probe evaluates them).
    "sorted": sorted, "type": type,
    # a value's text, for a round trip through a parser that returns an
    # object: probe-only, the derive route has no reading of it
    "str": str,
    # the call a claim's `@` is compiled to (`_exact_products`)
    "_exact_matmul": lambda a, b: _linalg_eval_words().matmul(a, b),
    "_exact_arith": lambda op, a, b: _linalg_eval_words().arith(op, a, b),
    # sympy's own capitalization, mirroring _math_vocab._SYMPY_FUNCS's
    # Abs/Min/Max synonyms so a claim written that way adjudicates on
    # either route
    "Abs": abs, "Min": min, "Max": max,
    # over C (a complex argument) each elementary function is its
    # principal complex value, as the derive route reads it
    "sqrt": _real_or_complex(math.sqrt, _cmath.sqrt,
                             lambda v: _linalg_eval_words().exact_sqrt(v)),
    "exp": _real_or_complex(math.exp, _cmath.exp),
    "log": _real_or_complex(math.log, _cmath.log,
                            lambda v: _linalg_eval_words().exact_log(v)),
    "log10": _real_or_complex(math.log10, _cmath.log10,
                              lambda v: _linalg_eval_words().exact_log(v, 10)),
    "log2": _real_or_complex(math.log2, lambda z: _cmath.log(z, 2),
                             lambda v: _linalg_eval_words().exact_log(v, 2)),
    "sin": _real_or_complex(math.sin, _cmath.sin),
    "cos": _real_or_complex(math.cos, _cmath.cos),
    "tan": _real_or_complex(math.tan, _cmath.tan),
    "norm": abs,   # see symbolic.py's _SYMPY_FUNCS: same placeholder scope
    "floor": math.floor, "ceil": math.ceil,
    # parity with _math_vocab._SYMPY_FUNCS (the derive route's own
    # vocabulary): every name there with a direct `math` module
    # equivalent, so a claim using one of these can be adjudicated on
    # either route, not proven on derive and silently unrecognized on
    # probe. `factorial` evaluates as gamma(x + 1), the continuous
    # extension the derive route already reasons about (sympy.factorial
    # is gamma-based), so both routes compute the same mathematical
    # object; math.gamma's own pole raises at non-positive integers
    # behave like any other raising sample.
    "factorial": _real_only(lambda v: math.gamma(v + 1)),
    "asin": _real_or_complex(math.asin, _cmath.asin),
    "acos": _real_or_complex(math.acos, _cmath.acos),
    "atan": _real_or_complex(math.atan, _cmath.atan),
    "sinh": _real_or_complex(math.sinh, _cmath.sinh),
    "cosh": _real_or_complex(math.cosh, _cmath.cosh),
    "tanh": _real_or_complex(math.tanh, _cmath.tanh),
    "gamma": _real_only(math.gamma), "lgamma": _real_only(math.lgamma),
    "erf": math.erf, "erfc": math.erfc,
    # complex accessors (the derive route's re/im/conjugate/arg): each
    # accepts a plain real too, so a claim using them adjudicates on
    # either route.
    "re": lambda v: v.real if isinstance(v, complex) else float(v),
    "im": lambda v: v.imag if isinstance(v, complex) else 0.0,
    "conjugate": lambda v: v.conjugate() if isinstance(v, complex) else float(v),
    "arg": lambda v: _cmath.phase(complex(v)),
}
_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name,
                  ast.Constant, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div,
                  ast.Pow, ast.Mod, ast.FloorDiv, ast.USub, ast.UAdd, ast.List, ast.Tuple,
                  ast.Subscript, ast.Index, ast.Slice,
                  # the matrix product, and a keyword argument
                  # (`sum(A, axis=0)`)
                  ast.MatMult, ast.keyword,
                  # truth-valued law expressions (`f(a, b) == (a <= b)`):
                  # comparisons and boolean connectives evaluate to
                  # Python bools, which are ints, so both routes treat
                  # them as the 0/1 quantity they are. Membership and
                  # identity operators stay out: `in` belongs to the
                  # quantifier grammar, `is` proves nothing about values
                  ast.Compare, ast.BoolOp, ast.And, ast.Or, ast.Not,
                  ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
                  # a dict literal, for a dict-returning function's own
                  # output claim (`f(x) == {"a": x}`); the probe
                  # evaluates it and _close compares dicts, the derive
                  # route declines and falls back.
                  ast.Dict)

# _EXC_TYPES (the exception names a raises(...) claim may assert) lives
# in records.py, imported above; consumers that used to find it here
# still can.


def _resolve_exception_type(name: str, fn) -> "type | None":
    """Intent:
        The exception class a `raises(f(x), <name>)` claim names, or
        None when nothing resolves it. Tried in order: the fixed
        `_EXC_TYPES` table, a built-in exception, a dotted path
        (`numpy.linalg.LinAlgError`: the longest importable module
        prefix, then attributes), and a bare name on the target's own
        module or one of its parent packages (`LinAlgError` for a
        `numpy.linalg` function, `StatisticsError` for
        `statistics.mean`).
    """
    import builtins
    import importlib

    def _exception_class(obj) -> bool:
        return isinstance(obj, type) and issubclass(obj, BaseException)

    if name in _EXC_TYPES:
        return _EXC_TYPES[name]
    if _exception_class(getattr(builtins, name, None)):
        return getattr(builtins, name)

    def _walk(module_name: str, attrs: list):
        try:
            obj = importlib.import_module(module_name)
        except Exception:
            return None
        for attr in attrs:
            obj = getattr(obj, attr, None)
            if obj is None:
                return None
        return obj if _exception_class(obj) else None

    parts = name.split(".")
    if len(parts) > 1:
        from ._claim_reach import path_refusal
        if path_refusal(name) is not None:
            return None
        for cut in range(len(parts) - 1, 0, -1):
            found = _walk(".".join(parts[:cut]), parts[cut:])
            if found is not None:
                return found
        return None
    module = getattr(fn, "__module__", None) or ""
    if not module and getattr(fn, "__self__", None) is not None:
        module = type(fn.__self__).__module__
    pieces = module.split(".") if module else []
    for cut in range(len(pieces), 0, -1):
        found = _walk(".".join(pieces[:cut]), [name])
        if found is not None:
            return found
    return None


@dataclass
class Conjecture:
    """One parsed claim, ready to be adjudicated: a relation between
    `lhs` and `rhs` over the function under test (`f`), the evidence
    route it's checked on, and everything a proof/probe attempt needs
    (declared domain, tolerance, prior counterexamples to replay, extra
    functions a multi-function law refers to). Built by `claim()`, which
    parses a claim's law text into these fields."""
    name: str
    lhs: str
    rhs: str
    relation: str = "=="        # "==" | "<=" | ">=" | ... | "in" | "not in"
    rhs_bound: object = None    # the domain a membership relation's rhs names, else None
    source: str = "user"
    route: str = "best"         # "best" (default cascade) | "probe" | "derive" | "examine" (see claim-driven-
                                 # development/0.1.0/claim-anatomy.md). "best" is
                                 # input-only: the cascade derive -> derive:extensive
                                 # -> probe, with the output record naming whichever
                                 # mechanism actually settled it ("auto" is retired,
                                 # an unknown route now, skipped loudly).
                                 # "derive:math_only" adjudicates as "derive" and
                                 # spawns no `[float]` companion.
    grammar: str = GRAMMAR      # statement dialect (record-schema.md's `grammar` field).
                                 # this module implements exactly one: the
                                 # `f`-and-parameter-names law language it and
                                 # symbolic.py parse. A claim declared under a
                                 # different one (mathema.data's, say) is
                                 # recognized and excluded by check_conjectures,
                                 # not misadjudicated as this one.
    funcs: dict = field(default_factory=dict)
    # extra function letters the law may apply, mapped to their callables:
    # {"g": other_fn} lets a law relate two implementations, f(x) == g(x).
    # `f` is always implicitly bound to the function under adjudication.
    # In a record this map is carried as meta["mathema.funcs"] (spec keys,
    # not callables), since the declared-claim field set is fixed.
    domain: dict = field(default_factory=dict)
    # per-parameter bounds this claim is asserted over (declared-schema.md's
    # `domain` field), usually lifted from an inline quantifier by claim().
    free_vars: frozenset = field(default_factory=frozenset)
    # domain keys with no real parameter to match; a claim-text `let
    # name in bounds` binding (grammar.extract_let_bindings), e.g. a
    # gauge-invariance claim's arbitrary shift constant. check_conjectures()
    # exempts these from its real-parameter-only domain-key check, but a
    # free variable's own declared bound is otherwise inert on the derive
    # route: only real parameters reach _domain_assumptions/the corner-
    # evaluation sign machinery, so this only helps a claim whose truth
    # doesn't depend on the free variable's exact range (unlike `let`'s
    # alias form, which substitutes an existing real parameter's own
    # already-bounded symbol and so has no such gap).
    # Empty means asserted without restriction.
    ambiguous_diff_vars: frozenset = field(default_factory=frozenset)
    # literal denominator names (grammar.extract_diff_fraction_sugar's
    # `d(<expr>/d<var>)` fraction sugar guessed at differentiation,
    # `dh`, not the stripped `h`. check_conjectures() checks these
    # against fn's own real parameter names once known: a real
    # collision (the literal name IS a parameter, e.g. a
    # gibbs_free_energy(dh, t, ds)-shaped function) means the guess was
    # never safe to make, and the claim is skipped:misspecified rather
    # than silently guessing wrong. Empty means the claim's `d(...)`
    # calls (if any) never used the fraction spelling at all.
    pins: list = field(default_factory=list)
    param_pins: dict = field(default_factory=dict)
    # `let <parameter> be None|True|False` bindings (grammar.
    # ParameterPin): the value each named parameter is passed at on
    # every call the claim makes. A number spelled the same way is a
    # single-point `let` bound in `domain`/`free_vars`, which reads as a
    # pin too when the name is a real parameter of a library function.
    meta: dict = field(default_factory=dict)   # declared extension data
                                 # (the spec's own meta object, e.g.
                                 # {"concepts": [...]}), carried onto
                                 # the claim's probe unchanged, per the
                                 # spec's pass-through rule
    # counterexamples already on record, replayed before any sampling so a
    # past falsification stays caught forever (cdd.md step 6: re-verification
    # is also a regression check). Each pin: {"args": [...], "aux": {...}}
    # with exact values, not display strings.
    tolerance: float | None = None
    # how close counts as equal (declared-schema.md's `tolerance` field;
    # no spec-level default). Also what `ε`/`eps`/`epsilon` resolves to
    # inside a law's own text (grammar.py/symbolic.py), so
    # `abs(f(x) - g(x)) <= ε` reads exactly like the mathematical
    # convention it's borrowed from.
    negated: bool = False
    # a domain-safety predicate claim stated in its grammar not-form
    # (`not is_pole_safe(x)`): the relation stays the positive
    # predicate every dispatch site matches on, and adjudication
    # inverts the family's decision, the evidence that falsifies the
    # positive claim is exactly what proves the negation.
    assuming: str = ""
    # raw text of a claim's own `assuming <...>,` prefix (grammar.
    # extract_assuming_clause), keyword included; empty string means
    # the claim had no such section. Held verbatim here and interpreted
    # at adjudication time by `_interpret_assumption`, which needs the
    # sibling claims and the function's facts: a relation (or `and`-
    # joined conjunction) constrains the region both routes work over,
    # `is_defined(f)`/`f is defined` resolves to the function's own
    # definedness region and is pinned into the statement, a bare
    # sibling name borrows that claim's relation, and `<name> holds` /
    # `<name> is proven` consults the referenced claim's verdict and
    # caps this claim's own.
    outcome: str = ""
    # raw text of a claim's own trailing `=> <...>` suffix (grammar.
    # extract_outcome_clause), captured verbatim. Unlike `assuming`,
    # nothing reads this yet, the parser round-trips it and no
    # adjudication consults it. Empty string means no such section.
    pseudo_infinity: float | None = None
    # the authored `let |inf| be v`, the claim level of the operational
    # infinity (P6): how far the computation (the probe route and the
    # float companion) runs along an unbounded direction, applied
    # symmetrically (records.pseudo_infinity_range). The derive route
    # never reads it (P1). Part of the claim's text, and so of its
    # identity, only where it bounds an unbounded direction (P8).
    resolved_pseudo_infinity: "PseudoInfinity | None" = field(
        default=None, compare=False)
    # the operational infinity that applies after resolution, claim >
    # function > MATHEMA_PSEUDO_INFINITY (records.resolve_pseudo_infinity),
    # with its source; set only on check_conjectures' working copy and
    # read through records.operational_range. Output, never identity
    # (P7): no renderer or fingerprint reads it.
    overflow_safe: tuple = field(default=(), compare=False)
    # the `(lhs, relation, rhs)` links of the function's own recorded
    # `is_overflow_safe` region, from the claims adjudicated beside
    # this one; set only on check_conjectures' working copy, read by
    # the `is_defined` probe to keep its points inside that region
    links: list = field(default_factory=list)
    # a chained comparison's pairwise links, each an (lhs, rel, rhs)
    # triple (grammar.split_relation_chain); empty for an ordinary
    # single-relation claim. When present, the claim is the CONJUNCTION
    # of its links; proven iff every link is, falsified if any link
    # is, and lhs/rel/rhs hold the first link so every single-link
    # consumer keeps working unchanged.
    raw: str = ""
    # the claim's original law text, before parsing (provenance, and the
    # source `check_conjectures` re-resolves the matrix sugar from when
    # the function's signature reveals a matrix the claim text alone did
    # not). Empty for a Conjecture built directly rather than via claim().
    scope_bound: frozenset = field(default_factory=frozenset)
    # the call names that are the function under test itself
    # (`midpoint(a, b)` for f = midpoint): no `let` renders for them
    under_test: frozenset = field(default_factory=frozenset)
    # the `funcs` names check_conjectures resolved from f's module or the
    # calling scope rather than from an explicit `funcs=`/`let` binding.
    # Their text stays the bare call name, which resolves the same way
    # when the claim is rebuilt, so rendering adds no `let` for them.
    trials: "int | None" = None
    # the claim's own trial budget (`claim(..., trials=)`, a claims
    # file's `trials:`), which may exceed the usual limit; None uses the
    # caller's. A finite domain whose point count is within it is swept
    # in full on the computation line.


class InvalidConjecture(ValueError):
    """Raised by `claim()` when a law's text doesn't parse into a valid
    `Conjecture` (bad syntax, an unrecognized relation, ...)."""


class ConflictingDomainBinding(InvalidConjecture):
    """Raised by `claim()` when the same name is given a domain both by
    a leading `let name be bounds` and an ordinary `for name in bounds`
    in the same law, two different declared bounds for one name, with
    no principled way to silently prefer one over the other. Distinct
    from a `let name be bounds` name that merely turns out, once a
    specific function is checked, to already be a real parameter with
    no separate `for` of its own in this claim; that case has only one
    declared bound to begin with, so `check_conjectures()` accepts it
    (and says so in the resulting note) rather than raising."""


def claim(law: str, name: str | None = None, source: str = "user",
         route: str = "best", grammar: str = GRAMMAR,
         funcs: dict | None = None, tolerance: float | None = None,
         pseudo_infinity: float | None = None,
         meta: dict | None = None,
         matrix_names: frozenset = frozenset(),
         trials: "int | None" = None) -> Conjecture:
    """The simple way to state a claim: one string, relation included.

        claim("f(-x) = -f(x)")
        claim("f(x)^2 ≥ 0")
        claim("min(x) <= f(x, alpha)", name="lower_bound")
        claim("f(x) == g(x) / log(2)", funcs={"g": nats_version})
        claim("raises(f(x), ValueError)")
        claim("let m = m1, for m1 in [0.1,1000], x1 in [-100,100], x2 in [-100,100],"
              " f(m,x1,m,x2) == (x1+x2)/2")
        claim("let g = pkg.mod.func1, for x in (0,100], g(x) >= 0")
        claim("let c be [-1e6,1e6], for dh in [-1e6,1e6], t in [0,1000], ds in [-1e6,1e6],"
              " d(f(dh+c,t,ds), t) == d(f(dh,t,ds), t)")

    Spellings are normalized by grammar.py (^ is power, = reads as ==,
    Unicode ≤ ≥ − · × π accepted), so equivalent spellings are the same
    statement. Accepted relations: ==, <=, >=, plus the raises(...)
    predicate and the family-derive-only `is_pole_safe(param)`/`is_number_set_safe(param)`
    predicates (no `f(...)` wrapper; these are facts about param's own
    declared domain, not fn's return value). `route` defaults to "best",
    which cascades: the fast proof attempt, then the extensive strategy
    ladder, then probing, and the output record names whichever route
    actually settled it. "derive" makes the fast proof attempt only; a
    claim it cannot decide still falls through to probing, with the
    derive attempt's status kept in `meta["mathema.derive_status"]`.
    "probe" samples only (seeded, verdict `holds`/`falsified`) ("auto" is retired, not a
    legacy spelling of "best"). A derive proof is the mathematics in
    exact arithmetic; `mathema.check` pairs it with a `<name>[float]`
    companion claim about the computation, and "derive:math_only"
    asks for the proof alone, with no companion. the safety predicates always adjudicate on the examine route
    regardless of the route passed in. A
    leading `let name = expr, ...` (see grammar.extract_let_bindings)
    substitutes each name for `(expr)` everywhere later in the law,
    e.g. binding one fresh name to two real parameters, forcing them
    equal, or, when `expr` is a bare dotted path, binds a callable
    letter (like `g` above) the same way an explicit `funcs=` entry
    would, without needing one; `let name be bounds` instead declares a
    genuinely free variable (no real parameter to alias, e.g. a gauge-
    invariance claim's arbitrary shift constant), `be`, not `in`, so
    it never reads like a `for` binding, exempted from the usual
    real-parameter-only domain-key check. If `name` also turns out to be
    a real parameter of whichever function is checked, with no separate
    `for name in ...` of its own in this same claim, that's harmless
    (there's still only one declared bound) and adjudicates like an
    ordinary `for`, noted in the result rather than treated as an error;
    declaring the *same* name via both `let ... be ...` and
    `for ... in ...` in one claim, though, raises `ConflictingDomainBinding`
    immediately; two different bounds for one name has no principled
    default to pick silently. `trials` is the claim's own trial
    budget, a positive whole number, which may exceed the usual limit."""
    if trials is not None:
        if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
            raise InvalidConjecture(
                f"trials must be a positive whole number, got {trials!r}")
        made = claim(law, name, source, route, grammar, funcs, tolerance,
                     pseudo_infinity, meta, matrix_names)
        return _dc_replace(made, trials=trials)
    first = _claim(law, name, source, route, grammar, funcs, tolerance,
                   pseudo_infinity, meta, matrix_names)
    if "|" not in blank_strings(law):
        return first
    # bars around a matrix are its determinant: once the claim's own
    # domain has said which names are matrices, the text is read again
    # with that known, keeping the first reading's name
    mats = frozenset(matrix_names) | linalg.declared_matrix_names(first.domain)
    if not mats:
        return first
    from .grammar import bars_over_matrices
    with bars_over_matrices(mats):
        return _claim(law, name if name is not None else first.name, source,
                      route, grammar, funcs, tolerance, pseudo_infinity,
                      meta, matrix_names)


def _claim(law: str, name: str | None, source: str, route: str,
           grammar: str, funcs: dict | None, tolerance: float | None,
           pseudo_infinity: float | None, meta: dict | None,
           matrix_names: frozenset) -> Conjecture:
    """Intent:
        `claim`'s parse of one law text, under whatever bar reading
        `grammar.bars_over_matrices` has set.
    """
    # "auto" is fully retired (the word stays free for automatic
    # differentiation): it is NOT a legacy alias, an "auto" route
    # reaches adjudication as an unknown route and skips loudly.
    # A safety predicate is a computation fact: whatever route the
    # author passed, it is examined through the full structural +
    # empirical cascade, and the record reports which mechanism
    # decided (the examine route). That normalization happens after
    # parsing, once the relation is known, see below.
    if "#" in blank_strings(law):
        raise InvalidConjecture(
            f"`#` has no meaning in a claim and would silently cut off "
            f"everything after it; remove it (a comment belongs outside "
            f"the claim text): {law.strip()!r}")
    if ":=" in blank_strings(law).replace("=:=", "   ").replace("≡", " "):
        raise InvalidConjecture(
            f"`:=` states a definition, which a claim never holds: a "
            f"runtime's missing values are stated under its key's "
            f"`defines:` (`missing := {{null, nan}}`), and a binding "
            f"states its type after a colon, `x in [0, 1] : float`: "
            f"{law.strip()!r}")
    from .policy import parse_policy, policy_text
    stated_policy = parse_policy(law)
    if stated_policy is not None:
        # a policy claim: what f does with a value that is not there
        text = policy_text(stated_policy)
        body = policy_text(stated_policy, premise=False)
        selector, _, word = body.partition(") ")
        return Conjecture(
            name=name or re.sub(r"\W+", "_", text).strip("_"),
            lhs=selector + ")" if word else body, rhs=word, relation="policy",
            source=source,
            route="probe" if route == "best" else route, grammar=grammar,
            meta=dict(meta or {}),
            assuming=(f"assuming {stated_policy.premise}" if stated_policy.premise
                      else ""),
            raw=text)
    absent_gate = re.match(r"^\s*is_absent_safe\s*\(\s*([A-Za-z_]\w*)\s*\)\s*$", law)
    if absent_gate:
        # the absence gate reads as the missing one does, over the other kind
        target = absent_gate.group(1)
        return Conjecture(
            name=name or f"is_absent_safe[{target}]", lhs=target, rhs="",
            relation="is_absent_safe", source=source,
            route="examine" if route == "best" else route, grammar=grammar,
            meta=dict(meta or {}), raw=law)
    try:
        text, ambiguous_diff_vars = extract_diff_fraction_sugar(law.strip())
    except UnreadableSpelling as e:
        said = str(e)
        if law.strip() not in said:
            said = f"{said}, in the claim {law.strip()!r}"
        raise InvalidConjecture(said) from e
    # outcome section: stripped first, on raw text, extract_outcome_
    # clause recognizes any accepted "implies" spelling directly rather
    # than relying on normalize() to have unified them, so it never has
    # to wait its turn in the retry loop below. Stub only: captured
    # verbatim, no semantics read it yet.
    outcome, text = extract_outcome_clause(text)
    # let/for/assuming section order: extract_let_bindings and
    # extract_assuming_clause only ever fire on text literally starting
    # with "let"/"assuming" (never misreading a bare trailing "name =
    # expr" statement as a let-continuation, since that shape is only
    # ever a continuation of an *already-found* let run), and
    # split_quantifier only fires on text literally starting with "for",
    # so retrying all three, each on whatever's left after the
    # others last ran, correctly finds any relative ordering of them
    # (`for ..., let ..., statement`, `assuming ..., for ..., let ...,
    # statement`, ...) exactly as readily as today's fixed `let ...,
    # for ..., statement` one, with no change to any of their own entry
    # conditions or internal logic. Loop terminates by construction:
    # each iteration either makes progress (text changes) or breaks
    # immediately.
    let_funcs: dict = {}
    let_domain: dict = {}
    dom: dict = {}
    aliases: dict = {}
    assuming = ""
    let_pseudo_inf: float | None = None
    while True:
        prev = text
        try:
            new_assuming, text = extract_assuming_clause(text)
        except UnreadableSpelling as e:
            said = str(e)
            if law.strip() not in said:
                said = f"{said}, in the claim {law.strip()!r}"
            raise InvalidConjecture(said) from e
        if new_assuming is not None:
            if not new_assuming.strip()[len("assuming"):].strip():
                raise InvalidConjecture(
                    f"`assuming` has no premise before its comma: state "
                    f"one (`assuming x > 0, ...`) or drop the keyword: "
                    f"{law.strip()!r}")
            assuming = (_conjoin_assuming(assuming, new_assuming, law)
                        if assuming else new_assuming)
        try:
            (new_funcs, new_free_domain, text, new_aliases,
             new_pseudo_inf) = extract_let_bindings(text)
        except InvalidDomain as e:
            raise InvalidConjecture(str(e)) from e
        let_funcs.update(new_funcs)
        let_domain.update(new_free_domain)
        aliases.update(new_aliases)
        if new_pseudo_inf is not None:
            if (let_pseudo_inf is not None
                    and let_pseudo_inf != new_pseudo_inf):
                raise InvalidConjecture(
                    "the operational infinity is bound twice with "
                    "different ranges")
            let_pseudo_inf = new_pseudo_inf
        try:
            text = normalize(text)
        except UnreadableSpelling as e:
            said = str(e)
            if law.strip() not in said:
                said = f"{said}, in the claim {law.strip()!r}"
            raise InvalidConjecture(said) from e
        try:
            new_dom, text = split_quantifier(text)
        except DuplicateBinding as e:
            raise ConflictingDomainBinding(str(e)) from e
        except InvalidDomain as e:
            raise InvalidConjecture(str(e)) from e
        rebound = sorted(set(new_dom) & set(dom) - {"n"})
        if rebound:
            raise ConflictingDomainBinding(
                f"{rebound} bound by two quantifiers in the same claim; "
                f"give each name one domain")
        dom.update(new_dom)
        if text == prev:
            break
    double_bound = sorted(set(let_domain) & set(dom))
    if double_bound:
        raise ConflictingDomainBinding(
            f"{double_bound} declared with both 'let ... be ...' and "
            f"'for ... in ...' in the same claim, pick one")
    # a `for` clause processed in an earlier retry-loop iteration, before
    # this claim's `let <alias> = <real name>` was even found, can commit
    # a domain key literally spelled the same as that alias
    # (`for m in [...], let m = m1, ...`), silently binding the
    # declared domain to the alias, not the real parameter it resolves
    # to, since the domain key is already committed by the time the
    # alias is known. Only reachable now that `for` can precede
    # `let`, caught here
    # rather than left to silently produce a domain key that can never
    # match a real parameter.
    aliased_domain_keys = sorted(set(aliases) & set(dom))
    if aliased_domain_keys:
        raise ConflictingDomainBinding(
            f"{aliased_domain_keys} used as a 'for ... in ...' binding name "
            f"before its own 'let {aliased_domain_keys[0]} = "
            f"{aliases[aliased_domain_keys[0]]}' alias was resolved, "
            f"write the real name ({aliases[aliased_domain_keys[0]]!r}) in "
            f"the 'for' clause instead, or move the 'let' earlier")
    from .grammar import ParameterPin
    param_pins = {k: v.value for k, v in let_domain.items()
                  if isinstance(v, ParameterPin)}
    let_domain = {k: v for k, v in let_domain.items() if k not in param_pins}
    dom = {**let_domain, **dom}
    prime_problem = unexpanded_prime_message(text)
    if prime_problem is not None:
        raise InvalidConjecture(prime_problem)
    r = parse_raises(text)
    ds = None if r is not None else parse_domain_safety(text)
    negated = False
    links: list = []
    rhs_bound = None
    if r is not None:
        lhs, exc = r
        rel, rhs = "raises", (exc or "")
    elif ds is not None:
        rel, lhs, rhs = ds[0], ds[1], ""
        if rel.startswith("not "):
            rel, negated = rel[4:], True
    else:
        section = _MISCASED_SECTION.match(text)
        if section is not None:
            raise InvalidConjecture(
                f"section keywords are lowercase: write "
                f"`{section.group(1).lower()}`, not `{section.group(1)}`, "
                f"in {law.strip()!r}")
        # a residual top-level comma is a comma-joined relation pair
        # (`f >= 1, f <= 4`), ambiguous with the section-separator comma
        # (and parsing as a bare tuple, which no relation split would
        # flag), refuse with the actionable spelling up front
        if len(_split_commas(text)) > 1:
            raise InvalidConjecture(
                "a claim carries one relation: state each as its own "
                "claim, or use a chained comparison (a <= b <= c)")
        # a top-level implication arrow that survived to here is not
        # outcome grammar (that shape is `=> self.<claim>`, stripped
        # off raw text up front) and not an assuming pin (those live in
        # the assuming section, already extracted), left in place it
        # would silently become part of one side's expression text, a
        # different claim than the author wrote
        if _split_top_level(text, ("=>",)) is not None:
            raise InvalidConjecture(
                "'=>' reads as an outcome clause and takes a claim "
                "reference (`=> self.<claim_name>`); to make one "
                "relation conditional on another, state the premise "
                "as `assuming <relation>, <statement>`")
        membership = split_membership(text)
        if membership is not None:
            lhs, rel, rhs = membership
            rhs_bound = _membership_bound(rhs)
            chain = _membership_as_chain(lhs, rel, rhs_bound)
            if chain is not None:
                # `f(x) in [0, 1]` is the chain `0 <= f(x) <= 1`, which
                # every route already reads; the membership spelling
                # is sugar for it, and the chain is the canonical text
                text, membership, rhs_bound = chain, None, None
        if membership is None:
            try:
                links = split_relation_chain(text)
            except NoRelation as e:
                planned = families.planned_family_note(text)
                raise InvalidConjecture(
                    str(e) if planned is None else f"{e}; {planned}"
                ) from e
            lhs, rel, rhs = links[0]
            if len(links) == 1:
                links = []
    # a residual `|` is a bar the grammar could not pair with another,
    # and left in place it reaches rendering as unparseable text
    for _side in ((lhs,) if rhs_bound is not None else (lhs, rhs)):
        if _side and "|" in blank_strings(_side):
            raise InvalidConjecture(
                f"the bars in {_side!r} do not pair up. Each opening bar "
                f"needs a closing one; abs(...), norm(...) and det(...) "
                f"are the call spellings of the same quantities.")
    # type-aware matrix sugar: `A^T` -> `A.T`, `|A|` -> `det(A)`,
    # `A^-1` -> `inv(A)`, but only for names known to be matrices, from
    # this claim's own domain or supplied by a caller holding the
    # function's signature. A scalar operand keeps power / abs /
    # reciprocal, so the reading is decided by the type, never guessed.
    mat_names = frozenset(matrix_names) | linalg.declared_matrix_names(dom)
    if mat_names:
        lhs = linalg.apply_matrix_sugar(lhs, mat_names)
        if rhs:
            rhs = linalg.apply_matrix_sugar(rhs, mat_names)
    # every side of a relation is an expression: text left over from a
    # malformed relation (`1 +`, `(`, the `= 1` that `===` splits into)
    # is refused here with the claim named, not left to surface as a
    # SyntaxError wherever the side is next parsed
    if r is None and ds is None:
        for _lhs, _rel, _rhs in (links or [(lhs, rel, rhs)]):
            for _side in ((_lhs,) if rhs_bound is not None else (_lhs, _rhs)):
                try:
                    ast.parse(_side, mode="eval")
                except SyntaxError:
                    command = _LATEX_COMMAND.search(blank_strings(_side))
                    if command is not None:
                        raise InvalidConjecture(
                            f"the LaTeX command `{command.group(0)}` has no "
                            f"meaning in the claim grammar (in the claim "
                            f"{law.strip()!r})") from None
                    raise InvalidConjecture(
                        f"cannot read {_side.strip()!r} as an expression "
                        f"in the claim {law.strip()!r}") from None
                problem = _unreadable_side(_side)
                if problem is not None:
                    where = ("" if _D_AT_SENTINEL in _side
                             else f"in {_side.strip()!r}, ")
                    raise InvalidConjecture(
                        f"{problem} ({where}claim {law.strip()!r})")
    # the record's grammar names the linear-algebra dialect when the
    # claim uses the matrix vocabulary: informative only (a reader sees
    # the parsing was matrix-aware), never required to round-trip, the
    # canonical statement re-parses under base `mathema` on its own.
    if grammar == GRAMMAR and linalg.mentions_matrix_ops(lhs, rhs):
        grammar = f"{GRAMMAR}/linalg"
    elif grammar == GRAMMAR and any(getattr(b, "base_type", None) == "L"
                                    for b in (*dom.values(), rhs_bound)):
        # the language dialect: a claim that writes a language, as a
        # domain or on the right of `in`, is read with the language
        # vocabulary; a finite-set domain stays
        # the base grammar, and the matrix dialect wins when both apply
        grammar = f"{GRAMMAR}/language"
    if let_pseudo_inf is not None:
        from .records import pseudo_infinity_range
        if (pseudo_infinity is not None
                and pseudo_infinity_range(pseudo_infinity)
                != pseudo_infinity_range(let_pseudo_inf)):
            raise InvalidConjecture(
                "pseudo_infinity stated twice: the let binding and the "
                "keyword argument disagree")
        pseudo_infinity = let_pseudo_inf
    accepted_spelling = None
    if rel in families.RETIRED_FAMILY_NAMES:
        accepted_spelling, rel = rel, families.current_family_name(rel)
    if name is not None and families.current_claim_name(name) != name:
        accepted_spelling = accepted_spelling or families.claim_base_name(name)
        name = families.current_claim_name(name)
    if accepted_spelling is not None:
        meta = {**(meta or {}), "mathema.accepted_spelling": accepted_spelling}
    if rel in routes.examine_predicates():
        # the examine normalization promised above: computation
        # facts always run the full cascade; a declared derive/probe/
        # best on a safety predicate is advisory and folds here
        route = "examine"
    if name is None and rel in routes.examine_predicates():
        # a bare predicate claim gets the canonical bracketed name the
        # rest of the system keys on (`is_pole_safe[x]`), the name a
        # suggestion would have carried, so family dispatch and the
        # call-form rebuilders read hand-written and suggested claims
        # identically; a negated predicate is a different claim and
        # gets its own name, never the positive row's
        name = f"{'not_' if negated else ''}{rel}[{lhs}]"
    if name is None:
        name = auto_claim_name(text)
    bound_funcs = {**let_funcs, **(funcs or {})}
    from ._claim_reach import path_refusal
    for bound_name, ref in bound_funcs.items():
        refused = path_refusal(ref) if isinstance(ref, str) else None
        if refused is not None:
            raise InvalidConjecture(
                f"{bound_name} = {ref}: {refused}, in the claim "
                f"{law.strip()!r}")
    for unbound in _unbound_call_names(lhs, rhs, set(bound_funcs)):
        # a bare call name (`budget_line(...)`) is a function reference
        # awaiting scope resolution at check time; recording it now;
        # the name as its own placeholder value; lets the renderer
        # treat it as the function it is rather than refusing
        bound_funcs[unbound] = unbound
    return Conjecture(name=name, lhs=lhs, rhs=rhs, relation=rel,
                      rhs_bound=rhs_bound,
                      source=source, route=route, grammar=grammar,
                      funcs=bound_funcs, domain=dom,
                      free_vars=frozenset(let_domain),
                      ambiguous_diff_vars=ambiguous_diff_vars, tolerance=tolerance,
                      negated=negated, assuming=assuming, outcome=outcome or "",
                      links=links, pseudo_infinity=pseudo_infinity,
                      param_pins=param_pins,
                      meta=dict(meta or {}), raw=law)


def _membership_bound(rhs: str):
    """Intent:
        The domain a membership relation's right-hand side names
        (`L[slug]`, `[0, 1]`, `{"a", "b"}`, `Z`), read by the domain
        grammar, or None when the text is not a domain and the
        relation is value containment (`"<" not in f(s)`).
    """
    from .domain import InvalidDomain, parse_binding
    try:
        parsed = parse_binding(f"_ in {rhs}")
    except InvalidDomain:
        return None
    return None if parsed is None else parsed[1]


def _membership_member(value, bound, sizes: "dict | None" = None) -> bool:
    """Intent:
        Whether `value` is a member of a membership relation's
        right-hand side: a domain that states nothing about missing
        values admits none (`f(x) in [0, 1]` is false at a NaN), and one
        that lists a sentinel admits what it lists, resolved against the
        value tested (`nan in {missing}` on a float, and a `None` that
        f returns where its containers are realised in a runtime whose
        holes include null). A space (`R^(m,n)`)
        judges a container by its shape, a named axis at the size
        `sizes` binds to the name, then every entry the same way.
    """
    from . import _shapes
    from .domain import MissingDefaults, complete, domain_contains
    nothing = MissingDefaults(False, (), "value", annotated=False)
    if value is None and _NULL_IS_A_HOLE.get() \
            and not getattr(bound, "dims", ()):
        # the null hole of the runtime f's containers are realised in
        return domain_contains(value, complete(bound, nothing), slot=True)
    return _shapes.in_space(value, complete(bound, nothing), sizes)


def _membership_as_chain(lhs: str, rel: str, bound) -> "str | None":
    """Intent:
        The chained comparison a membership in a plain numeric
        interval reduces to (`f(x) in [0, 1]` -> `0 <= f(x) <= 1`,
        open endpoints strict), or None for any other right-hand
        side, including `not in`, which has no chain form.
    """
    from .domain import Interval
    if rel != "in" or not isinstance(bound, Interval):
        return None
    lo, hi = bound
    if not all(isinstance(v, (int, float)) for v in (lo, hi)):
        return None
    left = "<=" if getattr(bound, "closed_lo", True) else "<"
    right = "<=" if getattr(bound, "closed_hi", True) else "<"
    return f"{_num(lo)} {left} {lhs} {right} {_num(hi)}"


def _num(v) -> str:
    return str(int(v)) if float(v).is_integer() else repr(float(v))


_NOT_CLAIM_SYNTAX = {
    ast.Lambda: "a lambda",
    ast.IfExp: "a conditional expression (`a if c else b`)",
    ast.Yield: "`yield`",
    ast.YieldFrom: "`yield`",
    ast.Await: "`await`",
    ast.NamedExpr: "an assignment expression (`:=`)",
    ast.JoinedStr: "an f-string",
    ast.Starred: "argument unpacking (`*`)",
    ast.Set: "a set literal",
}
_BITWISE_OPS = (ast.LShift, ast.RShift, ast.BitAnd, ast.BitOr, ast.BitXor)


_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")
_MISCASED_SECTION = re.compile(
    r"^\s*((?!for\b|let\b|assuming\b)(?i:for|let|assuming))\s")

_SPECIAL_CALL_SHAPES = {
    "d": "d(expr, var, ...) or d(expr, var, order)",
    "integrate": "integrate(expr, var) or integrate(expr, var, lo, hi)",
    "lim": "lim(expr, var, point)",
    "Sum": "Sum(expr, var, lo, hi)",
    "Prod": "Prod(expr, var, lo, hi)",
}


def _is_variable(node) -> bool:
    return isinstance(node, ast.Name) and node.id != _D_AT_SENTINEL


def _special_call_problem(node: ast.Call) -> str | None:
    """Intent:
        Why one call of a reserved form (`d`, `integrate`, `lim`, `Sum`,
        `Prod`) does not have that form's shape, or None when it does.
        Every variable slot must hold a plain name, and a derivative
        order must be a non-negative integer.
    """
    name, args = node.func.id, node.args
    shape = f"`{name}` is written {_SPECIAL_CALL_SHAPES[name]}"
    if name == "d":
        at = next((k for k, a in enumerate(args)
                   if isinstance(a, ast.Name) and a.id == _D_AT_SENTINEL),
                  len(args))
        diff = args[1:at]
        if not args or not diff or not _is_variable(diff[0]):
            return f"{shape}: each variable a plain name"
        for a in diff[1:]:
            if _is_variable(a):
                continue
            if not (isinstance(a, ast.Constant) and type(a.value) is int
                    and a.value >= 0):
                return (f"{shape}: each variable a plain name and an "
                        f"order a non-negative integer")
        pairs = args[at + 1:]
        if at < len(args):
            if not pairs or len(pairs) % 2:
                return "`d(...) @ {...}` needs one `name = value` per point"
            names = [p.id for p in pairs[::2] if _is_variable(p)]
            if len(names) != len(pairs) // 2:
                return "`d(...) @ {...}` assigns values to plain names only"
            if len(set(names)) != len(names):
                return (f"`d(...) @ {{...}}` gives "
                        f"{sorted({n for n in names if names.count(n) > 1})} "
                        f"two values")
        return None
    if name == "integrate":
        ok = ((len(args) == 2 and _is_variable(args[1]))
              or (len(args) >= 4 and (len(args) - 1) % 3 == 0
                  and all(_is_variable(a) for a in args[1::3])))
        return None if ok else f"{shape}, the variable a plain name"
    if name == "lim":
        ok = (len(args) in (3, 4) and _is_variable(args[1])
              and (len(args) == 3 or (isinstance(args[3], ast.Constant)
                                      and args[3].value in ("+", "-"))))
        return None if ok else f"{shape}, the variable a plain name"
    ok = len(args) == 4 and _is_variable(args[1])
    return None if ok else f"{shape}, the variable a plain name"


def _is_grammar_function(name: str) -> bool:
    """Whether `name` is one of the claim grammar's own functions (a
    reserved call form, a probe-route builtin, or a linalg reduction)
    rather than a function the claim names."""
    return (is_reserved(name) or name in _SAFE_FUNCS
            or name in linalg.CALL_KEYWORDS)


def _is_keyword_value(node: ast.AST) -> bool:
    """Whether `node` can be a keyword argument's value in a claim: a
    literal (a negative number included) or a bare name."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return isinstance(node, (ast.Constant, ast.Name))


def _unreadable_side(side: str) -> str | None:
    """Intent:
        Why one side of a relation is not claim syntax, or None when it
        is. The side is Python expression text that already parses.

    Notes:
        An unparenthesised `and`/`or`/`not` heading a side means the
        author joined two relations: Python precedence would read
        `f(x) >= 1 and f(x) <= 2` as `f(x) >= (1 and f(x) <= 2)`, a
        different and usually vacuous claim. A parenthesised boolean
        (`f(a, b) == (a <= b)`) is a truth value and stays readable.
        Keyword arguments, bitwise operators and the other refused
        constructs have no reading in the claim grammar; accepting them
        would drop or reinterpret part of what the author wrote.
    """
    tree = ast.parse(side.strip(), mode="eval").body
    top_boolean = (isinstance(tree, ast.BoolOp)
                   or (isinstance(tree, ast.UnaryOp)
                       and isinstance(tree.op, ast.Not)))
    if top_boolean and tree.col_offset == 0:
        return ("`and`, `or` and `not` cannot join relations inside one "
                "claim: state each relation as its own claim, or write a "
                "bounded quantity as a chained comparison (`1 <= f(x) <= 2`); "
                "a boolean value needs its own parentheses")
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _SPECIAL_CALL_SHAPES):
            problem = _special_call_problem(node)
            if problem is not None:
                return problem
        what = _NOT_CLAIM_SYNTAX.get(type(node))
        if what is not None:
            return f"{what} is not claim syntax"
        if isinstance(node, ast.Call) and node.keywords:
            if any(k.arg is None for k in node.keywords):
                return "argument unpacking (`**`) is not claim syntax"
            called = node.func.id if isinstance(node.func, ast.Name) else ""
            words = [k.arg for k in node.keywords]
            if len(set(words)) != len(words):
                return "a keyword argument passed twice is not claim syntax"
            if called and not _is_grammar_function(called):
                # a function the claim names takes keywords as its own
                # callers pass them, each a literal or a name
                for k in node.keywords:
                    if not _is_keyword_value(k.value):
                        return (f"{k.arg}={ast.unparse(k.value)} is not "
                                "claim syntax: a keyword argument takes a "
                                "literal or a name")
                continue
            allowed = linalg.CALL_KEYWORDS.get(called, ())
            if any(w not in allowed for w in words):
                return ("keyword arguments are not claim syntax on the "
                        "grammar's own functions: the keywords are `axis=` "
                        "on sum, mean, prod, min, max, std, var, count, "
                        "median, cumsum, cumprod, cummax and cummin, and "
                        "`ddof=` on std and var; a function the claim "
                        "names takes its own")
        if isinstance(node, ast.Constant) and (
                isinstance(node.value, bytes) or node.value is Ellipsis):
            return f"the literal {ast.unparse(node)} is not claim syntax"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
            return ("`~` is not claim syntax; approximate equality is "
                    "written `~=` (or `≈`)")
        if isinstance(node, ast.BinOp) and isinstance(node.op, _BITWISE_OPS):
            return "bitwise operators are not claim syntax"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"the attribute {node.attr!r} is not claim syntax"
        if (isinstance(node, ast.Name) and node.id.startswith("__")
                and node.id != _D_AT_SENTINEL):
            return f"the name {node.id!r} is not claim syntax"
    return None


def _find_bare_reserved_name(src: str, param_names: set[str]) -> str | None:
    """The first reserved function name (`grammar.is_reserved()`, or a
    `_SAFE_FUNCS`-only name like `len`/`sum`) used as a bare value
    rather than a call, in claim-law text `src`, `None` if there
    isn't one, or `src` doesn't even parse (some other check reports
    that). A name in `param_names` is never flagged, reserved or not;
    a real function can have a parameter literally named `d`, and a
    claim referencing that real parameter bare is exactly correct usage,
    not a missing call. Checked once, early, in `check_conjectures()`'s
    own per-claim loop; before either route ever runs, so a
    misspecified claim (`f(x) == sin` typed instead of `f(x) == sin(x)`)
    gets one clear, route-independent verdict (`skipped:misspecified`)
    instead of each route separately discovering the identical mistake
    through its own, differently-shaped internal error path
    (`_validate`'s own `InvalidConjecture`, `try_prove`'s
    `NotSymbolic`)."""
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        return None
    call_func_ids = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and id(node) not in call_func_ids \
                and node.id not in param_names:
            if is_reserved(node.id) or node.id in _SAFE_FUNCS:
                return node.id
    return None


_ASSUMING_RELATIONS = (">=", "<=", ">", "<", "==", "!=")
_ASSUMING_VERDICT = re.compile(
    r"^([A-Za-z_]\w*(?:\.\w+)*)\s+(?:is\s+proven|holds)$")


def _parse_assuming_relation(part: str):
    """Intent:
        One assuming conjunct as (lhs, relation, rhs), parsed
        directly rather than through claim(), which doesn't accept the
        strict `<`/`>` an assuming clause legitimately uses. The text
        is normalized first (`^` to `**`, unicode relations to ascii).

    Notes:
        `None` when no top-level relation operator is found.
    """
    from types import SimpleNamespace
    from .grammar import normalize as _normalize
    part = _normalize(part.strip())
    depth = 0
    i = 0
    while i < len(part):
        ch = part[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            for op in ("<=", ">=", "!=", "==", "~=", "<", ">"):
                if part.startswith(op, i):
                    # `<`/`>` must not be half of a two-char operator
                    if op in ("<", ">") and i + 1 < len(part) \
                            and part[i + 1] == "=":
                        continue
                    lhs, rhs = part[:i].strip(), part[i + len(op):].strip()
                    if not lhs or not rhs:
                        return None
                    if op == "~=":
                        # `a ~= b` is `abs(a - b) <= ε`
                        return SimpleNamespace(
                            lhs=f"abs(({lhs}) - ({rhs}))", relation="<=",
                            rhs="ε")
                    return SimpleNamespace(lhs=lhs, relation=op, rhs=rhs)
        i += 1
    return None


def _parse_assuming_links(part: str):
    """Intent:
        One assuming conjunct as its list of plain relations: a single
        relation gives one link, a chained comparison one link per
        adjacent pair, conjoined (`a < 0 < b` is `a < 0` and `0 < b`,
        through `grammar.split_relation_chain`, as a chained statement
        is read).

    Notes:
        `None` when the conjunct does not read as plain relations: no
        top-level relation, a chain `split_relation_chain` refuses (an
        equality inside a chain), or a side that is itself a
        comparison (`a < (0 < b)`).
    """
    from types import SimpleNamespace

    from .grammar import normalize as _normalize
    text = _normalize(part.strip())
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        node = None
    if isinstance(node, ast.Compare) and len(node.ops) > 1:
        try:
            chain = split_relation_chain(text)
        except NoRelation:
            return None
        links = [SimpleNamespace(lhs=lhs, relation=rel, rhs=rhs)
                 for lhs, rel, rhs in chain]
    else:
        single = _parse_assuming_relation(part)
        if single is None:
            return None
        links = [single]
    for link in links:
        for side in (link.lhs, link.rhs):
            try:
                side_node = ast.parse(side, mode="eval").body
            except SyntaxError:
                continue
            if isinstance(side_node, ast.Compare):
                return None
    return links


#: the word an auto-generated claim name spells each relation with
_RELATION_WORDS = {"=:=": "equiv", "==": "eq", "~=": "approx", "!=": "ne",
                   "<=": "le", ">=": "ge", "<": "lt", ">": "gt", "=": "eq"}
_RELATION_TOKEN = re.compile(r"=:=|==|~=|!=|<=|>=|<|>|=")


def auto_claim_name(statement: str) -> str:
    """Intent:
        The name a claim takes when none is given: its normalized
        statement as a lowercase identifier, each relation spelled as a
        word (`f(x) >= 0` -> `f_x_ge_0`, `f(x) <= 0` -> `f_x_le_0`), cut
        at 40 characters.

    Notes:
        The name depends on the statement alone, never on the claim's
        position among others, so two distinct claims can name alike;
        the callers that key claims by name refuse that collision.
    """
    worded = _RELATION_TOKEN.sub(
        lambda m: f" {_RELATION_WORDS[m.group(0)]} ", statement)
    return re.sub(r"[^a-z0-9]+", "_", worded.lower()).strip("_")[:40] or "claim"


def _conjoin_assuming(first: str, second: str, law: str) -> str:
    """Intent:
        Two `assuming` clauses of one claim as the single clause that is
        their conjunction, in the order written:
        `assuming m >= 3`, `assuming n >= 3` -> `assuming m >= 3 and n >= 3`.

    Raises:
        InvalidConjecture: when either clause is not a relation or a
            matrix structure premise (or an `and` of them), since a
            definedness or lemma premise has its own clause shape and
            joining it to another with `and` would change what it says.
    """
    from . import matrices as _mtx
    from .grammar import parse_domain_safety

    def joinable(part: str) -> bool:
        if _parse_assuming_links(part) is not None:
            return True
        parsed = parse_domain_safety(part.strip())
        return (parsed is not None and parsed[0] in _mtx.PROPERTIES
                and parsed[1].isidentifier())
    bodies = [re.sub(r"^assuming\s+", "", c.strip()) for c in (first, second)]
    for body in bodies:
        if "-->" in body or not all(joinable(part)
                                    for part in _split_top_and(body)):
            raise InvalidConjecture(
                f"two `assuming` clauses are joined only when both are "
                f"relations or structure premises; state the premises in one `assuming` clause, "
                f"joined with `and` (a bound on two dimensions can be "
                f"`assuming min(m, n) >= 3`): {law.strip()!r}")
    return "assuming " + " and ".join(bodies)


def _split_top_and(text: str) -> list[str]:
    """A relation conjunction split at top-level ` and ` only, an
    `and` nested inside brackets never splits."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(" and ", i):
            parts.append(text[start:i])
            start = i + 5
            i += 5
            continue
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _interpret_assumption(cj, conjectures):
    """Intent:
        Give a claim's `assuming <...>,` clause its constraining
        semantics. Accepted shapes:
        - a relation, or an `and`-joined conjunction of relations
          (`assuming b^2 - 4*a*c >= 0.01, ...`);
        - `is_defined(f)` / `f is defined`: the exact region where
          every call to f returns, computed fresh and PINNED into the
          statement as `is_defined(f) --> <region>`;
        - a pinned form (`<name> --> <region>`, `is_defined(f) -->
          <region>`): the recorded region, parse-validated here and
          then checked by the caller against a fresh computation. A
          pin that still agrees is kept byte-exact (the record stays
          stable); one the code has moved out from under is recomputed
          with a note. This is what makes a rendered statement
          round-trip without ever asserting a stale region;
        - a bare name referencing a sibling claim whose statement IS a
          relation (`assuming real_roots, ...`), rendered pinned;
        - `<name> is proven` / `<name> holds`: the prerequisite-lemma
          form, the referenced claim, earlier in the same batch, must
          have reached that verdict, and an empirical prerequisite
          caps this claim's own maximum verdict at holds.

    Notes:
        Returns None for no clause; ("relation", display,
        [Conjecture, ...]) for constraint clauses; ("defined",
        display) for the un-pinned is_defined form (the caller
        computes and pins the region); ("verdict", display, name,
        wanted) for the prerequisite form; a Probe (skip) when the
        clause was clearly meant to be interpreted but can't be.
    """
    raw = (cj.assuming or "").strip()
    if not raw:
        return None
    text = re.sub(r"^assuming\s+", "", raw).strip()
    for part in _split_top_and(text):
        gate = re.match(r"^\s*(is_missing_safe|is_absent_safe)\s*\(.*\)\s*$", part)
        if gate is not None:
            note = _gate_premise_refusal(cj)
            return Probe(cj.name, statement_text(cj.relation, cj.lhs, cj.rhs),
                         "skipped:misspecified", route=None, note=note)

    # a matrix STRUCTURE premise (`assuming A is symmetric`,
    # `assuming is_positive_definite(A)`): a conjunct naming a matrix
    # predicate over a bare parameter. It narrows synthesis to
    # matrices with the structure (entailment-closed) and, on the
    # derive route, becomes a sympy assumption. A clause of structure
    # conjuncts alone is a structure premise; one that also states
    # relations (`assuming A is symmetric and det(A) > 0`) is a
    # relation premise over the rest, carrying the structures too.
    from . import matrices as _mtx
    from .grammar import parse_domain_safety
    struct_map: dict = {}
    others: list = []
    for part in _split_top_and(text):
        parsed = parse_domain_safety(part.strip())
        if (parsed is not None and not parsed[0].startswith("not ")
                and parsed[0] in _mtx.PROPERTIES
                and parsed[1].isidentifier()):
            struct_map.setdefault(parsed[1], set()).add(parsed[0])
        else:
            others.append(part.strip())
    closed = {param: tuple(sorted(_mtx.entailed(props)))
              for param, props in struct_map.items()}
    if struct_map and not others:
        return ("structure", text, closed)

    def skip(reason: str):
        return Probe(cj.name, statement_text(cj.relation, cj.lhs, cj.rhs),
                     "skipped", route=None, note=reason)

    def conjuncts_of(region_text: str, display: str):
        parsed_list = []
        for part in _split_top_and(region_text):
            parsed = _parse_assuming_links(part)
            inner = part.strip()[1:-1].strip()
            if (parsed is None and part.strip().startswith("(")
                    and part.strip().endswith(")")
                    and len(_split_top_and(inner)) > 1):
                return skip(f"a parenthesised conjunction in an assuming "
                            f"clause is not supported yet: write it without "
                            f"the parentheses, `assuming {inner}`")
            if parsed is None:
                return skip(f"assuming clause must be a plain relation "
                            f"(==, !=, >=, <=, >, <), or a chain of "
                            f"ordering relations (a < 0 < b): {part!r}")
            parsed_list.extend(parsed)
        if not parsed_list:
            return skip(f"empty assuming region in {text!r}")
        return ("relation", display, parsed_list)

    defined_form = re.fullmatch(
        r"(?:is_defined\(\s*f\s*\)|f\s+is\s+defined)"
        r"(?:\s*(?:-->|=>|⟹)\s*(?P<region>.+))?", text, re.DOTALL)
    if defined_form is not None:
        region = defined_form.group("region")
        if region is None:
            return ("defined", "f is defined")
        # the pinned form: the region after --> is the record's own
        # resolved fact. Parse-validated here (a garbage pin skips
        # loudly), then handed back as text: the caller recomputes the
        # region from the live code and keeps the pin only while the
        # two still agree, so a record can never keep asserting a
        # region the code has moved out from under.
        parsed = conjuncts_of(region.strip(),
                              f"f is defined --> {region.strip()}")
        if isinstance(parsed, Probe):
            return parsed
        return ("defined-pinned", f"f is defined --> {region.strip()}",
                region.strip())
    # one or more `<name> holds` / `<name> is proven` conjuncts: a
    # claim may rest on several lemmas, and the weakest of them bounds
    # what this claim can reach
    parts = [part.strip() for part in _split_top_and(text)]
    verdicts = [_ASSUMING_VERDICT.match(part) for part in parts]
    if any(v is not None for v in verdicts):
        if not all(v is not None for v in verdicts):
            unmatched = [part for part, v in zip(parts, verdicts) if v is None]
            return skip(f"assuming mixes lemma references with other "
                        f"conditions ({', '.join(repr(u) for u in unmatched)}) "
                        f"; state the lemmas in one `assuming` clause and "
                        f"the region conditions in the claim's own domain")
        refs = [(v.group(1), "proven" if " is " in part else "holds")
                for v, part in zip(verdicts, parts)]
        # a discharged lemma is an established fact, so its statement
        # is available to the proof as well as its verdict, the
        # caller decides whether the regions line up (see
        # _lemma_conjuncts)
        lemmas = [c for c in conjectures
                  if c is not cj and getattr(c, "name", None)
                  in {name for name, _ in refs}]
        return ("verdict", text, refs, lemmas)
    other_verdict = re.search(
        r"(?:^|\band\s+)([A-Za-z_]\w*(?:\.\w+)*)\s+is\s+"
        r"(falsified|unknown)\b", text)
    if other_verdict is not None:
        # a premise rests on a claim that holds or is proven; any other
        # verdict word is refused rather than read as no premise at all
        ref, word = other_verdict.group(1), other_verdict.group(2)
        names = {getattr(c, "name", None) for c in conjectures
                 if c is not cj}
        missing = ("" if ref in names else
                   f"; and {ref!r} names no claim in this batch")
        return skip(f"`assuming {ref} is {word}` is not a premise mathema "
                    f"reads: a premise rests on a claim that holds or is "
                    f"proven (`assuming {ref} holds`, `assuming {ref} is "
                    f"proven`){missing}")
    pinned_name = re.fullmatch(r"([A-Za-z_]\w*(?:\.\w+)*)\s*(?:-->|=>|⟹)\s*(.+)",
                               text, re.DOTALL)
    if pinned_name is not None:
        name, region = pinned_name.group(1), pinned_name.group(2).strip()
        return conjuncts_of(region, f"{name} --> {region}")
    if re.fullmatch(r"[A-Za-z_]\w*", text):
        ref = next((c for c in conjectures
                    if c is not cj and getattr(c, "name", None) == text), None)
        if ref is None or not ref.rhs or ref.relation not in _ASSUMING_RELATIONS:
            return skip(f"assuming references {text!r}, which is not a "
                        f"claim in this batch with a plain relation statement")
        region = f"{ref.lhs} {ref.relation} {ref.rhs}"
        return conjuncts_of(region, f"{ref.name} --> {region}")
    if struct_map:
        relations = conjuncts_of(" and ".join(others), text)
        if isinstance(relations, Probe):
            return relations
        return (*relations, closed)
    return conjuncts_of(text, text)


#: how to write each math constant when a parameter of the same name
#: takes the bare token
_CONSTANT_SPELLINGS = {
    "e": "write exp(1) for Euler's number",
    "pi": "write acos(-1) for pi",
    "oo": "write inf for infinity",
    "inf": "write oo for infinity",
    "infinity": "write inf for infinity",
}


def _shadowed_constants(lhs: str, rhs: str, param_names: set) -> list[str]:
    """Intent:
        Math-constant names (`e`/`pi`) that a real parameter shadows: a
        bare `ast.Name` in the law that is both a `MATH_CONSTANTS` name
        AND a parameter. The parameter wins (unchanged), but the caller
        warns, naming the spelling that still reaches the constant
        (`_CONSTANT_SPELLINGS`), so the reading is never silent.

    Notes:
        Value position only: a name in a call's function slot (there is
        none for these, but the guard keeps the rule exact) is not a
        shadow. `None` sides contribute nothing.
    """
    hits: list[str] = []
    for src in (lhs, rhs):
        if not src:
            continue
        try:
            tree = ast.parse(str(src), mode="eval")
        except SyntaxError:
            continue
        call_func_ids = {id(n.func) for n in ast.walk(tree)
                         if isinstance(n, ast.Call)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and id(node) not in call_func_ids \
                    and node.id in MATH_CONSTANTS and node.id in param_names \
                    and node.id not in hits:
                hits.append(node.id)
    return hits


#: names a claim may use as values without declaring them: the
#: mathematical constants, infinity, the missing-value sentinel, and the
#: claim's own tolerance
_KNOWN_VALUE_NAMES = frozenset(
    set(MATH_CONSTANTS) | {"oo", "infinity", "inf", "nan", "missing",
                           "eps", "epsilon", "ε", _D_AT_SENTINEL})

#: calls whose argument after the expression is a variable they bind
#: (`d(f(x), x)`, `Sum(f(i), i, 1, n)`, `lim(f(x), x, 0)`)
_BINDING_CALLS = frozenset({"d", "integrate", "Sum", "Prod", "sum", "prod",
                            "lim"})


def _bound_by_calls(tree) -> set:
    """Intent:
        The variables a derivative, integral, sum, product or limit
        binds inside a parsed expression: the argument after the
        expression, every differentiation variable of `d`, and each
        variable a `d(...) @ {x = a}` evaluation substitutes.
    """
    bound: set = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _BINDING_CALLS):
            continue
        args = node.args[1:]
        if node.func.id != "d":
            args = args[:1]
        after_at = None
        for arg in args:
            if isinstance(arg, ast.Name) and arg.id == _D_AT_SENTINEL:
                after_at = 0
                continue
            if after_at is not None:
                if after_at % 2 == 0 and isinstance(arg, ast.Name):
                    bound.add(arg.id)
                after_at += 1
            elif isinstance(arg, ast.Name):
                bound.add(arg.id)
    return bound


def _sides(lv, rv) -> str:
    """Intent:
        The two compared values of a failed relation, `left vs right`;
        two strings that differ yet read the same (a composed and a
        decomposed character) are both spelled out.
    """
    if isinstance(lv, str) and isinstance(rv, str):
        import unicodedata

        from .probing import spell_text
        alike = lv != rv and (unicodedata.normalize("NFC", lv)
                              == unicodedata.normalize("NFC", rv))
        return f"{spell_text(lv, force=alike)} vs {spell_text(rv, force=alike)}"
    return f"{lv!r} vs {rv!r}"


def _names_in_claim(cj) -> set:
    """Intent:
        Every bare name the claim's statement reads, across its sides
        and chain links: the parameters it quantifies. A parameter the
        claim fills with a literal (`f(values, "nope")`) is not among
        them.
    """
    names: set = set()
    sides = [cj.lhs, cj.rhs] + [t for link in (cj.links or ()) for t in (link[0], link[2])]
    for side in sides:
        if not side:
            continue
        try:
            tree = ast.parse(side, mode="eval")
        except SyntaxError:
            continue
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    return names


def _declared_names(cj, cj_domain: dict, facts, fn) -> set:
    """Intent:
        Every name a claim may use as a value: the function's
        parameters, names bound by `for`/`let`, bound functions, the
        dimension names of a declared space (`R^(m,n)`) or of a `Shape`
        marker on the signature, and the known constants.
    """
    declared = (set(facts.params) | set(cj_domain) | set(cj.free_vars)
                | set(cj.funcs or ()) | set(_KNOWN_VALUE_NAMES) | {"f"})
    for bound in cj_domain.values():
        declared |= {d for d in getattr(bound, "dims", ()) if isinstance(d, str)}
    if fn is not None:
        try:
            from .types import shapes_from_signature
            for marker in shapes_from_signature(fn).values():
                declared |= {d for d in getattr(marker, "dims", ())
                             if isinstance(d, str)}
        except Exception:
            pass
    return declared


def _undeclared_names(cj, declared: set) -> list[str]:
    """Intent:
        The names a claim's statement, chain links and relational
        premise use as values that nothing declares, in the order they
        first appear. A name used as a subscript (`f(n)[i]`) is an
        index, quantified over the valid positions, and so is bound. Empty for a claim whose statement is not a
        relation (a safety predicate, `f =:= g`), whose operands are
        read differently.
    """
    if cj.relation not in ("==", "~=", "!=", "<=", ">=", "<", ">", "raises",
                           "in", "not in"):
        return []
    sides = [cj.lhs] if cj.relation == "raises" or cj.rhs_bound is not None \
        else [cj.lhs, cj.rhs]
    for link in cj.links or ():
        sides += [link[0], link[2]]
    premise = re.sub(r"^assuming\s+", "", (cj.assuming or "").strip())
    if premise and "-->" not in premise:
        parts = [_parse_assuming_links(p) for p in _split_top_and(premise)]
        if all(p is not None for p in parts):
            sides += [s for links in parts for p in links
                      for s in (p.lhs, p.rhs)]
    trees = []
    for src in sides:
        if not src:
            continue
        try:
            trees.append(ast.parse(str(src), mode="eval"))
        except SyntaxError:
            continue
    # a subscript index (`f(n)[i] == i`) binds its name on every side
    indices = {n.id for tree in trees for sub in ast.walk(tree)
               if isinstance(sub, ast.Subscript)
               for n in ast.walk(sub.slice) if isinstance(n, ast.Name)}
    found: list[str] = []
    for tree in trees:
        call_funcs = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        bound = _bound_by_calls(tree) | indices
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and id(node) not in call_funcs
                    and not node.id.startswith("__")
                    and node.id not in declared and node.id not in bound
                    and node.id not in found):
                found.append(node.id)
    return found


def _unbound_call_names(lhs: str, rhs: str, existing: set) -> list[str]:
    """Intent:
        Call-position names in a claim's law text that aren't `f`, a
        recognized math/reserved call form, or already bound, the
        candidates for scope resolution, and the names the renderer
        must treat as functions in the meantime.
    """
    from .grammar import reserved_names
    known = ({"f"} | existing | set(_SAFE_FUNCS) | reserved_names()
             | {"sum", "prod", "raises"} | set(linalg.VOCABULARY))
    found: list[str] = []
    for src in (lhs, rhs):
        if not src:
            continue
        try:
            tree = ast.parse(str(src), mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and not node.func.id.startswith("__") \
                    and node.func.id not in known and node.func.id not in found:
                found.append(node.func.id)
    return found


def _collect_definedness_guards(fn, facts) -> list:
    """Every raise-region guard of fn itself; see `_definedness_guards`."""
    return _definedness_guards(fn, facts)[0]


def _definedness_guards(fn, facts, working: bool = False,
                        domain: "dict | None" = None) -> "tuple[list, list]":
    """Intent:
        `(guards, gaps)`: every raise-region guard of fn itself,
        registered partiality lemmas plus explicit raise branches from
        the piecewise lift, and the reasons the list may be incomplete
        (a statement the walk stopped at, an operation whose region does
        not lift, a call whose definedness is not known, explicit raises
        the piecewise lift could not read). An explicit raise counts
        whatever its exception type, `raise OverflowError` included,
        since it is the author defining the function (P2). With
        `working`, the explicit raises are the function's own guards
        cutting its working domain (decision A) and are left out; what
        remains is every way a call inside the working domain fails.
    """
    from .symbolic._conditioned import lift_piecewise
    from .symbolic._partiality import partiality_walk
    guards: list = []
    gaps: list = []
    opaque: list = []
    try:
        walked, unread = partiality_walk(fn, facts, domain, opaque_out=opaque)
        guards += walked
        if unread:
            gaps.append(unread)
    except Exception:
        gaps.append("the raise-region pass failed")
    gaps += opaque
    raises = facts.tree is not None and any(
        isinstance(node, ast.Raise) for node in ast.walk(facts.tree))
    if working:
        raises = False
    elif facts.branch_count and not facts.loops and not facts.recursion:
        try:
            pw = lift_piecewise(fn, facts)
            if pw is not None:
                guards += pw.raise_guards
            elif raises:
                gaps.append(_RAISES_UNREAD)
        except Exception:
            if raises:
                gaps.append(_RAISES_UNREAD)
    if raises and not (facts.branch_count and not facts.loops
                       and not facts.recursion):
        gaps.append("the explicit raises do not lift")
    enforced = getattr(fn, "__mathema_enforced_range__", None)
    if enforced and (enforced.get("intervals") or enforced.get("checks")):
        region = _range_violation_region(fn, facts, enforced)
        if region is None:
            gaps.append("derive cannot read the result range enforce_range "
                        "checks, so it decides nothing about it; the probe "
                        "runs the code instead")
        else:
            guards.append((region, "RangeError"))
    return guards, gaps


def _working_domain_record(fn, facts, cj, domain: dict) -> dict:
    """Intent:
        What a family claim's working domain is, for the record: each
        parameter whose domain the function's own guards narrow, mapped
        to the narrowed domain as text, and `guards` listing the
        conditions a conditional raise cuts. Empty for a value claim
        (its explicit domain is never narrowed) and where no guard
        narrows anything.
    """
    import sympy

    from .domain import bound_to_sympy_set
    if facts is None:
        return {}
    if cj.relation not in routes.examine_predicates():
        # a value claim: only a parameter it binds no domain for
        if not _reads_working_domain(fn, facts, cj, domain):
            return {}
        unbound = {p: found[1] for p in facts.params
                   if domain.get(p) is None
                   and (found := _unbound_working_bound(fn, facts, p))}
        cuts = guard_cut_texts(fn, facts) or [
            str(c) for c in _own_guard_conditions(fn, facts)]
        cuts += _finite_guard_texts(facts, domain)
        if cuts:
            unbound["guards"] = cuts
        return unbound
    cuts = guard_cut_texts(fn, facts)
    enforced = getattr(fn, "__mathema_enforced_domain__", None) or {}
    listed_texts = _finite_guard_texts(facts, domain)
    if not cuts and not enforced and not listed_texts:
        return {}
    out: dict = {}
    from .domain import render_domain_bound as _render_bound
    from .hazards import finite_guard_sets
    for p, values in finite_guard_sets(facts).items():
        if domain.get(p) is None:
            out[p] = _render_bound(values)
    for p in facts.params:
        bound = domain.get(p)
        if bound is None:
            continue
        try:
            here = bound_to_sympy_set(bound)
        except Exception:
            continue
        narrowed = here
        sym = sympy.Symbol(p, real=True)
        if p in enforced:
            try:
                narrowed = narrowed & bound_to_sympy_set(enforced[p])
            except Exception:
                pass
        for text in cuts:
            try:
                cond = sympy.sympify(text, locals={p: sym})
            except Exception:
                continue
            if getattr(cond, "free_symbols", None) != {sym}:
                continue
            try:
                narrowed = narrowed - cond.as_set()
            except Exception:
                continue
        if narrowed != here:
            out[p] = _set_text(narrowed)
    if out and (cuts or listed_texts):
        out["guards"] = list(cuts) + listed_texts
    return out


def _finite_guard_texts(facts, domain: dict) -> list:
    """The condition of each guard refusing a parameter outside a set of
    strings, as claim text (`side not in {"buy", "sell"}`), for the
    parameters the claim binds no domain for."""
    from .domain import render_domain_bound
    from .hazards import finite_guard_sets
    return [f"{p} not in {render_domain_bound(values)}"
            for p, values in finite_guard_sets(facts).items()
            if (domain or {}).get(p) is None]


def _always_raises(stmts) -> bool:
    """Whether a block of statements raises on every path through it: a
    `raise`, or an `if` whose branches both always raise, reached before
    anything else ends the block."""
    for stmt in stmts:
        if isinstance(stmt, ast.Raise):
            return True
        if isinstance(stmt, ast.If) and stmt.orelse \
                and _always_raises(stmt.body) and _always_raises(stmt.orelse):
            return True
        if isinstance(stmt, (ast.Return, ast.Break, ast.Continue)):
            return False
    return False


def _working_domain_empty(fn, facts, cj, domain: dict) -> bool:
    """Intent:
        Whether a family claim's working domain is empty: f's own guards
        refuse every input its annotations and binding admit. The
        stateless families (is_state_safe, is_deterministic,
        is_reproducible) are examined from the source alone and are
        never read over a domain. Read from
        the body (no `return` anywhere and every path ends in a `raise`,
        or a guard cut or `enforce_domain` that leaves no point of a
        parameter's domain) and corroborated by calls at points of the
        domain, each of which must be refused by f's own guard.
    """
    import inspect

    import sympy

    from .domain import bound_to_sympy_set, without_sentinels
    if cj.relation not in routes.examine_predicates() or facts is None \
            or facts.tree is None or not facts.params:
        return False
    if cj.relation in families.GROUPS["stateless"]:
        # state and repeatability are read from the source, never by
        # calling f, and say nothing about which inputs f accepts
        return False
    # the numbers each parameter admits, its holes and absence aside
    domain = {p: without_sentinels(b) if b is not None else None
              for p, b in domain.items()}
    func = next((n for n in ast.walk(facts.tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
    if func is None:
        return False
    returns = any(isinstance(n, ast.Return) for n in ast.walk(func))
    empty = not returns and _always_raises(func.body)
    if not empty:
        enforced = getattr(fn, "__mathema_enforced_domain__", None) or {}
        cuts = guard_cut_texts(fn, facts)
        for p in facts.params:
            bound = domain.get(p)
            try:
                here = bound_to_sympy_set(bound) if bound is not None \
                    else sympy.S.Reals
                if p in enforced:
                    here = here & bound_to_sympy_set(enforced[p])
            except Exception:
                continue
            sym = sympy.Symbol(p, real=True)
            for text in cuts:
                try:
                    cond = sympy.sympify(text, locals={p: sym})
                    if getattr(cond, "free_symbols", None) == {sym}:
                        here = here - cond.as_set()
                except Exception:
                    continue
            if here is sympy.S.EmptySet:
                empty = True
                break
    if not empty:
        return False
    # corroborated: f's own guard refuses a call at each point tried
    from .claim_families import _interval_ends
    points = []
    for value_at in (lambda lo, hi: lo, lambda lo, hi: (lo + hi) / 2,
                     lambda lo, hi: hi):
        point = {}
        for p in facts.params:
            if facts.param_kinds.get(p) not in ("scalar", "int"):
                return False
            ends = _interval_ends(domain.get(p)) or (-1.0, 1.0)
            v = value_at(*ends)
            point[p] = int(v) if facts.param_kinds.get(p) == "int" else float(v)
        points.append(point)
    body = inspect.unwrap(fn)
    for point in points:
        try:
            _call_by_name(fn, point)
        except Exception as exc:
            if not deliberate_raise(exc, body if exc.__class__.__name__
                                    not in ("DomainError",) else fn):
                return False
            continue
        return False
    return True


def _point_of(text: "str | None") -> dict:
    """The `name = number` pairs a witness text states, before any
    colon that explains it."""
    out: dict = {}
    for name, value in re.findall(
            r"\b([A-Za-z_]\w*) = (-?[0-9.]+(?:e[-+]?\d+)?)\b",
            (text or "").split(":")[0]):
        out[name] = value
    return out


def _refused_by_own_guard(fn, witness) -> bool:
    """Whether f, called at a witness point (`{name: value}`), raises
    from one of its own guards."""
    if not witness:
        return False
    try:
        point = {str(k): float(v) for k, v in dict(witness).items()}
    except (TypeError, ValueError):
        return False
    try:
        _call_by_name(fn, point)
    except Exception as exc:
        return deliberate_raise(exc, fn)
    return False


def _own_guard_conditions(fn, facts) -> list:
    """Intent:
        The conditions of f's own explicit raise branches, as sympy
        relations; empty when they do not lift.
    """
    from .symbolic._conditioned import lift_piecewise
    if facts is None or facts.tree is None or not facts.branch_count \
            or facts.loops or facts.recursion:
        return []
    try:
        pw = lift_piecewise(fn, facts)
    except Exception:
        return []
    return [cond for cond, _exc in (getattr(pw, "raise_guards", None) or [])]


def _reads_working_domain(fn, facts, cj, domain: "dict | None") -> bool:
    """Intent:
        Whether a value claim is read over the working domain f's own
        raise branches leave: it binds no domain (in the claim or the
        call) for any parameter those branches read.
    """
    from .hazards import finite_guard_sets
    if cj.relation in routes.examine_predicates() or cj.relation == "raises":
        return False
    conds = _own_guard_conditions(fn, facts)
    read = {str(sym) for cond in conds
            for sym in getattr(cond, "free_symbols", ())}
    read |= set(finite_guard_sets(facts))
    bound = set(cj.domain or {}) | set(domain or {})
    return bool(read) and not (read & bound)


def _unbound_working_bound(fn, facts, p: str):
    """Intent:
        The working domain of a real parameter no binding names, as
        `(Interval, text)`: the real line cut by f's own guards (a
        conditional raise, `@enforce_domain`). None when the guards
        leave the whole line, leave something other than one interval,
        or the parameter is not a real scalar.
    """
    import sympy

    from .domain import Interval, bound_to_sympy_set, render_domain_bound
    from .hazards import finite_guard_sets
    listed = finite_guard_sets(facts).get(p)
    if listed is not None:
        # a guard to a set of strings leaves exactly that set
        return (listed, render_domain_bound(listed))
    if facts.param_kinds.get(p) != "scalar":
        return None
    here = sympy.S.Reals
    enforced = (getattr(fn, "__mathema_enforced_domain__", None) or {}).get(p)
    if enforced is not None:
        try:
            here = here & bound_to_sympy_set(enforced)
        except Exception:
            return None
    sym = sympy.Symbol(p, real=True)
    for text in guard_cut_texts(fn, facts):
        try:
            cond = sympy.sympify(text, locals={p: sym})
        except Exception:
            continue
        if getattr(cond, "free_symbols", None) != {sym}:
            continue
        try:
            here = here - cond.as_set()
        except Exception:
            return None
    if here == sympy.S.Reals:
        return None
    if isinstance(here, sympy.Union) and all(
            isinstance(part, sympy.Interval) for part in here.args):
        # the working domain is a union: stated, while the claim keeps
        # the real line and the routes skip what the guards refuse
        return (None, _set_text(here))
    if not isinstance(here, sympy.Interval):
        return None
    lo = float(here.start) if here.start.is_finite else float("-inf")
    hi = float(here.end) if here.end.is_finite else float("inf")
    return (Interval(lo, hi, not here.left_open, not here.right_open),
            _set_text(here))


def _set_text(found) -> str:
    """A real set as interval text: `[0, 4]`, `(0, 4]`, a union joined
    with `∪`."""
    import sympy
    if isinstance(found, sympy.Interval):
        lo = "(" if found.left_open else "["
        hi = ")" if found.right_open else "]"
        ends = [("-oo" if e == -sympy.oo else "oo" if e == sympy.oo
                 else str(e)) for e in (found.start, found.end)]
        return f"{lo}{ends[0]}, {ends[1]}{hi}"
    if isinstance(found, sympy.Union):
        return " ∪ ".join(_set_text(part) for part in found.args)
    return str(found)


def guard_cut_texts(fn, facts) -> list:
    """Intent:
        Each condition under which fn raises deliberately, as claim
        text (`x < 0`): its own explicit raise branches, the cuts its
        guards make in the working domain. Empty when there are none or
        they do not lift.
    """
    from .symbolic._base import REL_TEXT
    from .symbolic._conditioned import lift_piecewise
    if facts.tree is None or not facts.branch_count or facts.loops \
            or facts.recursion:
        return []
    try:
        pw = lift_piecewise(fn, facts)
    except Exception:
        return []
    out: list = []
    for cond, _exc in (getattr(pw, "raise_guards", None) or []):
        pieces = list(cond.args) if hasattr(cond, "args") and \
            type(cond).__name__ == "Or" else [cond]
        for piece in pieces:
            op = REL_TEXT.get(type(piece))
            text = (f"{piece.lhs} {op} {piece.rhs}" if op is not None
                    else str(piece))
            if text not in out:
                out.append(text)
    return out


def deliberate_raise(exc: BaseException, fn) -> bool:
    """Intent:
        Whether a call's exception is one of fn's own guards rejecting
        the call (decision A): `@enforce_domain`'s DomainError, an entry
        DimensionError from `@enforce_dimensions`, or a `raise`
        statement in fn's own body. A failed assert, an exit check, a
        RangeError and a raise from anything fn calls are not.
    """
    import inspect

    from .authoring import DimensionError, DomainError, MissingValueError
    if isinstance(exc, MissingValueError):
        return False
    if isinstance(exc, DomainError):
        return True
    if isinstance(exc, DimensionError):
        return not exc.at_exit
    if isinstance(exc, AssertionError):
        return False
    body = inspect.unwrap(fn)
    code = getattr(body, "__code__", None)
    tb = exc.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    if tb is None or code is None or tb.tb_frame.f_code is not code:
        return False
    return tb.tb_lineno in _raise_lines(body)


def _raise_lines(fn) -> frozenset:
    """The source lines of the `raise` statements in fn's own body."""
    try:
        lines, start = inspect.getsourcelines(fn)
        import textwrap
        tree = ast.parse(textwrap.dedent("".join(lines)))
    except (OSError, TypeError, SyntaxError):
        return frozenset()
    return frozenset(node.lineno + start - 1 for node in ast.walk(tree)
                     if isinstance(node, ast.Raise))


def _range_violation_region(fn, facts, enforced: dict):
    """Intent:
        Where `enforce_range` raises: the lifted result outside one of
        the intervals or checks it enforces, as a sympy condition over
        the parameters, or None when the body does not lift.
    """
    import sympy

    from .symbolic import lift
    try:
        lifted = lift(fn, facts)
    except Exception:
        return None
    if lifted is None or isinstance(lifted.expr, tuple):
        return None
    out = lifted.expr
    parts = []
    for bound in enforced.get("intervals") or ():
        lo, hi = bound[0], bound[1]
        if lo != -math.inf:
            parts.append(out < lo if getattr(bound, "closed_lo", True)
                         else out <= lo)
        if hi != math.inf:
            parts.append(out > hi if getattr(bound, "closed_hi", True)
                         else out >= hi)
    negated = {"<": ">=", "<=": ">", ">": "<=", ">=": "<"}
    for rel, number in enforced.get("checks") or ():
        parts.append(sympy.Rel(out, number, negated[rel]))
    return sympy.Or(*parts) if parts else None


def _negated_guard_texts(cond, negate, op_text) -> list[str]:
    """One guard condition, negated and rendered as claim-grammar
    relation texts. An Or-guard De Morgans into several conjuncts
    (`(a > 1) | (a < 0)` negates to `a <= 1` and `a >= 0`); a
    trivially-false guard contributes nothing; a shape with no plain
    negation contributes nothing either, the guard still gates
    claims through the raise-region machinery, this pass just gains no
    expressible region text from it (under-reporting is conservative:
    a pin with fewer conjuncts assumes less)."""
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    try:
        cond = _with_timeout(lambda: sympy.simplify(cond),
                             FAST_TIMEOUT_SECONDS)
    except Exception:
        pass
    if cond is sympy.false:
        return []
    if isinstance(cond, sympy.Or):
        out: list[str] = []
        for part in cond.args:
            texts = _negated_guard_texts(part, negate, op_text)
            if not texts:
                return []   # one inexpressible disjunct spoils the negation
            out.extend(texts)
        return out
    flip = negate.get(type(cond))
    if flip is None:
        return []
    flipped = flip(cond.lhs, cond.rhs)
    return [f"{flipped.lhs} {op_text[type(flipped)]} {flipped.rhs}"]


def _definedness_region_structured(fn, facts,
                                   gaps: "list | None" = None,
                                   working: bool = False,
                                   domain: "dict | None" = None) -> list:
    """Intent:
        The region where fn itself returns, as sympy relationals over
        fn's OWN parameter symbols; one per raise guard, negated,
        with And-shaped path guards reduced against the other
        conjuncts. The single structural source: the rendered region
        (`_definedness_region`) and the is_defined family's
        equivalence check both read from here, so they can never
        disagree about what the region is.

    Notes:
        When `gaps` is a list, the reasons the returned conjuncts may
        not be the whole region are appended to it: the guard
        collection's own gaps, and each guard whose negation is not a
        conjunction of relations (`x` a non-positive integer, a divisor
        that is zero everywhere). With `working`, the region is the part
        of the working domain where fn returns: its own explicit raises
        are guards and are left out (`_definedness_guards`). `domain`,
        when given, says which parameters are integers.
    """
    import sympy

    from .symbolic._base import NEGATED_REL as negate
    negated_rels: list = []

    def emit(rel) -> None:
        if rel not in negated_rels:
            negated_rels.append(rel)

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    guards, collection_gaps = _definedness_guards(fn, facts, working, domain)
    dropped: list = []

    def drop(cond) -> None:
        dropped.append(f"the region where {cond} has no expressible "
                       f"complement")
    deferred: list = []
    for cond, _exc in guards:
        if any(isinstance(sym, sympy.Dummy) for sym in cond.free_symbols):
            # a loop body's guard over its trip index: the region is
            # where SOME trip meets it, which no conjunct states
            drop(cond)
            continue
        if isinstance(cond, sympy.Not):
            # a failed assert's region, `not (0 <= x <= 4)`, read as the
            # disjunction it is
            cond = cond.to_nnf()
        # note: simple (and Or-shaped) guards yield conjuncts directly;
        # And-shaped path guards wait for the second pass below (an
        # unsatisfiable one, Eq(x, 0) & (x > 0), simplifies away
        # here first)
        if isinstance(cond, sympy.And):
            try:
                cond = _with_timeout(lambda c=cond: sympy.simplify(c),
                                     FAST_TIMEOUT_SECONDS)
            except Exception:
                pass
            if cond is sympy.false:
                continue
            if isinstance(cond, sympy.And):
                deferred.append(cond)
                continue
        if cond is sympy.false:
            continue
        for piece in ([cond] if not isinstance(cond, sympy.Or)
                      else list(cond.args)):
            flip = negate.get(type(piece))
            if flip is not None and piece is not sympy.false:
                emit(flip(piece.lhs, piece.rhs))
            elif piece is not sympy.false:
                drop(piece)
    for cond in deferred:
        # a path guard And(a1, ..., an) negates to a disjunction, not
        # a region conjunct on its own. But wherever every arg except
        # one is IMPLIED by an existing conjunct (the path condition is
        # the negation of another guard's region, the common
        # guarded-parameter shape), the guard reduces to the negation
        # of the remaining arg, soundly: within the region, a1..ak hold,
        # so not(a1 & ... & an) is exactly not(a_rest).
        rest = [arg for arg in cond.args
                if not any(arg == negated for negated in negated_rels)]
        flip = negate.get(type(rest[0])) if len(rest) == 1 else None
        if flip is not None:
            emit(flip(rest[0].lhs, rest[0].rhs))
        else:
            drop(cond)
    if gaps is not None:
        gaps.extend(collection_gaps + dropped)
    return negated_rels


def _definedness_region(fn, facts) -> list[str]:
    """Intent:
        The structural region rendered as claim-grammar relation texts,
        the `is_defined` suggestion's statements, and the raw
        material `_defined_expansion` substitutes per call.
    """
    from .symbolic._base import REL_TEXT as op_text
    return [f"{rel.lhs} {op_text[type(rel)]} {rel.rhs}"
            for rel in _definedness_region_structured(fn, facts)]


def _region_texts_agree(pinned: str, fresh: str) -> bool:
    """Whether a recorded definedness region and a freshly computed one
    state the same thing, compared through the grammar's own normalize
    so spelling differences (glyphs, spacing) never read as drift."""
    from .grammar import normalize

    def canon(text: str) -> str:
        try:
            return " ".join(normalize(text or "").split())
        except Exception:
            return " ".join((text or "").split())
    return canon(pinned) == canon(fresh)


def _defined_expansion(fn, facts, cj) -> str:
    """Intent:
        The exact region `assuming is_defined(f)` quantifies over,
        computed and rendered, the negation of every raise region
        (explicit guards and registered partiality lemmas), each
        substituted with each claim call's own arguments, or "" when
        the function has no raise region at all: a total function's
        definedness premise carries no arrow, never a prose stand-in
        the grammar would refuse to read back.
    """
    from .symbolic._base import (NEGATED_REL as negate, NotSymbolic,
                                 _bind_params, _expr_to_sympy)
    guards = _collect_definedness_guards(fn, facts)
    if not guards:
        return ""
    try:
        params, _aggregate = _bind_params(fn, facts)
    except Exception:
        return ""
    conds: list[str] = []
    for src in (cj.lhs, cj.rhs):
        if not src:
            continue
        try:
            tree = ast.parse(str(src), mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "f"):
                continue
            subs = {}
            ok = True
            for p, arg in zip(facts.params, node.args):
                sym = params.get(p)
                try:
                    val = _expr_to_sympy(arg, dict(params))
                except NotSymbolic:
                    ok = False
                    break
                if sym is None or isinstance(val, tuple):
                    ok = False
                    break
                subs[sym] = val
            if not ok:
                continue
            from .symbolic._base import REL_TEXT as op_text
            for cond, _exc in guards:
                try:
                    sub = cond.subs(subs, simultaneous=True)
                except Exception:
                    continue
                for text in _negated_guard_texts(sub, negate, op_text):
                    if text not in conds:
                        conds.append(text)
    if not conds:
        return ""
    return " and ".join(conds)


def _outside_definedness(fn, facts, cj):
    """Intent:
        A predicate over a claim's points: True where some call to f in
        the claim meets one of f's raise guards (the region `assuming f
        is defined` leaves out, exactly as the proof reads it), or where
        that cannot be decided at the point. Every point is outside when
        a call's arguments do not lift.
    """
    import sympy

    from .symbolic._base import NotSymbolic, _bind_params, _expr_to_sympy
    guards = _collect_definedness_guards(fn, facts)
    if not guards:
        return None
    try:
        params, _aggregate = _bind_params(fn, facts)
    except Exception:
        return lambda point: True
    regions: list = []
    for src in (cj.lhs, cj.rhs):
        if not src:
            continue
        try:
            tree = ast.parse(str(src), mode="eval")
        except SyntaxError:
            return lambda point: True
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "f"):
                continue
            subs = {}
            for p, arg in zip(facts.params, node.args):
                sym = params.get(p)
                try:
                    val = _expr_to_sympy(arg, dict(params))
                except NotSymbolic:
                    return lambda point: True
                if sym is None or isinstance(val, tuple):
                    return lambda point: True
                subs[sym] = val
            for cond, _exc in guards:
                regions.append(cond.subs(subs, simultaneous=True))

    def outside(point: dict) -> bool:
        for region in regions:
            values = {}
            for sym in region.free_symbols:
                value = point.get(str(sym))
                if isinstance(value, bool) or not isinstance(value, (int, float)) \
                        or not math.isfinite(value):
                    return True
                values[sym] = sympy.Rational(value)
            try:
                truth = region.subs(values)
            except Exception:
                return True
            if truth is sympy.false:
                continue
            return True
        return False
    return outside


def _calling_scope() -> dict:
    """Intent:
        The merged local variables of every non-mathema frame on the
        current call stack, nearest frame winning a name collision,
        the "functions declared as local variables" a claim's bare
        call name can resolve against (a notebook cell's helper, a
        test function's nested def).

    Notes:
        Walk capped at 25 frames. Only read, never kept: the returned
        dict is a plain snapshot, holding no frame references.
    """
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    merged: dict = {}
    frame = inspect.currentframe()
    try:
        f = frame.f_back if frame is not None else None
        for _ in range(25):
            if f is None:
                break
            path = os.path.abspath(f.f_code.co_filename)
            if not path.startswith(pkg_dir + os.sep):
                for k, v in f.f_locals.items():
                    merged.setdefault(k, v)
            f = f.f_back
    finally:
        del frame
    return merged


def _bind_scope_functions(cj, fn) -> str:
    """Intent:
        Resolve a claim's unbound call names (`budget_line(...)` with
        no `funcs=` entry) against the target function's own module
        scope, then the calling scope's local variables, so a claim
        can reference a sibling function by name the way it references
        `f`. Returns a note suffix naming every binding made
        (terse input, explicit output), or "" when nothing resolved.

    Notes:
        An explicit `funcs=`/`let` binding always wins (its names are
        never rescanned); only plain Python functions bind (never a
        class or other callable, which probing would then construct).
        A name that resolves nowhere is left alone, the existing
        failure paths report it.
    """
    # an entry whose value is its own name is claim()'s parse-time
    # placeholder for a bare call name, exactly what this resolver
    # exists to fill in; a real binding (callable or dotted ref) is
    # never rescanned
    really_bound = {n for n, v in cj.funcs.items() if v != n}
    cj.under_test = cj.under_test | {n for n, v in cj.funcs.items()
                                     if v != n and _is_under_test(v, fn)}
    wanted = [n for n, v in cj.funcs.items() if v == n]
    wanted += [n for n in _unbound_call_names(cj.lhs, cj.rhs, really_bound)
               if n not in wanted]
    if not wanted:
        return ""
    fn_scope = module_scope(fn)
    caller_scope: dict | None = None
    bound = []
    for name in wanted:
        target, where = None, None
        v = fn_scope.get(name)
        if inspect.isfunction(v):
            target, where = v, "f's module"
        else:
            if caller_scope is None:
                caller_scope = _calling_scope()
            v = caller_scope.get(name)
            if inspect.isfunction(v):
                target, where = v, "the calling scope"
        if target is not None:
            cj.funcs[name] = target
            cj.scope_bound = cj.scope_bound | {name}
            if _is_under_test(target, fn):
                # the function under test by its own name is f
                cj.under_test = cj.under_test | {name}
                continue
            bound.append(f"{name} = {getattr(target, '__module__', '?')}"
                         f".{getattr(target, '__qualname__', name)} ({where})")
    return "; bound " + ", ".join(bound) if bound else ""


def _system_reach(cj) -> "str | None":
    """Intent:
        Why a function the claim names reaches the system, or None: a
        dotted reference resolved along its whole path, and a bare call
        name bound from the function's module or the calling scope
        judged by the function it bound to.
    """
    from ._claim_reach import object_refusal, walk_refusal
    for name, ref in sorted((cj.funcs or {}).items()):
        if isinstance(ref, str):
            if ref == name or "." not in ref or ":" in ref:
                continue
            said = walk_refusal(ref)
        elif name in (cj.scope_bound or ()):
            said = object_refusal(
                ref, f"{name} = {getattr(ref, '__module__', '?')}."
                     f"{getattr(ref, '__qualname__', name)}")
        else:
            continue
        if said is not None:
            return said
    return None


def _third_party_warnings(cj, fn) -> list:
    """Intent:
        One warning per function the claim names that is third-party
        code whose effects mathema cannot establish
        (`_claim_reach.third_party_warning`): a dotted `let` binding,
        and a bare call name bound from the function's module or the
        calling scope. Empty for mathema itself, the author's own
        project and a function whose effects are established; a call
        the claim makes that passes a value to `out`, by keyword or by
        position, writes its argument, so its effects are never
        established. The project is the one `_project_root` finds.
    """
    from ._claim_reach import call_writes_argument, third_party_warning
    own = getattr(fn, "__module__", "") or ""
    root = _project_root(fn)
    calls: dict = {}
    for side in (cj.lhs, cj.rhs, cj.assuming):
        try:
            tree = ast.parse(side or "0", mode="eval")
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                calls.setdefault(n.func.id, []).append(
                    (len(n.args), [k.arg for k in n.keywords]))

    def writes(name: str, obj) -> bool:
        return obj is not None and any(
            call_writes_argument(obj, n, kw) for n, kw in calls.get(name, ()))

    out: list = []
    for name, ref in sorted((cj.funcs or {}).items()):
        if isinstance(ref, str):
            if ref == name or "." not in ref or ":" in ref:
                continue
            obj = _resolve_bound_ref(ref)
            said = third_party_warning(f"let {name} = {ref}", obj, ref, own,
                                       root, writes_argument=writes(name, obj))
        elif name in (cj.scope_bound or ()):
            path = (f"{getattr(ref, '__module__', '?')}."
                    f"{getattr(ref, '__qualname__', name)}")
            said = third_party_warning(f"{name} = {path}", ref, path, own,
                                       root, writes_argument=writes(name, ref))
        else:
            continue
        if said is not None and said not in out:
            out.append(said)
    return out


def _project_root(fn) -> str:
    """Intent:
        The project a function belongs to: the nearest directory above
        its source file holding a pyproject.toml, else the working
        directory.
    """
    try:
        source = inspect.getsourcefile(fn) or ""
    except (TypeError, OSError):
        source = ""
    here = os.path.dirname(os.path.abspath(source)) if source else ""
    while here:
        if os.path.exists(os.path.join(here, "pyproject.toml")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return "."


def _resolve_bound_ref(ref: str):
    """Intent:
        A claim's dotted function reference resolved to its callable,
        or None when it does not resolve or reaches the system
        (`_claim_reach.walk_refusal`).
    """
    from ._claim_reach import walk_refusal
    if "." in ref and ":" not in ref and walk_refusal(ref) is not None:
        return None
    return _resolve_func_ref(ref)


def _validate(src: str, param_names: set[str],
              funcs: frozenset = frozenset()) -> tuple:
    """AST-whitelist an expression; returns (code, auxiliary names).
    `funcs` are extra callable letters a claim has bound (g, h, ...)."""
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise InvalidConjecture(f"unparseable law {src!r}") from e
    callable_names = {"f"} | funcs | set(_SAFE_FUNCS) | set(linalg.VOCABULARY)
    # a call's own function-position Name (`sin` in `sin(x)`) is a
    # legitimate reference to a recognized function; a bare Name with
    # the same text (`sin` on its own) is the mistake the reserved-name
    # check below exists to catch. `ast.walk` visits both through the
    # identical Name branch with no structural difference between them,
    # so the only way to tell them apart is to know in advance which
    # Name objects are sitting in a Call's own `func` slot.
    call_func_ids = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    aux: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            # the security refusal, distinct from the generic node
            # whitelist below: a dunder reach-in is never a law,
            # whichever route would evaluate it
            raise InvalidConjecture(
                f"disallowed attribute {node.attr!r} in {src!r}")
        if isinstance(node, ast.Attribute):
            # the transpose of any vector or matrix expression (`A.T`,
            # `f(A).T`), or a bundled parameter's field read
            # (`self.rate`, `cfg.a`, a table's column `df.returns`):
            # one level deep, rooted at a plain name, never a dunder
            if node.attr == "T":
                continue
            if not (isinstance(node.value, ast.Name)
                    and not node.value.id.startswith("__")
                    and not node.attr.startswith("__")):
                raise InvalidConjecture(
                    f"only a parameter's own field may be read by "
                    f"attribute in a law ({src!r})")
            continue
        if not isinstance(node, _ALLOWED_NODES):
            raise InvalidConjecture(
                f"{type(node).__name__} is not allowed in a law ({src!r})")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) \
                    or node.func.id.startswith("__"):
                raise InvalidConjecture(f"disallowed call in {src!r}")
            if node.func.id not in callable_names:
                called = node.func.id
                raise InvalidConjecture(
                    f"unrecognized call {called!r} in {src!r}, not a known "
                    f"math function, and no function of that name was found "
                    f"in f's module or the calling scope (bind one "
                    f"explicitly with funcs={{{called!r}: <function>}})")
        if isinstance(node, ast.Name) and id(node) not in call_func_ids:
            if node.id.startswith("__"):
                raise InvalidConjecture(f"disallowed name {node.id!r}")
            # a real parameter's own name always wins over any reserved
            # meaning; a function can have a parameter literally named
            # `d`, and a claim referencing it bare is correct usage, not
            # a missing call, regardless of what `d(...)` would mean.
            if node.id not in param_names:
                if is_reserved(node.id) or node.id in _SAFE_FUNCS:
                    raise InvalidConjecture(
                        f"{node.id!r} is reserved for its call form "
                        f"({node.id}(...)), not usable as a plain variable")
                # a bare math constant (pi/e that isn't a parameter) is
                # NOT an aux free variable; it binds to its real value
                # in the probe env below, matching the derive route's
                # _MATH_ATTRS rather than being sampled randomly
                if node.id not in callable_names and node.id not in MATH_CONSTANTS:
                    aux.add(node.id)
    code = compile(_exact_products(tree), "<conjecture>", "eval")
    from ._exact_side import register_source
    register_source(code, src, tree)
    return code, aux


def _exact_products(tree):
    """A copy of a claim's tree with each `a @ b` written as the call
    `_linalg_eval.matmul(a, b)` and each `a + b` (`-`, `*`, `/`, `**`)
    as `_linalg_eval.arith("+", a, b)`: exact entry by entry when an
    operand is an array of finite real numbers, the operands' own
    operator otherwise."""
    import copy

    from ._linalg_eval import ARITH, MATMUL
    arithmetic = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
                  ast.Pow: "**"}

    class _Products(ast.NodeTransformer):
        def visit_BinOp(self, node):
            self.generic_visit(node)
            if isinstance(node.op, ast.MatMult):
                return ast.copy_location(ast.Call(
                    func=ast.Name(id=MATMUL, ctx=ast.Load()),
                    args=[node.left, node.right], keywords=[]), node)
            op = arithmetic.get(type(node.op))
            if op is not None:
                return ast.copy_location(ast.Call(
                    func=ast.Name(id=ARITH, ctx=ast.Load()),
                    args=[ast.Constant(value=op), node.left, node.right],
                    keywords=[]), node)
            return node
    return ast.fix_missing_locations(_Products().visit(copy.deepcopy(tree)))



def _instance_bundles(fn, facts) -> dict:
    """Intent:
        The parameters that sample as INSTANCES rather than scalars:
        {param: (cls_or_None, field_names)}. A dataclass-annotated
        parameter (or a method's self on a dataclass) constructs
        normally over its declared numeric fields; a plain simple
        class samples the fields the body reads and builds the
        instance as `object.__new__(cls)` + setattr, the declared
        `param.field` domains are the validity contract, exactly as a
        scalar parameter's declared domain already is.
    """
    import dataclasses as _dc

    from .symbolic._base import (_attr_keys_used, _dataclass_field_names,
                                 _enclosing_class)
    out: dict = {}
    if facts.tree is None:
        return out
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        sig = None
    for p in facts.params:
        ann = sig.parameters[p].annotation if sig and p in sig.parameters \
            else None
        if ann is not None and _dc.is_dataclass(ann):
            fields = _dataclass_field_names(ann)
            if fields:
                out[p] = (ann, fields)
            continue
        if p == facts.params[0] and p in ("self", "cls"):
            cls = _enclosing_class(fn)
            if cls is not None and _dc.is_dataclass(cls):
                fields = _dataclass_field_names(cls)
                if fields:
                    out[p] = (cls, fields)
            elif cls is not None:
                read = _attr_keys_used(facts.tree, p)
                if read:
                    out[p] = (cls, read)
    return out


def _shape_constraints(assumption, resolver):
    """Intent:
        Premise constraints on dimension sizes, keyed by the
        resolver's canonical dimension keys: `(lo, hi, groups)` where
        `lo`/`hi` bound a key against a constant and `groups` are sets
        of keys an `==` forces to one size. The resolver already
        unifies shared marker names structurally, so only cross-key
        equalities and constant bounds come from premises here.

    Notes:
        Returns `(None, None, None)` when no premise touches a
        dimension. The rejection filter still guards every conjunct,
        so an unplanned constraint is a wasted draw, never a wrong
        verdict.
    """
    import ast as _ast

    if not assumption:
        return None, None, None
    marker_names = resolver.marker_names()

    def dim_key(node):
        if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
                and node.func.id == "dim" and len(node.args) == 2
                and isinstance(node.args[0], _ast.Name)
                and isinstance(node.args[1], _ast.Constant)):
            return resolver.key(node.args[0].id, int(node.args[1].value))
        if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
                and node.func.id == "dim" and len(node.args) == 1
                and isinstance(node.args[0], _ast.Name)):
            # `dim(a)` is the first axis, `dim(a, 0)`
            return resolver.key(node.args[0].id, 0)
        if isinstance(node, _ast.Name) and node.id in marker_names:
            return node.id
        return None

    def const(node):
        if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
            return int(node.value)
        return None

    groups: list = []
    lo: dict = {}
    hi: dict = {}
    saw = False
    for acj in assumption:
        try:
            ln = _ast.parse(acj.lhs, mode="eval").body
            rn = _ast.parse((acj.rhs or ""), mode="eval").body
        except SyntaxError:
            continue
        lk, rk = dim_key(ln), dim_key(rn)
        lc, rc = const(ln), const(rn)
        if acj.relation == "==" and lk is not None and rk is not None:
            if lk != rk:
                saw = True
                groups.append({lk, rk})
        elif lk is not None and rc is not None:
            saw = True
            if acj.relation in (">=", ">", "=="):
                lo[lk] = max(lo.get(lk, 1), rc + (1 if acj.relation == ">" else 0))
            if acj.relation in ("<=", "<", "=="):
                hi[lk] = min(hi.get(lk, 64), rc - (1 if acj.relation == "<" else 0))
        elif rk is not None and lc is not None:
            saw = True
            if acj.relation in ("<=", "<", "=="):
                lo[rk] = max(lo.get(rk, 1), lc + (1 if acj.relation == "<" else 0))
            if acj.relation in (">=", ">", "=="):
                hi[rk] = min(hi.get(rk, 64), lc - (1 if acj.relation == ">" else 0))
    if not saw:
        return None, None, None

    merged: list = []
    for g in groups:
        hit = [m for m in merged if m & g]
        for m in hit:
            merged.remove(m)
        merged.append(set().union(g, *hit))
    return lo, hi, merged


def _single_point(bound) -> "float | None":
    """The one value a bound admits when it is a single point (`let c
    be 2.0` reads as the interval [2.0, 2.0]), else None."""
    from .domain import _sentinel_piece
    pieces = [p for p in getattr(bound, "pieces", None) or ()
              if not _sentinel_piece(p)]
    if len(pieces) == 1 and isinstance(pieces[0], tuple) \
            and not isinstance(pieces[0], frozenset):
        lo, hi = pieces[0]
        if isinstance(lo, (int, float)) and lo == hi:
            return lo
    if isinstance(bound, tuple) and len(bound) == 2 and bound[0] == bound[1] \
            and isinstance(bound[0], (int, float)):
        return bound[0]
    return None


def call_defaults(fn, cj) -> "tuple[dict, dict, str | None]":
    """Intent:
        How a claim about a library function (a key of a registered
        `compendium:` file) calls it, beyond the parameters it
        samples: `(kept, pins, problem)`. `kept` maps each parameter
        with a default that the claim neither binds, pins nor names to
        that default; `pins` maps each parameter the claim pins (`let
        axis be 0`, `let keepdims be True`) to its value; `problem`
        names a pinned parameter the function does not have. For any
        other function nothing is kept (its defaulted parameters are
        sampled like the rest), a `None`/`True`/`False` pin is passed,
        and a number pin is passed for a parameter a call to f leaves
        out; where every call passes it, it stays a single-point bound.

    Notes:
        A number spelled `let p be 2` is a single-point bound, so it
        is a pin when `p` is a parameter, and a pin of a parameter that
        no longer exists when the claim's text never reads `p`; an
        integral point is passed as an int.
    """
    import re

    from .compendium import library_key_of
    key = library_key_of(fn)
    # a pin written in the call (`f(a, axis=1)`) is a pin as `let axis
    # be 1` is
    pins = {**_pins_in_calls(cj), **dict(getattr(cj, "param_pins", None) or {})}
    if key is None and not pins and not any(
            _single_point((cj.domain or {}).get(n)) is not None
            for n in (cj.free_vars or ())):
        return {}, {}, None
    try:
        sig = callable_signature(fn).parameters
    except (TypeError, ValueError):
        return {}, {}, None
    if key is None:
        # any other function: a literal pin is passed, a number pin on
        # a parameter some call to f leaves out is passed to that call,
        # and every defaulted parameter is sampled
        for name in sorted(cj.free_vars or ()):
            point = _single_point((cj.domain or {}).get(name))
            if point is None or name not in sig or name in pins \
                    or not _some_call_omits(cj, fn, name):
                continue
            pins[name] = (int(point) if isinstance(point, float)
                          and point.is_integer() else point)
        missing = sorted(p for p in pins if p not in sig)
        name = getattr(fn, "__qualname__", None) or "the function"
        return {}, {p: v for p, v in pins.items() if p in sig}, (
            f"{', '.join(missing)} {'is not a parameter' if len(missing) == 1 else 'are not parameters'} "
            f"of {name}, so the pin names nothing to pass"
            if missing else None)
    text = " ".join(str(t) for t in (cj.lhs, cj.rhs, cj.assuming) if t)
    # a name followed by a single `=` is a keyword argument of a grammar
    # word (`var(m, ddof=1)`), not a read of that name
    named = set(re.findall(r"\b([A-Za-z_]\w*)\b(?!\s*=(?!=))", text))
    # a method whose library states no signature takes a pin of any
    # name, passed on as a keyword
    any_keyword = bool(getattr(fn, "__mathema_unstated_signature__", False))

    def takes(p) -> bool:
        return p in sig or any_keyword
    for name in sorted(cj.free_vars or ()):
        point = _single_point((cj.domain or {}).get(name))
        if point is None or (not takes(name) and name in named):
            continue
        pins[name] = (int(point) if isinstance(point, float)
                      and point.is_integer() else point)
    missing = sorted(p for p in pins if not takes(p))
    problem = (f"{', '.join(missing)} {'is not a parameter' if len(missing) == 1 else 'are not parameters'} "
               f"of {key}, so the pin names nothing to pass"
               if missing else None)
    kept = {p: param.default for p, param in sig.items()
            if param.default is not param.empty
            and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
            and p not in (cj.domain or {}) and p not in pins
            and p not in named}
    return kept, {p: v for p, v in pins.items() if takes(p)}, problem


def _pins_in_calls(cj) -> dict:
    """The keyword arguments every call to f in the claim passes as the
    same literal value (`f(a, axis=1)`), `{name: value}`."""
    seen: dict = {}
    calls = 0
    sides = [cj.lhs, cj.rhs, *[t for link in (cj.links or ()) for t in (link[0], link[2])]]
    for src in sides:
        try:
            tree = ast.parse(src or "0", mode="eval")
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "f"):
                continue
            calls += 1
            for k in n.keywords:
                if k.arg is None:
                    continue
                if isinstance(k.value, ast.Name) and k.value.id == "inf":
                    value = float("inf")
                else:
                    try:
                        value = ast.literal_eval(k.value)
                    except ValueError:
                        continue
                seen.setdefault(k.arg, []).append(value)
    return {name: values[0] for name, values in seen.items()
            if len(values) == calls and all(v == values[0] for v in values)}


def _with_pins(fn, pins: dict):
    """`fn` called with each pinned parameter a call leaves out passed at
    its pin (`let alpha be 2`); `fn` itself when nothing is pinned."""
    if not pins:
        return fn
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        return fn

    def call(*a, **k):
        try:
            given = sig.bind_partial(*a, **k).arguments
        except TypeError:
            given = {}
        return fn(*a, **{**{p: v for p, v in pins.items() if p not in given}, **k})
    return call


def pins_into_calls(cj, fn):
    """Intent:
        `cj` written with its pins in the call: each `let p be v` that
        pins a parameter of f (`call_defaults`) and that the claim reads
        nowhere else becomes the keyword `p=v` on every call to f that
        leaves `p` out, and its `let` goes. `cj` unchanged when it pins
        nothing that can move.
    """
    import math
    import re
    from dataclasses import replace as _replace
    try:
        pins = call_defaults(fn, cj)[1]
        sig = callable_signature(fn)
    except Exception:
        return cj
    if not pins:
        return cj
    sides = [cj.lhs, cj.rhs, *[t for link in (cj.links or ()) for t in (link[0], link[2])]]
    read: set = set()
    for src in sides:
        # a keyword in a call names that callee's parameter, not a read
        stripped = re.sub(r"\b[A-Za-z_]\w*\s*=(?!=)", " ", src or "")
        read |= set(re.findall(r"\b[A-Za-z_]\w*\b", stripped))
    movable = {p: v for p, v in pins.items() if p not in read}
    if not movable:
        return cj

    def literal(v):
        if isinstance(v, float) and math.isinf(v):
            name = ast.Name(id="inf", ctx=ast.Load())
            return name if v > 0 else ast.UnaryOp(op=ast.USub(), operand=name)
        return ast.Constant(value=v)

    calls = [0]

    def rewrite(src):
        if not src:
            return src
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError:
            return src
        changed = False
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "f"):
                continue
            calls[0] += 1
            try:
                bound = sig.bind_partial(*([None] * len(n.args)),
                                         **{k.arg: None for k in n.keywords
                                            if k.arg is not None})
            except TypeError:
                continue
            for p, v in movable.items():
                if p not in bound.arguments:
                    n.keywords.append(ast.keyword(arg=p, value=literal(v)))
                    changed = True
        return ast.unparse(tree) if changed else src

    links = [(rewrite(a), rel, rewrite(b)) for a, rel, b in (cj.links or ())]
    lhs, rhs = rewrite(cj.lhs), rewrite(cj.rhs)
    if not calls[0]:
        # a statement that calls f nowhere (a region row) keeps its let
        return cj
    return _replace(cj, lhs=lhs, rhs=rhs,
                    links=links if cj.links else cj.links,
                    free_vars=frozenset(cj.free_vars or ()) - set(movable),
                    domain={k: v for k, v in (cj.domain or {}).items()
                            if k not in movable},
                    param_pins={k: v for k, v in (cj.param_pins or {}).items()
                                if k not in movable})


def _some_call_omits(cj, fn, name: str) -> bool:
    """Whether some call to f in the claim's text binds no argument to
    the parameter `name`."""
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        return False
    for src in (cj.lhs, cj.rhs):
        try:
            tree = ast.parse(src or "0", mode="eval")
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "f"):
                continue
            try:
                bound = sig.bind_partial(*([None] * len(n.args)),
                                         **{k.arg: None for k in n.keywords
                                            if k.arg is not None})
            except TypeError:
                continue
            if name not in bound.arguments:
                return True
    return False


def defaults_meta(kept: dict, pins: dict) -> dict:
    """Intent:
        The `mathema.defaults` record field: each parameter a library
        call passed at a value the claim did not sample, as the repr of
        that value (numpy's own no-value sentinel reads `<no value>`),
        a pinned one with `(pinned)` beside it.
    """
    out = {p: _value_text(v) for p, v in kept.items()}
    out.update({p: f"{_value_text(v)} (pinned)" for p, v in pins.items()})
    return dict(sorted(out.items()))


def _function_name(fn) -> str:
    """The dotted name a function is stated under: its library claim key
    (`numpy.mean`), else its module and qualified name."""
    from .compendium import library_key_of
    return library_key_of(fn) or (
        f"{getattr(fn, '__module__', '')}."
        f"{getattr(fn, '__qualname__', getattr(fn, '__name__', ''))}")


def _kept_in_calls(target, name: str, texts) -> dict:
    """Intent:
        Each parameter of `target` with a default that some call
        `name(...)` in `texts` leaves unpassed, mapped to that default.
    """
    import ast as _ast
    try:
        sig = callable_signature(target).parameters
    except (TypeError, ValueError):
        return {}
    kept: dict = {}
    for text in texts:
        try:
            tree = _ast.parse(str(text), mode="eval")
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if not (isinstance(node, _ast.Call)
                    and isinstance(node.func, _ast.Name)
                    and node.func.id == name):
                continue
            given = {k.arg for k in node.keywords if k.arg}
            for i, (p, param) in enumerate(sig.items()):
                if param.default is param.empty or param.kind in (
                        param.VAR_POSITIONAL, param.VAR_KEYWORD):
                    continue
                positional = param.kind in (param.POSITIONAL_ONLY,
                                            param.POSITIONAL_OR_KEYWORD)
                if (positional and i < len(node.args)) or p in given:
                    continue
                kept[p] = param.default
    return kept


def claim_defaults(fn, cj) -> dict:
    """Intent:
        The `mathema.defaults` record field: for each function the claim
        calls at values it does not sample, keyed by the function's
        dotted name, the values passed (`defaults_meta`). The target
        contributes what `call_defaults` keeps and pins; a `let`-bound
        library function (`let g = numpy.sqrt`) contributes each
        defaulted parameter a call to it in the claim leaves unpassed.
    """
    from .compendium import library_key_of
    out: dict = {}
    kept, pinned, _problem = call_defaults(fn, cj)
    if kept or pinned:
        out[_function_name(fn)] = defaults_meta(kept, pinned)
    texts = [t for t in (cj.lhs, cj.rhs, cj.assuming) if t]
    for name, ref in sorted((cj.funcs or {}).items()):
        if ref == name:
            continue
        target = ref if callable(ref) else _resolve_bound_ref(str(ref))
        key = library_key_of(target) if target is not None else None
        if key is None or key in out:
            continue
        bound_kept = _kept_in_calls(target, name, texts)
        if bound_kept:
            out[key] = defaults_meta(bound_kept, {})
    return dict(sorted(out.items()))


def defaults_note(resolved: dict) -> str:
    """The note line for a `claim_defaults` result: the values each
    function was held at, the function named when there are several."""
    def values(held: dict) -> str:
        return ", ".join(f"{p}={v}" for p, v in held.items())
    if len(resolved) == 1:
        (held,) = resolved.values()
        return "held at their defaults: " + values(held)
    return "held at their defaults: " + "; ".join(
        f"{name} {values(held)}" for name, held in resolved.items())


def _value_text(value) -> str:
    text = repr(value)
    return "<no value>" if text in ("<no value>", "<NoValue>") else text


def _draw_trial_sizes(resolver, lo, hi, groups, rng, floor=None):
    """Sizes for one trial: the resolver draws one per distinct key
    (shared dims agree structurally), then premise equality groups
    collapse each to a single shared draw and premise bounds apply.
    `floor` is the resolver's round of guaranteed small draws."""
    sizes = resolver.draw_sizes(rng, lo, hi, floor=floor)
    for group in (groups or []):
        g_lo = max((lo.get(k, 1) for k in group), default=1)
        g_hi = min((hi.get(k, max(6, 4 * g_lo)) for k in group),
                   default=max(6, 4 * g_lo))
        n = max(1, g_lo) if floor == 0 else \
            rng.randint(max(1, g_lo), max(g_lo, g_hi))
        for k in group:
            sizes[k] = n
    return sizes


def _synth_instance(bundle, p: str, cj_domain: dict, rng, specials):
    """Intent:
        One sampled instance for a bundled parameter: every field
        drawn like a scalar parameter named `p.field` (its declared
        domain respected when one exists). Dataclasses construct
        normally; a plain class is built field-by-field without
        running __init__; the declared field domains are the
        contract.
    """
    import dataclasses as _dc

    from .probing import _synth
    cls, fields = bundle
    bound = cj_domain.get(p)
    if getattr(bound, "base_type", None) == "L":
        # the parameter is quantified over a language: its members are
        # the instances, and a claim-level field bound narrows them by
        # a bounded rejection
        from .domain import path_bindings_hold
        inst = None
        for _ in range(20):
            inst = _synth("object", rng, bound)
            if path_bindings_hold(inst, p, cj_domain):
                break
        return inst
    values = {f: _synth("float", rng, cj_domain.get(f"{p}.{f}"),
                        specials=specials) for f in fields}
    if isinstance(cls, type) and _dc.is_dataclass(cls):
        return cls(**values)
    inst = object.__new__(cls)
    for f, v in values.items():
        setattr(inst, f, v)
    return inst


def _emit_position(probe, conjectures: list, declared_order: dict) -> float:
    """Where a probe belongs in the returned list: its conjecture's own
    declared position, so dependency-driven adjudication order never
    leaks into what the caller sees. A float companion sits directly
    after the claim it was spawned from."""
    parent = (probe.meta or {}).get("mathema.companion_of")
    name = parent if parent is not None else probe.name
    for cj in conjectures:
        if cj.name == name:
            return declared_order.get(id(cj), 0) + (0.5 if parent else 0)
    return 0


def _with_empty_input_lines(probe: "Probe", ctx, fn, facts,
                            companions: bool, siblings: list = ()):
    """Intent:
        `(probe, lines)`: the claim's empty-input lines
        (`_empty_input.empty_input_lines`), and the claim itself,
        falsified with the witness of the first falsified line. A claim
        already falsified keeps its own witness; a skipped claim has no
        lines.
        Without `companions` (a caller asking for the claim alone, as
        for the float companion) the claim is its mathematics over
        non-empty inputs and no line is made. `siblings` are the claims
        checked beside it, whose literal calls at the empty input
        (`f([]) in {missing}`) state the empty policy.
    """
    if not companions or probe.verdict.startswith("skipped"):
        return probe, []
    assumption = (None if ctx.assumption is None else
                  [(a.lhs, a.relation, a.rhs) for a in ctx.assumption])
    try:
        from ._empty_input import empty_input_lines
        from ._empty_input import STATED
        lines = empty_input_lines(ctx.cj, fn, facts, ctx.cj_domain,
                                  assumption, [*siblings, *STATED.get()])
    except TimeoutError:
        raise
    except Exception:
        return probe, []
    broken = next((line for line in lines if line.verdict == "falsified"),
                  None)
    if broken is None or probe.verdict == "falsified":
        return probe, lines
    return _falsified_by_empty_input(probe, broken), lines


def _falsified_by_empty_input(probe: "Probe", broken: "Probe") -> "Probe":
    """Intent:
        `probe` falsified by its falsified empty-input line `broken`, with
        the claim's own finding over non-empty inputs kept in
        `meta["mathema.mathematics"]`.
    """
    from dataclasses import replace as _replace
    note = (f"{probe.note + '; ' if probe.note else ''}{broken.name} is "
            f"falsified: {broken.note}")
    # the verdict is the executed call's, so the route is the probe's;
    # a proof over the non-empty inputs stays in the sketch
    # the claim's own finding over non-empty inputs, kept as it was
    mathematics = {k: v for k, v in (("verdict", probe.verdict), ("route", probe.route),
                                     ("note", probe.note), ("n", probe.n))
                   if v is not None}
    meta = {**(probe.meta or {}), "mathema.empty_input": broken.name,
            "mathema.mathematics": mathematics,
            "mathema.witness_executed": True}
    return _replace(probe, verdict="falsified", route="probe",
                    counterexample=broken.counterexample, note=note,
                    meta=meta)


def _own_finding(probe: "Probe") -> "Probe":
    """`probe` as it was before its empty-input line falsified it: its
    own finding over non-empty inputs, from `meta["mathema.mathematics"]`."""
    from dataclasses import replace as _replace
    found = (probe.meta or {}).get("mathema.mathematics")
    if not (probe.meta or {}).get("mathema.empty_input") or not found:
        return probe
    meta = {k: v for k, v in (probe.meta or {}).items()
            if k not in ("mathema.empty_input", "mathema.mathematics",
                         "mathema.witness_executed")}
    return _replace(probe, verdict=found["verdict"], route=found.get("route"),
                    note=found.get("note"), n=found.get("n", probe.n),
                    counterexample=None, meta=meta)


def _emit_companion(out: list, companion: "Probe", parent: str) -> None:
    """Append a stamped float companion to the output, tagged with the
    claim it was spawned from and the family it belongs to."""
    companion.meta = {**(companion.meta or {}),
                      "mathema.companion_of": parent,
                      "mathema.family": FLOAT_FAMILY}
    out.append(companion)


def _lemma_conjuncts(lemmas: list, cj, cj_domain: dict) -> list:
    """Intent:
        The relations a set of discharged lemmas contribute to the
        proof of the claim that rests on them.

    Notes:
        A proven lemma is a true statement, so assuming it is plain
        modus ponens, but only where it was established. A lemma
        proven over `x in [0,10]` says nothing about `x = -3`, so
        contributing its relation to a claim quantified more widely
        would be unsound.

        The guard is deliberately strict: every parameter the lemma
        bounds must be bounded identically here. Equality needs no
        subset reasoning to be obviously right, and a sibling claim on
        the same function almost always shares its domain. A lemma
        whose region does not line up still gates and still caps; it
        simply does not lend its content.
    """
    contributed = []
    for lemma in lemmas:
        if not lemma.rhs or lemma.relation not in _ASSUMING_RELATIONS:
            continue
        if any(cj_domain.get(name) != bound
               for name, bound in (lemma.domain or {}).items()):
            continue
        for lhs, relation, rhs in (list(lemma.links or ())
                                   or [(lemma.lhs, lemma.relation,
                                        lemma.rhs)]):
            parsed = _parse_assuming_relation(f"{lhs} {relation} {rhs}")
            if parsed is not None:
                contributed.append(parsed)
    return contributed


def _premise_refs(cj) -> list:
    """Every sibling claim a verdict premise names (`assuming X holds
    and Y is proven`). Only this form is order-dependent, a borrowed
    relation (`assuming real_roots`) reads the sibling's *statement*,
    which is available whatever order the batch runs in."""
    clause = getattr(cj, "assuming", "") or ""
    if not clause:
        return []
    from .grammar import _ASSUMING_PREFIX
    body = _ASSUMING_PREFIX.sub("", clause).strip()
    names = []
    for part in _split_top_and(body):
        matched = _ASSUMING_VERDICT.match(part.strip())
        if matched is not None:
            names.append(matched.group(1))
    return names


def _adjudication_order(conjectures: list) -> tuple[list, set]:
    """Intent:
        `(order, in_cycle)`, the conjectures arranged so a claim's
        prerequisites are adjudicated before it, and the names caught
        in a premise cycle.

    Notes:
        A batch's declaration order is the author's, not a dependency
        statement: requiring a prerequisite to be written first made a
        forward reference skip for a reason that had nothing to do with
        the claim. Resolution is by name, and a name that appears twice
        cannot be resolved to one claim, so duplicates are left in
        place for the caller to reject rather than silently binding to
        the first.

        Anything not in a cycle keeps its declared position relative to
        its peers, a stable sort, so output order only moves where a
        dependency actually demanded it.
    """
    by_name: dict = {}
    for cj in conjectures:
        by_name.setdefault(cj.name, []).append(cj)
    unique = {name: rows[0] for name, rows in by_name.items() if len(rows) == 1}

    order: list = []
    placed: set = set()
    visiting: set = set()
    in_cycle: set = set()

    def visit(cj) -> None:
        if id(cj) in placed:
            return
        if id(cj) in visiting:
            in_cycle.add(cj.name)
            return
        visiting.add(id(cj))
        for ref in _premise_refs(cj):
            prerequisite = unique.get(ref)
            if prerequisite is None or prerequisite is cj:
                continue
            visit(prerequisite)
            if prerequisite.name in in_cycle:
                in_cycle.add(cj.name)
        visiting.discard(id(cj))
        placed.add(id(cj))
        order.append(cj)

    for cj in conjectures:
        visit(cj)
    return order, in_cycle


def _resolve_matrix_sugar(cj: "Conjecture", fn_matrix_names: frozenset) -> "Conjecture":
    """Apply the type-aware matrix sugar to an already-built claim using
    the names the function's signature declares to be matrices, unioned
    with the claim's own declared matrix domain. A claim built without
    the signature in view (a bare `claim("|A| == 1")` handed to
    `check_conjectures`, whose `A` is a matrix only by its parameter
    marker) is resolved here, at the one place the function is always
    known. Returns `cj` unchanged when nothing is a matrix or no sugar
    was present."""
    import dataclasses

    mats = frozenset(fn_matrix_names) | linalg.declared_matrix_names(cj.domain)
    if not mats:
        return cj
    links = cj.links
    if cj.raw and "|" in blank_strings(cj.raw) \
            and cj.relation not in ("raises",):
        # bars around a matrix fold to its determinant as the text is
        # read, so the text is read again knowing the signature's
        # matrices
        try:
            again = claim(cj.raw, name=cj.name, route=cj.route,
                          grammar=cj.grammar, matrix_names=mats)
        except InvalidConjecture:
            again = cj
        lhs, rhs, links = again.lhs, again.rhs, again.links
    else:
        lhs = linalg.apply_matrix_sugar(cj.lhs, mats)
        rhs = linalg.apply_matrix_sugar(cj.rhs, mats) if cj.rhs else cj.rhs
    if lhs == cj.lhs and rhs == cj.rhs:
        return cj
    grammar = cj.grammar
    if grammar == GRAMMAR and linalg.mentions_matrix_ops(lhs, rhs):
        grammar = f"{GRAMMAR}/linalg"
    return dataclasses.replace(cj, lhs=lhs, rhs=rhs, links=links,
                               grammar=grammar)


def _effective_facts(fn, facts=None):
    """Intent:
        The facts to adjudicate `fn` under: the caller's when given,
        else the callable's own injected `__mathema_facts__` (how a
        foreign proxy states its real parameters and kinds without a
        Python body to read), else analysis of its source. Every
        entry that meets a callable, including a `funcs=`-bound one,
        resolves facts through here so the injection seam holds at
        each of them.

    Notes:
        The injected value is recognized by type name rather than
        isinstance so this stays import-cycle-free with analysis.
    """
    if facts is not None:
        return facts
    injected = getattr(fn, "__mathema_facts__", None)
    if type(injected).__name__ == "Facts":
        return injected
    return analyze_source(fn)


def _receiver_params_bound(fn, facts, conjectures):
    """Intent:
        The facts of a library method read as a function of its
        receiver (`runtime_types.receiver_form`), with each positional
        parameter that has a default (`lower=None` of
        `pandas.Series.clip`) and that some claim binds in its domain
        added to the parameters, in signature order, so that claim
        samples it and passes it. Any other function's facts are
        returned as they are.
    """
    import dataclasses
    if getattr(fn, "__mathema_receiver_params__", None) is None:
        return facts
    try:
        sig = callable_signature(fn).parameters
    except (TypeError, ValueError):
        return facts
    bound = {name for cj in conjectures
             for name in (getattr(cj, "domain", None) or {})}
    extra = {name for name, param in sig.items()
             if name in bound and name not in facts.params
             and param.kind in (param.POSITIONAL_ONLY,
                                param.POSITIONAL_OR_KEYWORD)}
    if not extra:
        return facts
    params = [name for name in sig
              if name in extra or name in facts.params]
    params += [name for name in facts.params if name not in params]
    kinds = {**facts.param_kinds, **{name: "unknown" for name in extra}}
    return dataclasses.replace(facts, params=params, param_kinds=kinds)


@quiet_while_probing
def check_conjectures(fn, conjectures: list[Conjecture],
                      domain: dict | None = None, trials: int | None = None,
                      trials_downscale: float | None = None, facts=None,
                      extensive: bool = False,
                      known_premises: dict | None = None,
                      float_companions: bool = False,
                      pseudo_infinity=None,
                      trials_scale: float | None = None) -> list[Probe]:
    """Adjudicate proposed claims against the live function.

    Throughout, bars around one of the matrices `fn`'s signature
    declares read as its determinant, and the `abs` of such a matrix
    renders with its call spelling (`grammar.bars_over_matrices`).

    `trials` omitted (`None`) uses the same structural-risk-based
    adaptive budget `probe()`'s own laws always have
    (`probing._starting_budget`), a claim about a structurally
    riskier function gets more trials, the same signal either way,
    since a claim is adjudicated by the exact same shared sampling
    setup (`probing._prepare_sampling`) `probe()`'s remaining
    structural checks use, computed lazily, at most once per call,
    the first time some claim actually reaches a probe-needing
    attempt. A batch of route="derive" claims whose proofs all decide
    never triggers it at all (an UNDECIDED derive claim now falls back
    to probing, empirical evidence supersedes an unknown, and pays
    for the setup like any probe claim). An explicit `trials=` always
    wins.

    `trials_scale` is the same dev-loop knob probe() takes, clamped to
    (0, 1] (shrinks only) and floored the same way (never below
    `_RiskPolicy.min_trials_floor_when_scaled` or `len(_SPECIALS)`, see
    probe()'s own docstring for why), so a single `--trials-scale` flag
    turns down every probe-route check in one call's worth of claims at
    once, built-in laws and author-stated conjectures alike.

    `extensive` reaches a route="derive" claim's own case-split
    fallback (`symbolic._prove.try_prove`), widening its wall-clock cap
    when an ordinary proof attempt comes back undecided, and also
    widens the critical-point analysis behind a probe-route claim's own
    sampling the same way it does for `probe()` (see
    `probing._prepare_sampling`). Default `False`, same as `probe()`'s
    own `extensive`.

    `float_companions=True` makes every claim the derive route proves
    (route "derive" or "best") spawn its computation claim,
    `<name>[float]`, emitted directly after it: a derive `proven` is
    the mathematics in exact arithmetic, and the companion is the same
    relation executed against the real code in float (see
    `gates._float_companion`). A claim authored with route
    `derive:math_only` adjudicates as a derive claim and spawns none,
    which its proof's meta states. `check()`, and so every CLI and
    store path, asks for companions; the default here keeps the
    adjudicator at one probe per claim.

    Returns one Probe per conjecture (plus any float companions): holds
    (n=…) / falsified (with the counterexample) / skipped (invalid law,
    nothing evaluable, or a different grammar entirely, see the
    `grammar` check below, tagged in `meta["mathema.foreign_grammar"]`
    so a caller can tell the two kinds of skip apart), each noting who
    proposed it.

    `pseudo_infinity` is the function level of the operational
    infinity (a claims-file entry's `pseudo_infinity:`, or
    `check(fn, pseudo_infinity=)`). Each claim's computation runs to
    the value resolved claim > function > `MATHEMA_PSEUDO_INFINITY`
    (`records.resolve_pseudo_infinity`, read once per call), else to the
    number representation's maximum; the derive route never reads it.
    Where the resolved value bounds an unbounded direction of a claim's
    effective domain, the claim's rows carry it with its level in
    `meta["mathema.pseudo_infinity"]`, and its computation rows show it
    as a `let` in front of their `condition` (P8).

    The bundled library claims (`compendium.ensure_bundled`) are
    applied before anything is adjudicated, unless a project layer is
    already installed.

    Raises:
        InvalidDomain: a function-level or `MATHEMA_PSEUDO_INFINITY`
            value that `let |inf| be` would refuse.
    """
    from .probing import resolve_trials_downscale
    trials_scale = resolve_trials_downscale(trials_downscale, trials_scale)
    from .types import matrix_param_names
    try:
        fn_mats = matrix_param_names(fn)
    except Exception:
        fn_mats = frozenset()
    try:
        facts = _effective_facts(fn, facts)
        runtime_mats = frozenset(p for p, k in facts.param_kinds.items()
                                 if k == "mat")
    except Exception:
        runtime_mats = frozenset()
    # the signature's matrices read the bars as determinants; those and
    # the matrix runtime types also render as matrices, their products
    # in written order
    # a policy claim is decided on the calls the other claims make, so
    # it is adjudicated after them
    built = [claim(c) if isinstance(c, str) else c for c in conjectures]
    for c in built:
        # a name bound to the function under test is f: nothing to `let`
        funcs = getattr(c, "funcs", None) or {}
        mine = {n for n, v in funcs.items() if v != n and _is_under_test(v, fn)}
        if mine:
            c.under_test = c.under_test | mine
    stated = [c for c in built if getattr(c, "relation", None) == "policy"]
    # the function's gates read every policy row, so they come last
    gates = [c for c in built if _policy_gate(c, fn, facts)]
    scalar_empty = [c for c in built if _empty_on_a_scalar(c, fn, facts)]
    values = [c for c in built if getattr(c, "relation", None) != "policy"
              and c not in gates and c not in scalar_empty]
    from ._empty_input import STATED
    # the claims checked here state the empty policy their value claims
    # read; a nested check (a chain's links) keeps the outer ones too
    stated_token = STATED.set((*STATED.get(), *built))
    try:
        return _check_built(fn, built, values, stated, gates, scalar_empty,
                            fn_mats, runtime_mats, domain, trials,
                            trials_scale, facts, extensive, known_premises,
                            float_companions, pseudo_infinity)
    finally:
        STATED.reset(stated_token)


def _check_built(fn, built, values, stated, gates, scalar_empty, fn_mats,
                 runtime_mats, domain, trials, trials_scale, facts,
                 extensive, known_premises, float_companions,
                 pseudo_infinity):
    """Intent:
        `check_conjectures`' adjudication of the built claims: the
        value claims, then the stated policy rows, then the gates.
    """
    from . import policy as _policy
    from .grammar import _BAR_MATRICES, bars_over_matrices, matrices_in_view
    with bars_over_matrices(fn_mats | _BAR_MATRICES.get()), \
            matrices_in_view(fn_mats | runtime_mats), _policy.batch(), \
            _policy.exceptions_of(fn):
        out = _check_conjectures(
            fn, values, domain=domain, trials=trials,
            trials_scale=trials_scale, facts=facts, extensive=extensive,
            known_premises=known_premises,
            float_companions=float_companions,
            pseudo_infinity=pseudo_infinity) if values else []
        for p in out:
            _policy.note_draws(p.name, p.n,
                               ((p.meta or {}).get("mathema.missing") or {}).get("origin"))
        if stated and facts is None:
            from . import analyze as _analyze
            facts = _analyze(fn)
        if stated:
            derived = _policy.guard_policies(facts)
            clash = _policy.contradicting_policies(
                [_policy.policy_text(_policy.parse_policy(
                    (f"{c.assuming}, " if c.assuming else "") + f"{c.lhs} {c.rhs}".strip()))
                 for c in stated])
            if clash:
                from .records import statement_text as policy_statement_text

                def policy_statement(c):
                    return policy_statement_text("policy", c.lhs, c.rhs)
                for cj in stated:
                    out.append(Probe(cj.name, policy_statement(cj), "skipped:misspecified",
                                     route=None, note=clash,
                                     meta={"mathema.invalid_conjecture": True,
                                           "mathema.surface": cj.source}))
                stated = []
            for cj in stated:
                row = _policy.adjudicate(cj, fn, facts, domain or {}, derived)
                row.grammar = cj.grammar
                row.meta = {**(row.meta or {}), **(cj.meta or {})}
                row.meta.setdefault("mathema.surface", cj.source)
                _stamp_defaults(row, fn, cj)
                out.append(row)
        for cj in scalar_empty:
            out.append(Probe(cj.name, statement_text(cj.relation, cj.lhs, cj.rhs),
                             "skipped:misspecified", route=None,
                             note=f"{cj.lhs} is a scalar; empty applies to a container",
                             meta={"mathema.invalid_conjecture": True,
                                   "mathema.surface": cj.source}))
        if gates:
            facts = facts if facts is not None else _effective_facts(fn, None)
            guards = _policy.guard_policies(facts)
            stated_rows = [p for p in out if (p.meta or {}).get("mathema.policy")]
            for cj in gates:
                row = _policy.safety_gate(cj, fn, facts, domain or {}, stated_rows,
                                          guards)
                row.grammar = cj.grammar
                row.meta = {**(row.meta or {}), **(cj.meta or {})}
                row.meta.setdefault("mathema.surface", cj.source)
                _stamp_defaults(row, fn, cj)
                out.append(row)
        witness = _policy.unrepeated_witness(_policy.active_batch())
        if witness:
            out = [_unrepeatable(p, witness) if p.name == "is_deterministic"
                   and p.verdict != "falsified" else p for p in out]
        for p in out:
            # a next step is the note's last line, its command last
            steps = (p.meta or {}).get("mathema.next_steps")
            if steps and not (p.note or "").endswith(steps[-1]):
                p.note = "\n".join([p.note or "", *steps]).lstrip("\n")
        return out


def _unrepeatable(row, witness: str):
    """`row`, an is_deterministic row, falsified by a call the check made
    twice with two answers; a proof it contradicts is said to be an
    engine defect."""
    from dataclasses import replace as _replace
    note = "the same call made twice gave two answers"
    if row.verdict == "proven":
        note += ("; this contradicts the proof above it, an engine defect worth "
                 "reporting")
    return _replace(row, verdict="falsified", route="probe", counterexample=witness,
                    note=note, sketch=row.sketch if row.verdict == "proven" else None)


def _stamp_defaults(row, fn, cj) -> None:
    """Records on a policy row or gate the values a library function's
    calls held its unsampled parameters at (`mathema.defaults`), as a
    value claim's row records them."""
    resolved = claim_defaults(fn, cj)
    if resolved:
        row.meta = {**(row.meta or {}), "mathema.defaults": resolved}


def _empty_on_a_scalar(cj, fn, facts) -> bool:
    """Whether a claim asks `is_empty_safe` of a scalar parameter, which
    has no slots to be empty."""
    if getattr(cj, "relation", None) != "is_empty_safe":
        return False
    try:
        facts = facts or _effective_facts(fn, None)
    except Exception:
        return False
    kind = facts.param_kinds.get(cj.lhs)
    return cj.lhs in facts.params and kind in ("scalar", "int")


def _is_under_test(candidate, fn) -> bool:
    """Whether a function a claim binds by name is the function under
    test itself."""
    for c in (candidate, getattr(candidate, "__wrapped__", None)):
        if c is None:
            continue
        if c is fn:
            return True
        if getattr(c, "__module__", None) == getattr(fn, "__module__", None) \
                and getattr(c, "__qualname__", None) == getattr(fn, "__qualname__", 0):
            return True
    return False


def _gate_premise_refusal(cj) -> "str | None":
    """Why `assuming is_missing_safe(f)` (or `is_absent_safe(f)`) is no
    premise, with what to write instead; None when the claim has none."""
    raw = re.sub(r"^\s*assuming\s+", "", (cj.assuming or "").strip())
    for part in _split_top_and(raw) if raw else ():
        gate = re.match(r"^\s*(is_missing_safe|is_absent_safe)\s*\(.*\)\s*$", part)
        if gate is None:
            continue
        param = next((p for p in (cj.domain or {}) if p.isidentifier()), "x")
        if gate.group(1) == "is_missing_safe":
            from ._missing_words import options
            return (f"assuming {part.strip()} is not a premise: a value claim is never "
                    f"judged where f returns a missing value, so the premise would "
                    f"change nothing.\n" + options([
                        f"to keep f from being called with a missing {param}, write "
                        f"in the domain: \\ {{missing}}",
                        f"to state what f does with one as its own claim (propagates, "
                        f"drops or raises), write, for example: missing(f, {param}) "
                        f"propagates"]))
        from ._missing_words import options
        return (f"assuming {part.strip()} is not a premise: a value claim is never "
                f"judged where f returns None, so the premise would change nothing."
                "\n" + options([
                    "to keep f from being called with None, write in the domain: "
                    "\\ {absent}",
                    f"to state what f does when {param} is None as its own claim, "
                    f"write, for example: absent(f, {param}) raises(TypeError)"]))
    return None


def _policy_gate(cj, fn, facts) -> bool:
    """Whether a claim is one of the gates the policy rows decide:
    `is_missing_safe(f)`, `is_absent_safe(f)` or `is_absent_safe(x)`;
    a parameter's `is_missing_safe(x)` stays its family's."""
    relation = getattr(cj, "relation", None)
    if relation == "is_absent_safe":
        return True
    if relation != "is_missing_safe":
        return False
    try:
        params = (facts or _effective_facts(fn, None)).params
    except Exception:
        return False
    return cj.lhs not in params


def _approx_reading(cj) -> "str | None":
    """How the record reads a `~=` claim, or None for any other: "read
    as abs(f(x) - x) <= ε, ε = 1e-9 (the default)", ε the declared
    tolerance when there is one."""
    if cj.relation != "~=" or cj.links or not cj.lhs or not cj.rhs:
        return None
    eps, why = ((cj.tolerance, "declared") if cj.tolerance is not None
                else (1e-9, "the default"))
    mantissa, _, exponent = f"{eps:g}".partition("e")
    text = f"{mantissa}e{int(exponent)}" if exponent else mantissa
    rhs = cj.rhs.strip()
    try:
        node = ast.parse(rhs, mode="eval").body
        bare = isinstance(node, (ast.Name, ast.Call, ast.Constant,
                                 ast.Subscript, ast.Attribute))
    except SyntaxError:
        bare = False
    if not bare:
        rhs = f"({rhs})"
    return (f"read as abs({cj.lhs.strip()} - {rhs}) <= ε, ε = {text} "
            f"({why})")


def _check_conjectures(fn, conjectures: list[Conjecture],
                       domain: dict | None = None, trials: int | None = None,
                       trials_scale: float = 1.0, facts=None,
                       extensive: bool = False,
                       known_premises: dict | None = None,
                       float_companions: bool = False,
                       pseudo_infinity=None) -> list[Probe]:
    """Intent:
        `check_conjectures`' adjudication, under the bar reading it
        sets.
    """
    from .compendium import ensure_bundled
    from .records import resolve_pseudo_infinity
    ensure_bundled()
    # the function and project levels, validated before any claim runs
    # so a bad value refuses the whole call
    resolve_pseudo_infinity(None, pseudo_infinity)
    facts = _receiver_params_bound(fn, _effective_facts(fn, facts),
                                   conjectures)
    kinds = {p: facts.param_kinds.get(p, "unknown") for p in facts.params}
    # an enforce_domain() guard is the function's domain: a parameter the
    # caller's domain leaves open ranges over what the guard admits
    domain = {**(getattr(fn, "__mathema_enforced_domain__", None) or {}),
              **(domain or {})}
    # the exact same sampling setup probe()'s own remaining structural
    # checks use (seeded RNG, adaptive budget, critical-point hints),
    # computed at most once per call, from the function-level domain,
    # not re-derived per claim, matching probe()'s own established
    # precedent of one sampling decision for the whole call. Lazy,
    # behind _sampling(): a route="derive" claim never reaches the
    # generic probe loop or a family's probe:algorithmic route, so a
    # batch made entirely of those never pays for the critical-point
    # search (_points_for_probe, wall-clock capped but not free) on
    # behalf of a probe attempt that's never made.
    _sampling_cache: list = []

    def _sampling():
        if not _sampling_cache:
            _sampling_cache.append(
                _prepare_sampling(fn, facts, domain, trials, trials_scale, extensive))
        return _sampling_cache[0]

    out: list[Probe] = []

    def _stamped(probe, cj, canonical=True, written=None):
        # one statement, every surface: the row, the display, and the
        # store all carry the canonical ascii text, which re-parses to
        # this claim (sections, quantifier, premise and all). The
        # structured fields beside it are the same claim for machines.
        from .grammar import domain_bound_to_json
        from .spec import canonical_claim_text
        implied, implied_resolution = _implied_bindings(
            cj, fn, {p2: k for p2, k in kinds.items()
                     if p2 not in (cj.domain or {}) and p2 not in domain})
        if cj.domain or implied:
            # the record states each binding completed from the
            # function's annotations, whichever path produced the row,
            # and what a parameter the claim leaves unbound admits
            written = dict(written if written is not None else (cj.domain or {}))
            done = _complete_missing(cj, fn) if cj.domain else ({}, [], None, {})
            completed, resolution = done[0], {**implied_resolution, **done[3]}
            if completed:
                cj = _dc_replace(cj, domain=completed)
            admitted_now = _missing_record({**implied, **(cj.domain or {})})
            ran = (probe.meta or {}).get("mathema.missing") or {}
            if not admitted_now and (ran.get("returned") or ran.get("said")):
                # what f did at a missing input the parameters' own
                # bindings do not admit (a path's) is still said
                admitted_now = {"admitted": {}}
            if admitted_now:
                earlier = (probe.meta or {}).get("mathema.missing") or {}
                merged = {**admitted_now, **earlier,
                          "tried": {**admitted_now.get("tried", {}),
                                    **earlier.get("tried", {})}}
                if not merged["tried"]:
                    merged.pop("tried")
                means = _missing_means(merged.get("admitted") or {}, resolution or {})
                if means:
                    merged["means"] = means
                # who admitted each kind: the type alone, or the author
                origin = {}
                for p2, entry in (merged.get("admitted") or {}).items():
                    kinds_here = (["absent"] if entry.get("absent") else []) + \
                        (["missing"] if entry.get("missing") else [])
                    if kinds_here:
                        origin[p2] = {k: _missing_origin(p2, k, written, resolution or {})
                                      for k in kinds_here}
                if origin:
                    merged["origin"] = origin
                probe.meta = {**(probe.meta or {}), "mathema.missing": merged}
                told = _missing_told(merged, written, resolution or {}, fn)
                # the computation line runs the numbers; what f did at a
                # hole is the policy lines' to say
                computation = probe.name.startswith(f"{cj.name}[")
                if told and not computation and told not in (probe.note or "") \
                        and not (probe.meta or {}).get("mathema.missing_unknown"):
                    probe.note = f"{probe.note or ''}; {told}".lstrip("; ")
        reading = _approx_reading(cj)
        if reading and probe.name == cj.name \
                and reading not in (probe.note or ""):
            probe.note = f"{probe.note or ''}; {reading}".lstrip("; ")
        if canonical:
            # the renderer is total over everything claim() accepts, so
            # a failure here is a renderer bug worth a loud crash, never
            # a claim to quietly record under a different spelling; a
            # pin is written in the call
            cj = pins_into_calls(cj, fn)
            probe.statement = canonical_claim_text(cj)
        if cj.domain:
            probe.domain = {p2: domain_bound_to_json(b)
                            for p2, b in cj.domain.items()}
        probe.grammar = cj.grammar
        probe.tolerance = cj.tolerance
        languages = _language_meta({**domain, **(cj.domain or {})})
        if languages:
            # what every `L[...]` binding resolved to, on the record,
            # beside any entry a family wrote under the same key (its
            # `return`, say)
            earlier = (probe.meta or {}).get("mathema.language")
            merged = {**earlier, **languages} if isinstance(earlier, dict) else languages
            probe.meta = {**(probe.meta or {}), "mathema.language": merged}
        if cj.domain and not probe.condition:
            # every quantified row carries its region as the ONE
            # canonical rendered condition, real parameter names,
            # grammar-roundtrip guaranteed, human-readable. This is
            # what lets the verified layer repopulate a claim whose
            # declared entry was deleted, region intact (derive rows
            # already carry the proof's own quantifier clause).
            from .domain import render_domain
            # pinned ascii: a record's bytes must not depend on the
            # writer's global unicode preference, display re-renders
            probe.condition = "for " + ", ".join(
                f"{p2} in {render_domain(b, ascii_mode=True)}"
                for p2, b in cj.domain.items())
        resolved = claim_defaults(fn, cj)
        if resolved:
            # the values each library call passed that the claim did not
            # sample, stated in the record and the note
            probe.meta = {**(probe.meta or {}), "mathema.defaults": resolved}
            said = defaults_note(resolved)
            if said not in (probe.note or ""):
                probe.note = f"{probe.note or ''}; {said}".lstrip("; ")
        inherited = {p2: b for p2, b in domain.items()
                     if p2 not in (cj.domain or {})}
        if inherited:
            # the parent domain's share of the region this claim was
            # adjudicated over, stated beside the claim's own bindings
            from .domain import render_domain
            meta = dict(probe.meta or {})
            meta["mathema.parent_domain"] = "for " + ", ".join(
                f"{p2} in {render_domain(b, ascii_mode=True)}"
                for p2, b in sorted(inherited.items()))
            probe.meta = meta
        stamp_pinf = pseudo_infinity_stamp(cj, facts, domain)
        if stamp_pinf is not None:
            # the operational infinity bounds a direction of this
            # claim's domain: the value and its level are output (P7, P8)
            probe.meta = {**(probe.meta or {}),
                          "mathema.pseudo_infinity": stamp_pinf}
            probe.condition = pseudo_infinity_condition(
                cj, facts, domain, probe)
        if cj.meta:
            # declared meta (the spec's own extension object, e.g.
            # concepts) passes through under the probe's meta, the
            # probe's own keys winning
            probe.meta = {**cj.meta, **(probe.meta or {})}
            accepted = cj.meta.get("mathema.accepted_spelling")
            if accepted:
                said = (f"{accepted} is an accepted spelling of "
                        f"{families.current_family_name(accepted)}")
                if said not in (probe.note or ""):
                    probe.note = f"{probe.note or ''}; {said}".lstrip("; ")
        if probe.verdict != "falsified" and _working_domain_empty(
                fn, facts, cj, {**domain, **(cj.domain or {})}):
            # every input f admits is refused by its own guards: there is
            # nothing to judge, and no verdict over nothing
            probe.verdict = "unknown"
            probe.route = None
            probe.sketch = None
            probe.note = ("no valid domain: f's own guards refuse every "
                          "input its annotations and binding admit")
        working = _working_domain_record(fn, facts, cj,
                                         {**domain, **(cj.domain or {})})
        if working:
            probe.meta = {**(probe.meta or {}),
                          "mathema.working_domain": working}
            per_param = [f"{p} in {b}" for p, b in working.items()
                         if p != "guards"]
            if per_param:
                said = ("the working domain is " + ", ".join(per_param)
                        + (f": f's own guard raises where "
                           f"{' or '.join(working['guards'])}"
                           if working.get("guards") else
                           ": f's own guard rejects the rest"))
            else:
                said = (f"the working domain is the domain left by f's "
                        f"guards ({' or '.join(working.get('guards') or [])})")
            if said not in (probe.note or ""):
                probe.note = f"{probe.note or ''}; {said}".lstrip("; ")
        if cj.source:
            # always stamped, "user" included: with no provenance
            # prose in the note, meta is the one source channel
            meta = dict(probe.meta or {})
            meta.setdefault("mathema.surface", cj.source)
            probe.meta = meta
        from .runtime_types import strong_hints
        for said in strong_hints(facts):
            # a parameter used as a vector with no runtime type named:
            # the row says which runtime type to annotate
            if said not in (probe.note or ""):
                probe.note = f"{probe.note or ''}; {said}".lstrip("; ")
        for said in linalg.norm_notes(
                cj, _claim_array_ranks({**domain, **(cj.domain or {})},
                                       fn, facts)):
            # a bare `||x||` names the norm it resolved to, Euclidean
            # for a vector and Frobenius for a matrix
            if said not in (probe.note or ""):
                probe.note = f"{probe.note or ''}; {said}".lstrip("; ")
        _stamp_examine_route(probe, cj, fn, facts)
        warnings = _third_party_warnings(cj, fn)
        if warnings:
            probe.meta = {**(probe.meta or {}),
                          "mathema.let_warning": warnings}
            for said in warnings:
                if said not in (probe.note or ""):
                    probe.note = f"{probe.note or ''}; {said}".lstrip("; ")
        return probe

    from .types import matrix_param_names
    _fn_mats = matrix_param_names(fn)
    conjectures = [claim(c) if isinstance(c, str) else c for c in conjectures]
    conjectures = [_resolve_matrix_sugar(c, _fn_mats) for c in conjectures]
    # prerequisites first, whatever order they were written in; the
    # returned list is put back in declaration order at the end, so
    # ordering is an adjudication concern and never a visible one
    declared_order = {id(cj): i for i, cj in enumerate(conjectures)}
    ordered, premise_cycles = _adjudication_order(conjectures)
    duplicate_names = {name for name in
                       (cj.name for cj in conjectures)
                       if [c.name for c in conjectures].count(name) > 1}
    overflow_links = overflow_safe_links(conjectures)
    from .policy import _CLAIM as _policy_claim
    for cj in ordered:
        _policy_claim.set(cj.name)
        if overflow_links and not cj.overflow_safe \
                and "is_defined" in (region_row_kind(cj.name),
                                     cj.relation):
            cj = _dc_replace(cj, overflow_safe=overflow_links)
        if cj.resolved_pseudo_infinity is None:
            # the working copy carries the operational infinity that
            # applies to this claim's computation; a claim synthesized
            # from an outer one (a chain link, a roll-up child) arrives
            # already resolved
            cj = _dc_replace(cj, resolved_pseudo_infinity=
                             resolve_pseudo_infinity(cj.pseudo_infinity,
                                                     pseudo_infinity))
        math_only = cj.route == MATH_ONLY_ROUTE
        if math_only:
            # the opt-out adjudicates exactly as a derive claim; only the
            # companion it would spawn is withheld
            cj = _dc_replace(cj, route="derive")
        gate_premise = _gate_premise_refusal(cj)
        if cj.links and gate_premise is not None:
            # a gate written as a premise is refused once for the claim,
            # never once per link
            out.append(_stamped(Probe(cj.name, statement_text(cj.relation, cj.lhs, cj.rhs),
                                      "skipped:misspecified", route=None,
                                      note=gate_premise), cj))
            continue
        if cj.links and region_row_kind(cj.name) is None:
            # a chained comparison is the conjunction of its links: run
            # each link through the full ordinary adjudication (same
            # domain/funcs/assuming/route) and fold, so no proof path is
            # duplicated; the exact combination rule tuple claims use
            chained, companion = _adjudicate_chain(
                cj, fn, facts, domain, trials, trials_scale, extensive,
                float_companions=(float_companions and not math_only
                                  and cj.route in ("derive", "best")))
            if math_only and chained.verdict == "proven":
                chained.meta = {**(chained.meta or {}),
                                "mathema.float_companion":
                                    "none (derive:math_only)"}
            # the links bound the chain's call names; one bound to the
            # function under test is f, with nothing to `let`
            cj.under_test = cj.under_test | {n for n, v in cj.funcs.items()
                                             if v != n and _is_under_test(v, fn)}
            lines = (chained.meta or {}).pop("mathema.chain_lines", None) or []
            out.append(_stamped(chained, cj))
            if companion is not None:
                _emit_companion(out, _stamped(companion, cj), cj.name)
            out.extend(lines)
            continue
        if (cj.relation in routes.safety_predicates() and cj.lhs == "f"
                and "f" not in facts.params
                and not getattr(families.families().get(cj.relation),
                                "whole_function", False)):
            # the function-wide spelling: the predicate over f is the
            # conjunction of the predicate over every numeric parameter
            # (a family that examines the whole function at once, the
            # computation roll-up, adjudicates `f` itself below)
            out.append(_stamped(_adjudicate_function_wide_safety(
                cj, fn, facts, domain, trials, trials_scale, extensive), cj))
            continue
        statement = statement_text(cj.relation, cj.lhs, cj.rhs)
        if cj.negated:
            statement = f"not {statement.strip()}"
        # no provenance prose: the source rides
        # meta["mathema.surface"] (and the compact rows' own
        # source field), and verdicts are always mathema's own, the
        # note carries only claim-specific substance
        note = _bind_scope_functions(cj, fn).lstrip("; ")
        reach = _system_reach(cj)
        if reach is not None:
            out.append(_stamped(Probe(
                cj.name, statement, "skipped:misspecified", route=None,
                note=f"{note}; {reach}".lstrip("; ")), cj))
            continue
        # an explicit route that can't evaluate this claim's forms
        # (probe asked to differentiate/integrate, ...) skips up front,
        # with the reason in the sketch, never mis-adjudicated or
        # reported as an "unresolved bound function"
        unsupported = routes.unsupported_forms(cj.route, cj)
        if unsupported:
            out.append(_stamped(Probe(
                cj.name, statement, "skipped", route=None, note=note,
                sketch=f"not implemented on the {cj.route} route: "
                       f"{', '.join(unsupported)}, the {cj.route} route's "
                       f"vocabulary does not evaluate these forms"), cj))
            continue
        shadowed = _shadowed_constants(cj.lhs, cj.rhs, set(facts.params))
        if shadowed:
            note += (f"; {', '.join(shadowed)} read as the parameter"
                     f"{'s' if len(shadowed) > 1 else ''}, not the math "
                     f"constant, "
                     + ", ".join(_CONSTANT_SPELLINGS[c] for c in shadowed))
        assumption = _interpret_assumption(cj, conjectures)
        if isinstance(assumption, Probe):
            out.append(_stamped(assumption, cj))
            continue
        verdict_cap = None
        defined_mode = False
        discharged: list = []
        premise_structures: dict = {}
        if assumption is not None and assumption[0] == "structure":
            # a matrix-structure premise narrows synthesis (and, on the
            # derive route, becomes a sympy assumption); it is not a
            # region, so it does not touch the domain box
            _kind, display, premise_structures = assumption
            statement = f"assuming {display}, {statement}"
            cj = _dc_replace(cj, assuming=f"assuming {display}")
            assumption = None
        if assumption is not None and assumption[0] in ("defined",
                                                         "defined-pinned"):
            expansion = _defined_expansion(fn, facts, cj)
            if assumption[0] == "defined-pinned":
                pinned = assumption[2]
                if _region_texts_agree(pinned, expansion):
                    # the pin still describes the code: keep its exact
                    # spelling, so the record stays byte-stable
                    expansion = pinned
                else:
                    note += (f"; the pinned definedness region "
                             f"({pinned}) no longer matches the code; "
                             f"recomputed as "
                             f"({expansion or 'no raise regions'})")
            premise = (f"assuming f is defined --> {expansion}"
                       if expansion else "assuming f is defined")
            statement = f"{premise}, {statement}"
            cj = _dc_replace(cj, assuming=premise)
            assumption = None
            defined_mode = True
        elif assumption is not None and assumption[0] == "verdict":
            _kind, display, refs, lemmas = assumption
            statement = f"assuming {display}, {statement}"
            cj = _dc_replace(cj, assuming=f"assuming {display}")
            ref_name = refs[0][0]
            if cj.name in premise_cycles:
                out.append(_stamped(Probe(
                    cj.name, statement, "skipped", route=None,
                    note=f"{note}; premise cycle: {cj.name} and "
                         f"{ref_name} rest on each other, so neither can "
                         f"be established first",
                    meta={"mathema.premise": "dependency-cycle"}), cj))
                continue
            if ref_name in duplicate_names:
                out.append(_stamped(Probe(
                    cj.name, statement, "unknown", route=None,
                    note=f"{note}; prerequisite {ref_name!r} names more "
                         f"than one claim in this batch, so there is no "
                         f"one verdict to rest on; give them distinct "
                         f"names",
                    meta={"mathema.premise": "ambiguous-reference"}), cj))
                continue
            in_batch = {name for name, _ in refs
                        if any(p.name == name for p in out)}
            external: dict = {}
            hints: list = []
            ambiguous: list = []
            for name, _wanted in refs:
                if name in in_batch:
                    continue
                info = (known_premises or {}).get(name)
                if isinstance(info, str):
                    hints.append(info)
                elif isinstance(info, dict) and info.get("verdict"):
                    # resolved outside the batch (a verified row under
                    # another key, or an accepted library-stub row):
                    # the premise is satisfied at that evidence level
                    external[name] = info
                elif isinstance(info, dict) and info.get("ambiguous"):
                    ambiguous.append((name, info["ambiguous"]))
                elif isinstance(info, dict) and info.get("hint"):
                    hints.append(info["hint"])
            if ambiguous:
                name, keys = ambiguous[0]
                out.append(_stamped(Probe(
                    cj.name, statement, "unknown", route=None,
                    note=f"{note}; prerequisite {name!r} matches claims "
                         f"under {', '.join(keys)}; qualify it "
                         f"({keys[0]}.{name})",
                    meta={"mathema.premise": "ambiguous-reference"}), cj))
                continue
            missing = [name for name, _ in refs
                       if name not in in_batch and name not in external]
            if missing:
                named = ", ".join(repr(m) for m in missing)
                hint = ("; " + "; ".join(hints)) if hints else ""
                out.append(_stamped(Probe(
                    cj.name, statement, "unknown", route=None,
                    note=f"{note}; prerequisite {named} is not a claim "
                         f"in this batch, nothing to rest this claim on"
                         f"{hint}",
                    meta={"mathema.premise": "missing-prerequisite"}), cj))
                continue
            resolved = [(name, wanted,
                         next(p for p in out if p.name == name))
                        for name, wanted in refs if name in in_batch]
            resolved += [
                (name, wanted,
                 Probe(name, name, external[name]["verdict"],
                       note=external[name].get("provenance", "")))
                for name, wanted in refs if name in external]
            unmet = [(name, wanted, ref) for name, wanted, ref in resolved
                     if not (ref.verdict == "proven" if wanted == "proven"
                             else ref.verdict in ("proven", "holds"))]
            if unmet:
                name, wanted, ref = unmet[0]
                out.append(_stamped(Probe(
                    cj.name, statement, "unknown", route=None,
                    note=f"{note}; prerequisite {name} is "
                         f"{ref.verdict}, not {wanted}, nothing to rest "
                         f"this claim on",
                    meta={"mathema.premise": "unmet-prerequisite"}), cj))
                continue
            # the weakest lemma bounds the conclusion; an external
            # premise is named by its provenance so the cap says whose
            # word it rests on
            empirical = [
                (external[name].get("provenance", name)
                 if name in external else name)
                for name, _, ref in resolved if ref.verdict == "holds"]
            if empirical:
                verdict_cap = ("holds", ", ".join(empirical))
            discharged = lemmas
            assumption = None
        elif assumption is not None:
            statement = f"assuming {assumption[1]}, {statement}"
            cj = _dc_replace(cj, assuming=f"assuming {assumption[1]}")
            if len(assumption) > 3:
                # structure conjuncts beside the relations
                premise_structures = assumption[3]
        validated = _validate_claim(cj, statement, note, facts, domain, fn=fn)
        if isinstance(validated, Probe):
            # a claim in another grammar is still the claim written,
            # `let` sections and bound functions included, so its row
            # keeps the canonical text and re-reads as the same claim;
            # any other rejected claim has no canonical form (it was
            # never a claim), so its record keeps what was written
            # a skipped claim's record states it whole, quantifier
            # included, so it reads back as the claim that was written;
            # text that was never a claim (an unknown relation) keeps
            # what was written
            out.append(_stamped(validated, cj, canonical=_renders(cj)))
            continue
        ctx = validated
        written_domain = {p: b for p, b in (ctx.record_domain or {}).items()
                          if p not in ctx.implied}
        cj_record = _dc_replace(cj, domain=written_domain) if written_domain else cj
        if assumption is not None:
            ctx.assumption = assumption[2]
            ctx.assumption_display = assumption[1]
        elif discharged:
            # what the lemmas establish is available to this proof, not
            # just the fact that they were established
            lent = _lemma_conjuncts(discharged, cj, ctx.cj_domain)
            if lent:
                ctx.assumption = lent
                ctx.assumption_display = ", ".join(
                    f"{r.lhs} {r.relation} {r.rhs}" for r in lent)
        ctx.assume_defined = defined_mode
        ctx.exclude_own_guards = (not defined_mode and
                                  _reads_working_domain(fn, facts, cj, domain))
        ctx.premise_structures = premise_structures
        ctx.companion_mode = (
            "math_only" if math_only else
            "spawn" if float_companions and cj.route in ("derive", "best")
            else None)
        ctx.companion_budget = cj.trials if cj.trials is not None else trials
        def stamp(probe, _cap=None):
            # `condition` is rendered text that gets read back,
            # docsync compares a verified row by feeding
            # f"{condition}, {statement}" through the claim grammar,
            # so it may only ever hold what the grammar accepts. An
            # assumed region reaches it the way a declared one does:
            # the premise narrows the quantified interval itself
            # (symbolic._prove._tighten_domain_by_assumption), and the
            # premise text rides in the statement.
            probe = _stamped(probe, cj_record, written=cj.domain or {})
            if _cap and classify_verdict(probe.verdict) == "proven":
                # a claim can be no better established than what it
                # rests on: resting a proof on a lemma that is itself
                # only empirically supported makes this evidence too,
                # whichever route reached it. Stated in the note and in
                # meta, never applied silently.
                capped_to, ref_name = _cap
                probe.verdict = capped_to
                probe.note = (f"{probe.note}; rests on {ref_name}, whose own "
                              f"evidence is empirical (holds), capped to "
                              f"{capped_to}").lstrip("; ")
                probe.meta = {**(probe.meta or {}),
                              "mathema.capped_by": ref_name}
            return probe
        if cj.route not in ("derive", "best", "probe", "examine"):
            out.append(_stamped(Probe(
                cj.name, statement, "skipped", route=None,
                note=f"unknown route {cj.route!r}"), cj_record))
            continue
        _kept, call_pins, pin_problem = call_defaults(fn, cj)
        if pin_problem is not None:
            out.append(stamp(Probe(
                cj.name, statement, "skipped:misspecified", route=None,
                note=f"{ctx.note}; {pin_problem}")))
            continue
        # the family is resolved for every concrete route: the derive
        # stage reads its derive half, and the probe stage reads its
        # probe:algorithmic half, a plain route="probe" claim on a
        # family-owned name reaches the family's own empirical
        # technique rather than the generic sampling loop
        ctx.family = _claim_family(cj, fn, facts)
        emptied = _empty_premise_parameter(ctx, facts)
        clash = None if emptied is not None else _fixed_dim_clash(ctx)
        if clash is not None:
            # a literal dimension in the binding and a premise on the same
            # dimension that refuses it: the same vacuous premise, naming
            # both
            emptied, premise_text, axis_words = clash
            out.append(stamp(Probe(
                cj.name, statement, "skipped", route=None,
                note=f"{ctx.note}; the premise ({premise_text}) admits no "
                     f"value of {emptied} in its declared domain "
                     f"{_shapes.domain_text(ctx.cj_domain[emptied])}: "
                     f"{emptied} {axis_words} by its binding, so the "
                     f"claim quantifies over nothing and is vacuous; "
                     f"state a premise the binding can satisfy",
                meta={"mathema.empty_premise": emptied})))
            continue
        if emptied is not None:
            out.append(stamp(Probe(
                cj.name, statement, "skipped", route=None,
                note=f"{ctx.note}; the premise ({ctx.assumption_display}) "
                     f"admits no value of {emptied} in its declared "
                     f"domain, so the claim quantifies over nothing and "
                     f"is vacuous; state a premise the domain can "
                     f"satisfy",
                meta={"mathema.empty_premise": emptied})))
            continue
        if cj.relation == "=:=":
            # function equivalence has its own ladder (form hash ->
            # symbolic difference -> code-vs-code sampling); neither
            # generic stage applies
            out.append(stamp(_adjudicate_equivalence(ctx, fn, facts)))
            continue
        if getattr(ctx.family, "examined_only", False) and not (
                cj.relation == families.claim_base_name(cj.name)
                or (cj.relation == "==" and (cj.lhs or "").replace(" ", "")
                    == (cj.rhs or "").replace(" ", ""))):
            # a claim that shares the family's name and states something
            # else is an ordinary claim
            ctx.family = None
        if getattr(ctx.family, "examined_only", False):
            # decided by examining the source, on every route: nothing
            # about this family runs the function
            out.append(stamp(_adjudicate_examined(ctx, fn, facts),
                             _cap=verdict_cap))
            continue
        from .probing import LanguageDrawFailed
        try:
            if call_pins:
                # the derive route reads the call the claim writes, never a
                # pinned parameter it does not pass, so a pinned claim is
                # adjudicated by execution
                ctx.derive_undecided = Probe(
                    cj.name, statement, "unknown", route="derive",
                    note=f"{ctx.note}; the derive route does not model the "
                         f"pinned parameter(s) {', '.join(sorted(call_pins))}",
                    meta={"mathema.derive_status": "unsupported"})
            elif cj.route in ("derive", "best", "examine"):
                # route="best" IS the cascade: its derive attempt engages
                # the extensive ladder inside the same try_prove call (the
                # fast attempt runs once; the ladder only starts where it
                # left off), so nothing is ever re-derived on the way down.
                # "examine" cascades the same way: structural half first,
                # empirical half when structure can't establish the fact.
                derived = _adjudicate_derive(
                    ctx, fn, facts,
                    extensive or cj.route in ("best", "examine"))
                if derived is not None:
                    derived, lines = _with_empty_input_lines(
                        derived, ctx, fn, facts, float_companions,
                        conjectures)
                    out.append(stamp(derived, _cap=verdict_cap))
                    if ctx.companion is not None:
                        _emit_companion(out, _stamped(ctx.companion, cj_record,
                                                      written=cj.domain or {}),
                                        derived.name)
                    if float_companions:
                        out.extend(_stamped(line, cj, canonical=False) for line in lines)
                    continue
                # route == "best" and the derive stage couldn't settle it:
                # fall through to the probe stage, same as an ordinary
                # probe claim.
            probed = _arbitrate_empirical_fallback(
                _adjudicate_probe(ctx, fn, facts, kinds, _sampling), ctx)
            if ctx.companion is None and probed.verdict == "holds" \
                    and _stands_in_for_derive(ctx):
                # the probe stood in for derive on the mathematics: the
                # computation line runs the corners a proof's companion
                # would, and is kept where it falsifies (the stand-in's
                # own draws already say where the computation held)
                _spawn_float_companion(
                    ctx, probed, fn, facts, _bound_funcs_of(cj),
                    [(a.lhs, a.relation, a.rhs) for a in ctx.assumption or ()])
                if ctx.companion is None \
                        or ctx.companion.verdict != "falsified":
                    ctx.companion = None
                    probed.meta.pop("mathema.float_companion", None)
            if ctx.guard_refused:
                refused = (f"{ctx.guard_refused} draw"
                           f"{'s' if ctx.guard_refused != 1 else ''} refused "
                           f"by f's own guard, outside the working domain")
                probed.note = f"{probed.note or ''}; {refused}".lstrip("; ")
                probed.meta = {**(probed.meta or {}),
                               "mathema.guard_refused": ctx.guard_refused}
            if ctx.path_no_value:
                outside = (f"{ctx.path_no_value} draw"
                           f"{'s' if ctx.path_no_value != 1 else ''} outside "
                           f"the binding: the path has no value")
                probed.note = f"{probed.note or ''}; {outside}".lstrip("; ")
                probed.meta = {**(probed.meta or {}),
                               "mathema.path_no_value": ctx.path_no_value}
            probed, lines = _with_empty_input_lines(probed, ctx, fn, facts,
                                                    float_companions,
                                                    conjectures)
            out.append(stamp(probed, _cap=verdict_cap))
            if ctx.companion is not None:
                _emit_companion(out, _stamped(ctx.companion, cj_record,
                                              written=cj.domain or {}),
                                probed.name)
            if float_companions:
                out.extend(_stamped(line, cj, canonical=False) for line in lines)
        except LanguageDrawFailed as e:
            # the language produced no member to evaluate the claim at
            out.append(stamp(Probe(
                cj.name, statement, "skipped", route=None,
                note=f"{ctx.note}; {e}",
                meta={"mathema.probe_gap": "input-synthesis"})))
    out.sort(key=lambda p: _emit_position(p, conjectures, declared_order))
    return out


# parameter kinds whose values run along a real direction
_DIRECTION_KINDS = frozenset({"scalar", "unknown", "int", *SEQUENCE_KINDS})


def pseudo_infinity_stamp(cj, facts, parent_domain: "dict | None") -> "dict | None":
    """Intent:
        The `mathema.pseudo_infinity` meta a claim's rows carry: the
        resolved operational infinity (`records.operational_infinity`)
        as `{"value", "source"}`, when it bounds an unbounded direction
        of the claim's effective domain (the parent domain overlaid by
        the claim's own bindings, over the function's numeric
        parameters and the claim's free variables); None otherwise
        (P8).
    """
    from .domain import unbounded_directions
    from .records import operational_infinity
    found = operational_infinity(cj)
    if found is None:
        return None
    names = [p for p in facts.params
             if facts.param_kinds.get(p, "unknown") in _DIRECTION_KINDS]
    names += sorted(set(cj.free_vars or ()) - set(names))
    effective = {**(parent_domain or {}), **(cj.domain or {})}
    if not unbounded_directions(names, effective):
        return None
    return found.meta()


def overflow_safe_links(conjectures: list) -> tuple:
    """Intent:
        The `(lhs, relation, rhs)` links of every `is_overflow_safe`
        claim in restriction form among `conjectures` (the function's
        own recorded region where its computation stays in float
        range); () when none states one.
    """
    out: list = []
    for c in conjectures:
        if region_row_kind(c.name) != "is_overflow_safe" \
                or c.relation == "is_overflow_safe" or not c.rhs:
            continue
        out.extend(c.links or [(c.lhs, c.relation, c.rhs)])
    return tuple(out)


def pseudo_infinity_condition(cj, facts, parent_domain: "dict | None",
                              probe) -> "str | None":
    """Intent:
        A computation row's `condition` with the resolved
        pseudo-infinity in front, as the grammar spells it: `let |inf|
        be 1e+06, for x in R`, the row's own condition after the
        binding, or the unbounded directions over R when it has none.
        The row's condition unchanged for a derive row (a proof is over
        the reals, P1) and for a claim-level value, which the statement
        already carries.
    """
    from .domain import unbounded_directions
    from .records import operational_infinity
    found = operational_infinity(cj)
    if (found is None or found.source == "claim"
            or routes.is_proof_route(probe.route)):
        return probe.condition
    rest = probe.condition
    if not rest:
        names = [p for p in facts.params
                 if facts.param_kinds.get(p, "unknown") in _DIRECTION_KINDS]
        names += sorted(set(cj.free_vars or ()) - set(names))
        effective = {**(parent_domain or {}), **(cj.domain or {})}
        rest = "for " + ", ".join(
            f"{p} in R" for p in unbounded_directions(names, effective))
    return f"{found.render()}, {rest}"


def _chain_statement(cj) -> str:
    """The chained comparison's own text (`a <= b <= c`), rebuilt from
    its links, the first link's lhs, then each link's relation and
    rhs. Reparses through split_relation_chain (round trip)."""
    parts = [cj.links[0][0]]
    for lhs, rel, rhs in cj.links:
        parts.append(rel)
        parts.append(rhs)
    return " ".join(parts)


def _conjunction_route(routes: list, default: str) -> str:
    """Intent:
        The route a conjunction reports, from the routes of the parts
        that set its verdict: their shared route when they agree; the
        one subroute when the rest report its plain root (`derive` and
        `derive:extensive` give `derive:extensive`, since the wider
        mechanism was needed to settle the whole); else their shared
        root; `default` when the parts share nothing or report none.
    """
    known = [r for r in routes if r]
    if not known:
        return default
    distinct = set(known)
    if len(distinct) == 1:
        return known[0]
    roots = {r.partition(":")[0] for r in distinct}
    if len(roots) != 1:
        return default
    subroutes = {r for r in distinct if ":" in r}
    return subroutes.pop() if len(subroutes) == 1 else roots.pop()


def _combine_conjunction(probes: list, name: str, statement: str,
                         labels: list, what: str = "chained comparison",
                         unit: str = "link") -> "Probe":
    """Intent:
        Fold the per-part verdicts of a conjunction into one: proven
        iff every part is; falsified as soon as any part is (carrying
        that part's counterexample, naming which); holds when every
        part at least holds; else the weakest couldn't-decide (unknown
        over skipped). The single combination rule shared by chained
        comparisons, tuple claims, and function-wide safety
        predicates.

    Notes:
        `labels` names each part for the counterexample/sketch (e.g.
        "link 1: a <= b"); `what`/`unit` name the conjunction kind in
        the combined note. The reported route is the one the deciding
        parts report (`_conjunction_route`): every part for a proof,
        the holding parts for a `holds`, the deciding part otherwise.
    """
    def corroboration(probe) -> dict:
        return {k: v for k, v in (probe.meta or {}).items()
                if k.startswith("mathema.corroboration")
                or k in ("mathema.witness_executed",
                         "mathema.restore_failed")}

    def with_caveats(note: str, parts) -> str:
        caveats: list = []
        for part in parts:
            said = getattr(part, "_caveat", None)
            if said and said not in caveats:
                caveats.append(said)
        return "; ".join([note, *caveats])

    # what every part recorded at its missing inputs, merged per key
    missing: dict = {}
    for probe in probes:
        for key, per_param in ((probe.meta or {}).get("mathema.missing") or {}).items():
            if not isinstance(per_param, dict):
                missing.setdefault(key, per_param)
                continue
            into = missing.setdefault(key, {})
            for p, members in (per_param or {}).items():
                if isinstance(members, dict) and isinstance(into.get(p, {}), dict):
                    into.setdefault(p, {})
                    for word, said in members.items():
                        into[p].setdefault(word, said)
                else:
                    into.setdefault(p, members)
    carried = {"mathema.missing": missing} if missing else {}
    first_drawn = next((p for p in probes if (p.meta or {}).get("mathema.drawn")), None)

    def drawn_by(probe) -> dict:
        # the entries are the ones the part whose count is printed drew
        drawn = (probe.meta or {}).get("mathema.drawn") if probe is not None else None
        return {"mathema.drawn": drawn} if drawn else {}

    for probe, label in zip(probes, labels):
        if probe.verdict == "falsified":
            cx = probe.counterexample
            return Probe(name, statement, "falsified", n=probe.n,
                         route=probe.route,
                         counterexample=(
                             None if not cx
                             # a witness that already names the part
                             # (`at x = 1, ...`) needs no label before it
                             else cx if f"{label} = " in str(cx)
                             else f"{label}: {cx}"),
                         sketch=(f"{label}: {probe.sketch}" if probe.sketch
                                 else None),
                         note=with_caveats(f"{what} falsified at {label}",
                                           probes),
                         meta={**corroboration(probe), **carried,
                               **drawn_by(probe)} or None)
    verdicts = [p.verdict for p in probes]
    if all(v == "proven" for v in verdicts):
        # the definition rows each part's proof read through, in order
        rows: list = []
        for probe in probes:
            for row in (probe.meta or {}).get("mathema.definitions") or ():
                if row not in rows:
                    rows.append(row)
        sketches = [f"{label}: {p.sketch}" for p, label in zip(probes, labels)
                    if p.sketch]
        # a proof's quantifier every part states alike is the whole's
        quantifiers = {p.condition for p in probes}
        return Probe(name, statement, "proven",
                     route=_conjunction_route(
                         [p.route for p in probes], "derive"),
                     sketch="; ".join(sketches) or None,
                     condition=(quantifiers.pop() if len(quantifiers) == 1
                                else None),
                     note=f"every {unit} of the {what} is proven",
                     meta=({"mathema.definitions": rows} if rows else {})
                     | carried | drawn_by(first_drawn) or None)
    if all(v in ("proven", "holds") for v in verdicts):
        n = min((p.n for p in probes if p.n), default=0)
        carried = {**carried, **drawn_by(next((p for p in probes if p.n == n), None))}
        # an engine-bug flag on any part (a derive disproof nothing
        # reproduced) stays on the whole
        flagged = {k: v for p in probes for k, v in corroboration(p).items()
                   if k.startswith("mathema.corroboration")
                   or k == "mathema.restore_failed"}
        uncorroborated = [lbl for p, lbl in zip(probes, labels)
                          if "derive found a disproof" in (p.note or "")]
        note = with_caveats(f"every {unit} of the {what} holds", probes)
        # a part that passed only within the tolerance says so, with its gap
        gaps = [f"{lbl}: {clause}" for p, lbl in zip(probes, labels)
                for clause in (p.note or "").split("; ")
                if p.verdict == "holds" and _WITHIN.search(clause)]
        if gaps:
            note = "; ".join([note, *gaps])
        if uncorroborated:
            note += (f"; derive found a disproof at "
                     f"{', '.join(uncorroborated)} that no run of the code "
                     f"reproduced, which is probably a mathema bug worth "
                     f"reporting")
        return Probe(name, statement, "holds", n=n,
                     route=_conjunction_route(
                         [p.route for p in probes if p.verdict == "holds"],
                         "probe"),
                     note=note, meta={**flagged, **carried} or None)
    weakest = next(p for p, v in zip(probes, verdicts)
                   if v not in ("proven", "holds"))
    label = labels[probes.index(weakest)]
    return Probe(name, statement, weakest.verdict, route=weakest.route,
                 sketch=weakest.sketch,
                 note=f"{what} {weakest.verdict} at {label}: "
                      f"{weakest.note}",
                 meta={**corroboration(weakest), **carried, **drawn_by(first_drawn)})


#: the clause a probe's note gives a pass within the tolerance, with its gap
_WITHIN = re.compile(r"within the (?:default tolerance|tolerance \(|round-off)")


def _adjudicate_chain(cj, fn, facts, domain, trials, trials_scale,
                      extensive, float_companions=False,
                      ) -> "tuple[Probe, Probe | None]":
    """Intent:
        Adjudicate a chained comparison by running each pairwise link
        through the ordinary single-relation path and folding the
        results (`_combine_conjunction`). No proof logic is duplicated:
        a synthesized single-link Conjecture carries the same domain,
        funcs, assuming, route, and tolerance, so every mechanism
        (derive, the empirical fallback, assuming) applies per link.

    Notes:
        The synthesized links are adjudicated in one nested
        `check_conjectures` call so they share the caller's sampling
        setup. A named-reference `assuming` inside a chain is the one
        unsupported combination (the referenced sibling isn't in the
        per-link batch), rare enough to leave to a future pass. Returns
        the chain's verdict and, when `float_companions` is set and the
        chain is proven with every link's float companion spawned, the
        chain's own companion, `<name>[float]`, folded from theirs by
        the same conjunction rule.
    """
    from dataclasses import replace as _replace

    link_cjs = []
    labels = []
    for i, (lhs, rel, rhs) in enumerate(cj.links, start=1):
        labels.append(f"link {i}: {statement_text(rel, lhs, rhs)}")
        link_cjs.append(_replace(cj, lhs=lhs, relation=rel, rhs=rhs,
                                 links=[], name=f"{cj.name}[link{i}]"))
    probes = check_conjectures(fn, link_cjs, domain=domain, trials=trials,
                               trials_downscale=trials_scale, facts=facts,
                               extensive=extensive,
                               float_companions=float_companions)
    link_names = {c.name for c in link_cjs}
    # each link's own finding over non-empty inputs; the empty input is
    # the chain's own line, below
    links = [_own_finding(p) for p in probes if p.name in link_names]
    # a link that does not read as a claim (an undeclared name, say)
    # makes the whole chain unreadable, whatever the other links decide
    refused = next((p for p in links
                    if (p.meta or {}).get("mathema.invalid_conjecture")), None)
    if refused is not None:
        return Probe(cj.name, _chain_statement(cj), refused.verdict,
                     route=None, note=refused.note,
                     meta={"mathema.invalid_conjecture": True}), None
    combined = _combine_conjunction(links, cj.name, _chain_statement(cj),
                                    labels)
    # the links' own empty-input lines are the chain's, one per sequence,
    # the first falsified one where any is
    empty: dict = {}
    for p in probes:
        if (p.meta or {}).get("mathema.family") == "is_empty_safe":
            if p.name not in empty or (p.verdict == "falsified"
                                       and empty[p.name].verdict != "falsified"):
                empty[p.name] = _replace(p, meta={**(p.meta or {}),
                                                  "mathema.companion_of": cj.name})
    combined.meta = {**(combined.meta or {}),
                     "mathema.chain_lines": list(empty.values())} if empty \
        else combined.meta
    companions = [p for p in probes if p.name not in link_names
                  and (p.meta or {}).get("mathema.family") != "is_empty_safe"]
    empty_broken = next((p for p in empty.values() if p.verdict == "falsified"), None)
    if combined.verdict != "proven" or len(companions) != len(links):
        if empty_broken is not None and combined.verdict != "falsified":
            combined = _falsified_by_empty_input(combined, empty_broken)
        return combined, None
    from .gates import companion_representation
    descriptor, _representation, representation_word = \
        companion_representation(cj.domain, facts)
    companion = _combine_conjunction(
        companions, companion_name(cj.name, descriptor), _chain_statement(cj),
        labels, what="float companion")
    companion.note = (f"the {representation_word} computation of {cj.name} ran "
                      f"link by link, and every link holds"
                      if companion.verdict == "holds" else
                      f"the {representation_word} computation of {cj.name} ran "
                      f"link by link; {companion.note}")
    broken = next((p for p in companions if p.verdict == "falsified"), None)
    if broken is not None:
        companion.stratum = broken.stratum
    combined.meta = {**(combined.meta or {}),
                     "mathema.float_companion": companion.name}
    if empty_broken is not None:
        combined = _falsified_by_empty_input(combined, empty_broken)
    return combined, companion


def _stamp_examine_route(probe, cj, fn, facts) -> None:
    """Intent:
        Restate a safety examination's route: a computation fact
        ESTABLISHED structurally is examined, not derived, so a safety
        predicate or a registered SafetyFamily name whose structural
        (derive) mechanism decided reports `examine`. The empirical half
        is ordinary sampling and keeps its real `probe` route (`probe` /
        `probe:algorithmic` / `probe:semi_analytical`): the route
        reflects the mechanism, not the claim's kind. The verdict
        already carries the SURETY (proven only for an established fact,
        holds for fail-to-refute).

    Notes:
        Mutates the probe in place, only when the claim is a safety
        examination and the route names a derive/probe mechanism,
        validation skips (route None) and non-safety claims pass
        through untouched.
    """
    if probe.route is None:
        return
    from .symbolic._matrix_lemmas import structure_properties
    if cj.relation in structure_properties():
        # a matrix structure predicate is a fact of matrix algebra about
        # a value, decided on derive by the matrix route or sampled on
        # the probe, never a computation fact
        return
    is_safety = cj.relation in routes.examine_predicates()
    if not is_safety:
        from .claim_families import SafetyFamily
        base = families.claim_base_name(cj.name)
        base_family = families.families().get(base)
        is_safety = (isinstance(base_family, SafetyFamily)
                     and _statement_is_family_claim(cj, base, base_family,
                                                    facts))
    if not is_safety:
        return
    root, _, _sub = probe.route.partition(":")
    if (root == "derive" and probe.verdict == "falsified"
            and "is_defined" in (region_row_kind(cj.name), cj.relation)
            and (probe.meta or {}).get("mathema.corroboration")
            == "reproduced"):
        # an is_defined falsification is decided by executing the
        # function at a point the computed region suggested, an
        # analytically seeded execution, never by the structure alone
        probe.route = "probe:semi_analytical"
        return
    if root == "derive":
        # a structural mechanism established the predicate (proven-
        # capable); the extensive-ladder detail folds into the plain
        # `examine` (the verdict already carries surety). This is the
        # one route `examine` names: the empirical half of a predicate
        # check is ordinary sampling and keeps its real `probe` route
        # (`probe` / `probe:algorithmic` / `probe:semi_analytical`),
        # since route reflects the mechanism, not the claim's kind.
        probe.route = "examine"


def _adjudicate_function_wide_safety(cj, fn, facts, domain, trials,
                                     trials_scale, extensive) -> "Probe":
    """Intent:
        Adjudicate a safety predicate stated over the function itself
        (`is_missing_safe(f)`, `is_pole_safe(f)`, ...): the
        conjunction of the same predicate over every numeric
        parameter, each adjudicated through the ordinary
        per-parameter path and folded by the chain rule, proven iff
        every parameter's own claim proves, falsified at the first
        parameter with a real counterexample (named), holds when
        every parameter at least holds.

    Notes:
        Numeric means every parameter that isn't a sequence, the
        N/Z/R/C-typed inputs a missing/pole/spelling hazard can
        actually reach. Only reachable when `f` isn't itself a real
        parameter name (a parameter literally named f keeps the
        ordinary per-parameter reading). The synthesized per-parameter
        claims run in one nested check_conjectures call, exactly as a
        chained comparison's links do.
    """
    from dataclasses import replace as _replace

    numeric = [p for p in facts.params
               if facts.param_kinds.get(p) not in SEQUENCE_KINDS]
    if cj.relation == "is_empty_safe":
        # the empty input belongs to the containers: they are the
        # parameters this one asks about
        numeric = [p for p in facts.params
                   if facts.param_kinds.get(p) in (*SEQUENCE_KINDS, "table")]
        if not numeric:
            scalar = facts.params[0] if facts.params else "the parameter"
            return Probe(cj.name, statement_text(cj.relation, "f", cj.rhs),
                         "skipped:misspecified", route=None,
                         note=(f"is_empty_safe(f) has no container parameter to test: "
                               f"{scalar} is a scalar; empty applies to a container"))
    statement = statement_text(cj.relation, "f", cj.rhs)
    if not numeric:
        if cj.relation == "is_missing_safe":
            containers = [p for p in facts.params
                          if facts.param_kinds.get(p) in SEQUENCE_KINDS
                          or facts.param_kinds.get(p) == "table"]
            from .runtime_types import realised_parameters
            runtime = {p: d.adapter for p, d in realised_parameters(facts).items()}
            first = containers[0] if containers else "the parameters"
            typed = f" ({runtime[first]})" if first in runtime else ""
            return Probe(cj.name, statement, "skipped", route=None,
                         note=(f"is_missing_safe(f) does not yet check container "
                               f"parameters such as {first}{typed}; its missing "
                               f"slots were tried by the claims and are listed in "
                               f"their records"))
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"{cj.relation}(f) covers the numeric "
                          f"parameters, and this function has none")
    sub_cjs = [_replace(cj, lhs=p, name=f"{cj.relation}[{p}]")
               for p in numeric]
    probes = check_conjectures(fn, sub_cjs, domain=domain, trials=trials,
                               trials_downscale=trials_scale, facts=facts,
                               extensive=extensive)
    combined = _combine_conjunction(probes, cj.name, statement, numeric,
                                    what=f"function-wide {cj.relation}",
                                    unit="parameter")
    if cj.relation == "is_missing_safe" and combined.verdict == "falsified":
        at = next((p.name.split("[", 1)[1].rstrip("]") for p in probes
                   if p.verdict == "falsified" and "[" in p.name), None)
        if at:
            combined.note = f"is_missing_safe(f) is false: see {at}."
    return combined


#: why derive leaves a function's raise statements to the probe
_RAISES_UNREAD = ("derive cannot read the function's raise statements, so "
                  "it decides nothing about them; the probe runs the code "
                  "instead")


def _last_clause(note: str) -> str:
    """The last `; `-separated clause of a note, a `; ` inside
    parentheses not counting as a separator."""
    depth, cut = 0, 0
    for i, ch in enumerate(note):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(depth - 1, 0)
        elif ch == ";" and depth == 0 and note[i + 1:i + 2] == " ":
            cut = i + 2
    return note[cut:]


def _derive_attempt_label(fallback: "Probe") -> str:
    """A short 'derive: <status> (<why>)' label for the attempt log,
    read off a stashed derive-undecided Probe; its
    mathema.derive_status meta (unliftable/undecided) and its own
    sketch/last-note reason."""
    status = (fallback.meta or {}).get("mathema.derive_status", "undecided")
    reason = fallback.sketch or _last_clause(fallback.note or "")
    reason = (reason or "").strip()
    # keep the trail readable: one clause, not the whole prior note
    if reason and reason.startswith("conjectured by"):
        reason = ""
    display = "underivable" if status == "unliftable" else status
    return f"derive: {display}" + (f" ({reason})" if reason else "")


def _probe_attempt_label(probed: "Probe") -> str:
    """A short 'probe: <status>' label for the attempt log."""
    if probed.verdict in ("holds", "falsified", "proven"):
        return f"probe: {probed.verdict}"
    if probed.verdict == "skipped" and probed.sketch \
            and "not implemented" in probed.sketch:
        return f"probe: {probed.sketch.split(', ')[0]}"
    reason = (probed.sketch or (probed.note or "").rsplit("; ", 1)[-1] or "").strip()
    if reason.startswith("conjectured by"):
        reason = "inconclusive"
    return f"probe: {probed.verdict}" + (f" ({reason})" if reason else "")


def _probe_said(probed: "Probe") -> str:
    """Why running the code did not settle a claim either, in words:
    `the probe could not decide it either (no point of the claim could
    be drawn)`."""
    reason = (probed.sketch or (probed.note or "").rsplit("; ", 1)[-1] or "").strip()
    if not reason or reason.startswith("conjectured by"):
        return "the probe could not decide it either"
    return f"the probe could not decide it either ({reason})"


def _merge_under(meta: dict, extra: dict) -> dict:
    """Intent:
        `meta` with `extra`'s keys added beneath it: a key already in
        `meta` keeps its value, except `mathema.language`, whose
        entries merge per key (an entry already present wins).
    """
    import copy
    out = dict(meta)
    for key, value in extra.items():
        if key == "mathema.language" and isinstance(value, dict) \
                and isinstance(out.get(key), dict):
            out[key] = {**copy.deepcopy(value), **out[key]}
        elif key not in out:
            out[key] = copy.deepcopy(value)
    return out


_WITNESS_SHRINK_EVALUATIONS = 400


def _witness_labels(cj, kinds, cj_domain) -> "tuple[tuple[str, ...] | None, set | None]":
    """Intent:
        `(names, shown)` for `_fmt` on a witness: every parameter by
        name, with only the ones the claim reads shown.
    """
    shown = set(_names_in_claim(cj))
    # a parameter the claim fills with a literal (`f(values, "info")`) is
    # shown too: its value is part of the point
    names = list(kinds)
    sides = [cj.lhs, cj.rhs] + [t for link in (cj.links or ()) for t in (link[0], link[2])]
    for side in sides:
        try:
            tree = ast.parse(side or "", mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "f":
                for i, arg in enumerate(node.args):
                    if isinstance(arg, (ast.Constant, ast.List, ast.Tuple)) \
                            and i < len(names):
                        shown.add(names[i])
                for kw in node.keywords:
                    if kw.arg and isinstance(kw.value, ast.Constant):
                        shown.add(kw.arg)
    return tuple(kinds), shown


def _exact_verdict(cj, code_l, code_r, env, fn, bound_funcs) -> "bool | None":
    """Intent:
        The claim at the point `env` in exact arithmetic: f and the
        claim's bound functions run on the point's exact values
        (`_exact_side.exact_sides` with `exact_calls`) under the fast
        wall-clock cap, the sides compared exactly (within the claim's
        own declared tolerance, when it states one). True or False, or
        None when the evaluation cannot be carried out exactly.
    """
    from ._exact_side import exact_sides
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    if not _inside_as_written(cj, env):
        return None
    try:
        exact = _with_timeout(
            lambda: exact_sides(code_l, code_r, env,
                                {"f": fn, **(bound_funcs or {})},
                                exact_calls=True),
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    if exact is None:
        return None
    return relation_holds_elementwise(
        exact[0], exact[1], cj.relation,
        cj.tolerance if cj.tolerance is not None else 0.0,
        exact_inequality=cj.tolerance is None, rel_tol=0.0)


def _inside_as_written(cj, env) -> bool:
    """Intent:
        Whether every coordinate of the executed point lies in the
        claim's domain read as written: a draw at an interval end
        written as a decimal is the float nearest that decimal, which
        can lie past it. A bound that is not a union of intervals or a
        finite set of numbers is not checked.
    """
    from fractions import Fraction

    from ._exact_witness import Undecided, in_bound
    for name, bound in (cj.domain or {}).items():
        value = env.get(name)
        values = (list(value) if isinstance(value, (list, tuple))
                  else value.ravel().tolist() if hasattr(value, "ravel")
                  else [value])
        for v in values:
            if not isinstance(v, float) or v != v or v in (float("inf"),
                                                           float("-inf")):
                continue
            q = Fraction(v)
            pieces = getattr(bound, "pieces", None)
            try:
                if not in_bound(q, bound):
                    return False
            except Undecided:
                sets = [p for p in (pieces or ()) if isinstance(p, frozenset)]
                members = [m for p in sets for m in p
                           if isinstance(m, (int, float))
                           and not isinstance(m, bool)]
                if members and len(sets) == len(pieces or ()) and q not in {
                        Fraction(repr(m)) if isinstance(m, float)
                        else Fraction(m) for m in members}:
                    return False
    return True


#: magnitudes past which a draw is a corner of the number representation
_CORNER_LARGE, _CORNER_SMALL = 1e150, 1e-150


def _magnitude_corner(args) -> bool:
    """Intent:
        Whether an executed point is a magnitude corner: every number in
        it finite, and some number at least 1e150 or nonzero and at most
        1e-150 in magnitude, where float arithmetic overflows or
        underflows although the exact value is finite.
    """
    import math
    values: list = []

    def collect(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            values.append(float(v))
        elif isinstance(v, (list, tuple)):
            for u in v:
                collect(u)
        elif hasattr(v, "ravel"):
            for u in v.ravel().tolist():
                collect(u)
        elif hasattr(v, "tolist"):
            collect(v.tolist())
    for a in args:
        collect(a)
    if not values or not all(math.isfinite(v) for v in values):
        return False
    return any(abs(v) >= _CORNER_LARGE or 0 < abs(v) <= _CORNER_SMALL
               for v in values)


def _exact_point_sides(code_l, code_r, env, fn, bound_funcs):
    """A function of a point (`{param: exact value}`) evaluating the
    claim's sides with f run on those exact numbers, under the fast cap;
    None where it cannot."""
    from ._exact_side import exact_sides
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout

    def at(point):
        try:
            return _with_timeout(
                lambda: exact_sides(code_l, code_r, {**env, **point},
                                    {"f": fn, **(bound_funcs or {})},
                                    exact_calls=True),
                FAST_TIMEOUT_SECONDS)
        except TimeoutError:
            return None
    return at


def _called_point(f_call, facts, env: dict, kinds: dict) -> dict:
    """Intent:
        The point f was last called at, `{param: value}`: the arguments
        of its last returning call (a literal the claim passes, a pin, a
        default included), else the sampled values of the parameters.
    """
    calls = [c for c in getattr(f_call, "calls", []) or [] if c[0] == "returned"]
    if calls:
        _kind, _out, args, kwargs = calls[-1]
        point = dict(zip(list(facts.params), args))
        point.update(kwargs or {})
        if point:
            return point
    return {p: env.get(p) for p in kinds}


def _exactly_holds_at(cj, code_l, code_r, env, fn, bound_funcs) -> bool:
    """Whether `_exact_verdict` finds the claim true at the point."""
    return _exact_verdict(cj, code_l, code_r, env, fn, bound_funcs) is True


def _stands_in_for_derive(ctx: "_ClaimContext") -> bool:
    """Intent:
        Whether this probe stands in for a derive attempt that could not
        settle the mathematics (the wall clock, or sympy unable to close
        the identity). Its draws then judge the mathematics, so a failure
        of the float computation at a point where the claim holds exactly
        belongs to the computation line. Where derive does not apply at
        all (an unliftable or unsupported claim) the probe is the
        computation line itself, and such a point falsifies it.
    """
    fallen = ctx.derive_undecided
    return fallen is not None and \
        (fallen.meta or {}).get("mathema.derive_status") == "undecided"


def _representation_word(cj_domain, facts) -> str:
    """The computation's representation in words ("float64")."""
    from .gates import companion_representation
    return companion_representation(cj_domain, facts)[2]


def _bound_funcs_of(cj) -> dict:
    """The claim's bound functions, a dotted reference resolved to the
    callable it names, as the derive stage resolves them."""
    try:
        return {name: (v if callable(v) else _resolve_bound_ref(v))
                for name, v in cj.funcs.items()}
    except AttributeError:
        return {}


def _exactly_decided(cj, code_l, code_r, env, callees, ok, *,
                     within: "float | None" = None, input_scaled: float = 0.0,
                     side: "int | None" = None):
    """Intent:
        The relation at the point `env` holds, re-decided with the claim's
        sides evaluated exactly (`_exact_side.exact_sides`): the function's
        results read as the exact values it returned, the claim's own
        literals and arithmetic exact, compared within the computation
        allowance (`_allowance.relation_within`; with `within` given,
        within that absolute allowance alone, 0.0 for an exact
        comparison). `ok` (the float verdict) comes back unchanged when
        the sides cannot be computed exactly.
    """
    from ._allowance import relation_within
    from ._exact_side import exact_sides
    exact = exact_sides(code_l, code_r, env, callees)
    if exact is None:
        return ok
    declared = cj.tolerance if cj.tolerance is not None else within
    held = relation_within(exact[0], exact[1], cj.relation, declared,
                           input_scaled, side,
                           exact_inequality=cj.tolerance is None)
    return ok if held is None else held


def _failure_at(cj, kinds, env, args, code_l, code_r, labels=(None, None)) -> "str | None":
    """Intent:
        The counterexample text the claim fails with at `args` (a raise,
        a membership, or a comparison, in the claim loop's own words),
        or None when it holds there or cannot be evaluated.
    """
    trial_env = dict(env)
    for p, v in zip(kinds, args):
        trial_env[p] = v
    try:
        lv = eval(code_l, {"__builtins__": {}}, trial_env)
        rv = eval(code_r, {"__builtins__": {}}, trial_env) if code_r is not None else None
    except Exception as e:
        if inputs_missing(args) and cj.relation not in ("in", "not in"):
            # a raise at a missing input is classified, not judged
            return None
        return (f"{_fmt(tuple(args), *labels)}: raised {type(e).__name__}, narrow "
                "the claim's domain to where every call returns, or state "
                "the raising region as its own raises(...) claim")
    if cj.relation in ("in", "not in"):
        if cj.rhs_bound is not None:
            sizes = _shapes.axis_sizes(cj.domain or {}, dict(zip(kinds, args)))
            member = _membership_member(lv, cj.rhs_bound, sizes)
        else:
            try:
                member = lv in rv  # type: ignore[operator]
            except TypeError:
                return None
        if member != (cj.relation == "in"):
            return (f"{_fmt(tuple(args), *labels)}: {lv!r} is "
                    f"{'not ' if cj.relation == 'in' else ''}in {cj.rhs}")
        return None
    missing_in = inputs_missing(args)
    if missing_in and inputs_missing([lv]):
        # a missing output at a missing input is classified, not judged
        return None
    if not missing_in and (holds_nan(lv) or holds_nan(rv)):
        return f"{_fmt(tuple(args), *labels)}: {lv!r} vs {rv!r}, and a nan is no value"
    if not missing_in and "absent" in (missing_class(lv), missing_class(rv)):
        # absence compares as absence: None agrees with None under == and
        # ~=, and fails against a value, under != and under an ordering
        from ._missing_words import absence_agrees, absence_words
        if absence_agrees(lv, rv, cj.relation):
            return None
        return (f"{_fmt(tuple(args), *labels)}: {lv!r} vs {rv!r}, "
                f"{absence_words(lv, rv, cj.relation)}")
    from ._allowance import reference_side, relation_within
    side = reference_side(cj)
    ok = relation_within(lv, rv, cj.relation, cj.tolerance, 0.0, side,
                         exact_inequality=cj.tolerance is None)
    if ok is False:
        callees = {k: v for k, v in trial_env.items()
                   if callable(v) and (k == "f" or k in (cj.funcs or {}))}
        if _exactly_decided(cj, code_l, code_r, trial_env, callees, ok,
                            side=side) is True:
            return None
        return f"{_fmt(tuple(args), *labels)}: {lv!r} vs {rv!r}"
    return None


def _shrink_language_witness(cj, kinds, cj_domain, env, args, code_l, code_r):
    """Intent:
        `(args, counterexample, steps)`: the witness shrunk inside each
        language-bound parameter's language, one of the language's own
        `shrink` candidates at a time, keeping a candidate only when it
        is in the claim's domain for that parameter and the claim still
        fails there, within `_WITNESS_SHRINK_EVALUATIONS` evaluations;
        None when the failure does not reproduce.
    """
    from .domain import LanguageRef, domain_contains, path_bindings_hold
    from .languages import resolve_language
    args = list(args)
    labels = _witness_labels(cj, kinds, cj_domain)
    current = _failure_at(cj, kinds, env, args, code_l, code_r, labels)
    if current is None:
        return None
    budget, steps = _WITNESS_SHRINK_EVALUATIONS, 0
    names = list(kinds)
    improved = True
    while improved and budget > 0:
        improved = False
        for i, p in enumerate(names):
            bound = cj_domain.get(p)
            if getattr(bound, "base_type", None) != "L":
                continue
            languages = []
            for piece in bound.pieces:
                if isinstance(piece, LanguageRef):
                    try:
                        languages.append(resolve_language(piece))
                    except Exception:
                        continue
            for language in languages:
                try:
                    if not language.contains(args[i]):
                        continue
                    candidates = iter(language.shrink(args[i]))
                except Exception:
                    continue
                while budget > 0:
                    # candidates are taken as they come, so a long value
                    # is not expanded into every candidate up front
                    try:
                        candidate = next(candidates)
                    except StopIteration:
                        break
                    except Exception:
                        break
                    try:
                        inside = (domain_contains(candidate, bound)
                                  and path_bindings_hold(candidate, p, cj_domain))
                    except Exception:
                        inside = False
                    if not inside:
                        continue
                    budget -= 1
                    trial = [*args[:i], candidate, *args[i + 1:]]
                    failure = _failure_at(cj, kinds, env, trial, code_l, code_r, labels)
                    if failure is not None:
                        args, current, steps, improved = trial, failure, steps + 1, True
                        break
                if improved:
                    break
            if improved:
                break
    return args, current, steps


def _arbitrate_empirical_fallback(probed: "Probe", ctx: "_ClaimContext") -> "Probe":
    """Intent:
        Decide which report stands when a route="best"/"derive" claim
        fell through to probing, and record the full cross-route
        attempt trail. Empirical evidence (holds/falsified) supersedes
        the derive unknown; a falsification is as strong from either
        route, and holds is evidence where there was none, while a
        probe that couldn't adjudicate either hands back the derive
        attempt's richer diagnosis. Either way the winning Probe's note
        lists every route tried and why each did or didn't decide.

    Notes:
        The structured mathema.derive_status / mathema.timeout meta is
        carried onto the winning Probe regardless of who adjudicated,
        so a coverage measurement keeps the derive-route signal. When
        derive's report stands, the probe's own meta (a family's
        resolved target, a probe gap) is merged beneath derive's.
    """
    fallback = ctx.derive_undecided
    if fallback is None:
        return probed
    if probed.verdict not in ("proven", "holds", "falsified"):
        # the probe route couldn't evaluate the claim's own text (a
        # calculus law), numeric evidence on the LIFTED intermediate
        # is the remaining route, and it supersedes the unknown the
        # same way ordinary probe evidence would
        lifted_numeric = _lifted_numeric_fallback(
            ctx, ctx.cj, ctx.statement, ctx.note, ctx.cj_domain)
        if lifted_numeric is not None:
            probed = lifted_numeric
    trail = (f"routes attempted, {_derive_attempt_label(fallback)}; "
             f"{_probe_attempt_label(probed)}")
    # "proven" from the empirical side exists only for an ESTABLISHED
    # examination (the family verdict contract requires the
    # exhaustive-coverage sketch), so it supersedes like any evidence;
    # a probe that found no value to compare says why, which is the
    # reason the claim stays open
    winner = (probed if probed.verdict in ("proven", "holds", "falsified")
              or (probed.meta or {}).get("mathema.missing_unknown")
              else fallback)
    # the note leads with the deciding route's own sentence; the route
    # log is kept on the record's meta
    if winner is probed and probed.verdict in ("proven", "holds", "falsified"):
        why = _derive_attempt_label(fallback).split("(", 1)
        reason = why[1].rsplit(")", 1)[0] if len(why) > 1 else ""
        # a next step rides on its own line inside the reason
        reason, *then = reason.split("\n")
        branch = re.search(r"line (\d+) \('([^']*)'\)", reason or "")
        needs = re.search(r"needs a domain specific enough for ([\w, ]+)", reason or "")
        told = (f"derive could not decide the branch at line {branch.group(1)} "
                f"({branch.group(2)})"
                + (f": it needs a domain specific enough for {needs.group(1).strip()}"
                   if needs else "")
                + ", so the probe decided it by running the code" if branch else
                "derive could not show whether f raises here (it returns a "
                "value in this domain), so the probe decided it by running "
                "the code" if "rather than raising" in reason else
                reason if reason.startswith("derive ") and (
                    "the probe" in reason or "running the code" in reason) else
                f"{reason}, so the probe decided it by running the code"
                if reason.startswith("derive ") else
                f"derive could not decide it ({reason}), so the probe decided "
                f"it by running the code"
                if reason else "derive could not decide it, so the probe "
                               "decided it by running the code")
        winner.note = f"{winner.note}; {told}".lstrip("; ")
        if then:
            # the next step, condition first and command last, goes on
            # a line of its own after the whole note (see _check_built)
            winner.meta = {**(winner.meta or {}), "mathema.next_steps": then}
    elif winner is fallback:
        # derive's own report stands; the note says why the probe could
        # not settle it either
        winner.note = f"{winner.note}; {_probe_said(probed)}".lstrip("; ")
    winner.meta = {**(winner.meta or {}), "mathema.routes_attempted": trail}
    carried = {k: v for k, v in (fallback.meta or {}).items()
               if k.startswith("mathema.derive") or k == "mathema.timeout"
               or k.startswith("mathema.corroboration")}
    if carried:
        winner.meta = {**(winner.meta or {}), **carried}
    if winner is fallback and probed.meta:
        winner.meta = _merge_under(winner.meta or {}, probed.meta)
    if (fallback.meta or {}).get("mathema.corroboration") == "uncorroborated":
        # the engine-bug signal must survive whichever route wins: a
        # symbolic disproof nothing reproduced was claimed here, and a
        # later reader (or the maintainer) needs to see that. A claim
        # form with no point evaluation had no reproduction attempted,
        # so that note names the missing witness instead.
        from .corroboration import (EXACT_ARITHMETIC_ONLY,
                                    EXACT_ARITHMETIC_ONLY_NOTE)
        if (fallback.meta or {}).get("mathema.corroboration_unexecutable"):
            winner.note = (f"{winner.note}; derive found a disproof it could "
                           f"not check by running the code, since this claim "
                           f"has no single point to evaluate")
        elif ((fallback.meta or {}).get("mathema.corroboration_reason")
              == EXACT_ARITHMETIC_ONLY):
            winner.note = (f"{winner.note}; derive found a disproof that "
                           f"no run of the code reproduced "
                           f"({EXACT_ARITHMETIC_ONLY_NOTE})")
        else:
            winner.note = (f"{winner.note}; derive found a disproof that "
                           f"no run of the code reproduced, which is probably "
                           f"a mathema bug worth reporting")
    return winner


@dataclass
class _ClaimContext:
    """One claim, validated and ready for a route to adjudicate: the
    parsed conjecture, its rendered statement, the note accumulated so
    far (validation appends its own inferences to it), the fully merged
    per-claim domain, the claim's bound extra-function names, and;
    once the orchestration loop has looked it up, the registered
    claim family, if any."""
    cj: Conjecture
    statement: str
    note: str
    cj_domain: dict
    extra: frozenset
    family: object | None = None
    derive_undecided: "Probe | None" = None
    derive_intermediates: "tuple | None" = None
    # (lhs_expr, rhs_expr, params) from an undecided derive attempt:
    # the resolved symbolic sides the numeric fallback samples when the
    # probe route cannot evaluate the claim's own text (a calculus law)
    assumption: "list | None" = None
    # the interpreted `assuming <...>,` clause, parsed as a list of
    # (never adjudicated) relation Conjectures; one per `and`-joined
    # conjunct. Both routes constrain themselves to the region where
    # ALL of them hold: derive by excluding raise guards and
    # strengthening ask()'s context, probe by rejection sampling.
    assumption_display: str = ""
    assume_defined: bool = False
    # a value claim binding no domain for the parameters f's own raise
    # branches read: those branches refuse their inputs, outside the
    # working domain, so derive excludes them and the probe skips (and
    # counts) the draws they refuse
    exclude_own_guards: bool = False
    guard_refused: int = 0
    # draws a path binding rejected because the path reached no value
    # (an index past the end, a field holding None) the bound does not
    # admit: outside the binding, counted in the record
    path_no_value: int = 0
    # matrix-structure premises: {param: (prop, ...)} the sampler
    # synthesises to, and the derive backend turns into sympy
    # assumptions (Q.symmetric, Q.positive_definite, ...)
    premise_structures: dict = field(default_factory=dict)
    # True for `assuming is_defined(f)`: the claim quantifies over the
    # exact region where every call to f returns, derive excludes
    # f's raise regions by construction (their negations feed the
    # decision machinery), probe skips raising samples as
    # outside-the-quantifier
    # set by _adjudicate_derive when a route="derive" attempt came back
    # undecided/unliftable: the unknown Probe it WOULD have reported,
    # kept while the claim falls through to the probe stage, empirical
    # evidence (holds or falsified) supersedes an unknown, and this
    # fallback is what the loop reports when probe couldn't adjudicate
    # either

    # whether a derive proof spawns its float companion: "spawn",
    # "math_only" (the claim opted out with route derive:math_only), or
    # None (companions not asked for); the staged companion rides
    # `companion` until the orchestration loop emits it
    companion_mode: "str | None" = None
    companion: "Probe | None" = None
    # the caller's explicit trials, which bound the companion's points too
    companion_budget: "int | None" = None
    # each bound parameter's missing-value resolution, `{param:
    # domain.MissingDefaults}`: the members the hole class stands for
    # and the spellings of absence, the values a listed sentinel is
    # realised as
    missing: dict = field(default_factory=dict)
    # the claim's own bindings completed from the annotations, which the
    # record's canonical text renders; the routes read `cj_domain`
    record_domain: dict = field(default_factory=dict)
    # the parameters the claim names without binding, completed from the
    # signature into `record_domain` for their holes and absence; the
    # record's text leaves them unbound
    implied: frozenset = frozenset()


def _claim_array_ranks(cj_domain: dict, fn, facts) -> dict:
    """Intent:
        The names a claim reads as vectors, matrices or tables,
        `{name: rank}` (`linalg.array_ranks`), from its merged domain,
        the function's signature markers and the parameters' runtime
        kinds.
    """
    shapes: dict = {}
    structures: dict = {}
    if fn is not None:
        from .types import shapes_from_signature, structures_from_signature
        try:
            shapes = shapes_from_signature(fn)
            structures = structures_from_signature(fn)
        except Exception:
            shapes, structures = {}, {}
    return linalg.array_ranks(cj_domain, shapes,
                              getattr(facts, "param_kinds", None),
                              structures)


#: attributes of a DataFrame that are not columns
_TABLE_ATTRIBUTES = frozenset({"T", "shape", "columns", "index", "values",
                               "iloc", "loc", "dtypes", "empty", "size",
                               "ndim", "schema", "height", "width"})


def _table_columns(param: str, cj, facts) -> list:
    """Intent:
        The column names a table parameter is drawn with: every column
        the claim (statement and premises) or the function body reads
        as `param.name` or `param["name"]`, in the order first met, or
        `["a", "b"]` when nothing names one.
    """
    trees = []
    for src in _claim_sides(cj) + [a for a in (cj.assuming or "",) if a]:
        text = re.sub(r"^\s*assuming\s+", "", str(src))
        try:
            trees.append(ast.parse(text, mode="eval"))
        except SyntaxError:
            continue
    if getattr(facts, "tree", None) is not None:
        trees.append(facts.tree)
    found: list = []
    for tree in trees:
        called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Attribute) and id(node) not in called \
                    and isinstance(node.value, ast.Name) \
                    and node.value.id == param \
                    and not node.attr.startswith("_") \
                    and node.attr not in _TABLE_ATTRIBUTES:
                name = node.attr
            elif isinstance(node, ast.Subscript) \
                    and isinstance(node.value, ast.Name) \
                    and node.value.id == param \
                    and isinstance(node.slice, ast.Constant) \
                    and isinstance(node.slice.value, str):
                name = node.slice.value
            if name is not None and name not in found:
                found.append(name)
    return found or ["a", "b"]


def _bound_for_arrays(callee):
    """Intent:
        A bound function as a vector or matrix claim calls it: a
        library function (numpy, scipy, pandas, polars) receives the
        claim's arrays as they are; any other Python function receives
        plain lists, realised through the runtime types its own
        signature names, or else its claims-file entry's
        `runtime_types:` declares. The result is read back as an array.
    """
    from . import _linalg_eval
    module = (getattr(callee, "__module__", "") or "").split(".", 1)[0]
    if module in ("numpy", "scipy", "pandas", "polars") \
            or not inspect.isfunction(callee):
        return _linalg_eval.law_callable(callee, plain_args=False)
    from types import SimpleNamespace

    from .compendium import declared_runtime_types
    from .runtime_types import calling, detect_parameters
    key = f"{getattr(callee, '__module__', '')}." \
          f"{getattr(callee, '__qualname__', '')}"
    declared = {str(k): str(v)
                for k, v in declared_runtime_types(key).items()}
    try:
        detected = detect_parameters(callee, declared or None)
    except Exception:
        detected = {}
    return _linalg_eval.law_callable(
        calling(callee, SimpleNamespace(runtime_types=detected)))


def _free_array(bound, resolver, trial_sizes: dict, env: dict, rng,
                specials) -> list:
    """Intent:
        A draw of a claim's own vector or matrix variable (`let b be
        R^n`): nested lists with one axis per dimension of its space,
        each element drawn from the space's element domain. A fixed
        size is that size; a dimension name the parameters carry takes
        this trial's size for it (drawn, or measured off an argument);
        any other name is a small random size.
    """
    sizes = []
    for d in bound.dims:
        if isinstance(d, int) or (isinstance(d, str) and d.isdigit()):
            sizes.append(int(d))
            continue
        name = resolver.canonical(d)
        size = trial_sizes.get(name)
        if size is None:
            anchor = resolver.anchor(name)
            if anchor is not None and anchor[0] in env:
                try:
                    size = resolver.measure(env[anchor[0]], anchor[1])
                except (IndexError, TypeError):
                    size = None
        sizes.append(size if size is not None else rng.randint(1, 5))

    def build(axis):
        if axis == len(sizes):
            return _synth("float", rng, bound, specials=specials)
        return [build(axis + 1) for _ in range(sizes[axis])]
    return build(0)


def _claim_sides(cj) -> list:
    """Every expression a claim's relation compares: both sides, and
    each link of a chained comparison."""
    sides = [cj.lhs, cj.rhs]
    for link in cj.links or ():
        sides += [link[0], link[2]]
    return [s for s in sides if s]


def _needs_language(cj, statement: str, note: str, error) -> "Probe":
    """The row for a claim naming a language nothing in this process
    serves: unknown, never falsified, with the package that adds the
    named languages (mathema-language) in the note and the gap in meta."""
    return Probe(cj.name, statement, "unknown", route=None,
                 note=f"{note}; needs mathema-language: {error}".lstrip("; "),
                 meta={"mathema.probe_gap": "language-unresolved"})


def _validate_claim(cj, statement: str, note: str, facts,
                    domain: dict, fn=None) -> "Probe | _ClaimContext":
    """Intent:
        Everything checked before either evidence route runs: grammar
        membership, bare-reserved-name, ambiguous-differential and
        `raises(...)` call-arity misspecifications, the per-claim domain merge (inline
        quantifier wins over the function-level argument, literal-
        argument inference filling gaps), free-variable/parameter
        reconciliation, and unknown domain keys.

    Notes:
        Returns an early-skip `Probe` at the first check that fails
        (route `None`: no evidence mechanism ever engaged), or a
        `_ClaimContext` carrying the merged domain and the note text
        with any validation-stage inferences appended.
    """
    _KNOWN_RELATIONS = frozenset({"==", "~=", "!=", "<=", ">=", "<", ">",
                                  "=:=", "in", "not in",
                                  "raises"}) | routes.examine_predicates()
    if cj.relation not in _KNOWN_RELATIONS:
        # a malformed/unrecognized relation is a validation skip, caught
        # here before any evidence route, never dispatched into a
        # prover (which would report a misleading "unknown" instead)
        return Probe(cj.name, statement, "skipped", route=None,
                     note=note + f"; unrecognized relation {cj.relation!r}")
    if cj.grammar != GRAMMAR and not cj.grammar.startswith(GRAMMAR + "/"):
        # a `mathema/<dialect>` sub-grammar (e.g. `mathema/linalg`) is
        # this same parser in a matrix-aware mode and IS adjudicated; a
        # foreign grammar (`mathema.data`'s) is not adjudicate-able here.
        # not a failure to adjudicate; this claim simply isn't this
        # module's grammar (mathema.data's, say, mixed into the same
        # declared file/key). Verdict "skipped" (blocked, with the
        # reason right here), tagged in `meta`
        # so a caller sweeping many claims (cli.py's cmd_verify) can
        # tell "not adjudicated by this route" apart from a genuine
        # unverifiable claim instead of conflating the two into one
        # strict-mode failure count.
        return Probe(cj.name, statement, "skipped", route=None,
                     note=note + f"; grammar {cj.grammar!r} is not "
                          f"{GRAMMAR!r}, so mathema does not check it",
                     meta={"mathema.foreign_grammar": cj.grammar})
    param_set = set(facts.params)
    bare_reserved = (_find_bare_reserved_name(cj.lhs, param_set)
                    if cj.relation != "raises" else None) \
        or (_find_bare_reserved_name(cj.rhs, param_set)
            if cj.rhs and cj.relation != "raises" and cj.rhs_bound is None
            and cj.relation not in routes.examine_predicates() else None)
    if bare_reserved is not None:
        # a purely syntactic mistake (a recognized function's name
        # used as a plain value, not called, `f(x) == sin` typed
        # instead of `f(x) == sin(x)`), independent of which route
        # would otherwise adjudicate it, so caught once here rather
        # than separately, differently, by each route's own
        # internal error path.
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; {bare_reserved!r} is reserved for its "
                          f"call form ({bare_reserved}(...)), not usable as a "
                          f"plain value, likely a missing call")
    # names the grammar also knows resolve by fixed precedence, a
    # parameter always wins over the vocabulary, a bare pi/e keeps its
    # mathematical meaning, and the resolution is STATED whenever a
    # claim actually uses such a name, never applied silently
    claim_names: set = set()
    for src in (cj.lhs, cj.rhs):
        if not src:
            continue
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError:
            continue
        # a norm's order (`norm(x, inf)`, the sugar's `||x||_inf`) is
        # not a bare name in the law, so it earns no constant note
        orders = {id(n.args[1]) for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "norm" and len(n.args) == 2
                  and isinstance(n.args[1], ast.Name)}
        claim_names |= {n.id for n in ast.walk(tree)
                        if isinstance(n, ast.Name) and id(n) not in orders}
    from ._math_vocab import _MATH_ATTRS
    from .grammar import reserved_names
    # a parameter shadowing a math constant (`pi`, `inf`) is noted once,
    # by `_shadowed_constants` with the spelling that still reaches the
    # constant, so those names are left out here
    vocab_names = (set(_MATH_ATTRS) | set(reserved_names()) | {"f"}) \
        - set(MATH_CONSTANTS)
    for name in sorted(claim_names & param_set & vocab_names):
        if name == "f":
            note = (f"{note}; 'f' names both the function under test and "
                    f"its own parameter here; a bare f reads as the "
                    f"parameter, f(...) as the call")
        else:
            note = (f"{note}; {name!r} here is f's own parameter, "
                    f"shadowing the grammar's {name}")
    for name in sorted((claim_names & set(_MATH_ATTRS))
                       - param_set - set(cj.domain or {})):
        note = f"{note}; bare {name!r} reads as the mathematical constant"
    for src in (cj.lhs, cj.rhs):
        # the security refusals (a dunder call, an attribute reach-in)
        # are facts about the claim's own text, not about either
        # route: caught here once so a best-route claim's derive
        # unknown can never outrank the refusal
        if not src:
            continue
        try:
            _validate(src, param_set, frozenset(cj.funcs or ()))
        except InvalidConjecture as e:
            if "disallowed" in str(e):
                return Probe(cj.name, statement, "skipped", route=None,
                             note=f"{note}; {e}")
    if fn is not None:
        # the TypeError a call that does not fit the signature raises
        # comes from the claim's own malformed text, never from the
        # function, so it can neither satisfy nor refute the claim
        sides = [cj.lhs] if cj.relation == "raises" else [cj.lhs, cj.rhs]
        try:
            pinned = frozenset(call_defaults(fn, cj)[1])
        except Exception:
            pinned = frozenset()
        for side in sides:
            mismatch = (_call_arity_mismatch(side, fn, param_set, pinned)
                        if side else None)
            if mismatch is not None:
                return Probe(cj.name, statement, "skipped:misspecified",
                             route=None, note=f"{note}; {mismatch}")
    if cj.relation == "raises" and fn is not None:
        if cj.rhs and _resolve_exception_type(cj.rhs, fn) is None:
            return Probe(cj.name, statement, "skipped:misspecified",
                         route=None,
                         note=f"{note}; unknown exception type "
                              f"{cj.rhs!r}: not a built-in exception, a "
                              f"dotted path to one, or a name on the "
                              f"module of {getattr(fn, '__name__', 'f')}")
    colliding = sorted(set(cj.ambiguous_diff_vars) & param_set)
    if colliding:
        # d(<expr>/d<var>)'s fraction sugar (grammar.
        # extract_diff_fraction_sugar) guessed a differentiation
        # variable by stripping a leading `d` off the literal
        # denominator name, if that literal name turns out to
        # also be a real parameter (a gibbs_free_energy(dh, t, ds)-
        # shaped function, say), the guess was never safe to make:
        # `d(expr/dh)` could mean either "divide by the real
        # parameter dh" or "differentiate with respect to h", and
        # only the function's own signature (known here, not at
        # parse time) can reveal the collision.
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; {colliding} could mean the real parameter "
                          f"or 'differentiate with respect to', "
                          f"d(expr/{colliding[0]}) is ambiguous here since "
                          f"{colliding[0]!r} is also a real parameter; use the "
                          f"explicit d(expr, {colliding[0][1:]}) form instead")
    cj_domain = {**domain, **cj.domain}   # inline quantifier wins
    for p in cj.domain or {}:
        # an int annotation completes a binding that states no type to
        # the integers (`[0, 10]` on `n: int` is `[0, 10] : int`)
        cj_domain[p] = _int_completed(cj_domain[p],
                                      facts.param_kinds.get(p))
    inferred_domain = _inferred_literal_domain(cj.lhs, facts.params)
    if cj.rhs:
        for p, bounds in _inferred_literal_domain(cj.rhs, facts.params).items():
            inferred_domain.setdefault(p, bounds)
    # a parameter the claim also names (`f(xs, y0) == f(xs, 0) + y0`) is
    # quantified, so a literal passed for it elsewhere pins nothing
    named = _names_in_text(cj.lhs) | _names_in_text(cj.rhs or "")
    inferred_domain = {p: b for p, b in inferred_domain.items()
                       if p not in cj_domain and p not in named}
    cj_domain = {**inferred_domain, **cj_domain}
    if inferred_domain:
        note = (f"{note}; inferred "
               + ", ".join(f"{p}={v[0]:g}" for p, v in sorted(inferred_domain.items()))
               + " from the claim's own literal argument")
    # the domains the parameters' own annotations, defaults and guards
    # state (`parameter_domain_facts`, the one reading every route
    # uses): an int annotation the integers, a Literal/Enum/bool its
    # stated values, a flag default the two bools, a guard to a set that
    # set, a registered adaptor its language, a str annotation the type
    # of strings; each fills a gap only (a stated domain always wins) and
    # is rendered here explicitly, never silently. Only a parameter the
    # claim reads is a coordinate; one it fills with a literal, or
    # leaves at its default, has nothing to infer
    read = _names_in_claim(cj)
    stated = {p: fact for p, fact in parameter_domain_facts(fn, facts).items()
              if p not in cj_domain and p in read}
    annotation_inferred = {p: b for p, (b, cat, _d) in stated.items() if cat == "int"}
    if annotation_inferred:
        cj_domain = {**annotation_inferred, **cj_domain}
        note = (f"{note}; inferred "
               + ", ".join(
                   f"{p} in Z"
                   for p in sorted(annotation_inferred))
               + " from its own "
               + "/".join(sorted({facts.param_kinds[p]
                                  for p in annotation_inferred}))
               + " annotation")
    literal_inferred = {p: b for p, (b, cat, _d) in stated.items()
                        if cat == "stated_values"}
    if literal_inferred:
        cj_domain = {**literal_inferred, **cj_domain}
        note = (f"{note}; inferred "
               + ", ".join(
                   p + " in {"
                   + ", ".join(repr(v) for v in sorted(vals, key=repr)) + "}"
                   for p, vals in sorted(literal_inferred.items()))
               + " from its own annotation's stated values")
    flag_inferred = {p: (b, d) for p, (b, cat, d) in stated.items() if cat == "flag"}
    if flag_inferred:
        cj_domain = {**{p: b for p, (b, _d) in flag_inferred.items()}, **cj_domain}
        note = (f"{note}; inferred "
               + ", ".join(f"{p} in {{False, True}} from its default "
                           f"{default!r}"
                           for p, (_b, default) in sorted(flag_inferred.items())))
    # a guard to a set is the working domain the guard leaves (decision
    # A); the record states it as such. A raises claim asks about the
    # inputs the guard refuses, outside that set, so it keeps its own
    # domain
    if cj.relation not in ("raises", "excluded_outside_domain"):
        cj_domain = {**{p: b for p, (b, cat, _d) in stated.items() if cat == "guard"},
                     **cj_domain}
    adaptor_inferred = {p: (b, d) for p, (b, cat, d) in stated.items()
                        if cat == "adaptor"}
    if adaptor_inferred:
        from .domain import render_domain
        cj_domain = {**{p: b for p, (b, _d) in adaptor_inferred.items()},
                     **cj_domain}
        note = (f"{note}; inferred "
               + ", ".join(
                   f"{p} in {render_domain(b, ascii_mode=True)} from its own "
                   f"{hint_text} annotation (adaptor {adaptor})"
                   for p, (b, (adaptor, hint_text))
                   in sorted(adaptor_inferred.items())))
    text_inferred = {p: (b, d) for p, (b, cat, d) in stated.items() if cat == "text"}
    if text_inferred:
        from .domain import render_domain
        cj_domain = {**{p: b for p, (b, _d) in text_inferred.items()}, **cj_domain}
        note = (f"{note}; inferred "
               + ", ".join(
                   f"{p} in {render_domain(b, ascii_mode=True)} from its own "
                   f"{hint_text} annotation"
                   for p, (b, hint_text) in sorted(text_inferred.items())))
    # a real parameter no binding names is read over the working
    # domain f's own guards leave (decision A); the record states it. A
    # raises claim asks about the inputs the guards refuse, so it keeps
    # the whole domain
    if cj.relation not in (*routes.examine_predicates(), "raises",
                           "excluded_outside_domain"):
        for p in facts.params:
            if p in read and p not in cj_domain:
                found = _unbound_working_bound(fn, facts, p)
                if found is not None and found[0] is not None:
                    cj_domain[p] = found[0]
    # canonical narrowing, at resolve time: the resolved domain IS the
    # canonical set (prover, records, and comparisons all use it); the
    # declared text stays the author's, and the collapse is rendered
    # here explicitly, never silently
    from .domain import bound_is_empty, canonical_bound, render_domain_bound
    for p, b in list(cj_domain.items()):
        canonical, declared_text = canonical_bound(b)
        if declared_text is not None:
            cj_domain[p] = canonical
            note = (f"{note}; {p}: declared {declared_text}, "
                    f"canonically {render_domain_bound(canonical)}")
    for p, b in cj_domain.items():
        # a reversed range is an empty domain: every claim over it is
        # vacuous, and adjudicating one as if it were real produces a
        # meaningless proof or a phantom falsification, refuse it
        # with the reason instead
        if isinstance(b, tuple) and not isinstance(b, frozenset) and len(b) == 2:
            try:
                lo, hi = float(b[0]), float(b[1])
            except (TypeError, ValueError):
                continue
            if lo > hi:
                return Probe(
                    cj.name, statement, "skipped:misspecified", route=None,
                    note=f"{note}; {p}'s declared range [{b[0]:g}, {b[1]:g}] "
                         f"is empty (the lower bound exceeds the upper), so "
                         f"every claim over it is vacuously true; state the "
                         f"intended bounds")
        if bound_is_empty(b):
            return Probe(
                cj.name, statement, "skipped:misspecified", route=None,
                note=f"{note}; {p}'s declared domain "
                     f"{render_domain_bound(b)} is empty (no value lies "
                     f"inside it), so every claim over it is vacuously "
                     f"true; state the intended bounds")
    free_var_collisions = sorted(set(cj.free_vars) & set(facts.params))
    if free_var_collisions:
        # `let name be bounds` (a free variable, no real parameter to
        # alias) and `for name in bounds` (a real parameter) share the
        # exact same underlying bound grammar, if the name declared
        # via `let` turns out to be a real parameter of this
        # particular fn anyway, that's harmless (cj_domain already
        # carries the same bound either way), so it adjudicates
        # exactly as if `for` had been used, just named explicitly
        # here rather than left for a reader to notice only by
        # comparing the claim's free_vars to fn's own signature.
        #
        # A real parameter's own kind (from its Python type
        # annotation, facts.param_kinds) is always the more
        # authoritative source of "what values are actually
        # possible" than a free variable's assumed-real default,
        # an int-typed [1, 100] and a float-typed [1, 100] aren't
        # close substitutes, one has 100 possible values and the
        # other infinitely many, so this isn't a cosmetic choice.
        # `Domain.explicit_type` (grammar.py) is the signal for
        # "assumed" vs "explicitly typed" here, whether the
        # binding's own text stated a type at all, independent of
        # its missing-value policy (missing-value inclusion/
        # exclusion no longer implies anything about whether a type
        # was stated, see grammar.py's own `parse_binding()`).
        # Assumed -> defer to the real kind (unwrap back to the
        # plain bound, exactly as an ordinary `for` binding would
        # carry it). Explicitly typed -> respect the deliberate
        # override, but only silently when it agrees with the real
        # kind; a disagreement (declaring an int-typed real float
        # parameter free, or vice versa) is flagged rather than left
        # for a reader to notice on their own.
        resolved = []
        for p in free_var_collisions:
            bound = cj_domain.get(p)
            explicit_type = isinstance(bound, Domain) and bound.explicit_type
            if isinstance(bound, Domain) and not explicit_type and len(bound.pieces) == 1:
                cj_domain[p] = bound.pieces[0]
                resolved.append(p)
            elif explicit_type:
                real_kind = facts.param_kinds.get(p)
                # facts.param_kinds' own vocabulary (analysis.py's
                # _param_kinds): "int"/"scalar"/"sequence"/"unknown".
                # Each base type maps to its own kind explicitly; a
                # type outside the table keeps its own name as the
                # kind, so a future type can disagree with a scalar
                # annotation instead of silently matching it.
                stated_kind = _stated_kind(bound)
                if not _kind_compatible(stated_kind, real_kind):
                    note = (f"{note}; let-declared free variable {p!r} states "
                           f"'{bound.base_type}' but the real parameter {p!r} "
                           f"is {real_kind!r}; the stated type is used as "
                           f"written, not silently reconciled")
        if resolved:
            note = (f"{note}; let-declared free variable(s) {resolved} "
                   f"match real parameter(s) of this function, deferred "
                   f"to the real parameter's own kind")
    ranks = _claim_array_ranks(cj_domain, fn, facts)
    complex_arrays = sorted(
        p for p, bound in cj_domain.items()
        if getattr(bound, "base_type", None) == "C"
        and getattr(bound, "dims", ()))
    if complex_arrays:
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; {', '.join(complex_arrays)} "
                          f"{'is' if len(complex_arrays) == 1 else 'are'} "
                          f"declared complex: matrices and vectors are "
                          f"real-only in this release")
    compared = list(cj.links or [(cj.lhs, cj.relation, cj.rhs)])
    premise = re.sub(r"^assuming\s+", "", (cj.assuming or "").strip())
    if premise and "-->" not in premise:
        for part in _split_top_and(premise):
            compared += [(a.lhs, a.relation, a.rhs)
                         for a in (_parse_assuming_links(part) or ())]
    for _lhs, _rel, _rhs in compared:
        refusal = linalg.matrix_ordering_reason(_rel, (_lhs, _rhs), ranks)
        if refusal is not None:
            return Probe(cj.name, statement, "skipped:misspecified",
                         route=None, note=f"{note}; {refusal}")
    if cj.relation in ("<=", ">=", "<", ">"):
        complex_typed = sorted(
            p for p, bound in cj_domain.items()
            if bound == "C" or getattr(bound, "base_type", None) == "C")
        if complex_typed:
            # mirrors the derive route's refusal of ordering over
            # opaque values: ordering was never meaningful to claim
            # over the complex plane, so no route should pretend to
            # adjudicate it.
            return Probe(cj.name, statement, "skipped", route=None,
                         note=f"{note}; ordering ({cj.relation}) isn't "
                              f"meaningful over the complex plane "
                              f"({', '.join(complex_typed)} ⊂ ℂ)")
    from .domain import KNOWN_BASE_TYPES, LanguageRef
    language_bound = {p: b for p, b in cj_domain.items()
                      if getattr(b, "base_type", None) == "L"}
    if language_bound:
        # every language a binding names resolves once, up front, so an
        # unknown name refuses here on both routes with the vocabulary,
        # and the resolved source is stated beside the claim; a
        # language whose members are not what the real parameter takes
        # is flagged, and the stated language is used as written
        from .languages import UnknownLanguage, resolve
        resolved_sources = []
        for p, b in sorted(language_bound.items()):
            for piece in b.pieces:
                if not isinstance(piece, LanguageRef):
                    continue
                try:
                    language, source = resolve(piece)
                except UnknownLanguage as e:
                    return _needs_language(cj, statement, note, e)
                resolved_sources.append(f"{p} in L[{piece.text}] ({source})")
                real_kind = facts.param_kinds.get(p)
                if not _kind_compatible(language.kind, real_kind):
                    note = (f"{note}; {p} is quantified over "
                            f"L[{piece.text}], whose members are "
                            f"{language.kind} values, but the real "
                            f"parameter {p!r} is {real_kind!r}; the stated "
                            f"language is used as written")
        note = f"{note}; " + ", ".join(resolved_sources)
    if getattr(cj.rhs_bound, "base_type", None) == "L":
        # a membership's right-hand language resolves up front too
        from .languages import UnknownLanguage, resolve
        for piece in cj.rhs_bound.pieces:
            if isinstance(piece, LanguageRef):
                try:
                    resolve(piece)
                except UnknownLanguage as e:
                    return _needs_language(cj, statement, note, e)
    strange_types = sorted(
        f"{p} ({bound.base_type})" for p, bound in cj_domain.items()
        if getattr(bound, "base_type", None) not in (None, *KNOWN_BASE_TYPES))
    if strange_types:
        # an unknown domain base type must refuse loudly on BOTH routes:
        # sampling a default range for it would silently ignore the
        # declared restriction, the exact silently-wrong-answer class
        # the derive route already refuses via InvalidDomain
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"{note}; unknown domain base type for "
                          f"{', '.join(strange_types)}: known types are "
                          f"{sorted(KNOWN_BASE_TYPES)}")
    unknown_keys = sorted(
        k for k in set(cj_domain) - set(facts.params) - set(cj.free_vars)
        # a dotted key quantifies a bundled parameter's field
        # (`self.rate`, `cfg.a`); its root must be a real parameter
        if not ("." in k and k.split(".", 1)[0] in facts.params))
    if unknown_keys:
        # a mistyped domain/quantifier variable used to be silently
        # ignored, neither route ever cross-checked cj_domain's
        # own keys against facts.params, so the claim's declared
        # restriction just never applied, with nothing to say so:
        # a claim could come back holds/falsified against an
        # unintentionally-unrestricted sample instead of an honest
        # skip. Checked once here, before either route dispatches,
        # covers both the per-claim quantifier and the function-
        # level domain= argument, since both are already merged
        # into cj_domain above.
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"{note}; domain key(s) {unknown_keys} don't match "
                          f"any real parameter (real parameters: "
                          f"{list(facts.params)})")
    undeclared = _undeclared_names(cj, _declared_names(cj, cj_domain, facts, fn))
    if undeclared:
        name = undeclared[0]
        return Probe(
            cj.name, statement, "skipped:misspecified", route=None,
            note=(f"{note}; undeclared name {name!r}: it is not a parameter "
                  f"of the function, not bound by `for` or `let`, and not a "
                  f"known constant or function; declare it with `let`, "
                  f"for example `let {name} be [0, 1], ...`"
                  + (f" (also undeclared: {', '.join(undeclared[1:])})"
                     if len(undeclared) > 1 else "")),
            meta={"mathema.invalid_conjecture": True})
    completed, missing_notes, refusal, resolution = _complete_missing(cj, fn)
    if refusal is not None:
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; {refusal}")
    if missing_notes:
        note = f"{note}; " + "; ".join(missing_notes)
    implied, implied_resolution = _implied_bindings(
        cj, fn, {p: k for p, k in facts.param_kinds.items()
                 if p in facts.params and p not in cj_domain})
    return _ClaimContext(cj=cj, statement=statement, note=note.lstrip("; "),
                         cj_domain=cj_domain, extra=frozenset(cj.funcs),
                         missing={**implied_resolution, **resolution},
                         record_domain={**implied, **completed},
                         implied=frozenset(implied))


def _admitted_scalar_points(ctx) -> list:
    """Intent:
        `[(param, word, value), ...]`: every missing value a scalar
        parameter's completed domain admits, realised with its
        resolution (`None` for absence, one value per hole member), in
        the order absence, then members; the points a proof's companion
        executes beside the domain's corners.
    """
    from .domain import (ABSENT, NO_ANNOTATION, _as_domain, _is_enumerated,
                         admitted, member, realise_sentinel)
    out: list = []
    for p, bound in (ctx.record_domain or {}).items():
        dom = _as_domain(bound)
        if not p.isidentifier() or dom.base_type == "L" or dom.dims \
                or _is_enumerated(dom):
            continue
        policy = ctx.missing.get(p, NO_ANNOTATION)
        absent, holes = admitted(dom, dom.policy)
        if absent:
            out += [(p, "None", v) for v in realise_sentinel(
                ABSENT, policy.members, policy.absence)]
        for h in holes:
            for word in (policy.members if h.member is None else (h.member,)):
                out += [(p, word, v) for v in realise_sentinel(member(word))]
    return out


def _listed_sentinels_fail(ctx, fn, facts, cj_domain: dict, bound_funcs,
                           assumption, statement: str, note: str) -> "Probe | None":
    """Intent:
        After a proof over the reals, the claim's own listed sentinels
        executed: every sentinel an enumerated binding lists
        (`{0.25, None}`, `{missing}`) belongs to the claim's point set,
        so the function is called at each, against in-domain points of
        the other parameters (their domain corners), and a raise or a
        failing relation there falsifies the claim itself. Returns a
        falsified `Probe` naming the first failing point, listed
        sentinels in the order absence, the class, then members; a
        `Probe` carrying only `meta["mathema.missing"]["tried"]` when
        every one holds; None when the claim lists none or its points
        cannot be evaluated here.
    """
    from .domain import (ABSENT, NO_ANNOTATION, _as_domain, _is_enumerated,
                         _member_sort_key, _set_sentinels, realise_sentinel)
    from .gates import _fmt_point, _point_evaluator
    from .runtime_types import calling
    listed: dict = {}
    for p, bound in (cj_domain or {}).items():
        dom = _as_domain(bound)
        if not p.isidentifier() or dom.base_type == "L" or not _is_enumerated(dom):
            continue
        sentinels = sorted(set(_set_sentinels(dom)), key=_member_sort_key)
        if not sentinels:
            continue
        policy = ctx.missing.get(p, NO_ANNOTATION)
        listed[p] = [(s, v) for s in sentinels
                     for v in realise_sentinel(s, policy.members, policy.absence)]
    if not listed:
        return None
    deps = _point_evaluator(ctx.cj, calling(fn, facts), facts, cj_domain,
                            bound_funcs, assumption)
    if deps is None:
        return None
    names = list(deps["names"])
    bases = [c for c in deps["corners"][:8] if deps["admits"](c)] or deps["corners"][:1]
    tried: dict = {}
    failures: list = []
    for p, values in listed.items():
        if p not in names:
            continue
        for sentinel, value in values:
            tried.setdefault(p, []).append(repr(value))
            for base in bases:
                point = {**base, p: value}
                if deps["evaluate"](point) is False:
                    rank = (0 if sentinel == ABSENT else 1 if sentinel.member is None
                            else 2)
                    failures.append((rank, point))
                    break
    from .probing import executed_missing, with_executed
    meta = with_executed({"mathema.missing": {"tried": tried}},
                         executed_missing(deps)) or {}
    if not failures:
        return Probe(ctx.cj.name, statement, "proven", meta=meta)
    point = sorted(failures, key=lambda f: f[0])[0][1]
    witness = _fmt_point(point, names)
    from ._brute_force import _raised_at
    raised = _raised_at(calling(fn, facts), facts, point)
    return Probe(ctx.cj.name, statement, "falsified", route="derive",
                 counterexample=witness, note=note,
                 sketch=(f"the real members are proven, and the claim's own "
                         f"listed point {witness} fails"
                         + (f": the function raised {raised}" if raised else "")),
                 meta={**meta, "mathema.corroboration": "reproduced",
                       "mathema.witness_executed": True})


def _container_holes(p: str, record, resolution: dict) -> tuple:
    """Intent:
        `(absent, holes)` for a container parameter: whether its
        completed domain admits the container itself absent, and the
        realised hole values its slots admit, one per member the
        resolution names (`[None, nan]` for a list).
    """
    from .domain import NO_ANNOTATION, _as_domain, admitted, member, realise_sentinel
    if record is None:
        return False, []
    dom = _as_domain(record)
    absent, admitted_holes = admitted(dom, dom.policy)
    policy = resolution.get(p, NO_ANNOTATION)
    words = [w for h in admitted_holes
             for w in (policy.members if h.member is None else (h.member,))]
    holes: list = []
    for w in dict.fromkeys(words):
        holes += realise_sentinel(member(w))
    return bool(absent), holes


def _admitted_container_points(ctx, facts) -> tuple:
    """Intent:
        `(points, holes)` for a proof's companion: `points` the floor of
        every vector, matrix and table parameter as `(param, word,
        value)`, `word` the hole member the value holds (`None` for the
        container absent, None for an item holding no hole), each built
        from a fixed small draw inside the element domain; `holes` the
        realised hole values each container's slots admit.
    """
    import random as _random

    from . import _floor
    from ._missing_policy import keys_of
    from ._sampling import _RNG_SEED
    from .domain import domain_contains
    rng = _random.Random(_RNG_SEED)
    points: list = []
    holes_of: dict = {}
    for p in facts.params:
        kind = facts.param_kinds.get(p, "unknown")
        bound = (ctx.cj_domain or {}).get(p)
        if kind not in SEQUENCE_KINDS and kind != "table":
            continue
        if bound is not None and getattr(bound, "base_type", None) == "L":
            continue
        absent, holes = _container_holes(p, (ctx.record_domain or {}).get(p),
                                         ctx.missing or {})
        try:
            admits_zero = bound is None or bool(domain_contains(0.0, bound))
        except Exception:
            admits_zero = False
        dims = tuple(getattr(bound, "dims", ()) or ())
        fixed = _floor.fixed_sizes(bound)
        if kind == "table":
            (length,) = _floor.sizes(bound, rng, (3, 3))
            base = {c: [_synth("float", rng,
                               _column_bound((ctx.cj_domain or {}).get(f"{p}.{c}"), bound))
                        for _ in range(length)]
                    for c in _table_columns(p, ctx.cj, facts)}
            floor = _floor.table_floor(holes, absent=absent)
        elif len(dims) >= 2:
            square = len(set(dims[:2])) == 1
            n_rows, n_cols = _floor.sizes(bound, rng, (2, 2) if square else (2, 3), 2)
            if not square and fixed[1:2] == (None,):
                n_cols = 3
            base = [[_synth("float", rng, bound) for _ in range(n_cols)]
                    for _ in range(n_rows)]
            floor = _floor.matrix_floor(holes, admits_zero, absent=absent)
        else:
            (length,) = _floor.sizes(bound, rng, (3, 3))
            base = [_synth("float", rng, bound) for _ in range(length)]
            floor = _floor.vector_floor(holes, admits_zero,
                                        length_free=not any(fixed), absent=absent)
        for item in floor:
            value = item(base)
            if value is None:
                continue
            if isinstance(value, _floor._Absent):
                points.append((p, "None", None))
                continue
            keys = keys_of({p: value})
            points.append((p, keys[0][2] if keys else None, value))
        if holes:
            holes_of[p] = holes
    return points, holes_of


def _column_bound(bound, table_bound):
    """The element domain a table column is drawn from: its own binding's
    element domain when the claim binds the column, else the table's."""
    if bound is None:
        return table_bound
    from dataclasses import replace as _replace
    if getattr(bound, "dims", ()):
        return _replace(bound, dims=())
    return bound


def _call_by_name(fn, point: dict, extra: "dict | None" = None):
    """`fn` called at the arguments `point` names, and `extra` for the
    parameters it does not: a positional-only parameter (`math.sqrt`'s
    `x`), or any argument of a callable with no signature, is passed by
    position in the point's order, the rest by name."""
    import inspect
    rest = {p: v for p, v in (extra or {}).items() if p not in point}
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(*point.values(), **rest)
    positional = [p for p, prm in params.items()
                  if prm.kind is inspect.Parameter.POSITIONAL_ONLY and p in point]
    return fn(*[point[p] for p in positional],
              **{p: v for p, v in point.items() if p not in positional}, **rest)


def _refill_caller(fn_call, pins: "dict | None" = None):
    """`call_at(point, given)`: f called at its arguments by name, each
    argument the original call gave (`given`, its positional and keyword
    arguments) and the point does not name passed as given, and each
    pinned parameter at its pin, giving `(output, raised)`; for reading
    what f did with a hole by filling it."""
    import inspect

    def call_at(point: dict, given: "tuple | None" = None):
        extra = dict(pins or {})
        if given is not None:
            try:
                sig = inspect.signature(fn_call)
                named = {n for n, prm in sig.parameters.items()
                         if prm.kind not in (prm.VAR_POSITIONAL, prm.VAR_KEYWORD)}
                extra.update({n: v for n, v in sig.bind_partial(
                    *given[0], **given[1]).arguments.items() if n in named})
            except (TypeError, ValueError):
                pass
        try:
            return _call_by_name(fn_call, point, extra), None
        except Exception as exc:
            return None, type(exc).__name__
    return call_at


def _nan_filled(value, fill: float):
    """`value` with every nan in it replaced by `fill`: a float, a list
    or tuple (nested), or a float numpy array; anything else as it is."""
    import math
    if isinstance(value, float):
        return fill if math.isnan(value) else value
    if isinstance(value, (list, tuple)):
        return type(value)(_nan_filled(v, fill) for v in value)
    if hasattr(value, "dtype") and getattr(value.dtype, "kind", "") == "f":
        import numpy as np
        return np.where(np.isnan(value), fill, value)
    return value


def _fill_value(bound):
    """Intent:
        An interior point of a parameter's domain (a container's element
        domain), for filling a hole whose argument holds no present value
        to read what f did with it: the midpoint of a bounded domain, one
        in from the finite end of a half-bounded one, 1.0 on the whole
        line, the smallest member of a finite set. None for a domain with
        no real value (a language, `{missing}` alone).
    """
    import math
    from dataclasses import replace as _replace

    from .domain import bound_to_sympy_set, domain_contains
    if bound is not None and getattr(bound, "base_type", None) in ("L", "S"):
        return None
    if bound is not None and getattr(bound, "dims", ()):
        bound = _replace(bound, dims=())
    if bound is None:
        return 1.0
    try:
        import sympy
        region = bound_to_sympy_set(bound)
        lo, hi = float(region.inf), float(region.sup)
        integral = bool(region.is_subset(sympy.S.Integers))
    except Exception:
        return None
    if math.isinf(lo) and math.isinf(hi):
        point = 1.0
    elif math.isinf(hi):
        point = lo + 1.0
    elif math.isinf(lo):
        point = hi - 1.0
    else:
        point = (lo + hi) / 2.0
    if integral:
        point = float(math.floor(point))
        for candidate in (point, point + 1.0, lo, hi):
            if domain_contains(int(candidate), bound):
                return int(candidate)
        return None
    if domain_contains(point, bound):
        return point
    return lo if domain_contains(lo, bound) else None


def _container_draws(p: str, kind: str, bound, record, resolution: dict,
                     resolver, shared: bool, structured: bool):
    """Intent:
        The `_floor.ContainerDraws` of one vector, matrix or table
        parameter: its floor (the degenerate containers, every admitted
        hole member in it, and a vector's magnitude corners) and the
        holes its random draws carry; None
        for a parameter that is not a container, or one drawn from a
        language or with a structure a floor item would break.
    """
    from . import _floor
    from .domain import domain_contains
    if bound is not None and getattr(bound, "base_type", None) == "L":
        return None
    shape = resolver.shapes.get(p)
    if kind == "table":
        form = "table"
    elif structured:
        return None
    elif shape is not None and shape.ndim >= 2:
        form = "mat"
    elif kind in SEQUENCE_KINDS or (shape is not None and shape.ndim == 1):
        form = "vec"
    else:
        return None
    absent, holes = _container_holes(p, record, resolution)
    try:
        admits_zero = bound is None or bool(domain_contains(0.0, bound))
    except Exception:
        admits_zero = False
    if form == "vec":
        from .probing import sequence_corners
        floor = _floor.vector_floor(holes, admits_zero, length_free=not shared,
                                    absent=absent)
        # the magnitude corners of the completed element range, after
        # the degenerate containers
        floor += _floor.corner_floor(
            sequence_corners(record if record is not None else bound),
            length_free=not shared)
    elif form == "mat":
        floor = _floor.matrix_floor(holes, admits_zero, absent=absent)
    else:
        from .probing import sequence_corners
        floor = _floor.table_floor(holes, absent=absent)
        # each column meets the magnitude corners of the completed
        # element range, after the degenerate tables
        floor += _floor.table_corner_floor(
            sequence_corners(record if record is not None else bound))
    return _floor.ContainerDraws(form, floor, holes)


def _asks_missing(cj) -> bool:
    """Whether a membership claim's right-hand side names a missing value
    (`in {missing}`, `in {nan}`, `in {None}`)."""
    from .domain import _as_domain, _set_sentinels
    bound = getattr(cj, "rhs_bound", None)
    if cj.relation not in ("in", "not in") or bound is None:
        return False
    try:
        return bool(_set_sentinels(_as_domain(bound)))
    except Exception:
        return False


def _lists_sentinel(bound) -> bool:
    """Whether a written binding lists a sentinel in a finite set (`{0.25,
    None}`, `{missing}`), the claim's own point rather than one its type
    admits."""
    from .domain import _as_domain, _is_enumerated, _set_sentinels
    if bound is None:
        return False
    try:
        dom = _as_domain(bound)
        return _is_enumerated(dom) and bool(_set_sentinels(dom))
    except Exception:
        return False


def _missing_laps(rng, kinds: dict, cj_domain: dict, resolution: dict,
                  record_domain: "dict | None" = None) -> dict:
    """Intent:
        `{param: _SpecialCycle}` for every parameter whose domain admits
        a sentinel: a finite set's listed sentinels, and for a scalar
        the sentinels its completed domain admits (a `float` slot's
        `nan`, an `Optional` parameter's `None`), each realised with the
        parameter's resolution (`None`, or its absence spellings, for
        absence; one value per member for the class), dispensed in
        order before any random draw. A vector's holes are drawn by the
        gap draws, not here.
    """
    from .domain import (ABSENT, NO_ANNOTATION, _as_domain, _is_enumerated,
                         _member_sort_key, _set_sentinels, admitted,
                         realise_sentinel)
    from .probing import _SpecialCycle
    out: dict = {}
    waiting = 0
    for p, kind in kinds.items():
        bound = cj_domain.get(p)
        if bound is None:
            bound = (record_domain or {}).get(p)
        if bound is None:
            continue
        dom = _as_domain(bound)
        if dom.dims:
            continue
        if dom.base_type == "L":
            # a language admits no hole of its own; an absence it admits
            # (`L[unicode] | {None}`) is drawn first
            record = _as_domain((record_domain or {}).get(p) or bound)
            if admitted(record, record.policy)[0] or getattr(dom, "absent", False):
                out[p] = _SpecialCycle(rng, values=[], first=[None])
            continue
        if _is_enumerated(dom):
            listed = sorted(set(_set_sentinels(dom)), key=_member_sort_key)
        elif (record_domain or {}).get(p) is not None \
                and kind not in (*SEQUENCE_KINDS, "dict", "table", "string"):
            record = _as_domain(record_domain[p])
            absent, holes = admitted(record, record.policy)
            listed = ([ABSENT] if absent else []) + sorted(set(holes),
                                                           key=_member_sort_key)
        else:
            continue
        if not listed:
            continue
        policy = resolution.get(p, NO_ANNOTATION)
        values = [v for s in listed
                  for v in realise_sentinel(s, policy.members, policy.absence)]
        if values:
            # each parameter's sentinels come after the ones before it,
            # so one missing input is drawn at a time
            from ._sampling import WAIT
            if _is_enumerated(dom):
                out[p] = _SpecialCycle(rng, values=[], first=values)
            else:
                out[p] = _SpecialCycle(rng, values=[], first=[WAIT] * waiting + values)
                waiting += len(values)
    return out


def _in_field_type(path: str, bound, cj_domain: dict):
    """Intent:
        A path binding's bound in the type of the field it reaches, when
        the root's language states that field as whole numbers (`o.qty
        in [1, 3]` over an int field reads `[1, 3] : int`); the bound
        unchanged otherwise, or when the bound states its own type.
    """
    import dataclasses

    from .domain import Domain, _as_domain
    if getattr(bound, "explicit_type", False):
        return bound
    plain_domain = (isinstance(bound, Domain) and bound.base_type == "R"
                    and not bound.dims)
    if not (isinstance(bound, tuple) or plain_domain):
        return bound
    root, _, rest = path.partition(".")
    if "[" in root:
        root, _, rest = path.partition("[")
        rest = "[" + rest
    fields = _language_field_bounds({root: cj_domain.get(root)}).get(root)
    if not fields:
        return bound
    try:
        field_bound = _path_bound(root, rest.lstrip("."), fields, {})
    except Exception:
        return bound
    base = getattr(_as_domain(field_bound), "base_type", None) \
        if field_bound is not None else None
    if base in ("Z", "N"):
        if isinstance(bound, Domain):
            return dataclasses.replace(bound, base_type="Z", explicit_type=True)
        return Domain(base_type="Z", pieces=(bound,), explicit_type=True)
    return bound


#: how a refusal names a slot type that holds no hole
_NO_HOLE_NAMES = {"str": "string"}


def _missing_record(domain: dict) -> dict:
    """Intent:
        What a record states about the missing values its bindings
        admit: `{"admitted": {param: {"absent": bool, "missing": [member,
        ...]}}}`; the route that executes a missing value adds what it
        tried.
        Empty when no binding admits one.
    """
    from .domain import _as_domain, admitted
    out: dict = {}
    tried: dict = {}
    for p, bound in (domain or {}).items():
        if not p.isidentifier():
            continue
        dom = _as_domain(bound)
        absent, holes = admitted(dom, dom.policy)
        if not absent and not holes:
            continue
        words = []
        for h in holes:
            words += list(dom.members) if h.member is None else [h.member]
        out[p] = {"absent": absent, "missing": list(dict.fromkeys(words))}
    if not out:
        return {}
    return {"admitted": out, **({"tried": tried} if tried else {})}


def _missing_means(admitted: dict, resolution: dict) -> str:
    """`missing for x (float) means nan`, one clause per parameter whose
    domain admits a hole, naming the slot type and its members."""
    parts = []
    for p, entry in admitted.items():
        members = entry.get("missing") or []
        if not members:
            continue
        slot = getattr(resolution.get(p), "slot_type", None) or "unannotated"
        words = (" or ".join(members) if len(members) <= 2
                 else ", ".join(members[:-1]) + " or " + members[-1])
        parts.append(f"missing for {p} ({slot}) means {words}")
    return "; ".join(parts)


def _annotation_words(fn, param: str) -> "str | None":
    """A parameter's annotation as it reads in source (`Optional[float]`),
    or None when it has none."""
    import inspect
    try:
        ann = inspect.signature(fn).parameters[param].annotation
    except (TypeError, ValueError, KeyError):
        return None
    if ann is inspect.Parameter.empty:
        return None
    from ._annotation_text import annotation_text
    return annotation_text(ann)


def _missing_origin(param: str, kind: str, written: dict, resolution: dict) -> str:
    """Who admitted a kind for a parameter: `listed` (a finite set the
    claim lists), `written` (a `|missing` or `|absent` the claim
    writes), `optional` (an `Optional` annotation), else `type`."""
    from .domain import _as_domain, _is_enumerated
    bound = written.get(param)
    if bound is not None:
        mine = [v for v in _written_sentinels(bound)
                if v.kind == kind and v not in getattr(bound, "excluded", ())]
        absent_written = kind == "absent" and bool(getattr(bound, "absent", False))
        if mine or absent_written:
            try:
                enumerated = _is_enumerated(_as_domain(bound))
            except Exception:
                enumerated = False
            return "listed" if enumerated else "written"
    policy = resolution.get(param)
    if kind == "absent" and policy is not None and policy.annotated and policy.absent:
        return "optional"
    return "type"


def _missing_told(missing: dict, written: dict, resolution: dict, fn) -> str:
    """Intent:
        One sentence per missing input the row executed: what the
        function did there. What to do about it is said once, on the
        policy row.
    """
    from ._missing_words import mixed_sentence
    said = missing.get("said") or {}
    behaviour = missing.get("behaviour") or {}
    mixed = missing.get("mixed") or {}
    raised_as = missing.get("raised") or {}
    parts = []
    returned = missing.get("returned") or {}
    if returned.get("absent") == "introduces":
        parts.append(f"f returns None at {returned.get('at')}, which its return type "
                     f"{returned.get('declared')} allows; that point has no value to "
                     f"compare, so it is recorded, not judged")
    for p, members in said.items():
        seen = behaviour.get(p, {})
        slot_type = getattr(resolution.get(p), "slot_type", "") or ""
        container = slot_type not in ("", "float", "complex", "datetime", "int",
                                      "bool", "str", "object", "unannotated")
        mixed_members = {m: mixed.get(p, {}).get(m, {}) for m, b in seen.items()
                         if b == "mixed"}
        if mixed_members:
            # a parameter treated more than one way is said once, by
            # behaviour, the member that differs named as the exception
            parts.append(mixed_sentence(p, mixed_members, raised_as.get(p, {}),
                                        _CONTAINER_NOUNS.get(slot_type, "container")
                                        if container else None))
        for member, sentence in members.items():
            if seen.get(member) == "mixed":
                continue
            parts.append(sentence)
    return "; ".join(parts)


#: what a note calls a container of each runtime type
_CONTAINER_NOUNS = {"pandas.Series": "series", "polars.Series": "series",
                    "numpy.ndarray": "array", "list": "list",
                    "pandas.DataFrame": "table", "polars.DataFrame": "table"}


def _renders(cj) -> bool:
    """Whether a conjecture has a canonical text."""
    from .spec import canonical_claim_text
    try:
        canonical_claim_text(cj)
    except Exception:
        return False
    return True


def _written_sentinels(bound) -> list:
    """Every sentinel a binding's own text wrote: admitted in a piece or
    a set, or excluded."""
    from .domain import is_sentinel
    found = [v for v in getattr(bound, "excluded", ()) if is_sentinel(v)]
    pieces = (bound,) if isinstance(bound, frozenset) else getattr(bound, "pieces", ())
    found += [v for piece in pieces if isinstance(piece, frozenset)
              for v in piece if is_sentinel(v)]
    return found


def _for_element_domain(defaults, bound):
    """Intent:
        The defaults with the hole members an element domain of that
        number type can hold: a real, integer or complex domain holds no
        `NaT`, which only a datetime slot holds, whatever the container.
    """
    from dataclasses import replace
    base = getattr(bound, "base_type", None) or (
        "R" if isinstance(bound, tuple) else None)
    if isinstance(bound, str):
        base = bound
    if base in ("R", "Z", "N", "C") and "NaT" in defaults.members \
            and defaults.slot_type != "datetime":
        return replace(defaults, members=tuple(m for m in defaults.members
                                               if m != "NaT"))
    return defaults


_IMPLIED_KINDS = frozenset({"scalar", "int", "sequence", "vec", "mat", "table"})


def _implied_bindings(cj, fn, kinds: dict) -> tuple:
    """Intent:
        `(completed, resolution)` for each parameter a claim names
        without binding it (`f(x) == 2*x + 1`): its domain completed from
        its annotation as `for x in R` (`for xs in R^n` for a container)
        would be, so the claim draws the holes and absence the signature
        admits. Only an annotated parameter of a number, container or
        table kind whose annotation admits a kind takes part; the claim's
        own text is not changed by it.
    """
    from .domain import Domain, complete
    from .types import missing_policy_from_signature
    if fn is None:
        return {}, {}
    names: set = set()
    calls = False
    for src in _claim_sides(cj) + [a for a in (cj.assuming or "",) if a]:
        text = re.sub(r"^\s*assuming\s+", "", str(src))
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError:
            continue
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        calls |= any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == "f" for n in ast.walk(tree))
    if not calls:
        return {}, {}
    bound = set(cj.domain or {}) | set(cj.free_vars or ())
    policy = missing_policy_from_signature(fn)
    completed: dict = {}
    resolution: dict = {}
    for p, kind in kinds.items():
        defaults = policy.get(p)
        if p in bound or p not in names or kind not in _IMPLIED_KINDS \
                or defaults is None or not defaults.annotated \
                or not (defaults.absent or defaults.members):
            continue
        dims = () if kind in ("scalar", "int") else ("n",)
        written = Domain(base_type="R", explicit_type=True, dims=dims)
        defaults = _for_element_domain(defaults, written)
        completed[p] = complete(written, defaults)
        resolution[p] = defaults
    return completed, resolution


def _as_domain_or_none(bound):
    """A binding as a Domain, or None for no binding."""
    from .domain import _as_domain
    return None if bound is None else _as_domain(bound)


def _int_completed(bound, kind: "str | None"):
    """Intent:
        A real binding that states no type, completed to the integers
        when its parameter is annotated `int` (`[0, 10]` on `n: int` is
        `[0, 10] : int`); any other binding unchanged. A type the claim
        states wins.
    """
    from dataclasses import replace

    from .domain import _as_domain
    if kind != "int" or bound is None or isinstance(bound, (str, frozenset)):
        return bound
    dom = _as_domain(bound)
    if dom.explicit_type or dom.base_type != "R" or dom.dims \
            or not dom.pieces \
            or any(isinstance(piece, frozenset) for piece in dom.pieces):
        return bound
    return replace(dom, base_type="Z", explicit_type=True)


def _complete_missing(cj, fn) -> tuple:
    """Intent:
        Each of the claim's own bindings completed from its parameter's
        annotation (`domain.complete`), with what the record says about
        it: `(completed, notes, refusal, resolution)`. `completed` maps
        every binding to its completed domain (the claim's canonical
        text renders it), `notes` states each resolution ("missing for
        x (float): nan") and where a written clause widens or narrows
        the annotation, `refusal` is the reason a binding cannot be
        adjudicated (the hole class listed on a string slot, which has
        no hole) or None, and `resolution` is `{param: MissingDefaults}`.
    """
    from .domain import (NO_ANNOTATION, PATH_DEFAULTS, MissingDefaults, admitted,
                         complete, is_sentinel)
    from .types import missing_policy_from_signature
    policy = missing_policy_from_signature(fn) if fn is not None else {}
    completed: dict = dict(cj.domain or {})
    notes: list = []
    resolution: dict = {}
    for p, bound in (cj.domain or {}).items():
        if "." in p or "[" in p:
            completed[p] = complete(_in_field_type(p, bound, cj.domain),
                                    PATH_DEFAULTS)
            continue
        # a claim's own constant (`let c be [-5, 5]`) is a number the
        # claim draws, never a value the function receives, so it admits
        # nothing missing
        defaults = (MissingDefaults(False, (), "constant", annotated=False)
                    if p in (cj.free_vars or ())
                    else policy.get(p, NO_ANNOTATION))
        defaults = _for_element_domain(defaults, bound)
        # a domain already completed carries the exclusions completion
        # added; only a binding's own text is checked for holes
        from .domain import ABSENT_UNSET, unset_refusal
        if ABSENT_UNSET in _written_sentinels(bound):
            # a call always passes a parameter
            return completed, notes, unset_refusal(p), resolution
        written_holes = [] if getattr(bound, "policy", None) is not None else [
            v for v in _written_sentinels(bound) if v.kind == "missing"]
        if written_holes and not defaults.members:
            # a hole written on a slot type that holds none
            what = _NO_HOLE_NAMES.get(defaults.slot_type, defaults.slot_type)
            article = "an" if what[:1] in "aeiou" else "a"
            return completed, notes, (f"{p} is {article} {what}, and {article} {what} "
                                      f"has no hole; to admit its absence write "
                                      f"`|absent`"), \
                resolution
        foreign = sorted({v.member for v in written_holes
                          if v.member is not None and v.member not in defaults.members})
        if foreign:
            return completed, notes, (
                f"a {defaults.slot_type} slot holds no {', '.join(foreign)}, so "
                f"{p} cannot hold it; its holes are "
                f"{', '.join(defaults.members)}"), resolution
        stated = _as_domain_or_none(bound)
        if defaults.annotated and stated is not None and stated.explicit_type:
            # a type the claim states wins over the annotation's, and the
            # record says which way it moves
            if defaults.slot_type == "int" and stated.base_type == "R":
                notes.append(f"the claim widens the type of {p} from int "
                             f"to the reals")
            elif defaults.slot_type == "float" and stated.base_type in ("Z", "N"):
                notes.append(f"the claim narrows the type of {p} from float "
                             f"to the integers")
        bound = _int_completed(bound, defaults.slot_type
                               if defaults.annotated else None)
        done = complete(bound, defaults)
        completed[p] = done
        resolution[p] = defaults
        absent, holes = admitted(done)
        written = (getattr(bound, "explicit_type", False)
                   or getattr(bound, "absent", False)
                   or any(is_sentinel(v) for v in getattr(bound, "excluded", ()))
                   or any(is_sentinel(v) for piece in getattr(bound, "pieces", ())
                          if isinstance(piece, frozenset) for v in piece)
                   or (isinstance(bound, frozenset)
                       and any(is_sentinel(v) for v in bound)))
        if defaults.annotated and written:
            claim_holes = bool(holes)
            widens = ((absent and not defaults.absent)
                      or (claim_holes and not defaults.members))
            narrows = ((defaults.absent and not absent)
                       or (bool(defaults.members) and not claim_holes))
            enumerated = isinstance(bound, frozenset) or (
                not getattr(bound, "explicit_type", False)
                and all(isinstance(pc, frozenset)
                        for pc in getattr(bound, "pieces", ()) or (None,)))
            ann = _annotation_words(fn, p) or defaults.slot_type
            if widens:
                added = (f"{p} = None" if absent and not defaults.absent
                         else f"a missing {p}")
                notes.append(f"{added} is outside the type {ann}, and the claim adds it")
            elif narrows and not enumerated:
                lost = ("absence" if defaults.absent and not absent else "a missing value")
                gone = (f"{p} = None" if defaults.absent and not absent
                        else f"a missing {p}")
                notes.append(f"the claim excludes {lost}, which {p}'s type {ann} "
                             f"admits; the claim no longer covers {gone}")
    return completed, notes, None, resolution


def replace_proof(proof, status: str, sketch: str):
    """Intent:
        A ProofResult with its decision inverted for a not-form claim,
        keeping meta; the witness swaps roles (a counterexample to the
        positive claim is support for the negation, so it moves into
        the sketch rather than staying a counterexample).
    """
    from .symbolic._proof_support import ProofResult
    return ProofResult(status, sketch=sketch,
                       counterexample=(proof.sketch if status == "disproven" else None),
                       quantifier=proof.quantifier, meta=dict(proof.meta))


def _provenance_meta(proof) -> dict:
    """Intent:
        The proof-mechanism provenance worth carrying onto the output
        record: the deciding mechanism and, when two engines disagreed
        about the same integral, the structured account of who said
        what and who refereed.

    Notes:
        Both keys are optional record decoration, internal to mathema
        and its siblings; the spec-level evidence statement is the
        `route` field; nothing external should rely on these.
    """
    meta = {}
    for key in ("mathema.derive_route", "mathema.engine_disagreement",
                "mathema.missing", "mathema.path_no_value",
                "mathema.matrix_lemmas",
                "mathema.corroboration", "mathema.corroboration_unexecutable",
                "mathema.corroboration_reason", "mathema.definitions"):
        if key in proof.meta:
            meta[key] = proof.meta[key]
    return meta


# the soundness gates live in mathema/gates.py, beside the
# corroboration engine they drive
from .gates import (  # noqa: E402
    FLOAT_FAMILY as FLOAT_FAMILY,
    MATH_ONLY_ROUTE as MATH_ONLY_ROUTE,
    companion_name as companion_name,
    _EXTREME as _EXTREME,
    _corroboration_gate as _corroboration_gate,
    _float_companion as _float_companion,
    _fmt_point as _fmt_point,
    _point_evaluator as _point_evaluator,
)

def _stmt_lines(nodes) -> set:
    """Every statement's line number under the given AST nodes."""
    return {stmt.lineno for node in nodes for stmt in ast.walk(node)
            if isinstance(stmt, ast.stmt)}


def _derive_line_coverage(fn, facts, domain):
    """The body statement lines a derive proof over `domain` actually
    covers: the whole body MINUS the branches `domain` proves
    unreachable (a domain-restricted proof never reasons about a branch
    its domain excludes). Returns `None` (read by the caller as 'the
    whole body') when there are no branches, no domain restriction, or
    the branch analysis cannot resolve every pruned branch to lines, so
    the derive coverage stays all-or-nothing there rather than
    under-counting on a partial analysis. This is provenance for the
    implementation-coverage pass, never a verdict."""
    tree = getattr(facts, "tree", None)
    if tree is None or not domain:
        return None
    ifs = [n for n in ast.walk(tree) if isinstance(n, ast.If)]
    if not ifs:
        return None
    try:
        from .symbolic import _bind_params, _unmodified_params
        from .symbolic._conditioned import (_affine_locals,
                                            _branch_condition_truth)
        unmodified = _unmodified_params(tree, set(facts.params))
        params, _aggregate = _bind_params(fn, facts)
        affine = _affine_locals(tree, unmodified, params)
        dead: set = set()
        for node in ifs:
            truth = _branch_condition_truth(node.test, domain, unmodified,
                                            affine, params)
            if truth is True:                 # the else is unreachable
                dead |= _stmt_lines(node.orelse)
            elif truth is False:              # the if-body is unreachable
                dead |= _stmt_lines(node.body)
    except Exception:
        return None
    if not dead:
        return None                           # nothing pruned: whole body
    live = _stmt_lines([tree]) - dead
    # facts.tree's line numbers are 1-based within the function's own
    # source block; map them to absolute FILE lines so the coverage pass
    # (which works in file lines) can intersect them.
    try:
        first_line = inspect.getsourcelines(fn)[1]
    except (OSError, TypeError):
        return None
    return {first_line - 1 + ln for ln in live}


def _adjudicate_examined(ctx: "_ClaimContext", fn, facts) -> "Probe":
    """Intent:
        The row for a family decided by examination alone: proven,
        falsified with the examined site as the witness, or unknown with
        what could not be read, on the examine route.
    """
    cj, statement, note = ctx.cj, ctx.statement, ctx.note
    derive = ctx.family.routes()["derive"]
    try:
        proof = families.call_route(derive, fn, facts, cj.lhs, cj.rhs,
                                    cj.relation, domain=ctx.cj_domain,
                                    tolerance=cj.tolerance)
    except TimeoutError:
        raise
    except Exception as exc:
        return Probe(cj.name, statement, "unknown", route="examine",
                     note=f"{note}; the examination failed: "
                          f"{type(exc).__name__}: {exc}".lstrip("; "))
    if proof is not None and cj.negated:
        if proof.status == "proven":
            proof = replace_proof(proof, "disproven",
                                  "the positive claim is proven, so its "
                                  "negation is falsified: " + (proof.sketch or ""))
        elif proof.status == "disproven":
            proof = replace_proof(proof, "proven",
                                  "the positive claim is falsified, and that "
                                  "evidence proves the negation: "
                                  + (proof.counterexample or proof.sketch or ""))
    meta = dict(getattr(proof, "meta", None) or {}) or None
    if proof is None or proof.status not in ("proven", "disproven"):
        why = (proof.sketch if proof is not None and proof.sketch
               else "the examination could not decide it")
        return Probe(cj.name, statement, "unknown", route="examine",
                     sketch=getattr(proof, "sketch", None),
                     note=f"{note}; {why}".lstrip("; "), meta=meta)
    if proof.status == "proven":
        return Probe(cj.name, statement, "proven", route="examine",
                     sketch=proof.sketch, note=note, meta=meta)
    return Probe(cj.name, statement, "falsified", route="examine",
                 sketch=proof.sketch, counterexample=proof.counterexample,
                 note=note, meta=meta)


def _numeric_pieces(pieces) -> list:
    """Intent:
        A bound's pieces over the numbers alone: each finite set without
        its sentinels (`∅`, `None`), and a set of sentinels only left
        out. A value claim's mathematics is over the numbers; the
        sentinels are its missing and absence companions' business.
    """
    from .domain import is_sentinel
    out = []
    for piece in pieces:
        if isinstance(piece, frozenset):
            numbers = frozenset(v for v in piece if not is_sentinel(v)
                                and v is not None)
            if numbers:
                out.append(numbers)
            continue
        out.append(piece)
    return out


def _guard_interval(bound) -> "tuple | None":
    """Intent:
        `(lo, hi, closed_lo, closed_hi)` for a guard bound that is one
        real interval (a pair or a real `Domain` of one such piece),
        else None.
    """
    pieces = getattr(bound, "pieces", None)
    if pieces is not None:
        pieces = _numeric_pieces(pieces)
        if getattr(bound, "base_type", "R") != "R" or len(pieces) != 1 \
                or getattr(bound, "dims", ()):
            return None
        bound = pieces[0]
    if isinstance(bound, (tuple, list)) and not isinstance(bound, frozenset) \
            and len(bound) == 2:
        try:
            lo, hi = float(bound[0]), float(bound[1])
        except (TypeError, ValueError):
            return None
        return (lo, hi, getattr(bound, "closed_lo", True),
                getattr(bound, "closed_hi", True))
    return None


def _real_set(bound):
    """Intent:
        A real domain bound (an interval, a union of intervals, a
        finite set of numbers, the reals or the integers) as the sympy
        set of the numbers it holds, open ends kept open; a hole or an
        absence it admits is no number and is left out. None for
        anything else.
    """
    from .domain import is_sentinel
    import sympy
    if bound is None:
        return None
    single = _guard_interval(bound)
    if single is not None:
        lo, hi, closed_lo, closed_hi = single
        from .domain import exact_number
        return sympy.Interval(exact_number(lo), exact_number(hi),
                              not closed_lo, not closed_hi)
    pieces = getattr(bound, "pieces", None)
    if pieces is not None:
        pieces = _numeric_pieces(pieces)
    base = getattr(bound, "base_type", None)
    if base not in ("R", "Z", "N") or getattr(bound, "dims", ()):
        return None
    if not pieces:
        return {"R": sympy.S.Reals, "Z": sympy.S.Integers,
                "N": sympy.S.Naturals0}[base]
    parts = []
    for piece in pieces:
        if isinstance(piece, frozenset):
            from .domain import exact_number
            try:
                parts.append(sympy.FiniteSet(*[exact_number(v)
                                               for v in piece
                                               if not is_sentinel(v)]))
            except Exception:
                return None
            continue
        found = _real_set(piece)
        if found is None:
            return None
        parts.append(found)
    joined = sympy.Union(*parts)
    if base == "Z":
        joined = joined & sympy.S.Integers
    if base == "N":
        joined = joined & sympy.S.Naturals0
    return joined


def _guard_refuses_part_of_the_claim(ctx: "_ClaimContext", fn, facts
                                     ) -> "str | None":
    """Intent:
        Why the derive route leaves a claim to the executed guard, or
        None: the function is wrapped by `enforce_domain()`, and some
        call of f in the claim passes a parameter an argument that is
        not shown, exactly, to stay inside the interval the guard
        admits over the claim's own region.

    Notes:
        The argument's range is computed with sympy (`imageset` of the
        argument over the claim's interval for its one variable), under
        the wall-clock cap; anything it cannot show inside counts as
        refused, since a proof must not reach inputs the function
        refuses.
    """
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    enforced = getattr(fn, "__mathema_enforced_domain__", None) or {}
    if not enforced:
        return None
    names = {"f", getattr(fn, "__name__", "f")}
    cj = ctx.cj
    sides = [cj.lhs, cj.rhs, *[rhs for _l, _r, rhs in (cj.links or [])]]
    for side in sides:
        try:
            tree = ast.parse(side or "", mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in names):
                continue
            for p, arg in zip(facts.params, node.args):
                if p not in enforced or \
                        facts.param_kinds.get(p) in SEQUENCE_KINDS:
                    continue
                text = ast.unparse(arg)

                def inside(text=text, bound=enforced.get(p)):
                    allowed = _real_set(bound)
                    if allowed is None:
                        return False
                    variables = sorted(
                        {n.id for n in ast.walk(ast.parse(text, mode="eval"))
                         if isinstance(n, ast.Name)})
                    if len(variables) != 1:
                        return False
                    (name,) = variables
                    where = _real_set(ctx.cj_domain.get(name))
                    if where is None:
                        return False
                    sym = sympy.Symbol(name, real=True)
                    expr = sympy.sympify(text, locals={name: sym})
                    if expr == sym:
                        return where.is_subset(allowed) is True
                    reached = sympy.imageset(sympy.Lambda(sym, expr), where)
                    return reached.is_subset(allowed) is True

                try:
                    ok = _with_timeout(inside, FAST_TIMEOUT_SECONDS)
                except TimeoutError:
                    ok = False
                except Exception:
                    ok = False
                if not ok:
                    return (f"the claim calls f at {text}, which is not shown "
                            f"to stay inside the domain its guard admits for "
                            f"{p}, so the derive route does not prove it; the "
                            f"executed guard decides")
    return None


def _empty_premise_parameter(ctx: "_ClaimContext", facts) -> str | None:
    """Intent:
        The parameter whose declared range the claim's premises leave
        with no point at all, or None when the premises (if any) leave
        every range non-empty or cannot be read as bounds.
    """
    if not ctx.assumption:
        return None
    from .symbolic._prove import premise_empties_domain
    try:
        premises = [(a.lhs, a.relation, a.rhs) for a in ctx.assumption]
    except AttributeError:
        return None
    return premise_empties_domain(ctx.cj_domain, set(facts.params), premises)


def _fixed_dim_clash(ctx: "_ClaimContext") -> "tuple | None":
    """Intent:
        `(param, premise_text, axis_words)` for the first premise that
        bounds a dimension the claim's own binding fixes to a size the
        premise refuses (`assuming len(xs) == 5` over `[0, 1]^30`), or
        None when no premise contradicts a fixed dimension.
    """
    if not ctx.assumption:
        return None
    try:
        premises = [(a.lhs, a.relation, a.rhs) for a in ctx.assumption]
    except AttributeError:
        return None
    return _shapes.premise_against_fixed_dim(premises, ctx.cj_domain)


def _family_owns_claim(family) -> bool:
    """Intent:
        Whether `family` adjudicates the claim under its own name (a
        safety or self-agreement predicate, a derivative-sign fact, a
        matrix or output predicate), rather than dispatching on the
        function's shape and deciding whatever relation the claim
        states (the dot-product, sum and fold lifters).
    """
    if family is None:
        return False
    from .claim_families import (MatrixPropertyFamily, OutputPredicateFamily,
                                 _NamedClaimFamily)
    return isinstance(family, (_NamedClaimFamily, MatrixPropertyFamily,
                               OutputPredicateFamily))


def _language_strategy_proof(cj, fn, bound_funcs, cj_domain, extensive):
    """Intent:
        The derive verdict a language's own strategy gives a claim whose
        one quantified parameter ranges over that language, or None when
        there is no strategy, the claim quantifies more than that
        parameter, or the strategy answers with nothing usable. A proof
        carries `mathema.derive_strategy` (the language's name) in its
        meta; an undecided or unliftable answer keeps its sketch; a
        disproof becomes undecided, since only an executed witness
        falsifies.

    Notes:
        The strategy runs under the wall-clock cap, and one that raises
        is treated as having no answer.
    """
    from ._timeout import EXTENSIVE_TIMEOUT_SECONDS, FAST_TIMEOUT_SECONDS, _with_timeout
    from .domain import LanguageRef
    from .languages import derive_strategy, resolve_language
    from .symbolic._proof_support import ProofResult
    if len(cj_domain) != 1:
        return None
    ((param, bound),) = cj_domain.items()
    pieces = getattr(bound, "pieces", ())
    if len(pieces) != 1 or not isinstance(pieces[0], LanguageRef):
        return None
    try:
        language = resolve_language(pieces[0])
    except Exception:
        return None
    found = derive_strategy(language)
    if found is None:
        return None
    hook, refinements = found
    functions = {**{name: v for name, v in bound_funcs.items() if callable(v)},
                 getattr(fn, "__name__", "f"): fn, "f": fn}
    cap = EXTENSIVE_TIMEOUT_SECONDS if extensive else FAST_TIMEOUT_SECONDS
    try:
        result = _with_timeout(
            lambda: hook(param=param, lhs=cj.lhs, relation=cj.relation, rhs=cj.rhs,
                         functions=functions, refinements=refinements),
            cap)
    except TimeoutError:
        return None
    except Exception:
        return None
    if not isinstance(result, ProofResult):
        return None
    meta = {**(result.meta or {}), "mathema.derive_strategy": language.name}
    if result.status == "proven":
        return ProofResult("proven", sketch=result.sketch, quantifier=result.quantifier,
                           meta=meta)
    if result.status == "disproven":
        return ProofResult("undecided",
                           sketch=f"the language's strategy claimed a disproof it did not "
                                  f"execute ({result.sketch}), so the probe decides")
    if result.status in ("undecided", "unliftable"):
        return ProofResult(result.status, sketch=result.sketch)
    return None


def _spawn_float_companion(ctx: "_ClaimContext", proven: "Probe", fn,
                           facts, bound_funcs, assumption) -> None:
    """Intent:
        Stage the float companion of a derive proof on `ctx`, and state
        on the proof's own meta what became of it: the companion's
        name, `none (derive:math_only)` for a claim that opted out,
        `none (...)` for a claim a family adjudicates under its own
        name (whichever mechanism proved it), or `none (...)` when the
        claim has no point evaluation against the code.

    Notes:
        Does nothing unless the caller asked for companions
        (`ctx.companion_mode` is "spawn" or "math_only"); the math_only
        opt-out is stated whether or not companions were asked for.
    """
    mode = ctx.companion_mode
    if mode is None:
        return
    if mode == "math_only":
        proven.meta = {**(proven.meta or {}),
                       "mathema.float_companion": "none (derive:math_only)"}
        return
    if _family_owns_claim(ctx.family):
        # a family claim states a fact about the code itself
        # (determinism, state, safety, structure), not a relation the
        # float sweep could re-execute as the same question
        proven.meta = {**(proven.meta or {}),
                       "mathema.float_companion":
                           "none (a built-in claim decides this claim)"}
        return
    excluded = (_outside_definedness(fn, facts, ctx.cj)
                if ctx.assume_defined else None)
    containers, holes = _admitted_container_points(ctx, facts)
    companion = _float_companion(proven, ctx.cj, fn, facts, ctx.cj_domain,
                                 bound_funcs, assum=assumption,
                                 budget=ctx.companion_budget,
                                 missing=_admitted_scalar_points(ctx) + containers,
                                 holes=holes, excluded=excluded)
    if companion is None:
        proven.meta = {**(proven.meta or {}),
                       "mathema.float_companion":
                           "none (the claim has no point evaluation against "
                           "the code)"}
        return
    proven.meta = {**(proven.meta or {}),
                   "mathema.float_companion": companion.name}
    ctx.companion = companion
    witness = (companion.meta or {}).get("mathema.proof_contradicted")
    if witness:
        # an executed point where the claim is false in exact arithmetic
        # too: the claim is falsified there, and a proof that said
        # otherwise failed (a probe that stood in for derive merely held)
        stood_in = proven.verdict == "holds"
        proven.verdict = "falsified"
        proven.route = "probe"
        # the witness with the reason the companion executed there
        proven.counterexample = companion.counterexample or witness
        proven.condition = None
        proven.sketch = (
            f"the probe's draws held, but at {witness} the claim is false "
            f"in exact arithmetic and in the executed computation"
            if stood_in else
            f"the proof failed: derive reported the claim proven "
            f"({proven.sketch}), but at {witness} it is false in exact "
            f"arithmetic and in the executed computation")
        proven.stratum = {"mathematics": "unsound", "blame": "claim",
                          "witness": witness}
        proven.meta = {**proven.meta,
                       "mathema.corroboration": "reproduced",
                       "mathema.witness_executed": True,
                       **({} if stood_in else
                          {"mathema.proof_contradicted": witness})}


def _same_univariate_region(fn, facts, links) -> "bool | None":
    """Intent:
        Whether the conjunction of `links` and the computed definedness
        region of fn's body are the same set of reals, when both read
        over one and the same parameter; None when that is not the case
        or the comparison does not finish under the fast wall-clock cap.
    """
    import ast as _ast

    import sympy as _sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _WallClockExpired, _with_timeout
    from .grammar import normalize as _normalize
    from .symbolic._base import REL_TEXT, NotSymbolic, _expr_to_sympy

    env = {p: _sympy.Symbol(p, real=True) for p in facts.params}
    ops = {v: k for k, v in REL_TEXT.items()}
    stated = []
    for lhs, rel, rhs in links:
        try:
            left = _expr_to_sympy(_ast.parse(_normalize(lhs), mode="eval").body,
                                  dict(env))
            right = _expr_to_sympy(_ast.parse(_normalize(rhs), mode="eval").body,
                                   dict(env))
        except (NotSymbolic, SyntaxError):
            return None
        if rel not in ops or isinstance(left, tuple) or isinstance(right, tuple):
            return None
        stated.append(ops[rel](left, right))
    gaps: list = []
    computed = list(_definedness_region_structured(fn, facts, gaps))
    if not computed or gaps:
        return None
    region_s, region_c = _sympy.And(*stated), _sympy.And(*computed)
    free = region_s.free_symbols | region_c.free_symbols
    if len(free) != 1:
        return None
    try:
        return bool(_with_timeout(
            lambda: region_s.as_set() == region_c.as_set(),
            FAST_TIMEOUT_SECONDS))
    except (TimeoutError, _WallClockExpired):
        return None
    except Exception:
        return None


def _chained_definedness_proof(family_derive, fn, facts, cj, cj_domain,
                               assumption):
    """Intent:
        Region equivalence for a chained `is_defined` region (`-1 <= x
        <= 1`), which is ONE region, the conjunction of its links:
        proven when the links together match every conjunct of the
        computed definedness region, one link each; undecided
        otherwise, so the probe half decides by execution. None when
        the derive half declines (no source).
    """
    from .symbolic import ProofResult
    if facts.tree is None:
        return None
    same = _same_univariate_region(fn, facts, cj.links)
    if same is True:
        return ProofResult(
            "proven",
            sketch="is_defined: the stated region, the conjunction of its "
                   "links, equals the computed definedness region of the "
                   "current body",
            meta={"mathema.derive_route": "definedness_equivalence"})
    if same is False:
        return ProofResult(
            "undecided",
            sketch="is_defined: the stated region (the conjunction of its "
                   "links) differs from the computed definedness region")
    matched: list = []
    total = None
    for lhs, rel, rhs in cj.links:
        proof = families.call_route(family_derive, fn, facts, lhs, rhs, rel,
                                    domain=cj_domain,
                                    tolerance=cj.tolerance,
                                    assumption=assumption)
        if proof is None:
            return None
        where = (proof.meta or {}).get("mathema.definedness_conjunct")
        if proof.status != "proven" or not where:
            return ProofResult(
                "undecided",
                sketch=f"is_defined: the stated region (the conjunction "
                       f"of its links) is not shown equal to the computed "
                       f"definedness region: link {lhs} {rel} {rhs} does "
                       f"not match one of its conjuncts")
        matched.append(where[0])
        total = where[1]
    if total is not None and sorted(matched) == list(range(1, total + 1)):
        return ProofResult(
            "proven",
            sketch=f"is_defined: the stated region, the conjunction of its "
                   f"{len(matched)} links, equals the computed definedness "
                   f"region of the current body",
            meta={"mathema.derive_route": "definedness_equivalence"})
    return ProofResult(
        "undecided",
        sketch="is_defined: the stated region (the conjunction of its "
               "links) does not cover the computed definedness region "
               "conjunct for conjunct")


def _bound_callables(cj) -> dict:
    """A claim's bound functions as callables, each reference resolved
    (None for one that does not resolve)."""
    out = {}
    for name, v in (cj.funcs or {}).items():
        try:
            out[name] = v if callable(v) else _resolve_bound_ref(v)
        except AttributeError:
            out[name] = None
    return out


def _text_set_members(bound) -> "list | None":
    """The members of a finite set of strings (a `frozenset`, or a
    domain listing them), or None for any other bound."""
    from .domain import Domain, _is_enumerated, is_sentinel
    if isinstance(bound, frozenset):
        values = [v for v in bound if not is_sentinel(v)]
    elif isinstance(bound, Domain) and _is_enumerated(bound) and not bound.dims:
        values = [v for piece in bound.pieces for v in piece if not is_sentinel(v)]
    else:
        return None
    if not values or not all(isinstance(v, str) for v in values):
        return None
    return sorted(set(values))


def _adjudicate_derive(ctx: "_ClaimContext", fn, facts,
                       extensive: bool) -> "Probe | None":
    """Intent:
        The derive stage: a registered family's own derive route first,
        then the eligibility gate, then the ordinary
        `try_prove`/`try_prove_raises` attempt, mapping the proof result
        to a Probe. `None` means route="best" fell through undecided;
        the probe stage gets its turn.

    Notes:
        Only ever called for route in ("derive", "best") (or the
        retired "auto" spelling skips loudly as an unknown route);
        `ctx.family` is already resolved by the orchestration loop.
    """
    cj, statement, note = ctx.cj, ctx.statement, ctx.note
    exact_law = False
    cj_domain, family = ctx.cj_domain, ctx.family
    # A registered family's own "derive" route is tried before
    # the ordinary derive_ineligible check below; it doesn't
    # go through try_prove()'s lhs/rhs machinery at all (a
    # completely separate function, e.g. is_numerically_stable's
    # pole-vs-domain check), so a funcs-bound claim that would
    # otherwise be unconditionally derive_ineligible can still
    # get a real derive attempt this way.
    # the claim's premises, in the (lhs, relation, rhs) form every derive
    # entry point takes. Computed here rather than further down because
    # the family route below is a derive attempt like any other, and a
    # premise the route never sees is a premise silently dropped: the
    # claim then gets adjudicated over a region its author excluded.
    assumption = (None if ctx.assumption is None else
                  [(a.lhs, a.relation, a.rhs) for a in ctx.assumption])
    refused = _guard_refuses_part_of_the_claim(ctx, fn, facts)
    if refused is not None:
        # the guard is the function's domain: a claim reaching inputs it
        # refuses is not the mathematics of the body alone, and the
        # executed guard decides it
        ctx.derive_undecided = Probe(
            cj.name, statement, "unknown", route="derive",
            note=f"{note}; {refused}",
            meta={"mathema.derive_status": "undecided"})
        return None
    family_derive = family.routes().get("derive") if family is not None else None
    # literals a double does not read exactly reach only the ordinary
    # prover exactly (`exact_literal_text`); every other derive route
    # reads the parsed doubles, so it does not decide such a claim
    overlong_all = overlong_literals(cj.raw or "")
    overlong_reason = (f"{', '.join(overlong_all)} has more digits than a "
                       f"double carries, and the proof reads every number "
                       f"exactly as written, so it does not decide this "
                       f"claim")
    if overlong_all and family_derive is not None:
        ctx.derive_undecided = Probe(
            cj.name, statement, "unknown", route="derive",
            note=f"{note}; {overlong_reason}",
            meta={"mathema.derive_status": "undecided"})
        return None
    reserved = getattr(family, "reserved", None)
    if reserved:
        # a family defined but not adjudicated in this release: the
        # derive half reports skipped with the reason, and the probe
        # half says the same
        ctx.derive_undecided = Probe(
            cj.name, statement, "skipped", route=None,
            note=f"{note}; {reserved}",
            meta={"mathema.derive_status": "unsupported"})
        return None
    if (family_derive is not None and cj.links
            and region_row_kind(cj.name) == "is_defined"):
        family_proof = _chained_definedness_proof(
            family_derive, fn, facts, cj, cj_domain, assumption)
    else:
        with _lengths_scope(cj, family, facts):
            family_proof = (families.call_route(family_derive, fn, facts,
                                                cj.lhs, cj.rhs, cj.relation,
                                                domain=cj_domain,
                                                tolerance=cj.tolerance,
                                                assumption=assumption)
                            if family_derive is not None else None)
    if family_proof is not None and cj.negated:
        # the not-form: a decided positive claim decides its negation
        # the other way (the falsifying witness IS the proof); an
        # undecided one stays undecided.
        if family_proof.status == "proven":
            family_proof = replace_proof(family_proof, "disproven",
                                         "the positive claim is proven, so its "
                                         "negation is falsified: " + (family_proof.sketch or ""))
        elif family_proof.status == "disproven":
            family_proof = replace_proof(family_proof, "proven",
                                         "the positive claim is falsified, and that "
                                         "evidence proves the negation: "
                                         + (family_proof.counterexample or family_proof.sketch or ""))
    if (family_proof is None and family_derive is not None
            and region_row_kind(cj.name)):
        # a region row the family's derive half declined: is_defined
        # with no source to compute a definedness region from, or a
        # computation family whose region is a fact about the
        # executed computation (P9); either way the claim is
        # adjudicated by execution in the probe stage, never read as
        # an ordinary relation over the parameters
        why = ("the target has no Python source, so there is no "
               "definedness region to compare"
               if region_row_kind(cj.name) == "is_defined" else
               f"{region_row_kind(cj.name)} is a computation fact, "
               f"established by execution alone")
        ctx.derive_undecided = Probe(
            cj.name, statement, "unknown", route="derive",
            note=f"{note}; {why}",
            meta={"mathema.derive_status": "unsupported"})
        return None
    if (family_proof is not None and family_proof.status == "proven"
            and cj.name == "is_defined"
            and (family_proof.meta.get("mathema.definedness_conjunct")
                 or [0, 1])[1] > 1):
        # an unindexed restriction names the WHOLE region; matching one
        # conjunct of several decides nothing, and execution does
        k, n = family_proof.meta["mathema.definedness_conjunct"]
        ctx.derive_undecided = Probe(
            cj.name, statement, "unknown", route="derive",
            sketch=family_proof.sketch,
            note=f"{note}; the stated region is conjunct {k} of the "
                 f"{n} in the computed region, not all of it (index "
                 f"the row, is_defined[{k}], to state one conjunct)",
            meta={"mathema.derive_status": "undecided"})
        return None
    if family_proof is not None and family_proof.status == "proven":
        return Probe(cj.name, statement, "proven",
                     sketch=family_proof.sketch, note=note,
                     condition=family_proof.quantifier, route="derive",
                     meta=_provenance_meta(family_proof))
    if family_proof is not None and family_proof.status == "disproven":
        return Probe(cj.name, statement, "falsified", route="derive",
                     sketch=family_proof.sketch,
                     counterexample=family_proof.counterexample, note=note,
                     meta=_provenance_meta(family_proof))
    if (family_proof is not None
            and family_proof.meta.get("mathema.corroboration") == "uncorroborated"
            and region_row_kind(cj.name) is None):
        # a family disproof the executed code did not reproduce: the
        # claim's own verdict is unknown with the engine-bug flag, and
        # like any unknown it is superseded by real empirical evidence,
        # so the flagged report is stashed and the probe stage decides
        ctx.derive_undecided = Probe(
            cj.name, statement, "unknown", route="derive",
            sketch=family_proof.sketch,
            note=f"{note}; derive could not decide it",
            meta={"mathema.derive_status": "undecided",
                  **_provenance_meta(family_proof)})
        return None
    if family_proof is not None and region_row_kind(cj.name):
        # region equivalence undecided: the claim is adjudicated by
        # execution in the probe stage (the family's own probe half,
        # which reads the region, never the ordinary prover or sampler,
        # which would ask whether the stated relation is TRUE)
        ctx.derive_undecided = Probe(
            cj.name, statement, "unknown", route="derive",
            sketch=family_proof.sketch,
            note=f"{note}; region equivalence undecided",
            meta={"mathema.derive_status": "undecided",
                  **_provenance_meta(family_proof)})
        return None
    # a body that calls library functions reads, through their
    # definition rows, in the grammar's own words; a claim about it is
    # then decided as mathematics (sums over a symbolic length, or the
    # matrix algebra). A route that does not apply returns None; one
    # that applies but does not decide leaves its reason as the derive
    # note should nothing below decide the claim either.
    definitions_hint = None
    if not ctx.assume_defined and not overlong_all:
        from .definitions import prove_through_definitions
        dproof = prove_through_definitions(
            cj, fn, facts, cj_domain, assumption,
            ctx.premise_structures, extensive)
        if dproof is not None and dproof.status == "proven":
            # trusted definition rows are axioms; a row only verified
            # by execution is evidence and caps the proof at holds
            from .definitions import rows_sketch
            capped, sketch = rows_sketch(
                (dproof.meta or {}).get("mathema.definitions") or [],
                dproof.sketch)
            proven = Probe(cj.name, statement,
                           "holds" if capped else "proven",
                           sketch=sketch, note=note,
                           condition=dproof.quantifier, route="derive",
                           meta=_provenance_meta(dproof))
            listed = _listed_sentinels_fail(ctx, fn, facts, cj_domain,
                                            _bound_callables(cj), assumption or [],
                                            statement, note)
            if listed is not None:
                if listed.verdict == "falsified":
                    return listed
                proven.meta = {**(proven.meta or {}), **listed.meta}
            _spawn_float_companion(ctx, proven, fn, facts,
                                   _bound_callables(cj), assumption or [])
            return proven
        if dproof is not None and dproof.status == "disproven":
            falsified = Probe(cj.name, statement, "falsified",
                              route="derive", sketch=dproof.sketch,
                              counterexample=dproof.counterexample,
                              note=note, meta=_provenance_meta(dproof))
            return _corroboration_gate(falsified, dproof, cj, fn, facts,
                                       cj_domain, _bound_callables(cj),
                                       assum=assumption or [])
        if dproof is not None and dproof.sketch:
            definitions_hint = dproof.sketch
    # a claim over vectors or matrices (an `R^n`/`R^(m,n)` domain, a
    # Vec/Mat or structure marker, a vector, matrix or table runtime
    # type) that uses one as a value is an identity of linear algebra,
    # decided by sympy's matrix algebra and never by the scalar route,
    # which would read each vector or matrix as one number. A structure
    # marker or an `assuming A is symmetric` premise becomes a sympy
    # assumption. A proof stands as the verdict; anything else is the
    # honest unknown on route="derive" and, on route="best", falls to
    # the probe stage, which evaluates vectors and matrices as arrays.
    ranks = _claim_array_ranks(cj_domain, fn, facts)
    premise_sides = [s for a in (ctx.assumption or ())
                     for s in (a.lhs, a.rhs) if s]
    callables = frozenset({"f"}) | frozenset(cj.funcs or ())
    array_uses = linalg.array_value_uses(
        _claim_sides(cj) + premise_sides, ranks, callables)
    from .symbolic import matrix_param_dims
    from .types import shapes_from_signature, structures_from_signature
    _shapes = shapes_from_signature(fn)
    matrix_claim = bool(matrix_param_dims(cj_domain, _shapes)) \
        and mentions_matrix_ops(*_claim_sides(cj))
    if array_uses or matrix_claim:
        mproof = None
        from .symbolic._matrix_lemmas import structure_properties
        if (not cj.negated and not cj.links and not overlong_all
                and (cj.relation in ("==", "~=", ">", ">=", "<", "<=", "!=")
                     or cj.relation in structure_properties())):
            _structs = dict(structures_from_signature(fn))
            for _pp, _props in (ctx.premise_structures or {}).items():
                _structs[_pp] = tuple(sorted(
                    set(_structs.get(_pp, ())) | set(_props)))
            mproof = try_prove_matrix(cj.lhs, cj.rhs, cj.relation, facts,
                                      cj_domain, _shapes, _structs,
                                      premises=assumption)
            if mproof is not None and mproof.status == "proven":
                return Probe(cj.name, statement, "proven",
                             sketch=mproof.sketch, note=note, route="derive",
                             meta=_provenance_meta(mproof))
        why = ("derive could not decide the matrix identity" if matrix_claim
               else f"derive could not decide the claim over the "
                    f"{'vector or matrix' if len(array_uses) == 1 else 'vectors or matrices'} "
                    f"{', '.join(array_uses)}")
        if definitions_hint is not None:
            why = definitions_hint
        unknown = Probe(
            cj.name, statement, "unknown", route="derive",
            sketch=(mproof.sketch if mproof is not None else None),
            note=f"{note}; {why}",
            meta={"mathema.derive_status":
                  (mproof.status if mproof is not None else "unliftable")})
        if cj.route == "derive":
            # strict: this route promises proof-strength evidence, so
            # an undecided identity is the honest unknown, never a
            # silent fall to sampling.
            return unknown
        ctx.derive_undecided = unknown
        return None
    no_ordinary_derive = cj.relation in routes.examine_predicates()
    # a multi-function claim now derives: each bound function lifts to
    # its own closed form inside try_prove (funcs= below). Only the
    # shapes with no ordinary derive machinery at all stay ineligible
    # (the predicate relations, and raises(...); whose call must be a
    # bare f(...) anyway).
    derive_ineligible = no_ordinary_derive or \
        (bool(ctx.extra) and cj.relation == "raises")
    if derive_ineligible:
        if no_ordinary_derive:
            # the registered family declined and there is no ordinary
            # derive route for this predicate: the claim's own verdict
            # is unknown, but empirical evidence supersedes an unknown;
            # stash the would-be report (feeds the cross-route trail)
            # and fall to the probe stage, on derive OR best (the
            # predicate families all have probe routes).
            ctx.derive_undecided = Probe(
                cj.name, statement, "unknown", route="derive",
                note=f"{note}; the built-in claim {cj.relation} could not "
                     f"decide it, and derive has no other way to read it",
                meta={"mathema.derive_status": "unsupported"})
            return None
        if cj.route == "derive":
            # a multi-function raises claim isn't uncertain, this route
            # structurally doesn't support that shape at all, so it
            # stays the plain "skipped" every other structural-mismatch
            # skip in this function uses.
            return Probe(cj.name, statement, "skipped", route=cj.route,
                         note=f"{note}; derive cannot yet read a raises "
                              f"claim over several functions, so on the derive "
                              f"route it stays unknown; to run the code "
                              f"instead, state it with route: best")
        # route == "best" and derive-ineligible: fall through to the
        # probe stage, same as an ordinary probe claim.
        return None
    bound_funcs: dict = {}
    if ctx.extra:
        try:
            bound_funcs = {name: (v if callable(v) else _resolve_bound_ref(v))
                          for name, v in cj.funcs.items()}
        except AttributeError:
            bound_funcs = dict.fromkeys(cj.funcs)
        if any(v is None for v in bound_funcs.values()):
            unresolved = sorted(n for n, v in bound_funcs.items() if v is None)
            if cj.route == "derive":
                return Probe(cj.name, statement, "skipped", route=cj.route,
                             note=f"{note}; could not resolve bound "
                                  f"function(s) {unresolved}, define it in "
                                  f"f's module or the calling scope, or bind "
                                  f"it explicitly with funcs=")
            # route == "best": the probe stage reports its own skip
            return None
    language_params = sorted(p for p, b in cj_domain.items()
                             if getattr(b, "base_type", None) == "L")
    row_domain, row_reason = (_row_lift_domain(fn, facts, cj_domain)
                              if language_params else (None, ""))
    if cj.relation in ("in", "not in"):
        # membership is decided by execution: the lift has no reading
        # of a value's membership in a language or a set
        from .symbolic._proof_support import ProofResult
        proof = ProofResult(
            "unliftable",
            sketch=f"derive cannot read membership in a language or a "
                   f"set, so `{cj.relation}` is decided by running the "
                   "code")
    elif language_params and row_domain is not None:
        # every language-bound parameter is a SCHEMA language and the
        # body reads only numeric fields of it (or a text field through
        # len()): each field read is one symbol bounded by its field
        # domain, a claim-level `o.field` binding overriding, and the
        # ordinary prover runs
        from .symbolic._base import row_fields
        # each row-bound parameter expands into exactly the field keys
        # bounded above, whatever class its rows are
        with row_fields({p: [k for k in row_domain if k.startswith(f"{p}.")]
                         for p in language_params}):
            exact_law = True
            proof = try_prove(fn, facts, exact_literal_text(cj.lhs),
                              exact_literal_text(cj.rhs), cj.relation,
                              domain={**row_domain, **cj_domain},
                              tolerance=cj.tolerance,
                              extensive=extensive, funcs=bound_funcs or None,
                              assumption=assumption,
                              assume_defined=ctx.assume_defined,
                              exclude_own_guards=ctx.exclude_own_guards)
    elif language_params:
        # a string or structured value has no symbolic reading, and a
        # real symbol standing in for one would prove real-only facts
        # it does not have, so the lift is declined outright unless the
        # language supplies its own derive strategy; a FINITE language
        # is still swept point by point by the brute-force fallback
        # below, which is the one derive mechanism it admits
        from .symbolic._proof_support import ProofResult
        proof = _language_strategy_proof(cj, fn, bound_funcs, cj_domain,
                                         extensive) or ProofResult(
            "unliftable",
            sketch=(row_reason if row_reason.startswith("derive cannot read the function") else
                    "derive cannot read " + ", ".join(language_params)
                    + ", a string or structured value from a language "
                    "domain (it decides only a finite language, member by "
                    "member)"))
    elif cj.relation == "raises":
        # only ever reachable via domain-conditioned branch
        # pruning, a raises claim with no domain specific
        # enough to settle which branch runs comes back
        # unliftable from try_prove_raises itself, same as any
        # other undecidable derive claim.
        proof = try_prove_raises(fn, facts, cj.lhs, cj.rhs or None,
                                 domain=cj_domain)
    else:
        exact_law = True
        with _lengths_scope(cj, family, facts):
            proof = try_prove(fn, facts, exact_literal_text(cj.lhs),
                              exact_literal_text(cj.rhs), cj.relation,
                              domain=cj_domain, tolerance=cj.tolerance,
                              extensive=extensive, funcs=bound_funcs or None,
                              assumption=assumption,
                              assume_defined=ctx.assume_defined,
                              exclude_own_guards=ctx.exclude_own_guards)
        if definitions_hint is not None \
                and proof.status in ("undecided", "unliftable"):
            from .symbolic._proof_support import ProofResult
            proof = ProofResult(proof.status, sketch=definitions_hint,
                                meta=dict(proof.meta))
    def _brute_force_fallback():
        """A claim quantified over a FINITE declared domain needs no
        symbolic argument: visiting every point the domain admits
        settles it outright. Tried only where the symbolic routes left
        no reliable verdict, so nothing they decided can move."""
        from ._brute_force import brute_force_proof
        from ._timeout import EXTENSIVE_TIMEOUT_SECONDS, _with_timeout
        from .runtime_types import calling
        try:
            return _with_timeout(
                lambda: brute_force_proof(cj, calling(fn, facts), facts,
                                          cj_domain,
                                          bound_funcs,
                                          assumption=assumption or [],
                                          resolution=ctx.missing),
                EXTENSIVE_TIMEOUT_SECONDS)
        except TimeoutError:
            # an unfinished sweep covers only a prefix of the domain,
            # which settles nothing
            return None

    depth_refusal = (proof.meta or {}).get("mathema.recursion_depth")
    if depth_refusal is not None:
        # the computation cannot recurse deep enough to cover this
        # domain, so a sweep of it would walk into the same stack limit
        # (or, for a branching recursion, run exponentially long first).
        # The refusal stands; an executed witness at the domain's top
        # turns it into the falsification the raise rule calls for.
        witnessed = _recursion_depth_witness(ctx, fn, facts, bound_funcs,
                                             assumption or [], proof, note)
        if witnessed is not None:
            return witnessed
    elif proof.status in ("undecided", "unliftable"):
        swept = _brute_force_fallback()
        if swept is not None and swept.meta.get("mathema.sweep_holds"):
            # every point executed and agreed, over a function the strict
            # examination could not show pure: holds, never proven
            return Probe(cj.name, statement, "holds", route="derive:brute_force",
                         sketch=swept.sketch,
                         note=f"{note + '; ' if note else ''}{swept.sketch}",
                         meta=_provenance_meta(swept))
        if swept is not None:
            proof = swept
    from collections import Counter
    overlong = Counter(overlong_literals(cj.raw or ""))
    if exact_law:
        # the law's own literals reached the proof exactly
        overlong -= Counter(overlong_literals(cj.lhs or "")
                            + overlong_literals(cj.rhs or ""))
    overlong = list(overlong)
    if overlong and proof.status in ("proven", "disproven"):
        # the parse read these literals as the nearest double, a
        # different number from the one written, so a symbolic verdict
        # on the parsed claim is not a verdict on the written one
        from .symbolic._proof_support import ProofResult
        proof = ProofResult(
            "undecided",
            sketch=(f"{', '.join(overlong)} has more digits than a double "
                    f"carries, and the proof reads every number exactly as "
                    f"written, so it does not decide this claim"))
    inlined = getattr(facts, "_inlined_globals", None)
    if inlined:
        # the lift read module-level constants as their current
        # values: state that explicitly (their exact values also ride
        # the record's dependency section, where the freshness sweep
        # watches them)
        note = (note + "; module constants read when it was checked: "
                + ", ".join(f"{k} = {v!r}"
                            for k, v in sorted(inlined.items())))
    if proof.status == "proven":
        # record-schema.md's own `route` field, an open string,
        # names the mechanism that actually won: a proof the fast
        # single-context attempt closed is plain "derive" even when
        # the caller had opted into extensive, and "derive:extensive"
        # states that one of the wider mechanisms (a ladder rung, the
        # case-split fallback, the widened-cap retry) actually decided
        # it. The one wider mechanism that stays plain "derive" is the
        # guard-boundary domain split, which is default-path and cheap.
        mechanism = proof.meta.get("mathema.derive_route")
        if proof.meta.get("mathema.derive_strategy") is not None:
            # a language's own strategy decided it, named by the
            # mechanism it states
            route = f"derive:{mechanism or 'language'}"
        elif mechanism == "brute_force":
            # a different kind of evidence from the wider symbolic
            # mechanisms, not a wider version of them: every point of a
            # finite region was visited. It gets its own subroute so a
            # reader can tell the two apart at a glance.
            route = "derive:brute_force"
        else:
            route = ("derive:extensive"
                    if mechanism is not None and mechanism != "domain_split"
                    else "derive")
        meta = _provenance_meta(proof)
        derive_lines = _derive_line_coverage(fn, facts, cj_domain)
        if derive_lines is not None:
            # per-branch attribution for the implementation-coverage pass:
            # a domain-restricted proof covers only its reachable branches.
            meta["mathema.derive_lines"] = sorted(derive_lines)
        proven = Probe(cj.name, statement, "proven",
                       sketch=proof.sketch, note=note,
                       condition=proof.quantifier, route=route,
                       meta=meta)
        if route != "derive:brute_force":
            listed = _listed_sentinels_fail(ctx, fn, facts, cj_domain, bound_funcs,
                                            assumption or [], statement, note)
            if listed is not None:
                if listed.verdict == "falsified":
                    return listed
                proven.meta = {**(proven.meta or {}), **listed.meta}
        # a derive proof is exact arithmetic; the computation is the
        # float companion's claim. A proof by executing every point of a
        # finite set already is the computation, and spawns none
        if route != "derive:brute_force":
            _spawn_float_companion(ctx, proven, fn, facts, bound_funcs,
                                   assumption or [])
        return proven
    if proof.status == "disproven":
        # a brute-force disproof names its own mechanism for the same
        # reason the proof does: the witness came from executing the
        # function at a point the domain admits, not from a symbolic
        # residual that still needs reproducing.
        dis_route = ("derive:brute_force"
                     if proof.meta.get("mathema.derive_route") == "brute_force"
                     else "derive")
        falsified = Probe(cj.name, statement, "falsified", route=dis_route,
                          sketch=proof.sketch,
                          counterexample=proof.counterexample, note=note,
                          meta=_provenance_meta(proof))
        # a symbolic decider can be wrong, only trust the disproof
        # once it reproduces against the REAL function
        gated = _corroboration_gate(falsified, proof, cj, fn, facts,
                                    cj_domain, bound_funcs,
                                    assum=assumption or [])
        if gated.verdict == "falsified" and ctx.exclude_own_guards \
                and _refused_by_own_guard(fn, proof.witness
                                          or _point_of(gated.counterexample)):
            # the witness is a point f's own guard refuses, outside the
            # working domain of a claim that binds none: no counterexample
            gated = Probe(cj.name, statement, "unknown", route=None,
                          sketch=proof.sketch,
                          note=f"{note + '; ' if note else ''}the derive "
                               f"witness is refused by f's own guard, "
                               f"outside the working domain",
                          meta=_provenance_meta(proof))
        if gated.verdict != "unknown":
            return gated
        # uncorroborated, so the symbolic disproof is not to be trusted
        # and there is no reliable verdict here at all. Over a finite
        # domain there is a better answer available than "unknown":
        # visiting every point settles the claim from the function
        # itself, which is exactly the evidence the failed corroboration
        # went looking for. A sweep that agrees the claim is false
        # supplies the witness the gate could not find; one that proves
        # it confirms the symbolic disproof was the engine bug the gate
        # suspected.
        swept = _brute_force_fallback()
        if swept is not None:
            if swept.status == "proven":
                proven = Probe(cj.name, statement, "proven",
                               sketch=swept.sketch, note=note,
                               condition=swept.quantifier,
                               route="derive:brute_force",
                               meta=_provenance_meta(swept))
                return proven
            if swept.status == "disproven":
                return Probe(cj.name, statement, "falsified",
                             route="derive:brute_force", sketch=swept.sketch,
                             counterexample=swept.counterexample, note=note,
                             meta=_provenance_meta(swept))
            if swept.meta.get("mathema.sweep_holds"):
                return Probe(cj.name, statement, "holds",
                             route="derive:brute_force", sketch=swept.sketch,
                             note=f"{note + '; ' if note else ''}{swept.sketch}",
                             meta=_provenance_meta(swept))
        # an unknown is superseded by real empirical evidence like any
        # other, stash the flagged report and fall through to the
        # probe stage; the uncorroborated meta rides on the stash so
        # the engine-bug signal survives whichever route wins
        ctx.derive_undecided = gated
        return None
    # undecided/unliftable. A route="derive" claim stays
    # skipped, never downgraded to probing: it promises
    # proof-strength evidence, and strict mode should
    # surface the gap, not paper over it. `proof.status`
    # (one of "undecided"/"unliftable") is also tagged in
    # `meta`, structured rather than only free text,
    # "genuinely unliftable" and "liftable but undecided"
    # are different failure modes a caller measuring
    # derive-route coverage needs to tell apart
    # programmatically, not just by parsing
    # `.note`/`.sketch`, same precedent as
    # `mathema.foreign_grammar` above, for the identical
    # kind of "verdict is the same on the surface, caller
    # may want the real reason" case.
    skip_meta = {"mathema.derive_status": proof.status}
    if "mathema.timeout" in proof.meta:
        # distinguishes a real wall-clock cutoff from an
        # ordinary "sympy gave up on its own" undecided,
        # both look identical on the surface (same verdict,
        # same proof.status), but a caller measuring derive-
        # route coverage needs to tell them apart the same
        # way it already tells unliftable from undecided.
        skip_meta["mathema.timeout"] = proof.meta["mathema.timeout"]
    # genuinely undecided/unliftable, on derive OR best: the claim's
    # own verdict is "unknown" (its epistemic state never moved), but
    # an unknown is superseded by real empirical evidence either way;
    # stash the would-be report (the cross-route trail and, for
    # route="derive", the fallback if probing can't decide either) and
    # fall through to the probe stage. Meta says which kind of
    # couldn't-decide this was.
    ctx.derive_undecided = Probe(
        cj.name, statement, "unknown", route="derive",
        sketch=proof.sketch,
        note=note + "; derive could not decide it",
        meta=skip_meta)
    ctx.derive_intermediates = getattr(proof, "intermediates", None)
    return None
    # route == "best": fall through to the probe stage rather
    # than reporting skipped, a proof attempt that couldn't
    # decide is not the same as a claim nobody ever tried to
    # check empirically. The reported route is plain "probe",
    # same as a claim that was always probe-only: why it fell
    # back isn't carried onto the output record (a caller can
    # run diagnostics on the function directly if they need
    # that). "probe:semi_analytical" is reserved for when the
    # probe itself was informed by critical-point sampling
    # (probing.py's own battery), which this fallback path
    # doesn't do.
    return None


def _recursion_depth_witness(ctx: "_ClaimContext", fn, facts, bound_funcs,
                             assumption, proof, note) -> "Probe | None":
    """Intent:
        The falsification behind a stack-depth refusal: the claim run at
        the top of the recursed parameter's domain, where the refusal
        says the call needs more frames than the interpreter allows. A
        RecursionError there is a raise inside the domain, so the value
        claim is falsified with that executed point as its witness, and
        the refusal's sketch (which names the safe bound) is kept.

        None when there is no finite top, the top is not admitted, the
        run does not end in a RecursionError, or it outruns the fast
        wall-clock cap.

    Notes:
        One point is run, never a sweep: a recursion descends one frame
        per index step before doing any other work, so a call past the
        limit raises after about a thousand frames, while the points
        below the limit can be arbitrarily expensive (a doubly recursive
        definition is exponential in its argument).
    """
    from ._timeout import FAST_TIMEOUT_SECONDS, _WallClockExpired, _with_timeout
    from .gates import _fmt_point, _point_evaluator
    info = proof.meta["mathema.recursion_depth"]
    param, top = info["param"], info["top"]
    if top is None:
        return None
    raised: list = []

    def _recording(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as exc:
            raised.append(exc)
            raise

    kit = _point_evaluator(ctx.cj, _recording, facts, ctx.cj_domain,
                           bound_funcs, assumption)
    if kit is None or list(kit["names"]) != [param]:
        return None
    point = {param: top}
    if not kit["admits"](point):
        return None
    try:
        verdict = _with_timeout(lambda: kit["evaluate"](point),
                                FAST_TIMEOUT_SECONDS)
    except (TimeoutError, _WallClockExpired):
        return None
    if verdict is not False or not raised \
            or not isinstance(raised[-1], RecursionError):
        return None
    where = _fmt_point(point, [param])
    cj = ctx.cj
    return Probe(cj.name, ctx.statement, "falsified", route="derive",
                 sketch=proof.sketch,
                 counterexample=f"{where}: raised RecursionError",
                 note=note,
                 stratum=_machine_failure_stratum(raised[-1], where),
                 meta={"mathema.corroboration": "reproduced",
                       "mathema.recursion_depth": dict(info)})


def _adjudicate_equivalence(ctx: "_ClaimContext", fn, facts) -> "Probe":
    """The `f =:= g` ladder, in its own module; see equivalence.py."""
    from .equivalence import adjudicate
    return adjudicate(ctx, fn, facts)


def _lifted_numeric_fallback(ctx, cj, statement, note, cj_domain):
    """Intent:
        Numeric evidence for a claim the probe route cannot evaluate (a
        d()/integrate()/Sum()/lim() law): lambdify the resolved
        symbolic intermediates the stalled derive attempt handed over
        and sample the relation over the declared domain. Route
        `probe:lifted_numeric`, ceiling holds, and the note says
        plainly that what was sampled is mathema's reconstruction, not
        the code.

    Notes:
        Declines (None) without intermediates, under an `assuming`
        clause (the sampler would run off the assumed surface), or for
        a relation the numeric comparison doesn't cover. A
        falsification here carries its executed witness on the
        INTERMEDIATE, real evidence against the claim, whose lift
        provenance the note states.
    """
    if ctx.derive_intermediates is None or ctx.assumption is not None:
        return None
    if cj.relation not in ("==", "~=", "!=", "<=", ">=", "<", ">"):
        return None
    from . import compiled as CF
    from .domain import domain_contains
    lhs_expr, rhs_expr, _params, opaque = ctx.derive_intermediates
    if isinstance(lhs_expr, tuple) or isinstance(rhs_expr, tuple):
        return None
    if opaque is not None:
        free = set(getattr(lhs_expr, "free_symbols", set()))
        if rhs_expr is not None:
            free |= set(getattr(rhs_expr, "free_symbols", set()))
        if any(opaque.is_opaque_symbol(s) for s in free):
            # a non-numeric value (a string, None, an Enum member) has
            # no numeric sampling story; the fallback must decline,
            # not adjudicate nonsense
            return None
    from .records import operational_range
    pinf = operational_range(cj)
    lhs_cf = CF.compile_form(lhs_expr, pseudo_infinity=pinf)
    rhs_cf = CF.compile_form(rhs_expr if rhs_expr is not None else _sympy_zero(),
                             pseudo_infinity=pinf)
    if lhs_cf is None or rhs_cf is None:
        return None

    def admits(point):
        for n, v in point.items():
            bound = cj_domain.get(n)
            if bound is None:
                continue
            try:
                if not domain_contains(float(v), bound):
                    return False
            except Exception:
                return False
        return True

    tol = cj.tolerance if cj.tolerance is not None else DEFAULT_TOLERANCE
    quad = "quad" in (lhs_cf.backend, rhs_cf.backend)
    try:
        if quad:
            # every quad-backed sample is real numeric integration:
            # far fewer trials, and one wall-clock envelope over the
            # whole check so a pathological integrand cannot hang the
            # fallback (expiry = decline, never a verdict)
            from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
            verdict, checked, cx = _with_timeout(
                lambda: CF.numeric_check(lhs_cf, rhs_cf, cj.relation,
                                         cj_domain, tolerance=tol,
                                         admits=admits, trials=12),
                4 * FAST_TIMEOUT_SECONDS)
        else:
            verdict, checked, cx = CF.numeric_check(lhs_cf, rhs_cf,
                                                    cj.relation, cj_domain,
                                                    tolerance=tol,
                                                    admits=admits)
    except TimeoutError:
        return None
    if verdict is None:
        return None
    contract = (f"numeric evidence on derive's own reading of the function "
                f"({checked} samples of that symbolic form, mathema's "
                f"reconstruction, not a run of the code; derive itself "
                f"could not decide it)")
    for cf in (lhs_cf, rhs_cf):
        if cf.validity:
            contract = f"{contract}; {cf.validity}"
            break
    meta = {"mathema.derive_status": "undecided",
            "mathema.lifted_numeric_samples": checked}
    if verdict == "falsified":
        return Probe(cj.name, statement, "falsified",
                     route="probe:lifted_numeric", n=checked,
                     counterexample=cx,
                     note=f"{note}; {contract}", meta=meta)
    return Probe(cj.name, statement, "holds",
                 route="probe:lifted_numeric", n=checked,
                 note=f"{note}; {contract}", meta=meta)


def _sympy_zero():
    import sympy
    return sympy.S.Zero



def _call_arity_mismatch(src: str, fn, param_set: set,
                         pinned: frozenset = frozenset()) -> str | None:
    """Intent:
        The reason a call to `f` in the claim text `src` cannot bind to
        `fn`'s signature (too many or too few arguments, an unknown
        keyword), or None when every such call fits or the signature
        cannot be read.

    Notes:
        A starred argument is not counted and makes the check decline
        for that call. A `pinned` parameter (`let p be ...`) the call
        does not pass itself is passed for it. A parameter literally named `f` makes `f(...)`
        ambiguous, so the check declines entirely.
    """
    if "f" in param_set:
        return None
    try:
        sig = callable_signature(fn)
        tree = ast.parse(src, mode="eval")
    except (TypeError, ValueError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "f"):
            continue
        if any(isinstance(a, ast.Starred) for a in node.args) \
                or any(k.arg is None for k in node.keywords):
            continue
        try:
            given_kw = {k.arg: None for k in node.keywords}
            bound = sig.bind_partial(*([None] * len(node.args)), **given_kw)
            sig.bind(*([None] * len(node.args)), **given_kw,
                     **{p: None for p in pinned
                        if p not in bound.arguments and p in sig.parameters})
        except TypeError:
            params = list(sig.parameters)
            given = len(node.args) + len(node.keywords)
            return (f"f is called here with {given} argument(s), but its "
                    f"signature takes {len(params)} ({', '.join(params)}), "
                    f"so any TypeError is raised by the malformed call "
                    f"itself; call f with its own parameters")
    return None


def _int_annotated_params(callee) -> list:
    """Intent:
        The names of a callable's int-annotated parameters, the
        signature's own statement of an integer contract, read for the
        TypeError-misspecification check above. Empty for anything
        unreadable.
    """
    try:
        sig = callable_signature(callee)
    except (TypeError, ValueError):
        return []
    out = []
    for name, prm in sig.parameters.items():
        ann = prm.annotation
        if ann is int or (isinstance(ann, str) and ann.strip() == "int"):
            out.append(name)
    return out


# which machine-failure raise maps to which implementation cause; a
# raise outside this table (ValueError, TypeError, ...) is the contract
# or the mathematics talking and gets no stratum at all
_MACHINE_FAILURE_CAUSES = {
    OverflowError: "implementation:overflow",
    RecursionError: "implementation:recursion-depth",
    MemoryError: "implementation:memory",
}


def _machine_failure_stratum(exc, witness: str) -> dict | None:
    """Intent:
        The stratum for a falsifying in-domain raise, when the raised
        type signals the MACHINE failing (overflow, recursion depth,
        memory), else None.

    Notes:
        `mathematics` is deliberately absent: a machine failure alone
        says nothing about whether the mathematical claim holds, only
        that the number representation gave out before the value
        existed. The verdict stays falsified either way; this only
        classifies.
    """
    for exc_type, cause in _MACHINE_FAILURE_CAUSES.items():
        if isinstance(exc, exc_type):
            return {"blame": "implementation", "cause": cause,
                    "representation": "f64", "witness": witness}
    return None


def _adjudicate_probe(ctx: "_ClaimContext", fn, facts, kinds: dict,
                      sampling) -> "Probe":
    """Intent:
        The probe stage, run under the pinned floating-point regime
        (`probing._pinned_float_env`), so an invalid operation is a
        NaN whatever `numpy.seterr` state the caller carries and the
        verdict and witness are the same in every process.
    """
    from .probing import _pinned_float_env
    kinds = _kinds_as_bound(fn, kinds, ctx.cj_domain)
    with _pinned_float_env():
        return _probe_stage(ctx, fn, facts, kinds, sampling)


def _kinds_as_bound(fn, kinds: dict, cj_domain: dict) -> dict:
    """Intent:
        The kinds the probe draws with: an unannotated parameter the
        body could read as a sequence, but which the claim binds to a
        scalar real domain (`q in [0, 1]`, no `^n`), is drawn as the
        scalar the claim states.
    """
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return kinds
    out = dict(kinds)
    for p, kind in kinds.items():
        bound = (cj_domain or {}).get(p)
        param = params.get(p)
        if (kind not in SEQUENCE_KINDS or bound is None or param is None
                or param.annotation is not inspect.Parameter.empty):
            continue
        if getattr(bound, "dims", ()) or getattr(bound, "base_type", "R") not in ("R", "Z", "N"):
            continue
        scalar = (isinstance(bound, tuple) and not isinstance(bound, frozenset)
                  and len(bound) == 2) or isinstance(bound, Domain)
        if scalar:
            out[p] = "int" if getattr(bound, "base_type", "R") in ("Z", "N") else "scalar"
    return out


def _family_premise_guard(ctx: "_ClaimContext", fn, facts, kinds: dict,
                          cj_domain: dict):
    """Intent:
        The claim's premises as a claim family's own trials apply them
        (`_premises.PremiseGuard`), evaluated in the namespace the
        generic sampling loop uses: the claim vocabulary, the bound
        functions, the parameters (as arrays where the claim reads them
        as vectors or matrices) and the marker dimensions. None when
        the claim has no premise.

    Raises:
        InvalidConjecture: a premise conjunct is not an expression the
            probe evaluates.
        KeyError: a premise conjunct is not a comparison.
    """
    if ctx.assumption is None:
        return None
    from . import _linalg_eval
    from . import _premises
    from . import dimensions as _dims
    from .matrices import _numpy
    from .types import shapes_from_signature
    cj = ctx.cj
    compiled = _premises.compile_premises(cj, ctx.assumption, kinds, ctx.extra)
    try:
        bound = {name: (v if callable(v) else _resolve_bound_ref(v))
                 for name, v in cj.funcs.items()}
    except AttributeError:
        bound = {}
    bound = {name: v for name, v in bound.items() if v is not None}
    array_params = frozenset(
        p for p in _claim_array_ranks(cj_domain, fn, facts)
        if p in kinds) if _numpy() is not None else frozenset()
    if array_params:
        bound = {name: _bound_for_arrays(v) for name, v in bound.items()}
    try:
        resolver = _dims.resolve(facts, shapes_from_signature(fn),
                                 claim_domain=cj_domain)
        bind_env = resolver.bind_env
    except _dims.DimensionConflict:
        bind_env = None
    from .runtime_types import calling
    inner = calling(fn, facts)
    if array_params:
        inner = _linalg_eval.law_callable(inner)
    base = {"f": inner, **_SAFE_FUNCS, **_linalg_eval.FUNCTIONS,
            **MATH_CONSTANTS, **bound}
    from .claim_families import _OUTSIDE_DOMAIN_FAMILIES
    ignore = (frozenset({cj.lhs.strip()})
              if families.claim_base_name(cj.name) in _OUTSIDE_DOMAIN_FAMILIES
              else frozenset())
    return _premises.PremiseGuard(
        compiled=compiled, params=tuple(facts.params), domain=cj_domain,
        draws=_premises.premise_draws(ctx.assumption, kinds, cj_domain,
                                      tolerance=cj.tolerance),
        solved=_premises.solve_equality(ctx.assumption, kinds),
        base_env=base, array_params=array_params, bind_env=bind_env,
        ignore=ignore)


def _probe_stage(ctx: "_ClaimContext", fn, facts, kinds: dict,
                 sampling) -> "Probe":
    """Intent:
        `_probe_stage_in_slots` under the hole members of f's slot
        types: a value f returns is read against a `{missing}` bound as
        a hole of the runtime its containers are realised in (see
        `_null_is_a_hole`).
    """
    token = _NULL_IS_A_HOLE.set(_null_is_a_hole(facts))
    try:
        return _probe_stage_in_slots(ctx, fn, facts, kinds, sampling)
    finally:
        _NULL_IS_A_HOLE.reset(token)


#: whether a `None` that f returns is the null hole of the runtime its
#: containers are realised in, while one claim is probed
_NULL_IS_A_HOLE: "contextvars.ContextVar[bool]" = contextvars.ContextVar(
    "mathema_null_is_a_hole", default=False)


def _null_is_a_hole(facts) -> bool:
    """Intent:
        Whether some container parameter of f is realised in a runtime
        whose holes include `null` (a pandas or a polars Series): a
        reduction over it answers no value with that runtime's null,
        which Python returns as `None`.
    """
    from .runtime_types import adapter, realised_parameters
    try:
        found = realised_parameters(facts)
    except Exception:
        return False
    for detection in found.values():
        runtime = adapter(detection.adapter)
        if "null" in (getattr(runtime, "MISSING_MEMBERS", ()) or ()):
            return True
    return False


def _probe_stage_in_slots(ctx: "_ClaimContext", fn, facts, kinds: dict,
                          sampling) -> "Probe":
    """Intent:
        The probe stage: relation/exception-type gates, a registered
        family's `probe:algorithmic` technique, then the generic
        seeded sampling loop over compiled lhs/rhs, with the final
        holds/falsified/skipped triage. Always returns a Probe.

    Notes:
        `sampling` is the per-call lazy `SamplingSetup` provider,
        shared with `probe()`'s own structural checks, computed at most
        once per `check_conjectures` call.
    """
    cj, statement, note = ctx.cj, ctx.statement, ctx.note
    cj_domain, extra, family = ctx.cj_domain, ctx.extra, ctx.family
    bundles = _instance_bundles(fn, facts)
    from .domain import unbounded_directions
    from .records import operational_infinity, operational_range
    from .types import shapes_from_signature
    pinf = operational_range(cj)
    # the real parameters no domain was declared for: the generic
    # sampling loop runs them along the whole reach
    shaped = set(shapes_from_signature(fn) or {})
    bare = [p for p, k in kinds.items()
            if k in ("scalar", "unknown") and cj_domain.get(p) is None
            and p not in shaped and p not in bundles]
    if pinf is not None:
        # the resolved pseudo-infinity is the computation's reading of
        # the declared oo: this stage (and only this stage) runs
        # infinite endpoints to it, and the record says so with its
        # source; the derive stage never sees this, so a proof still
        # covers actual infinity (P1, P6)
        cj_domain, _approximated = _operational_domain(cj_domain, pinf)
        directions = [p for p, k in kinds.items() if k in _DIRECTION_KINDS]
        directions += sorted(set(cj.free_vars or ()) - set(directions))
        if unbounded_directions(directions, ctx.cj_domain):
            resolved = operational_infinity(cj)
            note = (f"{note}; the computation approximates infinity as "
                    f"{resolved.magnitude():g}; the "
                    f"mathematics keeps the declared oo").lstrip("; ")
    region_claim = region_row_kind(cj.name) is not None
    if not region_claim and cj.relation not in (frozenset({"==", "~=", "!=", "<=", ">=", "<", ">",
                                      "in", "not in", "raises"})
                           | (routes.examine_predicates()
                              & routes.route_capabilities("probe"))):
        # a safety predicate passes only when the capability table says
        # the probe route can evaluate it (today just is_missing_safe,
        # whose empirical half is a literal-NaN call served by its
        # registered probe:algorithmic family below, the generic
        # sampling loop still never sees it; the family guard after the
        # dispatch catches a decline).
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"unknown relation {cj.relation!r}")
    raised_type = (_resolve_exception_type(cj.rhs, fn)
                   if cj.relation == "raises" and cj.rhs else None)
    if cj.relation == "raises" and cj.rhs and raised_type is None:
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"unknown exception type {cj.rhs!r}")
    # A registered family's own "probe:algorithmic" route, tried
    # before the generic blind-sampling loop below, reachable for
    # route="best" once ordinary derive/family-derive didn't resolve
    # the claim, and for a plain route="probe" claim on a
    # family-owned name (the orchestration loop resolves the family
    # for every concrete route). Calls fn directly, not through the
    # compiled lhs/rhs eval() the generic loop below needs.
    algo_route = family.routes().get("probe:algorithmic") if family is not None else None
    if algo_route is not None:
        # the probe is registered under "probe:algorithmic", but a member
        # may name a more specific mechanism to stamp (fuzz + shrink ->
        # "probe:minimal_example"); the stamped subroute has its own rung
        # on EVIDENCE_LADDER.
        probe_route = getattr(family, "probe_route", "probe:algorithmic")
        setup = sampling()
        from . import _premises
        from .runtime_types import calling
        try:
            guard = _family_premise_guard(ctx, fn, facts, kinds, cj_domain)
        except (InvalidConjecture, KeyError) as e:
            return Probe(cj.name, statement, "skipped", route=None,
                         note=f"{note}; assuming clause isn't evaluable "
                              f"on the probe route: {e}")
        family_fn = calling(fn, facts)
        with _premises.active(guard):
            algo_result = algo_route(
                guard.wrap(family_fn) if guard is not None else family_fn,
                facts, cj, cj_domain, setup.rng, setup.budget)
        premise_unmet = (guard is not None and guard.admitted == 0
                         and guard.rejected > 0)
        if algo_result is not None:
            # (verdict, checked, cx), optionally with the established
            # sketch, and then the family's own record meta, copied onto
            # the record, whose `mathema.sampled` text (what was sampled)
            # joins the note
            import copy

            from .claim_families import split_probe_result
            verdict, checked, cx, established, algo_meta = \
                split_probe_result(algo_result)
            algo_meta = copy.deepcopy(algo_meta) if algo_meta else {}
            if algo_meta.get("mathema.sampled"):
                note = f"{note}; {algo_meta['mathema.sampled']}".lstrip("; ")
            # a family's caveat (a hidden input, a restore that failed) is
            # a sentence in the row's note, never a key of its own; it
            # rides on the Probe, outside the record, for a function-wide
            # conjunction to carry into its own note
            caveat = algo_meta.pop("mathema.caveat", None)
            if caveat:
                note = f"{note}; {caveat}".lstrip("; ")
            algo_meta = algo_meta or None

            def _with_caveat(row):
                row._caveat = caveat
                return row
            if verdict == "proven":
                # an ESTABLISHED empirical examination: the guard only
                # lets this through with the exhaustive-coverage
                # sketch, so the surety is real however it was reached
                return Probe(cj.name, statement, "proven", n=checked,
                             route=probe_route, sketch=established,
                             note=note, meta=algo_meta)
            if verdict == "falsified":
                # the safety families whose falsification is BY
                # CONSTRUCTION about the implementation stratum:
                # spelling divergence, unguarded crashes, an overflow
                # and a recursion limit have no mathematical reading at
                # all; a roll-up carries the cause its failing child
                # reports (`mathema.cause`)
                family_cause = {
                    "is_representation_safe": "implementation:representation",
                    "is_language_defined":
                        "implementation:accidental-crash",
                    "is_overflow_safe": "implementation:overflow",
                    "is_recursion_safe": "implementation:recursion-depth",
                }.get(families.claim_base_name(cj.name)) or (
                    algo_meta or {}).get("mathema.cause")
                return _with_caveat(Probe(
                    cj.name, statement, "falsified", n=checked,
                    route=probe_route, counterexample=cx, note=note,
                    stratum=({"blame": "implementation",
                              "cause": family_cause,
                              "witness": cx}
                             if family_cause else None),
                    meta=algo_meta))
            if verdict == "holds":
                return _with_caveat(Probe(
                    cj.name, statement, "holds", n=checked,
                    route=probe_route, note=note, meta=algo_meta))
            if verdict == "unknown":
                # the family examined the function and could not
                # settle it (a roll-up with an unsettled child): the
                # honest unknown, with what was examined in the note
                return Probe(cj.name, statement, "unknown", n=checked,
                             route=probe_route,
                             note=note + (f"; {cx}" if cx else ""),
                             meta=algo_meta)
            why = cx or ("no sampled point satisfied the assuming clause"
                         if premise_unmet else "no evaluable inputs")
            return Probe(cj.name, statement, "skipped", route=probe_route,
                         note=note + f"; {why}", meta=algo_meta)
    if region_claim:
        # the executed reading above is the last one, and it could
        # not sample a point of this claim
        return Probe(cj.name, statement, "unknown", route=None,
                     note=f"{note}; {region_row_kind(cj.name)} is decided by "
                          f"running the code, and the probe could not draw "
                          f"a single point of this claim")
    if cj.relation in routes.examine_predicates():
        # only reachable when the registered family declined, the
        # generic sampling loop below has no meaning for a
        # domain-safety predicate, so stop here rather than
        # dispatching predicate text into the compiled-expression
        # machinery.
        return Probe(cj.name, statement, "unknown", route=None,
                     note=f"{note}; the built-in claim {cj.relation} could not "
                          "decide it, and the probe has no other way to "
                          "check it")
    # a string parameter with no stated domain has no honest sampling
    # story, as in the automatic probes: numbers drawn for it would
    # falsify the claim on inputs the function was never meant to take
    from .domain import bare_text_type
    named = _names_in_claim(cj)
    for p, k in kinds.items():
        if k == "string" and p in named and (
                ctx.cj_domain.get(p) is None or bare_text_type(ctx.cj_domain.get(p))):
            return Probe(
                cj.name, statement, "skipped", route=None,
                note=(f"{note}; {string_domain_hint(p)}, or annotate it "
                      "Literal[...]"),
                meta={"mathema.probe_gap": "string-domain-missing"})
    # the generic loop's reading of the domain: every unbounded direction,
    # declared or bare, runs with finite values out to the resolved
    # pseudo-infinity, else the number representation's maximum (P1: a
    # real domain contains no infinity)
    from ._sampling import representation_reach
    reach_max = representation_reach()
    cj_domain, _approximated = _operational_domain(
        cj_domain, pinf if pinf is not None else (-reach_max, reach_max),
        bare=bare)
    try:
        if cj.relation == "raises" or cj.rhs_bound is not None:
            code_l, aux_names = _validate(cj.lhs, set(kinds), extra)
            code_r = None
        else:
            code_l, aux_l = _validate(cj.lhs, set(kinds), extra)
            code_r, aux_r = _validate(cj.rhs, set(kinds), extra)
            aux_names = aux_l | aux_r
    except InvalidConjecture as e:
        return Probe(cj.name, statement, "skipped", route=None, note=str(e),
                     meta={"mathema.invalid_conjecture": True})
    aux = sorted(aux_names)
    # a bound extra function is either an already-live callable (an
    # in-process convenience for a caller adjudicating one Conjecture
    # directly, e.g. claim("f(x) == g(x)", funcs={"g": other_fn})) or
    # a dotted "module.qualname" reference, the same shape a spec
    # key already uses, resolved here. Only the reference form
    # survives declare()/entry_claims()'s round trip through the
    # declared-schema dict shape, since a live callable has no
    # serializable representation there.
    try:
        bound_funcs = {name: (v if callable(v) else _resolve_bound_ref(v))
                      for name, v in cj.funcs.items()}
    except AttributeError:
        bound_funcs = {}
    if any(v is None for v in bound_funcs.values()):
        unresolved = [name for name, v in bound_funcs.items() if v is None]
        return Probe(cj.name, statement, "skipped", route=None,
                     note=note + f"; could not resolve bound function(s) "
                                 f"{unresolved}, define it in f's module or "
                                 f"the calling scope, or bind it explicitly "
                                 f"with funcs=")
    from . import _premises
    premise_words = _premises.premise_words()
    assum_eval = None
    if ctx.assumption is not None:
        try:
            assum_eval = _premises.compile_premises(
                cj, ctx.assumption, kinds, extra)
        except (InvalidConjecture, KeyError) as e:
            return Probe(cj.name, statement, "skipped", route=None,
                         note=f"{note}; assuming clause isn't evaluable "
                              f"on the probe route: {e}")
    # an EQUALITY conjunct makes the feasible region a measure-zero
    # surface random draws essentially never land on: solve the
    # equality for one variable symbolically, so every trial computes
    # that coordinate from the others and sits exactly on the surface
    # (the rejection filter below still checks every other conjunct)
    assum_solved = (_premises.solve_equality(ctx.assumption, kinds)
                    if assum_eval is not None else None)
    from . import dimensions as _dims
    from .types import shapes_from_signature
    try:
        resolver = _dims.resolve(facts, shapes_from_signature(fn),
                                 claim_domain=cj_domain)
    except _dims.DimensionConflict as e:
        # the claim's own space form contradicts the signature's Shape
        # marker on how many axes a parameter has: misspecified, skipped
        # with the reason, never adjudicated against one of two shapes
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"{note}; {e}",
                     meta={"mathema.premise": "dimension-conflict"})
    shape_lo, shape_hi, shape_groups = _shape_constraints(
        ctx.assumption, resolver)
    plan_dims = bool(resolver.distinct_keys())
    premise_draws = _premises.premise_draws(ctx.assumption, kinds,
                                            cj_domain, tolerance=cj.tolerance)
    from .types import structures_from_signature
    # a parameter's structure comes from its signature marker and from
    # an `assuming A is symmetric` premise; both narrow synthesis the
    # same way, the premise's set unioned onto the marker's
    param_structures = dict(structures_from_signature(fn))
    for _pp, _props in (ctx.premise_structures or {}).items():
        param_structures[_pp] = tuple(sorted(
            set(param_structures.get(_pp, ())) | set(_props)))
    # the runtime type each sequence parameter is realised as, and the
    # matrices drawn as nested lists, which stay within the list
    # adapter's size cap per axis
    from .runtime_types import ListAdapter, realised_parameters
    runtime_names = {p: d.adapter
                     for p, d in realised_parameters(facts).items()}
    nested = {p for p in kinds if p not in runtime_names and (
        param_structures.get(p) or (resolver.shapes.get(p) is not None
                                    and resolver.shapes[p].ndim >= 2))}
    if shape_lo is not None and shape_hi is not None:
        for p in nested:
            for axis in range(resolver.shapes[p].ndim
                              if p in resolver.shapes else 1):
                key = resolver.key(p, axis)
                if key is not None:
                    shape_hi[key] = min(
                        shape_hi.get(key, max(8, 4 * shape_lo.get(key, 2))),
                        ListAdapter.SIZE_CAP)
    setup = sampling()
    rng, specials = setup.rng, setup.specials
    from .probing import claim_sampling_budget
    risk, budget = claim_sampling_budget(setup, facts, cj_domain)
    if getattr(cj, "trials", None) is not None:
        # the claim's own trials, which may exceed the usual limit
        budget = cj.trials
    critical_hints, truncated_hints = setup.critical_hints, setup.truncated_hints
    extra_cycles, probe_route = setup.extra_cycles, setup.route
    from .probing import _language_lap
    # a language-bound parameter's first draws are one lap over its
    # language's hazards
    language_laps = {p: lap for p in kinds
                     if (lap := _language_lap(rng, cj_domain.get(p))) is not None}
    # a finite set's listed sentinels: each value they stand for is
    # drawn once, before any random draw
    missing_laps = _missing_laps(rng, kinds, cj_domain, ctx.missing,
                                 record_domain=ctx.record_domain)
    from .probing import _SpecialCycle
    for _p in list(language_laps):
        if _p in missing_laps:
            # the absence a language binding admits comes before its hazards
            lap = language_laps[_p]
            first = missing_laps.pop(_p).first_values() + list(lap._first)
            language_laps[_p] = _SpecialCycle(rng, values=lap._values[len(lap._first):],
                                              first=first)
    # what the record says was tried for each listed sentinel
    missing_meta = ({"mathema.missing": {"tried": {
        p: [repr(v) for v in lap.first_values()]
        for p, lap in missing_laps.items()}}} if missing_laps else {})
    # what the function did at each missing input it was called with
    from .probing import ExecutedMissing, LastCall, with_executed
    executed_record = ExecutedMissing()
    from .probing import signature_defaults
    executed_record.defaults = signature_defaults(fn)
    f_call = LastCall()
    from .probing import parameter_defaults
    f_call.defaults = parameter_defaults(fn)
    from ._missing_words import declared_optional_return
    declared_return = declared_optional_return(fn)
    # a membership whose right-hand side names a missing value asks
    # about the missing output itself, and is judged at every point
    asks_missing = _asks_missing(cj)
    # each vector, matrix or table parameter meets its floor of
    # degenerate containers first, then random draws carrying holes
    axis_users: dict = {}
    for _p in kinds:
        for _axis in range(resolver.shapes[_p].ndim if _p in resolver.shapes else 0):
            axis_users.setdefault(resolver.key(_p, _axis), set()).add(_p)
    containers = {}
    import random as _random_mod
    from ._sampling import _RNG_SEED
    implied_rng = _random_mod.Random(_RNG_SEED + 1)
    for _p, _k in kinds.items():
        # a length is the floor's to choose only when no other parameter
        # shares its axis and neither the claim nor a binding over a
        # marker's name fixes a number for it
        shared = any(len(users) > 1 or not str(key).isidentifier()
                     or key in resolver.fixed
                     for key, users in axis_users.items()
                     if key is not None and _p in users)
        made = _container_draws(_p, _k, cj_domain.get(_p),
                                (ctx.record_domain or {}).get(_p), ctx.missing or {},
                                resolver, shared, bool(param_structures.get(_p)))
        if made is not None:
            containers[_p] = made

    def completed_at(point_args) -> bool:
        # a missing input the claim's own binding does not list: the
        # parameter's binding, or the binding of the path that reached it
        from ._missing_policy import keys_of
        for p, v in zip(kinds, point_args):
            for q, _k, _m in keys_of({p: v}, executed_record.paths):
                if not _lists_sentinel(cj_domain.get(q if q in cj_domain else p)):
                    return True
        return False
    lap_floor = None
    def sample_bound(p):
        # a container's elements are drawn from its completed domain, so
        # every spelling of one claim draws the same points; a scalar's
        # from the binding as written
        if p in containers and p not in ctx.implied:
            return (ctx.record_domain or {}).get(p) or cj_domain.get(p)
        return cj_domain.get(p)

    longest_lap = max([*(lap.lap_size() for lap in (*language_laps.values(),
                                                     *missing_laps.values())),
                       *(c.remaining() for c in containers.values())],
                      default=0)
    if longest_lap > budget:
        # a lap longer than the complexity budget raises the trial
        # count to the lap, so every hazard is visited, and the
        # sampling line says so
        lap_floor = (longest_lap, budget)
        budget = longest_lap
    checked, cx, cx_stratum = 0, None, None
    # the largest exact ordering violation the default allowance
    # absorbed, and the arguments it happened at
    absorbed, absorbed_at = 0.0, None
    # the largest disagreement a draw's own round-off accounted for
    roundoff_absorbed, roundoff_at = 0.0, None
    # the largest equality gap the relative tolerance absorbed at a draw
    # that holds in exact arithmetic, and the draws that passed only
    # within a tolerance and could not be evaluated exactly
    relative_absorbed, relative_at = 0.0, None
    inconclusive = 0
    # the draws where the claim's own side has no value, exact or float
    undecided, undecided_at = 0, None
    pinned = _pinned_arg_sets(cj, len(kinds), kinds=list(kinds.values()))
    # `^n` holds n = 1: after every other draw, one more takes every free
    # axis that two parameters share, or that spans a matrix, at its
    # least size together (vectors of length 1 side by side, a 1 by 1
    # matrix), which no single container's floor can build alone; its
    # values come from a stream of their own, so the draws before it are
    # the ones the claim draws without it
    smallest_keys = {key for key, users in axis_users.items()
                     if key is not None and str(key).isidentifier()
                     and key not in resolver.fixed
                     and (len(users) > 1 or any(resolver.shapes[u].ndim >= 2
                                                for u in users))}
    smallest_trial = None
    if plan_dims and smallest_keys:
        smallest_trial = budget + len(pinned)
    # a literal argument in the claim's own call (`f(values, "nope",
    # 0.35)`) fixes that parameter to the literal; the call passes it
    # verbatim, so sampling must not overwrite it with a synthesized
    # value (which would misreport the witness, e.g. `"nope"` as 0).
    varied: set = set()
    literal_args = _literal_call_args(cj.lhs, facts.params, varied)
    if cj.rhs:
        literal_args.update(_literal_call_args(cj.rhs, facts.params, varied))
    literal_args = {p: v for p, v in literal_args.items() if p not in varied}
    # a library call's defaulted parameters the claim leaves alone stay
    # at their defaults, and a pinned one at its pin: fixed values, not
    # samples, and a pin is passed on every call of f
    kept_defaults, call_pins, _problem = call_defaults(fn, cj)
    literal_args.update({p: v for p, v in {**kept_defaults,
                                           **call_pins}.items()
                         if p in kinds and p not in literal_args})
    # the sampling line states only the parameters actually drawn; the
    # held ones are stated by the defaults note
    sampled_kinds = {p: k for p, k in kinds.items()
                     if p not in kept_defaults and p not in call_pins}
    # the domain box's corners replay with the recorded counterexamples,
    # before any random sampling
    pinned += [c for c in _domain_corners(kinds, cj_domain, literal_args)
               if c not in pinned]
    # and the solutions of the function's own guards inside the domain
    pinned += [c for c in _guard_points(fn, facts, kinds, cj_domain,
                                        literal_args)
               if c not in pinned]
    call_raised = [None]   # the LABEL of the callee that raised, or None
    call_nan = [None]      # the LABEL of the first callee to return a NaN
    # the first callee to return a hole of another member (`pd.NA`, `NaT`,
    # a Decimal NaN), as `(label, member)`
    call_hole: list = [None]
    # the LABEL and sign of the first callee to return an infinity for
    # finite arguments
    call_inf: list = [None, 0]
    # the first point where the float computation gave no value, or
    # missed the result beyond its precision, while the claim holds
    # there in exact arithmetic: the `[float]` line's witness, with the
    # conditioning words and record of a miss; or, when the probe stands
    # in for derive and no computation line was asked for, a finding
    computation_cx = None
    computation_note = None
    computation_meta: dict = {}
    computation_finding = None
    stands_in = _stands_in_for_derive(ctx)
    # a library definition row: a failure only at a magnitude corner is a
    # finding about the library's computation, and the row stands
    from .compendium import library_key_of
    corner_row = (cj.name or "").split("@", 1)[0] == "definition" \
        and library_key_of(fn) is not None
    corner_finding = None
    # a loss a definition row's conditioning explains at a draw, and
    # what the conditioning says about the miss a falsification stands on
    conditioning_finding = None
    miss_conditioning = None
    # the side the claim's words make exact, when they settle it; the
    # draw decides where two claim words face each other
    claim_side = reference_side(cj)
    side = claim_side

    def _tagged(callee, label, inject=None):
        # a raise from the function under test (or a bound function) is
        # pedantic evidence; a raise from the law's own plumbing (a
        # malformed sum(...), a bad index, a wrong argument count) is a
        # broken sample, not a counterexample; attribution is the
        # difference
        try:
            sig = callable_signature(callee)
        except (TypeError, ValueError):
            sig = None
        # a complex result under a real claim is no value at all, the
        # same as a raise
        complex_raises = complex_is_a_raise(callee, cj_domain)

        def _wrapped(*a, **k):
            if inject and sig is not None:
                # each pinned parameter the call does not pass itself
                try:
                    given = sig.bind_partial(*a, **k).arguments
                except TypeError:
                    given = {}
                k = {**{p: v for p, v in inject.items() if p not in given},
                     **k}
            if sig is not None:
                try:
                    sig.bind(*a, **k)
                except TypeError:
                    raise   # the law called it wrong: untagged
            try:
                value = callee(*a, **k)
            except Exception:
                call_raised[0] = label
                raise
            if complex_raises and is_complex_value(value):
                call_raised[0] = label
                raise ComplexResult(label, value)
            if call_nan[0] is None and holds_nan(value):
                call_nan[0] = label
            elif call_hole[0] is None and missing_class(value) == "hole":
                from .domain import member_of
                call_hole[0] = (label, member_of(value) or "a hole")
            if call_inf[0] is None:
                sign = holds_inf(value)
                if sign and not any(
                        is_missing(v) or holds_nan(v) or holds_inf(v)
                        for v in (*a, *k.values())):
                    call_inf[0], call_inf[1] = label, sign
            return value
        return _wrapped

    # each call realises the drawn values as the parameters' runtime
    # types and observes the result as a plain value
    from .runtime_types import calling
    # a claim over vectors, matrices or tables evaluates them as numpy
    # arrays (so `x + y` is elementwise, never a list concatenation):
    # each function still receives its arguments as its own runtime
    # type, and what it returns is read back as an array
    from . import _linalg_eval
    from .matrices import _numpy
    array_ranks = _claim_array_ranks(cj_domain, fn, facts)
    array_names = [p for p in array_ranks
                   if p in kinds or p in (cj.free_vars or ())]
    as_arrays = bool(array_names) and _numpy() is not None
    # a witness over vectors or matrices names each argument
    arg_names, shown_names = _witness_labels(cj, kinds, cj_domain)
    if as_arrays:
        arg_names, shown_names = tuple(kinds), None
    table_columns = {p: _table_columns(p, cj, facts)
                     for p, k in kinds.items() if k == "table"}
    fn_call = calling(fn, facts)
    if as_arrays:
        fn_call = _linalg_eval.law_callable(fn_call)
        bound_funcs = {name: _bound_for_arrays(v)
                       for name, v in bound_funcs.items()}
    executed_record.refill_at = _refill_caller(fn_call, call_pins)
    executed_record.fills = {
        p: fill for p in kinds
        if (fill := _fill_value((ctx.record_domain or {}).get(p) or cj_domain.get(p)
                                )) is not None}
    from .domain import path_bindings_verdict
    path_bound = {p for p in kinds
                  if any(key.startswith(p + ".") or key.startswith(p + "[")
                         for key in cj_domain)}
    outside_draw = [False]

    def path_words(point_args) -> list:
        # what each path binding reached that is not a value, as a
        # witness names it: `d.note unset`, `o.lines[1] = null (hole)`
        from .domain import leaf_words, path_leaves, path_steps, path_text
        words: list = []
        for p, v in zip(kinds, point_args):
            if p not in path_bound:
                continue
            for key in cj_domain:
                if not (key.startswith(p + ".") or key.startswith(p + "[")):
                    continue
                for where, leaf in path_leaves(v, path_steps(key[len(p):])):
                    said = leaf_words(path_text(p, where), leaf)
                    if said is not None and said not in words:
                        words.append(said)
        return words

    # the paths the claim binds, whose absences and holes are missing
    # inputs as a parameter's are
    executed_record.paths = {p: [key for key in cj_domain
                                 if key.startswith(p + ".") or key.startswith(p + "[")]
                             for p in path_bound}

    def at_missing(point_args) -> bool:
        # a missing input: an argument that is or holds one, or a path
        # the claim binds that reached an absence or a hole
        return inputs_missing(point_args) or bool(path_words(point_args))

    def in_a_slot(v) -> bool:
        # the argument is missing, or a slot of its vector, matrix or
        # table is; a record's fields are reached by paths instead
        if missing_class(v) is not None:
            return True
        if isinstance(v, dict):
            return False
        if isinstance(v, (list, tuple)):
            return any(in_a_slot(x) for x in v)
        if hasattr(v, "shape") or type(v).__module__.split(".")[0] in (
                "pandas", "polars"):
            return inputs_missing([v])
        return False

    def admitted_hole(point_args) -> bool:
        # a drawn argument holding a hole or absence the claim does not
        # list as one of its own points, one its type or a written
        # clause admits; held, literal and path-bound parameters aside
        return any(in_a_slot(v) and p not in literal_args
                   and p not in path_bound
                   and not _lists_sentinel(cj_domain.get(p))
                   for p, v in zip(kinds, point_args))

    def _point_text(point_args) -> str:
        # the witness's arguments, then what a path reached that is not
        # a value
        said = _fmt(tuple(point_args), arg_names, shown_names)
        words = path_words(point_args)
        return ", ".join([said, *words]) if words else said

    def _drawn_text(point_args) -> str:
        # the drawn arguments alone, the parameters held at their
        # defaults left out: a finding about the computation at a draw
        # names the draw, not the call's whole signature
        drawn = [(p, v) for p, v in zip(kinds, point_args)
                 if p in sampled_kinds]
        if not drawn or len(drawn) == len(kinds):
            return _point_text(point_args)
        return _fmt(tuple(v for _p, v in drawn), tuple(p for p, _v in drawn),
                    shown_names)

    def narrowed(p, draw):
        # a parameter with path bindings is drawn until every binding
        # holds, a bounded rejection; a point none satisfies is outside
        # the claim's domain. A draw a path reaches no value in (an
        # index past the end, a field holding None) is counted
        v = draw()
        if p not in path_bound:
            return v
        for _ in range(21):
            said = path_bindings_verdict(v, p, cj_domain)
            if said is None:
                return v
            if said == "no value":
                ctx.path_no_value += 1
            if _ == 20:
                outside_draw[0] = True
                return v
            v = draw()
        return v

    fn_tagged = f_call.wrap(_tagged(fn_call, "f", inject=call_pins))

    def f_nan_unread(env, lv, rv) -> bool:
        # whether the claim's sides never read a nan f returned: they
        # come out the same with every nan in f's output filled by v,
        # 2v and 0.9v (v = 1)
        if holds_nan(lv) or holds_nan(rv):
            return False
        from ._missing_policy import _same_output
        flags = (call_raised[0], call_nan[0], call_hole[0], list(call_inf))
        plain_f = _tagged(fn_call, "f", inject=call_pins)
        try:
            for fill in (1.0, 2.0, 0.9):
                env_filled = {**env, "f": lambda *a, _fill=fill, **k:
                              _nan_filled(plain_f(*a, **k), _fill)}
                try:
                    lf = eval(code_l, {"__builtins__": {}}, env_filled)
                    rf = (eval(code_r, {"__builtins__": {}}, env_filled)
                          if code_r is not None else None)
                except Exception:
                    return False
                if as_arrays:
                    lf = _linalg_eval.scalar(lf)
                    rf = _linalg_eval.scalar(rf) if code_r is not None else None
                if not (_same_output(lf, lv) and _same_output(rf, rv)):
                    return False
            return True
        finally:
            call_raised[0], call_nan[0], call_hole[0] = flags[:3]
            call_inf[:] = flags[3]
    # a claim that names the function under test (`clamp(rate)`) calls f
    bound_tagged = {name: (f_call.wrap(_tagged(v, name)) if _is_under_test(v, fn)
                           else _tagged(v, name))
                    for name, v in bound_funcs.items()}
    # the lengths the samples inside the premise region actually had,
    # per sequence parameter, for the sampling note
    sequence_params = [p for p, k in kinds.items()
                       if k in SEQUENCE_KINDS or k == "table"]
    observed_lengths: dict = {}
    args: list = []
    from ._missing_words import DrawTally
    tally = DrawTally()
    # a draw is tallied when the row counted it
    tallied = checked
    main_rng = rng
    for trial in range(budget + len(pinned) + (smallest_trial is not None)):
        if checked > tallied:
            tally.add(dict(zip(kinds, args)))
            tallied = checked
        if trial == smallest_trial:
            rng = _random_mod.Random(_RNG_SEED + 2)
        f_call.record(executed_record, dict(zip(kinds, args)))
        call_raised[0] = call_nan[0] = call_inf[0] = call_hole[0] = None
        outside_draw[0] = False
        # the first sampled trials are a claim's guaranteed small draws:
        # length 1 and a 1-by-1 matrix, then 1-by-n, then n-by-1
        small_round = trial - len(pinned) \
            if 0 <= trial - len(pinned) < 3 else None
        trial_sizes: dict = (
            _draw_trial_sizes(resolver, shape_lo, shape_hi, shape_groups, rng,
                              floor=small_round)
            if plan_dims and trial >= len(pinned) else {})
        if trial == smallest_trial:
            trial_sizes = {k: (max(1, (shape_lo or {}).get(k, 1))
                               if k in smallest_keys else size)
                           for k, size in trial_sizes.items()}
        # MATH_CONSTANTS before the per-trial parameter assignment
        # below, so a parameter named `e`/`pi` overrides the constant
        # (precedence identical to the derive route)
        env = {"f": fn_tagged, **_SAFE_FUNCS, **_linalg_eval.FUNCTIONS,
               **MATH_CONSTANTS, **bound_tagged}
        args = []
        if trial < len(pinned):
            # a counterexample already on record replays before any
            # sampling: a past falsification stays caught forever, and
            # a fixed implementation must clear the exact point that
            # broke it before fresh evidence counts.
            for p, v in zip(kinds, pinned[trial]):
                env[p] = v
                args.append(v)
        else:
            for p, k in kinds.items():
                if p in literal_args:
                    # the call fixes this parameter to a literal: use it
                    # verbatim for both the sample and the witness.
                    v = literal_args[p]
                    env[p] = v
                    args.append(v)
                    continue
                if k == "dict" and getattr(cj_domain.get(p), "base_type",
                                           None) == "L":
                    # a mapping parameter quantified over a language: the
                    # members ARE the mappings, drawn from the language
                    v = narrowed(p, lambda p=p, k=k: _synth(
                        k, rng, cj_domain.get(p), lap=language_laps.get(p)))
                    env[p] = v
                    args.append(v)
                    continue
                if k == "dict":
                    # a mapping parameter: synthesise a dict matching the
                    # nested key structure the body reads (from
                    # facts.tree), so `d["field"]`, `d["a"]["b"]` and
                    # `d.values()` all find what they expect.
                    from .symbolic._base import _dict_key_tree
                    tree_keys = (_dict_key_tree(facts.tree, p)
                                 if facts.tree is not None else {})
                    # a claim's binding of one key (`d.note in ...`)
                    # bounds what that key holds, its absence included
                    fields = {key[len(p) + 1:]: b for key, b in cj_domain.items()
                              if key.startswith(p + ".")
                              and key[len(p) + 1:].isidentifier()}
                    v = _synth_dict(tree_keys, rng, specials, fields=fields)
                    env[p] = v
                    args.append(v)
                    continue
                if p in bundles:
                    v = _synth_instance(bundles[p], p, cj_domain, rng,
                                        specials)
                    env[p] = v
                    args.append(v)
                    continue
                if k == "table" and getattr(cj_domain.get(p), "base_type",
                                            None) != "L":
                    # a table: one equal-length column per name the
                    # claim or the body reads (a table language draws
                    # its own members below); a vector domain on the
                    # table (`for df in [0, 1]^n`) bounds every column
                    bound = sample_bound(p)
                    column = bound if len(getattr(bound, "dims", ())
                                          or ()) == 1 else None
                    # a fixed dimension on the table's vector domain is
                    # every column's length; a column's own binding
                    # (`for df.r in [0, 1]^n`) bounds that column
                    length = (trial_sizes.get(resolver.key(p, 0))
                              or rng.randint(1, 8))
                    v = {c: _synth("sequence", rng,
                                   _column_bound(cj_domain.get(f"{p}.{c}"), column),
                                   specials=specials, length=length)
                         for c in table_columns[p]}
                    if p in containers:
                        v = containers[p].next(v, rng)
                    env[p] = v
                    args.append(v)
                    continue
                shape = resolver.shapes.get(p)
                if param_structures.get(p):
                    # a structure-marked matrix: synthesised WITH the
                    # declared property (symmetric, positive-definite,
                    # ...), entailment-closed, at the resolved square
                    # size; the marker narrows the domain to matrices
                    # that have the structure rather than any nested list
                    from . import matrices as _mtx
                    key = resolver.key(p, 0)
                    n = trial_sizes.get(key) or rng.randint(1, 5)
                    v = _mtx.synth_for(param_structures[p], n, rng)
                elif shape is not None and (
                        shape.ndim >= 2
                        or (shape.ndim == 1 and k not in SEQUENCE_KINDS)):
                    # a matrix-shaped (marker-declared) parameter, or a
                    # space binding (`R^n`, `R^(n,n)`) on a parameter
                    # whose kind the signature does not state: the
                    # resolver nests to the axes, each leaf a fresh
                    # element draw, sizes fixed by the shape plan
                    # (shared marker dims agree by construction)
                    v = resolver.synth(
                        p, trial_sizes,
                        lambda: _synth("float", rng, sample_bound(p),
                                       specials=specials), rng)
                    if shape.ndim == 2:
                        from .matrices import rank_edge
                        v = rank_edge(v, trial)
                else:
                    # a scalar or 1-D sequence: _synth owns the element
                    # domain and the special-value shapes; the plan
                    # only fixes a 1-D length when a premise did
                    length = trial_sizes.get(resolver.key(p, 0))
                    if length is None and small_round == 0 \
                            and k in SEQUENCE_KINDS:
                        length = 1
                    v = narrowed(p, lambda p=p, k=k, length=length: _synth(
                        k, rng, sample_bound(p),
                        specials=specials, extra=critical_hints.get(p),
                        extra_cycle=extra_cycles.get(p),
                        length=length,
                        lap=language_laps.get(p) or missing_laps.get(p)))
                if p in containers and isinstance(v, (list, tuple)) \
                        and trial != smallest_trial:
                    # the floor's degenerate containers first, then
                    # draws carrying holes
                    # a binding the claim left to the signature draws its
                    # holes from a stream of its own, so the values the
                    # claim draws are the ones it drew without them
                    v = containers[p].next(list(v), implied_rng if p in ctx.implied
                                           else rng)
                env[p] = v
                args.append(v)
            for p, draw in premise_draws.items():
                # an equality premise fixes this parameter's draw, so
                # the sample lies on the premise by construction
                if p in literal_args:
                    continue
                v = draw(rng, trial_sizes.get(resolver.key(p, 0)))
                env[p] = v
                args[list(kinds).index(p)] = v
        if outside_draw[0]:
            # a path binding no draw satisfied: the point is outside the
            # claim's domain, so it neither confirms nor denies anything
            continue
        for a_name in aux:
            # eps/epsilon/ε resolve to the claim's own declared
            # tolerance, not a random aux value, same convention as
            # the derive route (symbolic.py's try_prove). An aux name
            # with its own declared bound in cj_domain (a `let name
            # be bounds` free variable) is sampled respecting that
            # bound; "float" is a placeholder kind here, not a
            # commitment to real-valued sampling: _synth dispatches
            # on the bound's own shape first (Domain/frozenset/"Z"/
            # "N" all override it), so an explicit `⊂ Z` refinement
            # on the free variable's own declaration still samples
            # integers regardless. Anything genuinely undeclared
            # keeps the old fixed uniform(-5, 5); there's no bound
            # to respect for a name nobody ever gave one.
            if a_name in ("eps", "epsilon", "ε"):
                env[a_name] = (cj.tolerance if cj.tolerance is not None
                               else DEFAULT_TOLERANCE)
            elif getattr(cj_domain.get(a_name), "dims", ()):
                # a declared vector or matrix (`let b be R^n`): each
                # axis named by a dimension the parameters carry takes
                # that dimension's size in this trial
                env[a_name] = _free_array(cj_domain[a_name], resolver,
                                          trial_sizes, env, rng, specials)
            elif a_name in cj_domain:
                env[a_name] = _synth("float", rng, cj_domain[a_name], specials=specials)
            else:
                env[a_name] = rng.uniform(-5, 5)
        if not all(_sample_in_domain(env[p], cj_domain.get(p))
                   for p in [*kinds, *aux] if p in env and p not in literal_args):
            # a point outside the declared domain says nothing about the
            # claim: a recorded counterexample from a wider domain, or a
            # draw that rounded past an open or fractional end, is
            # rejected before the function is called
            continue
        if assum_solved is not None and trial >= len(pinned):
            # place the sample exactly on the assumed equality surface:
            # the solved-out coordinate is computed from the others,
            # then held to its own declared bound like any draw
            if not _premises.place_solved(assum_solved, env, cj_domain):
                continue
            p_name = assum_solved[0]
            if p_name in kinds and p_name in env:
                args[list(kinds).index(p_name)] = env[p_name]
        if as_arrays:
            for p in array_names:
                if p in env:
                    env[p] = _linalg_eval.as_array(env[p])
        # marker dim names (Shape("m","n")) become real quantities the
        # premise and law can reference, read off this trial's shapes
        resolver.bind_env(env, {p: env[p] for p in kinds if p in env})
        if assum_eval is not None:
            # the claim only quantifies over the region the assuming
            # clause carves out: a sample violating ANY conjunct
            # neither confirms nor denies anything (rejection sampling)
            for a_name in sorted(assum_eval.aux):
                if a_name not in env:
                    env[a_name] = rng.uniform(-5, 5)
            if not _premises.admits(assum_eval, {**env, **premise_words}):
                continue
        for p in sequence_params:
            if isinstance(env.get(p), (list, tuple)) or (
                    _linalg_eval.is_array(env.get(p)) and env[p].ndim >= 1):
                observed_lengths.setdefault(p, set()).add(
                    _shapes.observed_shape(env[p]) or (len(env[p]),))
        if cj.relation == "raises" and completed_at(args):
            # a missing input the type admitted and the claim did not
            # list: what the call does there is classified, not judged
            try:
                eval(code_l, {"__builtins__": {}}, env)
            except Exception:
                pass
            executed_record.classified += 1
            continue
        if cj.relation == "raises":
            # the claim is that the call raises: returning any value is
            # the counterexample, raising the wrong type falsifies a
            # typed raises claim, raising right is a pass
            try:
                v = eval(code_l, {"__builtins__": {}}, env)
            except Exception as e:
                checked += 1
                if raised_type is not None and not isinstance(e, raised_type):
                    cx = (f"{_point_text(args)}: raised "
                          f"{type(e).__name__}, claimed {cj.rhs}")
                    break
                continue
            checked += 1
            cx = f"{_point_text(args)}: returned {v!r} instead of raising"
            break
        try:
            lv = eval(code_l, {"__builtins__": {}}, env)
            rv = eval(code_r, {"__builtins__": {}}, env) if code_r is not None else None
            if as_arrays:
                # a 1-by-1 result (`x.T @ A @ x` over a column) is the
                # number it holds
                lv = _linalg_eval.scalar(lv)
                rv = _linalg_eval.scalar(rv) if code_r is not None else None
        except Exception as e:
            if not call_raised[0] and admitted_hole(args):
                # the claim's own words at a hole or absence it only
                # admits: classified, the companions judge f there
                executed_record.classified += 1
                continue
            if not call_raised[0] and not at_missing(args) and (
                    call_nan[0] == "f" or call_inf[0] is not None):
                # the code gave no value at a finite input, whatever the
                # claim's own float side does there
                checked += 1
                cx = (f"{_point_text(args)}: "
                      + (f"{call_inf[0]} returned "
                         f"{'-inf' if call_inf[1] < 0 else 'inf'}"
                         if call_inf[0] is not None else "f returned nan")
                      + ", and no value for a finite input")
                break
            if not call_raised[0]:
                if isinstance(e, (IndexError, ZeroDivisionError)):
                    # the claim's own expression has no value at this
                    # in-domain point: an index outside a sequence it
                    # reads (a literal `[9]` past the end of a result),
                    # or a division by zero
                    checked += 1
                    cx = (f"{_fmt(tuple(args), arg_names, shown_names)}: "
                          f"the claim's own expression raised "
                          f"{type(e).__name__} ({e}); narrow the claim's "
                          f"domain to where it has a value")
                    break
                elif claim_side_has_no_value(e):
                    # the claim's own side has no real value at this
                    # in-domain point: the claim is wrong there
                    checked += 1
                    cx = (f"{_fmt(tuple(args), arg_names, shown_names)}: "
                          f"the claim's own side has no real value here "
                          f"({e}); narrow the claim's domain to where "
                          f"every side of it is real")
                    break
                # the claim's own side has no float value here: read
                # exactly when it can be (`_exact_side`), else the draw
                # is undecided and the claim cannot hold
                call_raised[0] = call_nan[0] = call_inf[0] = None
                decided = _exactly_decided(
                    cj, code_l, code_r, env, {"f": fn_call, **bound_funcs},
                    None, side=side)
                if decided is True and _exactly_decided(
                        cj, code_l, code_r, env,
                        {"f": fn_call, **bound_funcs}, None,
                        within=0.0, side=side) is not True:
                    # it passes only within the tolerance: the
                    # mathematics at the point decides
                    decided = _exact_verdict(cj, code_l, code_r, env,
                                             fn_call, bound_funcs)
                    if decided is None:
                        call_raised[0] = call_nan[0] = call_inf[0] = None
                        call_hole[0] = None
                        inconclusive += 1
                        continue
                call_raised[0] = call_nan[0] = call_inf[0] = call_hole[0] = None
                if decided is None:
                    if undecided_at is None:
                        undecided_at = (f"{_point_text(args)}: the claim's own "
                                        f"side raised {type(e).__name__} "
                                        f"({e})")
                    undecided += 1
                    continue
                checked += 1
                if decided is False:
                    cx = (f"{_point_text(args)}: the claim is false here, "
                          f"its own side read exactly")
                    break
                continue
            if ctx.exclude_own_guards and call_raised[0] == "f" \
                    and deliberate_raise(e, fn):
                # a draw f's own guard refuses is outside the working
                # domain of a claim that binds none: never a trial
                ctx.guard_refused += 1
                continue
            if ctx.assume_defined and call_raised[0] == "f":
                # `assuming is_defined(f)`: a sample where F raises is
                # outside the quantified region, rejected. A raise
                # from a BOUND function is not excused: is_defined(f)
                # says nothing about g, and the pedantic reading stands
                continue
            if at_missing(args) and not asks_missing:
                # a raise at a missing input is classified into the
                # executed missing inputs, never judged
                executed_record.classified += 1
                continue
            # a raise at a floating-point BOUNDARY: sin(m)^2 + cos(m)^2
            # can round to 1.0000000000000002 and push acos past its
            # edge at an isolated float, however exact the mathematics
            # is. It is still a raise at an in-domain point, so it
            # falsifies like any other; when every input nudged within
            # the tolerance evaluates AND satisfies the claim, the
            # counterexample names it as sub-epsilon fragility (stratum
            # 5.6) with the clamp remedy instead of the domain one.
            slack = cj.tolerance if cj.tolerance is not None else DEFAULT_TOLERANCE
            boundary = False
            # a refusal by the function's own mathema guard is the guard
            # doing its job at its own boundary, never a float wobble
            from .authoring import DomainError as _GuardRefusal
            refused = isinstance(e, _GuardRefusal)
            for direction in ((1.0, -1.0) if not refused else ()):
                jenv = dict(env)
                for p in kinds:
                    v = jenv[p]
                    if isinstance(v, float):
                        jenv[p] = v * (1.0 + direction * slack) \
                            + direction * slack * 1e-3
                try:
                    jl = eval(code_l, {"__builtins__": {}}, jenv)
                    jr = eval(code_r, {"__builtins__": {}}, jenv)
                    jok = (_close(jl, jr, tolerance=slack,
                                  rel_tol=_declared_rel_tol(cj))
                           if cj.relation in ("==", "~=") else
                           values_differ(jl, jr, tolerance=slack,
                                         rel_tol=_declared_rel_tol(cj))
                           if cj.relation == "!=" else
                           jl <= jr + slack if cj.relation == "<=" else
                           jl >= jr - slack)
                except Exception:
                    continue
                if jok:
                    boundary = True
                    break
            if boundary:
                checked += 1
                cx = (f"{_point_text(args)}: raised {type(e).__name__} at a "
                      f"floating-point boundary (the same inputs nudged "
                      f"within ε evaluate cleanly), a clamp at the raising "
                      f"operation's argument would remove the instability")
                # nudged inputs evaluating cleanly IS the maths-sound
                # evidence: the failure lives in the number
                # representation's last ulp
                cx_stratum = {"mathematics": "sound",
                              "blame": "implementation",
                              "cause": "implementation:sub-epsilon-boundary",
                              "representation": "f64",
                              "witness": _point_text(args)}
                break
            # a TypeError under a NON-INTEGER sample against a callable
            # with an int-typed parameter is a claim-domain
            # misspecification, not a counterexample: the sampled point
            # violates the signature's own type contract (range(7.7),
            # observed live via a float-typed twin bound to an
            # int-typed loop), so falsifying would blame the function
            # for the claim's missing `subset Z`. Say so loudly and
            # skip; a TypeError at all-integral samples still
            # falsifies like any other raise.
            if isinstance(e, TypeError):
                raiser = fn if call_raised[0] == "f" \
                    else bound_funcs.get(call_raised[0])
                int_params = _int_annotated_params(raiser)
                nonint = [p2 for p2, v2 in zip(kinds, args)
                          if p2 in int_params and isinstance(v2, float)
                          and not float(v2).is_integer()]
                if not nonint:
                    nonint = [p2 for p2, v2 in zip(kinds, args)
                              if isinstance(v2, float)
                              and not float(v2).is_integer()]
                if int_params and nonint:
                    return Probe(
                        cj.name, statement, "skipped:misspecified",
                        route=None,
                        note=f"{note}; {call_raised[0]} raised TypeError at "
                             f"{_point_text(args)}: parameter(s) "
                             f"{', '.join(int_params)} of "
                             f"{call_raised[0]} are int-typed but the "
                             f"claim's domain admits non-integers "
                             f"({', '.join(nonint)}); add `subset Z` "
                             f"to the integer variable's domain")
            # a raise on the list realisation of a parameter the body
            # uses as a vector, matrix or table while the signature
            # names no runtime type for it, in a module importing a
            # library with a runtime type adapter: the list was the
            # wrong object to hand the function, a misspecification of
            # the parameter's type, never a counterexample
            if call_raised[0] == "f" and isinstance(
                    e, (TypeError, ValueError, AttributeError)):
                hints = facts.runtime_hints or {}
                listed = [hints[p2]["text"] for p2, v2 in zip(kinds, args)
                          if p2 in hints and isinstance(v2, (list, tuple))]
                if listed:
                    return Probe(
                        cj.name, statement, "skipped:misspecified",
                        route=None,
                        note=f"{note}; f raised {type(e).__name__} at "
                             f"{_point_text(args)}, sampled as a list: "
                             + "; ".join(listed))
            # a raise is not a value: the claim asserts an equality or
            # ordering AT this in-domain point, and there is nothing on
            # one side to compare, pedantically, that falsifies it.
            checked += 1
            if isinstance(e, ComplexResult):
                cx = (f"{_point_text(args)}: {e}, which a real claim reads "
                      f"as a raise; narrow the claim's domain to where every "
                      f"call is real, or annotate the function complex")
                break
            cx = (f"{_point_text(args)}: raised {type(e).__name__}, narrow "
                  "the claim's domain to where every call returns, or state "
                  "the raising region as its own raises(...) claim")
            cx_stratum = _machine_failure_stratum(e, _point_text(args))
            break
        if cj.relation in ("in", "not in") and not asks_missing \
                and at_missing(args) \
                and classified(args, f_call.outputs() or [lv, rv]):
            # membership in a set of values at a missing input that came
            # back missing: classified, as a value claim's point is
            executed_record.classified += 1
            continue
        if cj.relation in ("in", "not in"):
            # membership is exact: a value is in the language or the
            # set, or it is not, and a missing value is in neither
            # unless the right-hand side admits it in so many words
            if cj.rhs_bound is not None:
                # a named axis of the output's space takes the size this
                # trial bound to the name
                sizes = _shapes.axis_sizes(cj_domain, {p: env[p] for p in kinds if p in env})
                member = _membership_member(lv, cj.rhs_bound, sizes)
            else:
                try:
                    member = bool(lv in rv)  # type: ignore[operator]
                except (TypeError, ValueError):
                    # a value that cannot be looked up in this rhs (an
                    # array's membership has no single truth value):
                    # unanswerable at this point, not a counterexample
                    continue
            checked += 1
            if member != (cj.relation == "in"):
                if as_arrays:
                    lv = _linalg_eval.shown(lv)
                cx = (f"{_point_text(args)}: {lv!r} is "
                      f"{'not ' if cj.relation == 'in' else ''}in {cj.rhs}")
                break
            continue
        missing_in = at_missing(args)
        if missing_in and (admitted_hole(args)
                           or classified(args, f_call.outputs() or [lv, rv])):
            # an admitted hole, or a missing output at a listed one:
            # classified into the executed missing inputs, never judged;
            # the missing and absence companions judge what f does there
            executed_record.classified += 1
            continue
        from ._exact_side import some_side_is_finite
        float_gave_out = not missing_in and (
            call_hole[0] is not None or holds_nan(lv) or holds_nan(rv)
            or (call_nan[0] == "f" and not f_nan_unread(env, lv, rv))
            or (call_inf[0] is not None and not (
                same_infinity(lv, rv)
                and cj.relation in ("==", "~=", "<=", ">=")
                and not some_side_is_finite(code_l, code_r, env,
                                            {"f": fn_call, **bound_funcs}))))
        if corner_row and _magnitude_corner(args) and (
                float_gave_out or call_inf[0] is not None
                or call_nan[0] == "f" or holds_nan(lv) or holds_nan(rv)):
            # a definition row's library gave no value at a magnitude
            # corner: a finding about its computation, not a wrong model
            checked += 1
            if corner_finding is None:
                corner_finding = _drawn_text(args)
            call_raised[0] = call_nan[0] = call_inf[0] = call_hole[0] = None
            continue
        if float_gave_out and (ctx.companion_mode == "spawn" or stands_in) \
                and _exactly_holds_at(cj, code_l, code_r, env, fn_call,
                                      bound_funcs):
            # the float computation gave no value (an overflow to inf or
            # nan) where the claim holds in exact arithmetic: a failure
            # of the computation, carried by the `[float]` line; where the
            # probe stands in for derive and no computation line was asked
            # for, a finding
            checked += 1
            gave = (f"{call_hole[0][0]} returned {call_hole[0][1]}"
                    if call_hole[0] is not None
                    else f"{call_nan[0]} returned nan" if call_nan[0] is not None
                    else f"{call_inf[0]} returned "
                         f"{'-inf' if call_inf[1] < 0 else 'inf'}"
                    if call_inf[0] is not None else
                    f"{_linalg_eval.shown(lv)!r} vs "
                    f"{_linalg_eval.shown(rv)!r}")
            if ctx.companion_mode == "spawn":
                if computation_cx is None:
                    computation_cx = f"{_point_text(args)}: {gave}"
            elif computation_finding is None:
                computation_finding = (
                    f"the {_representation_word(cj_domain, facts)} computation "
                    f"gave no value at {_point_text(args)} ({gave}), where the "
                    f"claim holds in exact arithmetic: a finding about the "
                    f"computation")
            call_raised[0] = call_nan[0] = call_inf[0] = call_hole[0] = None
            continue
        if not missing_in and call_hole[0] is not None:
            # a hole of any member computed from inputs that are not
            # missing is no value, as a NaN is
            checked += 1
            cx = f"{_point_text(args)}: {call_hole[0][0]} returned {call_hole[0][1]}"
            break
        if not missing_in and (holds_nan(lv) or holds_nan(rv) or (
                call_nan[0] == "f" and not f_nan_unread(env, lv, rv))):
            # a NaN computed from inputs that are not missing is no
            # value, like a raise: every value relation fails at this
            # in-domain point, `!=` included, and the witness names
            # the callee that returned it; f's own nan fails it even
            # where the claim's words read past it (`sum(f(xs))`), and
            # not where the claim never reads that slot (`f(a)[1:]`)
            checked += 1
            cx = (f"{_point_text(args)}: {call_nan[0]} returned nan"
                  if call_nan[0] is not None else
                  f"{_point_text(args)}: "
                  f"{_linalg_eval.shown(lv)!r} vs "
                  f"{_linalg_eval.shown(rv)!r}, and a nan is no value")
            break
        if call_inf[0] is not None and same_infinity(lv, rv) \
                and not some_side_is_finite(code_l, code_r, env,
                                            {"f": fn_call, **bound_funcs}):
            # both sides overflow toward the same infinity: one
            # extended-real point, so the point reads as two equal
            # values (a NaN never gets here, it agrees with nothing);
            # where a side read exactly is finite, the code overflowed
            # and the infinity is no value (below)
            checked += 1
            if cj.relation in ("==", "~=", "<=", ">="):
                continue
            cx = (f"{_point_text(args)}: both sides are "
                  f"{'-inf' if call_inf[1] < 0 else 'inf'}, the same point, "
                  f"which {cj.relation} does not admit")
            break
        if call_inf[0] is not None:
            # an infinity a callee returned for finite arguments is an
            # overflow or a pole, the computation not producing a value
            # (the case where `math` raises): against a value, or the
            # opposite infinity, every value relation fails
            checked += 1
            cx = (f"{_point_text(args)}: {call_inf[0]} returned "
                  f"{'-inf' if call_inf[1] < 0 else 'inf'}, and an "
                  f"infinity for a finite input is no value")
            break
        if not missing_in and "absent" in (missing_class(lv), missing_class(rv)):
            # a None f returned from present inputs is the absence policy
            # line's fact: declared by the return type, or flagged there
            from ._missing_words import absence_agrees, absence_words
            if any(o is None for o in f_call.outputs()):
                if declared_return:
                    executed_record.returned_absent(dict(zip(kinds, args)),
                                                    declared_return)
                else:
                    from .policy import record_introduced
                    record_introduced(dict(zip(kinds, args)))
            if absence_agrees(lv, rv, cj.relation):
                # absence compares as absence: None agrees with None
                checked += 1
                continue
            if declared_return and any(o is None for o in f_call.outputs()):
                # a None the return type declares, against a value or
                # under a relation absence does not admit: recorded above,
                # not judged
                continue
            # an absence against a value, under != or under an ordering
            # fails every relation
            checked += 1
            cx = (f"{_point_text(args)}: "
                  f"{_linalg_eval.shown(lv)!r} vs {_linalg_eval.shown(rv)!r}, "
                  f"{absence_words(lv, rv, cj.relation)}")
            break
        if missing_in:
            # the code returned a value at a missing input: judged as
            # usual, a side the law left without a value failing
            ok = relation_within(lv, rv, cj.relation, cj.tolerance, 0.0, side,
                                 exact_inequality=cj.tolerance is None)
            if ok is False:
                ok = _exactly_decided(
                    cj, code_l, code_r, env, {"f": fn_call, **bound_funcs},
                    ok, side=side)
                call_raised[0] = call_nan[0] = call_inf[0] = None
            if ok is None:
                continue
            checked += 1
            if ok is False:
                cx = (f"{_point_text(args)}: "
                      f"{_linalg_eval.shown(lv)!r} vs {_linalg_eval.shown(rv)!r}")
                break
            continue
        checked += 1
        # a declared tolerance governs the comparison outright; the
        # 1e-9 default is only a floating-point-representation fudge
        # factor for claims that never declared one, and must not
        # swamp a genuinely smaller declared tolerance (e.g. ε used
        # as the claim's own bound, where 1e-9 could dominate it)
        slack = cj.tolerance if cj.tolerance is not None else DEFAULT_TOLERANCE
        # `~=` (approximately equal) is not a separate comparison: it
        # is exactly what a toleranced `==` already means, kept as
        # its own relation token only so to_latex() can still render
        # \approx (see grammar.py's _UNICODE).
        # strict relations get NO tolerance credit: `>` at measured
        # equality is not supported (0 > 0 must fail, or a claim false
        # at every point can ride the slack to "holds"); tolerance
        # relieves only the closed relations, whose truth a float wobble
        # can obscure but not create. A matrix/array-valued side (a
        # function returning a matrix, `0 <= f(X) <= 1`) is compared
        # ELEMENTWISE: the relation holds iff it holds at every element,
        # a scalar broadcasting across the matrix.
        if as_arrays:
            lv, rv = _linalg_eval.comparable(lv, rv)
        # the claim read exactly decides where it can be (the code's
        # results as the values it returned): a float claim side that
        # rounds the way the code does would agree with it and hide the
        # code's error. Every comparison is within the one computation
        # allowance (`_allowance`): the absolute part never exceeds the
        # relative part of the result
        # f is read exactly as the claim calls it, its pins passed
        callees = {"f": _with_pins(fn_call, call_pins), **bound_funcs}
        exact_now = exact_sides(code_l, code_r, env, callees)
        side = exact_side_at(cj, code_l, code_r, env, claim_side, callees)
        call_raised[0] = call_nan[0] = call_inf[0] = None
        compare_l, compare_r = (exact_now if exact_now is not None
                                else (lv, rv))
        ok = relation_within(compare_l, compare_r, cj.relation, cj.tolerance,
                             0.0, side, exact_inequality=cj.tolerance is None)
        hidden_by_float = exact_now is not None and ok is False and \
            relation_within(lv, rv, cj.relation, cj.tolerance, 0.0, side,
                            exact_inequality=cj.tolerance is None) is True
        roundoff_gap = None
        if ok is False and as_arrays \
                and cj.relation in ("==", "~=", "<=", ">="):
            # the draw disagrees by no more than the round-off its own
            # magnitudes produce (inputs moved by a few units in the
            # last place move the sides by as much), which enters the
            # absolute part of the allowance and is capped with it
            allowance = _linalg_eval.roundoff_allowance(
                lambda jenv: (eval(code_l, {"__builtins__": {}}, jenv),
                              eval(code_r, {"__builtins__": {}}, jenv)),
                env, [*array_names, *(p for p in kinds
                                      if isinstance(env.get(p), float))],
                (lv, rv), domain=cj_domain)
            call_raised[0] = call_nan[0] = call_inf[0] = None
            if allowance > 0 and relation_within(
                    compare_l, compare_r, cj.relation, cj.tolerance,
                    allowance, side, exact_inequality=cj.tolerance is None):
                ok = True
                roundoff_gap = _linalg_eval.largest_gap(lv, rv)
        within = (ok is True and cj.tolerance is None
                  and cj.relation in ("==", "~=")
                  and relation_within(compare_l, compare_r, cj.relation,
                                      ABSOLUTE, 0.0, side) is not True)
        exactly_false = False
        if within:
            # a draw that passes only within a tolerance is decided in
            # exact arithmetic: false there falsifies, true there holds
            # with the gap printed, and a draw that cannot be evaluated
            # exactly is inconclusive and not counted
            exact_ok = _exact_verdict(cj, code_l, code_r, env, fn_call,
                                      bound_funcs)
            call_raised[0] = call_nan[0] = call_inf[0] = call_hole[0] = None
            if exact_ok is None:
                checked -= 1
                inconclusive += 1
                continue
            if exact_ok is False:
                ok, exactly_false = False, True
            elif roundoff_gap is not None:
                if roundoff_gap > roundoff_absorbed:
                    roundoff_absorbed, roundoff_at = roundoff_gap, _point_text(args)
            else:
                gap = (_linalg_eval.largest_gap(lv, rv) if as_arrays
                       else abs(lv - rv))
                if gap > relative_absorbed:
                    relative_absorbed, relative_at = gap, _point_text(args)
        if ok is None:
            # structurally unanswerable on this route: an ordering over
            # values that do not order (a complex value), or two
            # matrices of mismatched shape. Not falsified, not a bad
            # sample; skip, as the derive route refuses the same.
            # Equality and closeness over complex values are answered.
            if is_complex_value(lv) or is_complex_value(rv):
                why = (f"; ordering ({cj.relation}) over complex values "
                       f"isn't meaningful ({type(lv).__name__} vs "
                       f"{type(rv).__name__}), only equality and "
                       f"closeness are")
            else:
                why = (f"; {cj.relation} over {type(lv).__name__} vs "
                       f"{type(rv).__name__} values isn't meaningful as a "
                       f"single verdict (mismatched matrix shapes, or "
                       f"values that do not compare)")
            return Probe(cj.name, statement, "skipped", route="probe",
                         note=note + why)
        if ok and cj.tolerance is None:
            gap = ordering_shortfall(lv, rv, cj.relation)
            if gap > absorbed:
                absorbed, absorbed_at = gap, _point_text(args)
        mathematics = None
        if not ok and not exactly_false and family is None:
            # the mathematics at the point: f run on the exact numbers
            # satisfying the claim makes this a miss of the computation;
            # violating it makes the claim false there. The calls these
            # readings make are not the draw's own
            made = list(f_call.calls)
            mathematics = _exact_verdict(cj, code_l, code_r, env, fn_call,
                                         bound_funcs)
            f_call.calls = made
            call_raised[0] = call_nan[0] = call_inf[0] = call_hole[0] = None
        aux_part = ("; " + ", ".join(
            f"{a} = {env[a]:.3g}" if isinstance(env[a], (int, float))
            else f"{a} = {env[a]!r}" for a in aux) if aux else "")
        if not ok:
            if not exactly_false and mathematics is not False \
                    and family is None:
                # what the conditioning says about the miss: inherent in
                # the inputs' magnitudes, or the code's own loss; with
                # neither the mathematics at the point nor κ readable
                # (opaque code) the falsification stands on its own
                gap, reference = largest_miss(compare_l, compare_r, side)
                made = list(f_call.calls)
                # a library row is an axiom: its mathematics holds
                # the reduction reading of κ needs a computation known to
                # reduce its inputs: its mathematics settled (a trusted
                # row, f run exactly), or a reduction word on the claim
                # side it stands against
                found = _conditioning.at_miss(
                    fn, facts, _called_point(f_call, facts, env, kinds), gap,
                    reference, cj_domain,
                    mathematics=True if corner_row else mathematics,
                    reduces=bool(corner_row or _conditioning.claim_reduces(cj)),
                    exact_at=(_exact_point_sides(code_l, code_r, env, fn_call,
                                                 bound_funcs)
                              if mathematics is True else None))
                f_call.calls = made
                if found["kappa"] is None and mathematics is None:
                    found = None
                if corner_row and found and found["inherent"] is True:
                    # a library definition row that loses only what its
                    # conditioning explains at this draw is not a wrong
                    # model: a finding about its computation
                    checked += 1
                    if conditioning_finding is None:
                        conditioning_finding = _conditioning.finding_words(
                            library_key_of(fn), _drawn_text(args), found)
                    call_raised[0] = call_nan[0] = call_inf[0] = None
                    call_hole[0] = None
                    continue
                if mathematics is True and found is not None and stands_in:
                    # the probe stands in for derive, and the claim holds
                    # here in exact arithmetic: the miss is the
                    # computation's, carried by the `[float]` line with its
                    # condition number, or noted when no computation line
                    # was asked for (where the probe is the computation
                    # line itself, the miss falsifies it below)
                    words = (found.get("words")
                             or "the float computation misses the result "
                                "beyond its precision")
                    if ctx.companion_mode == "spawn":
                        if computation_cx is None:
                            shown_l, shown_r = ((_linalg_eval.shown(lv),
                                                 _linalg_eval.shown(rv))
                                                if as_arrays else (lv, rv))
                            computation_cx = (f"{_point_text(args)}{aux_part}: "
                                              f"{_sides(shown_l, shown_r)}")
                            computation_note = words
                            computation_meta = {"mathema.conditioning": found}
                    elif computation_finding is None:
                        computation_finding = (
                            f"{words} at {_point_text(args)}{aux_part}, where "
                            f"the claim holds in exact arithmetic: a finding "
                            f"about the computation")
                    call_raised[0] = call_nan[0] = call_inf[0] = None
                    call_hole[0] = None
                    continue
                miss_conditioning = found
            if as_arrays:
                lv, rv = _linalg_eval.shown(lv), _linalg_eval.shown(rv)
            cx = f"{_point_text(args)}{aux_part}: {_sides(lv, rv)}"
            if exactly_false:
                cx += (", within the float tolerance but false here in "
                       "exact arithmetic")
            elif hidden_by_float:
                cx += (", equal in float but not with the claim's own side "
                       "read exactly")
            break
    rng = main_rng
    if corner_finding is not None:
        finding = (f"{library_key_of(fn)} gives no value at {corner_finding}, "
                   f"a magnitude corner where the exact value is finite: a "
                   f"finding about its computation; the row stands")
        note = f"{note}; {finding}".lstrip("; ")
        missing_meta = {**(missing_meta or {}),
                        "mathema.computation_finding": finding}  # type: ignore[dict-item]
    if conditioning_finding is not None:
        note = f"{note}; {conditioning_finding}".lstrip("; ")
        missing_meta = {**(missing_meta or {}),
                        "mathema.conditioning_finding": conditioning_finding}  # type: ignore[dict-item]
    if cx is not None and miss_conditioning is not None:
        note = f"{note}; {miss_conditioning['words']}".lstrip("; ")
        missing_meta = {**(missing_meta or {}),
                        "mathema.conditioning": miss_conditioning}  # type: ignore[dict-item]
    if computation_finding is not None:
        note = f"{note}; {computation_finding}".lstrip("; ")
        missing_meta = {**(missing_meta or {}),
                        "mathema.computation_finding": computation_finding}  # type: ignore[dict-item]
    if computation_cx is not None:
        from .gates import companion_name, companion_representation
        descriptor, _rep, rep_word = companion_representation(cj_domain, facts)
        ctx.companion = Probe(
            companion_name(cj.name, descriptor), statement, "falsified",
            route="probe", counterexample=computation_cx,
            note=(f"the {rep_word} computation of {cj.name} misses the result "
                  f"beyond its precision where the claim holds in exact "
                  f"arithmetic; {computation_note}" if computation_note else
                  f"the {rep_word} computation of {cj.name} gave no value "
                  f"where the claim holds in exact arithmetic"),
            meta=computation_meta)
    if checked > tallied:
        tally.add(dict(zip(kinds, args)))
    f_call.record(executed_record, dict(zip(kinds, args)))
    missing_meta = with_executed(missing_meta, executed_record) or {}
    if tally.meta():
        missing_meta = {**missing_meta, "mathema.drawn": tally.meta()}
    shrunk_meta: dict = {}
    if cx is not None and cx_stratum is None and assum_eval is None and not aux \
            and any(getattr(cj_domain.get(p), "base_type", None) == "L" for p in kinds):
        # a witness over a language is shrunk inside the language, as
        # the hazard families' witnesses are
        found = _shrink_language_witness(
            cj, kinds, cj_domain, env, args, code_l, code_r)
        if found is not None:
            args, cx, steps = found
            shrunk_meta = {"mathema.witness_shrunk": {"steps": steps}}
            if steps:
                note = (f"{note}; the witness was shrunk inside the language "
                        f"in {steps} step{'s' if steps != 1 else ''}").lstrip("; ")
    if cx is not None:
        return Probe(cj.name, statement, "falsified", n=checked, route=probe_route,
                     counterexample=cx, note=note, stratum=cx_stratum,
                     meta={"mathema.sampling": _sampling_shorthand(
                               sampled_kinds, cj_domain, checked, critical_hints,
                               truncated_hints, observed_lengths,
                               set(premise_draws), runtime_names, nested,
                               lap_floor, {p: c.holes for p, c in containers.items()}),
                          "mathema.confidence": _probe_density(risk, checked),
                          "mathema.counterexample_args": _yaml_safe_args(args),
                          **shrunk_meta, **missing_meta})
    if undecided:
        return Probe(cj.name, statement, "unknown", route="probe", n=checked,
                     note=(f"{note}; the claim's own side could not be "
                           f"evaluated at {undecided} draw"
                           f"{'s' if undecided != 1 else ''}, first at "
                           f"{undecided_at}").lstrip("; "),
                     meta={**missing_meta,
                           "mathema.claim_side_unknown": undecided_at})
    inconclusive_words = (
        f"{inconclusive} draw{'s' if inconclusive != 1 else ''} passed only "
        f"within the tolerance and could not be evaluated in exact "
        f"arithmetic, so {'they are' if inconclusive != 1 else 'it is'} "
        f"not counted")
    if checked == 0 and inconclusive:
        return Probe(cj.name, statement, "unknown", route="probe",
                     note=f"{note}; {inconclusive_words}".lstrip("; "),
                     meta=dict(missing_meta))
    if checked == 0 and executed_record.classified and executed_record.first:
        # every point executed was a missing input the code raised at or
        # answered with a missing value: nothing left to compare
        from ._missing_words import unknown_reason
        said = unknown_reason(executed_record.first, f"{cj.relation} {cj.rhs}",
                              {p for p in kinds if _lists_sentinel(cj_domain.get(p))})
        return Probe(cj.name, statement, "unknown", route="probe",
                     note=f"{note}; {said}".lstrip("; "),
                     meta={**missing_meta, "mathema.missing_unknown": True})
    if checked == 0:
        why = ("; no sampled point satisfied the assuming clause"
               if assum_eval is not None else "; no evaluable inputs")
        return Probe(cj.name, statement, "skipped", route="probe",
                     note=note + why)
    if absorbed > 0:
        note = (f"{note}; fails by {absorbed:.3g} at {absorbed_at}, within "
                f"the default tolerance ({DEFAULT_TOLERANCE:g})").lstrip("; ")
    if roundoff_absorbed > 0:
        note = (f"{note}; differs by {roundoff_absorbed:.3g} at "
                f"{roundoff_at}, within the round-off of that draw's "
                f"magnitudes").lstrip("; ")
    if relative_absorbed > 0:
        note = (f"{note}; differs by {relative_absorbed:.3g} at "
                f"{relative_at}, within the tolerance ({DEFAULT_TOLERANCE:g} "
                f"plus {_declared_rel_tol(cj):g} times the larger side), and "
                f"holds there in exact arithmetic").lstrip("; ")
    if inconclusive:
        note = f"{note}; {inconclusive_words}".lstrip("; ")
    return Probe(cj.name, statement, "holds", n=checked, route=probe_route, note=note,
                 meta={"mathema.sampling": _sampling_shorthand(
                           sampled_kinds, cj_domain, checked, critical_hints,
                           truncated_hints, observed_lengths,
                           set(premise_draws), runtime_names, nested,
                           lap_floor, {p: c.holes for p, c in containers.items()}),
                      "mathema.confidence": _probe_density(risk, checked),
                      **missing_meta})



# namespace-friendly alias: mathema.claims.check(fn, [...])
check = check_conjectures

EVIDENCE_LADDER = (
    # a proof: from the lifted body, from the function's structure
    # (`examine`), over every point of a finite region (brute force),
    # and a mathematics-only proof with no float companion
    ("derive", "examine", "derive:brute_force", "derive:math_only"),
    ("derive:extensive",),
    # A reserved, not-yet-built "numerical" evidence tier belongs here,
    # between derive:extensive and the informed-probing rung below,
    # a real numerical-methods engine (finite-difference/bisection with
    # error bounds, not just a probe:algorithmic sample) would be
    # stronger than sampling but still short of a symbolic proof. Named
    # here so the slot isn't accidentally claimed by something smaller
    # first.
    ("probe:semi_analytical", "probe:algorithmic", "probe:minimal_example",
     "probe:counterfactual"),
    # a compendium definition row (`axiom`) is trusted testimony, as
    # strong as a plain holds and never stronger
    ("probe", "probe:lifted_numeric", "axiom"),
    ("documented",),
    ("declared",),
)
# Route/intent-provenance strength, strongest first. `derive`/
# `derive:extensive`/`probe:semi_analytical`/`probe:algorithmic`/
# `probe` are Probe.route values (record-schema.md, claim-anatomy.md's
# "evidence route"); `documented`/`declared` are record-schema.md's
# intent-provenance classes ("Where intent comes from"), included on
# the same scale since both answer "how much should a reader trust
# this." Each element is a tuple of one or more routes tied at that
# rank. `probe:semi_analytical` (critical-point-informed sampling),
# `probe:algorithmic` (a family-provided technique, e.g. pairwise
# monotonicity), `probe:minimal_example` (fuzzing with shrinking) and
# `probe:counterfactual` (a policy row decided by refilling) are all
# "informed rather than blind" probing, from different information
# sources, none stronger than another. `probe:lifted_numeric` is
# sampling of a numerically lifted body, level with `probe`. A
# definition row's `axiom` route ranks with trusted testimony, level
# with `probe`: a definition is trusted, not adjudicated.
#
# This ranks *how a positive verdict was reached*, not how much to
# trust a `falsified` verdict: a claim proven true by derive is
# stronger evidence than one merely holding under probing, but a
# falsification is not weaker just because it came from probe rather
# than derive, a corroborated counterexample (probing.py's own seeded
# sampler, or symbolic._proof_support._corroborate_disproof for the
# derive route) is equally definitive either way. `evidence_rank` below
# is for comparing routes, not for judging a falsified/skipped verdict.


def evidence_rank(route_or_class: str) -> int:
    """Intent:
        Position of a route (or intent-provenance class) in
        EVIDENCE_LADDER. Lower is stronger; two routes in the same
        rung tie.

    Notes:
        A `:fallback`/`:extensive`/`:semi_analytical`/`:algorithmic`
        suffix beyond the base route it modifies does not necessarily
        create a new rung: `probe` and `probe:fallback` rank the same
        (a route="best" claim that fell back to probing is exactly as
        strong as an ordinary route="probe" claim, it just tried
        derive first and reports why it fell back), but a suffix can
        also name a genuinely stronger rung of its own, as
        `probe:algorithmic`/`probe:semi_analytical` do here. An unlisted
        `derive:<mechanism>` (a language strategy's) ranks as the
        default path ranks a wider mechanism, with `derive:extensive`;
        `derive:language` (no mechanism named) ranks with `derive`. A value
        this ladder doesn't recognize at all (a custom route from a
        different verification technique, per record-schema.md's "Open
        for extension") ranks last, weaker than every known value,
        never stronger. A definition row's `axiom` ranks with trusted
        testimony, level with `probe`.
    """
    base, _, sub = route_or_class.partition(":")
    candidates = [route_or_class]
    if base == "derive" and sub and sub not in ("language", "domain_split"):
        # a language strategy's `derive:<mechanism>`: ranked as the
        # default path ranks a wider mechanism, derive:extensive
        candidates.append("derive:extensive")
    candidates.append(base)
    for candidate in candidates:
        for rank, rung in enumerate(EVIDENCE_LADDER):
            if candidate in rung:
                return rank
    return len(EVIDENCE_LADDER)
