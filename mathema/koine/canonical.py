# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The canonical form of a KOINE document, and `koine_hash` over it.

The canonical form keeps what a function computes and drops how it was
written and by whom:

- kept: `koine`, the `feature` lines (sorted), the `parameter` lines
  (kinds, and a record's field names: the mathematical domain) and
  `body`;
- dropped: `lifter`, `source`, `function` (name and key are identity),
  `returns` (derived from the body), `manifest` (how a runtime shows a
  non-value, a property of the runtime rather than the mathematics),
  `structure`, every parameter's representation (`f64`, `i64`, `f32`:
  the machine, not the mathematics) and `element:`, every `at:` span,
  and a failure's type and message (the spelling of a refusal; its
  kind stays);
- respelled: a real literal with an integral value as that integer
  (`1.0` is `1`), any other real as the shortest decimal that
  round-trips its binary64 value; a negated numeric literal as the
  negative literal; `operator::unary::identity(x)` as `x`;
- renamed: parameters to `_p0`, `_p1`, ... in declaration order, and
  locals to `_0`, `_1`, ... in order of first binding. A function's
  interface is positional; what it calls its inputs is documentation,
  so two bodies that differ only in parameter names hash alike.
- respelled: a call to another function of the program, by what its
  callee computes rather than by the locator addressing it. A call to
  the function's own key is `call::self(args...)`. A call to a key
  found in `siblings` becomes `call::hashed(hash, args...)`, `hash`
  being that callee's own canonical hash, computed the same way over
  the same `siblings`; a callee already on the hashing stack (mutual
  recursion) becomes `call::ancestor(k, args...)` instead, `k` the
  number of frames up the stack, which keeps the hashing finite. A key
  `siblings` does not reach (a library, another file, an unresolved
  name) keeps only its bare last segment, `call::external(name, args...)`.

The canonical spelling is the compact printing, one term per line.
`koine_hash` is `koine-<version>:` and the first sixteen hex digits of its
SHA-256.

The nominal form is the canonical form with parameter names kept and
every call to another function of the program left exactly as the
document writes it, locator and all. `nominal_hash` is the same digest
over it. It answers a different question: not "the same mathematics"
but "the same mathematics behind the same interface", which is what a
claim written in those names needs before it can be adjudicated
unchanged on the other function.

Pure functions; the document is never mutated.
"""
from __future__ import annotations

import hashlib

from .document import Document
from .vocabulary import KOINE_VERSION
from .syntax import Int, List, Name, Real, Str, Term, compact_document

HASH_PREFIX = f"koine-{KOINE_VERSION}:"

_KEEP = ("koine", "feature", "parameter", "body")


def canonical_terms(doc: Document, *, nominal: bool = False, siblings: dict | None = None
                    ) -> tuple:
    """Intent:
        The document's terms in canonical form; with `nominal`, the
        parameters keep their names and a call to another function of
        the program keeps its locator. Otherwise `siblings` (locator to
        that callee's own `Document`) lets a call be respelled by what
        it calls rather than by how the callee is addressed.
    """
    calls = None if nominal else _Calls(siblings or {})
    return _canonical_terms(doc, nominal=nominal, calls=calls, stack=())


def _canonical_terms(doc: Document, *, nominal: bool, calls: "_Calls | None",
                     stack: tuple) -> tuple:
    params = list(doc.parameter_names)
    names = _Renamer(params, rename_params=not nominal, calls=calls, key=doc.key, stack=stack)
    kept = [t for t in doc.terms if isinstance(t, Term) and t.head in _KEEP]
    features = sorted((t for t in kept if t.head == "feature"),
                      key=lambda t: compact_document([t]))
    out = [t for t in kept if t.head == "koine"] + features
    out += [_parameter(t, names) for t in kept if t.head == "parameter"]
    for t in kept:
        if t.head == "body":
            out.append(Term("body", tuple(_statement(s, names) for s in t.args)))
    return tuple(out)


def canonical_text(doc: Document, siblings: dict | None = None) -> str:
    """Intent:
        The canonical spelling: `compact` of each canonical term, one
        per line.
    """
    return compact_document(canonical_terms(doc, siblings=siblings))


def nominal_text(doc: Document) -> str:
    """Intent:
        The nominal spelling: the canonical spelling with the
        parameters' own names and every call to another function of
        the program left as its locator.
    """
    return compact_document(canonical_terms(doc, nominal=True))


def _digest(text: str) -> str:
    return HASH_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def koine_hash(doc: Document, siblings: dict | None = None) -> str:
    """Intent:
        `koine-<version>:<sha256[:16]>` over the canonical spelling.
        `siblings` (locator to that callee's own `Document`) lets a
        call to another function of the program hash by what it calls.
    """
    return _digest(canonical_text(doc, siblings))


def nominal_hash(doc: Document) -> str:
    """Intent:
        `koine-<version>:<sha256[:16]>` over the nominal spelling.
    """
    return _digest(nominal_text(doc))


def unresolved_calls(doc: Document, siblings: dict | None = None) -> tuple:
    """Intent:
        The locators, sorted, of every call the canonical hash of `doc`
        rests on by bare name alone: calls in `doc`, or in a sibling it
        reaches, to a function that is neither the caller itself nor in
        `siblings`. Two different locators with the same last segment
        hash alike, so equal canonical hashes are equal only up to
        these callees.
    Notes:
        `koine_hash` is unaffected; this reports what it depends on.
    """
    siblings = siblings or {}
    found: set = set()
    seen = {doc.key}
    pending = [doc]
    while pending:
        current = pending.pop()
        names: list = []
        _collect_calls(current.terms, names)
        for locator in names:
            if locator == current.key:
                continue
            if locator in siblings:
                if locator not in seen:
                    seen.add(locator)
                    pending.append(siblings[locator])
            else:
                found.add(locator)
    return tuple(sorted(found))


def _bare_name(locator: str) -> str:
    """The locator's last segment: after its last `#` (a
    `py:<file>#<name>` locator) if it has one, else after its last `.`
    (a `module.qualname` locator), else the locator itself."""
    return locator.rpartition("#")[2].rpartition(".")[2]


class _Calls:
    """Resolves a `call::function` locator against the siblings
    supplied with the document: the function's own key is `call::self`, a key
    already on the hashing stack is `call::ancestor`, a key `siblings`
    reaches is `call::hashed` of that callee's own canonical hash
    (followed through the same siblings, so a chain of calls resolves
    throughout), and anything else is `call::external` of its bare
    name.

    A callee's hash depends on the stack above it only through the
    stack entries its calls can reach, and the distance to each. Hashes
    are remembered under exactly that context, so a callee reached by
    many paths is hashed once per distinct context, not once per path."""

    def __init__(self, siblings: dict):
        self.siblings = siblings
        self._callees: dict = {}
        self._memo: dict = {}

    def resolve(self, locator: str, key: str, stack: tuple, args: tuple) -> Term:
        if locator == key:
            return Term("call::self", args)
        if locator in stack:
            return Term("call::ancestor", (Int(len(stack) - stack.index(locator)),) + args)
        sibling = self.siblings.get(locator)
        if sibling is None:
            return Term("call::external", (Str(_bare_name(locator)),) + args)
        return Term("call::hashed", (Str(self._hash(locator, sibling, stack + (key,))),) + args)

    def _hash(self, locator: str, sibling: Document, stack: tuple) -> str:
        context = (locator, sibling.key, self._context(locator, stack))
        found = self._memo.get(context)
        if found is None:
            terms = _canonical_terms(sibling, nominal=False, calls=self, stack=stack)
            found = self._memo[context] = _digest(compact_document(terms))
        return found

    def _context(self, locator: str, stack: tuple) -> tuple:
        """The (stack entry, distance up the stack) pairs a hash of
        `locator` can observe: entries called from `locator` or from a
        sibling reached through calls that avoid the stack."""
        on_stack = set(stack)
        seen, pending, touched = {locator}, [locator], set()
        while pending:
            for callee in self._callees_of(pending.pop()):
                if callee in on_stack:
                    touched.add(callee)
                elif callee in self.siblings and callee not in seen:
                    seen.add(callee)
                    pending.append(callee)
        return tuple(sorted((e, len(stack) - stack.index(e)) for e in touched))

    def _callees_of(self, locator: str) -> tuple:
        found = self._callees.get(locator)
        if found is None:
            names: list = []
            _collect_calls(self.siblings[locator].terms, names)
            found = self._callees[locator] = tuple(dict.fromkeys(names))
        return found


def _collect_calls(node, out: list) -> None:
    """Appends the locator of every `call::function` under `node`."""
    if isinstance(node, Term):
        if node.head == "call::function" and node.args and isinstance(node.args[0], Str):
            out.append(node.args[0].value)
        for child in node.args:
            _collect_calls(child, out)
        for _, child in node.named:
            _collect_calls(child, out)
    elif isinstance(node, (List, tuple)):
        for child in (node.items if isinstance(node, List) else node):
            _collect_calls(child, out)


def _parameter(p: Term, names: "_Renamer") -> Term:
    """A parameter line with only its (renamed) name and kind; a
    record's fields keep their names, which are part of its shape."""
    args = tuple(names.use(a) if i == 0 else a for i, a in enumerate(p.args[:2]))
    named = []
    for key, value in p.named:
        if key == "fields" and isinstance(value, List):
            named.append((key, List(tuple(
                Term(f.head, f.args[:2]) if isinstance(f, Term) else f for f in value.items))))
    return Term(p.head, tuple(args), tuple(named))


def _number(text: str):
    """A real literal's canonical node: the integer when its value is
    integral, else the shortest round-trip decimal."""
    value = float(text)
    if value.is_integer():
        return Int(int(value))
    return Real(repr(value))


class _Renamer:
    """Parameters become `_p<i>` by declaration order (unless kept
    nominal); locals become `_<j>` by order of first binding. Also
    carries the call-resolution context (the resolver, the document's
    own key, the stack of callers being hashed), unchanged as it walks
    one document."""

    def __init__(self, params: list, *, rename_params: bool = True,
                calls: "_Calls | None" = None, key: str | None = None, stack: tuple = ()):
        self.params = set(params)
        self.map: dict = ({p: f"_p{i}" for i, p in enumerate(params)}
                          if rename_params else {})
        self.locals = 0
        self.calls = calls
        self.key = key
        self.stack = stack

    def bind(self, node):
        if not isinstance(node, Name) or node.id in self.params:
            return node
        if node.id not in self.map:
            self.map[node.id] = f"_{self.locals}"
            self.locals += 1
        return Name(self.map[node.id])

    def use(self, node):
        if isinstance(node, Name) and node.id in self.map:
            return Name(self.map[node.id])
        return node


def _block(node, names):
    if isinstance(node, List):
        return List(tuple(_statement(s, names) for s in node.items))
    return node


def _statement(st, names: _Renamer):
    if not isinstance(st, Term):
        return st
    head, a = st.head, list(st.args)
    named = [(k, v) for k, v in st.named if k != "at"]
    if head == "statement::bind" and len(a) == 2:
        value = _expr(a[1], names)
        a = [names.bind(a[0]), value]
    elif head == "statement::bind_many" and len(a) == 2:
        values = List(tuple(_expr(v, names) for v in getattr(a[1], "items", ())))
        targets = List(tuple(names.bind(n) for n in getattr(a[0], "items", ())))
        a = [targets, values]
    elif head == "statement::update" and len(a) == 3:
        a = [names.use(a[0]), a[1], _expr(a[2], names)]
    elif head == "statement::define" and len(a) == 3:
        name = names.bind(a[0])
        params = List(tuple(names.bind(p) for p in getattr(a[1], "items", ())))
        a = [name, params, _expr(a[2], names)]
    elif head == "statement::branch" and len(a) == 3:
        a = [_expr(a[0], names), _block(a[1], names), _block(a[2], names)]
    elif head == "statement::loop::range" and len(a) == 5:
        start, stop = _expr(a[1], names), _expr(a[2], names)
        a = [names.bind(a[0]), start, stop, a[3], _block(a[4], names)]
    elif head == "statement::loop::each" and len(a) == 4:
        seq = _expr(a[1], names)
        item = names.bind(a[0])
        named = [(k, names.bind(v) if k == "index" else v) for k, v in named]
        a = [item, seq, a[2], _block(a[3], names)]
    elif head in ("statement::require", "statement::fail"):
        a = [_expr(x, names) if i < len(a) - 1 else _failure(x) for i, x in enumerate(a)]
    else:
        a = [_expr(x, names) for x in a]
    return Term(head, tuple(a), tuple(named))


def _failure(node):
    if isinstance(node, Term) and node.head.startswith("failure::"):
        return Term(node.head)
    return node


def _expr(node, names: _Renamer):
    if isinstance(node, Name):
        return names.use(node)
    if isinstance(node, Real):
        try:
            return _number(node.text)
        except (ValueError, OverflowError):
            return node
    if isinstance(node, List):
        return List(tuple(_expr(x, names) for x in node.items))
    if not isinstance(node, Term):
        return node
    if (node.head == "call::function" and names.calls is not None
            and node.args and isinstance(node.args[0], Str)):
        call_args = tuple(_expr(a, names) for a in node.args[1:])
        return names.calls.resolve(node.args[0].value, names.key, names.stack, call_args)
    args = tuple(_expr(x, names) for x in node.args)
    named = tuple((k, _expr(v, names)) for k, v in node.named)
    if node.head == "operator::unary::identity" and len(args) == 1:
        return args[0]
    if node.head == "operator::unary::negation" and len(args) == 1:
        inner = args[0]
        if isinstance(inner, Int):
            return Int(-inner.value)
        if isinstance(inner, Real):
            return _number(inner.text[1:] if inner.text.startswith("-") else "-" + inner.text)
    return Term(node.head, args, named)
