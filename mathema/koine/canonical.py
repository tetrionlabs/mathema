# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The canonical form of a KOINE document, and `koine_hash` over it.

The canonical form keeps what a function computes and drops how it was
written and by whom:

- kept: `koine`, the `feature` lines (sorted), the `parameter` lines
  (names and kinds: the mathematical domain) and `body`;
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
- renamed: locals to `_0`, `_1`, ... in order of first binding.

The canonical spelling is the compact printing, one term per line.
`koine_hash` is `koine-<version>:` and the first sixteen hex digits of its
SHA-256. Pure functions; the document is never mutated.
"""
from __future__ import annotations

import hashlib

from .document import Document
from .vocabulary import KOINE_VERSION
from .syntax import Int, List, Name, Real, Term, compact_document

HASH_PREFIX = f"koine-{KOINE_VERSION}:"

_KEEP = ("koine", "feature", "parameter", "body")


def canonical_terms(doc: Document) -> tuple:
    """Intent:
        The document's terms in canonical form.
    """
    names = _Renamer(set(doc.parameter_names))
    kept = [t for t in doc.terms if isinstance(t, Term) and t.head in _KEEP]
    features = sorted((t for t in kept if t.head == "feature"),
                      key=lambda t: compact_document([t]))
    out = [t for t in kept if t.head == "koine"] + features
    out += [_parameter(t) for t in kept if t.head == "parameter"]
    for t in kept:
        if t.head == "body":
            out.append(Term("body", tuple(_statement(s, names) for s in t.args)))
    return tuple(out)


def canonical_text(doc: Document) -> str:
    """Intent:
        The canonical spelling: `compact` of each canonical term, one
        per line.
    """
    return compact_document(canonical_terms(doc))


def koine_hash(doc: Document) -> str:
    """Intent:
        `koine-<version>:<sha256[:16]>` over the canonical spelling.
    """
    return HASH_PREFIX + hashlib.sha256(canonical_text(doc).encode("utf-8")).hexdigest()[:16]


def _parameter(p: Term) -> Term:
    """A parameter line with only its name and kind; a record's fields
    likewise."""
    args = p.args[:2]
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
    def __init__(self, params: set):
        self.params = params
        self.map: dict = {}

    def bind(self, node):
        if not isinstance(node, Name) or node.id in self.params:
            return node
        if node.id not in self.map:
            self.map[node.id] = f"_{len(self.map)}"
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
