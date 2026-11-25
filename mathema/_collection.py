# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim over a named finite collection, decided by enumerating it.

`for fn in pkg.mod.STAGES, describe(fn) == "(float) -> float"` ranges
`fn` over the members of a module-level tuple, list, frozenset or dict
(a dict's values; each member is named by its key). The collection is
finite and listed, so the claim is decided by judging every member,
never a sample of them: a collection either is enumerated whole, or
the claim is not decided.

A member is identified by its position, a name (a function's
qualified name, else its text capped in length) and a hash of what it
is (`_code_identity.membership_identity`: a function's source, or its
bytecode when there is no source, with its defaults, its closure and
the module-level names it reads; any other value by its type and
contents). The collection's own hash covers its kind and every member's
name and hash in order. A row's record keeps them, so a member added,
removed, reordered or changed makes the record stale; the claim's text
names only the dotted path, so its identity does not move when the
members do.

How a member is judged depends on where the bound name sits in the
claim:

- `argument`: the name is a parameter of the function, or a name the
  claim passes to a call (`decline_category(emit(fn))`). Each member is
  one point, and the claim is decided there by the point evaluator
  every finite sweep uses (`gates._point_evaluator`). A point is exact
  when both sides hold no float (texts, whole numbers, booleans,
  records of them) or the claim holds there in exact arithmetic.
- `subject`: the name is `f`. Each member is the function under test,
  and the rest of the claim is adjudicated against it as any claim on a
  function is.
- `function`: the name is called in the claim (`g(0.5) >= 0`). Each
  member is bound to that name as a `let g = ...` binding would bind it.

The verdicts of the members roll up (`roll_up`): falsified when any
member is, naming the first; unknown when any member is neither proven
nor holds; holds when every member is supported and one only holds;
proven when every member is proven. An empty collection is proven
vacuously, and the row says the collection is empty.
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field, replace

from .records import Probe, classify_verdict

__all__ = ["COLLECTION_MEMBER_BUDGET", "COLLECTION_META", "CollectionRefused",
           "Member", "collection_binding", "collection_hash", "collection_moved",
           "collection_record", "listed_members", "member_name", "resolve_collection",
           "roll_up"]

#: the most members a collection is enumerated over; a larger one leaves
#: the claim unknown, never sampled
COLLECTION_MEMBER_BUDGET = 1000  # :draft
#: the characters a member's text is capped at, where it has no
#: qualified name
NAME_CAP = 60  # :draft
#: the row meta key that records the collection a row was decided over
COLLECTION_META = "mathema.collection"  # :draft

#: the kinds of module-level value a collection may be
_KINDS: dict = {tuple: "tuple", list: "list", frozenset: "frozenset", dict: "dict"}


class CollectionRefused(ValueError):
    """The dotted path does not name a collection the domain reads."""


@dataclass(frozen=True)
class Member:
    """One member of a collection: its position, its name, the hash of
    what it is, and the value itself (never compared or recorded)."""
    index: int
    name: str
    digest: str
    value: object = field(default=None, compare=False, repr=False)

    def record(self) -> dict:
        """The member as the record lists it."""
        return {"index": self.index, "name": self.name, "hash": self.digest}


def _capped(text: str) -> str:
    return text if len(text) <= NAME_CAP else text[:NAME_CAP - 3] + "..."


def _text(value, depth: int = 3) -> str:
    """A member's text: a function or class by its qualified name, a
    tuple, list or dict by the text of its items, anything else by its
    `repr`, or by its type's name where the `repr` shows an address,
    which is not the same in another process."""
    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None)
    if callable(value) and isinstance(module, str) and isinstance(qualname, str):
        return f"{module}.{qualname}"
    if depth > 0 and type(value) in (tuple, list):
        inner = ", ".join(_text(v, depth - 1) for v in value)
        if type(value) is list:
            return f"[{inner}]"
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    if depth > 0 and type(value) is dict:
        return "{" + ", ".join(f"{_text(k, depth - 1)}: {_text(v, depth - 1)}"
                               for k, v in value.items()) + "}"
    try:
        said = repr(value)
    except Exception:
        return type(value).__qualname__
    return type(value).__qualname__ if " at 0x" in said else said


def member_name(value, key=None) -> str:
    """Intent:
        The name a member is reported by: a function's or class's
        qualified name (`pkg.mod.fn`), else its text (`_text`) capped at
        `NAME_CAP` characters; a dict member is named by its key, then
        the name of its value.
    """
    own = _capped(_text(value))
    return own if key is None else f"{_capped(_text(key))}: {own}"


def member_hash(value) -> str:
    """The hash of a member (`_code_identity.membership_identity`)."""
    from ._code_identity import membership_identity
    return membership_identity(value)


def listed_members(value) -> "tuple[str, tuple]":
    """Intent:
        `(kind, members)`: the kind of a collection value and its
        members, in the order they are listed: a tuple's or a list's
        in order, a dict's values in insertion order named by their
        keys, and a frozenset's sorted by name and hash, since a set
        lists no order of its own.

    Raises:
        CollectionRefused: the value is not a tuple, list, frozenset or
            dict.
    """
    kind = _KINDS.get(type(value))
    if kind is None:
        kind = next((k for t, k in _KINDS.items() if isinstance(value, t)), None)
    if kind is None:
        raise CollectionRefused(  # :draft
            f"is {_article(type(value).__name__)}, not a tuple, list, "
            f"frozenset or dict")
    if kind == "dict":
        found = [Member(i, member_name(v, key=k), member_hash(v), v)
                 for i, (k, v) in enumerate(value.items())]
    else:
        found = [Member(i, member_name(v), member_hash(v), v)
                 for i, v in enumerate(value)]
    if kind == "frozenset":
        found = [replace(m, index=i) for i, m in
                 enumerate(sorted(found, key=lambda m: (m.name, m.digest)))]
    return kind, tuple(found)


def _article(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


def resolve_collection(path: str) -> "tuple[str, tuple]":
    """Intent:
        `(kind, members)` for the module-level collection a dotted path
        names, resolved as a dotted language name or `let` reference is
        (`_claim_reach.walk_refusal`, then the longest importable
        module prefix and its attributes).

    Raises:
        CollectionRefused: the path reaches the system, does not
            resolve, or names a value that is not a collection.
    """
    from ._claim_reach import walk_refusal
    from .languages import _import_dotted
    said = walk_refusal(path)
    if said is not None:
        raise CollectionRefused(said)
    found = _import_dotted(path)
    if found is None:
        raise CollectionRefused(f"{path} does not resolve")  # :draft
    try:
        return listed_members(found)
    except CollectionRefused as e:
        raise CollectionRefused(f"{path} {e}") from None


def collection_hash(kind: str, members) -> str:
    """`cl:<sha>`, a 12-hex-char hash of a collection's kind and of
    every member's name and hash, in order."""
    text = json.dumps([kind, [[m.name, m.digest] for m in members]])
    return f"cl:{hashlib.sha256(text.encode('utf-8', 'surrogatepass')).hexdigest()[:12]}"


def collection_record(path: str, kind: str, members) -> dict:
    """The record of the collection a row was decided over: its path,
    kind, size, hash and members."""
    return {"path": path, "kind": kind, "size": len(members),
            "hash": collection_hash(kind, members),
            "members": [m.record() for m in members]}


def collection_moved(recorded: dict, now: "dict | None") -> "str | None":
    """Intent:
        What changed in a collection since its record, as the sentence
        verify reports, or None when nothing did: the members added,
        removed and changed by name, or that they were reordered. `now`
        None means the path no longer names a collection.
    """
    path = recorded.get("path", "?")
    if now is None:
        return f"the collection {path} no longer resolves"  # :draft
    if recorded.get("hash") == now.get("hash"):
        return None
    was = [(m.get("name"), m.get("hash")) for m in recorded.get("members") or []]
    is_ = [(m.get("name"), m.get("hash")) for m in now.get("members") or []]
    was_names = [n for n, _ in was]
    is_names = [n for n, _ in is_]
    said: list = []
    added = [n for n in is_names if n not in was_names]
    removed = [n for n in was_names if n not in is_names]
    before, after = dict(was), dict(is_)
    changed = [n for n in is_names if n in before and before[n] != after[n]]
    if added:
        said.append(f"{_listed(added)} added")  # :draft
    if removed:
        said.append(f"{_listed(removed)} removed")  # :draft
    if changed:
        said.append(f"{_listed(changed)} changed")  # :draft
    kept = [n for n in is_names if n in before]
    if kept != [n for n in was_names if n in after]:
        said.append("its members reordered")  # :draft
    if not said and now.get("kind") != recorded.get("kind"):
        said.append(f"it is now {_article(str(now.get('kind')))}")  # :draft
    elif not said:
        said.append("its members changed")  # :draft
    return f"the collection {path} moved: " + ", ".join(said)  # :draft


def _listed(names: list) -> str:
    shown = ", ".join(str(n) for n in names[:3])
    return shown if len(names) <= 3 else f"{shown} and {len(names) - 3} more"


#: the strength order of a member's verdict in the roll-up
_SUPPORT = {"proven": 2, "holds": 1}


def roll_up(verdicts) -> "tuple[str, int | None]":
    """Intent:
        `(verdict, index)`: the collection's verdict from its members'
        verdicts in order, and the index of the member that decides it
        (None when every member agrees, or there are none). Falsified
        when any member is falsified, at the first one; else unknown
        when any member is neither proven nor holds, at the first such;
        else holds when any member only holds, at the first; else
        proven, vacuously so over no members.
    """
    kinds = [classify_verdict(v or "") for v in verdicts]
    for kind, word in (("falsified", "falsified"),):
        if kind in kinds:
            return word, kinds.index(kind)
    for i, kind in enumerate(kinds):
        if kind not in _SUPPORT:
            return "unknown", i
    if "holds" in kinds:
        return "holds", kinds.index("holds")
    return "proven", None


def collection_binding(cj) -> "tuple[str, object] | None":
    """The `(name, CollectionRef)` a claim binds over a named
    collection, or None when it binds none."""
    from .domain import CollectionRef
    for name, bound in (getattr(cj, "domain", None) or {}).items():
        if isinstance(bound, CollectionRef):
            return name, bound
    return None


def _call_heads(cj) -> set:
    heads: set = set()
    for text in (cj.lhs, cj.rhs, *[t for link in (cj.links or [])
                                    for t in (link[0], link[2])]):
        try:
            tree = ast.parse(text or "0", mode="eval")
        except SyntaxError:
            continue
        heads |= {n.func.id for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return heads


def _names_read(cj) -> set:
    found: set = set()
    for text in (cj.lhs, cj.rhs, cj.assuming or "",
                 *[t for link in (cj.links or []) for t in (link[0], link[2])]):
        try:
            tree = ast.parse(text or "0", mode="eval")
        except SyntaxError:
            continue
        found |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    return found


def _reading(cj, name: str, params) -> "str | None":
    """Where the bound name sits: `subject`, `function`, `argument`, or
    None when the claim never reads it."""
    if name == "f":
        return "subject"
    if name in _call_heads(cj):
        return "function"
    if name in params or name in _names_read(cj):
        return "argument"
    return None


# --- adjudication -----------------------------------------------------

def _row(cj, statement: str, verdict: str, *, route=None, note="", counterexample=None,
         sketch=None, meta=None, n: int = 0) -> Probe:
    return Probe(cj.name, statement, verdict, n=n, route=route, note=note,
                 counterexample=counterexample, sketch=sketch, meta=dict(meta or {}))


def adjudicate(cj, fn, facts, domain: "dict | None" = None,
               budget: "int | None" = None) -> Probe:
    """Intent:
        The one row of a claim over a named collection: the collection
        resolved and listed, each member judged (see the module
        docstring), the members' verdicts rolled up, and the collection
        recorded in the row's meta (`COLLECTION_META`).
    """
    from .conjecture import statement_text
    name, ref = collection_binding(cj)
    statement = statement_text(cj.relation, cj.lhs, cj.rhs)
    budget = COLLECTION_MEMBER_BUDGET if budget is None else budget
    from .domain import CollectionRef
    named = [n for n, b in (cj.domain or {}).items() if isinstance(b, CollectionRef)]
    if len(named) > 1:
        return _row(cj, statement, "skipped:misspecified",  # :draft
                    note=f"{', '.join(named)} each range over a named collection; "
                         f"a claim ranges over one",
                    meta={"mathema.invalid_conjecture": True})
    try:
        kind, members = resolve_collection(ref.path)
    except CollectionRefused as e:
        return _row(cj, statement, "skipped:misspecified",  # :draft
                    note=f"{name} ranges over {ref.path}, which is not a named "
                         f"collection: {e}",
                    meta={"mathema.invalid_conjecture": True})
    except Exception as e:  # the module raised on import or on a member
        return _row(cj, statement, "skipped:misspecified",  # :draft
                    note=f"{name} ranges over {ref.path}, which could not be "
                         f"listed: {type(e).__name__}",
                    meta={"mathema.invalid_conjecture": True})
    record = collection_record(ref.path, kind, members)
    meta = {COLLECTION_META: record}
    if len(members) > budget:
        return _row(cj, statement, "unknown", meta=meta,  # :draft
                    note=f"the collection has {len(members)} members, more than "
                         f"the budget of {budget}")
    params = list(getattr(facts, "params", None) or [])
    reading = _reading(cj, name, params)
    if reading is None:
        return _row(cj, statement, "skipped:misspecified", meta=meta,  # :draft
                    note=f"{name} ranges over {ref.path}, but the claim never "
                         f"reads {name}")
    if not members:
        record["reading"] = reading
        return _row(cj, statement, "proven", route="derive:collection", meta=meta,  # :draft
                    sketch=f"the collection {ref.path} is empty, so the claim "
                           f"holds of every member vacuously",
                    note=f"the collection {ref.path} is empty")  # :draft
    if reading in ("subject", "function"):
        uncallable = next((m for m in members if not callable(m.value)), None)
        if uncallable is not None:
            return _row(cj, statement, "skipped:misspecified", meta=meta,  # :draft
                        note=f"{name} is called in the claim, but member "
                             f"{uncallable.index} of {ref.path} ({uncallable.name}) "
                             f"is not a function")
        judged = _each_as_function(cj, name, reading, members, fn, domain)
    else:
        judged = _each_as_point(cj, name, members, fn, facts, domain)
        if isinstance(judged, str):
            return _row(cj, statement, "unknown", meta=meta, note=judged)
    return _rolled(cj, statement, name, ref.path, reading, members, judged, record)


def _rolled(cj, statement, name, path, reading, members, judged, record) -> Probe:
    """The collection's row from each member's `(verdict, witness,
    note)`."""
    verdicts = [v for v, _w, _n in judged]
    verdict, at = roll_up(verdicts)
    record["reading"] = reading
    record["verdicts"] = verdicts
    meta = {COLLECTION_META: record}
    size = len(members)
    every = (f"all {size} members of {path}" if size != 1
             else f"the one member of {path}")
    if verdict == "proven":
        return _row(cj, statement, "proven", route="derive:collection", meta=meta,  # :draft
                    n=size,
                    sketch=f"{every} were judged, and the claim is proven of each",
                    note=f"enumerated {path}: {size} members listed, {size} judged")
    assert at is not None
    member = members[at]
    named = f"member {member.index} of {path}, {member.name}"  # :draft
    _v, witness, said = judged[at]
    if verdict == "falsified":
        return _row(cj, statement, "falsified", route="derive:collection", meta=meta,  # :draft
                    n=size,
                    counterexample=(f"{name} = {member.name} (member {member.index})"
                                    + (f": {witness}" if witness else "")),
                    note=f"the claim fails at {named}")
    if verdict == "holds":
        return _row(cj, statement, "holds", route="probe:collection", meta=meta,  # :draft
                    n=size,
                    note=f"enumerated {path}: {size} members listed, {size} judged, "
                         f"every one supports the claim; {named} is short of a "
                         f"proof" + (f": {said}" if said else ""))
    return _row(cj, statement, "unknown", meta=meta,  # :draft
                note=f"{named} is not decided" + (f": {said}" if said else ""))


def _each_as_function(cj, name, reading, members, fn, domain) -> list:
    """Each member's `(verdict, witness, note)` with the member as the
    function under test (`subject`) or bound to the name the claim calls
    (`function`), the rest of the claim adjudicated as written."""
    from .conjecture import check_conjectures
    rest = {k: v for k, v in (cj.domain or {}).items() if k != name}
    out = []
    for m in members:
        if reading == "subject":
            inner = replace(cj, domain=rest)
            target = m.value
        else:
            inner = replace(cj, domain=rest, funcs={**(cj.funcs or {}), name: m.value})
            target = fn
        rows = check_conjectures(target, [inner], domain=domain)
        row = next((r for r in rows if r.name == inner.name), None)
        if row is None:
            out.append(("unknown", None, "no row came back"))
            continue
        out.append((row.verdict, row.counterexample, row.note or ""))
    return out


def _numberless(value, depth: int = 4) -> bool:
    """Whether a value holds no float, complex or decimal number: a
    text, a whole number, a boolean, None, or a container of them."""
    import numbers
    if isinstance(value, (bool, int, str, bytes, type(None))):
        return True
    if depth <= 0:
        return False
    if isinstance(value, (tuple, list, frozenset, set)):
        return all(_numberless(v, depth - 1) for v in value)
    if isinstance(value, dict):
        return all(_numberless(k, depth - 1) and _numberless(v, depth - 1)
                   for k, v in value.items())
    if isinstance(value, numbers.Number):
        return False
    return False


def _each_as_point(cj, name, members, fn, facts, domain):
    """Each member's `(verdict, witness, note)` with the member as the
    value of `name` at one point, decided by the point evaluator; or the
    reason, as text, that the members cannot be judged this way."""
    import itertools

    from . import _brute_force
    from .conjecture import (Probe as _Probe, _bind_scope_functions, _bound_funcs_of,
                             _effective_facts, _validate_claim, statement_text)
    from .domain import finite_members
    from .gates import _point_evaluator
    from .runtime_types import calling
    if cj.assuming:
        return ("a premise beside a collection the claim passes as an "  # :draft
                "argument is not read yet")
    rest = {k: v for k, v in (cj.domain or {}).items() if k != name}
    params = list(getattr(facts, "params", None) or [])
    free = cj.free_vars if name in params else cj.free_vars | {name}
    inner = replace(cj, domain=rest, free_vars=frozenset(free), funcs=dict(cj.funcs or {}))
    facts = _effective_facts(fn, facts)
    # the members are the values the parameter is called with, as for
    # any binding whose values the claim states; a parameter the claim
    # never names is passed what the claim's call passes it
    read = _names_read(cj)
    stated = {p: "unknown" for p in params if p == name or p not in read}
    facts = replace(facts, param_kinds={**facts.param_kinds, **stated})
    note = _bind_scope_functions(inner, fn).lstrip("; ")
    validated = _validate_claim(inner, statement_text(inner.relation, inner.lhs, inner.rhs),
                                note, facts, dict(domain or {}), fn=fn)
    if isinstance(validated, _Probe):
        return validated.note or "the claim could not be read at a point"
    bound_funcs = _bound_funcs_of(validated.cj)
    deps = _point_evaluator(validated.cj, calling(fn, facts), facts,
                            validated.cj_domain, bound_funcs)
    if deps is None:
        return ("the claim cannot be evaluated at a point, so its members "  # :draft
                "cannot each be judged")
    names = list(deps["names"])
    others = [n for n in names if n != name]
    grid: dict = {}
    total = 1
    for other in others:
        bound = validated.cj_domain.get(other)
        listed = (finite_members(bound, _brute_force.BRUTE_FORCE_POINT_BUDGET)
                  if bound is not None else None)
        if listed is None:
            return (f"{other} has no finite domain, and a collection is "  # :draft
                    f"enumerated only beside finite bindings")
        grid[other] = listed
        total *= len(listed)
    if total * len(members) > _brute_force.BRUTE_FORCE_POINT_BUDGET:
        return (f"the collection with its other bindings gives "  # :draft
                f"{total * len(members)} points, more than the budget of "
                f"{_brute_force.BRUTE_FORCE_POINT_BUDGET}")
    stateful = _brute_force._examination_obstacle(fn)
    if stateful is _brute_force._STATEFUL:
        return ("the function writes or reads state outside its arguments, so "  # :draft
                "one call per member is not the whole story")
    unread = stateful if stateful is not None else (
        None if facts.is_pure is True else "the function is not shown to be pure")
    evaluate, admits = deps["evaluate"], deps["admits"]
    out = []
    for m in members:
        member_unread = unread
        if member_unread is None and callable(m.value):
            obstacle = _brute_force._examination_obstacle(m.value)
            if obstacle is not None:
                member_unread = (f"{m.name} is not shown to be pure"
                                 if obstacle is _brute_force._STATEFUL else obstacle)
        held_all, exact_all, failed_at, undecided = True, True, None, None
        for combo in itertools.product(*(grid[o] for o in others)):
            point = {name: m.value, **dict(zip(others, combo))}
            if not admits(point):
                continue
            try:
                said = evaluate(point)
            except Exception as e:  # the claim's own reading failed there
                undecided = f"reading the claim there raised {type(e).__name__}"  # :draft
                break
            if said is None:
                undecided = "the claim could not be evaluated there"  # :draft
                break
            if said is False:
                failed_at = point
                break
            sides = evaluate.sides()
            if not (sides is not None and all(_numberless(s) for s in sides)):
                exact, _ = _brute_force._exactly_at(validated.cj, evaluate, point)
                if exact is False:
                    failed_at = point
                    break
                if exact is None:
                    exact_all = False
        if failed_at is not None:
            shown = ", ".join(f"{o} = {failed_at[o]!r}" for o in others)
            out.append(("falsified", shown, ""))
        elif undecided is not None:
            out.append(("unknown", None, undecided))
        elif held_all and exact_all and member_unread is None:
            out.append(("proven", None, ""))
        else:
            out.append(("holds", None,  # :draft
                        f"proven needs the function to be shown pure: {member_unread}"
                        if member_unread else
                        "a side holds a float the claim could not decide exactly"))
    return out


def stamped(row: Probe, cj) -> Probe:
    """Intent:
        The row with the claim's canonical text and its structured
        fields beside it, as every row carries them: the statement, the
        domain (a collection as its path), the condition, the grammar,
        the tolerance, the source and the claim's own meta.
    """
    from ._tolerance import written_tolerance
    from .domain import domain_bound_to_json, render_domain
    from .spec import canonical_claim_text
    row.statement = canonical_claim_text(cj)
    if cj.domain:
        row.domain = {p: domain_bound_to_json(b) for p, b in cj.domain.items()}
        row.condition = "for " + ", ".join(
            f"{p} in {render_domain(b, ascii_mode=True)}" for p, b in cj.domain.items())
    row.grammar = cj.grammar
    row.tolerance = written_tolerance(cj.tolerance)
    meta = {**(cj.meta or {}), **(row.meta or {})}
    if cj.source:
        meta.setdefault("mathema.surface", cj.source)
    row.meta = meta
    return row
