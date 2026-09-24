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

Expressions are validated against a strict AST whitelist before evaluation:
this pipeline accepts untrusted proposals, so nothing outside arithmetic,
comparisons handled by the relation, and a fixed set of safe calls can run.
"""
from __future__ import annotations

import ast
import cmath as _cmath
import inspect
import math
import operator as _operator
import os
import re
import sys
from dataclasses import dataclass, field
from dataclasses import replace as _dc_replace

from . import families, routes
from ._math_vocab import _D_AT_SENTINEL, MATH_CONSTANTS
from .analysis import analyze_source
from .grammar import (Domain, InvalidDomain, NoRelation,
                      is_missing, extract_assuming_clause,
                      extract_diff_fraction_sugar, extract_let_bindings,
                      extract_outcome_clause, _split_top_level,
                      is_reserved, normalize,
                      parse_domain_safety, parse_raises, split_quantifier,
                      split_relation_chain, unexpanded_prime_message,
                      UnreadableSpelling)
from . import linalg
from ._scan import _split_commas, blank_strings
from .domain import DuplicateBinding
from .probing import (ComplexResult, _close, _fmt, _prepare_sampling,
                      _probe_density, _sampling_shorthand, _synth,
                      _synth_dict, complex_is_a_raise, is_complex_value,
                      ordering_shortfall, relation_holds_elementwise)
from .records import _EXC_TYPES, Probe, classify_verdict, statement_text
from .symbolic import (mentions_matrix_ops, try_prove, try_prove_matrix,
                       try_prove_raises)


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


def _literal_call_args(text: str, sig_params: list) -> dict:
    """`{param: value}` for every `f(...)` call argument that is a plain
    literal at a real parameter's position: the call passes that value
    verbatim, so the parameter is FIXED to it, not synthesized. Unlike
    `_inferred_literal_domain` (numeric only, for branch pruning), this
    keeps every literal kind (a string `"nope"`, a `True`, a number) and
    its actual value, so both the sample and the counterexample witness
    show what the call really passed rather than a synthesized
    placeholder in a literal's slot."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return {}
    fixed: dict = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "f"):
            continue
        for p, arg in zip(sig_params, node.args):
            if isinstance(arg, ast.Constant):
                fixed[p] = arg.value
    return fixed


def _yaml_safe_args(args) -> list:
    """Intent:
        A falsifying argument tuple as YAML-safe values a later run can
        replay exactly: numbers pass through, a complex value becomes
        its coordinate spelling, sequences recurse.
    """
    out = []
    for v in args:
        if isinstance(v, complex) and not isinstance(v, (int, float)):
            out.append(f"{v.real:g}{v.imag:+g}j")
        elif isinstance(v, (list, tuple)):
            out.append(_yaml_safe_args(v))
        else:
            out.append(v)
    return out


_MAX_CORNERS = 64


def _domain_corners(kinds: dict, domain: dict, literal_args: dict) -> list:
    """Intent:
        The corners of a claim's bounded domain box as argument lists,
        in `kinds` order: every combination of each parameter's included
        endpoints, with a literal argument held at its literal. Empty
        unless every parameter is a real or integer scalar with a finite
        interval domain (or fixed by a literal), and when the box has
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
        if k not in ("scalar", "float", "int"):
            return []
        bound = domain.get(p)
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


def _sample_in_domain(value, bound) -> bool:
    """Intent:
        Whether one sampled scalar lies inside its parameter's declared
        bound, for the probe route's per-trial check. Only a real number
        is judged here: a sequence, mapping, string or complex value
        has its own sampler, and a missing value is the missing-value
        policy's to decide. A whole float counts as the integer it
        equals, and an infinity is inside exactly when the bound is
        unbounded in its direction.
    """
    from .domain import domain_contains
    if bound is None or isinstance(value, bool) \
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


def _pinned_arg_sets(cj, arity: int) -> list:
    """Intent:
        The claim's recorded counterexamples (`Conjecture.pins`) as
        replayable argument tuples, restored from their YAML-safe
        spellings; entries with the wrong arity are skipped rather
        than misapplied.
    """
    out = []
    for pin in cj.pins or []:
        stored = pin.get("args") if isinstance(pin, dict) else None
        if not isinstance(stored, list) or len(stored) != arity:
            continue
        restored = []
        for v in stored:
            if isinstance(v, str) and ("j" in v or "J" in v):
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
    base = cj.name.split("[", 1)[0]
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

_FINITE_NO_ERROR = "mathema.f.finite_no_error"

_COMPARISON_RELATIONS = frozenset({"==", "~=", "!=", "<=", ">=", "<", ">"})

#: the families stated as `f(<params>) == f(<params>)`, the call agreeing
#: with itself, each examining one way it could fail to
_SELF_AGREEMENT_FAMILIES = frozenset({"is_deterministic", "is_reproducible",
                                      "is_state_safe"})


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
        `g(f, <params>) == 1` with `g` bound to `mathema.f.finite_no_
        error`. `is_deterministic`, `is_reproducible` and
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
    if base == "is_defined":
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
        from .f import finite_no_error
        return (cj.relation == "==" and _squash(cj.rhs) == "1"
                and _squash(cj.lhs) == _squash(
                    f"g(f, {', '.join(facts.params)})")
                and (bound == _FINITE_NO_ERROR or bound is finite_no_error))
    return not isinstance(family, (_NamedClaimFamily, MatrixPropertyFamily,
                                   OutputPredicateFamily))


def _resolve_func_ref(ref: str, *, root: str = "."):
    """A dotted `module.qualname` string (a mathema-internal helper, or
    any other importable function, the same shape a spec key already
    uses) resolved to the live callable it names, including a method
    key like `pkg.mod.Class.method` (the longest importable prefix is
    the module, the rest is walked as attributes). A language-tagged
    key (`ts:src/ema.ts#ema`) resolves through its registered target
    resolver instead, so a store sweep reaches foreign implementations
    the same way it reaches Python ones. `None` if nothing importable
    or the name isn't found there."""
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
    walked = _prefix_walk(ref, root)
    if walked is None:
        return None
    obj = walked[2]
    return obj if callable(obj) else None

# what parameter kind (analysis.py's _param_kinds vocabulary) a stated
# domain base type corresponds to, for reconciling a let-declared type
# against the real parameter's own annotation.
_BASE_TYPE_KIND = {"Z": "int", "N": "int", "R": "scalar", "C": "complex"}

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


def _runtime_dim(value, axis):
    """`dim(value, axis)` at evaluation time: the size of the axis-th
    dimension of a nested-sequence value, descending first elements.
    Raises IndexError past the value's depth, the same honest failure
    an over-indexed axis deserves."""
    v = value
    for _ in range(int(axis)):
        v = v[0]
    return len(v)


_SAFE_FUNCS = {
    "abs": abs, "min": min, "max": max, "len": len, "sum": sum,
    "dim": _runtime_dim,
    # output-shape builtins for the output-contract invariants
    # (preserves_type, is_permutation_of_input): probe-only, harmless,
    # not sympy functions (the derive route reports them unsupported and
    # the probe evaluates them).
    "sorted": sorted, "type": type,
    # sympy's own capitalization, mirroring _math_vocab._SYMPY_FUNCS's
    # Abs/Min/Max synonyms so a claim written that way adjudicates on
    # either route
    "Abs": abs, "Min": min, "Max": max,
    "sqrt": math.sqrt, "exp": math.exp, "log": math.log,
    "log10": math.log10, "log2": math.log2,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
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
    "factorial": lambda v: math.gamma(v + 1),
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "gamma": math.gamma, "lgamma": math.lgamma,
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
    relation: str = "=="        # "==" | "<=" | ">="
    source: str = "user"
    route: str = "best"         # "best" (default cascade) | "probe" | "derive" | "examine" (see claim-driven-
                                 # development/0.1.0/claim-anatomy.md). "best" is
                                 # input-only: the cascade derive -> derive:extensive
                                 # -> probe, with the output record naming whichever
                                 # mechanism actually settled it ("auto" is retired,
                                 # an unknown route now, skipped loudly).
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
    # the domain approximation for infinity, parallel to tolerance: an
    # unbounded (+-inf) domain is checked for implementation numerical
    # stability only up to this magnitude, applied symmetrically
    # (records.pseudo_infinity_range resolves it to the (-v, v)
    # range consumers read). None means full float extremes are
    # assumed (the pedantic default). Rendered in the claim text
    # only when set (an ordinary bounded-domain claim never states it).
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
    # the `funcs` names check_conjectures resolved from f's module or the
    # calling scope rather than from an explicit `funcs=`/`let` binding.
    # Their text stays the bare call name, which resolves the same way
    # when the claim is rebuilt, so rendering adds no `let` for them.


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
         matrix_names: frozenset = frozenset()) -> Conjecture:
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
    predicate (declared-schema.md, "Domain is a claim field") and the
    family-derive-only `is_pole_safe(param)`/`is_builtin_safe(param)`
    predicates (no `f(...)` wrapper; these are facts about param's own
    declared domain, not fn's return value). `route` defaults to "probe"
    (seeded sampling, verdict `holds`/`falsified`); "derive" asks for a
    symbolic proof instead (verdict `proven`/`falsified`, or `skipped`
    when the function or claim can't be lifted to a closed form; see
    symbolic.py); "best" cascades, the fast proof attempt, then the
    extensive strategy ladder, then probing, and the output record
    names whichever route actually settled it ("auto" is retired, not a
    legacy spelling of "best"). the safety predicates always adjudicate on the examine route
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
    default to pick silently."""
    # "auto" is fully retired (the word stays free for automatic
    # differentiation): it is NOT a legacy alias, an "auto" route
    # reaches adjudication as an unknown route and skips loudly.
    # A safety predicate is an implementation fact: whatever route the
    # author passed, it is examined through the full structural +
    # empirical cascade, and the record reports which mechanism
    # decided (the examine route). That normalization happens after
    # parsing, once the relation is known, see below.
    if "#" in blank_strings(law):
        raise InvalidConjecture(
            f"`#` has no meaning in a claim and would silently cut off "
            f"everything after it; remove it (a comment belongs outside "
            f"the claim text): {law.strip()!r}")
    try:
        text, ambiguous_diff_vars = extract_diff_fraction_sugar(law.strip())
    except UnreadableSpelling as e:
        raise InvalidConjecture(str(e)) from e
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
        new_assuming, text = extract_assuming_clause(text)
        if new_assuming is not None:
            if not new_assuming.strip()[len("assuming"):].strip():
                raise InvalidConjecture(
                    f"`assuming` has no premise before its comma: state "
                    f"one (`assuming x > 0, ...`) or drop the keyword: "
                    f"{law.strip()!r}")
            assuming = new_assuming
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
        text = normalize(text)
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
    dom = {**let_domain, **dom}
    prime_problem = unexpanded_prime_message(text)
    if prime_problem is not None:
        raise InvalidConjecture(prime_problem)
    r = parse_raises(text)
    ds = None if r is not None else parse_domain_safety(text)
    negated = False
    links: list = []
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
        try:
            links = split_relation_chain(text)
        except NoRelation as e:
            raise InvalidConjecture(str(e)) from e
        lhs, rel, rhs = links[0]
        if len(links) == 1:
            links = []
    # a residual `|` is a bar the grammar could not pair with another,
    # and left in place it reaches rendering as unparseable text
    for _side in (lhs, rhs):
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
            for _side in (_lhs, _rhs):
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
    if let_pseudo_inf is not None:
        from .records import pseudo_infinity_range
        if (pseudo_infinity is not None
                and pseudo_infinity_range(pseudo_infinity)
                != pseudo_infinity_range(let_pseudo_inf)):
            raise InvalidConjecture(
                "pseudo_infinity stated twice: the let binding and the "
                "keyword argument disagree")
        pseudo_infinity = let_pseudo_inf
    if rel in routes.examine_predicates():
        # the examine normalization promised above: implementation
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
        import re
        name = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "claim"
    bound_funcs = {**let_funcs, **(funcs or {})}
    for unbound in _unbound_call_names(lhs, rhs, set(bound_funcs)):
        # a bare call name (`budget_line(...)`) is a function reference
        # awaiting scope resolution at check time; recording it now;
        # the name as its own placeholder value; lets the renderer
        # treat it as the function it is rather than refusing
        bound_funcs[unbound] = unbound
    return Conjecture(name=name, lhs=lhs, rhs=rhs, relation=rel,
                      source=source, route=route, grammar=grammar,
                      funcs=bound_funcs, domain=dom,
                      free_vars=frozenset(let_domain),
                      ambiguous_diff_vars=ambiguous_diff_vars, tolerance=tolerance,
                      negated=negated, assuming=assuming, outcome=outcome or "",
                      links=links, pseudo_infinity=pseudo_infinity,
                      meta=dict(meta or {}), raw=law)


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
            return ("keyword arguments are not claim syntax: pass each "
                    "argument by position")
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
                    rel = "==" if op == "~=" else op
                    return SimpleNamespace(lhs=lhs, relation=rel, rhs=rhs)
        i += 1
    return None


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

    # a matrix STRUCTURE premise (`assuming A is symmetric`,
    # `assuming is_positive_definite(A)`): every conjunct names a
    # matrix predicate over a bare parameter. It narrows synthesis to
    # matrices with the structure (entailment-closed) and, on the
    # derive route, becomes a sympy assumption. Recognised only when
    # EVERY conjunct is a structure predicate; a clause mixing a
    # structure premise with a relation falls through to the relation
    # path (which reports the structure conjunct it cannot read).
    from . import matrices as _mtx
    from .grammar import parse_domain_safety
    struct_map: dict = {}
    all_structure = True
    for part in _split_top_and(text):
        parsed = parse_domain_safety(part.strip())
        if (parsed is not None and not parsed[0].startswith("not ")
                and parsed[0] in _mtx.PROPERTIES
                and parsed[1].isidentifier()):
            struct_map.setdefault(parsed[1], set()).add(parsed[0])
        else:
            all_structure = False
            break
    if all_structure and struct_map:
        closed = {param: tuple(sorted(_mtx.entailed(props)))
                  for param, props in struct_map.items()}
        return ("structure", text, closed)

    def skip(reason: str):
        return Probe(cj.name, statement_text(cj.relation, cj.lhs, cj.rhs),
                     "skipped", route=None, note=reason)

    def conjuncts_of(region_text: str, display: str):
        parsed_list = []
        for part in _split_top_and(region_text):
            parsed = _parse_assuming_relation(part)
            if parsed is None:
                return skip(f"assuming clause must be a plain relation "
                            f"(==, !=, >=, <=, >, <): {part!r}")
            parsed_list.append(parsed)
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
                        f"-- state the lemmas in one `assuming` clause and "
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
    if re.search(r"\bis\s+(falsified|unknown)\b", text):
        return None   # other lemma-verdict spellings stay uninterpreted
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
    return conjuncts_of(text, text)


#: how to write each math constant when a parameter of the same name
#: takes the bare token
_CONSTANT_SPELLINGS = {
    "e": "write exp(1) for Euler's number",
    "pi": "write acos(-1) for pi",
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


def _unbound_call_names(lhs: str, rhs: str, existing: set) -> list[str]:
    """Intent:
        Call-position names in a claim's law text that aren't `f`, a
        recognized math/reserved call form, or already bound, the
        candidates for scope resolution, and the names the renderer
        must treat as functions in the meantime.
    """
    from .grammar import reserved_names
    known = ({"f"} | existing | set(_SAFE_FUNCS) | reserved_names()
             | {"sum", "prod", "raises"})
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
    """Every raise-region guard of fn itself: registered partiality
    lemmas plus explicit raise branches from the piecewise lift. Float
    overflow is left out: where a computation leaves the doubles is an
    operational boundary, stated by an operational infinity, not part
    of the region the function is defined on."""
    from .symbolic._conditioned import lift_piecewise
    from .symbolic._partiality import partiality_guards
    guards: list = []
    try:
        guards += partiality_guards(fn, facts)
    except Exception:
        pass
    if facts.branch_count and not facts.loops and not facts.recursion:
        try:
            pw = lift_piecewise(fn, facts)
            if pw is not None:
                guards += pw.raise_guards
        except Exception:
            pass
    return [(cond, exc) for cond, exc in guards if exc != "OverflowError"]


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


def _definedness_region_structured(fn, facts) -> list:
    """Intent:
        The region where fn itself returns, as sympy relationals over
        fn's OWN parameter symbols; one per raise guard, negated,
        with And-shaped path guards reduced against the other
        conjuncts. The single structural source: the rendered region
        (`_definedness_region`) and the is_defined family's
        equivalence check both read from here, so they can never
        disagree about what the region is.
    """
    import sympy

    from .symbolic._base import NEGATED_REL as negate
    negated_rels: list = []

    def emit(rel) -> None:
        if rel not in negated_rels:
            negated_rels.append(rel)

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    guards = _collect_definedness_guards(fn, facts)
    deferred: list = []
    for cond, _exc in guards:
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
        for piece in ([cond] if not isinstance(cond, sympy.Or)
                      else list(cond.args)):
            flip = negate.get(type(piece))
            if flip is not None and piece is not sympy.false:
                emit(flip(piece.lhs, piece.rhs))
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
        if len(rest) == 1:
            flip = negate.get(type(rest[0]))
            if flip is not None:
                emit(flip(rest[0].lhs, rest[0].rhs))
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
    wanted = [n for n, v in cj.funcs.items() if v == n]
    wanted += [n for n in _unbound_call_names(cj.lhs, cj.rhs, really_bound)
               if n not in wanted]
    if not wanted:
        return ""
    module_scope = getattr(fn, "__globals__", None) or {}
    caller_scope: dict | None = None
    bound = []
    for name in wanted:
        target, where = None, None
        v = module_scope.get(name)
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
            bound.append(f"{name} = {getattr(target, '__module__', '?')}"
                         f".{getattr(target, '__qualname__', name)} ({where})")
    return "; bound " + ", ".join(bound) if bound else ""


def _validate(src: str, param_names: set[str],
              funcs: frozenset = frozenset()) -> tuple:
    """AST-whitelist an expression; returns (code, auxiliary names).
    `funcs` are extra callable letters a claim has bound (g, h, ...)."""
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise InvalidConjecture(f"unparseable law {src!r}") from e
    callable_names = {"f"} | funcs | set(_SAFE_FUNCS)
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
            # a bundled parameter's field read (`self.rate`, `cfg.a`):
            # one level deep, rooted at a plain name, never a dunder
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
    return compile(tree, "<conjecture>", "eval"), aux



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
    import inspect as _inspect

    from .symbolic._base import (_attr_keys_used, _dataclass_field_names,
                                 _enclosing_class)
    out: dict = {}
    if facts.tree is None:
        return out
    try:
        sig = _inspect.signature(fn)
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
                hi[rk] = min(hi.get(rk, 64), lc - (1 if acj.relation == "<" else 0))
    if not saw:
        return None, None, None

    merged: list = []
    for g in groups:
        hit = [m for m in merged if m & g]
        for m in hit:
            merged.remove(m)
        merged.append(set().union(g, *hit))
    return lo, hi, merged


def _draw_trial_sizes(resolver, lo, hi, groups, rng):
    """Sizes for one trial: the resolver draws one per distinct key
    (shared dims agree structurally), then premise equality groups
    collapse each to a single shared draw and premise bounds apply."""
    sizes = resolver.draw_sizes(rng, lo, hi)
    for group in (groups or []):
        g_lo = max((lo.get(k, 1) for k in group), default=1)
        g_hi = min((hi.get(k, 6) for k in group), default=6)
        n = rng.randint(max(1, g_lo), max(g_lo, g_hi))
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
    values = {f: _synth("float", rng, cj_domain.get(f"{p}.{f}"),
                        specials=specials) for f in fields}
    if isinstance(cls, type) and _dc.is_dataclass(cls):
        return cls(**values)
    inst = object.__new__(cls)
    for f, v in values.items():
        setattr(inst, f, v)
    return inst


def _emit_position(probe, conjectures: list, declared_order: dict) -> int:
    """Where a probe belongs in the returned list: its conjecture's own
    declared position, so dependency-driven adjudication order never
    leaks into what the caller sees."""
    for cj in conjectures:
        if cj.name == probe.name:
            return declared_order.get(id(cj), 0)
    return 0


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
        parsed = _parse_assuming_relation(
            f"{lemma.lhs} {lemma.relation} {lemma.rhs}")
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
    lhs = linalg.apply_matrix_sugar(cj.lhs, mats)
    rhs = linalg.apply_matrix_sugar(cj.rhs, mats) if cj.rhs else cj.rhs
    if lhs == cj.lhs and rhs == cj.rhs:
        return cj
    grammar = cj.grammar
    if grammar == GRAMMAR and linalg.mentions_matrix_ops(lhs, rhs):
        grammar = f"{GRAMMAR}/linalg"
    return dataclasses.replace(cj, lhs=lhs, rhs=rhs, grammar=grammar)


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


def check_conjectures(fn, conjectures: list[Conjecture],
                      domain: dict | None = None, trials: int | None = None,
                      trials_scale: float = 1.0, facts=None,
                      extensive: bool = False,
                      known_premises: dict | None = None) -> list[Probe]:
    """Adjudicate proposed claims against the live function.

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

    Returns one Probe per conjecture: holds (n=…) / falsified (with the
    counterexample) / skipped (invalid law, nothing evaluable, or a
    different grammar entirely, see the `grammar` check below, tagged
    in `meta["mathema.foreign_grammar"]` so a caller can tell the two
    kinds of skip apart), each noting who proposed it.
    """
    facts = _effective_facts(fn, facts)
    kinds = {p: facts.param_kinds.get(p, "unknown") for p in facts.params}
    domain = domain or {}
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

    def _stamped(probe, cj, canonical=True):
        # one statement, every surface: the row, the display, and the
        # store all carry the canonical ascii text, which re-parses to
        # this claim (sections, quantifier, premise and all). The
        # structured fields beside it are the same claim for machines.
        from .grammar import domain_bound_to_json
        from .spec import canonical_claim_text
        if canonical:
            # the renderer is total over everything claim() accepts, so
            # a failure here is a renderer bug worth a loud crash, never
            # a claim to quietly record under a different spelling
            probe.statement = canonical_claim_text(cj)
        if cj.domain:
            probe.domain = {p2: domain_bound_to_json(b)
                            for p2, b in cj.domain.items()}
        probe.grammar = cj.grammar
        probe.tolerance = cj.tolerance
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
        if cj.meta:
            # declared meta (the spec's own extension object, e.g.
            # concepts) passes through under the probe's meta, the
            # probe's own keys winning
            probe.meta = {**cj.meta, **(probe.meta or {})}
        if cj.source:
            # always stamped, "user" included: with no provenance
            # prose in the note, meta is the one source channel
            meta = dict(probe.meta or {})
            meta.setdefault("mathema.surface", cj.source)
            probe.meta = meta
        _stamp_examine_route(probe, cj, fn, facts)
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
    for cj in ordered:
        if cj.links:
            # a chained comparison is the conjunction of its links: run
            # each link through the full ordinary adjudication (same
            # domain/funcs/assuming/route) and fold, so no proof path is
            # duplicated; the exact combination rule tuple claims use
            out.append(_stamped(_adjudicate_chain(
                cj, fn, facts, domain, trials, trials_scale, extensive), cj))
            continue
        if (cj.relation in routes.safety_predicates() and cj.lhs == "f"
                and "f" not in facts.params):
            # the function-wide spelling: the predicate over f is the
            # conjunction of the predicate over every numeric parameter
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
        validated = _validate_claim(cj, statement, note, facts, domain, fn=fn)
        if isinstance(validated, Probe):
            # a rejected claim has no canonical form (it was never a
            # claim), so its record keeps what was written, verbatim
            out.append(_stamped(validated, cj, canonical=False))
            continue
        ctx = validated
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
        ctx.premise_structures = premise_structures
        def stamp(probe, _cap=None):
            # `condition` is rendered text that gets read back,
            # docsync compares a verified row by feeding
            # f"{condition}, {statement}" through the claim grammar,
            # so it may only ever hold what the grammar accepts. An
            # assumed region reaches it the way a declared one does:
            # the premise narrows the quantified interval itself
            # (symbolic._prove._tighten_domain_by_assumption), and the
            # premise text rides in the statement.
            probe = _stamped(probe, cj)
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
                note=f"unknown route {cj.route!r}"), cj))
            continue
        # the family is resolved for every concrete route: the derive
        # stage reads its derive half, and the probe stage reads its
        # probe:algorithmic half, a plain route="probe" claim on a
        # family-owned name reaches the family's own empirical
        # technique rather than the generic sampling loop
        ctx.family = _claim_family(cj, fn, facts)
        emptied = _empty_premise_parameter(ctx, facts)
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
        if cj.route in ("derive", "best", "examine"):
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
                out.append(stamp(derived, _cap=verdict_cap))
                continue
            # route == "best" and the derive stage couldn't settle it:
            # fall through to the probe stage, same as an ordinary
            # probe claim.
        probed = _arbitrate_empirical_fallback(
            _adjudicate_probe(ctx, fn, facts, kinds, _sampling), ctx)
        out.append(stamp(probed, _cap=verdict_cap))
    out.sort(key=lambda p: _emit_position(p, conjectures, declared_order))
    return out


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
                if k.startswith("mathema.corroboration")}

    for probe, label in zip(probes, labels):
        if probe.verdict == "falsified":
            cx = probe.counterexample
            return Probe(name, statement, "falsified", n=probe.n,
                         route=probe.route,
                         counterexample=(f"{label}: {cx}" if cx else None),
                         sketch=(f"{label}: {probe.sketch}" if probe.sketch
                                 else None),
                         note=f"{what} falsified at {label}",
                         meta=corroboration(probe))
    verdicts = [p.verdict for p in probes]
    if all(v == "proven" for v in verdicts):
        return Probe(name, statement, "proven",
                     route=_conjunction_route(
                         [p.route for p in probes], "derive"),
                     note=f"every {unit} of the {what} proven")
    if all(v in ("proven", "holds") for v in verdicts):
        n = min((p.n for p in probes if p.n), default=0)
        return Probe(name, statement, "holds", n=n,
                     route=_conjunction_route(
                         [p.route for p in probes if p.verdict == "holds"],
                         "probe"),
                     note=f"every {unit} of the {what} holds")
    weakest = next(p for p, v in zip(probes, verdicts)
                   if v not in ("proven", "holds"))
    label = labels[probes.index(weakest)]
    return Probe(name, statement, weakest.verdict, route=weakest.route,
                 sketch=weakest.sketch,
                 note=f"{what} {weakest.verdict} at {label}: "
                      f"{weakest.note}",
                 meta=corroboration(weakest))


def _adjudicate_chain(cj, fn, facts, domain, trials, trials_scale,
                      extensive) -> "Probe":
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
        per-link batch), rare enough to leave to a future pass.
    """
    from dataclasses import replace as _replace

    link_cjs = []
    labels = []
    for i, (lhs, rel, rhs) in enumerate(cj.links, start=1):
        labels.append(f"link {i}: {statement_text(rel, lhs, rhs)}")
        link_cjs.append(_replace(cj, lhs=lhs, relation=rel, rhs=rhs,
                                 links=[], name=f"{cj.name}[link{i}]"))
    probes = check_conjectures(fn, link_cjs, domain=domain, trials=trials,
                               trials_scale=trials_scale, facts=facts,
                               extensive=extensive)
    return _combine_conjunction(probes, cj.name, _chain_statement(cj),
                                labels)


def _stamp_examine_route(probe, cj, fn, facts) -> None:
    """Intent:
        Restate a safety examination's route: an implementation fact
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
    is_safety = cj.relation in routes.examine_predicates()
    if not is_safety:
        from .claim_families import SafetyFamily
        base = cj.name.split("[", 1)[0]
        base_family = families.families().get(base)
        is_safety = (isinstance(base_family, SafetyFamily)
                     and _statement_is_family_claim(cj, base, base_family,
                                                    facts))
    if not is_safety:
        return
    root, _, _sub = probe.route.partition(":")
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
               if facts.param_kinds.get(p) != "sequence"]
    statement = statement_text(cj.relation, "f", cj.rhs)
    if not numeric:
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"{cj.relation}(f) covers the numeric "
                          f"parameters, and this function has none")
    sub_cjs = [_replace(cj, lhs=p, name=f"{cj.relation}[{p}]")
               for p in numeric]
    probes = check_conjectures(fn, sub_cjs, domain=domain, trials=trials,
                               trials_scale=trials_scale, facts=facts,
                               extensive=extensive)
    return _combine_conjunction(probes, cj.name, statement, numeric,
                                what=f"function-wide {cj.relation}",
                                unit="parameter")


def _derive_attempt_label(fallback: "Probe") -> str:
    """A short 'derive: <status> (<why>)' label for the attempt log,
    read off a stashed derive-undecided Probe; its
    mathema.derive_status meta (unliftable/undecided) and its own
    sketch/last-note reason."""
    status = (fallback.meta or {}).get("mathema.derive_status", "undecided")
    reason = fallback.sketch or (fallback.note or "").rsplit("; ", 1)[-1]
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
        so a coverage measurement keeps the derive-route signal.
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
    # exhaustive-coverage sketch), so it supersedes like any evidence
    winner = (probed if probed.verdict in ("proven", "holds", "falsified")
              else fallback)
    winner.note = f"{winner.note}; {trail}"
    carried = {k: v for k, v in (fallback.meta or {}).items()
               if k.startswith("mathema.derive") or k == "mathema.timeout"
               or k.startswith("mathema.corroboration")}
    if carried:
        winner.meta = {**(winner.meta or {}), **carried}
    if (fallback.meta or {}).get("mathema.corroboration") == "uncorroborated":
        # the engine-bug signal must survive whichever route wins: a
        # symbolic disproof nothing reproduced was claimed here, and a
        # later reader (or the maintainer) needs to see that. A claim
        # form with no point evaluation had no reproduction attempted,
        # so that note names the missing witness instead.
        if (fallback.meta or {}).get("mathema.corroboration_unexecutable"):
            winner.note = (f"{winner.note}; derive reported an UNCORROBORATED "
                           f"disproof (the claim form has no point "
                           f"evaluation, so derive had no executed witness)")
        else:
            winner.note = (f"{winner.note}; derive reported an UNCORROBORATED "
                           f"disproof (probable engine bug, worth reporting)")
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


_REAL_KINDS = {"scalar", "float", "int"}


def _derive_operational_domain(cj, cj_domain: dict, facts) -> dict:
    """Intent:
        The domain the derive route reads when the claim declares an
        operational infinity (`pseudo_infinity`, `let |inf| be ...`):
        every real scalar parameter's unbounded direction stops at the
        declared stand-in for infinity, so "for all x" means for all x
        the author treats as finite. With no operational infinity the
        declared domain is returned unchanged, and infinity is infinity.
    """
    from .domain import Interval
    from .records import pseudo_infinity_range
    pinf = pseudo_infinity_range(getattr(cj, "pseudo_infinity", None))
    if pinf is None:
        return cj_domain
    plo, phi = pinf
    out = dict(cj_domain)
    for p in facts.params or ():
        if facts.param_kinds.get(p, "scalar") not in _REAL_KINDS:
            continue
        b = out.get(p)
        if b is None or b == "R":
            out[p] = Interval(plo, phi)
        elif isinstance(b, tuple) and not isinstance(b, frozenset) and len(b) == 2:
            try:
                lo, hi = float(b[0]), float(b[1])
            except (TypeError, ValueError):
                continue
            if lo == float("-inf") or hi == float("inf"):
                out[p] = Interval(max(lo, plo), min(hi, phi),
                                  getattr(b, "closed_lo", True) or lo < plo,
                                  getattr(b, "closed_hi", True) or hi > phi)
    return out


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
                                  "=:=",
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
                          f"{GRAMMAR!r}, not adjudicated by this route",
                     meta={"mathema.foreign_grammar": cj.grammar})
    param_set = set(facts.params)
    bare_reserved = (_find_bare_reserved_name(cj.lhs, param_set)
                    if cj.relation != "raises" else None) \
        or (_find_bare_reserved_name(cj.rhs, param_set)
            if cj.rhs and cj.relation != "raises"
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
            claim_names |= {n.id for n in ast.walk(ast.parse(src, mode="eval"))
                            if isinstance(n, ast.Name)}
        except SyntaxError:
            pass
    from ._math_vocab import _MATH_ATTRS
    from .grammar import reserved_names
    vocab_names = set(_MATH_ATTRS) | set(reserved_names()) | {"f"}
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
    if cj.relation == "raises" and fn is not None:
        # the TypeError a call that does not fit the signature raises
        # comes from the claim's own malformed text, never from the
        # function, so it can neither satisfy nor refute the claim
        mismatch = _call_arity_mismatch(cj.lhs, fn, param_set)
        if mismatch is not None:
            return Probe(cj.name, statement, "skipped:misspecified",
                         route=None, note=f"{note}; {mismatch}")
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
    inferred_domain = _inferred_literal_domain(cj.lhs, facts.params)
    if cj.rhs:
        for p, bounds in _inferred_literal_domain(cj.rhs, facts.params).items():
            inferred_domain.setdefault(p, bounds)
    inferred_domain = {p: b for p, b in inferred_domain.items() if p not in cj_domain}
    cj_domain = {**inferred_domain, **cj_domain}
    if inferred_domain:
        note = (f"{note}; inferred "
               + ", ".join(f"{p}={v[0]:g}" for p, v in sorted(inferred_domain.items()))
               + " from the claim's own literal argument")
    # annotation-inferred domain TYPE, the same gap-filling shape as
    # the literal inference above: an int annotation is domain
    # information the author already wrote, so a parameter with no
    # stated bound at all resolves to the integer type, rendered here
    # explicitly; a stated domain always wins, and a plain
    # float/unknown annotation infers nothing (everywhere-real is
    # already the default reading). A bool parameter's two-point set
    # arrives through facts.finite_domains below instead, the same
    # channel a Literal[...]/Enum annotation uses, so the stated
    # values are the real False/True objects
    _ANNOTATION_DOMAIN = {"int": "Z"}
    annotation_inferred = {
        p: _ANNOTATION_DOMAIN[facts.param_kinds.get(p)]
        for p in facts.params
        if p not in cj_domain
        and facts.param_kinds.get(p) in _ANNOTATION_DOMAIN}
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
    # a Literal[...]/Enum annotation states the parameter's entire
    # value set, the finite-set counterpart of the type inference
    # above, rendered the same way
    literal_inferred = {
        p: frozenset(vals)
        for p, vals in getattr(facts, "finite_domains", {}).items()
        if p not in cj_domain}
    if literal_inferred:
        cj_domain = {**literal_inferred, **cj_domain}
        note = (f"{note}; inferred "
               + ", ".join(
                   p + " in {"
                   + ", ".join(repr(v) for v in sorted(vals, key=repr)) + "}"
                   for p, vals in sorted(literal_inferred.items()))
               + " from its own annotation's stated values")
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
                stated_kind = _BASE_TYPE_KIND.get(bound.base_type,
                                                  bound.base_type.lower())
                if real_kind not in (None, "unknown", stated_kind):
                    note = (f"{note}; let-declared free variable {p!r} states "
                           f"'{bound.base_type}' but the real parameter {p!r} "
                           f"is {real_kind!r}; the stated type is used as "
                           f"written, not silently reconciled")
        if resolved:
            note = (f"{note}; let-declared free variable(s) {resolved} "
                   f"match real parameter(s) of this function, deferred "
                   f"to the real parameter's own kind")
    if cj.relation in ("<=", ">="):
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
    from .domain import KNOWN_BASE_TYPES
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
    return _ClaimContext(cj=cj, statement=statement, note=note,
                         cj_domain=cj_domain, extra=frozenset(cj.funcs))


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
                "mathema.corroboration", "mathema.corroboration_unexecutable"):
        if key in proof.meta:
            meta[key] = proof.meta[key]
    return meta


# infinity approximation for the numerical-stability sweep when a claim
# declares no pseudo_infinity cap: the "full extreme" corner value. The
# sampler's own 1e6 specials already probe overflow-prone functions
# (exp overflows ~710); this caps an unbounded corner so it is finite.
def _operational_domain(cj_domain: dict, magnitude: float):
    """Intent:
        The empirical-check reading of a `let |inf| be v` claim: every
        infinite interval endpoint rewritten to the operational
        magnitude (closed there; the operational extreme is an
        attainable trial point), leaving every finite endpoint and
        every non-interval bound exactly as declared. Returns the
        rewritten copy plus a rendering of each change, so the record
        can state the operational region next to the true proof
        region.

    Notes:
        The probe stage's reading. The derive route bounds the same
        unbounded directions through `_derive_operational_domain`, so
        a proof under an operational infinity is a proof up to it, and
        the record states that bound.
        Bare type bounds ("N", "Z", a Domain object) are not rewritten,
        the shorthand replaces the oo SYMBOL the author wrote,
        nothing else.
    """
    from .grammar import Interval
    rewritten: dict = {}
    changes: list = []
    for p, bound in cj_domain.items():
        if not (isinstance(bound, tuple) and not isinstance(bound, frozenset)
                and len(bound) == 2):
            rewritten[p] = bound
            continue
        try:
            lo, hi = float(bound[0]), float(bound[1])
        except (TypeError, ValueError):
            rewritten[p] = bound
            continue
        lo_inf, hi_inf = lo == -float("inf"), hi == float("inf")
        if not (lo_inf or hi_inf):
            rewritten[p] = bound
            continue
        new_lo = -magnitude if lo_inf else bound[0]
        new_hi = magnitude if hi_inf else bound[1]
        closed_lo = True if lo_inf else getattr(bound, "closed_lo", True)
        closed_hi = True if hi_inf else getattr(bound, "closed_hi", True)
        rewritten[p] = Interval(new_lo, new_hi, closed_lo, closed_hi)
        changes.append(f"{p} in {rewritten[p]!r}")
    return rewritten, changes


# the soundness gates moved to mathema/gates.py (beside the
# corroboration engine they drive); these re-imports keep the public
# knob and every existing reference working unchanged
from .gates import (  # noqa: E402
    _EXTREME as _EXTREME,
    _STABILITY_CHECK as _STABILITY_CHECK,
    _corroboration_gate as _corroboration_gate,
    _fmt_point as _fmt_point,
    _point_evaluator as _point_evaluator,
    _stability_gate as _stability_gate,
    set_numerical_stability_check as set_numerical_stability_check,
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
    family_derive = family.routes().get("derive") if family is not None else None
    family_proof = (families.call_route(family_derive, fn, facts, cj.lhs,
                                        cj.rhs, cj.relation,
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
    if family_proof is not None and cj.name.split("[", 1)[0] == "is_defined":
        # region equivalence is the ONLY reading of an is_defined
        # claim: an undecided family verdict is final, the ordinary
        # prover and the probe sampler would answer a different
        # question (is the stated relation TRUE?), not whether it
        # names the definedness region
        return Probe(cj.name, statement, "unknown", route=cj.route,
                     sketch=family_proof.sketch,
                     note=f"{note}; region equivalence undecided",
                     meta=_provenance_meta(family_proof))
    # a matrix-algebra relation claim (det / transpose / matmul / trace
    # / inverse over declared matrix parameters) is decided by sympy's
    # matrix algebra, not by lifting f's body, so it is attempted before
    # the ordinary derive-eligibility gate (which would treat `det` as
    # an unresolved bound function). A structure marker or an
    # `assuming A is symmetric` premise becomes a sympy assumption. A
    # proof stands as the verdict; an undecided identity falls to the
    # matrix-value probe (sampled concrete matrices, a witness on
    # disagreement), a route="derive" claim to the honest unknown.
    if (not cj.negated
            and cj.relation in ("==", "~=", ">", ">=", "<", "<=", "!=")
            and mentions_matrix_ops(cj.lhs, cj.rhs)):
        from .claim_families import matrix_relation_probe
        from .symbolic import matrix_param_dims
        from .types import shapes_from_signature, structures_from_signature
        _shapes = shapes_from_signature(fn)
        _dims = matrix_param_dims(cj_domain, _shapes)
        if _dims:
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
            if cj.route == "derive":
                # strict: this route promises proof-strength evidence, so
                # an undecided identity is the honest unknown, never a
                # silent fall to sampling.
                return Probe(
                    cj.name, statement, "unknown", route="derive",
                    sketch=(mproof.sketch if mproof is not None else None),
                    note=f"{note}; matrix identity not closed symbolically",
                    meta={"mathema.derive_status":
                          (mproof.status if mproof is not None
                           else "unliftable")})
            mprobe = matrix_relation_probe(cj, fn, _dims, _structs,
                                           statement, note)
            if mprobe is not None:
                return mprobe
            return Probe(
                cj.name, statement, "unknown", route="derive",
                sketch=(mproof.sketch if mproof is not None else None),
                note=f"{note}; matrix identity not closed symbolically and "
                     f"not sampleable here",
                meta={"mathema.derive_status": "undecided"})
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
                note=f"{note}; the registered family for this claim's own "
                     f"name couldn't decide it, and there is no ordinary "
                     f"derive route for this predicate",
                meta={"mathema.derive_status": "unsupported"})
            return None
        if cj.route == "derive":
            # a multi-function raises claim isn't uncertain, this route
            # structurally doesn't support that shape at all, so it
            # stays the plain "skipped" every other structural-mismatch
            # skip in this function uses.
            return Probe(cj.name, statement, "skipped", route=cj.route,
                         note=f"{note}; derive route does not yet lift "
                              f"multi-function raises claims")
        # route == "best" and derive-ineligible: fall through to the
        # probe stage, same as an ordinary probe claim.
        return None
    bound_funcs: dict = {}
    if ctx.extra:
        try:
            bound_funcs = {name: (v if callable(v) else _resolve_func_ref(v))
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
    derive_domain = _derive_operational_domain(cj, cj_domain, facts)
    if cj.relation == "raises":
        # only ever reachable via domain-conditioned branch
        # pruning, a raises claim with no domain specific
        # enough to settle which branch runs comes back
        # unliftable from try_prove_raises itself, same as any
        # other undecidable derive claim.
        proof = try_prove_raises(fn, facts, cj.lhs, cj.rhs or None,
                                 domain=derive_domain)
    else:
        proof = try_prove(fn, facts, cj.lhs, cj.rhs, cj.relation,
                          domain=derive_domain, tolerance=cj.tolerance,
                          extensive=extensive, funcs=bound_funcs or None,
                          assumption=assumption,
                          assume_defined=ctx.assume_defined)
    def _brute_force_fallback():
        """A claim quantified over a FINITE declared domain needs no
        symbolic argument: visiting every point the domain admits
        settles it outright. Tried only where the symbolic routes left
        no reliable verdict, so nothing they decided can move."""
        from ._brute_force import brute_force_proof
        from ._timeout import EXTENSIVE_TIMEOUT_SECONDS, _with_timeout
        try:
            return _with_timeout(
                lambda: brute_force_proof(cj, fn, facts, cj_domain,
                                          bound_funcs,
                                          assumption=assumption or []),
                EXTENSIVE_TIMEOUT_SECONDS)
        except TimeoutError:
            # an unfinished sweep covers only a prefix of the domain,
            # which settles nothing
            return None

    depth_refusal = (proof.meta or {}).get("mathema.recursion_depth")
    if depth_refusal is not None:
        # the implementation cannot recurse deep enough to cover this
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
        if swept is not None:
            proof = swept
    inlined = getattr(facts, "_inlined_globals", None)
    if inlined:
        # the lift read module-level constants as their current
        # values: state that explicitly (their exact values also ride
        # the record's dependency section, where the freshness sweep
        # watches them)
        note = (note + "; module constants read at adjudication: "
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
        if mechanism == "brute_force":
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
        # a derive proof is exact; the residual risk is NUMERICAL, so
        # sweep the implementation for instability near the boundaries
        return _stability_gate(proven, cj, fn, facts, cj_domain, bound_funcs,
                               assum=assumption or [])
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
                return _stability_gate(proven, cj, fn, facts, cj_domain,
                                       bound_funcs, assum=assumption or [])
            if swept.status == "disproven":
                return Probe(cj.name, statement, "falsified",
                             route="derive:brute_force", sketch=swept.sketch,
                             counterexample=swept.counterexample, note=note,
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
        note=note + f"; derive route {proof.status}",
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
    from .records import pseudo_infinity_range
    pinf = pseudo_infinity_range(getattr(cj, "pseudo_infinity", None))
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
    contract = (f"numeric evidence on the LIFTED intermediate ({checked} "
                f"samples of the resolved symbolic form, mathema's "
                f"reconstruction, not the code; the symbolic comparison "
                f"itself stayed undecided)")
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



def _call_arity_mismatch(src: str, fn, param_set: set) -> str | None:
    """Intent:
        The reason a call to `f` in the claim text `src` cannot bind to
        `fn`'s signature (too many or too few arguments, an unknown
        keyword), or None when every such call fits or the signature
        cannot be read.

    Notes:
        A starred argument is not counted and makes the check decline
        for that call. A parameter literally named `f` makes `f(...)`
        ambiguous, so the check declines entirely.
    """
    import inspect as _inspect
    if "f" in param_set:
        return None
    try:
        sig = _inspect.signature(fn)
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
            sig.bind(*([None] * len(node.args)),
                     **{k.arg: None for k in node.keywords})
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
    import inspect as _inspect
    try:
        sig = _inspect.signature(callee)
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
        that the carrier gave out before the value existed. The
        verdict stays falsified either way; this only classifies.
    """
    for exc_type, cause in _MACHINE_FAILURE_CAUSES.items():
        if isinstance(exc, exc_type):
            return {"blame": "implementation", "cause": cause,
                    "representation": "f64", "witness": witness}
    return None


def _adjudicate_probe(ctx: "_ClaimContext", fn, facts, kinds: dict,
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
    from .records import pseudo_infinity_range
    pinf = pseudo_infinity_range(getattr(cj, "pseudo_infinity", None))
    if pinf is not None:
        # the |inf| binding is the empirical reading of the declared
        # oo: this stage (and only this stage) rewrites infinite
        # endpoints to the operational magnitude, and the record says
        # so next to the true region; the derive stage never sees
        # this, so a symbolic proof still covers actual infinity
        cj_domain, approximated = _operational_domain(cj_domain, pinf[1])
        if approximated:
            note = (f"{note}; the implementation and empirical analysis "
                    f"approximate infinity as the pseudo-infinity "
                    f"{pinf[1]:g} ({', '.join(approximated)}); the "
                    f"symbolic proof region keeps the declared oo")
    if cj.name.split("[", 1)[0] == "is_defined":
        # region equivalence has no empirical reading: sampling the
        # stated relation as a bare fact answers the wrong question
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"{note}; is_defined adjudicates by region "
                          f"equivalence on the derive route only")
    if cj.relation not in (frozenset({"==", "~=", "!=", "<=", ">=", "<", ">",
                                      "raises"})
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
    if cj.relation == "raises" and cj.rhs and cj.rhs not in _EXC_TYPES:
        return Probe(cj.name, statement, "skipped", route=None,
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
        # "probe:minimal_example"); evidence_rank folds any subroute back
        # to the "probe" rung, so this is descriptive, not a strength claim.
        probe_route = getattr(family, "probe_route", "probe:algorithmic")
        setup = sampling()
        algo_result = algo_route(fn, facts, cj, cj_domain, setup.rng, setup.budget)
        if algo_result is not None:
            if len(algo_result) == 4:
                verdict, checked, cx, established = algo_result
            else:
                verdict, checked, cx = algo_result
                established = None
            if verdict == "proven":
                # an ESTABLISHED empirical examination: the guard only
                # lets this through with the exhaustive-coverage
                # sketch, so the surety is real however it was reached
                return Probe(cj.name, statement, "proven", n=checked,
                             route=probe_route, sketch=established,
                             note=note)
            if verdict == "falsified":
                # two safety families whose falsification is BY
                # CONSTRUCTION about the implementation stratum:
                # spelling divergence and unguarded crashes have no
                # mathematical reading at all
                family_cause = {
                    "is_representation_safe": "implementation:representation",
                    "is_arbitrary_input_safe":
                        "implementation:accidental-crash",
                }.get(cj.name.split("[", 1)[0])
                return Probe(cj.name, statement, "falsified", n=checked,
                             route=probe_route, counterexample=cx, note=note,
                             stratum=({"blame": "implementation",
                                       "cause": family_cause,
                                       "witness": cx}
                                      if family_cause else None))
            if verdict == "holds":
                return Probe(cj.name, statement, "holds", n=checked,
                             route=probe_route, note=note)
            return Probe(cj.name, statement, "skipped", route=probe_route,
                         note=note + f"; {cx or 'no evaluable inputs'}")
    if cj.relation in routes.examine_predicates():
        # only reachable when the registered family declined, the
        # generic sampling loop below has no meaning for a
        # domain-safety predicate, so stop here rather than
        # dispatching predicate text into the compiled-expression
        # machinery.
        return Probe(cj.name, statement, "unknown", route=None,
                     note=f"{note}; the registered family for this claim's "
                          "own name couldn't decide it, and the generic "
                          "sampling loop has no meaning for this predicate")
    try:
        if cj.relation == "raises":
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
        bound_funcs = {name: (v if callable(v) else _resolve_func_ref(v))
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
    assum_eval = None
    if ctx.assumption is not None:
        compiled: list = []
        aux_all: set = set()
        try:
            for acj in ctx.assumption:
                a_code_l, a_aux_l = _validate(acj.lhs, set(kinds), extra)
                a_code_r, a_aux_r = _validate(acj.rhs, set(kinds), extra)
                a_tol = cj.tolerance if cj.tolerance is not None else DEFAULT_TOLERANCE
                a_rel = _declared_rel_tol(cj)
                a_op = {"<=": _operator.le, ">=": _operator.ge,
                        "<": _operator.lt, ">": _operator.gt,
                        "==": lambda a, b, t=a_tol, r=a_rel:
                            _close(a, b, tolerance=t, rel_tol=r),
                        "!=": lambda a, b, t=a_tol, r=a_rel:
                            not _close(a, b, tolerance=t, rel_tol=r)
                        }[acj.relation]
                compiled.append((a_code_l, a_code_r, a_op))
                aux_all |= a_aux_l | a_aux_r
            assum_eval = (compiled, aux_all)
        except (InvalidConjecture, KeyError) as e:
            return Probe(cj.name, statement, "skipped", route=None,
                         note=f"{note}; assuming clause isn't evaluable "
                              f"on the probe route: {e}")
    # an EQUALITY conjunct makes the feasible region a measure-zero
    # surface random draws essentially never land on: solve the
    # equality for one variable symbolically, so every trial computes
    # that coordinate from the others and sits exactly on the surface
    # (the rejection filter below still checks every other conjunct)
    assum_solved = None
    if assum_eval is not None and ctx.assumption is not None:
        import ast as _ast

        import sympy as _sp

        from . import _timeout as _timeout_mod
        from ._timeout import _with_timeout
        from .grammar import _node_to_sympy
        for acj in ctx.assumption:
            if acj.relation != "==" or not acj.rhs:
                continue
            try:
                l_expr = _node_to_sympy(_ast.parse(acj.lhs, mode="eval").body, {})
                r_expr = _node_to_sympy(_ast.parse(acj.rhs, mode="eval").body, {})
            except Exception:
                continue
            surface = l_expr - r_expr
            syms = {str(s): s for s in surface.free_symbols}
            for p_name in [p for p in kinds if p in syms] + \
                          [a for a in sorted(syms) if a not in kinds]:
                try:
                    sols = _with_timeout(
                        lambda: _sp.solve(_sp.Eq(surface, 0), syms[p_name]),
                        _timeout_mod.FAST_TIMEOUT_SECONDS)
                except Exception:
                    continue
                if len(sols) == 1:
                    others = sorted(set(syms) - {p_name})
                    try:
                        compute = _sp.lambdify(
                            [syms[o] for o in others], sols[0], "math")
                    except Exception:
                        continue
                    assum_solved = (p_name, others, compute)
                    break
            if assum_solved is not None:
                break
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
    from .types import structures_from_signature
    # a parameter's structure comes from its signature marker and from
    # an `assuming A is symmetric` premise; both narrow synthesis the
    # same way, the premise's set unioned onto the marker's
    param_structures = dict(structures_from_signature(fn))
    for _pp, _props in (ctx.premise_structures or {}).items():
        param_structures[_pp] = tuple(sorted(
            set(param_structures.get(_pp, ())) | set(_props)))
    setup = sampling()
    rng, specials, risk, budget = setup.rng, setup.specials, setup.risk, setup.budget
    critical_hints, truncated_hints = setup.critical_hints, setup.truncated_hints
    extra_cycles, probe_route = setup.extra_cycles, setup.route
    checked, cx, cx_stratum = 0, None, None
    # the largest exact ordering violation the default allowance
    # absorbed, and the arguments it happened at
    absorbed, absorbed_at = 0.0, None
    pinned = _pinned_arg_sets(cj, len(kinds))
    # a literal argument in the claim's own call (`f(values, "nope",
    # 0.35)`) fixes that parameter to the literal; the call passes it
    # verbatim, so sampling must not overwrite it with a synthesized
    # value (which would misreport the witness, e.g. `"nope"` as 0).
    literal_args = _literal_call_args(cj.lhs, facts.params)
    if cj.rhs:
        literal_args.update(_literal_call_args(cj.rhs, facts.params))
    # the domain box's corners replay with the recorded counterexamples,
    # before any random sampling
    pinned += [c for c in _domain_corners(kinds, cj_domain, literal_args)
               if c not in pinned]
    call_raised = [None]   # the LABEL of the callee that raised, or None

    def _tagged(callee, label):
        # a raise from the function under test (or a bound function) is
        # pedantic evidence; a raise from the law's own plumbing (a
        # malformed sum(...), a bad index, a wrong argument count) is a
        # broken sample, not a counterexample; attribution is the
        # difference
        try:
            sig = inspect.signature(callee)
        except (TypeError, ValueError):
            sig = None
        # a complex result under a real claim is no value at all, the
        # same as a raise
        complex_raises = complex_is_a_raise(callee, cj_domain)

        def _wrapped(*a, **k):
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
            return value
        return _wrapped

    fn_tagged = _tagged(fn, "f")
    bound_tagged = {name: _tagged(v, name) for name, v in bound_funcs.items()}
    for trial in range(budget + len(pinned)):
        call_raised[0] = None
        trial_sizes: dict = (
            _draw_trial_sizes(resolver, shape_lo, shape_hi, shape_groups, rng)
            if plan_dims and trial >= len(pinned) else {})
        # MATH_CONSTANTS before the per-trial parameter assignment
        # below, so a parameter named `e`/`pi` overrides the constant
        # (precedence identical to the derive route)
        env = {"f": fn_tagged, **_SAFE_FUNCS, **MATH_CONSTANTS, **bound_tagged}
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
                if k == "dict":
                    # a mapping parameter: synthesise a dict matching the
                    # nested key structure the body reads (from
                    # facts.tree), so `d["field"]`, `d["a"]["b"]` and
                    # `d.values()` all find what they expect.
                    from .symbolic._base import _dict_key_tree
                    tree_keys = (_dict_key_tree(facts.tree, p)
                                 if facts.tree is not None else {})
                    v = _synth_dict(tree_keys, rng, specials)
                    env[p] = v
                    args.append(v)
                    continue
                if p in bundles:
                    v = _synth_instance(bundles[p], p, cj_domain, rng,
                                        specials)
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
                    n = trial_sizes.get(key) or rng.randint(2, 5)
                    v = _mtx.synth_for(param_structures[p], n, rng)
                elif shape is not None and shape.ndim >= 2:
                    # a matrix-shaped (marker-declared) parameter: the
                    # resolver nests to the marked axes, each leaf a
                    # fresh element draw, sizes fixed by the shape plan
                    # (shared marker dims agree by construction)
                    v = resolver.synth(
                        p, trial_sizes,
                        lambda: _synth("float", rng, cj_domain.get(p),
                                       specials=specials), rng)
                else:
                    # a scalar or 1-D sequence: _synth owns the element
                    # domain and the special-value shapes; the plan
                    # only fixes a 1-D length when a premise did
                    length = trial_sizes.get(resolver.key(p, 0))
                    v = _synth(k, rng, cj_domain.get(p),
                              specials=specials, extra=critical_hints.get(p),
                              extra_cycle=extra_cycles.get(p),
                              length=length)
                env[p] = v
                args.append(v)
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
            from .domain import domain_contains
            p_name, others, compute = assum_solved
            try:
                sv = compute(*[env[o] for o in others if o in env])
            except Exception:
                sv = None
            if isinstance(sv, (int, float)) and not isinstance(sv, bool) \
                    and sv == sv:
                p_bound = cj_domain.get(p_name)
                if p_bound is not None and not domain_contains(sv, p_bound):
                    continue
                env[p_name] = sv
                if p_name in kinds:
                    args[list(kinds).index(p_name)] = sv
        # marker dim names (Shape("m","n")) become real quantities the
        # premise and law can reference, read off this trial's shapes
        resolver.bind_env(env, {p: env[p] for p in kinds if p in env})
        if assum_eval is not None:
            # the claim only quantifies over the region the assuming
            # clause carves out: a sample violating ANY conjunct
            # neither confirms nor denies anything (rejection sampling)
            compiled, a_aux = assum_eval
            for a_name in a_aux:
                if a_name not in env:
                    env[a_name] = rng.uniform(-5, 5)
            try:
                if not all(a_op(eval(a_l, {"__builtins__": {}}, env),
                                eval(a_r, {"__builtins__": {}}, env))
                           for a_l, a_r, a_op in compiled):
                    continue
            except Exception:
                continue
        if cj.relation == "raises":
            # the claim is that the call raises: returning any value is
            # the counterexample, raising the wrong type falsifies a
            # typed raises claim, raising right is a pass
            try:
                v = eval(code_l, {"__builtins__": {}}, env)
            except Exception as e:
                checked += 1
                if cj.rhs and not isinstance(e, _EXC_TYPES[cj.rhs]):
                    cx = (f"{_fmt(tuple(args))}: raised "
                          f"{type(e).__name__}, claimed {cj.rhs}")
                    break
                continue
            checked += 1
            cx = f"{_fmt(tuple(args))}: returned {v!r} instead of raising"
            break
        try:
            lv = eval(code_l, {"__builtins__": {}}, env)
            rv = eval(code_r, {"__builtins__": {}}, env)
        except Exception as e:
            if any(is_missing(v) for v in args):
                # missing-value behavior is its own axis
                # (is_missing_safe), never adjudicated through a value
                # claim's samples
                continue
            if not call_raised[0]:
                # the law's own plumbing failed, not the function,
                # a broken sample, never a counterexample
                continue
            if ctx.assume_defined and call_raised[0] == "f":
                # `assuming is_defined(f)`: a sample where F raises is
                # outside the quantified region, rejected. A raise
                # from a BOUND function is not excused: is_defined(f)
                # says nothing about g, and the pedantic reading stands
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
            for direction in (1.0, -1.0):
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
                           not _close(jl, jr, tolerance=slack,
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
                cx = (f"{_fmt(tuple(args))}: raised {type(e).__name__} at a "
                      f"floating-point boundary (the same inputs nudged "
                      f"within ε evaluate cleanly), a clamp at the raising "
                      f"operation's argument would remove the instability")
                # nudged inputs evaluating cleanly IS the maths-sound
                # evidence: the failure lives in the carrier's last ulp
                cx_stratum = {"mathematics": "sound",
                              "blame": "implementation",
                              "cause": "implementation:sub-epsilon-boundary",
                              "representation": "f64",
                              "witness": _fmt(tuple(args))}
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
                             f"{_fmt(tuple(args))}: parameter(s) "
                             f"{', '.join(int_params)} of "
                             f"{call_raised[0]} are int-typed but the "
                             f"claim's domain admits non-integers "
                             f"({', '.join(nonint)}); add `subset Z` "
                             f"to the integer variable's domain")
            # a raise is not a value: the claim asserts an equality or
            # ordering AT this in-domain point, and there is nothing on
            # one side to compare, pedantically, that falsifies it.
            checked += 1
            if isinstance(e, ComplexResult):
                cx = (f"{_fmt(tuple(args))}: {e}, which a real claim reads "
                      f"as a raise; narrow the claim's domain to where every "
                      f"call is real, or annotate the function complex")
                break
            cx = (f"{_fmt(tuple(args))}: raised {type(e).__name__}, narrow "
                  "the claim's domain to where every call returns, or state "
                  "the raising region as its own raises(...) claim")
            cx_stratum = _machine_failure_stratum(e, _fmt(tuple(args)))
            break
        if (is_missing(lv) or is_missing(rv)) and not (
                not any(is_missing(v) for v in args)
                and any(isinstance(v, float) and v != v for v in (lv, rv))):
            # a domain that includes missing by default (see
            # grammar.parse_binding's own policy) can sample the
            # missing sentinel itself as a candidate value; a
            # function that returns it unchanged (identity, say)
            # leaves lv/rv genuinely non-comparable, neither
            # confirming nor denying the claim, so this sample is
            # inconclusive. A NaN computed from non-missing inputs is
            # different: it is the function's value at an in-domain
            # point, and the comparison below reads it as IEEE does
            # (no ordering holds, and it equals no number).
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
        ok = relation_holds_elementwise(
            lv, rv, cj.relation, slack,
            exact_inequality=cj.tolerance is None,
            rel_tol=_declared_rel_tol(cj))
        if ok is None:
            # structurally unanswerable on this route: an ordering over
            # values that do not order (a complex return), or two
            # matrices of mismatched shape. Not falsified, not a bad
            # sample; skip, as the derive route refuses the same.
            return Probe(cj.name, statement, "skipped", route="probe",
                         note=note + f"; ordering ({cj.relation}) over "
                              f"{type(lv).__name__} vs {type(rv).__name__} "
                              f"values isn't meaningful as a single verdict "
                              f"(a complex value, or mismatched matrix shapes)")
        if ok and cj.tolerance is None:
            gap = ordering_shortfall(lv, rv, cj.relation)
            if gap > absorbed:
                absorbed, absorbed_at = gap, _fmt(tuple(args))
        if not ok:
            aux_part = ("; " + ", ".join(
                f"{a}={env[a]:.3g}" if isinstance(env[a], (int, float))
                else f"{a}={env[a]!r}" for a in aux) if aux else "")
            cx = f"{_fmt(tuple(args))}{aux_part}: {lv!r} vs {rv!r}"
            break
    if cx is not None:
        return Probe(cj.name, statement, "falsified", n=checked, route=probe_route,
                     counterexample=cx, note=note, stratum=cx_stratum,
                     meta={"mathema.sampling": _sampling_shorthand(
                               kinds, cj_domain, checked, critical_hints, truncated_hints),
                          "mathema.confidence": _probe_density(risk, checked),
                          "mathema.counterexample_args": _yaml_safe_args(args)})
    if checked == 0:
        why = ("; no sampled point satisfied the assuming clause"
               if assum_eval is not None else "; no evaluable inputs")
        return Probe(cj.name, statement, "skipped", route="probe",
                     note=note + why)
    if absorbed > 0:
        note = (f"{note}; fails by {absorbed:.3g} at {absorbed_at}, within "
                f"the default tolerance ({DEFAULT_TOLERANCE:g})").lstrip("; ")
    return Probe(cj.name, statement, "holds", n=checked, route=probe_route, note=note,
                 meta={"mathema.sampling": _sampling_shorthand(
                           kinds, cj_domain, checked, critical_hints, truncated_hints),
                      "mathema.confidence": _probe_density(risk, checked)})



# namespace-friendly alias: mathema.claims.check(fn, [...])
check = check_conjectures

EVIDENCE_LADDER = (
    ("derive",),
    ("derive:extensive",),
    # A reserved, not-yet-built "numerical" evidence tier belongs here,
    # between derive:extensive and the informed-probing rung below,
    # a real numerical-methods engine (finite-difference/bisection with
    # error bounds, not just a probe:algorithmic sample) would be
    # stronger than sampling but still short of a symbolic proof. Named
    # here so the slot isn't accidentally claimed by something smaller
    # first.
    ("probe:semi_analytical", "probe:algorithmic"),
    ("probe",),
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
# rank, `probe:semi_analytical` (critical-point-informed sampling)
# and `probe:algorithmic` (a family-provided technique, e.g. pairwise
# monotonicity) are both "informed rather than blind" probing, from
# different information sources, neither stronger than the other.
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
        `probe:algorithmic`/`probe:semi_analytical` do here. A value
        this ladder doesn't recognize at all (a custom route from a
        different verification technique, per record-schema.md's "Open
        for extension") ranks last, weaker than every known value,
        never stronger.
    """
    base = route_or_class.split(":", 1)[0]
    for candidate in (route_or_class, base):
        for rank, rung in enumerate(EVIDENCE_LADDER):
            if candidate in rung:
                return rank
    return len(EVIDENCE_LADDER)
