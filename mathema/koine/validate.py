# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Validation of a KOINE document.

`validate(document)` returns every problem, each `where: what`, with
`where` a path such as `body[2].arg[1]`; an empty list means valid.
Signatures come from `vocabulary`, so every term is checked the same
way: its head is known, its positional and named arguments have the
right count and sort. On top of that the body is walked with a scope:
a name is used only after it is bound, a parameter is never assigned,
nothing follows a `return` or `fail`, a loop body never refuses or
returns, a sequence operand names a sequence parameter, a local
function is called with its own arity, and a term that needs a
feature appears only in a document announcing it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import vocabulary as V
from .document import Document
from .syntax import LITERALS, Bool, Int, List, Name, Real, Str, Term


@dataclass
class _Scope:
    params: dict                       # name -> kind head
    features: frozenset
    locals: set = field(default_factory=set)
    funcs: dict = field(default_factory=dict)

    def bound(self, name: str) -> bool:
        return name in self.params or name in self.locals

    def child(self) -> "_Scope":
        return _Scope(self.params, self.features, set(self.locals), dict(self.funcs))


def validate(doc) -> list[str]:
    """Intent:
        Every way `doc` (a `Document`) fails KOINE, as `where: what`
        strings; empty when valid.
    """
    if not isinstance(doc, Document):
        return ["document: not a KOINE document"]
    out: list[str] = []
    params = _envelope(doc, out)
    scope = _Scope(params, doc.features)
    _block(doc.body, "body", scope, out, in_loop=False)
    return out


# --- generic signature check ---------------------------------------------

def _arguments(term: Term, sig: V.Signature, where: str, out: list, check) -> None:
    n = len(term.args)
    most = len(sig.positional) if sig.rest is None else None
    if n < sig.min_positional or (most is not None and n > most):
        want = str(sig.min_positional) if most == sig.min_positional else \
            f"{sig.min_positional} to {most}" if most is not None else \
            f"at least {sig.min_positional}"
        out.append(f"{where}: {term.head} takes {want} positional argument(s), got {n}")
    if sig.rest is not None and n - len(sig.positional) < sig.rest_min:
        out.append(f"{where}: {term.head} takes at least "
                   f"{len(sig.positional) + sig.rest_min} argument(s), got {n}")
    for i, arg in enumerate(term.args):
        sort = sig.positional[i] if i < len(sig.positional) else sig.rest
        if sort is not None:
            check(arg, sort, f"{where}.arg[{i}]")
    given = {k for k, _ in term.named}
    for name, (sort, required) in sig.named.items():
        if required and name not in given:
            out.append(f"{where}: {term.head} requires {name}:")
    for name, value in term.named:
        if name in sig.named:
            check(value, sig.named[name][0], f"{where}.{name}")
        elif sig.any_named is not None:
            check(value, sig.any_named, f"{where}.{name}")
        else:
            out.append(f"{where}: {term.head} takes no argument named {name}")


def _nullary(node, heads, where: str, what: str, out: list) -> None:
    if not (isinstance(node, Term) and node.head in heads and not node.args and not node.named):
        out.append(f"{where}: expected {what}, got {_show(node)}")


def _show(node) -> str:
    from .syntax import inline
    text = inline(node)
    return text if len(text) <= 60 else text[:57] + "..."


def _plain_check(out: list):
    """The sort checks that need no scope."""
    def check(node, sort: str, where: str) -> None:
        if sort == V.STR:
            if not isinstance(node, Str):
                out.append(f"{where}: expected a string, got {_show(node)}")
        elif sort == V.INT:
            if not isinstance(node, Int):
                out.append(f"{where}: expected an integer, got {_show(node)}")
        elif sort == V.POSINT:
            if not (isinstance(node, Int) and node.value > 0):
                out.append(f"{where}: expected a positive integer, got {_show(node)}")
        elif sort == V.START:
            if not (isinstance(node, Int) and node.value in (0, 1)):
                out.append(f"{where}: expected 0 or 1, got {_show(node)}")
        elif sort == V.BOOL:
            if not isinstance(node, Bool):
                out.append(f"{where}: expected true or false, got {_show(node)}")
        elif sort == V.NAME:
            if not isinstance(node, Name):
                out.append(f"{where}: expected a name, got {_show(node)}")
        elif sort == V.KIND:
            _nullary(node, V.KINDS, where, "a kind::", out)
        elif sort == V.REPR:
            _nullary(node, V.REPRS, where, "a representation::", out)
        elif sort == V.NONVALUE:
            _nullary(node, V.NONVALUES, where, "a nonvalue::", out)
        elif sort == V.UPDATE_OP:
            _nullary(node, V.UPDATE_OPS, where, "an update operator", out)
        elif sort == V.OPERATION:
            _nullary(node, V.OPERATIONS, where, "an operator:: or function::", out)
        elif sort == V.FEATURE:
            if not (isinstance(node, Name) and node.id in V.KNOWN_FEATURES):
                out.append(f"{where}: unknown feature {_show(node)}")
        elif sort == V.LITERAL:
            if not isinstance(node, LITERALS):
                out.append(f"{where}: expected a literal, got {_show(node)}")
        elif sort == V.AS:
            if not (isinstance(node, Term) and node.head in V.MANIFESTATIONS):
                out.append(f"{where}: expected an as::, got {_show(node)}")
            else:
                _arguments(node, V.MANIFESTATIONS[node.head], where, out, check)
        elif sort == V.SPAN:
            if not (isinstance(node, Term) and node.head == V.SPAN_HEAD):
                out.append(f"{where}: expected span(line, end_line, text), got {_show(node)}")
            else:
                _arguments(node, V.SPAN_SIG, where, out, check)
        elif sort == V.FAILURE:
            if not (isinstance(node, Term) and node.head in V.FAILURES):
                out.append(f"{where}: expected a failure::, got {_show(node)}")
            else:
                _arguments(node, V.FAILURES[node.head], where, out, check)
                if isinstance(node.args[0] if node.args else None, Str) and not node.args[0].value:
                    out.append(f"{where}.arg[0]: the failure type is empty")
        elif sort == V.FIELDS:
            if not isinstance(node, List) or not node.items:
                out.append(f"{where}: expected a non-empty list of field(...)")
            else:
                for i, f in enumerate(node.items):
                    if not (isinstance(f, Term) and f.head == V.FIELD):
                        out.append(f"{where}[{i}]: expected field(name, kind, representation)")
                    else:
                        _arguments(f, V.FIELD_SIG, f"{where}[{i}]", out, check)
        else:
            out.append(f"{where}: {sort} is not allowed here")
    return check


# --- envelope ----------------------------------------------------------------

def _envelope(doc: Document, out: list) -> dict:
    check = _plain_check(out)
    counts: dict = {}
    for i, t in enumerate(doc.terms):
        where = f"[{i}]"
        if not isinstance(t, Term) or t.head not in V.ENVELOPE:
            out.append(f"{where}: {_show(t)} is not a document term")
            continue
        counts[t.head] = counts.get(t.head, 0) + 1
        if t.head != "body":
            _arguments(t, V.ENVELOPE[t.head], t.head, out, check)
    for head in V.REQUIRED:
        if head not in counts:
            out.append(f"document: {head}(...) is missing")
    for head in V.SINGLE:
        if counts.get(head, 0) > 1:
            out.append(f"document: {head}(...) appears {counts[head]} times")
    version = doc.first("koine")
    if version is not None and version.args and version.args[0] != Str(V.KOINE_VERSION):
        out.append(f"koine: this is KOINE {V.KOINE_VERSION}, the document says {_show(version.args[0])}")
    lang = doc.language
    if lang is not None and not (lang.isalnum() and lang[:1].isalpha() and lang == lang.lower()):
        out.append(f"lifter: {lang!r} is not a language tag")
    sha = doc._named("source", "sha256")
    if sha is not None and not (len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)):
        out.append("source: sha256 must be 64 lowercase hex digits")
    params: dict = {}
    for p in doc.parameters:
        if not p.args or not isinstance(p.args[0], Name):
            continue
        name = p.args[0].id
        if name in params:
            out.append(f"parameter: {name} is declared twice")
        kind = p.args[1].head if len(p.args) > 1 and isinstance(p.args[1], Term) else "kind::unknown"
        params[name] = kind
        if kind == "kind::record" and p.get("fields") is None:
            out.append(f"parameter: record {name} names no fields")
    seen = set()
    for m in doc.all("manifest"):
        if m.args and isinstance(m.args[0], Term):
            op = m.get("operation")
            key = (m.args[0].head, op.head if isinstance(op, Term) else None)
            if key in seen:
                what = key[0] + (f" for {key[1]}" if key[1] else "")
                out.append(f"manifest: {what} is given twice")
            seen.add(key)
    return params


# --- body ------------------------------------------------------------------

def _block(stmts, where: str, scope: _Scope, out: list, in_loop: bool) -> None:
    ended = False
    for i, st in enumerate(stmts):
        w = f"{where}[{i}]"
        if ended:
            out.append(f"{w}: nothing may follow a return or a fail")
            return
        head = _statement(st, w, scope, out, in_loop)
        ended = head in V.TERMINAL


def _statement(st, where: str, scope: _Scope, out: list, in_loop: bool) -> str | None:
    if not (isinstance(st, Term) and st.head in V.STATEMENTS):
        out.append(f"{where}: {_show(st)} is not a statement")
        return None
    head = st.head
    sig = V.STATEMENTS[head]
    before = len(out)
    plain = _plain_check(out)

    def check(node, sort, w):
        if sort == V.EXPR:
            # a local function's body is checked in its own scope below
            if not (head == "statement::define" and w == f"{where}.arg[2]"):
                _expr(node, w, scope, out)
        elif sort in (V.NAME, V.NAMES, V.BLOCK, V.EXPRS, V.SEQ):
            pass
        else:
            plain(node, sort, w)

    _arguments(st, sig, where, out, check)
    if len(out) > before and len(st.args) < sig.min_positional:
        return head
    if in_loop and head in V.NOT_IN_LOOPS:
        out.append(f"{where}: {head} is not allowed inside a loop")
    a = st.args

    if head == "statement::bind":
        if _target(a[0], f"{where}.arg[0]", scope, out):
            scope.locals.add(a[0].id)
    elif head == "statement::bind_many":
        names, values = a[0], a[1]
        if not isinstance(names, List) or not isinstance(values, List):
            out.append(f"{where}: bind_many takes a list of names and a list of expressions")
            return head
        if len(names.items) != len(values.items) or not names.items:
            out.append(f"{where}: names and values must pair one to one")
        ids = [n.id for n in names.items if isinstance(n, Name)]
        if len(set(ids)) != len(names.items):
            out.append(f"{where}.arg[0]: the names must be distinct names")
        for j, v in enumerate(values.items):
            _expr(v, f"{where}.arg[1][{j}]", scope, out)
        for j, n in enumerate(names.items):
            if _target(n, f"{where}.arg[0][{j}]", scope, out):
                scope.locals.add(n.id)
    elif head == "statement::update":
        t = a[0]
        if not (isinstance(t, Name) and t.id in scope.locals):
            out.append(f"{where}.arg[0]: must name a local bound earlier")
    elif head == "statement::define":
        name, params = a[0], a[1]
        ok_params = isinstance(params, List) and all(isinstance(p, Name) for p in params.items) \
            and len({p.id for p in params.items}) == len(params.items)
        if not ok_params:
            out.append(f"{where}.arg[1]: the parameters must be distinct names")
        if not isinstance(name, Name) or scope.bound(name.id) or name.id in scope.funcs:
            out.append(f"{where}.arg[0]: a fresh name")
        inner = scope.child()
        if ok_params:
            inner.locals |= {p.id for p in params.items}
        _expr(a[2], f"{where}.arg[2]", inner, out)
        if isinstance(name, Name) and ok_params:
            scope.funcs[name.id] = len(params.items)
    elif head == "statement::branch":
        then_scope, else_scope = scope.child(), scope.child()
        _list_block(a[1], f"{where}.arg[1]", then_scope, out, in_loop)
        _list_block(a[2], f"{where}.arg[2]", else_scope, out, in_loop)
        scope.locals |= then_scope.locals & else_scope.locals
    elif head == "statement::loop::range":
        inner = scope.child()
        if _target(a[0], f"{where}.arg[0]", scope, out):
            inner.locals.add(a[0].id)
        _list_block(a[4], f"{where}.arg[4]", inner, out, True)
    elif head == "statement::loop::each":
        _sequence(a[1], f"{where}.arg[1]", scope, out)
        inner = scope.child()
        if _target(a[0], f"{where}.arg[0]", scope, out):
            inner.locals.add(a[0].id)
        idx = st.get("index")
        if idx is not None and _target(idx, f"{where}.index", scope, out):
            inner.locals.add(idx.id)
        _list_block(a[3], f"{where}.arg[3]", inner, out, True)
    return head


def _list_block(node, where: str, scope: _Scope, out: list, in_loop: bool) -> None:
    if not isinstance(node, List):
        out.append(f"{where}: expected a block [statement, ...]")
        return
    _block(node.items, where, scope, out, in_loop)


def _target(node, where: str, scope: _Scope, out: list) -> bool:
    if not isinstance(node, Name):
        out.append(f"{where}: expected a name")
        return False
    if node.id in scope.params:
        out.append(f"{where}: parameter {node.id} may not be assigned")
        return False
    if node.id in scope.funcs:
        out.append(f"{where}: {node.id} names a local function")
        return False
    return True


def _sequence(node, where: str, scope: _Scope, out: list) -> None:
    if isinstance(node, Name):
        if scope.params.get(node.id) not in V.SEQUENCE_KINDS:
            out.append(f"{where}: {node.id} is not a sequence parameter")
    elif isinstance(node, Term) and node.head == "value::field":
        _expr(node, where, scope, out)
    else:
        out.append(f"{where}: expected a sequence parameter or a value::field")


def _expr(node, where: str, scope: _Scope, out: list) -> None:
    if isinstance(node, Name):
        if not scope.bound(node.id):
            out.append(f"{where}: {node.id} is not bound here")
        return
    if isinstance(node, Real):
        try:
            if not math.isfinite(float(node.text)):
                out.append(f"{where}: {node.text} is not a finite real")
        except ValueError:
            out.append(f"{where}: {node.text} is not a real")
        return
    if isinstance(node, (Int, Str, Bool)):
        return
    if not (isinstance(node, Term) and node.head in V.EXPRESSIONS):
        out.append(f"{where}: {_show(node)} is not an expression")
        return
    sig = V.EXPRESSIONS[node.head]
    if sig.feature and sig.feature not in scope.features:
        out.append(f"{where}: {node.head} needs feature({sig.feature})")
    plain = _plain_check(out)

    def check(arg, sort, w):
        if sort == V.EXPR:
            _expr(arg, w, scope, out)
        elif sort == V.SEQ:
            _sequence(arg, w, scope, out)
        elif sort == V.LITERALS:
            if not isinstance(arg, List) or not arg.items:
                out.append(f"{w}: expected a non-empty list of literals")
            else:
                for j, m in enumerate(arg.items):
                    if not isinstance(m, LITERALS):
                        out.append(f"{w}[{j}]: expected a literal, got {_show(m)}")
        else:
            plain(arg, sort, w)

    _arguments(node, sig, where, out, check)
    head = node.head
    if head == "value::field":
        base = node.args[0] if node.args else None
        if not (isinstance(base, Name) and scope.params.get(base.id) == "kind::record"):
            out.append(f"{where}.arg[0]: must name a record parameter")
    elif head == "call::local":
        name = node.args[0] if node.args else None
        arity = scope.funcs.get(name.id) if isinstance(name, Name) else None
        if arity is None:
            out.append(f"{where}.arg[0]: {_show(name)} is not a local function bound here")
        elif len(node.args) - 1 != arity:
            out.append(f"{where}: {name.id} takes {arity} argument(s), got {len(node.args) - 1}")
    elif head in ("call::function", "call::library"):
        key = node.args[0] if node.args else None
        if isinstance(key, Str) and not key.value:
            out.append(f"{where}.arg[0]: the key is empty")
