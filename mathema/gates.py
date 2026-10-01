# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The soundness gates at the derive->Probe seam, beside the
corroboration engine they drive: `_corroboration_gate` (no derive
disproof survives unless an executed in-domain point reproduces it
against the real function; an unreproduced one downgrades to unknown
with the engine-bug flag), `_float_companion` (the `<name>[float]`
claim a derive proof spawns: the same relation executed against the
real code in float, at the domain's corners and sampled interior
points), and `_point_evaluator`, the injected-dependency builder both
(and the corroboration engine) run on.

The gates consume `conjecture`'s claim plumbing (`_validate`,
`_SAFE_FUNCS`) through call-time imports: `conjecture` imports this
module at load, this module reaches back only when a gate actually
runs, so the import graph stays acyclic."""
from __future__ import annotations

from . import _shapes
from ._math_vocab import MATH_CONSTANTS
from .corroboration import INCONCLUSIVE
from .records import Probe
from .runtime_types import SEQUENCE_KINDS


def _conjecture_bits():
    """The claim-plumbing names the evaluator needs from conjecture,
    resolved at call time (see the module docstring's cycle note)."""
    from .conjecture import InvalidConjecture, _SAFE_FUNCS, _validate
    return InvalidConjecture, _SAFE_FUNCS, _validate


_EXTREME = 1e10

# the name suffix, and the family, of a derive claim's computation
# companion
FLOAT_SUFFIX = "[float]"
FLOAT_FAMILY = "is_numerically_stable"

# the authored route that states the mathematics alone: adjudicated as
# a derive claim, spawning no float companion
MATH_ONLY_ROUTE = "derive:math_only"


def _integer_bound(bound) -> bool:
    """Intent:
        Whether a declared bound admits integers only: a `Z`/`N` domain
        (a subset of one included) or a finite set of whole numbers.
        What a parameter's values ARE is read off its domain, whatever
        its annotation says.
    """
    from .domain import bound_assumptions
    if isinstance(bound, (frozenset, set)):
        return bool(bound) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool)
            and v == v and abs(v) != float("inf") and v == int(v)
            for v in bound)
    try:
        return bool((bound_assumptions(bound) or {}).get("integer"))
    except Exception:
        return False


def _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum=(),
                     cap=None, reach=None, sequences=False,
                     exact=False):
    """Intent:
        Build the injected dependencies the corroboration engine needs
        for THIS claim: `evaluate(point)` decides the original claim's
        relation at a concrete point by calling the real `fn` (True =
        holds, False = a genuine counterexample, None = can't tell);
        `probe_finite(point)` returns a computation-failure detail
        (a raise, a NaN, an inf or a deviation past a magnitude-scaled
        tolerance where the relation fails), None where the code
        agrees, or `corroboration.INCONCLUSIVE` where the claim's own
        evaluation failed; `admits(point)` is
        in-domain-and-assumption membership; `sample(name, rng)` draws
        a value respecting the parameter's declared bound; `exact`
        drops the default allowance, so a claim with no declared
        tolerance is compared with none; `corners` are the domain's
        corner points; `reach` is the magnitude an unbounded direction
        runs to; plus the free-variable `names`.

    Notes:
        `None` when the claim can't be numerically evaluated at all (a
        calculus form d/lim/integrate, or an uncompilable law): the
        caller then marks a disproof uncorroborated and spawns no float
        companion. An unbounded direction runs to `cap`, the claim's
        resolved pseudo-infinity range, when one applies, else to `reach`
        when given (the float companion's large magnitude, sampled
        log-uniformly so moderate magnitudes are visited too), else to
        +-`_EXTREME`. A sequence parameter is evaluable only with
        `sequences=True`: `sample` then draws a list (respecting a
        declared per-element bound) and `admits` requires a list whose
        every element the bound admits. A coordinate whose domain is
        integer-only reaches `fn` as an int, corners included.
    """
    import math
    from .domain import (_as_int_if_whole, bound_to_sympy_set,
                         domain_contains, is_missing, operational_domain)
    from .probing import (ComplexResult, _bound_is_complex, _fmt_value,
                          _is_matrix_value, _synth, complex_is_a_raise,
                          holds_inf, holds_nan, is_complex_value,
                          plain_value, relation_holds_elementwise,
                          same_infinity, values_agree, values_differ)
    InvalidConjecture, _SAFE_FUNCS, _validate = _conjecture_bits()
    kinds = {p: facts.param_kinds.get(p, "unknown") for p in facts.params}
    # the gates verify VALUE claims by calling fn at a point; a
    # non-value relation or a bundled (dataclass/dict) parameter isn't
    # reproducible this way, and a sequence parameter only when the
    # caller asked for list-valued points
    seq_names = {p for p, k in kinds.items() if k in SEQUENCE_KINDS}
    # a parameter whose binding states a space is a container whatever
    # kind the body suggested
    seq_names |= {p for p in kinds if _shapes.dims_of(cj_domain.get(p))}
    if seq_names and not sequences:
        return None
    if cj.relation not in ("==", "~=", "!=", "<=", ">=", "<", ">"):
        return None
    extra = frozenset(bound_funcs)
    from . import _indexed
    indexed = _indexed.uses_indexed_form(cj.lhs) or _indexed.uses_indexed_form(cj.rhs)
    bound_indices: set = set()
    try:
        if indexed:
            extra = extra | frozenset(_indexed.INDEXED_FORMS)
        code_l, aux_l = _validate(cj.lhs, set(kinds), extra)
        code_r, aux_r = _validate(cj.rhs, set(kinds), extra) if cj.rhs else (None, set())
        if indexed:
            # a Sum/Prod index is bound over its summand: it is no
            # coordinate of the point, even when a parameter shares its
            # name
            code_l, aux_l, bound_l = _indexed.compile_indexed(cj.lhs, aux_l)
            bound_r: set = set()
            if cj.rhs:
                code_r, aux_r, bound_r = _indexed.compile_indexed(cj.rhs, aux_r)
            bound_indices = bound_l | bound_r
    except (InvalidConjecture, ValueError):
        return None
    slack = (cj.tolerance if cj.tolerance is not None
             else 0.0 if exact else 1e-9)
    # `ε`/`eps`/`epsilon` in a law is the claim's tolerance, a fixed
    # value, never a free variable to sample
    eps_names = (aux_l | aux_r) & {"eps", "epsilon", "ε"}
    # a parameter the claim never reads (a literal fills it, or its
    # default does) is no coordinate of the point
    from .conjecture import _names_in_claim
    read = _names_in_claim(cj)
    names = [p for p in kinds if p not in bound_indices and p in read] + sorted(
        (aux_l | aux_r) - MATH_CONSTANTS.keys() - eps_names)
    # raises from the function under test (or a bound function) are
    # tagged so the evaluators below can tell a genuine in-domain raise,
    # which IS a failure of a value claim, per the pedantic raise
    # rule, from a raise in the law's own plumbing, which proves
    # nothing about the claim; a non-finite RESULT from the function is
    # tagged the same way, since an inf or NaN the law's own arithmetic
    # produced says nothing about the code either
    calls_raised = [None]
    # the first callee that returned a nan or an infinity for finite,
    # non-missing arguments, as the witness text ("f returned inf")
    calls_nonfinite: list = [None]

    def _tag(callee, label):
        # a complex result under a real claim counts as a raise too
        complex_raises = complex_is_a_raise(callee, cj_domain)

        def _wrapped(*a, **kw):
            try:
                out = callee(*a, **kw)
            except Exception as exc:
                calls_raised[0] = type(exc).__name__
                raise
            if complex_raises and is_complex_value(out):
                calls_raised[0] = "a complex result"
                raise ComplexResult(label, out)
            if calls_nonfinite[0] is None and isinstance(out, float) \
                    and (out != out or abs(out) == float("inf")) \
                    and _finite_arguments(a, kw):
                calls_nonfinite[0] = (
                    f"{label} returned "
                    f"{'nan' if out != out else '-inf' if out < 0 else 'inf'}")
            elif calls_nonfinite[0] is None and isinstance(out, complex) \
                    and (holds_nan(out) or holds_inf(out)) \
                    and _finite_arguments(a, kw):
                # a NaN or an infinity in either component is no value
                calls_nonfinite[0] = (
                    f"{label} returned nan" if holds_nan(out) else
                    f"{label} returned {_fmt_value(complex(out))}")
            elif calls_nonfinite[0] is None and _is_matrix_value(out) \
                    and (holds_nan(out) or holds_inf(out)) \
                    and _finite_arguments(a, kw):
                # an array holding a NaN or an infinity, element by
                # element the same as a scalar result
                calls_nonfinite[0] = (
                    f"{label} returned an array holding "
                    + ("nan" if holds_nan(out) else "an infinity"))
            return out
        return _wrapped

    def _reset():
        calls_raised[0] = None
        calls_nonfinite[0] = None

    from .runtime_types import calling
    from ._linalg_eval import FUNCTIONS as _VECTOR_FUNCS
    from ._exact_premises import premise_functions
    from ._linalg_eval import as_array, law_callable, scalar
    from .conjecture import _bound_for_arrays
    from .matrices import _numpy
    # a claim over vectors or matrices evaluates them as arrays, so
    # `2 * xs` scales and `xs + ys` adds elementwise, never a list
    # repeated or concatenated; the function still receives its own
    # runtime type and its result is read back as an array
    as_arrays = bool(seq_names) and _numpy() is not None
    fn_call = calling(fn, facts)
    if as_arrays:
        fn_call = law_callable(fn_call)
        bound_funcs = {name: _bound_for_arrays(v)
                       for name, v in bound_funcs.items()}
    base_env = {"f": _tag(fn_call, "f"), **_SAFE_FUNCS,
                **_VECTOR_FUNCS, **MATH_CONSTANTS,
                **{name: _tag(v, name) for name, v in bound_funcs.items()},
                **{name: (cj.tolerance if cj.tolerance is not None else 1e-9)
                   for name in eps_names},
                **(_indexed.indexed_env() if indexed else {})}
    from .records import pseudo_infinity_range
    if cap is not None:
        cap_lo, cap_hi = pseudo_infinity_range(cap)
    elif reach is not None:
        cap_lo, cap_hi = -float(reach), float(reach)
    else:
        cap_lo, cap_hi = -_EXTREME, _EXTREME

    int_names = {name for name in names
                 if _integer_bound(cj_domain.get(name))
                 or kinds.get(name) in ("int", "bool")}
    language_names = {name for name in names
                      if getattr(cj_domain.get(name), "base_type", None) == "L"}
    # coordinates the claim quantifies over the complex plane: drawn,
    # cornered and compared as complex values
    complex_names = {name for name in names
                     if _bound_is_complex(cj_domain.get(name))}

    def _typed(point):
        # a whole-number coordinate of an integer domain is passed as an
        # int, the value the probe route draws there; a float would make
        # `range(n)` raise where the claim is about integers
        return {n: (_as_int_if_whole(v) if n in int_names else
                    as_array(v) if as_arrays and n in seq_names
                    and isinstance(v, (list, tuple)) else v)
                for n, v in point.items()}

    def _values(point):
        # the bindings are the globals, so a Sum/Prod term (a lambda)
        # resolves f and the point's coordinates too
        env = {"__builtins__": {}, **base_env, **_typed(point)}
        lv = eval(code_l, env)
        rv = eval(code_r, env) if code_r is not None else 0
        if as_arrays:
            # a 1-by-1 result (`x.T @ A @ x` over a column) is the number it holds
            lv, rv = scalar(lv), scalar(rv)
        return plain_value(lv), plain_value(rv)

    def _relation_holds(lv, rv, tol):
        # inf-aware: an infinity here is one the law's own arithmetic
        # produced (a callee's own nan or inf is no value, read before
        # this: two sides at the same infinity, inf and inf or -inf and
        # -inf, are one extended-real point and agree; a NaN is the
        # absence of a value and agrees with nothing, another NaN
        # included; no value against a value fails). Native comparison handles inf/-inf, never
        # abs(inf - inf) = NaN; abs-difference is only for the finite
        # case.
        rel = cj.relation
        if same_infinity(lv, rv):
            # one extended-real point: equal, so no strict order
            return rel in ("==", "~=", "<=", ">=")
        if isinstance(lv, complex) or isinstance(rv, complex):
            # over C equality and closeness compare by abs(lv - rv);
            # ordering has no complex reading
            finite = not any(holds_inf(v) for v in (lv, rv))
            close = lv == rv or (finite and abs(lv - rv) <= tol)
            if rel in ("==", "~="):
                return close
            if rel == "!=":
                return not (lv == rv) if cj.tolerance is None else not close
            return None
        both_finite = all(abs(v) != float("inf") for v in (lv, rv))
        if rel in ("==", "~="):
            return lv == rv or (both_finite and abs(lv - rv) <= tol)
        if rel == "!=":
            # with no declared tolerance an inequality fails only at an
            # actual equality
            if cj.tolerance is None:
                return not (lv == rv)
            return not (lv == rv or (both_finite and abs(lv - rv) <= tol))
        if both_finite:
            # strict relations compare natively: equality within
            # tolerance must not count as strictly greater/less (the
            # probe loop applies the same rule)
            return (lv <= rv + tol if rel == "<=" else
                    lv >= rv - tol if rel == ">=" else
                    lv < rv if rel == "<" else
                    lv > rv if rel == ">" else None)
        # an infinity on one side: native comparison is exact
        return (lv <= rv if rel == "<=" else lv >= rv if rel == ">=" else
                lv < rv if rel == "<" else lv > rv if rel == ">" else None)

    def _real(v):
        # a plain real number the relation can compare, not a bool,
        # string, None, complex, list, tuple, or NaN (inf is allowed:
        # _relation_holds compares it natively)
        return (isinstance(v, (int, float)) and not isinstance(v, bool)
                and v == v)

    def _complex_pair(lv, rv):
        # two numbers, at least one of them complex
        return (any(isinstance(v, complex) for v in (lv, rv))
                and all(isinstance(v, (int, float, complex))
                        and not isinstance(v, bool) for v in (lv, rv)))

    def _array_relation(lv, rv, tol, point):
        # an array result compared element by element: a NaN the code
        # computed from non-missing inputs is no value and fails; one
        # that propagates a missing input is the missing-value axis's
        # business
        if holds_nan(lv) or holds_nan(rv):
            if any(is_missing(v) or holds_nan(v) for v in point.values()):
                return None
            return False
        return relation_holds_elementwise(
            lv, rv, cj.relation, tol,
            exact_inequality=cj.tolerance is None, rel_tol=0.0)

    def evaluate(point):
        _reset()
        try:
            lv, rv = _values(point)
        except Exception as e:
            # a raise FROM THE FUNCTION at an in-domain point is a
            # genuine failure of a value claim (the pedantic raise
            # rule), so it reproduces a disproof, and so does the
            # claim's own expression having no value (an index outside
            # a sequence it reads, a division by zero); any other
            # plumbing raise stays inconclusive
            return False if calls_raised[0] or isinstance(
                e, (IndexError, ZeroDivisionError)) else None
        if calls_nonfinite[0] is not None:
            # a nan or an infinity the code returned for finite inputs
            # is no value: against a value every relation fails. Two
            # sides overflowing toward the same infinity are one
            # extended-real point and agree, as equal sides; a NaN is
            # the absence of a value and agrees with nothing
            if _same_no_value(lv, rv):
                return cj.relation in ("==", "~=", "<=", ">=")
            return False
        if _complex_pair(lv, rv) and not (holds_nan(lv) or holds_nan(rv)):
            if (holds_inf(lv) or holds_inf(rv)) and not calls_nonfinite[0]:
                # an infinity only the law's own arithmetic produced
                return None
            return _relation_holds(lv, rv, slack)
        if _is_matrix_value(lv) or _is_matrix_value(rv):
            return _array_relation(lv, rv, slack, point)
        if _real(lv) and _real(rv):
            if (abs(lv) == float("inf") or abs(rv) == float("inf")) \
                    and not calls_nonfinite[0]:
                # an infinity only the law's own arithmetic produced
                # (the function returned finite values) says nothing
                # about the code
                return None
            # an overflow the function itself returned is an executed
            # value like any other: if the relation fails on it, that
            # is a counterexample (the overflow rule)
            return _relation_holds(lv, rv, slack)
        # non-numeric result: an EQUALITY relation still compares
        # exactly (None vs a real number is a genuine mismatch, so an
        # opaque disproof reproduces), and ordering over non-orderable
        # values proves nothing. A NaN that propagates a missing input
        # is the missing-policy axis's business, inconclusive here; a
        # NaN computed from non-missing inputs, a scalar or an element
        # of an array or list, is no value and fails every relation,
        # `!=` included: it agrees with nothing, another NaN included
        # (P4)
        if holds_nan(lv) or holds_nan(rv):
            if any(is_missing(v) or holds_nan(v) for v in point.values()):
                return None
            return False
        if cj.relation in ("==", "~="):
            try:
                return bool(lv == rv)
            except Exception:
                return None
        if cj.relation == "!=":
            try:
                return not (lv == rv)
            except Exception:
                return None
        return None

    def probe_finite(point):
        # a computation failure only: a raise from the code, a NaN
        # or an inf the code returned where the relation then fails, or
        # a deviation past a MAGNITUDE-SCALED tolerance (so a correct
        # large-magnitude identity is not flagged, only catastrophic
        # cancellation or a real break is). An inf that still satisfies
        # the relation is fine; a non-numeric result is inconclusive,
        # never a flag.
        _reset()
        try:
            lv, rv = _values(point)
        except Exception as e:
            # a raise from the function under test is a computation
            # failure, and so is the claim's own expression having no
            # value (an index outside a sequence it reads, a division
            # by zero); the law's own plumbing failing otherwise says
            # nothing about the code, and is no agreement either
            if calls_raised[0]:
                return f"the computation raises {calls_raised[0]} here"
            if isinstance(e, (IndexError, ZeroDivisionError)):
                return (f"the claim's own expression raises "
                        f"{type(e).__name__} here ({e})")
            return INCONCLUSIVE
        if calls_nonfinite[0] is not None:
            # no value at a finite input: an overflow, a pole, a nan.
            # Two sides at the same infinity are one extended-real
            # point and agree, as equal sides; a NaN, or an infinity
            # against a value, is a failure
            if _same_no_value(lv, rv) and cj.relation in ("==", "~=",
                                                          "<=", ">="):
                return None
            if calls_nonfinite[0].endswith("nan"):
                return (f"the computation returns NaN here "
                        f"({calls_nonfinite[0]})")
            return (f"{calls_nonfinite[0]}, and an infinity for a finite "
                    f"input is no value")
        if _complex_pair(lv, rv):
            # over C: equality and closeness within a magnitude-scaled
            # tolerance; an infinity or a NaN only the law's own
            # arithmetic produced says nothing about the code
            if holds_nan(lv) or holds_nan(rv) or holds_inf(lv) \
                    or holds_inf(rv) or cj.relation not in ("==", "~=", "!="):
                return None
            scaled = slack + 1e-7 * max(abs(lv), abs(rv), 1.0)
            if _relation_holds(lv, rv, scaled):
                return None
            return (f"the relation fails on the executed values "
                    f"({_fmt_value(complex(lv))} {cj.relation} "
                    f"{_fmt_value(complex(rv))}), past the magnitude-scaled "
                    f"tolerance: precision loss")
        if _is_matrix_value(lv) or _is_matrix_value(rv):
            if holds_nan(lv) or holds_nan(rv) or holds_inf(lv) \
                    or holds_inf(rv):
                # only the law's own arithmetic: the code's own no-value
                # results were read above
                return None
            try:
                import numpy
                size = float(numpy.max(numpy.abs(numpy.asarray(
                    [lv, rv], dtype=complex))))
            except Exception:
                return None
            scaled = slack + 1e-7 * max(size, 1.0)
            held = _array_relation(lv, rv, scaled, point)
            if held is None or held:
                return None
            return (f"the relation fails on the executed values ({lv!r} "
                    f"{cj.relation} {rv!r}), past the magnitude-scaled "
                    f"tolerance: precision loss")
        if any(isinstance(v, float) and v != v for v in (lv, rv)):
            return ("the computation returns NaN here"
                    if calls_nonfinite[0] else None)
        if not (_real(lv) and _real(rv)):
            return None
        overflowed = any(abs(v) == float("inf") for v in (lv, rv))
        if overflowed and not calls_nonfinite[0]:
            return None
        scaled = slack + 1e-7 * max(abs(lv) if not overflowed else 0.0,
                                    abs(rv) if not overflowed else 0.0, 1.0)
        if _relation_holds(lv, rv, scaled):
            return None
        if overflowed:
            return (f"the computation overflows to inf here, and the "
                    f"relation fails on the executed values ({lv!r} "
                    f"{cj.relation} {rv!r})")
        return (f"the relation fails on the executed values ({lv!r} "
                f"{cj.relation} {rv!r}), past the magnitude-scaled "
                f"tolerance: precision loss")

    def _ends(bound):
        # the bound's (lo, hi) as floats, +-inf for an unbounded end
        if isinstance(bound, tuple):
            return float(bound[0]), float(bound[1])
        try:
            sset = bound_to_sympy_set(bound)
            return float(sset.inf), float(sset.sup)
        except Exception:
            return None

    def _wide_draw(name, rng, lo, hi):
        # a log-uniform magnitude out to the reach, so an unbounded
        # direction is visited at moderate AND at large magnitudes
        top = max(math.log10(max(abs(cap_lo), abs(cap_hi), 1.0)), 0.0)
        magnitude = 10.0 ** rng.uniform(-3.0, top)
        if math.isinf(lo) and math.isinf(hi):
            value = magnitude if rng.random() < 0.5 else -magnitude
        elif math.isinf(hi):
            value = lo + magnitude
        else:
            value = hi - magnitude
        value = min(max(value, cap_lo if math.isinf(lo) else lo),
                    cap_hi if math.isinf(hi) else hi)
        return int(round(value)) if name in int_names else value

    # under a pseudo-infinity, a declared unbounded direction samples
    # out to it and no further
    sample_domain = (operational_domain(cj_domain, (cap_lo, cap_hi))[0]
                     if cap is not None else cj_domain)

    from .probing import _synth_dict
    from .symbolic._base import _dict_key_tree
    dict_keys = {name: (_dict_key_tree(facts.tree, name) if facts.tree is not None else {})
                 for name in names if kinds.get(name) == "dict"}

    from . import dimensions as _dims
    from .types import shapes_from_signature
    try:
        resolver = _dims.resolve(facts, shapes_from_signature(fn),
                                 claim_domain=cj_domain)
    except _dims.DimensionConflict:
        resolver = None
    # the sequence coordinates whose axes a marker or a binding names or
    # fixes are drawn to the plan: a fixed size is that size and a shared
    # name agrees across the point; an anonymous 1-D axis keeps the
    # free draw
    planned = {n for n in seq_names if resolver is not None
               and resolver.shapes.get(n) is not None
               and resolver.shapes[n].ndim >= 1
               and any(a is not None for a in resolver.shapes[n].axes)}
    first_planned = next((n for n in names if n in planned), None)
    point_sizes: dict = {}

    def _planned_draw(name, rng, b):
        # a point's coordinates are drawn in `names` order, so the first
        # planned coordinate draws the point's sizes and the rest reuse
        # them
        if name == first_planned or not point_sizes:
            point_sizes.clear()
            point_sizes.update(resolver.draw_sizes(rng))
        if resolver.shapes[name].ndim == 1:
            return _synth("sequence", rng, b,
                          length=point_sizes.get(resolver.key(name, 0)))
        return resolver.synth(name, point_sizes,
                              lambda: _synth("float", rng, b), rng)

    def sample(name, rng):
        # an unbounded parameter samples within the pseudo-infinity
        # range (or the reach), so a declared range bounds the draws
        # too, not only the corners
        b = sample_domain.get(name)
        if name in seq_names:
            # a sequence's declared bound is per element
            if name in planned:
                return _planned_draw(name, rng, b)
            return _synth("sequence", rng, b)
        if name in complex_names:
            # both components, each inside the pseudo-infinity range
            # when one applies
            b = cj_domain.get(name)
            if isinstance(b, tuple):
                c1, c2 = complex(b[0]), complex(b[1])
                z = complex(rng.uniform(min(c1.real, c2.real),
                                        max(c1.real, c2.real)),
                            rng.uniform(min(c1.imag, c2.imag),
                                        max(c1.imag, c2.imag)))
            else:
                z = complex(_synth("complex", rng, b))
            if cap is None:
                return z
            return complex(min(max(z.real, cap_lo), cap_hi),
                           min(max(z.imag, cap_lo), cap_hi))
        if reach is not None and cap is None:
            ends = (-math.inf, math.inf) if b is None else _ends(b)
            if ends is not None and (math.isinf(ends[0]) or math.isinf(ends[1])):
                return _wide_draw(name, rng, *ends)
        if kinds.get(name) == "dict":
            # a mapping parameter carries the keys the body reads, as
            # the probe draws it, so a missing key is never the failure
            return _synth_dict(dict_keys.get(name, {}), rng)
        if b is None:
            b = (cap_lo, cap_hi)
        return _synth(kinds.get(name, "float"), rng, b)

    # a premise is a question about the domain, so its reductions are
    # computed exactly; the law itself stays in float
    premise_words = premise_functions(_VECTOR_FUNCS)

    def admits(point):
        for n in seq_names:
            # a sequence coordinate is a container of the shape its
            # binding states, each element inside the declared
            # per-element bound
            v = point.get(n)
            bound = cj_domain.get(n)
            dims = _shapes.dims_of(bound)
            if dims:
                shape = _shapes.observed_shape(v)
                if shape is None or not _shapes.fits(shape, dims):
                    return False
                elements = list(_shapes.leaves(v))
            elif isinstance(v, (list, tuple)):
                elements = list(v)
            else:
                return False
            if bound is not None and not all(
                    isinstance(e, (int, float)) and domain_contains(e, bound)
                    for e in elements):
                return False
        for n in names:
            bound = cj_domain.get(n)
            v = point.get(n)
            if bound is None or v is None or n in seq_names:
                continue
            if n in language_names or isinstance(v, complex):
                # a language coordinate is judged by its language and a
                # complex one as a complex value, never coerced to a real
                if not domain_contains(v, bound):
                    return False
                continue
            try:
                fv = float(v)
                fv = int(fv) if fv.is_integer() else fv
            except (TypeError, ValueError, OverflowError):
                continue
            if not domain_contains(fv, bound):
                return False
        for a_l, a_rel, a_r in assum:
            try:
                env = {**base_env, **premise_words, **_typed(point)}
                al = eval(compile(a_l, "<a>", "eval"), {"__builtins__": {}}, env)
                ar = eval(compile(a_r, "<a>", "eval"), {"__builtins__": {}}, env)
            except Exception:
                return False
            ops = {"<=": lambda x, y: x <= y, ">=": lambda x, y: x >= y,
                   "<": lambda x, y: x < y, ">": lambda x, y: x > y,
                   "==": lambda x, y: values_agree(x, y) is True,
                   "!=": lambda x, y: values_differ(x, y)}
            if not ops.get(a_rel, lambda x, y: True)(al, ar):
                return False
        return True

    def _endpoint(name, which):
        # the domain's edge in one direction, at the cap/reach when that
        # direction is unbounded, stepped just inside an open end (an
        # integer domain's open end steps to the next integer)
        bound = cj_domain.get(name)
        if bound is None:
            return cap_lo if which == "lo" else cap_hi
        ends = _ends(bound)
        if ends is None:
            return cap_lo if which == "lo" else cap_hi
        val = ends[0] if which == "lo" else ends[1]
        if val != val or math.isinf(val):
            return cap_lo if which == "lo" else cap_hi
        if name in int_names:
            val = math.ceil(val) if which == "lo" else math.floor(val)
            if not domain_contains(val, bound):
                val = val + 1 if which == "lo" else val - 1
            return int(val)
        if not domain_contains(val, bound):
            val = math.nextafter(val, math.inf if which == "lo" else -math.inf)
        return val

    import random as _random
    # a corner's sizes: a fixed axis at its size, every other axis at the
    # corner length 3, shared names agreeing
    corner_sizes = ({k: (int(k) if isinstance(k, str) and k.isdigit() else 3)
                     for k in resolver.distinct_keys()}
                    if resolver is not None else {})

    def _corner_value(name, value):
        # a sequence's corner is a short constant list at the
        # per-element edge; a planned coordinate is nested to its axes
        if name in planned:
            return resolver.synth(name, corner_sizes, lambda: value,
                                  _random.Random(0))
        return [value] * 3 if name in seq_names else value

    def _language_edges(name):
        # a language coordinate has no numeric ends: its corners are the
        # language's own hazard values, the empty string and the long
        # one where the language has them, else two sampled members
        from .domain import LanguageRef
        from .languages import resolve_language
        values: list = []
        for piece in cj_domain[name].pieces:
            if isinstance(piece, LanguageRef):
                values.extend(resolve_language(piece).hazards())
        by_kind = {h.kind: h.value for h in values}
        first = by_kind.get("empty", values[0].value if values else None)
        last = by_kind.get("length", values[-1].value if values else None)
        if first is None or last is None:
            import random as _random
            drawn = sample(name, _random.Random(0))
            first = drawn if first is None else first
            last = drawn if last is None else last
        return first, last

    def _complex_corners(name):
        # a rectangle's four corners, else the plane's far points on
        # both axes (+-R, +-R*1j at the cap or reach), an excluded
        # point left out
        bound = cj_domain.get(name)
        pieces = (getattr(bound, "pieces", None) or
                  ((bound,) if isinstance(bound, tuple) else ()))
        rect = next((p for p in pieces if isinstance(p, tuple)
                     and any(isinstance(v, complex) for v in p)), None)
        if rect is not None:
            c1, c2 = complex(rect[0]), complex(rect[1])
            points = [complex(re, im) for re in (c1.real, c2.real)
                      for im in (c1.imag, c2.imag)]
        else:
            r = max(abs(cap_lo), abs(cap_hi))
            points = [complex(-r, 0.0), complex(r, 0.0),
                      complex(0.0, -r), complex(0.0, r)]
        kept = [z for z in dict.fromkeys(points)
                if bound is None or domain_contains(z, bound)]
        return kept or points[:1]

    edges = {n: (list(_language_edges(n)) if n in language_names else
                 _complex_corners(n) if n in complex_names else
                 [_endpoint(n, "lo"), _endpoint(n, "hi")]) for n in names}
    if len(names) <= 6:
        # every corner of the box: 2^k points for k real coordinates
        # (four per complex coordinate)
        import itertools
        corners = [{n: _corner_value(n, v) for n, v in zip(names, choice)}
                   for choice in itertools.product(*(edges[n] for n in names))]
    else:
        corners = [{n: _corner_value(n, edges[n][min(i, len(edges[n]) - 1)])
                    for n in names} for i in (0, 1)]

    # this dict is the point-runtime kit; `interfaces.runtime` states
    # its contract (and the narrower obligation of a foreign runner
    # whose callable stands in for fn) so the seam is testable
    return dict(evaluate=evaluate, probe_finite=probe_finite, admits=admits,
                sample=sample, corners=corners, names=names)


def _fmt_point(point, names):
    """A point rendered for a counterexample string, numeric coords
    as :.6g, discrete/string coords (a string domain member) as-is."""
    parts = []
    for n in names:
        if n not in point:
            continue
        v = point[n]
        if isinstance(v, str):
            from .probing import spell_text
            parts.append(f"{n}={spell_text(v)}")
            continue
        capped = _shapes.witness_text(v)
        if capped is not None:
            # a large vector or matrix prints its shape, a first row and
            # a count; the full value rides in the counterexample's
            # arguments
            parts.append(f"{n} = {capped}")
            continue
        parts.append(f"{n}={v:.6g}" if isinstance(v, (int, float))
                     and not isinstance(v, bool) else f"{n}={v!r}")
    return ", ".join(parts)


def _sequence_witness(witness, seq_names):
    """Intent:
        A symbolic witness with each sequence parameter's element
        coordinates reassembled into a list the real function can be
        called with. A fold's disproof names its witness per element
        (`x[0]`, `x[L - 1]`, `x[k]`) beside an integer length symbol
        (`L`); the list has that length, the concretely indexed
        elements at their positions and a symbolically indexed
        element's value everywhere else.

    Notes:
        A sequence whose length can't be read off the witness is left
        out, so the corroboration search samples that parameter
        instead. Every other coordinate passes through unchanged, and
        an empty or absent witness comes back as given.
    """
    import re as _re
    if not witness or not seq_names:
        return witness
    out = dict(witness)
    for p in seq_names:
        entries = {}
        for key, value in witness.items():
            m = _re.fullmatch(rf"{_re.escape(p)}\[(.+)\]", str(key))
            if m is not None and isinstance(value, (int, float)):
                entries[m.group(1).strip()] = float(value)
        for key in [k for k in out if str(k).startswith(f"{p}[")]:
            del out[key]
        # the bare parameter name, when the witness carries one, is a
        # scalar stand-in the list replaces
        out.pop(p, None)
        if not entries:
            continue
        index_names = {n for text in entries
                       for n in _re.findall(r"[A-Za-z_]\w*", text)}
        lengths = [witness[n] for n in sorted(index_names)
                   if isinstance(witness.get(n), (int, float))
                   and float(witness[n]).is_integer() and witness[n] >= 1]
        env = {n: int(witness[n]) for n in index_names
               if isinstance(witness.get(n), (int, float))
               and float(witness[n]).is_integer()}
        concrete, filler = {}, None
        for text, value in entries.items():
            try:
                idx = eval(compile(text, "<index>", "eval"),
                           {"__builtins__": {}}, dict(env))
            except Exception:
                filler = value if filler is None else filler
                continue
            if isinstance(idx, int):
                concrete[idx] = value
        if lengths:
            n = int(lengths[0])
        elif concrete and all(i >= 0 for i in concrete):
            n = max(concrete) + 1
        else:
            continue
        seq = [filler if filler is not None else 0.0] * n
        for idx, value in concrete.items():
            if -n <= idx < n:
                seq[idx] = value
        out[p] = seq
    return out


_DEFAULT_ORDERING_SLACK = 1e-9


def _exact_witness_violation(cj, fn, facts, cj_domain, bound_funcs, assum,
                             proof, seq_names):
    """Intent:
        `(point, compared)`: `point` is the point derive named as its
        witness when the real code executed there violates a closed
        ordering (`<=`/`>=`) or an equality (`==`) compared exactly,
        with none of the default allowance, else None; `compared` is
        whether the code was executed and compared there at all. No
        comparison happens when the claim is not such a relation,
        declares its own tolerance (which is then part of the claim),
        or names no in-domain witness.

    Notes:
        `~=` is approximate equality by its own spelling, so it keeps
        the allowance and is never rechecked exactly. A coordinate
        derive's witness leaves free (the difference does not depend on
        it) is drawn from its declared bound with a fixed seed, a few
        draws at most, and the first admissible completion is the point
        compared.
    """
    import random
    from . import corroboration as C
    if cj.relation not in ("<=", ">=", "==") or cj.tolerance is not None:
        return None, False
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum,
                            sequences=True, exact=True)
    if deps is None:
        return None, False
    seeds = C._seed_points(_sequence_witness(proof.witness, seq_names),
                           deps["names"])
    if not seeds:
        return None, False
    named = seeds[0]
    missing = [n for n in deps["names"] if n not in named]
    rng = random.Random(0)
    for _ in range(8 if missing else 1):
        point = {**named, **{n: deps["sample"](n, rng) for n in missing}}
        if deps["admits"](point):
            holds = deps["evaluate"](point)
            if holds is False:
                return point, True
            return None, holds is True
    return None, False


def _corroboration_gate(falsified, proof, cj, fn, facts, cj_domain,
                        bound_funcs, assum=()):
    """Intent:
        Only trust a derive `disproven` once a concrete in-domain
        counterexample reproduces the failure against the REAL
        function, seeded by the proof's own witness. Reproduced ->
        `falsified` (meta corroboration=reproduced; route
        probe:semi_analytical when the analytical seed guided it). Not
        reproduced -> verdict `unknown` with the uncorroborated flag:
        a symbolic disproof nothing reproduces means an engine bug
        somewhere (a corrupted residual, an off-surface search), so the
        record must neither assert the falsification nor hide that it
        was claimed. A disproof whose witness is already an executed
        call to the real function (a raise-region disproof ran the call
        and saw it raise) stands as it is.

    Notes:
        The search compares with the claim's tolerance, or the 1e-9
        default. For a closed ordering with no declared tolerance, a
        search that reproduces nothing is followed by one exact
        comparison at derive's own witness: a violation there, however
        small, is `falsified` with that witness. An equality `==` gets
        the same exact comparison; `~=` does not.
    """
    from . import corroboration as C
    if proof.meta.get("mathema.witness_executed") and falsified.counterexample:
        # no stratum: a raise at the witness is the contract or the
        # mathematics talking, which the probe route leaves unclassified
        # too (conjecture._machine_failure_stratum)
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "reproduced"}
        return falsified
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum,
                            sequences=True)
    if deps is None:
        # a claim with no point evaluation against the function (a
        # calculus form d/lim/integrate, a law that won't compile, a
        # bundled parameter) can't produce an executed witness, and a
        # falsification needs one: the verdict is unknown, flagged
        # uncorroborated like any other disproof nothing reproduced
        falsified.verdict = "unknown"
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "uncorroborated",
                          "mathema.corroboration_unexecutable": True}
        falsified.counterexample = None
        falsified.note = (
            f"{falsified.note}; uncorroborated disproof: the derive route "
            f"reported this false, but the claim form has no point "
            f"evaluation against the function, so the symbolic disproof "
            f"has no executed witness, and a falsification needs one; the "
            f"verdict stays unknown").lstrip("; ")
        return falsified
    seq_names = [n for n in deps["names"]
                 if facts.param_kinds.get(n) in SEQUENCE_KINDS]
    result = C.corroborate_disproof(deps["evaluate"], deps["names"],
                                    sample=deps["sample"], admits=deps["admits"],
                                    witness=_sequence_witness(proof.witness,
                                                              seq_names))
    if result.point is not None:
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "reproduced"}
        pt = _fmt_point(result.point, deps["names"])
        falsified.counterexample = pt or falsified.counterexample
        if falsified.stratum is None:
            # a symbolic disproof plus a reproduced executed witness is
            # the evidence bar for indicting the mathematics itself
            falsified.stratum = {"mathematics": "unsound",
                                 "blame": "claim", "witness": pt}
        if result.seeded and \
                proof.meta.get("mathema.derive_route") != "brute_force":
            # a seeded reproduction means the analytical witness guided
            # an empirical search, so the route names that. The one
            # mechanism this is wrong for is the exhaustive sweep: its
            # witness is not a seed, it is an executed call to the real
            # function at a point the domain admits, so the gate has
            # nothing to add and relabelling it would report weaker
            # evidence than was actually obtained.
            falsified.route = "probe:semi_analytical"
        return falsified
    exact_point, compared = _exact_witness_violation(
        cj, fn, facts, cj_domain, bound_funcs, assum, proof, seq_names)
    if exact_point is not None:
        pt = _fmt_point(exact_point, deps["names"])
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "reproduced"}
        falsified.counterexample = pt or falsified.counterexample
        if falsified.stratum is None:
            falsified.stratum = {"mathematics": "unsound",
                                 "blame": "claim", "witness": pt}
        falsified.note = (
            f"{falsified.note}; reproduced exactly at derive's witness: "
            f"the executed code violates the relation there by less than "
            f"the default tolerance ({_DEFAULT_ORDERING_SLACK:g}) the probe "
            f"route allows, and compared exactly it fails").lstrip("; ")
        return falsified
    falsified.verdict = "unknown"
    falsified.meta = {**(falsified.meta or {}),
                      "mathema.corroboration": "uncorroborated"}
    falsified.counterexample = None
    if compared and proof.meta.get("mathema.exact_disproof"):
        # derive's difference is exactly nonzero at the witness, and the
        # code, executed there and compared exactly, agrees with the
        # claim: floating point rounded the difference away
        falsified.meta["mathema.corroboration_reason"] = \
            C.EXACT_ARITHMETIC_ONLY
        falsified.note = (
            f"{falsified.note}; uncorroborated disproof: "
            f"{C.EXACT_ARITHMETIC_ONLY_NOTE} (compared exactly at derive's "
            f"witness, the executed values are equal), so the verdict "
            f"stays unknown").lstrip("; ")
        return falsified
    falsified.note = (
        f"{falsified.note}; uncorroborated disproof: the derive route "
        f"reported this false but no in-domain counterexample reproduced "
        f"against the function ({result.checked} points checked), a "
        f"symbolic disproof nothing reproduces indicates an engine bug "
        f"worth reporting, so the verdict stays unknown")
    return falsified


def companion_name(parent_name: str, descriptor: str = "float") -> str:
    """The name of a claim's computation companion: `<parent
    name>[float]`, or `<parent name>[complex]` for a claim over C,
    with any runtime type after it (`<parent name>[float,
    pandas.Series]`)."""
    return f"{parent_name}[{descriptor}]"


def companion_representation(cj_domain: "dict | None",
                             facts=None) -> tuple:
    """Intent:
        The number representation a claim's companion computes in,
        as `(descriptor, representation, its name)`: complex128
        (`("complex", PY_COMPLEX128, "complex128")`) when the claim's
        domain binds a coordinate in C, else float64 (`("float",
        PY_FLOAT64, "float64")`). The descriptor goes on to name each
        runtime type other than a list that a parameter of `facts` is
        realised as (`"float, pandas.Series"`).
    """
    from .probing import _bound_is_complex
    from .representations import PY_COMPLEX128, PY_FLOAT64
    from .runtime_types import descriptor_names
    runtime = "".join(f", {name}" for name in descriptor_names(facts))
    if any(_bound_is_complex(b) for b in (cj_domain or {}).values()):
        return "complex" + runtime, PY_COMPLEX128, "complex128"
    return "float" + runtime, PY_FLOAT64, "float64"


def companion_descriptor(name: str) -> tuple[str, ...]:
    """The computation descriptor a companion's name carries in its
    last bracket, one entry per comma-separated item: `law[float]`
    gives `("float",)`, and a descriptor naming more of the computation
    (`law[float, cpython3.12]`) gives each part. A name with no
    trailing bracket gives `()`.

    Only a companion row's name holds a descriptor; whether a row is a
    companion is read from its meta (`mathema.companion_of`), since a
    parameter target (`is_overflow_safe[x]`) or a conjunct index has
    the same shape.
    """
    if not name.endswith("]") or "[" not in name:
        return ()
    inside = name[name.rindex("[") + 1:-1]
    return tuple(part.strip() for part in inside.split(",") if part.strip())


def _reach_text(names, cj_domain, resolved, reach) -> str:
    """Intent:
        How far the float companion ran along the claim's unbounded
        directions, in words, or an empty string when every coordinate
        is bounded (P8). `resolved` is the claim's resolved
        pseudo-infinity, stated as its `let` binding; without one the
        directions ran to the number representation's reach.
    """
    from .domain import unbounded_directions
    unbounded = unbounded_directions(names, cj_domain)
    if not unbounded:
        return ""
    who = ", ".join(unbounded)
    if resolved is not None:
        return f"unbounded directions ({who}) run to {resolved.render()}"
    return (f"unbounded directions ({who}) run to magnitude "
            f"{reach[1]:g}, sampled log-uniformly (no |inf| declared)")


def _same_no_value(lv, rv) -> bool:
    """Intent:
        Whether two sides that have no value agree: only when both are
        the same infinity (`probing.same_infinity`), one extended-real
        point. A NaN never agrees, not even with another NaN, and an
        infinity never agrees with a value or the opposite infinity.
    """
    from .probing import same_infinity
    return same_infinity(lv, rv)


def _finite_arguments(args, kwargs) -> bool:
    """Whether every argument of a call is a finite, non-missing value
    (a number, or a list or tuple of them); a non-numeric argument
    counts as finite."""
    from .domain import is_missing
    from .probing import holds_inf, holds_nan
    return not any(is_missing(v) or holds_nan(v) or holds_inf(v)
                   for v in (*args, *kwargs.values()))


def _float_companion(parent, cj, fn, facts, cj_domain, bound_funcs,
                     assum=(), budget=None) -> "Probe | None":
    """Intent:
        The computation claim a derive proof spawns. `parent` is proven in
        exact arithmetic, which is all a derive `proven` says; the
        companion `<name>[float]` is the same relation executed against
        the REAL code in float: at every corner of the declared domain and
        at sampled interior points, unbounded directions running to the
        claim's resolved pseudo-infinity (`records.operational_range`:
        claim, function level or `MATHEMA_PSEUDO_INFINITY`) when one
        applies and to the number representation's maximum
        (`_sampling.representation_reach`, sampled log-uniformly)
        otherwise. A raise, a NaN, or an inf or a precision loss where the
        relation fails on the executed values falsifies it with that point
        as the witness; otherwise it holds, over the points it executed.

    Notes:
        `None` when the claim has no point evaluation against the code
        (a calculus form, a law that won't compile): a limit or an
        integral is a claim about the mathematics only. The companion
        carries the parent's surface, so it gates exactly when the
        parent does. A sweep the wall-clock cap cuts short is
        `unknown`, naming the point that was executing. `budget`, when
        given, is the total number of points drawn, corners included
        (the caller's trials); otherwise every corner plus the
        corroboration budget of interior points.
    """
    from . import corroboration as C
    from ._sampling import representation_reach
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .records import operational_infinity, operational_range
    resolved = operational_infinity(cj)
    cap = operational_range(cj)
    descriptor, representation, representation_word = \
        companion_representation(cj_domain, facts)
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum,
                            cap=cap, reach=representation.max_magnitude,
                            sequences=True)
    if deps is None:
        return None
    name = companion_name(parent.name, descriptor)
    top = float(representation.max_magnitude or representation_reach())
    reach = cap if cap is not None else (-top, top)
    reach_text = _reach_text(deps["names"], cj_domain, resolved, reach)
    interior = (C._CORROBORATION_BUDGET if budget is None
                else max(0, int(budget) - len(deps["corners"])))
    progress = C.StabilitySweep()
    try:
        sweep = _with_timeout(
            lambda: C.sweep_stability(deps["probe_finite"], deps["names"],
                                      sample=deps["sample"],
                                      corners=deps["corners"],
                                      admits=deps["admits"],
                                      budget=interior, progress=progress),
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        at = (_fmt_point(progress.in_flight, deps["names"])
              if progress.in_flight else "")
        return Probe(
            name, parent.statement, "unknown", route="probe",
            n=progress.checked,
            note=f"the computation of {parent.name} in "
                 f"{representation_word}; "
                 f"the sweep hit the {FAST_TIMEOUT_SECONDS}s wall-clock cap"
                 + (f" executing {at}" if at else "")
                 + (f"; {reach_text}" if reach_text else ""),
            meta={"mathema.timeout": "fast"})
    what = (f"the computation of {parent.name} in {representation_word}, "
            f"executed at {sweep.checked} points (every domain corner, then sampled "
            f"interior points)"
            + (f"; {reach_text}" if reach_text else ""))
    if sweep.fragile_point is not None:
        pt = _fmt_point(sweep.fragile_point, deps["names"])
        remedy = ("narrow the domain, "
                  + ("" if not reach_text else
                     "lower the |inf| binding, " if cap is not None else
                     "declare an |inf| for the unbounded directions, ")
                  + "fix the code, or state the claim with "
                    "route derive:math_only")
        # a covered call's computation region, when the compendium
        # states one and the failing point lies outside it
        from .compendium import computation_diagnosis
        covered = computation_diagnosis(fn, facts, sweep.fragile_point)
        return Probe(
            name, parent.statement, "falsified", route="probe",
            n=sweep.checked, counterexample=pt, note=what,
            sketch=f"{parent.name} is mathematically proven, but its "
                   f"computation fails at {pt}: {sweep.detail}; "
                   + (f"{covered}; " if covered else "")
                   + f"{remedy}",
            # the proof that coexists with the executed break is the
            # evidence that the mathematics is sound and the code is not
            stratum={"mathematics": "sound", "blame": "implementation",
                     "cause": "implementation:numerical-instability",
                     "representation": representation.tag, "witness": pt})
    if sweep.checked == 0:
        return Probe(name, parent.statement, "skipped", route="probe",
                     note=f"{what}; no in-domain point satisfied the "
                          f"claim's premises, so nothing was executed")
    return Probe(name, parent.statement, "holds", route="probe",
                 n=sweep.checked, note=what)
