# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `f =:= g` (equivalence) ladder over two live callables.

Four rungs, strongest first, each free to decline: identical canonical
form; the symbolic difference of the two lifts; the read-only closed
forms compared directly; shared-draw sampling of both real functions.
A falsification from the symbolic rung must reproduce on an executed
point before it stands (the executed-witness invariant); an
unreproduced one downgrades to unknown with the engine-bug flag.

A claim family registered under the name `equivalence` is consulted
before the built-in ladder and may return a verdict of its own; the
result passes the same family verdict contract every family route
does (a falsification must carry its witness), and this module still
assembles the Probe. `f =:= g` means `for x in D, f(x) == g(x)`, so a
point where one side raises and the other returns a value falsifies,
with the executed raise as the witness. A complex result under a real
claim counts as a raise (unless that side is annotated `complex`). A
point where both sides raise the same exception type is agreement (the
two behave the same there); different exception types at the same point
falsify, with the executed pair as the witness. A drawn point where
either side returns a non-finite float or something non-numeric is not
adjudicated, and every such point is counted in the record's sampling
meta rather than dropped silently.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Callable, Protocol

from .records import Probe

#: shared draws per sampling run
EQUIV_SAMPLE_DRAWS = 96
#: value agreements required before sampling may report holds
EQUIV_MIN_AGREEMENTS = 24
#: the shared-draw seed, fixed so both sides see identical points
EQUIV_SEED = 20260718
#: the relative slack term beside the default tolerance; a declared
#: tolerance is the whole allowance and gets none
EQUIV_REL_SLACK = 1e-9

#: verdicts a registered equivalence family may return
_FAMILY_VERDICTS = frozenset({"proven", "holds", "falsified", "unknown",
                              "skipped"})

_RAISED = object()


class EquivalenceContext(Protocol):
    """What the ladder reads off the adjudication context: exactly
    these four fields, so a test can pass a plain namespace."""
    cj: object
    statement: str
    note: str
    cj_domain: dict


@dataclass
class _Case:
    """One equivalence adjudication's fixed inputs, bundled so each
    rung takes a single argument beside the cross-rung state."""
    cj: object
    statement: str
    note: str
    cj_domain: dict
    fn: Callable
    facts: object
    gfn: Callable
    gfacts: object
    rhs_name: str
    annotations: dict


@dataclass
class _LadderState:
    """Cross-rung coupling, named instead of implied: the symbolic
    rung parks a non-proven proof here for the sampling rung's
    corroboration handshake, and the sampling rung parks its tallies
    for the fallthrough note."""
    proof: object | None = None
    executed: int = 0
    sampling_meta: dict | None = None
    raise_note: str | None = None


def _stamp(probe: Probe, rung: str) -> Probe:
    probe.meta = {**(probe.meta or {}), "mathema.equivalence.rung": rung}
    return probe


def _draw_in_domain(value, bound) -> bool:
    """Intent:
        Whether a synthesized draw is actually inside the claim's
        domain before either function is called: the sampler can
        return an excluded value after its retry budget, and draws an
        infinite declared endpoint deliberately, both fine as value-
        claim stressors and both wrong as shared equivalence points.
        A sequence draw checks each element; a non-numeric draw (a
        string kind) passes, membership is a numeric question here.
    """
    if isinstance(value, (list, tuple)):
        return all(_draw_in_domain(v, bound) for v in value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    if value != value or abs(value) == float("inf"):
        return False
    if bound is None:
        return True
    from .domain import domain_contains
    try:
        return bool(domain_contains(value, bound))
    except Exception:
        return True


def _guarded_family_result(result: dict) -> dict:
    """The family verdict contract, enforced: a closed verdict
    vocabulary, and a falsification must carry its witness. A
    violation raises; it is a family implementation bug, never a
    claim outcome."""
    verdict = result.get("verdict")
    if verdict not in _FAMILY_VERDICTS:
        raise ValueError(f"equivalence family returned verdict "
                         f"{verdict!r}, not in the closed vocabulary "
                         f"{sorted(_FAMILY_VERDICTS)}")
    if verdict == "falsified" and not result.get("counterexample"):
        raise ValueError("equivalence family falsified without a "
                         "counterexample; a falsification must carry "
                         "its witness")
    return result


def _numberlike(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v) -> bool:
    return _numberlike(v) and v == v and abs(v) != float("inf")


def _run_side(fn, args, complex_raises: bool):
    """Intent:
        Call one side at `args`: `(value, None)` when it returns, or
        `(_RAISED, name)` naming the exception it raised. A complex
        result counts as a raise when `complex_raises`, named
        `complex <value>`.
    """
    from .probing import _fmt_value, is_complex_value
    try:
        value = fn(*args)
    except Exception as e:
        return _RAISED, type(e).__name__
    if complex_raises and is_complex_value(value):
        try:
            text = _fmt_value(complex(value))
        except (TypeError, ValueError):
            text = repr(value)
        return _RAISED, f"complex {text}"
    return value, None


def _one_sided_raise(args, names, fv, f_exc, gv, g_exc, rhs_name) -> str | None:
    """Intent:
        The counterexample text for a point where exactly one side
        raised and the other returned a value, else None.
    """
    from .probing import _fmt, _fmt_value
    if (fv is _RAISED) == (gv is _RAISED):
        return None
    point = _fmt(tuple(args), names=tuple(names))
    if fv is _RAISED:
        raised = (f"f returned the complex value {f_exc[len('complex '):]}, "
                  f"which a real claim reads as a raise"
                  if f_exc.startswith("complex ")
                  else f"f raised {f_exc}")
        return f"{point}: {raised}, {rhs_name} returned {_fmt_value(gv)}"
    raised = (f"{rhs_name} returned the complex value "
              f"{g_exc[len('complex '):]}, which a real claim reads as a raise"
              if g_exc.startswith("complex ")
              else f"{rhs_name} raised {g_exc}")
    return f"{point}: {raised}, f returned {_fmt_value(fv)}"


def _raise_kind(exc: str) -> str:
    """The behaviour a raise stands for when two sides are compared:
    the exception type name, or `a complex result` for a complex value
    a real claim reads as a raise."""
    return "a complex result" if exc.startswith("complex ") else exc


def _differing_raises(args, names, fv, f_exc, gv, g_exc,
                      rhs_name) -> str | None:
    """Intent:
        The counterexample text for a point where both sides raised,
        but not the same kind of raise, else None.
    """
    from .probing import _fmt
    if not (fv is _RAISED and gv is _RAISED):
        return None
    if _raise_kind(f_exc) == _raise_kind(g_exc):
        return None
    point = _fmt(tuple(args), names=tuple(names))

    def said(side, exc):
        if exc.startswith("complex "):
            return (f"{side} returned the complex value "
                    f"{exc[len('complex '):]}, which a real claim reads "
                    f"as a raise")
        return f"{side} raised {exc}"
    return f"{point}: {said('f', f_exc)}, {said(rhs_name, g_exc)}"


def adjudicate(ctx: EquivalenceContext, fn, facts) -> Probe:
    """Intent:
        The full `=:=` adjudication: validate the claim shape, bind
        and analyze the right-hand side, consult a registered
        equivalence family, then run the rung ladder. Records carry
        both sides' structural complexity as annotations, never
        verdict-bearing.

    Notes:
        First slice: `f` on the left, one funcs=-bound name on the
        right, same arity (positional alignment).
    """
    from .conjecture import _effective_facts, _resolve_func_ref
    from .inventory import structural_complexity

    cj, statement, note = ctx.cj, ctx.statement, ctx.note
    cj_domain = ctx.cj_domain

    lhs_name, rhs_name = cj.lhs.strip(), (cj.rhs or "").strip()
    if lhs_name != "f" or not rhs_name.isidentifier():
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; equivalence takes bare function names: "
                          f"f =:= g with g bound via funcs= (got "
                          f"{cj.lhs!r} =:= {cj.rhs!r})")
    try:
        bound = {name: (v if callable(v) else _resolve_func_ref(v))
                 for name, v in cj.funcs.items()}
    except AttributeError:
        bound = {}
    gfn = bound.get(rhs_name)
    if gfn is None:
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; {rhs_name!r} is not bound, pass "
                          f"funcs={{{rhs_name!r}: <function>}}")
    try:
        gfacts = _effective_facts(gfn)
    except Exception as e:
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"{note}; could not analyze {rhs_name}: {e}")
    if len(facts.params) != len(gfacts.params):
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; arity differs (f takes "
                          f"{len(facts.params)}, {rhs_name} takes "
                          f"{len(gfacts.params)}), positional equivalence "
                          f"is not meaningful")
    annotations: dict = {}
    try:
        annotations["mathema.equivalence.complexity"] = {
            "f": structural_complexity(fn)["cyclomatic"],
            rhs_name: structural_complexity(gfn)["cyclomatic"]}
    except Exception:
        pass

    case = _Case(cj=cj, statement=statement, note=note,
                 cj_domain=cj_domain or {}, fn=fn, facts=facts, gfn=gfn,
                 gfacts=gfacts, rhs_name=rhs_name, annotations=annotations)

    family_probe = _family_verdict(case)
    if family_probe is not None:
        return family_probe

    state = _LadderState()
    for _, rung in RUNGS:
        probe = rung(case, state)
        if probe is not None:
            return probe
    return _fallthrough(case, state)


def _family_verdict(case: _Case) -> Probe | None:
    """A registered `equivalence` family's own adjudication, when one
    exists, accepts the claim, and does not decline. The family
    returns a plain dict; this module owns Probe assembly."""
    from .families import call_route, families

    family = families().get("equivalence")
    if family is None or not family.can_handle(case.fn, case.facts,
                                               case.cj.name):
        return None
    route_fn = (family.routes() or {}).get("equivalence")
    if route_fn is None:
        return None
    result = call_route(route_fn, case.fn, case.facts, case.gfn,
                        case.gfacts, domain=case.cj_domain,
                        tolerance=case.cj.tolerance,
                        statement=case.statement)
    if result is None:
        return None
    result = _guarded_family_result(result)
    note = case.note
    if result.get("note"):
        note = f"{note}; {result['note']}" if note else result["note"]
    return Probe(case.cj.name, case.statement, result["verdict"],
                 route=result.get("route"), n=int(result.get("n") or 0),
                 counterexample=result.get("counterexample"),
                 sketch=result.get("sketch"), note=note,
                 stratum=result.get("stratum"),
                 meta={**case.annotations, **(result.get("meta") or {})})


def _rung_form(case: _Case, state: _LadderState) -> Probe | None:
    if case.facts.form and case.facts.form == case.gfacts.form:
        return _stamp(Probe(
            case.cj.name, case.statement, "proven", route="derive",
            sketch=f"f and {case.rhs_name} lift to the identical "
                   f"canonical form (form hash {case.facts.form})",
            note=case.note, meta=dict(case.annotations)), "form")
    return None


def _rung_symbolic(case: _Case, state: _LadderState) -> Probe | None:
    from .symbolic import try_prove

    params = ", ".join(case.facts.params)
    try:
        proof = try_prove(case.fn, case.facts, f"f({params})",
                          f"{case.rhs_name}({params})", "==",
                          domain=case.cj_domain,
                          tolerance=case.cj.tolerance,
                          funcs={case.rhs_name: case.gfn})
    except Exception:
        proof = None
    if proof is not None and proof.status == "proven":
        return _stamp(Probe(
            case.cj.name, case.statement, "proven", route="derive",
            sketch=f"the symbolic difference of the two lifted bodies "
                   f"vanishes: {proof.sketch}",
            condition=proof.quantifier, note=case.note,
            meta=dict(case.annotations)), "symbolic")
    if proof is not None and proof.status == "disproven" \
            and (proof.meta or {}).get("mathema.witness_executed"):
        # an executed raise: when the other side returns a value at the
        # same point, the two disagree there and that point is the
        # witness; otherwise the raise is recorded and the verdict is
        # left to the value rungs
        falsified = _raise_witness_probe(case, proof)
        if falsified is not None:
            return falsified
        coinciding = _coinciding_raise_proof(case)
        if coinciding is not None:
            return coinciding
        state.raise_note = proof.sketch
        proof = replace(proof, status="undecided")
    state.proof = proof
    return None


def _raise_witness_probe(case: _Case, proof) -> Probe | None:
    """Intent:
        Both sides executed at the witness of a raise-region disproof,
        and a falsified Probe when exactly one of them raises there, or
        both raise different kinds of exception. None when the witness
        has no complete point, both sides raise the same kind, or both
        return.
    """
    from .domain import _as_int_if_whole
    from .probing import complex_is_a_raise
    witness = proof.witness or {}
    params = list(case.facts.params)
    if not all(p in witness for p in params):
        return None
    args = []
    for p in params:
        v = witness[p]
        kind = case.facts.param_kinds.get(p, "unknown")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = _as_int_if_whole(v) if kind in ("int", "bool") else float(v)
        args.append(v)
    fv, f_exc = _run_side(case.fn, args,
                          complex_is_a_raise(case.fn, case.cj_domain))
    gv, g_exc = _run_side(case.gfn, args,
                          complex_is_a_raise(case.gfn, case.cj_domain))
    cx = _one_sided_raise(args, params, fv, f_exc, gv, g_exc, case.rhs_name)
    what = "one side raises where the other returns a value"
    if cx is None:
        cx = _differing_raises(args, params, fv, f_exc, gv, g_exc,
                               case.rhs_name)
        what = "the two sides raise different exceptions"
    if cx is None:
        return None
    return _stamp(Probe(
        case.cj.name, case.statement, "falsified", route="derive",
        counterexample=cx, sketch=proof.sketch,
        note=f"{case.note}; {what}: {proof.sketch}",
        meta={**case.annotations, "mathema.corroboration": "reproduced"}),
        "symbolic")


def _coinciding_raise_proof(case: _Case) -> Probe | None:
    """Intent:
        Proven when both sides raise the same exception on exactly the
        same region of the declared domain and their closed forms agree
        everywhere else, else None.

    Notes:
        The value half is the symbolic difference proved under
        `assume_defined`, which quantifies over the points where every
        call returns. The raise half compares the two sides' complete
        raise regions (`_raise_regions`), exception by exception, and
        needs the regions of different exceptions on one side to be
        disjoint, since at an overlap the exception raised depends on
        evaluation order.
    """
    from .symbolic import try_prove

    try:
        regions = _coinciding_raise_regions(case)
    except TimeoutError:
        return None
    if not regions:
        return None
    params = ", ".join(case.facts.params)
    try:
        proof = try_prove(case.fn, case.facts, f"f({params})",
                          f"{case.rhs_name}({params})", "==",
                          domain=case.cj_domain,
                          tolerance=case.cj.tolerance,
                          funcs={case.rhs_name: case.gfn},
                          assume_defined=True)
    except Exception:
        return None
    if proof.status != "proven":
        return None
    name = case.facts.params[0]
    where = "; ".join(f"{exc} where {_region_text(region, name)}"
                      for exc, region in sorted(regions.items()))
    return _stamp(Probe(
        case.cj.name, case.statement, "proven", route="derive",
        sketch=f"both sides raise the same exception on the same region "
               f"({where}), and wherever both return the symbolic "
               f"difference vanishes: {proof.sketch}",
        condition=proof.quantifier, note=case.note,
        meta=dict(case.annotations)), "symbolic")


def _region_text(region, name: str) -> str:
    """A region of one parameter's values as relation text: `x = 0`,
    `-1 <= x < 0`, pieces joined by `or`; sympy's own spelling for any
    other shape."""
    import sympy

    def num(v) -> str:
        try:
            return f"{float(v):g}"
        except (TypeError, ValueError):
            return str(v)

    if isinstance(region, sympy.Union):
        return " or ".join(_region_text(part, name) for part in region.args)
    if isinstance(region, sympy.FiniteSet):
        return " or ".join(f"{name} = {num(v)}" for v in region)
    if isinstance(region, sympy.Interval):
        parts = []
        if region.start.is_finite:
            parts.append(f"{num(region.start)} "
                         f"{'<' if region.left_open else '<='} ")
        parts.append(name)
        if region.end.is_finite:
            parts.append(f" {'<' if region.right_open else '<='} "
                         f"{num(region.end)}")
        return "".join(parts)
    return f"{name} in {region}"


def _coinciding_raise_regions(case: _Case) -> "dict | None":
    """Intent:
        The shared raise regions of the two sides, as {exception name:
        region inside the declared domain}, when both sides' complete
        raise regions are the same exception by exception and the
        regions of different exceptions are disjoint. None otherwise,
        including whenever a region cannot be decided.
    """
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout

    def compute():
        f_regions = _raise_regions(case.fn, case.facts, case.cj_domain,
                                   case.facts.params[0])
        if f_regions is None:
            return None
        g_domain = {case.gfacts.params[0]:
                    case.cj_domain.get(case.facts.params[0])}
        g_regions = _raise_regions(case.gfn, case.gfacts, g_domain,
                                   case.facts.params[0])
        if g_regions is None or set(f_regions) != set(g_regions):
            return None
        for exc in f_regions:
            same = sympy.SymmetricDifference(f_regions[exc],
                                             g_regions[exc]).is_empty
            if same is not True:
                return None
        kinds = sorted(f_regions)
        for i, a in enumerate(kinds):
            for b in kinds[i + 1:]:
                if sympy.Intersection(f_regions[a],
                                      f_regions[b]).is_empty is not True:
                    return None
        return f_regions

    return _with_timeout(compute, FAST_TIMEOUT_SECONDS)


def _raise_regions(fn, facts, cj_domain, name: str) -> "dict | None":
    """Intent:
        Every region of the declared domain where `fn` raises, as
        {exception name: sympy set of values of its single parameter,
        renamed to `name`}, empty regions left out. None when the
        function has more than one parameter, the raise-region walk did
        not read every statement, the body asserts, raises from inside
        a loop or recursion, can return a complex value, or a region is
        not a set of values of that one parameter.
    """
    import ast

    import sympy

    from .domain import bound_to_sympy_set
    from .symbolic._base import _bind_params
    from .symbolic._conditioned import lift_piecewise
    from .symbolic._partiality import partiality_walk

    if facts.tree is None or len(facts.params) != 1:
        return None
    nodes = list(ast.walk(facts.tree))
    if any(isinstance(n, ast.Assert) for n in nodes):
        return None
    complex_regions: list = []
    try:
        guards, unread = partiality_walk(fn, facts, cj_domain or {},
                                         complex_out=complex_regions)
    except TimeoutError:
        raise
    except Exception:
        return None
    if unread is not None or complex_regions:
        return None
    guards = list(guards)
    if any(isinstance(n, ast.Raise) for n in nodes):
        if facts.loops or facts.recursion:
            return None
        try:
            pw = lift_piecewise(fn, facts)
        except TimeoutError:
            raise
        except Exception:
            return None
        if pw is None:
            return None
        guards += list(pw.raise_guards)
    try:
        params, _aggregate = _bind_params(fn, facts)
    except Exception:
        return None
    sym = params.get(facts.params[0])
    if sym is None:
        return None
    bound = (cj_domain or {}).get(facts.params[0])
    try:
        domain_set = (sympy.S.Reals if bound is None
                      else bound_to_sympy_set(bound))
    except Exception:
        return None
    shared = sympy.Symbol(name, real=True)
    regions: dict = {}
    for cond, exc in guards:
        if cond.free_symbols - {sym}:
            return None
        try:
            region = cond.subs(sym, shared).as_set()
        except TimeoutError:
            raise
        except Exception:
            return None
        region = sympy.Intersection(region, domain_set)
        if region.is_empty is True:
            continue
        regions[exc] = (sympy.Union(regions[exc], region)
                        if exc in regions else region)
    return regions


def _rung_closed_forms(case: _Case, state: _LadderState) -> Probe | None:
    if state.raise_note is not None or not (
            _raise_free(case.fn, case.facts, case.cj_domain)
            and _raise_free(case.gfn, case.gfacts, case.cj_domain)):
        return None
    closed = _closed_forms_identical(case.fn, case.facts, case.gfn,
                                     case.gfacts, case.cj_domain)
    if closed is not None:
        return _stamp(Probe(
            case.cj.name, case.statement, "proven", route="derive",
            sketch=closed, note=case.note,
            meta=dict(case.annotations)), "closed-forms")
    return None


def _rung_sampled(case: _Case, state: _LadderState) -> Probe | None:
    from .conjecture import DEFAULT_TOLERANCE
    from .probing import _fmt, _fmt_value, _synth, complex_is_a_raise

    cj = case.cj
    kinds = {p: case.facts.param_kinds.get(p, "unknown")
             for p in case.facts.params}
    rng = random.Random(EQUIV_SEED)
    tol = cj.tolerance if cj.tolerance is not None else DEFAULT_TOLERANCE
    rel_slack = 0.0 if cj.tolerance is not None else EQUIV_REL_SLACK
    f_complex = complex_is_a_raise(case.fn, case.cj_domain)
    g_complex = complex_is_a_raise(case.gfn, case.cj_domain)
    checked, cx, both_raised = 0, None, 0
    discarded = {"out_of_domain": 0, "not_compared": 0, "non_numeric": 0}
    for _ in range(EQUIV_SAMPLE_DRAWS):
        args = [_synth(k, rng, case.cj_domain.get(p))
                for p, k in kinds.items()]
        if not all(_draw_in_domain(a, case.cj_domain.get(p))
                   for p, a in zip(kinds, args)):
            discarded["out_of_domain"] += 1
            continue
        fv, f_exc = _run_side(case.fn, args, f_complex)
        gv, g_exc = _run_side(case.gfn, args, g_complex)
        state.executed += 1
        one_sided = _one_sided_raise(args, kinds, fv, f_exc, gv, g_exc,
                                     case.rhs_name)
        if one_sided is not None:
            checked += 1
            cx = one_sided
            break
        if fv is _RAISED and gv is _RAISED:
            checked += 1
            cx = _differing_raises(args, kinds, fv, f_exc, gv, g_exc,
                                   case.rhs_name)
            if cx is not None:
                break
            both_raised += 1
            continue
        if not (_numberlike(fv) and _numberlike(gv)):
            discarded["non_numeric"] += 1
            continue
        if not (_finite(fv) and _finite(gv)):
            discarded["not_compared"] += 1
            continue
        checked += 1
        scale = max(abs(fv), abs(gv), 1.0)
        if abs(fv - gv) > tol + rel_slack * scale:
            cx = (_fmt(tuple(args), names=tuple(kinds))
                  + f": {_fmt_value(fv)} vs {_fmt_value(gv)}")
            break

    sampling: dict = {"draws": EQUIV_SAMPLE_DRAWS, "checked": checked,
                      "seed": EQUIV_SEED}
    if both_raised:
        sampling["both_raised"] = both_raised
    nonzero = {k: v for k, v in discarded.items() if v}
    if nonzero:
        sampling["discarded"] = nonzero
    meta = {**case.annotations, "mathema.equivalence.sampling": sampling}
    skipped = discarded["not_compared"] + discarded["non_numeric"]
    aside = (f"; {skipped} of {state.executed} executed points were "
             f"not comparable" if skipped else "")
    if both_raised:
        aside += (f"; at {both_raised} of the agreeing points both sides "
                  f"raised the same exception")
    if state.raise_note:
        aside += f"; not proven, since {state.raise_note}"

    if cx is not None:
        return _stamp(Probe(
            cj.name, case.statement, "falsified", route="probe",
            n=checked, counterexample=cx,
            note=f"{case.note}; the two implementations disagree at an "
                 f"executed shared point, a raise on one side against a "
                 f"value on the other, or different exceptions, counting "
                 f"as a disagreement{aside}",
            meta=meta), "sampled")
    if state.proof is not None and state.proof.status == "disproven":
        # the symbolic rung claimed inequivalence but no executed point
        # reproduces it: the standard uncorroborated downgrade
        return _stamp(Probe(
            cj.name, case.statement, "unknown", route="derive",
            sketch=state.proof.sketch,
            note=f"{case.note}; uncorroborated disproof: the symbolic "
                 f"difference was reported nonzero but {checked} "
                 f"executed shared points all agree, a probable "
                 f"engine bug worth reporting",
            meta={**meta, "mathema.corroboration": "uncorroborated"}),
            "symbolic")
    if checked >= EQUIV_MIN_AGREEMENTS:
        return _stamp(Probe(
            cj.name, case.statement, "holds", route="probe", n=checked,
            note=f"{case.note}; {checked} executed shared points agree "
                 f"within tolerance (sampling, never proof){aside}",
            meta=meta), "sampled")
    state.sampling_meta = meta
    return None


RUNGS: tuple = (
    ("form", _rung_form),
    ("symbolic", _rung_symbolic),
    ("closed-forms", _rung_closed_forms),
    ("sampled", _rung_sampled),
)


def _fallthrough(case: _Case, state: _LadderState) -> Probe:
    """Nothing decided. The route reports the strongest mechanism that
    actually produced information: derive when a proof attempt
    returned a result, probe when points executed, None when no
    mechanism engaged at all."""
    meta = state.sampling_meta or dict(case.annotations)
    sampling = meta.get("mathema.equivalence.sampling") or {}
    checked = sampling.get("checked", 0)
    if state.proof is not None and state.proof.status != "unliftable":
        # the symbolic mechanism genuinely engaged (undecided or an
        # uncorroborated disproof already handled upstream); unliftable
        # means it never got to reason at all
        route = "derive"
    elif state.executed:
        route = "probe"
    else:
        route = None
    return Probe(case.cj.name, case.statement, "unknown", route=route,
                 sketch=(state.proof.sketch if state.proof is not None
                         else None),
                 note=f"{case.note}; neither the canonical forms, the "
                      f"symbolic difference, nor sampling ({checked} "
                      f"evaluable points) could settle equivalence"
                      + (f"; {state.raise_note}" if state.raise_note
                         else ""),
                 meta=meta)


def _raise_free(fn, facts, cj_domain) -> bool:
    """Intent:
        Whether `fn` provably never raises on any input: the raise-
        region walk read every statement and found no implicit raise
        region, and the body holds no `raise` or `assert` of its own.
        Two closed forms that agree say nothing about a point where
        one side has no value, so the closed-form rung needs this of
        both sides.
    """
    import ast

    from .symbolic._partiality import partiality_walk
    if facts.tree is None:
        return False
    if any(isinstance(n, (ast.Raise, ast.Assert))
           for n in ast.walk(facts.tree)):
        return False
    try:
        guards, unread = partiality_walk(fn, facts, cj_domain or {})
    except TimeoutError:
        raise
    except Exception:
        return False
    return unread is None and not guards


def _closed_forms_identical(fn, facts, gfn, gfacts, cj_domain) -> str | None:
    """Intent:
        The read-only closed forms of both sides, compared directly:
        obtain each side's lift through the same lift chain
        adjudication uses, align g's parameters positionally onto
        f's, unify every free symbol by name onto assumption-carrying
        symbols from the claim's domain, and ask whether the
        difference simplifies to zero under the fast cap. Returns the
        proof sketch on success, None otherwise, never a disproof (a
        nonzero residual here may be a lift-shape artifact; executed
        sampling owns falsification).
    """
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .audit import _try_derive_lift
    from .domain import bound_assumptions

    fx = _try_derive_lift(fn, facts, extra_domain=cj_domain)
    g_domain = {gp: cj_domain[fp]
                for fp, gp in zip(facts.params, gfacts.params)
                if fp in (cj_domain or {})}
    gx = _try_derive_lift(gfn, gfacts, extra_domain=g_domain)
    if fx is None or gx is None or isinstance(fx, tuple) or isinstance(gx, tuple):
        return None
    rename = {gp: fp for fp, gp in zip(facts.params, gfacts.params)
              if fp != gp}

    def unified(expr, name_map):
        subs = {}
        for s in expr.free_symbols:
            name = name_map.get(str(s), str(s))
            bound = (cj_domain or {}).get(name)
            kwargs = None
            if bound is not None:
                try:
                    kwargs = bound_assumptions(bound)
                except Exception:
                    kwargs = None
            subs[s] = sympy.Symbol(name, **(kwargs or {"real": True}))
        return expr.subs(subs, simultaneous=True)

    try:
        fx_u = unified(fx, {})
        gx_u = unified(gx, rename)
        residual = _with_timeout(lambda: sympy.simplify(fx_u - gx_u),
                                 FAST_TIMEOUT_SECONDS)
    except Exception:
        return None
    if residual == 0:
        return ("the two closed forms are identical under the declared "
                "domain: both sides lift to expressions whose difference "
                "simplifies to zero")
    return None
