# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `f =:= g` (equivalence) ladder over two live callables.

An equivalence claim has two lines. The mathematics line is derive's
exact ladder, strongest first, each rung free to decline: identical
canonical form; the symbolic difference of the two lifts (with the
regions where both sides refuse alike); the read-only closed forms
compared directly. A disproof from the symbolic rung stands once both
sides, run at derive's witness and compared exactly, disagree there,
however small the difference (`_exact_disagreement`); one that exact
evaluation does not confirm downgrades to unknown with the engine-bug
flag. The mathematics is exact: a declared tolerance never reaches it.

The computation line runs both real functions at shared draws and
compares what they return under the claim's tolerance. When the
mathematics line decides, the computation is its own row,
`<name>[float]`, beside the claim's row. When derive cannot decide,
the shared draws are the claim's only row, as the probe's row is for a
value claim.

A claim family registered under the name `equivalence` is consulted
before the built-in ladder and may return a verdict of its own; the
result passes the same family verdict contract every family route
does (a falsification must carry its witness), and this module still
assembles the Probe. The ladder compares two Python forms: when
either side's facts were read by a frontend other than the Python one
(`_read_elsewhere`), only the family adjudicates, and with no family
verdict the claim is skipped. `f =:= g` means `for x in D, f(x) == g(x)`, so a
point where one side raises and the other returns a value falsifies,
with the executed raise as the witness. A complex result under a real
claim counts as a raise (unless that side is annotated `complex`). A
point where both sides raise the same exception type is agreement (the
two behave the same there); different exception types at the same point
falsify, with the executed pair as the witness. A value is read per
P4: two sides at the same infinity agree; a NaN from non-missing inputs
agrees with nothing, and an infinity disagrees with a value or the
opposite infinity. A drawn point with a missing input, or where either
side returns something non-numeric, is not adjudicated, and every such
point is counted in the record's sampling meta rather than dropped
silently.

`prove_bodies_equal(left, right, domain)` runs the derive rungs alone on
two lifted bodies (KOINE documents, materialised through the engine's
rendering), for a pair whose sides were read by different frontends:
the answer names the rung reached and, for a falsification, the point
both bodies were executed at. Exception names are compared only when
both documents name one language.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import TYPE_CHECKING, Callable, Protocol

from .records import Probe

if TYPE_CHECKING:
    from .koine.document import Document

#: shared draws per sampling run
EQUIV_SAMPLE_DRAWS = 96
#: value agreements required before sampling may report holds
EQUIV_MIN_AGREEMENTS = 24
#: the shared-draw seed, fixed so both sides see identical points
EQUIV_SEED = 20260718
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
    #: whether two raises of different exception types disagree; the
    #: names are compared only when both sides run in one runtime
    compare_refusals: bool = True


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
        return an excluded value after its retry budget, fine as a
        value-claim stressor and wrong as a shared equivalence point.
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


def adjudicate(ctx: EquivalenceContext, fn,
               facts) -> "tuple[Probe, Probe | None]":
    """Intent:
        The full `=:=` adjudication, as `(claim row, computation row)`:
        validate the claim shape, bind and analyze the right-hand side,
        consult a registered equivalence family, then run the rung
        ladder. When a mathematics rung decides (proven or falsified),
        the computation row runs both functions at shared draws
        (`_computation_row`); otherwise there is none. Records carry
        both sides' structural complexity as annotations, never
        verdict-bearing.

    Notes:
        First slice: `f` on the left, one funcs=-bound name on the
        right, same arity (positional alignment).
    """
    from .conjecture import _effective_facts, _resolve_bound_ref
    from .inventory import structural_complexity

    cj, statement, note = ctx.cj, ctx.statement, ctx.note
    cj_domain = ctx.cj_domain

    lhs_name, rhs_name = cj.lhs.strip(), (cj.rhs or "").strip()
    if lhs_name != "f" or not rhs_name.isidentifier():
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; equivalence takes bare function names: "
                          f"f =:= g with g bound via funcs= (got "
                          f"{cj.lhs!r} =:= {cj.rhs!r})"), None
    try:
        bound = {name: (v if callable(v) else _resolve_bound_ref(v))
                 for name, v in cj.funcs.items()}
    except AttributeError:
        bound = {}
    gfn = bound.get(rhs_name)
    if gfn is None:
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; {rhs_name!r} is not bound, pass "
                          f"funcs={{{rhs_name!r}: <function>}}"), None
    try:
        gfacts = _effective_facts(gfn)
    except Exception as e:
        return Probe(cj.name, statement, "skipped", route=None,
                     note=f"{note}; could not analyze {rhs_name}: {e}"), None
    if len(facts.params) != len(gfacts.params):
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=f"{note}; arity differs (f takes "
                          f"{len(facts.params)}, {rhs_name} takes "
                          f"{len(gfacts.params)}), positional equivalence "
                          f"is not meaningful"), None
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
        return family_probe, None
    if _read_elsewhere(facts) or _read_elsewhere(gfacts):
        return Probe(cj.name, statement, "skipped", route="equivalence",
                     note=_joined(note, _ACROSS_RUNTIMES),
                     meta=dict(annotations)), None

    state = _LadderState()
    for name, rung in RUNGS:
        probe = rung(case, state)
        if name == "sampled" and cj.route == "derive" and probe is not None \
                and probe.verdict == "holds":
            # on the derive route sampling falsifies only: shared points
            # that agree are no verdict
            state.sampling_meta = {k: v for k, v in (probe.meta or {}).items()
                                   if k != "mathema.equivalence.rung"}
            continue
        if probe is None:
            continue
        if name in _MATHEMATICS_RUNGS and probe.verdict in ("proven",
                                                            "falsified"):
            return probe, _computation_row(case, probe)
        return probe, None
    return _fallthrough(case, state), None


#: the note on a pair across runtimes that no family adjudicated
_ACROSS_RUNTIMES = "equivalence across runtimes needs the equivalence family"

def _joined(note: str, text: str) -> str:
    return f"{note}; {text}" if note else text


def _read_elsewhere(facts) -> bool:
    """Intent:
        Whether `facts` were read by a frontend other than the Python
        one: their `provenance` names another frontend (by `name` in a
        mapping, or as a string), or, with no frontend named, their form
        hash is namespaced (`"<frontend>:<sha>"`) outside `py` and `doc`.
    """
    from .analysis import written_elsewhere
    return written_elsewhere(facts)


def _family_verdict(case: _Case) -> Probe | None:
    """A registered `equivalence` family's own adjudication, when one
    exists, accepts the claim, and does not decline. The family's route
    is called as `(fn, facts, gfn, gfacts, domain=, tolerance=,
    statement=)`, `tolerance` the claim's as parsed (a bare number, a
    `_tolerance.ToleranceKind`, or None). The family returns a plain
    dict; this module owns Probe assembly."""
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
    """Intent:
        Prove the pair equal when both sides carry the same canonical
        form hash, computed by `analyze_source` from each Python body.
        A form supplied with facts built or edited elsewhere is an
        identity label rather than a canonical form of the body, so a
        pair with one falls through to the symbolic and sampled steps.
    """
    if not (case.facts.form_is_computed()
            and case.gfacts.form_is_computed()):
        return None
    if case.facts.form == case.gfacts.form:
        return _stamp(Probe(
            case.cj.name, case.statement, "proven", route="derive",
            sketch=f"f and {case.rhs_name} reduce to the same "
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
                          tolerance=None,
                          funcs={case.rhs_name: case.gfn})
    except Exception:
        proof = None
    if proof is not None and proof.status == "proven":
        return _stamp(Probe(
            case.cj.name, case.statement, "proven", route="derive",
            sketch=f"the difference of the two functions, read "
                   f"symbolically, is zero: {proof.sketch}",
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
            state.proof = proof
            return falsified
        coinciding = _coinciding_raise_proof(case, state)
        if coinciding is not None:
            return coinciding
        if state.proof is not None and state.proof.status == "disproven":
            # the two sides refuse alike, and derive found their values
            # different at a point where both return: the next rung
            # executes both sides there
            return None
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
    from .probing import complex_is_a_raise
    args = _witness_args(case, proof)
    if args is None:
        return None
    params = list(case.facts.params)
    from .runtime_types import calling
    fv, f_exc = _run_side(calling(case.fn, case.facts), args,
                          complex_is_a_raise(case.fn, case.cj_domain))
    gv, g_exc = _run_side(calling(case.gfn, case.gfacts), args,
                          complex_is_a_raise(case.gfn, case.cj_domain))
    cx = _one_sided_raise(args, params, fv, f_exc, gv, g_exc, case.rhs_name)
    what = "one side raises where the other returns a value"
    if cx is None and case.compare_refusals:
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


def _witness_args(case: _Case, proof) -> list | None:
    """Intent:
        The arguments a proof's witness names, in `f`'s parameter
        order, each read as its parameter's kind (a whole number for an
        `int` or `bool` parameter, a float otherwise); None when the
        witness does not name every parameter.
    """
    from .domain import _as_int_if_whole
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
    return args


def _coinciding_raise_proof(case: _Case,
                            state: "_LadderState | None" = None
                            ) -> Probe | None:
    """Intent:
        Proven when both sides raise the same exception on exactly the
        same region of the declared domain and their closed forms agree
        everywhere else, else None. When the regions coincide and
        derive finds the values different at a point where both return,
        that disproof is left in `state.proof` for the next rung to
        execute.

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
                          tolerance=None,
                          funcs={case.rhs_name: case.gfn},
                          assume_defined=True)
    except Exception:
        return None
    if proof.status != "proven":
        _where_both_return(case, regions, state)
        return None
    name = case.facts.params[0]
    if case.compare_refusals:
        where = "; ".join(f"{exc} where {_region_text(region, name)}"
                          for exc, region in sorted(regions.items()))
        same = "both sides raise the same exception on the same region"
    else:
        where = "; ".join(
            f"{side} raises {', '.join(sorted(by_side))} where "
            f"{_region_text(_union(by_side.values()), name)}"
            for side, by_side in (("f", regions["f"]),
                                  (case.rhs_name, regions[case.rhs_name])))
        same = ("both sides refuse on the same region, the exception names "
                "left uncompared across runtimes")
    return _stamp(Probe(
        case.cj.name, case.statement, "proven", route="derive",
        sketch=f"{same} ({where}), and wherever both return the symbolic "
               f"difference vanishes: {proof.sketch}",
        condition=proof.quantifier, note=case.note,
        meta=dict(case.annotations)), "symbolic")


def _where_both_return(case: _Case, regions: dict,
                       state: "_LadderState | None") -> None:
    """Intent:
        The value question on the part of the declared domain where
        neither side refuses: each piece of the domain minus the shared
        raise region is handed to the symbolic rung as the domain, and
        the first disproof naming a point is left in `state.proof`,
        where the next rung executes both sides at that point, as for
        any symbolic disproof.
    """
    from .symbolic import try_prove
    if state is None:
        return
    try:
        pieces = _returning_pieces(case, regions)
    except TimeoutError:
        return
    name = case.facts.params[0]
    params = ", ".join(case.facts.params)
    for bound in pieces:
        try:
            proof = try_prove(case.fn, case.facts, f"f({params})",
                              f"{case.rhs_name}({params})", "==",
                              domain={name: bound},
                              tolerance=None,
                              funcs={case.rhs_name: case.gfn})
        except Exception:
            return
        if proof.status == "disproven" and _witness_args(case, proof):
            state.proof = proof
            return


def _returning_pieces(case: _Case, regions: dict) -> list:
    """Intent:
        The declared domain of the single parameter minus the shared
        raise region, one bound per piece: an `Interval` (its ends as
        floats) or a finite set. Empty when the remainder is not a
        union of intervals and finite sets.
    """
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .domain import Interval, bound_to_sympy_set

    refused = (_union(regions["f"].values()) if not case.compare_refusals
               else _union(regions.values()))

    def remainder():
        bound = (case.cj_domain or {}).get(case.facts.params[0])
        domain = (sympy.S.Reals if bound is None
                  else bound_to_sympy_set(bound))
        return sympy.Complement(domain, refused)

    rest = _with_timeout(remainder, FAST_TIMEOUT_SECONDS)
    out: list = []
    for part in (rest.args if isinstance(rest, sympy.Union) else (rest,)):
        if isinstance(part, sympy.Interval):
            out.append(Interval(float(part.start), float(part.end),
                                closed_lo=not part.left_open,
                                closed_hi=not part.right_open))
        elif isinstance(part, sympy.FiniteSet):
            out.append(frozenset(float(v) for v in part))
        else:
            return []
    return out


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


def _union(regions):
    import sympy
    return sympy.Union(*regions)


def _coinciding_raise_regions(case: _Case) -> "dict | None":
    """Intent:
        The shared raise regions of the two sides, as {exception name:
        region inside the declared domain}, when both sides' complete
        raise regions are the same exception by exception and the
        regions of different exceptions are disjoint. When the case
        does not compare refusal names, the regions are compared
        whatever exception raises them, and the result is
        {"f": regions of f, <rhs name>: regions of the other side}.
        None otherwise, including whenever a region cannot be decided.
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
        if g_regions is None:
            return None
        for side in (f_regions, g_regions):
            kinds = sorted(side)
            for i, a in enumerate(kinds):
                for b in kinds[i + 1:]:
                    if sympy.Intersection(side[a],
                                          side[b]).is_empty is not True:
                        return None
        if not case.compare_refusals:
            if not f_regions or not g_regions:
                return None
            same = sympy.SymmetricDifference(
                _union(f_regions.values()),
                _union(g_regions.values())).is_empty
            if same is not True:
                return None
            return {"f": f_regions, case.rhs_name: g_regions}
        if set(f_regions) != set(g_regions):
            return None
        for exc in f_regions:
            same = sympy.SymmetricDifference(f_regions[exc],
                                             g_regions[exc]).is_empty
            if same is not True:
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


@dataclass
class _Sampled:
    """What one run of both functions at the shared draws found: the
    first disagreement's text (None when every compared point agreed),
    the points compared, the points executed, the sampling meta, and
    the largest gap between two agreeing values as `(gap, allowance,
    point text)` (None when every agreeing pair was equal)."""
    counterexample: str | None
    checked: int
    executed: int
    both_raised: int
    discarded: dict
    meta: dict
    largest: tuple | None = None

    def gap_words(self, tolerance) -> str:
        """The note's clause for the largest gap the tolerance covered,
        empty when the agreeing values were equal."""
        if self.largest is None:
            return ""
        from .conjecture import passed_within_words
        gap, allowance, at = self.largest
        return "; " + passed_within_words("==", gap, at, allowance, tolerance)

    def aside(self) -> str:
        """The note's account of points not compared, and of agreeing
        points where both sides raised the same exception."""
        skipped = self.discarded["not_compared"] + self.discarded["non_numeric"]
        text = (f"; {skipped} of {self.executed} executed points were "
                f"not comparable" if skipped else "")
        if self.both_raised:
            text += (f"; at {self.both_raised} of the agreeing points both "
                     f"sides raised the same exception")
        return text


def _values_agree(case: _Case, fv, gv) -> bool:
    """Intent:
        Whether two finite values the functions returned at one point
        agree under the claim's tolerance: within a declared kind
        (`_tolerance.ToleranceKind.allows`), within a declared bare
        number read as an absolute allowance, or, with none declared,
        within each side's computation allowance added:
        `|a - b| <= 2 * _allowance.allowance(max(|a|, |b|))`, each
        computed value allowed to miss the exact one by the rule every
        other computation line uses.

    Notes:
        Both functions run at the same inputs and return numbers, so
        the inputs' own round-off (`allowance`'s `input_scaled`, which
        arrays carry) is 0 here.
    """
    from ._allowance import allowance
    from ._tolerance import ToleranceKind
    tol = case.cj.tolerance
    if isinstance(tol, ToleranceKind):
        return tol.allows(fv, gv)
    if tol is None:
        return abs(fv - gv) <= 2 * allowance(max(abs(fv), abs(gv)))
    return abs(fv - gv) <= tol


def _agreement_allowance(case: _Case, fv, gv) -> float:
    """The gap `_values_agree` allows between two values: the declared
    kind's bound, the declared bare number, or each side's computation
    allowance added."""
    from ._allowance import allowance
    from ._tolerance import ToleranceKind
    tol = case.cj.tolerance
    if isinstance(tol, ToleranceKind):
        return float(tol.bound(abs(fv), abs(gv)))
    if tol is None:
        return float(2 * allowance(max(abs(fv), abs(gv))))
    return float(tol)


def _sample_pair(case: _Case) -> _Sampled:
    """Intent:
        Run both functions at `EQUIV_SAMPLE_DRAWS` shared draws from
        the claim's domain (seed `EQUIV_SEED`) and compare them point by
        point, stopping at the first disagreement: a raise on one side
        against a value on the other, two raises of different kinds
        when the refusal names are compared, no value against a value,
        or two values the tolerance does not cover (`_values_agree`). A
        point where both sides raise alike, both return None, or both
        give the same no-value result (the same infinity, two NaN
        holes) agrees.
    """
    from .probing import (_fmt, _fmt_value, _synth, classified,
                          complex_is_a_raise, missing_class, same_infinity)
    from .runtime_types import calling

    kinds = {p: case.facts.param_kinds.get(p, "unknown")
             for p in case.facts.params}
    rng = random.Random(EQUIV_SEED)
    f_complex = complex_is_a_raise(case.fn, case.cj_domain)
    g_complex = complex_is_a_raise(case.gfn, case.cj_domain)
    # each side's drawn values realised as its parameters' runtime types
    f_call = calling(case.fn, case.facts)
    g_call = calling(case.gfn, case.gfacts)
    checked, executed, cx, both_raised = 0, 0, None, 0
    largest = None
    discarded = {"out_of_domain": 0, "not_compared": 0, "non_numeric": 0}
    for _ in range(EQUIV_SAMPLE_DRAWS):
        args = [_synth(k, rng, case.cj_domain.get(p))
                for p, k in kinds.items()]
        if not all(_draw_in_domain(a, case.cj_domain.get(p))
                   for p, a in zip(kinds, args)):
            discarded["out_of_domain"] += 1
            continue
        fv, f_exc = _run_side(f_call, args, f_complex)
        gv, g_exc = _run_side(g_call, args, g_complex)
        executed += 1
        if classified(args, [v for v in (fv, gv) if v is not _RAISED],
                      fv is _RAISED or gv is _RAISED):
            # a raise or a missing output at a missing input is
            # classified, not judged
            continue
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
        if "absent" in (missing_class(fv), missing_class(gv)):
            # a None from present inputs, or a value against a None at a
            # missing input, is no value on that side
            checked += 1
            if not (fv is None and gv is None):
                cx = (_fmt(tuple(args), names=tuple(kinds))
                      + f": {_fmt_value(fv)} vs {_fmt_value(gv)}")
                break
            continue
        if not (_numberlike(fv) and _numberlike(gv)):
            discarded["non_numeric"] += 1
            continue
        if not (_finite(fv) and _finite(gv)):
            # the two functions are the same where both have no value
            # of one kind: two NaNs agree, whatever object carries them,
            # and two sides at the same infinity are one extended-real
            # point; a no-value side against a value, a NaN against an
            # infinity, and opposite infinities disagree
            checked += 1
            if same_infinity(fv, gv) or (missing_class(fv) == "hole"
                                         and missing_class(gv) == "hole"):
                continue
            cx = (_fmt(tuple(args), names=tuple(kinds))
                  + f": {_fmt_value(fv)} vs {_fmt_value(gv)}")
            break
        checked += 1
        if not _values_agree(case, fv, gv):
            cx = (_fmt(tuple(args), names=tuple(kinds))
                  + f": {_fmt_value(fv)} vs {_fmt_value(gv)}")
            break
        try:
            gap = float(abs(fv - gv))
        except (TypeError, OverflowError):
            gap = 0.0
        if gap > 0 and (largest is None or gap > largest[0]):
            largest = (gap, _agreement_allowance(case, fv, gv),
                       _fmt(tuple(args), names=tuple(kinds)))

    sampling: dict = {"draws": EQUIV_SAMPLE_DRAWS, "checked": checked,
                      "seed": EQUIV_SEED}
    if both_raised:
        sampling["both_raised"] = both_raised
    nonzero = {k: v for k, v in discarded.items() if v}
    if nonzero:
        sampling["discarded"] = nonzero
    return _Sampled(cx, checked, executed, both_raised, discarded,
                    {"mathema.equivalence.sampling": sampling}, largest)


#: what the note of a falsified shared-draw row says counts as a
#: disagreement
_DISAGREEMENT = ("a raise on one side against a value on the other, "
                 "different exceptions, or no value (a NaN, or an infinity "
                 "other than the other side's), counting as a disagreement")


def _rung_sampled(case: _Case, state: _LadderState) -> Probe | None:
    """Intent:
        The shared draws standing in for a mathematics line derive
        could not decide: falsified at the first disagreement, holds
        once `EQUIV_MIN_AGREEMENTS` points agree, and unknown with the
        engine-bug flag when the symbolic rung found the two different
        and no executed point shows it. None when too few points were
        compared, the tallies parked for the fallthrough note.
    """
    cj = case.cj
    run = _sample_pair(case)
    state.executed += run.executed
    checked = run.checked
    meta = {**case.annotations, **run.meta}
    aside = run.aside()
    if state.raise_note:
        aside += f"; not proven, since {state.raise_note}"

    if run.counterexample is not None:
        return _stamp(Probe(
            cj.name, case.statement, "falsified", route="probe",
            n=checked, counterexample=run.counterexample,
            note=f"{case.note}; the two implementations disagree at an "
                 f"executed shared point, {_DISAGREEMENT}{aside}",
            meta=meta), "sampled")
    if state.proof is not None and state.proof.status == "disproven":
        # the symbolic rung claimed inequivalence but neither exact
        # evaluation at its witness nor any executed point reproduces
        # it: the standard uncorroborated downgrade
        return _stamp(Probe(
            cj.name, case.statement, "unknown", route="derive",
            sketch=state.proof.sketch,
            note=f"{case.note}; derive found the two functions "
                 f"different, but {checked} points run on both agree, "
                 f"which is probably a mathema bug worth reporting",
            meta={**meta, "mathema.corroboration": "uncorroborated"}),
            "symbolic")
    if checked >= EQUIV_MIN_AGREEMENTS:
        return _stamp(Probe(
            cj.name, case.statement, "holds", route="probe", n=checked,
            note=f"{case.note}; {checked} executed shared points agree "
                 f"within tolerance (sampling, never proof){aside}"
                 f"{run.gap_words(cj.tolerance)}",
            meta=meta), "sampled")
    state.sampling_meta = meta
    return None


def _computation_row(case: _Case, main: Probe) -> Probe:
    """Intent:
        The computation line of a claim whose mathematics line decided:
        both functions run at the shared draws (`_sample_pair`) under
        the claim's tolerance, as the row `<name>[float]` (the number
        representation and runtime types named as for a value claim's
        companion). Falsified at the first disagreement, holds once
        `EQUIV_MIN_AGREEMENTS` points agree, unknown with fewer.
    """
    from .gates import companion_name, companion_representation
    descriptor, _representation, word = companion_representation(
        case.cj_domain, case.facts)
    run = _sample_pair(case)
    meta = dict(run.meta)
    what = (f"the {word} computation of {case.cj.name} ran both "
            f"functions at {run.checked} shared point"
            f"{'s' if run.checked != 1 else ''}{run.aside()}")
    name = companion_name(main.name, descriptor)
    if run.counterexample is not None:
        return _stamp(Probe(
            name, main.statement, "falsified", route="probe",
            n=run.checked, counterexample=run.counterexample,
            note=f"{what}; the two implementations disagree at an "
                 f"executed shared point, {_DISAGREEMENT}",
            meta=meta), "sampled")
    if run.checked >= EQUIV_MIN_AGREEMENTS:
        return _stamp(Probe(
            name, main.statement, "holds", route="probe", n=run.checked,
            note=f"{what}, and they agree within tolerance at every one "
                 f"(sampling, never proof)"
                 f"{run.gap_words(case.cj.tolerance)}",
            meta=meta), "sampled")
    return _stamp(Probe(
        name, main.statement, "unknown", route="probe", n=run.checked,
        note=f"{what}; at least {EQUIV_MIN_AGREEMENTS} agreeing points "
             f"are needed before the computation holds",
        meta=meta), "sampled")


def _rung_exact_witness(case: _Case, state: _LadderState) -> Probe | None:
    """Intent:
        A symbolic disproof whose witness is not yet an executed call,
        confirmed or not by both sides evaluated exactly at derive's
        witness (`_exact_disagreement`): falsified on the mathematics
        line when they disagree there, however small the difference.
        None otherwise, leaving the disproof to the shared draws,
        which reproduce it or downgrade it to unknown with the
        engine-bug flag.
    """
    proof = state.proof
    if proof is None or proof.status != "disproven" \
            or (proof.meta or {}).get("mathema.witness_executed"):
        return None
    found = _exact_disagreement(case, proof, case.rhs_name)
    if found is None:
        return None
    cx, _point = found
    return _stamp(Probe(
        case.cj.name, case.statement, "falsified", route="derive",
        counterexample=cx, sketch=proof.sketch,
        note=f"{case.note}; derive found the two functions different, and "
             f"both sides evaluated exactly at its witness confirm it: "
             f"{proof.sketch}",
        meta={**case.annotations, "mathema.corroboration": "reproduced"}),
        "symbolic")


def _witness_points(case: _Case, proof) -> list:
    """Intent:
        The points at which to check a disproof, each a list of
        arguments in `f`'s parameter order: derive's witness when it
        names every parameter, else up to eight completions of it, each
        coordinate the witness leaves free drawn from its declared
        bound with a fixed seed. Only points inside the declared domain
        are kept; a witness coordinate that is not a real number gives
        none.
    """
    from .domain import _as_int_if_whole
    from .probing import _synth
    witness = proof.witness or {}
    params = list(case.facts.params)

    def read(p, v):
        kind = case.facts.param_kinds.get(p, "unknown")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
        return _as_int_if_whole(v) if kind in ("int", "bool") else float(v)

    named = {p: read(p, witness[p]) for p in params if p in witness}
    if any(v is None for v in named.values()):
        return []
    free = [p for p in params if p not in named]
    rng = random.Random(0)
    points = []
    for _ in range(8 if free else 1):
        drawn = {p: _synth(case.facts.param_kinds.get(p, "unknown"), rng,
                           case.cj_domain.get(p)) for p in free}
        args = [named[p] if p in named else drawn[p] for p in params]
        if all(_draw_in_domain(a, case.cj_domain.get(p))
               for p, a in zip(params, args)):
            points.append(args)
    return points


def _exact_disagreement(case: _Case, proof, rhs_name: str,
                        named: bool = False) -> "tuple[str, list] | None":
    """Intent:
        `(witness text, arguments)` when both sides, run at the first
        admissible point of derive's witness (`_witness_points`),
        disagree there exactly: one side raises and the other returns,
        the two raise different exceptions within one runtime, or their
        values differ. The values are compared exactly: each side run on
        the point's exact rationals when both then return exact
        numbers, which is the mathematics of the point; otherwise the
        floats each side returned, read as the exact rationals they
        hold. None when the sides agree there, a value is not a finite
        number, or the evaluation runs past the fast wall-clock cap.
        Two values are written in full, `<f's> vs <g's>`, or with
        `named`, as what each side returned.
    """
    from ._exact_body import exact_callee
    from ._exact_side import to_exact, wrap
    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .probing import _fmt, complex_is_a_raise
    from .runtime_types import calling

    points = _witness_points(case, proof)
    if not points:
        return None
    args = points[0]
    params = list(case.facts.params)

    def exact_value(callee):
        if not all(_numberlike(a) for a in args):
            return None
        try:
            # the body read exactly, checked against its own float run
            # on the same arguments (`_exact_body.exact_callee`)
            value = wrap(exact_callee(callee), exact_calls=True)(
                *[to_exact(a) for a in args])
        except Exception:
            return None
        return value if _numberlike(value) or isinstance(value, Fraction) \
            else None

    def decide():
        fv, f_exc = _run_side(calling(case.fn, case.facts), args,
                              complex_is_a_raise(case.fn, case.cj_domain))
        gv, g_exc = _run_side(calling(case.gfn, case.gfacts), args,
                              complex_is_a_raise(case.gfn, case.cj_domain))
        cx = _one_sided_raise(args, params, fv, f_exc, gv, g_exc, rhs_name)
        if cx is None and case.compare_refusals:
            cx = _differing_raises(args, params, fv, f_exc, gv, g_exc,
                                   rhs_name)
        if cx is not None:
            return cx
        if not (_finite(fv) and _finite(gv)):
            return None
        fx, gx = exact_value(case.fn), exact_value(case.gfn)
        if fx is not None and gx is not None:
            # the exact values themselves, an integer or a ratio
            left, right = str(Fraction(fx)), str(Fraction(gx))
        else:
            # every digit a float holds, since the two may differ in the
            # last of them
            left, right = repr(fv), repr(gv)
            fx, gx = fv, gv
        if Fraction(fx) == Fraction(gx):
            return None
        said = (f"f returned {left}, {rhs_name} returned {right}" if named
                else f"{left} vs {right}")
        return f"{_fmt(tuple(args), names=tuple(params))}: {said}"

    try:
        cx = _with_timeout(decide, FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    return None if cx is None else (cx, args)


RUNGS: tuple = (
    ("form", _rung_form),
    ("symbolic", _rung_symbolic),
    ("closed-forms", _rung_closed_forms),
    ("symbolic witness", _rung_exact_witness),
    ("sampled", _rung_sampled),
)

#: the rungs of the mathematics line: a verdict from one of them is
#: derive's, and the claim's computation is a row of its own
_MATHEMATICS_RUNGS = frozenset({"form", "symbolic", "closed-forms",
                                "symbolic witness"})


def _fallthrough(case: _Case, state: _LadderState) -> Probe:
    """Nothing decided. The route reports the strongest mechanism that
    actually produced information: derive when a proof attempt
    returned a result, probe when points executed, None when no
    mechanism engaged at all; a claim on the derive route reports
    derive. On the derive route the sampled rung falsifies only, and the
    note says how many points agreed."""
    meta = state.sampling_meta or dict(case.annotations)
    sampling = meta.get("mathema.equivalence.sampling") or {}
    checked = sampling.get("checked", 0)
    if case.cj.route == "derive":
        # the derive route reports its own unknown, as for any claim
        route = "derive"
    elif state.proof is not None and state.proof.status != "unliftable":
        # the symbolic mechanism genuinely engaged (undecided or an
        # uncorroborated disproof already handled upstream); unliftable
        # means it never got to reason at all
        route = "derive"
    elif state.executed:
        route = "probe"
    else:
        route = None
    if case.cj.route == "derive":
        said = (f"neither the canonical forms nor the symbolic difference "
                f"could settle equivalence, and the {checked} shared points "
                f"sampled found no disagreement, which on the derive route "
                f"is not a verdict")
    else:
        said = (f"neither the canonical forms, the symbolic difference, "
                f"nor sampling ({checked} evaluable points) could settle "
                f"equivalence")
    return Probe(case.cj.name, case.statement, "unknown", route=route,
                 sketch=(state.proof.sketch if state.proof is not None
                         else None),
                 note=f"{case.note}; {said}"
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
                "domain: both sides read as expressions whose difference "
                "simplifies to zero")
    return None


@dataclass(frozen=True)
class BodyEquivalence:
    """What `prove_bodies_equal` found about two lifted bodies.

    `verdict` is `proven`, `falsified` or `unknown`. `rung` names the
    derive rung that reached it: `form` (the two bodies have one
    canonical form), `symbolic` (their difference, read symbolically,
    vanishes on the domain, or a disproof from it reproduced on both),
    `closed-forms` (their closed forms are identical), or None when no
    rung engaged. A falsification carries `witness`, the executed
    point and what each side did there, and `point`, the arguments by
    the left body's parameter names. `meta` holds the corroboration
    (`reproduced`, or `uncorroborated` for a disproof no executed point
    reproduced) and `mathema.timeout` when the cap fired.
    """
    verdict: str
    rung: str | None
    sketch: str | None = None
    witness: str | None = None
    point: dict | None = None
    note: str | None = None
    meta: dict = field(default_factory=dict)


def prove_bodies_equal(left: Document | str, right: Document | str,
                       domain: dict, *,
                       siblings: dict | None = None) -> BodyEquivalence:
    """Whether two lifted bodies compute the same function on `domain`.

    `left` and `right` are the documents frontends wrote, each as a
    document or as KOINE text. `domain` maps the left body's parameter
    names to their bounds: a bound as a claim's domain holds it (what
    a registered equivalence family receives), its text (`"(0, inf)"`),
    or a list `[lo, hi]` for a closed interval. The right body's
    parameters align with the left's by position. The answer's
    `meta["mathema.domain"]` states each bound as it was read.
    `siblings` binds the other functions either body calls, as
    `sibling_scope` takes them. The answer is the mathematics line of
    `f =:= g`, which is exact, so it takes no tolerance.

    The derive rungs of `f =:= g` run on the engine's rendering of each
    body, under the extensive wall-clock cap: one canonical form, the
    symbolic difference, the closed forms. Nothing is sampled. A
    falsification stands only at a point executed on both bodies, where
    the two compared exactly disagree, however small the difference; a
    disproof no executed point reproduces is `unknown`. A point where
    both bodies refuse is agreement when they raise the same exception;
    when the two documents name different languages, the bodies run in
    different runtimes and their exception names are not compared, so
    a refusal on one side matches any refusal on the other.

    Raises:
        ValueError: a document the engine does not take (the message
            says why), or a `domain` name that is not a parameter of
            `left`.
    """
    import types

    from ._timeout import EXTENSIVE_TIMEOUT_SECONDS, _with_timeout
    from .koine.canonical import koine_hash, unresolved_calls
    from .koine.facts import (_document, facts_from_koine, materialised,
                              sibling_documents)

    ldoc, rdoc = _document(left), _document(right)
    lfacts, rfacts = facts_from_koine(ldoc), facts_from_koine(rdoc)
    unknown_names = sorted(set(domain or {}) - set(lfacts.params))
    if unknown_names:
        raise ValueError(f"domain names {', '.join(unknown_names)}, not a "
                         f"parameter of the left body ({', '.join(lfacts.params)})")
    bounds = {name: _read_bound(name, b) for name, b in (domain or {}).items()}
    stated = {"mathema.domain": _stated_domain(bounds)}
    if len(lfacts.params) != len(rfacts.params):
        return BodyEquivalence(
            "unknown", None,
            note=f"arity differs (the left body takes {len(lfacts.params)}, "
                 f"the right {len(rfacts.params)}), positional equivalence "
                 f"is not meaningful", meta=stated)
    same_runtime = ldoc.language is not None and ldoc.language == rdoc.language
    docs = sibling_documents(siblings)
    if not (unresolved_calls(ldoc, docs) or unresolved_calls(rdoc, docs)) \
            and koine_hash(ldoc, docs) == koine_hash(rdoc, docs) \
            and (not same_runtime or _refusals(ldoc) == _refusals(rdoc)):
        return BodyEquivalence(
            "proven", "form",
            sketch=f"the two bodies have one canonical form "
                   f"({koine_hash(ldoc, docs)})", meta=stated)
    case = _Case(cj=types.SimpleNamespace(name="bodies", tolerance=None),
                 statement="", note="", cj_domain=bounds,
                 fn=materialised(ldoc, siblings), facts=lfacts,
                 gfn=materialised(rdoc, siblings), gfacts=rfacts,
                 rhs_name="g", annotations={},
                 compare_refusals=same_runtime)
    try:
        answer = _with_timeout(lambda: _derive_bodies(case),
                               EXTENSIVE_TIMEOUT_SECONDS)
    except TimeoutError:
        answer = BodyEquivalence(
            "unknown", None,
            note=f"the derive rungs did not finish within the extensive "
                 f"cap ({EXTENSIVE_TIMEOUT_SECONDS}s)",
            meta={"mathema.timeout": "extensive"})
    return replace(answer, meta={**stated, **answer.meta})


def _read_bound(name: str, bound):
    """Intent:
        One parameter's bound as a claim's domain holds it: text read
        as the binding `<name> in <text>`, a list or a stored mapping
        read as `domain_bound_from_json` reads it, any other bound
        kept as given.

    Raises:
        ValueError: text that does not read as a bound.
    """
    from .domain import domain_bound_from_json, parse_binding
    if isinstance(bound, str):
        read = parse_binding(f"{name} in {bound}")
        if read is None:
            raise ValueError(f"{name}: {bound!r} does not read as a bound")
        return read[1]
    if isinstance(bound, (list, dict)):
        return domain_bound_from_json(bound)
    return bound


def _stated_domain(bounds: dict) -> dict:
    """Intent:
        Each bound rendered as the domain text a record shows.
    """
    from .domain import render_domain_bound
    out = {}
    for name, bound in bounds.items():
        try:
            out[name] = render_domain_bound(bound)
        except Exception:
            out[name] = repr(bound)
    return out


def _refusals(doc) -> list:
    """Intent:
        The exception type every `failure::raise` in `doc`'s body
        names, in body order.
    """
    from .koine.facts import _terms
    from .koine.syntax import Str
    return [t.args[0].value for t in _terms(doc.first("body"))
            if t.head == "failure::raise" and t.args
            and isinstance(t.args[0], Str)]


def _derive_bodies(case: _Case) -> BodyEquivalence:
    """Intent:
        The symbolic and closed-form rungs on two materialised bodies,
        with a disproof that carries no executed witness checked at its
        point on both sides.
    """
    state = _LadderState()
    probe = _rung_symbolic(case, state)
    if probe is None and state.proof is not None \
            and state.proof.status == "disproven":
        return _corroborated(case, state.proof)
    if probe is None and state.raise_note is not None:
        probe = _raise_region_witness(case, state)
    if probe is None:
        probe = _rung_closed_forms(case, state)
    if probe is None:
        engaged = (state.proof is not None
                   and state.proof.status != "unliftable")
        note = ("neither the canonical forms, the symbolic difference, nor "
                "the closed forms settle it")
        if state.raise_note:
            note += f"; {state.raise_note}"
        return BodyEquivalence(
            "unknown", "symbolic" if engaged else None,
            sketch=state.proof.sketch if state.proof is not None else None,
            note=note)
    meta = dict(probe.meta or {})
    rung = meta.pop("mathema.equivalence.rung", None)
    point = None
    if probe.verdict == "falsified" and state.proof is not None:
        args = _witness_args(case, state.proof)
        point = dict(zip(case.facts.params, args)) if args else None
    return BodyEquivalence(probe.verdict, rung, sketch=probe.sketch,
                           witness=probe.counterexample, point=point,
                           note=(probe.note or "").lstrip("; ") or None,
                           meta=meta)


def _raise_region_witness(case: _Case, state: _LadderState) -> Probe | None:
    """Intent:
        A falsification at a point inside the domain where exactly one
        side raises: the two sides' complete raise regions (whatever
        exception raises them) differ there, and both sides executed at
        that point confirm it. None when the regions cannot be read,
        do not differ, or no point of the difference reproduces.
    """
    import sympy

    from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
    from .symbolic import ProofResult

    def difference():
        f_regions = _raise_regions(case.fn, case.facts, case.cj_domain,
                                   case.facts.params[0])
        g_domain = {case.gfacts.params[0]:
                    case.cj_domain.get(case.facts.params[0])}
        g_regions = _raise_regions(case.gfn, case.gfacts, g_domain,
                                   case.facts.params[0])
        if f_regions is None or g_regions is None:
            return None
        return sympy.SymmetricDifference(_union(f_regions.values()),
                                         _union(g_regions.values()))

    try:
        region = _with_timeout(difference, FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    point = _point_in(region)
    if point is None:
        return None
    proof = ProofResult("disproven", sketch=state.raise_note,
                        witness={case.facts.params[0]: point})
    probe = _raise_witness_probe(case, proof)
    if probe is not None:
        state.proof = proof
    return probe


def _point_in(region) -> float | None:
    """Intent:
        One real point of a sympy set of reals: the first member of a
        finite set, the midpoint of a bounded interval, a point one
        unit inside a half-bounded one, the first piece's point for a
        union. None for an empty or unrecognised set.
    """
    import sympy
    if region is None or region.is_empty is not False:
        return None
    if isinstance(region, sympy.Union):
        for part in region.args:
            point = _point_in(part)
            if point is not None:
                return point
        return None
    if isinstance(region, sympy.FiniteSet):
        return float(min(region))
    if isinstance(region, sympy.Interval):
        lo, hi = region.start, region.end
        if lo.is_finite and hi.is_finite:
            return float((lo + hi) / 2)
        if lo.is_finite:
            return float(lo + 1)
        if hi.is_finite:
            return float(hi - 1)
        return 0.0
    return None


def _corroborated(case: _Case, proof) -> BodyEquivalence:
    """Intent:
        A symbolic disproof checked at its own point: both bodies run
        there and compared exactly (`_exact_disagreement`), and the pair
        is falsified when they disagree (a raise against a value, a
        refusal of another type within one runtime, or values that
        differ at all); `unknown` with the engine-bug flag otherwise.
    """
    found = _exact_disagreement(case, proof, "g", named=True)
    if found is not None:
        cx, args = found
        return BodyEquivalence(
            "falsified", "symbolic", sketch=proof.sketch, witness=cx,
            point=dict(zip(case.facts.params, args)),
            note="the two bodies disagree at the executed point",
            meta={"mathema.corroboration": "reproduced"})
    return BodyEquivalence(
        "unknown", "symbolic", sketch=proof.sketch,
        note="derive found the two bodies different, but no executed "
             "point reproduces it, which is probably a mathema bug worth "
             "reporting",
        meta={"mathema.corroboration": "uncorroborated"})
