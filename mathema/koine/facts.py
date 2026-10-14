# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A KOINE document read into the `Facts` the engine derives from.

`facts_from_koine(document)` validates the document, counts its
structure from the body (loops, branches, recursion) and its guards,
renders the body to the liftable Python subset, and returns a `Facts`
whose `koine` is the document and whose `tree` is the rendering. The
loop rows and call groups are read off the rendered tree, since they
are spelled in Python. A document the engine cannot take is declined
with `KoineDeclined`, carrying the engine's decline shape
`{"line", "statement", "message", "category"}`:

- `invalid-koine`: the text does not parse, or the document is not
  valid KOINE;
- `structure-conflict`: the document's `structure` line disagrees
  with the counts taken from its body;
- `unsupported-koine-feature`: the body has no rendering in the
  liftable subset.

`hydrated(facts)` is the one place a `Facts` carrying `koine` and no
`tree` gets its tree and structural fields; `rendered_scope(facts)` is
what the rendered body's names resolve in, and `sibling_scope(fn,
siblings)` the same with the other functions of the program the body
calls bound under the names the rendering calls them by.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, replace
from typing import Iterator, Mapping

from ..analysis import Facts, _call_groups, _loops, _max_depth
from ._render import RenderError, materialise, namespace, render
from .canonical import koine_hash
from .document import Document
from .syntax import KoineSyntaxError, List, Name, Term
from .validate import validate
from .vocabulary import LOOPS

#: the categories `facts_from_koine` declines with
INVALID = "invalid-koine"
STRUCTURE_CONFLICT = "structure-conflict"
UNSUPPORTED = "unsupported-koine-feature"

#: KOINE kinds with no `Facts` kind of the same name, and the kind each
#: is read as
_KIND_READS = {"record": "dict"}
_FACTS_KINDS = frozenset({"scalar", "int", "bool", "complex", "string", "sequence",
                          "vec", "mat", "table", "dict", "unknown"})
_RETURNS_KINDS = frozenset({"scalar", "sequence", "bool"})


class KoineDeclined(ValueError):
    """A KOINE document the engine does not take; `decline` says where
    and why, in the engine's decline shape."""

    def __init__(self, decline: dict):
        super().__init__(f"{decline['category']}: {decline['message']}")
        self.decline = decline


@dataclass(frozen=True)
class Structure:
    """The structural counts of a body: its loops, its branches (a
    `statement::branch` or a `statement::require`, each one `if`), and
    whether it calls its own function."""
    loops: int
    branches: int
    recursion: bool


def _declined(category: str, message: str, statement: Term | None = None) -> KoineDeclined:
    line = None
    text = None
    span = statement.get("at") if isinstance(statement, Term) else None
    if isinstance(span, Term) and len(span.args) == 3:
        line = getattr(span.args[0], "value", None)
        text = getattr(span.args[2], "value", None) or None
    return KoineDeclined({"line": line, "statement": text, "message": message,
                          "category": category})


def _document(doc) -> Document:
    if isinstance(doc, str):
        try:
            doc = Document.parse(doc)
        except KoineSyntaxError as e:
            raise _declined(INVALID, str(e)) from None
    if not isinstance(doc, Document):
        raise TypeError(f"not a KOINE document: {type(doc).__name__}")
    problems = validate(doc)
    if problems:
        raise _declined(INVALID, "; ".join(problems))
    return doc


def statements(stmts) -> Iterator[Term]:
    """Intent:
        Every statement in `stmts` and in the blocks nested inside
        them, outermost first.
    """
    for st in stmts:
        if not isinstance(st, Term):
            continue
        yield st
        for a in st.args:
            if isinstance(a, List):
                yield from statements(a.items)


def _terms(node) -> Iterator[Term]:
    """Every term inside `node`, `node` included."""
    if isinstance(node, Term):
        yield node
        for a in node.args:
            yield from _terms(a)
        for _, v in node.named:
            yield from _terms(v)
    elif isinstance(node, List):
        for x in node.items:
            yield from _terms(x)


def structure(doc: Document) -> Structure:
    """Intent:
        The structural counts of `doc`'s body: one loop per
        `statement::loop::*`, one branch per `statement::branch` and
        `statement::require`, recursion when a `call::function` names
        the document's own key.
    """
    loops = branches = 0
    recursion = False
    for st in statements(doc.body):
        if st.head in LOOPS:
            loops += 1
        elif st.head in ("statement::branch", "statement::require"):
            branches += 1
    if doc.key is not None:
        recursion = any(t.head == "call::function" and t.args
                        and getattr(t.args[0], "value", None) == doc.key
                        for t in _terms(doc.first("body")))
    return Structure(loops, branches, recursion)


def _names(node, params: set) -> set:
    found = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, Name) and n.id in params:
            found.add(n.id)
        elif isinstance(n, Term):
            stack.extend(n.args)
            stack.extend(v for _, v in n.named)
        elif isinstance(n, List):
            stack.extend(n.items)
    return found


def guards(doc: Document) -> dict:
    """Intent:
        The enforcement posture of each parameter, read off the body:
        `raise` when the parameter appears in the test of a
        `statement::require` or of a `statement::branch` whose first
        block fails at once, `clamp` when it is passed bare to
        `function::order::minimum` or `maximum` and is not refused,
        `none` otherwise.
    """
    params = list(doc.parameter_names)
    pset = set(params)
    raised: set = set()
    clamped: set = set()
    for st in statements(doc.body):
        if st.head == "statement::require" and st.args:
            raised |= _names(st.args[0], pset)
        elif st.head == "statement::branch" and len(st.args) == 3 \
                and isinstance(st.args[1], List) \
                and any(isinstance(s, Term) and s.head == "statement::fail"
                        for s in st.args[1].items):
            raised |= _names(st.args[0], pset)
    for t in _terms(doc.first("body")):
        if t.head in ("function::order::minimum", "function::order::maximum"):
            clamped |= {a.id for a in t.args if isinstance(a, Name) and a.id in pset}
    return {p: "raise" if p in raised else "clamp" if p in clamped else "none"
            for p in params}


def _check_structure(doc: Document, counted: Structure) -> None:
    stated = doc.first("structure")
    if stated is None:
        return
    said = {k: getattr(v, "value", None) for k, v in stated.named}
    found = {"loops": counted.loops, "branches": counted.branches,
             "recursion": counted.recursion}
    conflicts = [f"{k}: {str(said[k]).lower()} stated, {str(v).lower()} in the body"
                 for k, v in found.items() if k in said and said[k] != v]
    if conflicts:
        raise _declined(STRUCTURE_CONFLICT, "the structure line disagrees with the body ("
                        + "; ".join(conflicts) + ")")


def _kind(term) -> str:
    kind = term.head.rpartition("::")[2] if isinstance(term, Term) else "unknown"
    kind = _KIND_READS.get(kind, kind)
    return kind if kind in _FACTS_KINDS else "unknown"


def facts_from_koine(doc) -> Facts:
    """Intent:
        The `Facts` the engine reads `doc` (a `Document`, or KOINE text)
        by: its name, parameters and kinds from the envelope, its
        structure and guards from the body, its tree and source from the
        rendering, and `koine_hash` as its form.

    Raises:
        KoineDeclined: the document is not valid KOINE, its structure
            line disagrees with its body, or its body has no rendering.
    """
    doc = _document(doc)
    counted = structure(doc)
    _check_structure(doc, counted)
    try:
        rendered = render(doc)
    except RenderError as e:
        raise _declined(UNSUPPORTED, str(e)) from None
    tree = rendered.tree
    params = list(doc.parameter_names)
    kinds = {p.args[0].id: _kind(p.args[1] if len(p.args) > 1 else None)
             for p in doc.parameters}
    returns = doc.first("returns")
    returns_kind = _kind(returns.args[0]) if returns is not None and returns.args else "unknown"
    if returns_kind not in _RETURNS_KINDS:
        returns_kind = "unknown"
    signature = "(" + ", ".join(
        f"{a.arg}: {ast.unparse(a.annotation)}" if a.annotation is not None else a.arg
        for a in tree.args.args) + ")"
    if tree.returns is not None:
        signature += f" -> {ast.unparse(tree.returns)}"
    groups, _ = _call_groups(tree, tree.name)
    return Facts(
        name=doc.name or tree.name,
        signature=signature,
        params=params,
        param_kinds=kinds,
        returns_kind=returns_kind,
        docstring=None,
        source=rendered.source,
        effects=[],
        is_pure=True,
        loops=_loops(tree),
        comprehensions=[],
        recursion=counted.recursion,
        branch_count=counted.branches,
        call_groups=groups,
        max_loop_depth=_max_depth(tree),
        lines=len(rendered.source.strip().splitlines()),
        form=koine_hash(doc),
        sigh=hashlib.sha256(signature.encode()).hexdigest()[:12],
        tree=tree,
        guards=guards(doc),
        koine=doc,
    )


def hydrated(facts: Facts) -> Facts:
    """Intent:
        `facts` with its tree and structural fields (loops, branches,
        recursion, guards, call groups, loop depth) taken from its
        KOINE document, when it carries one and no tree; `facts` itself
        otherwise, or when the document is declined. Every other field
        is kept as given. The result is computed once per document and
        reused.
    """
    doc = getattr(facts, "koine", None)
    if doc is None or facts.tree is not None:
        return facts
    cached = getattr(facts, "_koine_hydrated", None)
    if cached is not None and cached[0] is doc:
        return cached[1]
    try:
        derived = facts_from_koine(doc)
    except KoineDeclined:
        out = facts
    else:
        out = replace(facts, tree=derived.tree, loops=derived.loops,
                      comprehensions=derived.comprehensions,
                      recursion=derived.recursion,
                      branch_count=derived.branch_count,
                      call_groups=derived.call_groups,
                      max_loop_depth=derived.max_loop_depth,
                      guards=derived.guards)
    facts._koine_hydrated = (doc, out)  # type: ignore[attr-defined]
    return out


def rendered_scope(facts) -> dict:
    """Intent:
        The names the rendered body of `facts.koine` reads besides its
        parameters: `math`, the helpers under their aliases and the
        exception classes it raises. Empty when `facts` carries no
        document or the document has no rendering. Computed once per
        document and reused.
    """
    doc = getattr(facts, "koine", None)
    if not isinstance(doc, Document):
        return {}
    cached = getattr(facts, "_koine_scope", None)
    if cached is not None and cached[0] is doc:
        return cached[1]
    try:
        scope = namespace(render(doc))
    except (RenderError, IndexError, AttributeError, TypeError):
        scope = {}
    facts._koine_scope = (doc, scope)  # type: ignore[attr-defined]
    return scope


def sibling_scope(fn, siblings: Mapping[str, object]) -> dict:
    """The names a lifted body reads, with the functions it calls bound.

    `fn` is a callable whose injected facts (`__mathema_facts__`) carry
    a KOINE document, or those facts themselves. `siblings` maps the
    locator a body calls another function of its program by (the key
    in its `call::function` term) to that function: its document, as a
    document or as KOINE text, or a callable. A document is bound as
    the engine's rendering of it, its own calls bound from the same
    mapping (mutual calls included); a callable is bound as given, and
    one carrying its own lifted body is read through that body.

    The result is the scope `rendered_scope` gives (`math`, the
    helpers, the exception classes the body raises) with each sibling
    the body calls added under the name its rendering calls it by.
    Set it as the callable's `__mathema_scope__` and every reading of
    the body (derive among them) resolves the calls in it. A sibling
    the body does not reach is left out; a call whose locator is not
    in `siblings`, or whose document has no rendering, stays unbound,
    and derive declines to read through it.

    Returns an empty mapping when `fn` carries no document or the
    document has no rendering.
    """
    facts = fn if isinstance(fn, Facts) else getattr(fn, "__mathema_facts__", None)
    doc = getattr(facts, "koine", None)
    if not isinstance(doc, Document):
        return {}
    try:
        rendered = render(doc)
    except (RenderError, IndexError, AttributeError, TypeError):
        return {}
    bound = _bound_siblings(rendered.externals, siblings)
    return {**rendered_scope(facts), **bound}


def materialised(doc: Document, siblings: "Mapping[str, object] | None" = None):
    """Intent:
        The engine's rendering of `doc` as a Python function in a
        module of its own, its calls to other functions of the program
        bound from `siblings` as `sibling_scope` binds them; a call
        `siblings` does not resolve stays unbound.

    Raises:
        RenderError: the body has no rendering.
    """
    rendered = render(doc)
    fn = materialise(rendered, key=doc.key,
                     bindings={name: None for name in rendered.externals})
    bound = _bound_siblings(rendered.externals, siblings or {})
    for name in rendered.externals:
        if name in bound:
            fn.__globals__[name] = bound[name]
        else:
            fn.__globals__.pop(name, None)
    return fn


def sibling_documents(siblings: "Mapping[str, object] | None") -> dict:
    """Intent:
        `{locator: Document}` for each entry of `siblings` given as a
        document or as KOINE text the engine takes; callables and
        declined documents are left out.
    """
    out: dict = {}
    for key, value in (siblings or {}).items():
        if isinstance(value, (Document, str)):
            try:
                out[key] = _document(value)
            except KoineDeclined:
                continue
    return out


def _bound_siblings(externals: dict, siblings: Mapping[str, object]) -> dict:
    """Intent:
        `{name: function}` for each name in `externals` (rendered name
        to locator) whose locator `siblings` resolves: a callable as
        given, a document materialised from its rendering. Every
        document reachable through the calls is materialised once, and
        each one's own names are bound after all are made, so siblings
        that call each other resolve.
    """
    made: dict = {}
    pending = sorted(set(externals.values()))
    while pending:
        key = pending.pop()
        if key in made or key not in siblings:
            continue
        value = siblings[key]
        if callable(value) and not isinstance(value, (Document, str)):
            made[key] = (value, {})
            continue
        try:
            sibling = _document(value)
            sibling_rendered = render(sibling)
        except (KoineDeclined, TypeError, RenderError, IndexError, AttributeError):
            continue
        fn = materialise(sibling_rendered, key=key,
                         bindings={name: None for name in sibling_rendered.externals})
        made[key] = (fn, sibling_rendered.externals)
        pending.extend(k for k in sibling_rendered.externals.values() if k not in made)
    for fn, own in made.values():
        for name, key in own.items():
            if key in made:
                fn.__globals__[name] = made[key][0]
            else:
                fn.__globals__.pop(name, None)
    return {name: made[key][0] for name, key in externals.items() if key in made}


def provenance(facts) -> dict | None:
    """Intent:
        Where the body `facts` are read by came from, as the record
        states it: `facts.provenance` as supplied, with `koine_hash` set
        to the hash of the document carried, `frontend` taken from the
        document's `lifter` line when not supplied, and `body_hashes`
        when more than one frontend wrote the body. None when
        `facts` carries no document and no provenance, as for a Python
        function read from its source.
    """
    doc = getattr(facts, "koine", None)
    stated = getattr(facts, "provenance", None)
    if not isinstance(doc, Document):
        return dict(stated) if stated else None
    out = dict(stated or {})
    out.setdefault("frontend", doc.lifter)
    out["koine_hash"] = koine_hash(doc)
    hashes = getattr(facts, "body_hashes", None) or {}
    if len(hashes) > 1:
        out["body_hashes"] = dict(hashes)
    return out


def provenance_change(now: dict | None, was: dict | None) -> str | None:
    """Intent:
        What moved between two body provenances (`provenance(facts)`
        now, and as a record states it): `"body"` when the
        `koine_hash`, or the hash of the body any frontend that could
        write it wrote (`body_hashes`), differs; `"frontend"` when the
        frontend that wrote it (its name or version) differs; None when
        neither did, or neither side has a provenance.
    """
    now = now or {}
    was = was or {}
    if not now and not was:
        return None
    if now.get("koine_hash") != was.get("koine_hash") \
            or now.get("body_hashes") != was.get("body_hashes"):
        return "body"
    if now.get("frontend") != was.get("frontend"):
        return "frontend"
    return None
