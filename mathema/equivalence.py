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
assembles the Probe. Sampling here is values-only: a drawn point where
either side raises, returns a non-finite float, or returns something
non-numeric is never adjudicated, and every such point is counted in
the record's sampling meta rather than dropped silently.
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
#: the relative slack term beside the claim's own tolerance
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
        # an executed raise, not a value disagreement: sampling compares
        # values only, so the raise is recorded and the verdict is left
        # to the value rungs
        state.raise_note = proof.sketch
        proof = replace(proof, status="undecided")
    state.proof = proof
    return None


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
    from .probing import _fmt, _fmt_value, _synth

    cj = case.cj
    kinds = {p: case.facts.param_kinds.get(p, "unknown")
             for p in case.facts.params}
    rng = random.Random(EQUIV_SEED)
    tol = cj.tolerance if cj.tolerance is not None else DEFAULT_TOLERANCE
    checked, cx = 0, None
    discarded = {"out_of_domain": 0, "not_compared": 0, "non_numeric": 0}
    for _ in range(EQUIV_SAMPLE_DRAWS):
        args = [_synth(k, rng, case.cj_domain.get(p))
                for p, k in kinds.items()]
        if not all(_draw_in_domain(a, case.cj_domain.get(p))
                   for p, a in zip(kinds, args)):
            discarded["out_of_domain"] += 1
            continue
        try:
            fv = case.fn(*args)
        except Exception:
            fv = _RAISED
        try:
            gv = case.gfn(*args)
        except Exception:
            gv = _RAISED
        state.executed += 1
        if fv is _RAISED or gv is _RAISED:
            discarded["not_compared"] += 1
            continue
        if not (_numberlike(fv) and _numberlike(gv)):
            discarded["non_numeric"] += 1
            continue
        if not (_finite(fv) and _finite(gv)):
            discarded["not_compared"] += 1
            continue
        checked += 1
        scale = max(abs(fv), abs(gv), 1.0)
        if abs(fv - gv) > tol + EQUIV_REL_SLACK * scale:
            cx = (_fmt(tuple(args), names=tuple(kinds))
                  + f": {_fmt_value(fv)} vs {_fmt_value(gv)}")
            break

    sampling: dict = {"draws": EQUIV_SAMPLE_DRAWS, "checked": checked,
                      "seed": EQUIV_SEED}
    nonzero = {k: v for k, v in discarded.items() if v}
    if nonzero:
        sampling["discarded"] = nonzero
    meta = {**case.annotations, "mathema.equivalence.sampling": sampling}
    skipped = discarded["not_compared"] + discarded["non_numeric"]
    aside = (f"; {skipped} of {state.executed} executed points were "
             f"not comparable" if skipped else "")
    if state.raise_note:
        aside += f"; not proven, since {state.raise_note}"

    if cx is not None:
        return _stamp(Probe(
            cj.name, case.statement, "falsified", route="probe",
            n=checked, counterexample=cx,
            note=f"{case.note}; the two implementations disagree at an "
                 f"executed shared point{aside}", meta=meta), "sampled")
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
