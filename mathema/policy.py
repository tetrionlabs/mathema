# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Policy claims: what a function does with a value that is not there.

A policy claim names a kind of missing input, a parameter, optionally one
member, and one of five behaviours:

    missing(f, x) propagates
    absent(f, x) raises(TypeError)
    missing(f, xs, null) drops
    absent(f) raises
    assuming count(xs) >= 1, missing(f, xs) drops

`absent` is the object itself not there (a `None` argument); `missing`
is a hole in a slot (`nan`, a `None` element, `pd.NA`). The behaviours
are counted in no-value slots (`_missing_policy`): `raises`, `drops`,
`propagates`, `converts`, `introduces`. Without a parameter the claim
covers every parameter that admits the kind; without a member, every
member of the class; with a premise, only the calls whose inputs meet
it, so two premised rows can state one behaviour each for calls the
premises partition.

A policy claim is decided on the calls the function already made in the
same check (value claims, their companions, a proof that executed every
point), and on a floor of its own only for a parameter and member no
other claim executed. Its source says where it came from: `stated` by
the author, `derived` from a guard in the body or from a library's
policy row the body calls, `default` for a kind the type alone admits
(a hole propagates, an absence raises), `observed` for a kind the
author admitted, where there is no default.
"""
from __future__ import annotations

import contextvars
import re
from contextlib import contextmanager
from dataclasses import dataclass, field, replace

BEHAVIOURS = ("raises", "drops", "propagates", "converts", "introduces")
KINDS = ("missing", "absent")

#: the word each kind is also spelled
_KIND_WORDS = {"missing": "missing", "∅": "missing", "absent": "absent",
               "None": "absent"}
#: the older predicate words, read as the behaviour they name
_BEHAVIOUR_WORDS = {**{b: b for b in BEHAVIOURS}, "removed": "drops"}

_SELECTOR = re.compile(
    r"^\s*(?P<kind>missing|absent|∅|None)\s*\(\s*f\s*"
    r"(?:,\s*(?P<param>[A-Za-z_]\w*)\s*(?:,\s*(?P<member>[A-Za-z_][\w:]*)\s*)?)?\)"
    r"(?:\s+(?P<behaviour>[a-z]+)(?:\s*\(\s*(?P<exc>[A-Za-z_][\w.]*)\s*\))?)?\s*$")
_PREDICATE = re.compile(
    r"^\s*(?P<kind>missing|absent)_(?P<behaviour>[a-z]+)\s*\(\s*f\s*"
    r"(?:,\s*(?P<param>[A-Za-z_]\w*)\s*(?:,\s*(?P<member>[A-Za-z_][\w:]*)\s*)?)?\)\s*$")


@dataclass(frozen=True)
class Policy:
    """One policy claim: the kind, the parameter (None for every
    parameter), the member (None for the whole class), the behaviour
    (None when no word states it), the exception a `raises` names, the
    premise its calls must meet, and where it came from."""
    kind: str
    parameter: "str | None" = None
    member: "str | None" = None
    behaviour: "str | None" = None
    exception: "str | None" = None
    premise: str = ""
    source: str = "stated"


def parse_policy(text: str) -> "Policy | None":
    """Intent:
        The policy a claim's text states, in the selector form
        (`missing(f, x) propagates`, `absent(f, x) raises(TypeError)`)
        or a predicate form (`missing_propagates(f, x)`), with an
        optional `assuming ...,` premise in front; None when the text is
        no policy claim.
    """
    body = (text or "").strip()
    premise = ""
    m = re.match(r"^\s*assuming\s+(?P<premise>.+?),\s*(?P<rest>(missing|absent|∅|None)"
                 r"(_[a-z]+)?\s*\(\s*f\b.*)$", body)
    if m:
        premise, body = m.group("premise").strip(), m.group("rest").strip()
    found = _SELECTOR.match(body)
    if found is None:
        found = _PREDICATE.match(body)
        if found is None:
            return None
    words = found.groupdict()
    behaviour = words.get("behaviour")
    if behaviour is not None:
        behaviour = _BEHAVIOUR_WORDS.get(behaviour)
        if behaviour is None:
            return None
    kind = _KIND_WORDS[words["kind"]]
    return Policy(kind=kind, parameter=words.get("param"), member=words.get("member"),
                  behaviour=behaviour, exception=words.get("exc"), premise=premise)


def policy_text(policy: Policy, premise: bool = True) -> str:
    """The canonical text of a policy claim, the selector form:
    `missing(f, xs, null) raises(TypeError)`, with `assuming ...,` in
    front when it has a premise."""
    target = "f" + (f", {policy.parameter}" if policy.parameter else "") + \
        (f", {policy.member}" if policy.member else "")
    word = ""
    if policy.behaviour:
        word = " " + policy.behaviour + (f"({policy.exception})"
                                         if policy.exception else "")
    text = f"{policy.kind}({target}){word}"
    if premise and policy.premise:
        text = f"assuming {policy.premise}, {text}"
    return text


# --- the calls one check made --------------------------------------------

@dataclass
class Call:
    """One call at a missing input: its arguments by name, what it
    returned or raised, and the claim that made it."""
    point: dict
    output: object = None
    raised: "str | None" = None
    claim: "str | None" = None


@dataclass
class Batch:
    """Every call at a missing input one check made, and how many draws
    each claim ran."""
    calls: list = field(default_factory=list)
    draws: dict = field(default_factory=dict)
    origins: dict = field(default_factory=dict)


_BATCH: contextvars.ContextVar = contextvars.ContextVar("mathema_policy_batch",
                                                        default=None)
_CLAIM: contextvars.ContextVar = contextvars.ContextVar("mathema_policy_claim",
                                                        default=None)


@contextmanager
def batch():
    """The batch of calls the enclosing check collects into; a new one
    only at the outermost check."""
    current = _BATCH.get()
    if current is not None:
        yield current
        return
    token = _BATCH.set(Batch())
    try:
        yield _BATCH.get()
    finally:
        _BATCH.reset(token)


def active_batch() -> "Batch | None":
    return _BATCH.get()


@contextmanager
def claim_scope(name: "str | None"):
    """Calls made inside are filed under the claim `name`."""
    token = _CLAIM.set(name)
    try:
        yield
    finally:
        _CLAIM.reset(token)


def record_call(point: dict, output=None, raised: "str | None" = None) -> None:
    """File one call at a missing input into the active batch."""
    current = _BATCH.get()
    if current is None:
        return
    current.calls.append(Call(dict(point), output, raised, _CLAIM.get()))


def note_draws(claim: str, n: "int | None", origin: "dict | None") -> None:
    """Remember how many draws a claim ran, and who admitted each kind
    for each parameter it bound."""
    current = _BATCH.get()
    if current is None:
        return
    if n:
        current.draws[claim] = max(n, current.draws.get(claim, 0))
    for p, kinds in (origin or {}).items():
        for kind, who in kinds.items():
            if current.origins.get((p, kind), "type") == "type":
                current.origins[(p, kind)] = who


# --- evidence --------------------------------------------------------------

def _members_in(value, kind: str) -> list:
    """The member words of `kind` a value holds."""
    from ._missing_policy import no_value_slots
    return list(dict.fromkeys(s.member for s in no_value_slots(value).slots
                              if s.kind == kind))


def _premise_holds(premise: str, point: dict) -> bool:
    """Whether a call's inputs meet a policy's premise (`count(xs) >= 1`),
    read in the claim's own words over the arguments as the claim sees
    them; a premise that cannot be read at this point is not met."""
    if not premise:
        return True
    from ._linalg_eval import FUNCTIONS, as_array
    env = {**FUNCTIONS, **{p: as_array(v) for p, v in point.items()}}
    try:
        return bool(eval(compile(premise, "<premise>", "eval"),
                         {"__builtins__": {}}, env))
    except Exception:
        return False


def _relevant(calls: list, param: str, kind: str, member: "str | None",
              premise: str) -> list:
    return [c for c in calls if param in c.point
            and (member in _members_in(c.point[param], kind) if member
                 else _members_in(c.point[param], kind))
            and _premise_holds(premise, c.point)]


def _behaviour_of(call: Call) -> str:
    from ._missing_policy import classify_call
    return classify_call(call.point, call.output, call.raised)


def _raised_matches(raised: "str | None", expected: "str | None") -> bool:
    """Whether an exception name is the one a `raises(...)` names, or a
    subclass of a built-in one."""
    if expected is None or raised is None:
        return True
    if raised == expected.rsplit(".", 1)[-1]:
        return True
    import builtins
    got, want = getattr(builtins, raised, None), getattr(builtins, expected, None)
    return (isinstance(got, type) and isinstance(want, type)
            and issubclass(got, want))


def _floor_points(fn, facts, param: str, kind: str, members: list,
                  domain: dict) -> list:
    """The points a policy row runs on its own: each member of the kind
    at `param` (as the whole value for a scalar, in the floor's
    degenerate vectors for a vector), the other parameters drawn inside
    their domains."""
    import random

    from . import _floor
    from ._sampling import _RNG_SEED
    from .domain import member as member_sentinel, realise_sentinel
    from .probing import _synth
    from .runtime_types import SEQUENCE_KINDS
    rng = random.Random(_RNG_SEED)
    kinds = {p: facts.param_kinds.get(p, "unknown") for p in facts.params}
    from .probing import signature_defaults
    defaulted = signature_defaults(fn)
    others = {q: _synth(k, rng, (domain or {}).get(q)) for q, k in kinds.items()
              if q != param and q not in defaulted}
    values: list = []
    container = kinds.get(param) in SEQUENCE_KINDS
    if kind == "absent":
        values = [None]
    elif container:
        holes = [v for w in members for v in realise_sentinel(member_sentinel(w))]
        base = _synth("sequence", rng, (domain or {}).get(param), length=3)
        for item in _floor.vector_floor(holes, admits_zero=False, length_free=True):
            made = item(base)
            if made is not None and not isinstance(made, _floor._Absent) \
                    and any(_members_in(made, "missing")):
                values.append(made)
    else:
        values = [v for w in members for v in realise_sentinel(member_sentinel(w))]
    return [{**others, param: v} for v in values]


def _run_floor(fn, facts, points: list) -> list:
    from .probing import _pinned_float_env
    from .runtime_types import calling
    call = calling(fn, facts)
    out = []
    for point in points:
        try:
            with _pinned_float_env():
                value = call(**point)
        except Exception as exc:
            out.append(Call(point, None, type(exc).__name__, None))
            continue
        out.append(Call(point, value, None, None))
    return out


def _evidence(calls: list, current: "Batch | None", floor: bool) -> str:
    """Where a verdict came from: `on the 57 draws of c`, `on its own
    floor (6 draws)`."""
    if floor:
        return f"on its own floor ({len(calls)} draw{'s' if len(calls) != 1 else ''})"
    claims = list(dict.fromkeys(c.claim for c in calls if c.claim))
    if len(claims) == 1 and current is not None and current.draws.get(claims[0]):
        return f"on the {current.draws[claims[0]]} draws of {claims[0]}"
    if claims:
        return "on the draws of " + ", ".join(claims)
    return f"on {len(calls)} call{'s' if len(calls) != 1 else ''}"


def _witness(call: Call) -> str:
    """`xs = [NA]: f raised TypeError`, `x = nan: f returned 1.0`."""
    from ._missing_words import point_shown, value_shown
    did = (f"f raised {call.raised}" if call.raised
           else f"f returned {value_shown(call.output)}")
    return f"{point_shown(call.point)}: {did}"


def _entry(call: Call, param: str, kind: str) -> str:
    """`nan in, 1.0 out`, `None in, raised TypeError`."""
    from ._missing_words import value_shown
    member = (_members_in(call.point.get(param), kind) or ["?"])[0]
    out = f"raised {call.raised}" if call.raised else f"{value_shown(call.output)} out"
    return f"{member} in, {out}"


def _decide(calls: list) -> dict:
    """`{behaviour: first call}` over the calls."""
    seen: dict = {}
    for c in calls:
        seen.setdefault(_behaviour_of(c), c)
    return seen


# --- a stated policy claim ------------------------------------------------

def adjudicate(cj, fn, facts, domain: dict, derived: "dict | None" = None):
    """Intent:
        The row for one stated policy claim `cj` (relation `policy`),
        decided on the calls the check already made, or on its own
        floor where none reached the parameter and member it names:
        `holds` when every call behaves as it says, `proven` when a
        guard in the body also says so, `falsified` with the executed
        witness otherwise, `unknown` when no call could be made.
    """
    from .records import Probe
    stated = parse_policy((f"{cj.assuming}, " if cj.assuming else "")
                          + f"{cj.lhs} {cj.rhs}".strip())
    statement = policy_text(stated)
    params = [stated.parameter] if stated.parameter else [
        p for p in facts.params if _admits(fn, p, stated.kind)]
    current = active_batch()
    rows_calls: list = []
    floor = False
    for p in params:
        found = _relevant(current.calls if current else [], p, stated.kind,
                          stated.member, stated.premise)
        if not found:
            members = [stated.member] if stated.member else _members_of(fn, p, stated.kind)
            points = [pt for pt in _floor_points(fn, facts, p, stated.kind, members,
                                                 domain)
                      if _premise_holds(stated.premise, pt)]
            found = _run_floor(fn, facts, points)
            floor = floor or bool(found)
        rows_calls += [(p, c) for c in found]
    meta = {"mathema.policy": {"kind": stated.kind, "parameter": stated.parameter,
                               "member": stated.member, "behaviour": stated.behaviour,
                               "exception": stated.exception, "premise": stated.premise,
                               "source": "stated"}}
    if not rows_calls:
        return Probe(cj.name, statement, "unknown", route="probe",
                     note=(f"no call reached a {'missing' if stated.kind == 'missing' else 'absent'} "
                           f"{stated.parameter or 'parameter'}, so nothing says what f does "
                           f"there; bind the parameter in a claim that admits it"),
                     meta=meta)
    calls = [c for _p, c in rows_calls]
    evidence = _evidence(calls, current, floor)
    meta["mathema.policy"]["evidence"] = evidence
    wrong = next((c for p, c in rows_calls
                  if _behaviour_of(c) != stated.behaviour
                  or (stated.behaviour == "raises"
                      and not _raised_matches(c.raised, stated.exception))), None)
    if wrong is not None:
        p = next(pp for pp, c in rows_calls if c is wrong)
        did = _behaviour_of(wrong)
        reason = f"stated; f {did} instead: {_entry(wrong, p, stated.kind)}"
        nxt = (f"state {_stated_word(stated, did, wrong, calls)} if that is "
               f"intended, or change f")
        meta["mathema.policy"].update({"reason": reason, "next": nxt})
        return Probe(cj.name, statement, "falsified", n=len(calls), route="probe",
                     counterexample=_witness(wrong), note=f"{reason}; {nxt}",
                     meta=meta)
    guard = None
    for p in params:
        members = [stated.member] if stated.member else _members_of(fn, p, stated.kind)
        found_guards = [(derived or {}).get((p, stated.kind, m))
                        or (derived or {}).get((p, stated.kind, None)) for m in members]
        if found_guards and all(g and g[0] == stated.behaviour
                                and _raised_matches(g[1], stated.exception)
                                for g in found_guards):
            guard = found_guards[0]
    if guard is not None:
        reason = f"stated; derived from the guard on line {guard[2]}; confirmed {evidence}"
        meta["mathema.policy"]["reason"] = reason
        return Probe(cj.name, statement, "proven", n=len(calls), route="examine",
                     note=reason, meta=meta)
    reason = f"stated; confirmed {evidence}"
    meta["mathema.policy"]["reason"] = reason
    return Probe(cj.name, statement, "holds", n=len(calls), route="probe",
                 note=reason, meta=meta)


def _stated_word(policy: Policy, behaviour: str, call: Call,
                 calls: "list | None" = None) -> str:
    """The claim that states what `call` did, narrowed to the call's
    member when the other members behave otherwise."""
    member = policy.member
    if member is None and calls and policy.parameter:
        kind = policy.kind
        mine = _members_in(call.point.get(policy.parameter), kind)
        others = [c for c in calls
                  if not set(_members_in(c.point.get(policy.parameter), kind)) & set(mine)]
        if len(mine) == 1 and any(_behaviour_of(c) != behaviour for c in others):
            member = mine[0]
    word = replace(policy, member=member, behaviour=behaviour,
                   exception=call.raised if behaviour == "raises" else None)
    return f"`{policy_text(word)}`"


def _admits(fn, param: str, kind: str) -> bool:
    from .domain import NO_ANNOTATION
    from .types import missing_policy_from_signature
    policy = missing_policy_from_signature(fn).get(param, NO_ANNOTATION)
    return bool(policy.absent) if kind == "absent" else bool(policy.members)


def _members_of(fn, param: str, kind: str) -> list:
    from .domain import NO_ANNOTATION
    from .types import missing_policy_from_signature
    if kind == "absent":
        return ["None"]
    policy = missing_policy_from_signature(fn).get(param, NO_ANNOTATION)
    return list(policy.members) or ["nan"]


# --- what the body says ----------------------------------------------------

def guard_policies(facts) -> dict:
    """Intent:
        The policy each guard in the body states, `{(param, kind, member):
        (behaviour, exception, line)}`, member None for the whole class:
        `if x is None: raise TypeError` states `absent(f, x)
        raises(TypeError)`, `if x != x: return 0.0` states `missing(f,
        x, nan) drops`. `x is None` covers absence only, `x != x` and
        `isnan(x)` the member `nan`, `isna(x)` every member and absence.
        A guard that returns `None` passes an absence on and turns a
        hole into an absence; one that returns `nan` passes a hole on
        and turns an absence into a hole; any other return drops.
    """
    import ast
    tree = getattr(facts, "tree", None)
    if tree is None:
        return {}
    params = set(facts.params)
    out: dict = {}

    def covered(test) -> list:
        keys: list = []
        for node in ast.walk(test):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) \
                    and node.left.id in params and len(node.ops) == 1:
                op, right = node.ops[0], node.comparators[0]
                if isinstance(op, (ast.Is, ast.Eq)) and isinstance(right, ast.Constant) \
                        and right.value is None:
                    keys.append((node.left.id, "absent", "None"))
                if isinstance(op, ast.NotEq) and isinstance(right, ast.Name) \
                        and right.id == node.left.id:
                    keys.append((node.left.id, "missing", "nan"))
            if isinstance(node, ast.Call) and node.args \
                    and isinstance(node.args[0], ast.Name) and node.args[0].id in params:
                name = (node.func.attr if isinstance(node.func, ast.Attribute)
                        else getattr(node.func, "id", ""))
                if name == "isnan":
                    keys.append((node.args[0].id, "missing", "nan"))
                if name in ("isna", "isnull"):
                    keys += [(node.args[0].id, "missing", None),
                             (node.args[0].id, "absent", "None")]
        return keys

    def returned(body) -> "str | None":
        for stmt in body:
            if isinstance(stmt, ast.Return):
                value = stmt.value
                if value is None or (isinstance(value, ast.Constant) and value.value is None):
                    return "None"
                text = ast.unparse(value)
                if "nan" in text:
                    return "nan"
                return "value"
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or isinstance(node.test, ast.UnaryOp):
            continue
        keys = covered(node.test)
        if not keys:
            continue
        raise_stmt = next((s for s in node.body if isinstance(s, ast.Raise)), None)
        back = returned(node.body)
        for p, kind, member in keys:
            if raise_stmt is not None:
                exc = raise_stmt.exc
                name = None
                if isinstance(exc, ast.Call):
                    exc = exc.func
                if isinstance(exc, ast.Name):
                    name = exc.id
                elif isinstance(exc, ast.Attribute):
                    name = exc.attr
                out.setdefault((p, kind, member), ("raises", name, node.lineno))
            elif back is not None:
                if back == "value":
                    behaviour = "drops"
                elif back == "None":
                    behaviour = "propagates" if kind == "absent" else "converts"
                else:
                    behaviour = "propagates" if kind == "missing" else "converts"
                out.setdefault((p, kind, member), (behaviour, None, node.lineno))
    return out


# --- the rows a record carries for every parameter -------------------------

def _why_admitted(fn, param: str, kind: str, origin: str) -> str:
    """Why a kind reaches a parameter, as the row says it: `x is
    Optional[float], so None is promised`, `the claim lists None for x`."""
    from .conjecture import _annotation_words
    if origin == "optional":
        return f"{param} is {_annotation_words(fn, param)}, so None is promised"
    if origin == "listed":
        word = "None" if kind == "absent" else "a missing value"
        return f"the claim lists {word} for {param}"
    word = "None" if kind == "absent" else "a missing value"
    return f"the claim admits {word} for {param}"


def _plain_type(fn, param: str) -> str:
    """A parameter's annotation without its `None`: `float` for
    `Optional[float]`."""
    from .conjecture import _annotation_words
    text = _annotation_words(fn, param) or "float"
    m = re.match(r"^Optional\[(.+)\]$", text)
    if m:
        return m.group(1)
    parts = [t.strip() for t in text.split("|") if t.strip() not in ("None", "NoneType")]
    return " | ".join(parts) or text


def default_rows(fn, facts, domain: dict, covered: set, name_of) -> list:
    """Intent:
        The policy rows a record carries for every parameter that admits
        a kind and no stated policy covers: a default for a kind the type
        alone admits (`missing(f, x) propagates` for a float, `absent(f,
        x) raises` for a parameter with no annotation), confirmed or
        contradicted by the calls; the observed behaviour for a kind the
        author admitted, where a raise stays unaccounted for until a
        claim states it; a derived row where a guard in the body states
        the behaviour. One row per member when the members behave
        differently.
    """
    from ._missing_words import DEFAULTS, value_shown
    from .domain import NO_ANNOTATION
    from .records import Probe
    from .types import missing_policy_from_signature
    current = active_batch()
    signature = missing_policy_from_signature(fn)
    guards = guard_policies(facts)
    composed = composed_policies(fn, facts)
    rows = []
    for p in facts.params:
        sig = signature.get(p, NO_ANNOTATION)
        for kind in KINDS:
            origin = (current.origins.get((p, kind)) if current else None)
            admitted = (sig.absent if kind == "absent" else bool(sig.members)) \
                or origin is not None
            if not admitted or (p, kind) in covered:
                continue
            if origin is None or origin == "type":
                origin = ("optional" if kind == "absent" and sig.annotated
                          and sig.absent else "type")
            done_members: set = set()
            guarded = any(k[0] == p and k[1] == kind for k in guards)
            # a library row composed through the body speaks for a kind
            # the type admits and no guard in the body decides; a kind the
            # author admitted stays observed (FM17)
            if p in composed and origin == "type" and not guarded \
                    and any(pol.kind == kind for pol in composed[p][1]):
                made = composed_rows(fn, facts, p, kind, composed[p][0],
                                     composed[p][1], name_of)
                rows += made
                done_members = {(r.meta or {}).get("mathema.policy", {}).get("member")
                                for r in made}
                if None in done_members:
                    continue
            calls = [c for c in _relevant(current.calls if current else [], p, kind,
                                          None, "")
                     if not done_members
                     or set(_members_in(c.point[p], kind)) - done_members]
            if done_members and not calls:
                continue
            floor = False
            if not calls:
                members = ["None"] if kind == "absent" else (list(sig.members) or ["nan"])
                calls = _run_floor(fn, facts, _floor_points(fn, facts, p, kind,
                                                            members, domain))
                floor = True
            if not calls:
                continue
            by_member: dict = {}
            for c in calls:
                for m in _members_in(c.point[p], kind):
                    by_member.setdefault(m, []).append(c)
            ways = {m: _decide(cs) for m, cs in by_member.items()}
            singles = {m: next(iter(w)) for m, w in ways.items() if len(w) == 1}
            split = (len(ways) > 1 and len(singles) == len(ways)
                     and len(set(singles.values())) > 1)
            groups = ([(m, by_member[m]) for m in ways] if split
                      else [(None, calls)])
            for member, cs in groups:
                rows.append(_default_row(fn, p, kind, member, cs, origin, sig,
                                         guards, current, floor, name_of,
                                         DEFAULTS, value_shown, Probe))
    return rows


def _default_row(fn, p, kind, member, calls, origin, sig, guards, current, floor,
                 name_of, DEFAULTS, value_shown, Probe):
    seen = _decide(calls)
    evidence = _evidence(calls, current, floor)
    guard = guards.get((p, kind, member)) or guards.get((p, kind, None)) or (
        guards.get((p, kind, "nan")) if kind == "missing" and member in (None, "nan")
        and set(_members_of(fn, p, kind)) <= {"nan"} else None)
    policy = Policy(kind=kind, parameter=p, member=member)
    meta_policy = {"kind": kind, "parameter": p, "member": member,
                   "evidence": evidence}
    meta = {"mathema.policy": meta_policy, "mathema.surface": "mathema"}

    def row(verdict, behaviour, exception, source, bracket, note=None, cx=None,
            route="probe", nxt=None):
        stated = replace(policy, behaviour=behaviour, exception=exception, source=source)
        meta_policy.update({"behaviour": behaviour, "exception": exception,
                            "source": source, "reason": bracket})
        if nxt:
            meta_policy["next"] = nxt
            note = note or f"{bracket}. {nxt}"
        statement = policy_text(stated)
        return Probe(name_of(stated), statement, verdict, n=len(calls), route=route,
                     counterexample=cx, note=note or f"{bracket}; {evidence}",
                     meta=meta)

    if len(seen) > 1:
        ways = "; ".join(f"{b} at {_witness(c)}" for b, c in seen.items())
        return row("falsified", None, None, "observed",
                   f"f treats a {kind} {p} more than one way: {ways}",
                   nxt=(f"state what f should do for each case with a premise, e.g. "
                        f"`assuming count({p}) >= 1, {kind}(f, {p}) drops`, or make f "
                        f"treat it one way"),
                   cx=_witness(next(iter(seen.values()))))
    (behaviour, call), = seen.items()
    exception = call.raised if behaviour == "raises" else None
    if guard is not None and guard[0] == behaviour:
        return row("proven", behaviour, exception, "derived",
                   f"derived from the guard on line {guard[2]}; confirmed {evidence}",
                   route="examine")
    if origin == "type":
        expected = DEFAULTS[kind]
        if behaviour == expected:
            if kind == "missing":
                members = ", ".join(sig.members) or "nan"
                what = (f"default: {p} has no annotation, so it may be {members}"
                        if sig.slot_type == "unannotated" else
                        f"default for a {sig.slot_type}: the type admits {members}")
                bracket = (f"{what}; change the word to raises or drops if f should "
                           f"do otherwise")
            else:
                bracket = (f"default: {p} has no annotation, so it may be None, and f "
                           f"raises on it; annotate {p} as float to exclude None, or "
                           f"keep this claim")
            return row("holds", behaviour, None, "default", bracket)
        entry = _entry(call, p, kind)
        bracket = (f"default for a {sig.slot_type}; f {behaviour} instead: {entry}"
                   if kind == "missing" and sig.slot_type != "unannotated" else
                   f"default: {p} may be missing; f {behaviour} instead: {entry}"
                   if kind == "missing" else
                   f"default: {p} may be None; f {behaviour} instead: {entry}")
        if behaviour == "drops":
            out = value_shown(call.output)
            nxt = (f"if {out} is the intended answer, write `{kind}(f, {p}) drops`; "
                   f"otherwise guard with `if {p} != {p}: raise ValueError` or "
                   f"return nan")
        elif behaviour == "raises":
            nxt = (f"if raising is intended, write `{kind}(f, {p}) raises({exception})`; "
                   f"otherwise make f return a value there")
        else:
            nxt = f"write `{kind}(f, {p}) {behaviour}` to accept it, or change f"
        stated_default = replace(policy, behaviour=expected, source="default")
        meta_policy.update({"behaviour": expected, "source": "default",
                            "reason": bracket, "next": nxt})
        return Probe(name_of(stated_default), policy_text(stated_default), "falsified",
                     n=len(calls), route="probe", counterexample=_witness(call),
                     note=f"{bracket}. {nxt}", meta=meta)
    why = _why_admitted(fn, p, kind, origin)
    if behaviour == "raises":
        bracket = (f"observed: {why}; f raised {exception} at "
                   f"{_witness(call).split(':', 1)[0]}")
        fix = (f"handle None in f, or state `{kind}(f, {p}) raises({exception})`, "
               f"or change the annotation to {_plain_type(fn, p)}"
               if origin == "optional" else
               f"handle it in f, or state `{kind}(f, {p}) raises({exception})`, or "
               f"remove it from the claim")
        return row("falsified", None, None, "observed", bracket,
                   nxt=fix, cx=_witness(call))
    return row("holds", behaviour, None, "observed",
               f"observed: {why}; f {behaviour}: {_entry(call, p, kind)}")


def row_name(policy: Policy) -> str:
    """The name a record gives a policy row mathema writes:
    `missing[x]`, `missing[xs, null]`, `absent[x]`."""
    inner = policy.parameter or "f"
    if policy.member:
        inner += f", {policy.member}"
    return f"{policy.kind}[{inner}]"


def contradicting_policies(statements: list) -> "str | None":
    """Intent:
        Why two of a function's policy claims cannot both hold, or None:
        the same kind, parameter, member and premise stated with two
        different behaviours (`missing(f, x) drops` beside `missing(f, x)
        propagates`).
    """
    seen: dict = {}
    for text in statements:
        stated = parse_policy(text or "")
        if stated is None or stated.behaviour is None:
            continue
        key = (stated.kind, stated.parameter, stated.member, stated.premise)
        other = seen.get(key)
        if other is not None and (other.behaviour, other.exception) != \
                (stated.behaviour, stated.exception):
            return (f"`{policy_text(other)}` and `{policy_text(stated)}` state two "
                    f"behaviours for one case; keep one, or give each a premise "
                    f"that tells the cases apart")
        seen.setdefault(key, stated)
    return None


# --- what a library's policy rows say, composed through the body ----------

_LIBRARY: dict = {}


def library_policies() -> dict:
    """`{library key: [Policy, ...]}` from the bundled compendium's policy
    rows (`numpy.mean: missing(f, a) propagates`), read once."""
    if _LIBRARY:
        return _LIBRARY
    import yaml

    from .compendium import _bundled_dir
    from .spec import claims_file_paths
    for path in claims_file_paths(_bundled_dir()):
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            continue
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            for row in entry.get("claims") or []:
                stated = parse_policy((row or {}).get("statement", ""))
                if stated is not None and stated.behaviour:
                    _LIBRARY.setdefault(key, []).append(stated)
    _LIBRARY.setdefault("", [])
    return _LIBRARY


def composed_policies(fn, facts) -> dict:
    """Intent:
        The policies a body inherits from the one library call it makes
        on a parameter, `{param: (key, [Policy, ...])}`: `return
        float(np.mean(xs))` inherits numpy.mean's rows, `return
        xs.mean()` on a `pandas.Series` pandas.Series.mean's, each
        restated over the parameter (`assuming count(xs) >= 1,
        missing(f, xs) drops`). A body that does anything else with the
        parameter inherits nothing.
    """
    import ast
    tree = getattr(facts, "tree", None)
    if tree is None:
        return {}
    returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value]
    if len(returns) != 1:
        return {}
    expr = returns[0].value
    while isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) \
            and expr.func.id in ("float", "int") and len(expr.args) == 1:
        expr = expr.args[0]
    if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Attribute):
        return {}
    from .runtime_types import realised_parameters
    scope = getattr(fn, "__globals__", {}) or {}
    rows = library_policies()
    runtime = {p: d.adapter for p, d in realised_parameters(facts).items()}
    owner = expr.func.value
    key = param = None
    if isinstance(owner, ast.Name) and owner.id in runtime and not expr.args:
        param, key = owner.id, f"{runtime[owner.id]}.{expr.func.attr}"
    elif isinstance(owner, ast.Name) and expr.args \
            and isinstance(expr.args[0], ast.Name) and expr.args[0].id in facts.params:
        module = getattr(scope.get(owner.id), "__name__", None)
        if module:
            param, key = expr.args[0].id, f"{module}.{expr.func.attr}"
    if key is None or key not in rows:
        return {}
    restated = []
    for policy in rows[key]:
        premise = re.sub(rf"\b{policy.parameter}\b", param, policy.premise) \
            if policy.parameter else policy.premise
        restated.append(replace(policy, parameter=param, premise=premise,
                                source="derived"))
    return {param: (key, restated)}


def composed_rows(fn, facts, param: str, kind: str, key: str, policies: list,
                  name_of) -> list:
    """The rows a parameter carries from a library's composed policy rows,
    each decided on the calls the check made: `proven` where the calls
    confirm it, `falsified` with the executed witness where they do not."""
    from .records import Probe
    current = active_batch()
    rows = []
    for policy in policies:
        if policy.kind != kind:
            continue
        calls = _relevant(current.calls if current else [], param, kind,
                          policy.member, policy.premise)
        if not calls:
            continue
        evidence = _evidence(calls, current, False)
        meta_policy = {"kind": kind, "parameter": param, "member": policy.member,
                       "behaviour": policy.behaviour, "exception": policy.exception,
                       "premise": policy.premise, "source": "derived",
                       "evidence": evidence}
        meta = {"mathema.policy": meta_policy, "mathema.surface": "mathema"}
        wrong = next((c for c in calls if _behaviour_of(c) != policy.behaviour
                      or (policy.behaviour == "raises"
                          and not _raised_matches(c.raised, policy.exception))), None)
        statement = policy_text(policy)
        if wrong is None:
            reason = f"composed through {key}'s policy row; confirmed {evidence}"
            meta_policy["reason"] = reason
            rows.append(Probe(name_of(policy), statement, "proven", n=len(calls),
                              route="examine", note=reason, meta=meta))
            continue
        did = _behaviour_of(wrong)
        reason = (f"composed through {key}'s policy row; f {did} instead: "
                  f"{_entry(wrong, param, kind)}")
        nxt = (f"state {_stated_word(policy, did, wrong, calls)} if that is "
               f"intended, or change f")
        meta_policy.update({"reason": reason, "next": nxt})
        rows.append(Probe(name_of(policy), statement, "falsified", n=len(calls),
                          route="probe", counterexample=_witness(wrong),
                          note=f"{reason}; {nxt}", meta=meta))
    return rows
