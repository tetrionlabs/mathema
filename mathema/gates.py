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
                     exact=False, holes=None):
    """Intent:
        Build the injected dependencies the corroboration engine needs
        for THIS claim: `evaluate(point)` decides the original claim's
        relation at a concrete point by calling the real `fn` (True =
        holds, False = a genuine counterexample, None = can't tell);
        `probe_finite(point)` returns a computation-failure detail
        (a raise, a NaN, an inf or a deviation past a magnitude-scaled
        tolerance where the relation fails), None where the code
        agrees, or a `corroboration.Undecided` reason where the claim's
        own side has no value, exact or float; `admits(point)` is
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
        every element the bound admits; a matrix coordinate (a claim
        space of two axes) draws a list of rows, and a table coordinate
        a dict of equal-length columns. `holes`, `{param: [value,
        ...]}`, are the hole values a container's slots admit: a draw
        carries them at `_floor.HOLE_RATE`, and `admits` accepts them. A
        coordinate whose domain is integer-only reaches `fn` as an int,
        corners included.
    """
    import math
    from .domain import (_as_int_if_whole, bound_to_sympy_set,
                         domain_contains, operational_domain)
    from .probing import (DEFAULT_RELATIVE_TOLERANCE, ComplexResult,
                          _bound_is_complex, _fmt_value, _is_matrix_value,
                          _synth, complex_is_a_raise,
                          ExecutedMissing, LastCall, classified,
                          holds_inf, holds_nan, inputs_missing,
                          is_complex_value, missing_class,
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
    # kind the body suggested; a table stays a table, its space bounding
    # every column
    seq_names |= {p for p, k in kinds.items()
                  if k != "table" and _shapes.dims_of(cj_domain.get(p))}
    if seq_names and not sequences:
        return None
    # a table coordinate is a container too when list-valued points were
    # asked for: a dict of columns, each a sequence
    table_names = ({p for p, k in kinds.items() if k == "table"}
                   if sequences else set())
    mat_names = {p for p in seq_names
                 if len(getattr(cj_domain.get(p), "dims", ()) or ()) >= 2}
    hole_values = {p: list(v) for p, v in (holes or {}).items() if v}
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
    # the calls the function under test (or a bound function) made at
    # the current point, for the executed missing inputs
    f_calls = LastCall()
    from .probing import parameter_defaults
    f_calls.defaults = parameter_defaults(fn)
    executed = ExecutedMissing()
    from .probing import signature_defaults
    executed.defaults = signature_defaults(fn)
    from ._missing_words import DrawTally
    tally = DrawTally()
    from ._missing_words import declared_optional_return
    declared_return = declared_optional_return(fn)

    def _tag(callee, label):
        # a complex result under a real claim counts as a raise too
        complex_raises = complex_is_a_raise(callee, cj_domain)
        from .conjecture import _is_under_test
        under_test = label == "f" or _is_under_test(callee, fn)

        def _wrapped(*a, **kw):
            try:
                out = callee(*a, **kw)
            except Exception as exc:
                calls_raised[0] = type(exc).__name__
                if under_test:
                    f_calls.calls.append(("raised", type(exc).__name__, a, kw))
                raise
            if under_test:
                f_calls.calls.append(("returned", out, a, kw))
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
        f_calls.reset()
        executed.last_classified = False

    from .conjecture import _lists_sentinel

    def _admitted(point) -> bool:
        # a hole or absence the claim does not list as its own point
        return any(inputs_missing([v]) and not _lists_sentinel(cj_domain.get(p))
                   for p, v in point.items())

    def _record_returned_none(point, lv, rv):
        # a None f returned from present inputs: filed for the absence
        # policy line, as declared by the return type or as introduced
        # against it
        if lv is None or rv is None:
            if declared_return:
                executed.returned_absent(dict(point), declared_return)
            else:
                from .policy import record_introduced
                record_introduced(dict(point))

    def _classify(point, raised, sides=()):
        # at a missing input, a raise or a missing output is classified
        # into the executed missing inputs and not judged; so is every
        # call at a hole or absence the claim only admits, which the
        # policy lines judge. True when it was. A law that calls no
        # function has its own sides as output
        at_missing = _admitted(point) or classified(
            point.values(), f_calls.outputs() or list(sides), raised)
        f_calls.record(executed, point)
        if at_missing:
            executed.classified += 1
            executed.last_classified = True
        return at_missing

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
    as_arrays = bool(seq_names or table_names) and _numpy() is not None
    fn_call = calling(fn, facts)
    if as_arrays:
        fn_call = law_callable(fn_call)
        bound_funcs = {name: _bound_for_arrays(v)
                       for name, v in bound_funcs.items()}
    from .conjecture import _fill_value, _refill_caller
    executed.refill_at = _refill_caller(fn_call)
    executed.fills = {p: fill for p in kinds
                      if (fill := _fill_value(cj_domain.get(p))) is not None}
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

    from . import _floor
    from .conjecture import _table_columns
    table_columns = {p: _table_columns(p, cj, facts) for p in table_names}
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
                    as_array(v) if as_arrays and n in seq_names | table_names
                    and isinstance(v, (list, tuple, dict)) else v)
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
            try:
                return lv == rv or (both_finite and abs(lv - rv) <= tol)
            except OverflowError:
                from fractions import Fraction
                return lv == rv or (both_finite and abs(
                    Fraction(lv) - Fraction(rv)) <= Fraction(tol))
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
            try:
                return (lv <= rv + tol if rel == "<=" else
                        lv >= rv - tol if rel == ">=" else
                        lv < rv if rel == "<" else
                        lv > rv if rel == ">" else None)
            except OverflowError:
                # an integer beyond float range: compare exactly
                from fractions import Fraction
                lv, rv, tol = Fraction(lv), Fraction(rv), Fraction(tol)
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
        # computed from inputs that are not missing is no value and
        # fails (a missing input was compared by kind before this)
        if holds_nan(lv) or holds_nan(rv):
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
            # rule), so it reproduces a disproof, and so does a claim
            # side with no value there (no real value, an index outside
            # a sequence it reads, a division by zero), except at a
            # missing input, where it is classified; any other plumbing
            # raise stays inconclusive
            if _classify(point, bool(calls_raised[0])):
                return None
            from .conjecture import claim_side_has_no_value
            return False if (calls_raised[0] or claim_side_has_no_value(e)
                             or isinstance(e, (IndexError, ZeroDivisionError))) \
                else None
        if _classify(point, False, (lv, rv)):
            return None
        if calls_nonfinite[0] is not None:
            # a nan or an infinity the code returned for finite inputs
            # is no value: against a value every relation fails. Two
            # sides overflowing toward the same infinity are one
            # extended-real point and agree, as equal sides, unless a
            # side read exactly is finite; a NaN is the absence of a
            # value and agrees with nothing
            if _same_no_value(lv, rv) and not _finite_exactly(point):
                return cj.relation in ("==", "~=", "<=", ">=")
            return False
        if not inputs_missing(point.values()) \
                and "absent" in (missing_class(lv), missing_class(rv)):
            # a None from present inputs is the absence policy line's
            # fact; absence compares as absence (None agrees with None
            # under == and ~=, and fails against a value, under != and
            # under an ordering)
            from ._missing_words import absence_agrees
            _record_returned_none(point, lv, rv)
            if absence_agrees(lv, rv, cj.relation):
                return True
            if declared_return and (lv is None or rv is None):
                return None
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
        # values proves nothing. A NaN computed from inputs that are not
        # missing, a scalar or an element of an array or list, is no
        # value and fails every relation, `!=` included: it agrees with
        # nothing, another NaN included (the no-value rule; a missing
        # input was compared by kind before this)
        if holds_nan(lv) or holds_nan(rv):
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

    # the executed missing inputs both evaluators record, read by
    # the routes that build a record from this kit
    evaluate.executed = executed  # type: ignore[attr-defined]
    evaluate.drawn = tally  # type: ignore[attr-defined]

    def _finite_exactly(point) -> bool:
        # two float sides at the same infinity stand for a finite value
        # when a side read exactly is finite: the code overflowed
        from ._exact_side import some_side_is_finite
        saved = (calls_raised[0], calls_nonfinite[0])
        held = some_side_is_finite(code_l, code_r,
                                   {**base_env, **_typed(point)},
                                   {"f": fn_call, **(bound_funcs or {})})
        calls_raised[0], calls_nonfinite[0] = saved
        return held

    def _exact_decision(point, tol) -> "bool | None":
        # the claim's sides read exactly, the function's results as the
        # exact values it returned (`_exact_side`): whether the relation
        # holds within `tol` there, None when the sides cannot be
        # computed exactly
        from ._exact_side import exact_sides
        env = {**base_env, **_typed(point)}
        exact = exact_sides(code_l, code_r, env,
                            {"f": fn_call, **(bound_funcs or {})})
        _reset()
        if exact is None:
            return None
        return relation_holds_elementwise(
            exact[0], exact[1], cj.relation, tol,
            exact_inequality=cj.tolerance is None, rel_tol=0.0)

    def _exact_holds(point, tol) -> bool:
        return _exact_decision(point, tol) is True

    def probe_finite(point):
        tally.add(point)
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
            # failure (a raise at a missing input is classified), and so
            # is a claim side with no value (no real value, an index
            # outside a sequence it reads, a division by zero); the
            # law's own plumbing failing otherwise says nothing about
            # the code, and is no agreement either
            if _classify(point, bool(calls_raised[0])):
                return None
            from .conjecture import claim_side_has_no_value
            if calls_raised[0]:
                return f"the computation raises {calls_raised[0]} here"
            if calls_nonfinite[0]:
                # the code gave no value at a finite input, whatever the
                # claim's own float side does there
                return (f"{calls_nonfinite[0]}, and an infinity or a nan "
                        f"for a finite input is no value")
            if isinstance(e, (IndexError, ZeroDivisionError)):
                return (f"the claim's own expression raises "
                        f"{type(e).__name__} here ({e})")
            if claim_side_has_no_value(e):
                return f"the claim's own side has no real value here ({e})"
            # the claim's own side read exactly, the code's results as
            # the values it returned; else the point is undecided
            from ._exact_side import exact_sides
            from .corroboration import Undecided
            _reset()
            exact = exact_sides(code_l, code_r,
                                {**base_env, **_typed(point)},
                                {"f": fn_call, **(bound_funcs or {})})
            _reset()
            held = None if exact is None else relation_holds_elementwise(
                exact[0], exact[1], cj.relation, slack,
                exact_inequality=cj.tolerance is None,
                rel_tol=DEFAULT_RELATIVE_TOLERANCE
                if cj.tolerance is None else 0.0)
            if held is None:
                return Undecided(f"the claim's own side raised "
                                 f"{type(e).__name__} ({e})")
            if held:
                return None
            return ("the relation fails on the executed values, the "
                    "claim's own side read exactly")
        if _classify(point, False, (lv, rv)):
            return None
        if not inputs_missing(point.values()) \
                and "absent" in (missing_class(lv), missing_class(rv)):
            from ._missing_words import absence_agrees, absence_words
            _record_returned_none(point, lv, rv)
            if absence_agrees(lv, rv, cj.relation) or declared_return:
                return None
            return (f"the computation returns None here "
                    f"({_fmt_value(lv)} vs {_fmt_value(rv)}), "
                    f"{absence_words(lv, rv, cj.relation)}")
        if inputs_missing(point.values()) and (holds_nan(lv) or holds_nan(rv)
                                               or None in (lv, rv)):
            # the code returned a value at a missing input and the law's
            # side holds no value there
            if relation_holds_elementwise(
                    lv, rv, cj.relation, slack,
                    exact_inequality=cj.tolerance is None, rel_tol=0.0) is False:
                return (f"the relation fails at a missing input "
                        f"({_fmt_value(lv)} {cj.relation} {_fmt_value(rv)})")
            return None
        if calls_nonfinite[0] is not None:
            # no value at a finite input: an overflow, a pole, a nan.
            # Two sides at the same infinity are one extended-real
            # point and agree, as equal sides; a NaN, or an infinity
            # against a value, is a failure
            if _same_no_value(lv, rv) and cj.relation in ("==", "~=",
                                                          "<=", ">=") \
                    and not _finite_exactly(point):
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
            scaled = slack + DEFAULT_RELATIVE_TOLERANCE * max(abs(lv), abs(rv))
            if _relation_holds(lv, rv, scaled):
                return None
            return (f"the relation fails on the executed values "
                    f"({_fmt_value(complex(lv))} {cj.relation} "
                    f"{_fmt_value(complex(rv))}), past the magnitude-scaled "
                    f"tolerance")
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
            scaled = slack + DEFAULT_RELATIVE_TOLERANCE * size
            # the claim read exactly decides where it can be: a float
            # claim side that rounds the way the code does would agree
            # with it and hide the code's error
            exact = _exact_decision(point, scaled)
            if exact is True:
                return None
            if exact is False:
                return ("the relation fails on the executed values, the "
                        "claim's own side read exactly")
            held = _array_relation(lv, rv, scaled, point)
            if held is None or held:
                return None
            return (f"the relation fails on the executed values ({lv!r} "
                    f"{cj.relation} {rv!r}), past the magnitude-scaled "
                    f"tolerance")
        if any(isinstance(v, float) and v != v for v in (lv, rv)):
            return ("the computation returns NaN here"
                    if calls_nonfinite[0] else None)
        if not (_real(lv) and _real(rv)):
            return None
        overflowed = any(abs(v) == float("inf") for v in (lv, rv))
        if overflowed and not calls_nonfinite[0]:
            return None
        magnitude = max(abs(lv) if not overflowed else 0.0,
                        abs(rv) if not overflowed else 0.0)
        try:
            scaled = slack + DEFAULT_RELATIVE_TOLERANCE * magnitude
        except OverflowError:
            # an integer beyond float range: the tolerance is exact too
            from fractions import Fraction
            scaled = Fraction(slack) \
                + Fraction(DEFAULT_RELATIVE_TOLERANCE) * magnitude
        exact = None if overflowed else _exact_decision(point, scaled)
        if exact is True:
            return None
        if exact is False:
            return (f"the relation fails on the executed values ({lv!r} "
                    f"{cj.relation} {rv!r} in float), the claim's own side "
                    f"read exactly")
        if _relation_holds(lv, rv, scaled):
            return None
        if overflowed:
            return (f"the computation overflows to inf here, and the "
                    f"relation fails on the executed values ({lv!r} "
                    f"{cj.relation} {rv!r})")
        return (f"the relation fails on the executed values ({lv!r} "
                f"{cj.relation} {rv!r}), past the magnitude-scaled "
                f"tolerance")

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
        if name in mat_names and name not in planned:
            # a matrix: rows of element draws, square when its two axes
            # share a name
            n_rows, n_cols = _floor.sizes(cj_domain.get(name), rng, (2, 4), ndim=2)
            rows = [[_synth("float", rng, b) for _ in range(n_cols)]
                    for _ in range(n_rows)]
            return _floor.gapped_rows(rows, hole_values.get(name, []), rng, 0)[0]
        if name in seq_names:
            # a sequence's declared bound is per element
            if name in planned:
                v = _planned_draw(name, rng, b)
                if resolver.shapes[name].ndim == 1:
                    return _floor.gapped(v, hole_values.get(name, []), rng, 0)[0]
                return _floor.gapped_rows(v, hole_values.get(name, []), rng, 0)[0]
            (length,) = _floor.sizes(cj_domain.get(name), rng)
            return _floor.gapped(_synth("sequence", rng, b, length=length),
                                 hole_values.get(name, []), rng, 0)[0]
        if name in table_names:
            # a table: one equal-length column per name the claim or the
            # body reads
            (length,) = _floor.sizes(cj_domain.get(name), rng)
            from .conjecture import _column_bound
            return {c: _floor.gapped(_synth("sequence", rng,
                                            _column_bound(cj_domain.get(f"{name}.{c}"), b),
                                            length=length),
                                     hole_values.get(name, []), rng, 0)[0]
                    for c in table_columns[name]}
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

    def column_bound(name, column):
        # the element domain a path binding (`for df.w in [0, 1]^n`)
        # states for one column of a table, None when it states none
        bound = cj_domain.get(f"{name}.{column}")
        if bound is None:
            return None
        from .conjecture import _column_bound
        return _column_bound(bound, None)

    def _element_ok(n, e, bound):
        # an element inside the declared per-element bound, or a hole
        # the slot admits
        if hole_values.get(n) and missing_class(e) is not None:
            return True
        return isinstance(e, (int, float)) and domain_contains(e, bound)

    def admits(point):
        for n in seq_names | table_names:
            # a sequence coordinate is a container of the shape its
            # binding states (a matrix a list of rows, a table a dict of
            # columns), each element inside the declared per-element
            # bound or a hole the slot admits
            v = point.get(n)
            bound = cj_domain.get(n)
            dims = _shapes.dims_of(bound)
            if dims:
                shape = _shapes.observed_shape(v)
                if shape is None or not _shapes.fits(shape, dims):
                    return False
                elements = list(_shapes.leaves(v))
            elif n in table_names:
                if not isinstance(v, dict):
                    return False
                # a column its own binding bounds holds its elements there
                for c, col in v.items():
                    col_bound = column_bound(n, c)
                    if col_bound is not None and not all(
                            _element_ok(n, e, col_bound) for e in col):
                        return False
                elements = [e for col in v.values() for e in col]
            elif isinstance(v, (list, tuple)):
                elements = list(v)
            else:
                return False
            if bound is not None and not all(_element_ok(n, e, bound)
                                             for e in elements):
                return False
        for n in names:
            bound = cj_domain.get(n)
            v = point.get(n)
            if bound is None or v is None or n in seq_names | table_names:
                continue
            if n in hole_values and missing_class(v) is not None:
                # a missing value the parameter's completed domain admits
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
        # per-element edge, a planned coordinate nested to its axes, a
        # matrix's a small one, a table's short columns
        if name in planned:
            return resolver.synth(name, corner_sizes, lambda: value,
                                  _random.Random(0))
        if name in mat_names:
            dims = tuple(getattr(cj_domain.get(name), "dims", ()) or ())
            n_cols = 2 if len(set(dims[:2])) == 1 else 3
            return [[value] * n_cols for _ in range(2)]
        if name in table_names:
            return {c: [_column_end(name, c, value)] * 3 for c in table_columns[name]}
        return [value] * 3 if name in seq_names else value

    def _column_end(name, column, value):
        # a column its own binding bounds takes that binding's edge on the
        # side the table's corner takes
        bound = column_bound(name, column)
        ends = _ends(bound) if bound is not None else None
        if ends is None:
            return value
        which = 0 if value == edges[name][0] else 1
        end = ends[which]
        if end != end or math.isinf(end):
            return value
        if not domain_contains(end, bound):
            end = math.nextafter(end, math.inf if which == 0 else -math.inf)
        return end

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
    for n in names:
        # -0.0 is a float input wherever 0 is in the domain, and code
        # can tell it from 0.0 (atan2, copysign, 1 / x)
        if n in language_names or n in complex_names:
            continue
        lo, hi = edges[n][0], edges[n][-1]
        integral = getattr(cj_domain.get(n), "base_type", None) in ("Z", "N")
        if (isinstance(lo, float) and isinstance(hi, float) and not integral
                and lo <= 0.0 <= hi and domain_contains(-0.0, cj_domain.get(n))
                if cj_domain.get(n) is not None else False):
            edges[n] = [*edges[n], -0.0]
        # a closed infinite end includes the point (ruling E2): the
        # computation executes x = inf there, unless a declared
        # operational infinity bounds the computation
        bound = cj_domain.get(n)
        if cap is None and bound is not None and not integral:
            pieces = getattr(bound, "pieces", None) or (
                (bound,) if isinstance(bound, tuple) else ())
            for piece in pieces:
                if not (isinstance(piece, tuple) and not isinstance(piece, frozenset)
                        and len(piece) == 2):
                    continue
                for end, closed in ((piece[0], getattr(piece, "closed_lo", True)),
                                    (piece[1], getattr(piece, "closed_hi", True))):
                    if isinstance(end, float) and math.isinf(end) and closed \
                            and end not in edges[n]:
                        edges[n] = [*edges[n], end]
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
    def exact_at(point):
        # the claim's sides at a point of exact numbers, the function and
        # the bound functions run on those numbers themselves
        from ._exact_side import exact_sides
        _reset()
        try:
            return exact_sides(code_l, code_r, {**base_env, **point},
                               {"f": fn_call, **(bound_funcs or {})},
                               exact_calls=True)
        finally:
            _reset()

    evaluate.exact_at = exact_at  # type: ignore[attr-defined]
    return dict(evaluate=evaluate, probe_finite=probe_finite, admits=admits,
                sample=sample, corners=corners, names=names)


def _fmt_point(point, names):
    """A point rendered for a counterexample string, a float coordinate
    at full precision (`probing._fmt_coordinate`), discrete/string
    coords (a string domain member) as-is."""
    parts = []
    for n in names:
        if n not in point:
            continue
        v = point[n]
        from .probing import _fmt_coordinate
        if isinstance(v, str):
            from .probing import spell_text
            parts.append(f"{n} = {spell_text(v)}")
            continue
        capped = _shapes.witness_text(v)
        if capped is not None:
            # a large vector or matrix prints its shape, a first row and
            # a count; the full value rides in the counterexample's
            # arguments
            parts.append(f"{n} = {capped}")
            continue
        parts.append(f"{n} = {_fmt_coordinate(v)}" if isinstance(v, float)
                     else f"{n} = {v!r}")
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
        `~=` is `abs(lhs - rhs) <= ε`, compared exactly as that ordering
        (ε the 1e-9 default). A coordinate
        derive's witness leaves free (the difference does not depend on
        it) is drawn from its declared bound with a fixed seed, a few
        draws at most, and the first admissible completion is the point
        compared.
    """
    import random
    from . import corroboration as C
    if cj.relation == "~=" and cj.tolerance is None and cj.rhs:
        from dataclasses import replace
        cj = replace(cj, lhs=f"abs(({cj.lhs}) - ({cj.rhs}))", relation="<=",
                     rhs="ε")
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


def _certified_point_witness(cj, deps, proof, cj_domain) -> "str | None":
    """Intent:
        The witness text when derive's witness, read as exact numbers
        (`_exact_witness.exact_number`: a rational, or an algebraic
        number with a verified isolating interval), lies in the claim's
        domain and the code run on those numbers makes the claim false,
        decided by the exact sign of the sides' difference; else None.
        Independent of the solver that found the witness: only the
        witness's value is taken from it.
    """
    from ._exact_witness import (Undecided, exact_number, in_bound,
                                 relation_fails)
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    witness = proof.witness or {}
    if cj.relation not in ("==", "!=", "<=", ">=", "<", ">") \
            or cj.tolerance is not None:
        return None
    names = list(deps["names"])
    if not names or any(n not in witness for n in names):
        return None

    def check():
        point = {}
        for n in names:
            value = exact_number(witness[n], FAST_TIMEOUT_SECONDS)
            bound = cj_domain.get(n)
            if bound is not None and not in_bound(value, bound):
                return None
            point[n] = value
        exact_at = getattr(deps["evaluate"], "exact_at", None)
        if exact_at is None:
            return None
        sides = exact_at(point)
        if sides is None or not relation_fails(sides[0], sides[1],
                                               cj.relation):
            return None
        return ", ".join(f"{n} = {witness[n]}" for n in names)
    try:
        return _with_timeout(check, FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    except (Undecided, ArithmeticError, TypeError, ValueError):
        return None


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
    if proof.meta.get("mathema.witness_certified") and falsified.counterexample:
        # the raise guard holds in the domain by certified interval
        # arithmetic while every float call returns: the mathematics is
        # false, the computation holds
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "certified"}
        falsified.note = (
            f"{falsified.note}; {proof.meta['mathema.witness_certified']}, "
            f"while every float call there returns a value").lstrip("; ")
        return falsified
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
            f"{falsified.note}; derive found this claim false, but there "
            f"is no single input to run it at, so no run of the code "
            f"confirms it; a falsification needs one, so the verdict "
            f"stays unknown").lstrip("; ")
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
        detail = deps["probe_finite"](result.point)
        if pt and isinstance(detail, str) and \
                detail.startswith("the claim's own"):
            # the witness carries why the claim fails there: its own
            # side has no value (no real value, or an expression of it
            # raising, named first)
            reason = (detail if "no real value" in detail else
                      f"{detail}, so the claim's own side has no real "
                      f"value here")
            falsified.counterexample = (
                f"{pt}: {reason}; narrow the claim's domain to where every "
                f"side of it is real")
        elif pt and isinstance(detail, str) and \
                detail.startswith("the computation returns None"):
            # the witness says what the code gave back: an absence
            falsified.counterexample = f"{pt}: {detail}"
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
    certified = (_certified_point_witness(cj, deps, proof, cj_domain)
                 if not assum else None)
    if certified is not None:
        falsified.meta = {**(falsified.meta or {}),
                          "mathema.corroboration": "reproduced"}
        falsified.counterexample = certified
        if falsified.stratum is None:
            falsified.stratum = {"mathematics": "unsound",
                                 "blame": "claim", "witness": certified}
        falsified.note = (
            f"{falsified.note}; reproduced exactly at derive's witness: the "
            f"code, run on the witness's exact value, makes the claim false "
            f"there, while every float draw passes (the computation holds "
            f"within its tolerance)").lstrip("; ")
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
            f"{falsified.note}; derive found this claim false, but "
            f"{C.EXACT_ARITHMETIC_ONLY_NOTE} (run at derive's "
            f"counterexample, the two sides come out equal), so the "
            f"verdict stays unknown").lstrip("; ")
        return falsified
    falsified.note = (
        f"{falsified.note}; derive found this claim false, but no run of "
        f"the code inside the domain reproduced it ({result.checked} points "
        f"checked); a disproof nothing reproduces is probably a mathema "
        f"bug worth reporting, so the verdict stays unknown")
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


def _listed_points(names, cj_domain) -> "list | None":
    """Every point of a claim whose coordinates all range over finite
    sets, each listed missing value realised as the value it stands for;
    None when a coordinate is not a finite set."""
    import itertools

    from .domain import (_as_domain, _is_enumerated, _member_sort_key, is_sentinel,
                         realise_sentinel)
    values = []
    for n in names:
        bound = (cj_domain or {}).get(n)
        if bound is None:
            return None
        dom = _as_domain(bound)
        if not _is_enumerated(dom) or dom.dims:
            return None
        members = sorted({v for piece in dom.pieces for v in piece},
                         key=_member_sort_key)
        realised = []
        for v in members:
            realised += realise_sentinel(v) if is_sentinel(v) else [v]
        values.append(realised)
    return [dict(zip(names, combo)) for combo in itertools.product(*values)]


def _listed_words(points, names) -> str:
    """`both listed points, 0.25 and None`, `the only listed point,
    0.25`, `the 3 listed points, 1, 2 and 3`."""
    from ._missing_words import point_shown, value_shown
    shown = [value_shown(pt[names[0]]) if len(names) == 1 else point_shown(pt)
             for pt in points]
    if len(shown) == 1:
        return f"the only listed point, {shown[0]}"
    listing = _and_words(", ".join(shown))
    if len(shown) == 2:
        return f"both listed points, {listing}"
    return f"the {len(shown)} listed points, {listing}"


def _and_words(words: str) -> str:
    """`None, nan` as `None and nan`, a list of words said aloud."""
    parts = [w.strip() for w in words.split(",") if w.strip()]
    if len(parts) <= 1:
        return words
    return ", ".join(parts[:-1]) + " and " + parts[-1]


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


def _exact_claim_at(cj, fn, facts, point: dict, assum) -> "bool | None":
    """Intent:
        Whether the claim holds at one executed point in exact
        arithmetic: the derive route run over the domain pinned to that
        point, each coordinate the decimal reading of the float that
        was executed (`repr`, as a declared bound is read). True or False when it decides, None when it
        does not (a sequence or non-numeric coordinate, a bound
        function, a claim with no relation, an undecided or timed-out
        attempt).
    """
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .symbolic import try_prove
    if cj.funcs or cj.relation not in ("==", "!=", "<=", ">=", "<", ">") \
            or cj.tolerance is not None:
        return None
    pinned: dict = {}
    for name, value in point.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or value != value or value in (float("inf"), float("-inf")):
            return None
        # the decimal reading of the executed float, the same reading
        # the derive route gives a declared bound, so a domain corner
        # pins to the corner the proof quantified over
        exact = sympy.Rational(repr(float(value))) \
            if isinstance(value, float) else sympy.Integer(value)
        pinned[name] = (exact, exact)
    try:
        result = _with_timeout(
            lambda: try_prove(fn, facts, cj.lhs, cj.rhs or "0", cj.relation,
                              domain=pinned,
                              assumption=[tuple(a) for a in assum or ()]
                              or None),
            FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    except Exception:
        return None
    if result.status == "proven":
        return True
    if result.status == "disproven":
        return False
    return None


#: the wall-clock seconds a computation line may spend executing every
#: point of a finite domain, judged from a timed estimate of one call and
#: scaled with the trials the caller asked for
_SWEEP_SECONDS = 1.0
#: the trials a computation line makes over a finite domain too large or
#: too slow to sweep: its discontinuities first, then a seeded sample
_PARTIAL_POINTS = 2000


class _FinitePlan:
    """The points a computation line runs over a finite domain and the
    coverage its note states."""

    def __init__(self, points, sampled, coverage):
        self.points, self.sampled, self.coverage = points, sampled, coverage

    @property
    def targeted(self) -> bool:
        return bool(self.coverage.at_discontinuities)


def _finite_plan(cj, fn, facts, deps, cj_domain, corners, admits,
                 scale: float = 1.0):
    """Intent:
        The computation line's plan over a finite domain, or None when
        some parameter's domain is not finite: every admitted point
        when a timed estimate of one call fits `_SWEEP_SECONDS` (times
        `scale`); otherwise the corners, every point at a
        discontinuity (`_discontinuities`), then a seeded sample up to
        `_PARTIAL_POINTS` (times `scale`).
    """
    import time

    from . import _discontinuities as D
    from ._brute_force import BRUTE_FORCE_POINT_BUDGET, _sweep_grid
    names = list(deps["names"])
    grid = _sweep_grid(names, cj_domain, BRUTE_FORCE_POINT_BUDGET)
    if grid is None or not grid:
        return None
    points = [pt for pt in D.grid_points(names, grid) if admits(pt)]
    if not points:
        return None
    trial = points[::max(1, len(points) // 5)][:5]
    started = time.perf_counter()
    for pt in trial:
        try:
            deps["probe_finite"](pt)
        except Exception:
            pass
    per_call = (time.perf_counter() - started) / max(1, len(trial))
    asked = getattr(cj, "trials", None)
    if (asked is not None and len(points) <= asked) or \
            per_call * len(points) <= _SWEEP_SECONDS * scale:
        # the claim's own trials cover the domain, or the timed estimate
        # fits the budget: every point
        return _FinitePlan(points, 0, D.Coverage(total=len(points), full=True))
    found = D.discontinuities(cj, fn, facts)
    hits = D.on_grid(found, points)
    chosen = list(corners) + hits
    sampled = max(0, int(_PARTIAL_POINTS * scale) - len(chosen))
    return _FinitePlan(chosen, sampled, D.Coverage(
        total=len(points), at_discontinuities=len(hits),
        discontinuity_words=D.words_of(found), edge_cases=len(corners),
        random=sampled))


def _interval_discontinuities(cj, fn, facts, deps, cj_domain, corners):
    """Intent:
        `(points, coverage)` for a domain that is not finite: the points
        at a discontinuity of a single-parameter argument over that
        parameter's interval (each with its float neighbours), the
        other coordinates at the first corner; `([], None)` when there
        are none.
    """
    from . import _discontinuities as D
    from .domain import Interval
    found = D.discontinuities(cj, fn, facts)
    if not found or not corners:
        return [], None
    points: list = []
    skipped = 0
    for name in deps["names"]:
        bound = cj_domain.get(name)
        pieces = getattr(bound, "pieces", None) or (
            (bound,) if isinstance(bound, tuple) else ())
        for piece in pieces:
            if not (isinstance(piece, (tuple, Interval))
                    and not isinstance(piece, frozenset) and len(piece) == 2):
                continue
            try:
                lo, hi = float(piece[0]), float(piece[1])
            except (TypeError, ValueError):
                continue
            values, more = D.on_interval(found, name, lo, hi)
            skipped += more
            points += [{**corners[0], name: v} for v in values]
    if not points:
        return [], None
    return points, D.Coverage(at_discontinuities=len(points),
                              discontinuity_words=D.words_of(found),
                              edge_cases=len(corners), skipped=skipped)


def _float_companion(parent, cj, fn, facts, cj_domain, bound_funcs,
                     assum=(), budget=None, missing=None,
                     holes=None, excluded=None) -> "Probe | None":
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
        corroboration budget of interior points. `missing` lists the
        missing values the claim's completed domain admits, `(param,
        word, value)`: each is executed at the first domain corner,
        after the corners and before the sampled points; a container's
        floor is listed the same way (its word None for an item that
        holds no hole). `holes`, `{param: [value, ...]}`, are the hole
        values a container's slots admit, carried by its sampled draws.
        A point where the code returns a missing value or raises at a
        missing input is classified, never judged. `excluded`, when given,
        is a predicate over points that the claim's premises leave out
        beyond its relations (`assuming f is defined`): such a point is
        never executed.
    """
    from . import corroboration as C
    from ._sampling import representation_reach
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .records import operational_infinity, operational_range
    resolved = operational_infinity(cj)
    cap = operational_range(cj)
    descriptor, representation, representation_word = \
        companion_representation(cj_domain, facts)
    # the admitted missing values, a container's by slot and a scalar's
    # as the parameter's own value, which the kit admits beside the
    # domain's own points
    holes = {p: list(v) for p, v in (holes or {}).items()}
    for p, _w, v in (missing or ()):
        if not isinstance(v, (list, tuple, dict)):
            holes.setdefault(p, []).append(v)
    deps = _point_evaluator(cj, fn, facts, cj_domain, bound_funcs, assum,
                            cap=cap, reach=representation.max_magnitude,
                            sequences=True, holes=holes)
    if deps is None:
        return None
    if excluded is not None:
        inside = deps["admits"]
        deps["admits"] = lambda point: inside(point) and not excluded(point)
    name = companion_name(parent.name, descriptor)
    # the companion's calls are filed under its own name
    from .policy import _CLAIM as _policy_claim
    _policy_claim.set(name)
    top = float(representation.max_magnitude or representation_reach())
    reach = cap if cap is not None else (-top, top)
    reach_text = _reach_text(deps["names"], cj_domain, resolved, reach)
    corners = list(deps["corners"])
    missing_corners = [{**corners[0], p: v} for p, _w, v in (missing or ())
                       if corners and p in deps["names"]]
    # the admitted missing inputs run first, so each is executed and
    # recorded whatever a domain corner does
    corners = missing_corners + corners
    # the admitted missing inputs run beside the budget, which is the
    # computation line's numbers
    interior = (C._CORROBORATION_BUDGET if budget is None
                else max(0, int(budget) - (len(corners) - len(missing_corners))))
    # a claim over finite sets only is its listed points, each run once
    listed = _listed_points(deps["names"], cj_domain)
    admits = deps["admits"]
    if listed is not None:
        corners, interior = listed, 0
        listed_ids = {id(pt) for pt in listed}
        admits = (lambda pt: id(pt) in listed_ids)  # noqa: E731
    scale = 1.0 if budget is None else max(
        1.0, float(budget) / (len(corners) + C._CORROBORATION_BUDGET))
    finite = None if listed is not None else _finite_plan(
        cj, fn, facts, deps, cj_domain, corners, admits, scale)
    coverage = None
    if finite is not None:
        corners, interior = finite.points, finite.sampled
        if finite.coverage.full:
            # the admitted missing inputs still run first, for the
            # policy lines
            corners = missing_corners + corners
        coverage = finite.coverage
    elif listed is None:
        targeted, coverage = _interval_discontinuities(
            cj, fn, facts, deps, cj_domain, corners)
        corners = corners + targeted
        if coverage is not None:
            coverage.random = interior
    if coverage is not None and not coverage.full:
        # the missing inputs are the policy lines' trials, not this line's
        coverage.edge_cases = max(0, coverage.edge_cases - len(missing_corners))
    corner_count = sum(1 for c in corners if admits(c))
    # the admitted missing inputs run for the policy lines, not as points
    # of the computation line
    holes_run = sum(1 for c in missing_corners if admits(c)) if listed is None else 0
    progress = C.StabilitySweep()
    try:
        sweep = _with_timeout(
            lambda: C.sweep_stability(deps["probe_finite"], deps["names"],
                                      sample=deps["sample"],
                                      corners=corners,
                                      admits=admits,
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
    tried: dict = {}
    for p, w, v in (missing or ()):
        if w and missing_corners and p in deps["names"]:
            # a scalar's value as executed, a container's member word
            said = w if isinstance(v, (list, tuple, dict)) else repr(v)
            if said not in tried.get(p, []):
                tried.setdefault(p, []).append(said)
    tried_meta = {"mathema.missing": {"tried": tried}} if tried else {}
    from .probing import executed_missing, with_executed
    tried_meta = with_executed(tried_meta, executed_missing(deps)) or {}
    drawn = getattr(deps["evaluate"], "drawn", None)
    if drawn is not None and drawn.meta():
        tried_meta = {**tried_meta, "mathema.drawn": drawn.meta()}
    numbers = max(0, sweep.checked - holes_run)
    if listed is not None:
        what = (f"the {representation_word} computation of {parent.name} ran at "
                + _listed_words(listed, deps["names"])
                + (f"; {reach_text}" if reach_text else ""))
    elif coverage is not None:
        what = (f"the {representation_word} computation of {parent.name} ran "
                + coverage.words(numbers)
                + (f"; {reach_text}" if reach_text else ""))
    else:
        inner = max(0, sweep.checked - corner_count)
        listing = ["every corner",
                   f"{inner} interior point{'s' if inner != 1 else ''}"]
        what = (f"the {representation_word} computation of {parent.name} ran at "
                f"{numbers} points: " + _and_words(", ".join(listing))
                + (f"; {reach_text}" if reach_text else ""))
    # the points a discontinuity analysis chose are the route's mechanism
    float_route = ("probe:semi_analytical"
                   if coverage is not None and coverage.at_discontinuities
                   else "probe")
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
        exact = _exact_claim_at(cj, fn, facts, sweep.fragile_point, assum)
        if exact is False:
            # the claim is false at the executed point in exact
            # arithmetic too: the proof, not the computation, failed
            return Probe(
                name, parent.statement, "falsified", route=float_route,
                n=numbers, counterexample=f"{pt}: {sweep.detail}",
                note=what,
                sketch=f"the proof of {parent.name} failed: at {pt} the "
                       f"claim is false in exact arithmetic as well as in "
                       f"the computation ({sweep.detail})",
                meta={"mathema.proof_contradicted": pt})
        relation_failed = sweep.detail.startswith("the relation fails")
        if exact is None and relation_failed:
            # finite values that contradict the proof: either float lost
            # the value or the proof is wrong, and nothing here says which
            return Probe(
                name, parent.statement, "falsified", route=float_route,
                n=numbers, counterexample=pt, note=what,
                sketch=f"{parent.name} is proven, but its computation "
                       f"fails at {pt}: {sweep.detail}; whether the "
                       f"mathematics holds at that point was not decided, "
                       f"so this is the computation failing or the proof "
                       f"failing; "
                       + (f"{covered}; " if covered else "")
                       + f"{remedy}")
        return Probe(
            name, parent.statement, "falsified", route=float_route,
            n=numbers, counterexample=pt, note=what,
            sketch=f"{parent.name} is mathematically proven, but its "
                   f"computation fails at {pt}: {sweep.detail}"
                   + (": precision loss" if relation_failed else "")
                   + ("; the claim holds there in exact arithmetic; "
                      if exact else "; ")
                   + (f"{covered}; " if covered else "")
                   + f"{remedy}",
            # the proof that coexists with the executed break is the
            # evidence that the mathematics is sound and the code is not
            stratum={"mathematics": "sound", "blame": "implementation",
                     "cause": "implementation:numerical-instability",
                     "representation": representation.tag, "witness": pt},
            meta=tried_meta or None)
    if sweep.undecided:
        at = _fmt_point(sweep.undecided_point, deps["names"])
        return Probe(name, parent.statement, "unknown", route=float_route,
                     n=numbers,
                     note=f"{what}; the claim's own side could not be "
                          f"evaluated at {sweep.undecided} point"
                          f"{'s' if sweep.undecided != 1 else ''}, first at "
                          f"{at}: {sweep.undecided_detail}",
                     meta=tried_meta or None)
    if numbers == 0:
        return Probe(name, parent.statement, "skipped", route=float_route,
                     note=f"{what}; no in-domain point satisfied the "
                          f"claim's premises, so nothing was executed")
    return Probe(name, parent.statement, "holds", route=float_route,
                 n=numbers, note=what, meta=tried_meta or None)
