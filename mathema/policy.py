# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Policy claims: what a function does with a value that is not there.

A policy claim names a kind of missing input, a parameter or a path
from one, optionally one member, and one of five behaviours:

    missing(f, x) propagates
    absent(f, x) raises(TypeError)
    missing(f, xs, null) drops
    absent(f) raises
    assuming count(xs) >= 1, missing(f, xs) drops
    absent(f, o.note) raises(TypeError)
    absent(f, d.note, unset) drops
    missing(f, o.lines[*].qty) propagates

On a path, absence has two members: `null`, the field or key holding
`None`, and `unset`, a key left out, an index past the end or a step
below an absent object.

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

#: a parameter, or a path from one (`o.note`, `o.lines[*].qty`)
_TARGET = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[(?:\d+|\*)\])*"
_SELECTOR = re.compile(
    r"^\s*(?P<kind>missing|absent|∅|None)\s*\(\s*f\s*"
    rf"(?:,\s*(?P<param>{_TARGET})\s*(?:,\s*(?P<member>[A-Za-z_][\w:]*)\s*)?)?\)"
    r"(?:\s+(?P<behaviour>[a-z]+)(?:\s*\(\s*(?P<exc>[A-Za-z_][\w.]*)\s*\))?)?\s*$")
_PREDICATE = re.compile(
    r"^\s*(?P<kind>missing|absent)_(?P<behaviour>[a-z]+)\s*\(\s*f\s*"
    rf"(?:,\s*(?P<param>{_TARGET})\s*(?:,\s*(?P<member>[A-Za-z_][\w:]*)\s*)?)?\)\s*$")


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
    # `[(param or path, kind, member), ...]` the call held, when the
    # route that made it knew the paths its claim binds
    keys: "list | None" = None
    # the behaviour read by refilling the hole, when the route did
    behaviour: "str | None" = None
    # a call that returned a value no fill of the hole changed: evidence
    # against raises and propagates only
    indifferent: bool = False


@dataclass
class Batch:
    """Every call at a missing input one check made, and how many draws
    each claim ran."""
    calls: list = field(default_factory=list)
    draws: dict = field(default_factory=dict)
    origins: dict = field(default_factory=dict)
    # the calls where f gave None back from present inputs
    introduced: list = field(default_factory=list)


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


def record_call(point: dict, output=None, raised: "str | None" = None,
                keys: "list | None" = None, behaviour: "str | None" = None,
                indifferent: bool = False) -> None:
    """File one call at a missing input into the active batch."""
    current = _BATCH.get()
    if current is None:
        return
    current.calls.append(Call(dict(point), output, raised, _CLAIM.get(),
                              list(keys) if keys is not None else None, behaviour,
                              indifferent))


def record_introduced(point: dict) -> None:
    """File one call where f gave None back from present inputs."""
    current = _BATCH.get()
    if current is None:
        return
    current.introduced.append(Call(dict(point), None, None, _CLAIM.get()))


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
    # `len` counts every slot, `count` the value slots
    env = {"len": len, **FUNCTIONS, **{p: as_array(v) for p, v in point.items()}}
    try:
        return bool(eval(compile(premise, "<premise>", "eval"),
                         {"__builtins__": {}}, env))
    except Exception:
        return False


def _keys(call: Call) -> list:
    """`[(param or path, kind, member), ...]` a call held."""
    from ._missing_policy import keys_of
    return call.keys if call.keys is not None else keys_of(call.point)


def _members_at(call: Call, param: str, kind: str) -> list:
    """The member words of `kind` a call held at a parameter or a path
    (`o.note`), each once."""
    return list(dict.fromkeys(m for q, k, m in _keys(call) if q == param and k == kind))


def _relevant(calls: list, param: str, kind: str, member: "str | None",
              premise: str) -> list:
    out = []
    for c in calls:
        members = _members_at(c, param, kind)
        if (member in members if member else members) and _premise_holds(premise, c.point):
            out.append(c)
    return out


def _behaviour_of(call: Call) -> str:
    from ._missing_policy import classify_call, unseen_kinds
    if call.behaviour is not None:
        return call.behaviour
    return classify_call(call.point, call.output, call.raised,
                         unseen_kinds(call.point, _keys(call)))


#: the module namespace of the function under check, where an exception
#: name a call raised or a row states is looked up
_SCOPE: contextvars.ContextVar = contextvars.ContextVar("mathema_policy_scope",
                                                        default=None)


@contextmanager
def exceptions_of(fn):
    """Exception names read inside are looked up in `fn`'s module."""
    token = _SCOPE.set(getattr(fn, "__globals__", None) or {})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def _exception_type(name: str, scope: "dict | None" = None):
    """The exception class a name stands for: a builtin, one the
    function's module (`scope`, else the one under check) reaches
    (`MissingInput`, `np.linalg.LinAlgError`), or one a dotted name
    imports (`numpy.linalg.LinAlgError`); None for anything else."""
    import builtins
    import importlib
    head, *rest = name.split(".")
    found = getattr(builtins, head, None) if not rest else None
    if found is None:
        found = (scope if scope is not None else _SCOPE.get() or {}).get(head)
        for part in rest:
            found = getattr(found, part, None)
    if found is None and rest:
        module_name, _, attr = name.rpartition(".")
        try:
            found = getattr(importlib.import_module(module_name), attr, None)
        except Exception:
            found = None
    return found if isinstance(found, type) and issubclass(found, BaseException) else None


def _raised_matches(raised: "str | None", expected: "str | None") -> bool:
    """Whether an exception name is the one a `raises(...)` names, or a
    subclass of it, as the long form `raises(f(x), E)` reads it."""
    if expected is None or raised is None:
        return True
    if raised == expected.rsplit(".", 1)[-1]:
        return True
    got, want = _exception_type(raised), _exception_type(expected)
    return got is not None and want is not None and issubclass(got, want)


def _floor_points(fn, facts, param: str, kind: str, members: list,
                  domain: dict, cj=None) -> list:
    """The points a policy row runs on its own: each member of the kind
    at `param` (as the whole value for a scalar, in the floor's
    degenerate vectors for a vector, inside a column of the floor's
    tables for a table), the other parameters drawn inside their
    domains."""
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
    elif kinds.get(param) == "table":
        from .conjecture import _table_columns
        holes = [v for w in members for v in realise_sentinel(member_sentinel(w))]
        bound = (domain or {}).get(param)
        (length,) = _floor.sizes(bound, rng, (3, 3))
        base = {c: [_synth("float", rng, bound) for _ in range(length)]
                for c in _table_columns(param, cj, facts)}
        for item in _floor.table_floor(holes):
            made = item(base)
            if made is not None and not isinstance(made, _floor._Absent):
                values.append(made)
    elif container:
        holes = [v for w in members for v in realise_sentinel(member_sentinel(w))]
        bound = (domain or {}).get(param)
        (length,) = _floor.sizes(bound, rng, (3, 3))
        base = _synth("sequence", rng, bound, length=length)
        for item in _floor.vector_floor(holes, admits_zero=False,
                                        length_free=not any(_floor.fixed_sizes(bound))):
            made = item(base)
            if made is not None and not isinstance(made, _floor._Absent) \
                    and any(_members_in(made, "missing")):
                values.append(made)
    else:
        values = [v for w in members for v in realise_sentinel(member_sentinel(w))]
    order = list(facts.params)
    # the other parameters as drawn, then each scalar one at its corners
    variants = [others] + [{**others, q: end} for q in others
                           for end in _corners((domain or {}).get(q))
                           if kinds.get(q) not in SEQUENCE_KINDS]
    return [{q: point[q] for q in sorted(point, key=lambda q: order.index(q)
                                          if q in order else len(order))}
            for point in ({**base, param: v} for v in values for base in variants)]


def _corners(bound) -> list:
    """The finite ends of a scalar domain that lie inside it."""
    import math

    from .domain import bound_to_sympy_set, domain_contains
    if bound is None or getattr(bound, "dims", ()):
        return []
    try:
        import sympy
        region = bound_to_sympy_set(bound)
        ends = [float(region.inf), float(region.sup)]
        integral = bool(region.is_subset(sympy.S.Integers))
    except Exception:
        return []
    out = []
    for end in ends:
        if math.isinf(end):
            continue
        value = int(end) if integral else end
        if domain_contains(value, bound) and value not in out:
            out.append(value)
    return out


def _run_floor(fn, facts, points: list, domain: "dict | None" = None) -> list:
    """The calls f makes at `points`; with the claim's `domain`, a call at
    a hole is read by refilling it (`_missing_policy.refill`): one call
    per hole member; a call whose refill is inconclusive or not repeatable
    is left out, and one indifferent to the slot is filed as a drop marked
    indifferent."""
    from ._missing_policy import INCONCLUSIVE, INDIFFERENT, NOT_REPEATABLE, refill
    from .conjecture import _fill_value
    from .probing import _pinned_float_env
    from .runtime_types import calling
    call = calling(fn, facts)

    from .conjecture import _call_by_name

    def call_at(point: dict):
        try:
            with _pinned_float_env():
                return _call_by_name(call, point), None
        except Exception as exc:
            return None, type(exc).__name__
    fills = ({p: fill for p in facts.params
              if (fill := _fill_value((domain or {}).get(p))) is not None}
             if domain is not None else {})
    out = []
    for point in points:
        value, raised = call_at(point)
        pieces = refill(call_at, point, value, raised, fills) if fills else None
        if pieces is None:
            out.append(Call(point, value, raised, None))
            continue
        out.extend(Call(at, got, err, None, None,
                        "drops" if behaviour == INDIFFERENT else behaviour,
                        behaviour == INDIFFERENT)
                   for at, got, err, behaviour in pieces
                   if behaviour not in (INCONCLUSIVE, NOT_REPEATABLE))
    return out


def _present_calls(fn, facts, domain: dict, draws: int = 24) -> list:
    """Calls of f at inputs with nothing missing, each parameter drawn
    inside its domain, for what the result may be."""
    import random

    from ._sampling import _RNG_SEED
    from .probing import _synth, inputs_missing, signature_defaults
    rng = random.Random(_RNG_SEED + 3)
    defaulted = signature_defaults(fn)
    kinds = {p: facts.param_kinds.get(p, "unknown") for p in facts.params
             if p not in defaulted}
    points = []
    for _ in range(draws):
        point = {q: _synth(k, rng, (domain or {}).get(q)) for q, k in kinds.items()}
        if not inputs_missing(point.values()):
            points.append(point)
    return _run_floor(fn, facts, points)


def _base_claim(name: str) -> str:
    """A row's claim name as its author wrote it: `c0[float]` for the
    companion of a chained comparison's link `c0[link1][float]`."""
    return re.sub(r"\[link\d+\]", "", name or "")


def _and(words: list) -> str:
    """`a`, `a and b`, `a, b and c`."""
    words = list(words)
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _on_draws(calls: list, current: "Batch | None") -> str:
    """Whose draws made the calls: `on the 43 draws of c[float]`, the
    claim named as its author wrote it."""
    bases = list(dict.fromkeys(_base_claim(c.claim) for c in calls if c.claim))
    draws = current.draws if current else {}

    def count(base: str) -> int:
        # the count the claim's own row prints, else its parts' largest
        if base in draws:
            return draws[base]
        return max((n for k, n in draws.items() if _base_claim(k) == base), default=0)
    if len(bases) == 1:
        n = count(bases[0])
        return f"on the {n} draws of {bases[0]}" if n else f"on the draws of {bases[0]}"
    roots = list(dict.fromkeys(b.split("[", 1)[0] for b in bases))
    if len(roots) == 1 and bases:
        n = max([count(b) for b in bases] + [count(roots[0])])
        return f"on the {n} draws of {roots[0]}" if n else f"on the draws of {roots[0]}"
    if bases:
        return "on the draws of " + _and(bases)
    return f"on {len(calls)} call{'s' if len(calls) != 1 else ''}"


def _at(call: Call, param: "str | None") -> str:
    """The point of a call as the record shows it, the one parameter
    alone when it names one: `x = None`, `xs = [null, 0.609]`, and what
    a path reached when it names one: `d.note unset`."""
    from ._missing_policy import is_path
    from ._missing_words import path_shown, point_shown
    if param and is_path(param):
        found = next(((k, m) for q, k, m in _keys(call) if q == param), None)
        if found is not None:
            return path_shown(param, found[1], call.point, found[0])
    if param and param in call.point:
        return point_shown({param: call.point[param]})
    return point_shown(call.point)


def _confirmed(calls: list, current: "Batch | None", floor: bool,
               param: "str | None" = None) -> str:
    """The clause every bracket ends with: `confirmed on the 43 draws of
    c[float]`, or `confirmed by calling f at x = None` for calls made for
    the row alone."""
    if floor:
        points = list(dict.fromkeys(_at(c, param) for c in calls))
        shown = points[:3] + ([f"{len(points) - 3} more"] if len(points) > 3 else [])
        return f"confirmed by calling f at {_and(shown)}"
    return "confirmed " + _on_draws(calls, current)


def _witness(call: Call, param: "str | None" = None) -> str:
    """`xs = [NA]: f raised TypeError`, `x = nan: f returned 1.0`, and
    for a path what it reached: `d.note unset: f raised KeyError`."""
    from ._missing_policy import is_path
    from ._missing_words import point_shown, value_shown
    did = (f"f raised {call.raised}" if call.raised
           else f"f returned {value_shown(call.output)}")
    if param and is_path(param):
        return f"{_at(call, param)}: {did}"
    return f"{point_shown(call.point)}: {did}"


def _in_slot(call: Call, param: str, kind: str) -> bool:
    from ._missing_words import _in_slot as held_in_slot
    return kind == "missing" and held_in_slot(call.point.get(param))


def _entry(call: Call, param: str, kind: str) -> str:
    """`nan in, 1.0 out`, `a null slot in, TypeError`."""
    from ._missing_policy import is_path
    from ._missing_words import value_shown
    member = (_members_at(call, param, kind) or ["?"])[0]
    out = call.raised if call.raised else f"{value_shown(call.output)} out"
    if is_path(param):
        return f"{_at(call, param)}, {out}"
    if _in_slot(call, param, kind):
        return f"a {member} slot in, {out}"
    return f"{member} in, {out}"


def _decide(calls: list) -> dict:
    """`{behaviour: first call}` over the calls."""
    seen: dict = {}
    for c in calls:
        seen.setdefault(_behaviour_of(c), c)
    return seen


def _hole_column(calls: list, param: str) -> "str | None":
    """The one column of a table parameter every call's holes sit in,
    or None."""
    from ._missing_policy import _hole_word, _table_columns
    columns: set = set()
    for c in calls:
        cols = _table_columns(c.point.get(param))
        if cols is None:
            return None
        columns |= {k for k, cells in cols.items()
                    if any(_hole_word(v) is not None for v in cells)}
    return next(iter(columns)) if len(columns) == 1 else None


def _count_class(value, column: "str | None") -> "str | None":
    """`>= 1` when a container still holds a value slot (in `column` for
    a table), `== 0` when every slot is a hole, None for a scalar."""
    from ._missing_policy import _hole_word, _table_columns, no_value_slots
    if column is not None:
        cells = (_table_columns(value) or {}).get(column) or []
        return ">= 1" if any(_hole_word(v) is None for v in cells) else "== 0"
    slots = no_value_slots(value)
    if slots.shape == ():
        return None
    return ">= 1" if slots.count() < slots.capacity() else "== 0"


def _cases(calls: list, param: str, kind: str, member: "str | None" = None,
           admitted: "list | None" = None) -> "list | None":
    """Intent:
        The policy rows that state what `calls` did at a missing `param`,
        one per (member, count class) observed: a member that behaves one
        way at every count is one row, one that behaves one way while
        values remain and another when every slot is a hole is a premised
        pair (`assuming count(xs) >= 1, ...` beside `assuming count(xs) ==
        0, ...`, a frame's count naming its column), and members that all
        behave alike share one row without a member, unless `member`
        names one or some member of `admitted` was not seen. None when
        some case holds more than one behaviour.
    """
    column = _hole_column(calls, param)

    def classes_by(classify) -> "dict | None":
        seen: dict = {}
        for c in calls:
            members = _members_at(c, param, kind)
            if len(members) != 1:
                continue
            cls = classify(c.point.get(param)) if kind == "missing" else None
            b = _behaviour_of(c)
            seen.setdefault(members[0], {}).setdefault(cls, set()).add(
                (b, c.raised if b == "raises" else None))
        if not seen or any(len(ways) > 1 for classes in seen.values()
                           for ways in classes.values()):
            return None
        return seen

    # a count premise first; where the count cannot tell the cases apart
    # (`[null]` and `[null, null]` both have no value slot), a length one
    seen = classes_by(lambda v: _count_class(v, column))
    count = f"count({param}.{column})" if column else f"count({param})"
    order: tuple = (">= 1", "== 0")
    if seen is None and not column:
        seen = classes_by(lambda v: None if _count_class(v, None) is None
                          else ("== 1" if len(v) == 1 else ">= 2"))
        count, order = f"len({param})", ("== 1", ">= 2")
    if seen is None:
        return None
    per_member: dict = {}
    for m, classes in seen.items():
        ways = {cls: next(iter(w)) for cls, w in classes.items()}
        if len(set(ways.values())) == 1:
            per_member[m] = ((None,) + next(iter(ways.values())),)
        else:
            per_member[m] = tuple((cls,) + ways[cls] for cls in order if cls in ways)
    alike = len(set(per_member.values())) == 1
    groups: list
    if member is not None:
        groups = [(member, next(iter(per_member.values())))] if alike else []
    elif alike and (admitted is None or set(per_member) >= set(admitted)):
        groups = [(None, next(iter(per_member.values())))]
    else:
        groups = list(per_member.items())
    if not groups:
        return None
    out = []
    for m, rows in groups:
        for cls, b, exc in rows:
            out.append(Policy(kind=kind, parameter=param, member=m, behaviour=b,
                              exception=exc, premise=f"{count} {cls}" if cls else ""))
    return out


def _written(policies: list) -> str:
    """`a`, `a` and `b` for claims to write."""
    return _and([f"`{policy_text(p)}`" for p in policies])


# --- a stated policy claim ------------------------------------------------

def none_default_misspecified(fn, params: "list | None" = None) -> "str | None":
    """Why a parameter annotated with a type that has no None, yet
    defaulting to None, leaves its absence undecided (`x: float = None`),
    or None: the sentence for the first such parameter."""
    import inspect
    import typing
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    for p, param in sig.parameters.items():
        if params is not None and p not in params:
            continue
        ann = param.annotation
        if param.default is not None or ann is inspect.Parameter.empty:
            continue
        if isinstance(ann, str):
            text = ann
            if any(w in text for w in ("None", "Optional", "Any", "object")):
                continue
        else:
            if ann in (typing.Any, object) or _admits_none(ann):
                continue
            text = getattr(ann, "__name__", None) or repr(ann).replace("typing.", "")
        return (f"{p} is annotated {text} but defaults to None; annotate it "
                f"Optional[{text}] or change the default")
    return None


def adjudicate(cj, fn, facts, domain: dict, derived: "dict | None" = None):
    """Intent:
        The row for one stated policy claim `cj` (relation `policy`),
        decided on the calls the check already made, or by calling f
        where none reached the parameter and member it names: `holds`
        when every call behaves as it says, `proven` when a guard in the
        body also says so, `falsified` with the executed witness
        otherwise, `unknown` with the reason when no call could decide
        it.
    """
    from .records import Probe
    stated = parse_policy((f"{cj.assuming}, " if cj.assuming else "")
                          + f"{cj.lhs} {cj.rhs}".strip())
    statement = policy_text(stated)
    current = active_batch()
    meta = {"mathema.policy": {"kind": stated.kind, "parameter": stated.parameter,
                               "member": stated.member, "behaviour": stated.behaviour,
                               "exception": stated.exception, "premise": stated.premise,
                               "source": "stated"}}

    def unknown(reason: str):
        meta["mathema.policy"]["reason"] = reason
        return Probe(cj.name, statement, "unknown", route="probe:counterfactual",
                     note=reason, meta=meta)

    if stated.kind == "absent" and stated.parameter is None \
            and stated.behaviour == "introduces":
        return _adjudicate_return(cj, fn, stated, statement, current, meta, unknown)
    misspecified = none_default_misspecified(
        fn, [stated.parameter] if stated.parameter else None) \
        if stated.kind == "absent" else None
    if misspecified:
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=misspecified, meta={**meta, "mathema.invalid_conjecture": True})
    params = [stated.parameter] if stated.parameter else [
        p for p in facts.params if _admits(fn, p, stated.kind)]
    rows_calls: list = []
    floor = False
    for p in params:
        found = _relevant(current.calls if current else [], p, stated.kind,
                          stated.member, stated.premise)
        if not found and _is_path(p) and stated.kind == "absent" \
                and stated.member in (None, "null"):
            # an optional field of a record parameter: called with it None
            from ._missing_policy import path_root
            points = [pt for q, pt in _field_floor(fn, facts, path_root(p), domain)
                      if q == p and _premise_holds(stated.premise, pt)]
            found = _run_floor(fn, facts, points)
            floor = floor or bool(found)
        elif not found and not _is_path(p):
            members = [stated.member] if stated.member else _members_of(fn, p, stated.kind)
            points = [pt for pt in _floor_points(fn, facts, p, stated.kind, members,
                                                 domain, cj)
                      if _premise_holds(stated.premise, pt)]
            found = _run_floor(fn, facts, points, domain or {})
            floor = floor or bool(found)
        rows_calls += [(p, c) for c in found]
    if stated.behaviour in ("drops", "converts", "introduces"):
        # a call indifferent to the slot breaks only raises and
        # propagates: a hole read as a fixed value is consistent with the
        # other words
        rows_calls = [(p, c) for p, c in rows_calls if not c.indifferent]
    if not rows_calls:
        return unknown(_why_undecided(stated, params, current))
    calls = [c for _p, c in rows_calls]
    param = stated.parameter or (params[0] if len(params) == 1 else None)
    evidence = _confirmed(calls, current, floor, param)
    meta["mathema.policy"]["evidence"] = evidence
    wrong = next((c for p, c in rows_calls
                  if _behaviour_of(c) != stated.behaviour
                  or (stated.behaviour == "raises"
                      and not _raised_matches(c.raised, stated.exception))), None)
    if wrong is not None:
        p = next(pp for pp, c in rows_calls if c is wrong)
        did = _behaviour_of(wrong)
        cases = _cases([c for pp, c in rows_calls if pp == p], p, stated.kind,
                       stated.member)
        if cases is not None and len(cases) > 1 and all(c.premise for c in cases) \
                and len({c.member for c in cases}) == 1:
            reason = (f"stated; f {_split_words(cases, p)}")
            nxt = f"state the two cases: {_written(cases)}; or change f"
        else:
            reason = f"stated; f {did} instead: {_entry(wrong, p, stated.kind)}"
            nxt = (f"state {_stated_word(stated, did, wrong, calls)} if that is "
                   f"intended, or change f")
        meta["mathema.policy"].update({"reason": reason, "next": nxt})
        return Probe(cj.name, statement, "falsified", n=len(calls), route="probe:counterfactual",
                     counterexample=_witness(wrong, p), note=f"{reason}; {nxt}",
                     meta=meta)
    guard = None
    for p in params:
        members = [stated.member] if stated.member else _members_of(fn, p, stated.kind)
        found_guards = [_guard_for(derived or {}, fn, p, stated.kind, m) for m in members]
        if found_guards and all(g and g[0] == stated.behaviour
                                and _raised_matches(g[1], stated.exception)
                                for g in found_guards):
            guard = found_guards[0]
    if guard is not None:
        reason = f"stated; from the guard on line {guard[2]}; {evidence}"
        meta["mathema.policy"]["reason"] = reason
        return Probe(cj.name, statement, "proven", n=len(calls), route="examine",
                     note=reason, meta=meta)
    reason = f"stated; {evidence}"
    meta["mathema.policy"]["reason"] = reason
    return Probe(cj.name, statement, "holds", n=len(calls), route="probe:counterfactual",
                 note=reason, meta=meta)


def _split_words(cases: list, param: str) -> str:
    """What a member split by count does, in words: `drops a null slot
    when values remain and raises TypeError when every slot is null`."""
    member = cases[0].member
    what = f"a {member} slot" if member else "a missing slot"

    def did(case) -> str:
        return (f"raises {case.exception}" if case.behaviour == "raises" and case.exception
                else case.behaviour)
    parts = []
    for case in cases:
        when = ("when values remain" if case.premise.endswith(">= 1")
                else f"when every slot is {member or 'missing'}")
        parts.append(f"{did(case)} {when}")
    head = parts[0].split(" ", 1)
    first = f"{head[0]} {what} {head[1]}" if cases[0].behaviour == "drops" else parts[0]
    return " and ".join([first] + parts[1:])


def _premise_names_param(premise: str, param: str) -> bool:
    """Whether a premise reads the value of `param` itself, not only its
    count or length."""
    rest = re.sub(rf"\b(count|len)\(\s*{re.escape(param)}\b[^)]*\)", "", premise)
    return re.search(rf"\b{re.escape(param)}\b", rest) is not None


def _why_undecided(stated: Policy, params: list, current: "Batch | None") -> str:
    """Why no call decided a stated policy row: a premise that cannot be
    read at the missing point, or no call reaching it."""
    from ._missing_words import point_shown
    word = "None" if stated.kind == "absent" else (stated.member or "nan")
    for p in params:
        if stated.premise and _premise_names_param(stated.premise, p):
            return (f"the premise {stated.premise} cannot be decided at {p} = {word}; a "
                    f"policy row's premise is about the other parameters or about "
                    f"count(...)")
        reached = _relevant(current.calls if current else [], p, stated.kind,
                            stated.member, "")
        if stated.premise and reached:
            from ._linalg_eval import FUNCTIONS, as_array
            call = reached[0]
            env = {"len": len, **FUNCTIONS,
                   **{q: as_array(v) for q, v in call.point.items()}}
            try:
                eval(compile(stated.premise, "<premise>", "eval"),
                     {"__builtins__": {}}, env)
            except Exception:
                column = _hole_column(reached, p)
                if isinstance(call.point.get(p), dict) or column:
                    col = column or next(iter(call.point[p]), "c")
                    return (f"the premise {stated.premise} cannot be evaluated on a "
                            f"frame; name a column, count({p}.{col})")
                return (f"the premise {stated.premise} cannot be evaluated at "
                        f"{point_shown({p: call.point[p]})}")
            return (f"no call where {p} is missing met the premise {stated.premise}")
    who = stated.parameter or "a parameter"
    if _is_path(who):
        member = f" ({stated.member})" if stated.member else ""
        return (f"no call reached a {stated.kind} {who}{member}, so nothing says what f "
                f"does there; bind {who} in a claim that admits it")
    if stated.kind == "absent":
        return (f"no call reached {who} = None, so nothing says what f does there; bind "
                f"{who} in a claim that admits None")
    return (f"no call reached a missing {who}, so nothing says what f does there; bind "
            f"{who} in a claim that admits it")


def _adjudicate_return(cj, fn, stated, statement, current, meta, unknown):
    """`absent(f) introduces`: decided on the calls where f returned None
    from present inputs."""
    from .records import Probe
    from ._missing_words import declared_optional_return, point_shown
    calls = list(current.introduced) if current else []
    if not calls:
        return unknown("no call gave None back from present inputs, so nothing says "
                       "f introduces an absence")
    declared = declared_optional_return(fn)
    as_declared = (f", as its return type {declared} declares" if declared
                   else ", which its return type does not declare")
    reason = (f"stated; f returned None at {point_shown(calls[0].point)}, from present "
              f"inputs{as_declared}")
    meta["mathema.policy"].update({"reason": reason,
                                   "evidence": _confirmed(calls, current, False)})
    return Probe(cj.name, statement, "holds", n=len(calls), route="probe:counterfactual",
                 note=reason, meta=meta)


def _stated_word(policy: Policy, behaviour: str, call: Call,
                 calls: "list | None" = None) -> str:
    """The claim that states what `call` did, narrowed to the call's
    member when the other members behave otherwise."""
    member = policy.member
    if member is None and calls and policy.parameter:
        kind = policy.kind
        mine = _members_at(call, policy.parameter, kind)
        others = [c for c in calls
                  if not set(_members_at(c, policy.parameter, kind)) & set(mine)]
        if len(mine) == 1 and any(_behaviour_of(c) != behaviour for c in others):
            member = mine[0]
    word = replace(policy, member=member, behaviour=behaviour,
                   exception=call.raised if behaviour == "raises" else None)
    return f"`{policy_text(word)}`"


def _is_path(name: "str | None") -> bool:
    from ._missing_policy import is_path
    return bool(name) and is_path(name)


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


def _guard_for(guards: dict, fn, p: str, kind: str, member: "str | None"):
    """The guard that decides a parameter's kind (and member), or None."""
    if kind == "absent":
        return guards.get((p, "absent", "None")) or guards.get((p, "absent", None))
    found = guards.get((p, kind, member)) or guards.get((p, kind, None))
    if found is None and member in (None, "nan") \
            and set(_members_of(fn, p, kind)) <= {"nan"}:
        found = guards.get((p, kind, "nan"))
    return found


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
        hole into an absence; one that returns `nan` (`float("nan")`,
        `math.nan`, `np.nan`) passes a hole on and turns an absence into
        a hole; one that returns the parameter itself passes it on; any
        other return drops.
    """
    import ast
    tree = getattr(facts, "tree", None)
    if tree is None:
        return {}
    params = set(facts.params)
    out: dict = {}

    def covered(test) -> list:
        # a test covers a parameter only when it depends on that parameter
        # alone: one check, or checks joined by `or`, each on one parameter
        parts = test.values if isinstance(test, ast.BoolOp) \
            and isinstance(test.op, ast.Or) else [test]
        keys: list = []
        for part in parts:
            found = checks(part)
            if not found:
                return []
            keys += found
        return keys

    def checks(test, compound: bool = False) -> list:
        keys: list = []
        if isinstance(test, ast.BoolOp) and not compound:
            return []
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

    def what(value, param) -> str:
        # what an expression is: None, a nan, the parameter itself, or a
        # value
        if value is None or (isinstance(value, ast.Constant) and value.value is None):
            return "None"
        if isinstance(value, ast.Name) and value.id == param:
            return "itself"
        if isinstance(value, ast.Name) and value.id == "nan":
            return "nan"
        if isinstance(value, ast.Attribute) and value.attr == "nan" \
                and isinstance(value.value, ast.Name) \
                and value.value.id in ("math", "np", "numpy"):
            return "nan"
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                and value.func.id == "float" and len(value.args) == 1 \
                and isinstance(value.args[0], ast.Constant) \
                and str(value.args[0].value).lower() == "nan":
            return "nan"
        return "value"

    def returned(body, param) -> "str | None":
        for stmt in body:
            if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == param for t in stmt.targets):
                # the parameter replaced by a value: `if scale is None:
                # scale = 1.0`
                return what(stmt.value, param)
            if isinstance(stmt, ast.Return):
                return what(stmt.value, param)
        return None

    # a check that also reads something else decides only part of a
    # case, and a later guard for the same case sees only what is left
    shadowed: set = set()
    ifs = sorted((n for n in ast.walk(tree) if isinstance(n, ast.If)),
                 key=lambda n: (n.lineno, n.col_offset))
    for node in ifs:
        if isinstance(node.test, ast.UnaryOp):
            continue
        keys = [k for k in covered(node.test) if k not in shadowed]
        if not covered(node.test):
            shadowed.update(checks(node.test, compound=True))
        if not keys:
            continue
        raise_stmt = next((s for s in node.body if isinstance(s, ast.Raise)), None)
        for p, kind, member in keys:
            back = returned(node.body, p)
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
                if back == "itself":
                    # what came in goes back out
                    behaviour = "propagates"
                elif back == "value":
                    behaviour = "drops"
                elif back == "None":
                    behaviour = "propagates" if kind == "absent" else "converts"
                else:
                    behaviour = "propagates" if kind == "missing" else "converts"
                out.setdefault((p, kind, member), (behaviour, None, node.lineno))
    return out


# --- the rows a record carries for every parameter -------------------------

def _why_admitted(fn, param: str, kind: str, origin: str, word: str) -> str:
    """Why a kind reaches a parameter, as the row says it: `x is
    Optional[float], so f promised to take None`, `the claim lists nan
    for x`."""
    from .conjecture import _annotation_words
    if origin == "path":
        what = "a key left out" if word == "unset" else (
            "None" if kind == "absent" else word)
        return f"{param} may be {what}"
    if origin == "optional":
        return f"{param} is {_annotation_words(fn, param)}, so f promised to take None"
    if origin == "listed":
        return f"the claim lists {word} for {param}"
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


def _or(words: list) -> str:
    words = list(words)
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def _default_words(p: str, kind: str, member: "str | None", sig, container: bool,
                   short: bool = False) -> str:
    """What a default row is the default for: `default for a float,
    which may be nan`, `default for a list slot that may be null`,
    `default: x has no annotation, so it may be None`."""
    if kind == "absent":
        if sig.slot_type == "unannotated":
            return f"default: {p} has no annotation, so it may be None"
        return f"default for a {sig.slot_type}, which may be None"
    # a numeric slot holds no NaT; only a datetime one does
    members = [member] if member else ([m for m in sig.members
                                        if m != "NaT" or sig.slot_type == "datetime"]
                                       or ["nan"])
    if sig.slot_type == "unannotated":
        return f"default: {p} has no annotation, so it may be {_or(members)}"
    if container:
        return (f"mathema's default word for a {sig.slot_type} slot that may be "
                f"{_or(members)}, not a claim of yours" if short else
                f"default for a {sig.slot_type} slot that may be {_or(members)}")
    if short:
        return f"mathema's default word for a {sig.slot_type}, not a claim of yours"
    return f"default for a {sig.slot_type}, which may be {_or(members)}"


def _function_key(fn) -> str:
    from .authoring import _fn_key
    return _fn_key(fn)


def default_rows(fn, facts, domain: dict, covered: set, name_of) -> list:
    """Intent:
        The policy rows a record carries for every parameter that admits
        a kind, beside the cases stated policy rows cover (`covered`, a
        set of `(kind, parameter, member, premise)`, parameter None for
        every parameter): a default for a kind the type alone admits
        (`missing(f, x) propagates` for a float, `absent(f, x) raises`
        for a parameter with no annotation), confirmed or contradicted by
        the calls; the observed behaviour for a kind the author admitted,
        where a raise stays unaccounted for until a claim states it; a
        derived row where a guard in the body or a library's own policy
        row states the behaviour; `absent(f) introduces` where the return
        type declares the None f gave back from present inputs. One row
        per member when the members behave differently or a stated row
        covers some of them.
    """
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
            if not admitted:
                continue
            mine = {(m, pr) for (k, q, m, pr) in covered if k == kind and q in (p, None)}
            if (None, "") in mine:
                continue
            stated_members = {m for m, pr in mine if m and not pr}
            premised = [(m, pr) for m, pr in mine if pr]
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
                                     [pol for pol in composed[p][1]
                                      if (pol.member, pol.premise) not in mine
                                      and pol.member not in stated_members],
                                     name_of, stated=mine)
                rows += made
                done_members = {(r.meta or {}).get("mathema.policy", {}).get("member")
                                for r in made}
                if None in done_members:
                    continue
            calls = [c for c in _relevant(current.calls if current else [], p, kind,
                                          None, "")
                     if not (set(_members_at(c, p, kind))
                             & (done_members | stated_members))
                     and not any((m is None or m in _members_at(c, p, kind))
                                 and _premise_holds(pr, c.point) for m, pr in premised)]
            # a record's own rows read the calls its claims made, and run
            # nothing of their own
            if not calls:
                continue
            rows += _member_rows(fn, p, kind, calls, origin, sig, guards, current,
                                 name_of, Probe,
                                 apart=bool(stated_members or premised) and kind == "missing")
    rows += _path_rows(fn, covered, current, guards, name_of)
    rows += _return_rows(fn, covered, current, name_of)
    return rows


def _member_rows(fn, p, kind, calls, origin, sig, guards, current, name_of, Probe,
                 apart: bool = False) -> list:
    """One row for `calls` at `p`, or one per member when the members
    behave differently (or `apart` asks for one per member)."""
    by_member: dict = {}
    for c in calls:
        for m in _members_at(c, p, kind):
            by_member.setdefault(m, []).append(c)
    ways = {m: _decide(cs) for m, cs in by_member.items()}
    singles = {m: next(iter(w)) for m, w in ways.items() if len(w) == 1}
    split = (len(ways) > 1 and len(singles) == len(ways)
             and len(set(singles.values())) > 1)
    groups = ([(m, [c for c in by_member[m]
                    if _members_at(c, p, kind) == [m]] or by_member[m])
               for m in ways] if split or apart else [(None, calls)])
    return [_default_row(fn, p, kind, member, cs, origin, sig, guards, current,
                         name_of, Probe) for member, cs in groups]


#: what a path's row reads for the type of what it reaches: nothing is
#: known of a field's type here, so a kind it reaches is observed
_PATH_SIG = None


def _path_rows(fn, covered: set, current: "Batch | None", guards: dict, name_of) -> list:
    """Intent:
        The rows for every path (`o.note`, `d.note`, `o.lines[*].qty`) a
        call reached no value at, a field's or key's absence or a hole:
        observed, since a record's field is the language's or the
        claim's to admit, and a raise there unaccounted for until a
        claim states it. One row per member where the members behave
        differently; none for a case a stated row covers.
    """
    from ._missing_policy import is_path
    from .domain import MissingDefaults
    from .records import Probe
    calls = list(current.calls) if current else []
    targets: list = []
    for c in calls:
        for q, k, _m in _keys(c):
            if is_path(q) and (q, k) not in targets:
                targets.append((q, k))
    rows: list = []
    sig = MissingDefaults(False, (), "field", annotated=False)
    for path, kind in targets:
        mine = {(m, pr) for (k, q, m, pr) in covered if k == kind and q == path}
        if (None, "") in mine:
            continue
        stated_members = {m for m, pr in mine if m and not pr}
        found = [c for c in _relevant(calls, path, kind, None, "")
                 if not set(_members_at(c, path, kind)) & stated_members]
        if not found:
            continue
        rows += _member_rows(fn, path, kind, found, "path", sig, guards, current,
                             name_of, Probe, apart=bool(stated_members))
    return rows


def _return_rows(fn, covered: set, current: "Batch | None", name_of) -> list:
    """`absent(f) introduces` from the return type, where f gave None back
    from present inputs and its return type declares it (FM15)."""
    from .records import Probe
    from ._missing_words import declared_optional_return, point_shown
    calls = list(current.introduced) if current else []
    declared = declared_optional_return(fn)
    if not calls or ("absent", None, None, "") in covered:
        return []
    if not declared:
        import inspect
        try:
            ann = inspect.signature(fn).return_annotation
        except (TypeError, ValueError):
            ann = inspect.Signature.empty
        if ann is inspect.Signature.empty:
            return []
        shown = ann if isinstance(ann, str) else getattr(ann, "__name__", repr(ann))
        policy = Policy(kind="absent", behaviour=None, source="observed")
        sentence = (f"f returned None at {point_shown(calls[0].point)} from present "
                    f"inputs, and its return type {shown} does not declare it")
        nxt = (f"declare the return type Optional[{shown}] if None is an answer f "
               f"gives, or make f return a value there")
        meta = {"mathema.policy": {"kind": "absent", "parameter": None, "member": None,
                                   "behaviour": None, "exception": None, "premise": "",
                                   "source": "observed", "reason": sentence,
                                   "sentence": sentence, "next": nxt},
                "mathema.surface": "mathema"}
        return [Probe(name_of(policy), policy_text(policy), "falsified", n=len(calls),
                      route="probe:counterfactual",
                      counterexample=f"{point_shown(calls[0].point)}: f returned None",
                      note=f"{sentence}. {nxt}", meta=meta)]
    policy = Policy(kind="absent", behaviour="introduces", source="annotation")
    reason = (f"from the return type {declared}: f returned None at "
              f"{point_shown(calls[0].point)} from present inputs; "
              f"{_confirmed(calls, current, False)}")
    meta = {"mathema.policy": {"kind": "absent", "parameter": None, "member": None,
                               "behaviour": "introduces", "exception": None,
                               "premise": "", "source": "annotation", "reason": reason},
            "mathema.surface": "mathema"}
    return [Probe(name_of(policy), policy_text(policy), "proven", n=len(calls),
                  route="examine", note=reason, meta=meta)]


def _default_row(fn, p, kind, member, calls, origin, sig, guards, current,
                 name_of, Probe):
    from ._missing_words import mixed_sentence, value_shown
    seen = _decide(calls)
    container = any(_in_slot(c, p, kind) for c in calls)
    guard = _guard_for(guards, fn, p, kind, member)
    policy = Policy(kind=kind, parameter=p, member=member)
    evidence = _confirmed(calls, current, False, p)
    meta_policy = {"kind": kind, "parameter": p, "member": member, "premise": "",
                   "evidence": evidence}
    meta = {"mathema.policy": meta_policy, "mathema.surface": "mathema"}
    key = _function_key(fn)

    def row(verdict, behaviour, exception, source, bracket, cx=None,
            route="probe:counterfactual", nxt=None, sentence=None, said=None,
            shown=None):
        stated = replace(policy, behaviour=behaviour, exception=exception, source=source)
        shown = shown or stated
        meta_policy.update({"behaviour": shown.behaviour, "exception": shown.exception,
                            "source": source, "reason": bracket})
        if nxt:
            meta_policy["next"] = nxt
        if sentence:
            meta_policy["sentence"] = sentence
        if said:
            meta_policy["said"] = said
        note = ". ".join(t for t in (sentence or bracket, said, nxt) if t)
        return Probe(name_of(stated), policy_text(shown), verdict, n=len(calls),
                     route=route, counterexample=cx, note=note, meta=meta)

    if len(seen) > 1:
        members_seen = list(dict.fromkeys(m for c in calls
                                          for m in _members_at(c, p, kind)))
        ways = {m: {} for m in members_seen}
        raised: dict = {}
        for c in calls:
            ms = _members_at(c, p, kind)
            # a call indifferent to the slot is said as what it showed
            b = "indifferent" if c.indifferent else _behaviour_of(c)
            for m in ms:
                ways[m].setdefault(b, _at(c, None))
                if c.raised:
                    raised.setdefault(m, c.raised)
        noun = "slot" if container else None
        said = mixed_sentence(p, {m: w for m, w in ways.items() if w}, raised,
                              "container" if noun else None)
        cases = _cases(calls, p, kind, member, list(sig.members) or None)
        what = f"a missing {p}" if kind == "missing" else f"{p} = None"
        if cases:
            nxt = f"to state each case, write {_written(cases)}; or make f treat {what} one way"
        elif kind == "missing" and container:
            nxt = (f"no premise on count({p}) or len({p}) tells these cases apart; make "
                   f"f treat {what} one way")
        else:
            nxt = (f"give each case a premise on another parameter that tells them apart, "
                   f"or make f treat {what} one way")
        return row("falsified", None, None, "observed",
                   f"f has no single policy for {what}",
                   sentence=f"f has no single policy for {what}", said=said, nxt=nxt,
                   cx=_witness(next(iter(seen.values())), p))
    (behaviour, call), = seen.items()
    exception = call.raised if behaviour == "raises" else None
    accepted = policy_text(replace(policy, behaviour=behaviour, exception=exception))
    if guard is not None and guard[0] == behaviour:
        return row("proven", behaviour, exception, "derived",
                   f"from the guard on line {guard[2]}; {evidence}", route="examine")
    if origin == "type":
        from ._missing_words import DEFAULTS
        expected = DEFAULTS[kind]
        if behaviour == expected:
            words = _default_words(p, kind, member, sig, container)
            if kind == "absent" and sig.slot_type == "unannotated":
                bracket = (f"{words}, and f raises on it; {evidence}. Annotate {p} as "
                           f"float to exclude None, or write this row with mathema "
                           f"claims {key} --write")
            elif sig.slot_type == "unannotated":
                bracket = (f"{words}; {evidence}. Annotate {p} as float to say so, or "
                           f"write this row with mathema claims {key} --write")
            else:
                other = "raises or drops" if kind == "missing" else "drops or propagates"
                bracket = (f"{words}; {evidence}. Keep it by writing it (mathema claims "
                           f"{key} --write), or change the word to {other} if f should "
                           f"do otherwise")
            return row("holds", behaviour, None, "default", bracket)
        words = _default_words(p, kind, member, sig, container, short=True)
        bracket = f"{words}; f {behaviour} instead: {_entry(call, p, kind)}"
        out = value_shown(call.output)
        slot_member = member or (_members_in(call.point.get(p), kind) or ["nan"])[0]
        if behaviour == "drops":
            if kind == "absent":
                nxt = (f"if {out} is the answer f should give for {p} = None, write "
                       f"`{accepted}`; if not, make f raise")
            elif container:
                nxt = (f"if {out} is the answer f should give when a slot is "
                       f"{slot_member}, write `{accepted}`; if not, make f raise or "
                       f"give a hole back")
            else:
                nxt = (f"if {out} is the answer f should give for a missing {p}, write "
                       f"`{accepted}`; if not, make f raise or give nan back")
        elif behaviour == "raises":
            fix = (f"make f skip or fill the {slot_member} slot" if container
                   else "make f give nan back")
            nxt = f"if the raise is intended, write `{accepted}`; if not, {fix}"
        elif behaviour == "propagates" and kind == "absent":
            nxt = f"if giving None back is intended, write `{accepted}`; if not, make f raise"
        else:
            nxt = f"if that is intended, write `{accepted}`; if not, change f"
        expected_policy = replace(policy, behaviour=expected, source="default")
        nxt += (f"; or accept it as a discovery: mathema accept {key} "
                f"{name_of(expected_policy)} --as discovery --corrected \"{accepted}\"")
        return row("falsified", expected, None, "default", bracket, nxt=nxt,
                   cx=_witness(call), shown=expected_policy)
    held = _members_at(call, p, kind)
    word = (member or (held[0] if held else "None")) if origin == "path" else (
        "None" if kind == "absent" else (member or held[0] if held else "nan"))
    why = _why_admitted(fn, p, kind, origin, word)
    if behaviour == "raises":
        at = _at(call, p)
        if origin == "path":
            from ._missing_words import path_place
            place = path_place(p, (_members_at(call, p, kind) or ["null"])[0],
                               call.point, kind)
            sentence = (f"f raised {exception} at {place}, and no claim says it may")
            nxt = (f"if the raise is intended, state `{accepted}`; otherwise handle "
                   f"it in f, or exclude it where {p} is bound, `\\ {{{word}}}`")
        elif origin == "optional":
            sentence = f"f raised {exception} at {at}, and no claim says it may"
            nxt = (f"{why}. If the raise is intended, state `{accepted}`; otherwise "
                   f"handle None in f, or annotate {p} as {_plain_type(fn, p)}")
        elif origin == "listed":
            sentence = (f"f raised {exception} at {at}, a point the claim lists, and no "
                        f"claim says it may")
            nxt = (f"if the raise is intended, state `{accepted}`; otherwise handle "
                   f"{word} in f, or remove {word} from the set")
        else:
            sentence = (f"f raised {exception} at {at}, a value the claim admits, and "
                        f"no claim says it may")
            nxt = (f"if the raise is intended, state `{accepted}`; otherwise handle "
                   f"{word} in f, or remove |{kind} from the domain")
        nxt += (f"; or accept the raise as a discovery (mathema accept {key} "
                f"{name_of(policy)} --as discovery) and state `{accepted}`")
        return row("falsified", None, None, "observed", sentence, sentence=sentence,
                   nxt=nxt, cx=_witness(call, p))
    return row("holds", behaviour, None, "observed",
               f"observed: {why}; f {behaviour} it ({_entry(call, p, kind)}) "
               f"{_on_draws(calls, current)}")


def row_name(policy: Policy) -> str:
    """The name a policy row goes by, on the record and in a claims file:
    `missing[x]`, `missing[xs, null]`, `absent[x]`, `absent[f]` for the
    return, `missing[xs, count >= 1]` for a premised row."""
    parts = [policy.parameter or "f"]
    if policy.member:
        parts.append(policy.member)
    if policy.premise:
        premise = policy.premise
        if policy.parameter:
            premise = re.sub(rf"\bcount\(\s*{re.escape(policy.parameter)}\s*\)", "count",
                             premise)
        parts.append(premise)
    return f"{policy.kind}[{', '.join(parts)}]"


def contradicting_policies(statements: list) -> "str | None":
    """Intent:
        Why two of a function's policy claims cannot both hold, or None:
        the same kind, parameter, member and premise stated with two
        different behaviours (`missing(f, x) drops` beside `missing(f, x)
        propagates`).
    """
    seen: dict = {}
    for text in statements:
        stated = parse_policy(text if isinstance(text, str) else "")
        if stated is None or stated.behaviour is None:
            continue
        key = (stated.kind, stated.parameter, stated.member, stated.premise)
        other = seen.get(key)
        if other is not None and (other.behaviour != stated.behaviour or (
                other.exception and stated.exception
                and other.exception != stated.exception)):
            return (f"`{policy_text(other)}` and `{policy_text(stated)}` state two "
                    f"behaviours for one case. Keep one (the record shows which f "
                    f"follows), or give each a premise on another parameter or on "
                    f"count(...) that tells the cases apart, e.g. `assuming count(xs) "
                    f">= 1, ...` beside `assuming count(xs) == 0, ...`")
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
    if expr.keywords:
        # a library's rows state its call at the defaults; a call passing
        # anything more is a different call
        return {}
    rebound = {t.id for n in ast.walk(tree)
               for t in (n.targets if isinstance(n, ast.Assign)
                         else [n.target] if isinstance(n, (ast.AugAssign, ast.AnnAssign,
                                                             ast.For, ast.NamedExpr))
                         else [])
               if isinstance(t, ast.Name)}
    from .runtime_types import realised_parameters
    scope = getattr(fn, "__globals__", {}) or {}
    rows = library_policies()
    runtime = {p: d.adapter for p, d in realised_parameters(facts).items()}
    owner = expr.func.value
    key = param = None
    if isinstance(owner, ast.Name) and owner.id in runtime and not expr.args:
        param, key = owner.id, f"{runtime[owner.id]}.{expr.func.attr}"
    elif isinstance(owner, ast.Name) and len(expr.args) == 1 \
            and isinstance(expr.args[0], ast.Name) and expr.args[0].id in facts.params:
        module = getattr(scope.get(owner.id), "__name__", None)
        held = runtime.get(expr.args[0].id)
        # a library's rows speak for its own values: numpy's mean of a
        # pandas Series is pandas' reduction, which skips holes
        if module and (held is None or held.split(".")[0] == module.split(".")[0]):
            param, key = expr.args[0].id, f"{module}.{expr.func.attr}"
    if key is None or key not in rows or param in rebound:
        # a parameter the body gives another value may reach the call
        # changed, so the call's rows do not speak for it
        return {}
    restated = []
    for policy in rows[key]:
        premise = re.sub(rf"\b{policy.parameter}\b", param, policy.premise) \
            if policy.parameter else policy.premise
        restated.append(replace(policy, parameter=param, premise=premise,
                                source="derived"))
    return {param: (key, restated)}


def composed_rows(fn, facts, param: str, kind: str, key: str, policies: list,
                  name_of, stated: "set | None" = None) -> list:
    """The rows a parameter carries from a library's composed policy rows,
    each decided on the calls the check made: `proven` where the calls
    confirm it, `falsified` with the executed witness where they do not.
    A class row is decided on the members no stated row with the same
    premise covers (`stated`, a set of `(member, premise)`)."""
    from .records import Probe
    current = active_batch()
    rows = []
    for policy in policies:
        if policy.kind != kind:
            continue
        calls = _relevant(current.calls if current else [], param, kind,
                          policy.member, policy.premise)
        apart = sorted({m for m, pr in (stated or set())
                        if m and pr == policy.premise and policy.member is None})
        if apart:
            calls = [c for c in calls
                     if not set(_members_in(c.point.get(param), kind)) & set(apart)]
        if not calls:
            continue
        evidence = _confirmed(calls, current, False, param)
        if apart:
            shown = sorted({m for c in calls for m in _members_in(c.point.get(param), kind)})
            evidence = (evidence.replace("confirmed ", f"confirmed for {_and(shown)} ", 1)
                        + f"; {_and(apart)} {'is' if len(apart) == 1 else 'are'} stated "
                          f"separately")
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
            reason = f"from {key}'s own policy row, which f calls; {evidence}"
            meta_policy["reason"] = reason
            rows.append(Probe(name_of(policy), statement, "proven", n=len(calls),
                              route="examine", note=reason, meta=meta))
            continue
        did = _behaviour_of(wrong)
        did_words = f"raises {wrong.raised}" if did == "raises" else did
        reason = (f"from {key}'s own policy row, which f calls; f {did_words} instead "
                  f"at {_at(wrong, param)}")
        cases = _cases(calls, param, kind, policy.member)
        if cases is not None and policy.premise:
            # the calls are the premise's, so each case keeps it
            cases = [c if c.premise else replace(c, premise=policy.premise)
                     for c in cases]
        if cases is not None and cases != [replace(policy, source="stated")] and \
                len(cases) > 1:
            nxt = f"state {_written(cases)} if that is intended, or change f"
        else:
            nxt = (f"state {_stated_word(policy, did, wrong, calls)} if that is "
                   f"intended, or change f")
        meta_policy.update({"reason": reason, "next": nxt})
        rows.append(Probe(name_of(policy), statement, "falsified", n=len(calls),
                          route="probe:counterfactual", counterexample=_witness(wrong),
                          note=f"{reason}; {nxt}", meta=meta))
    return rows


# --- the gates: is_missing_safe(f), is_absent_safe(f) --------------------

def _path_calls(fn, facts, params: list, kind: str, domain: dict,
                current: "Batch | None") -> dict:
    """`{path: [call, ...]}`: the calls where a path inside one of
    `params` reached no value of `kind`, and for absence a call per
    optional field of a record parameter no call reached, the field set
    to None."""
    from ._missing_policy import is_path, path_root
    out: dict = {}
    for c in (current.calls if current else []):
        for q, k, _m in _keys(c):
            if k == kind and is_path(q) and path_root(q) in params:
                if c not in out.setdefault(q, []):
                    out[q].append(c)
    if kind == "absent":
        for p in params:
            for path, point in _field_floor(fn, facts, p, domain):
                if path not in out:
                    found = _run_floor(fn, facts, [point])
                    if found:
                        out[path] = found
    for p in params:
        for keys, point in _type_floor(fn, facts, p, domain, kind):
            paths = [q for q, _k, _m in keys]
            if len(keys) == 1 and paths[0] in out:
                continue
            found = _run_floor(fn, facts, [point])
            for c in found:
                c.keys = list(keys)
            for q in paths:
                out.setdefault(q, []).extend(found)
    return out


def _annotation(fn, param: str):
    import typing
    try:
        return typing.get_type_hints(fn).get(param)
    except Exception:
        return None


def _admits_none(ann) -> bool:
    import types
    import typing
    return ann is type(None) or (
        typing.get_origin(ann) in (typing.Union, types.UnionType)
        and type(None) in typing.get_args(ann))


def _others(fn, facts, param: str, domain: dict) -> dict:
    """The parameters beside `param`, drawn inside their domains."""
    import random

    from ._sampling import _RNG_SEED
    from .probing import _synth, signature_defaults
    rng = random.Random(_RNG_SEED)
    defaulted = signature_defaults(fn)
    return {q: _synth(facts.param_kinds.get(q, "unknown"), rng, (domain or {}).get(q))
            for q in facts.params if q != param and q not in defaulted}


_UNSET = object()


def _type_cases(cls, depth: int = 0, element: bool = False) -> list:
    """Intent:
        `[(steps, kind, member, leaf), ...]`: every place inside a value
        of record type `cls` (a dataclass, a pydantic model, a TypedDict)
        where its type states a no-value, with the value that puts it
        there: an Optional field or key holding None (`absent`, `null`),
        a TypedDict key its type does not require left out (`absent`,
        `unset`), a list element that is a float (`missing`, `nan`) or
        admits None (`missing`, `null`), and a float field of a record
        that is a list's element (`missing`, `nan`, `o.lines[*].qty`).
        `steps` walks from the value,
        `"*"` for a list's element; nested records are walked three
        levels deep.
    """
    import typing
    if depth > 3 or not _is_record_type(cls):
        return []
    try:
        hints = typing.get_type_hints(cls)
    except Exception:
        return []
    optional_keys = getattr(cls, "__optional_keys__", ()) if typing.is_typeddict(cls) else ()
    out: list = []
    for name, ann in hints.items():
        if name in optional_keys:
            out.append(([name], "absent", "unset", _UNSET))
        inner = ann
        if _admits_none(ann):
            out.append(([name], "absent", "null", None))
            inner = next((a for a in typing.get_args(ann) if a is not type(None)), ann)
        if element and inner is float:
            out.append(([name], "missing", "nan", float("nan")))
        out += [([name, *steps], k, m, leaf) for steps, k, m, leaf in _inner_cases(inner, depth)]
    return out


def _inner_cases(ann, depth: int) -> list:
    """The cases inside a field's own type: a list's elements, a nested
    record's fields."""
    import typing
    if typing.get_origin(ann) is list and typing.get_args(ann):
        (element,) = typing.get_args(ann)[:1]
        out: list = []
        if element is float:
            out.append((["*"], "missing", "nan", float("nan")))
        inner = element
        if _admits_none(element):
            out.append((["*"], "missing", "null", None))
            inner = next((a for a in typing.get_args(element) if a is not type(None)),
                         element)
        out += [(["*", *steps], k, m, leaf) for steps, k, m, leaf
                in _type_cases(inner, depth + 1, element=True)]
        return out
    return _type_cases(ann, depth + 1)


def _is_record_type(cls) -> bool:
    import dataclasses
    import typing
    return isinstance(cls, type) and (dataclasses.is_dataclass(cls)
                                      or typing.is_typeddict(cls)
                                      or isinstance(getattr(cls, "model_fields", None),
                                                    dict))


def _set_at(value, steps: list, leaf):
    """A deep copy of `value` with `leaf` at `steps` (`_UNSET` leaves a
    key out); a list on the way holds one element, built if empty."""
    import copy
    out = copy.deepcopy(value)
    target = out
    for k, step in enumerate(steps):
        last = k == len(steps) - 1
        if step == "*":
            if not isinstance(target, list):
                return None
            if not target:
                return None
            if last:
                target[0] = leaf
            else:
                target = target[0]
            continue
        if isinstance(target, dict):
            if last:
                if leaf is _UNSET:
                    target.pop(step, None)
                else:
                    target[step] = leaf
            else:
                target = target.get(step)
        else:
            if last:
                object.__setattr__(target, step, leaf)
            else:
                target = getattr(target, step, None)
        if target is None and not last:
            return None
    return out


def _path_text(param: str, steps: list) -> str:
    return param + "".join("[*]" if s == "*" else f".{s}" for s in steps)


def _type_floor(fn, facts, param: str, domain: dict, kind: str) -> list:
    """Intent:
        `[(keys, point), ...]` for a record parameter: one point per place
        its type states a no-value of `kind`, the value there, and for
        absence one more with every Optional field of the record itself
        None together; the other parameters drawn inside their domains.
        `keys` are `(path, kind, member)` for the calls' filing.
    """
    cls = _annotation(fn, param)
    if not _is_record_type(cls):
        return []
    base = _plain_value(cls)
    if base is None:
        return []
    others = _others(fn, facts, param, domain)
    out: list = []
    top_null: list = []
    for steps, k, member, leaf in _type_cases(cls):
        if k != kind:
            continue
        made = _set_at(base, steps, leaf)
        if made is None:
            continue
        path = _path_text(param, steps)
        out.append(([(path, k, member)], {**others, param: made}))
        if len(steps) == 1 and member == "null" and k == "absent":
            top_null.append(steps)
    if len(top_null) > 1:
        made = base
        for steps in top_null:
            made = _set_at(made, steps, None)
        if made is not None:
            out.append(([(_path_text(param, st), "absent", "null") for st in top_null],
                        {**others, param: made}))
    return out

def _optional_fields(cls) -> list:
    """The fields of a record type (a pydantic model, a dataclass) whose
    annotation admits None."""
    import dataclasses
    import types
    import typing

    def admits_none(ann) -> bool:
        return ann is type(None) or (
            typing.get_origin(ann) in (typing.Union, types.UnionType)
            and type(None) in typing.get_args(ann))
    fields = getattr(cls, "model_fields", None)
    if isinstance(fields, dict):
        return [n for n, info in fields.items()
                if admits_none(getattr(info, "annotation", None))]
    if isinstance(cls, type) and dataclasses.is_dataclass(cls):
        try:
            hints = typing.get_type_hints(cls)
        except Exception:
            return []
        return [f.name for f in dataclasses.fields(cls) if admits_none(hints.get(f.name))]
    return []


def _plain_value(ann, depth: int = 0):
    """A present value of an annotation's type, for a record the floor
    builds: a record built field by field, `None` where nothing fits."""
    import types
    import typing
    origin = typing.get_origin(ann)
    if origin in (typing.Union, types.UnionType):
        inner = [a for a in typing.get_args(ann) if a is not type(None)]
        return _plain_value(inner[0], depth) if inner else None
    simple = {str: "a", int: 1, float: 1.0, bool: True, list: [], dict: {}}
    if ann in simple:
        return simple[ann]
    if origin is list and typing.get_args(ann) and depth < 3:
        # one element, so a floor can put a no-value inside it
        element = _plain_value(typing.get_args(ann)[0], depth + 1)
        return [element] if element is not None else []
    if origin in (list, dict, tuple, set):
        return origin()
    if isinstance(ann, type) and typing.is_typeddict(ann) and depth < 3:
        try:
            hints = typing.get_type_hints(ann)
        except Exception:
            return None
        return {k: _plain_value(v, depth + 1) for k, v in hints.items()}
    if depth < 3:
        made = _plain_record(ann, depth + 1)
        if made is not None:
            return made
    return None


def _plain_record(cls, depth: int = 0):
    """An instance of a record type with a present value in every field
    its type does not default, or None for another type."""
    import dataclasses
    import typing
    fields = getattr(cls, "model_fields", None)
    try:
        if isinstance(fields, dict):
            values = {n: _plain_value(info.annotation, depth) for n, info in fields.items()
                      if info.is_required()}
            return cls.model_construct(**values)
        if isinstance(cls, type) and dataclasses.is_dataclass(cls):
            hints = typing.get_type_hints(cls)
            # a field its type defaults by a factory (an empty list) is built
            # too, so a floor can reach inside it
            values = {f.name: _plain_value(hints.get(f.name), depth)
                      for f in dataclasses.fields(cls)
                      if f.default is dataclasses.MISSING}
            return cls(**values)
    except Exception:
        return None
    return None


def _field_floor(fn, facts, param: str, domain: dict) -> list:
    """`[(path, point), ...]`: one point per optional field of a record
    parameter, that field set to None, the other parameters drawn
    inside their domains."""
    import dataclasses
    import random
    import typing

    from ._sampling import _RNG_SEED
    from .probing import _synth, signature_defaults
    try:
        cls = typing.get_type_hints(fn).get(param)
    except Exception:
        return []
    names = _optional_fields(cls)
    base = _plain_record(cls) if names else None
    if base is None:
        return []
    rng = random.Random(_RNG_SEED)
    defaulted = signature_defaults(fn)
    others = {q: _synth(facts.param_kinds.get(q, "unknown"), rng, (domain or {}).get(q))
              for q in facts.params if q != param and q not in defaulted}
    out = []
    for name in names:
        if hasattr(base, "model_copy"):
            value = base.model_copy(update={name: None})
        else:
            value = dataclasses.replace(base, **{name: None})
        out.append((f"{param}.{name}", {**others, param: value}))
    return out


def _stated_for(rows: list, kind: str, p: str, member: str) -> list:
    """The stated policy rows that speak for a parameter's member."""
    out = []
    for row in rows:
        pol = (row.meta or {}).get("mathema.policy") or {}
        if pol.get("kind") == kind and pol.get("parameter") in (p, None) \
                and pol.get("member") in (member, None):
            out.append(row)
    return out


def _library_for(composed: dict, p: str, kind: str, member: str) -> list:
    if p not in composed:
        return []
    return [pol for pol in composed[p][1]
            if pol.kind == kind and pol.member in (member, None)]


#: a behaviour word said of several members at once
_PLURAL = {"drops": "drop", "propagates": "propagate", "raises": "raise",
           "converts": "convert", "introduces": "introduce", "follows": "follow",
           "does": "do"}


def _plural(clause: str) -> str:
    """A clause whose subject is one member, said of several."""
    word, _, rest = clause.partition(" ")
    bare = word.rstrip(",;")
    return f"{_PLURAL.get(bare, bare)}{word[len(bare):]} {rest}".strip()


def _by_member(said: list) -> str:
    """Per-member clauses (`nan drops, ...`), members saying the same
    thing said once: `null and nan drop, stated`."""
    groups: dict = {}
    for clause in said:
        member, _, rest = clause.partition(" ")
        groups.setdefault(rest, []).append(member)
    out = []
    for rest, members in groups.items():
        out.append(f"{members[0]} {rest}" if len(members) == 1
                   else f"{_and(members)} {_plural(rest)}")
    return "; ".join(out)


def _library_words(policies: list, sep: str = " and ") -> str:
    """What premised library rows say, in words: `drops when values
    remain and propagates when every slot is missing`."""
    parts = []
    for pol in policies:
        word = (f"raises {pol.exception}" if pol.behaviour == "raises" and pol.exception
                else pol.behaviour)
        when = _when(pol.premise)
        parts.append(f"{word} {when}".strip())
    return sep.join(parts)


def _when(premise: str) -> str:
    """A count premise in words: `when values remain`, `when every slot
    is missing`."""
    if premise.endswith(">= 1"):
        return "when values remain"
    if premise.endswith("== 0"):
        return "when every slot is missing"
    return f"where {premise}" if premise else ""


def _follows(pol: Policy, call: Call) -> bool:
    return _behaviour_of(call) == pol.behaviour and (
        pol.behaviour != "raises" or _raised_matches(call.raised, pol.exception))


def _did(call: Call) -> str:
    """What one call did, as a verb phrase: `raises TypeError`, `drops`."""
    b = _behaviour_of(call)
    return f"raises {call.raised}" if b == "raises" else b


def _where(call: Call, p: str, member: str) -> str:
    """Where a call put the hole, in words: `when every slot is NA` for a
    container of that member alone, `at xs = [NA, 0.2]` otherwise."""
    from ._missing_words import _all_member, value_shown
    value = call.point.get(p)
    shown = value_shown(value)
    if _in_slot(call, p, "missing") and _all_member(shown, member):
        return f"when every slot is {member}"
    return f"at {_at(call, p)}"


def safety_gate(cj, fn, facts, domain: dict, stated_rows: list, guards: dict):
    """Intent:
        Adjudicate `is_missing_safe(f)` or `is_absent_safe(f)` (or one
        parameter's `is_absent_safe(x)`): every parameter that admits
        the kind has a policy the code follows at every member, reaching
        into a container's slots. `proven` when each member's policy is
        derived (a guard in the body, a library's own policy row f
        calls) or stated and confirmed; `holds` when some member is
        confirmed by execution alone (a lone scalar called at every
        member included); `falsified` on a policy the code contradicts, a
        member treated more than one way, a raise no claim accounts for,
        or an absence f returns from present inputs that its return type
        does not declare. The absence gate also calls f at inputs with
        nothing missing, for the absence the result may carry. The row says, per parameter, what each member
        does and whose word it is; a falsified one also names its
        counterexample and the one next step, the same one the policy
        row gives.
    """
    import typing

    from ._missing_words import declared_optional_return, point_shown
    from .domain import NO_ANNOTATION
    from .records import Probe
    from .runtime_types import SEQUENCE_KINDS
    from .types import missing_policy_from_signature
    kind = "absent" if cj.relation == "is_absent_safe" else "missing"
    word = "absence" if kind == "absent" else "a missing value"
    whole = cj.lhs not in facts.params
    params = list(facts.params) if whole else [cj.lhs]
    statement = f"{cj.relation}({cj.lhs})"
    misspecified = none_default_misspecified(fn, params) if kind == "absent" else None
    if misspecified:
        return Probe(cj.name, statement, "skipped:misspecified", route=None,
                     note=misspecified, meta={"mathema.invalid_conjecture": True})
    current = active_batch()
    signature = missing_policy_from_signature(fn)
    composed = composed_policies(fn, facts)
    lone = len(facts.params) == 1
    parts: list = []
    table: dict = {}
    failures: list = []
    nexts: list = []
    weakest = "proven"
    witness = None
    n = 0
    for p in params:
        sig = signature.get(p, NO_ANNOTATION)
        origin = (current.origins.get((p, kind)) if current else None)
        admitted = (sig.absent if kind == "absent" else bool(sig.members)) \
            or origin is not None
        slot = sig.slot_type or "unannotated"
        if not admitted:
            parts.append(f"{p} ({slot}) admits no {'None' if kind == 'absent' else 'hole'}")
            continue
        if origin is None or origin == "type":
            origin = "optional" if kind == "absent" and sig.annotated and sig.absent \
                else "type"
        container = facts.param_kinds.get(p) in (*SEQUENCE_KINDS, "table")
        # a numeric slot holds no NaT; only a datetime one does
        members = [m for m in _members_of(fn, p, kind)
                   if m != "NaT" or slot == "datetime"]
        said: list = []
        library_follows: list = []
        library_breaks: list = []
        guarded = [m for m in members if _guard_for(guards, fn, p, kind, m)]
        for m in members:
            calls = _relevant(current.calls if current else [], p, kind, m, "")
            floor = False
            if not calls:
                calls = _run_floor(fn, facts, _floor_points(fn, facts, p, kind, [m],
                                                            domain, cj), domain or {})
                floor = bool(calls)
            n += len(calls)
            entry: dict = {"member": m}
            table.setdefault(p, []).append(entry)
            if not calls:
                entry["source"] = "unstated"
                said.append(f"{m} was never reached")
                weakest = "unknown" if weakest != "falsified" else weakest
                continue
            ways = _decide(calls)
            stated = _stated_for(stated_rows, kind, p, m)
            # a stated row falsified at this member (not only at another)
            wrong = []
            for r in stated:
                pol = parse_policy(r.statement) if r.verdict == "falsified" else None
                bad = [c for c in calls if pol is not None
                       and _premise_holds(pol.premise, c.point) and not _follows(pol, c)]
                if bad:
                    wrong.append((r, bad[0]))
            stated = [r for r in stated if r.verdict != "falsified"
                      or any(r is w for w, _c in wrong)]
            if wrong:
                w, bad_call = wrong[0]
                did = _did(bad_call)
                entry.update({"source": "stated", "behaviour": did.split(" ")[0]})
                said.append(f"{m} {did}, contradicting the stated `{w.statement}`")
                failures.append(f"{w.statement} is falsified: {w.counterexample}")
                witness = witness or w.counterexample
                nexts.append(((w.meta or {}).get("mathema.policy") or {}).get("next")
                             or "")
                continue
            premised = [r for r in stated if ((r.meta or {}).get("mathema.policy")
                                               or {}).get("premise")]
            guard_here = _guard_for(guards, fn, p, kind, m)
            library_here = [] if guard_here or origin != "type" else \
                _library_for(composed, p, kind, m)
            if stated and not premised and all(r.verdict == "unknown" for r in stated):
                # a stated row the calls did not decide leaves the member
                # undecided
                entry["source"] = "stated"
                said.append(f"{m}: {stated[0].statement} is undecided ({stated[0].note})")
                weakest = "unknown" if weakest != "falsified" else weakest
                continue
            if stated and not premised:
                behaviour, call = next(iter(ways.items()))
                entry.update({"source": "stated", "behaviour": behaviour})
                said.append(f"{m} {_did(call)}, stated")
                continue
            if premised or (library_here and any(pol.premise for pol in library_here)):
                stated_pols = [q for q in (parse_policy(r.statement) for r in premised)
                               if q is not None]
                rest = [pol for pol in library_here
                        if pol.premise not in {q.premise for q in stated_pols}]
                broken = next(((pol, c) for c in calls for pol in rest
                               if _premise_holds(pol.premise, c.point)
                               and not _follows(pol, c)), None)
                uncovered = [c for c in calls
                             if not any(_premise_holds(q.premise, c.point)
                                        for q in stated_pols + rest)]
                if broken is not None:
                    pol, c = broken
                    entry.update({"source": "library", "behaviour": _behaviour_of(c)})
                    library_breaks.append((m, c, pol))
                    continue
                if uncovered:
                    c = uncovered[0]
                    entry.update({"source": "unstated", "behaviour": _behaviour_of(c)})
                    said.append(f"{m} {_did(c)} {_where(c, p, m)}, and no claim says "
                                f"it may")
                    failures.append(f"f {_did(c)} at {_at(c, p)}, and no claim says it may")
                    witness = witness or _witness(c)
                    continue
                if stated_pols:
                    entry["source"] = "stated"
                    pieces = []
                    if rest:
                        pieces.append(f"{_library_words(rest)}, from "
                                      f"{composed[p][0]}'s own policy row")
                    pieces.append(f"{_library_words(stated_pols)}, stated")
                    said.append(f"{m} " + "; ".join(pieces))
                else:
                    entry["source"] = "library"
                    library_follows.append(m)
                continue
            as_member = m if kind == "missing" else None
            if len(ways) > 1:
                row = _default_row(fn, p, kind, as_member, calls, origin, sig, guards,
                                   current, row_name, Probe)
                cases = _cases(calls, p, kind, m)
                both = (_split_words(cases, p) if cases and len(cases) > 1
                        else _and([_did(c) + " " + _where(c, p, m)
                                   for c in ways.values()]))
                entry.update({"source": "unstated", "behaviours": {
                    b: _at(c, None) for b, c in ways.items()}})
                said.append(f"{m} {both}, and no claim states either")
                failures.append(f"f has no single policy for {p} = {m}")
                witness = witness or "; ".join(_witness(c) for c in ways.values())
                nexts.append(((row.meta or {}).get("mathema.policy") or {}).get("next")
                             or "")
                continue
            behaviour, call = next(iter(ways.items()))
            entry["behaviour"] = behaviour
            if behaviour == "raises":
                entry["exception"] = call.raised
            did = _did(call)
            guard = guard_here
            if guard is not None:
                entry["source"] = "guard"
                if guard[0] != behaviour:
                    said.append(f"{m} {did}, where the guard on line {guard[2]} says "
                                f"{guard[0]}")
                    failures.append(f"the guard on line {guard[2]} says {guard[0]} for "
                                    f"{p} = {m}, and f {behaviour}")
                    witness = witness or _witness(call)
                    continue
                said.append(f"{m} {did}, from the guard on line {guard[2]}")
                continue
            if library_here:
                if all(_follows(pol, c) for pol in library_here for c in calls):
                    entry["source"] = "library"
                    library_follows.append(m)
                else:
                    entry["source"] = "library"
                    bad = next(c for c in calls
                               if not all(_follows(pol, c) for pol in library_here))
                    library_breaks.append((m, bad, library_here[0]))
                continue
            default = behaviour == ("raises" if kind == "absent" else "propagates") \
                and origin == "type"
            if behaviour == "raises" and not default:
                row = _default_row(fn, p, kind, as_member, calls, origin, sig, guards,
                                   current, row_name, Probe)
                entry["source"] = "unstated"
                said.append(f"{m} raises {call.raised}, and no claim says it may")
                failures.append(f"f raised {call.raised} at {_at(call, p)}, and no claim "
                                f"says it may")
                witness = witness or _witness(call)
                nexts.append(((row.meta or {}).get("mathema.policy") or {}).get("next")
                             or "")
                continue
            exhaustive = lone and not container
            entry["source"] = "exhaustive" if exhaustive else (
                "default" if default else "observed")
            said.append(f"{m} {did}, {_confirmed(calls, current, floor or exhaustive, p)}"
                        f"; no claim states it yet")
            if weakest == "proven":
                # what the code did, with no claim saying it should
                weakest = "holds"
        clauses = []
        if library_follows:
            key = composed[p][0]
            words = _library_words(_library_for(composed, p, kind, library_follows[0]),
                                   sep=", ")
            clauses.append(f"{_and(library_follows)} follow"
                           f"{'s' if len(library_follows) == 1 else ''} {key}'s own "
                           f"policy row ({words})" if len(_library_for(
                               composed, p, kind, library_follows[0])) > 1 else
                           f"{_and(library_follows)} "
                           f"{words if len(library_follows) == 1 else _plural(words)}, "
                           f"from {key}'s own policy row")
        for m, c, pol in library_breaks:
            key = composed[p][0]
            clauses.append(f"{m} does not: f {_did(c)} {_where(c, p, m)}"
                           if library_follows else
                           f"{m} does not follow {key}'s own policy row: f {_did(c)} "
                           f"{_where(c, p, m)}")
            failures.append(f"f does not follow {key}'s own policy row at {_at(c, p)}: "
                            f"f {_did(c).replace('raises', 'raised')} where the row says "
                            f"{pol.behaviour}")
            witness = witness or _witness(c)
            accepted = _cases([c], p, kind, m) or [replace(
                pol, member=m, behaviour=_behaviour_of(c),
                exception=c.raised if c.raised else None)]
            accepted = [replace(a, premise=a.premise or pol.premise) for a in accepted]
            verb = "the raise is" if c.raised else "that is"
            nexts.append(f"state {_written(accepted)} if {verb} intended, or change f")
        if said:
            clauses.append(_by_member(said))
        cover = ""
        if guarded and set(guarded) != set(members):
            cover = (f"; the guard covers {_and(guarded)}, not "
                     f"{_and([m for m in members if m not in guarded])}")
        parts.append(f"{p} ({slot}): {'; '.join(clauses)}{cover}")
        if guarded:
            for e in table.get(p, []):
                e["guarded"] = e["member"] in guarded
    # the fields and keys inside a parameter (R7): what a path reached
    # that is not a value, from the calls the check made and, for a
    # record's optional field no call reached, a floor of its own
    path_calls = _path_calls(fn, facts, params, kind, domain, current)
    for path, calls_here in path_calls.items():
        said = []
        by_member: dict = {}
        for c in calls_here:
            for m in _members_at(c, path, kind):
                by_member.setdefault(m, []).append(c)
        for m, calls in by_member.items():
            n += len(calls)
            entry = {"member": m}
            table.setdefault(path, []).append(entry)
            ways = _decide(calls)
            stated = [r for r in _stated_for(stated_rows, kind, path, m)
                      if ((r.meta or {}).get("mathema.policy") or {}).get("parameter")
                      == path]
            wrong = [r for r in stated if r.verdict == "falsified"]
            if wrong:
                w = wrong[0]
                entry.update({"source": "stated"})
                said.append(f"{m} contradicts the stated `{w.statement}`")
                failures.append(f"{w.statement} is falsified: {w.counterexample}")
                witness = witness or w.counterexample
                nexts.append(((w.meta or {}).get("mathema.policy") or {}).get("next") or "")
                continue
            if len(ways) > 1:
                entry["source"] = "unstated"
                said.append(f"{m} " + _and([_did(c) + " at " + _at(c, path)
                                            for c in ways.values()])
                            + ", and no claim states either")
                failures.append(f"f has no single policy for {path} ({m})")
                witness = witness or "; ".join(_witness(c, path) for c in ways.values())
                continue
            behaviour, call = next(iter(ways.items()))
            entry["behaviour"] = behaviour
            if stated:
                entry["source"] = "stated"
                said.append(f"{m} {_did(call)}, stated")
                continue
            if behaviour == "raises":
                row = _default_row(fn, path, kind, m, calls, "path", None, guards,
                                   current, row_name, Probe)
                entry.update({"source": "unstated", "exception": call.raised})
                said.append(f"{m} raises {call.raised}, and no claim says it may")
                failures.append(f"f raised {call.raised} at {_at(call, path)}, and no "
                                f"claim says it may")
                witness = witness or _witness(call, path)
                nexts.append(((row.meta or {}).get("mathema.policy") or {}).get("next")
                             or "")
                continue
            entry["source"] = "observed"
            said.append(f"{m} {_did(call)}, {_confirmed(calls, current, False, path)}; "
                        f"no claim states it yet")
            if weakest == "proven":
                weakest = "holds"
        if said:
            parts.append(f"{path} (field): {_by_member(said)}")
    from ._missing_policy import path_root
    for p in params:
        ann = _annotation(fn, p)
        if (ann is dict or typing.get_origin(ann) is dict) \
                and not any(path_root(q) == p for q in path_calls):
            parts.append(f"{p} is a plain dict, which states nothing about its keys, so "
                         f"the gate reaches a key only through a claim that binds it "
                         f"(`for {p}.key in ... | {{unset}}`)")
    if kind == "absent" and whole:
        # what the output may be: a None from present inputs is the
        # return type's to declare
        back = list(current.introduced) if current else []
        own = _present_calls(fn, facts, domain)
        n += len(own)
        back += [c for c in own if c.raised is None and c.output is None]
        if back:
            declared = declared_optional_return(fn)
            stated = [r for r in stated_rows
                      if ((r.meta or {}).get("mathema.policy") or {}).get("parameter") is None
                      and r.statement == "absent(f) introduces" and r.verdict != "falsified"]
            where = point_shown(back[0].point)
            if declared:
                parts.append(f"the result may be None, as the return type {declared} "
                             f"declares (f returned None at {where} from present inputs)")
            elif stated:
                parts.append(f"the result may be None, as stated (f returned None at "
                             f"{where} from present inputs)")
            else:
                import inspect
                try:
                    ann = inspect.signature(fn).return_annotation
                except (TypeError, ValueError):
                    ann = inspect.Signature.empty
                shown = ("no annotation" if ann is inspect.Signature.empty else
                         ann if isinstance(ann, str) else getattr(ann, "__name__", repr(ann)))
                sentence = (f"f returned None at {where} from present inputs, and its "
                            f"return type {shown} does not declare it")
                parts.append(sentence)
                failures.append(sentence)
                witness = witness or f"{where}: f returned None"
                nexts.append(f"declare the return type Optional[{shown}] if None is an "
                             f"answer f gives, or make f return a value there")
    sketch = "; ".join(parts) if parts else f"f has no parameter that admits {word}"
    meta = {"mathema.gate": {"kind": kind, "parameters": table}}
    nxt = next((x for x in nexts if x), "")
    if nxt:
        meta["mathema.gate"]["next"] = nxt
    if failures:
        meta["mathema.gate"]["reason"] = failures[0]
        return Probe(cj.name, statement, "falsified", n=n, route="probe:counterfactual",
                     counterexample=witness, note=sketch, sketch=sketch, meta=meta)
    if not table:
        return Probe(cj.name, statement, "proven", n=0, route="examine",
                     note=f"no parameter admits {word}; {sketch}", sketch=sketch,
                     meta=meta)
    if weakest == "unknown":
        return Probe(cj.name, statement, "unknown", n=n, route="probe:counterfactual",
                     note=sketch, sketch=sketch, meta=meta)
    return Probe(cj.name, statement, weakest, n=n,
                 route="examine" if weakest == "proven" else "probe:counterfactual",
                 note=sketch, sketch=sketch, meta=meta)
