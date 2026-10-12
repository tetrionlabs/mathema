# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""KOINE text: the term model, the parser and the printers.

A KOINE document is a sequence of terms. A term is a `::` path applied
to positional and named arguments, `operator::binary::addition(a, 1)`,
or a bare path with no arguments, `constant::pi`. The atoms are names
(`x`, a reference to a parameter or a local), integers (`3`, `-3`),
reals written as decimals (`0.5`, `1e-07`), double-quoted strings with
JSON escapes, and `true`/`false`. A list is `[a, b]`. `#` starts a
comment that runs to the end of the line.

    document := term*
    term     := atom | list | path [ "(" [ arg ("," arg)* [","] ] ")" ]
    arg      := [ ident ":" ] term
    list     := "[" [ term ("," term)* [","] ] "]"
    path     := ident ( "::" ident )*
    atom     := integer | real | string | "true" | "false"
    ident    := [A-Za-z_][A-Za-z0-9_]*

A single identifier with no parentheses is a name; any path containing
`::`, or any identifier followed by parentheses, is a term. The model is
immutable, so documents can be hashed, shared and compared freely.

`compact` prints a node with no whitespace: the canonical bytes.
`pretty` prints it indented, one argument per line wherever the inline
form would pass the line width: the file form.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Union


@dataclass(frozen=True)
class Name:
    id: str


@dataclass(frozen=True)
class Int:
    value: int


@dataclass(frozen=True)
class Real:
    text: str


@dataclass(frozen=True)
class Str:
    value: str


@dataclass(frozen=True)
class Bool:
    value: bool


@dataclass(frozen=True)
class List:
    items: tuple = ()


@dataclass(frozen=True)
class Term:
    head: str
    args: tuple = ()
    named: tuple = field(default=())   # ((name, node), ...) in written order

    def get(self, name: str, default=None):
        for key, value in self.named:
            if key == name:
                return value
        return default

    def without(self, *names: str) -> "Term":
        return Term(self.head, self.args,
                    tuple((k, v) for k, v in self.named if k not in names))

    def replace(self, *, args=None, named=None) -> "Term":
        return Term(self.head, self.args if args is None else tuple(args),
                    self.named if named is None else tuple(named))


Node = Union[Name, Int, Real, Str, Bool, List, Term]
ATOMS = (Name, Int, Real, Str, Bool)
LITERALS = (Int, Real, Str, Bool)


class KoineSyntaxError(ValueError):
    """Text that is not KOINE; the message names the line and column."""

    def __init__(self, message: str, line: int, column: int):
        super().__init__(f"{line}:{column}: {message}")
        self.line, self.column = line, column


# --- tokens ----------------------------------------------------------

_TOKEN = re.compile(r"""
  (?P<skip>[ \t\r\n]+|\#[^\n]*)
| (?P<real>-?(?:0|[1-9][0-9]*)(?:\.[0-9]+(?:[eE][-+]?[0-9]+)?|[eE][-+]?[0-9]+))
| (?P<int>-?(?:0|[1-9][0-9]*))
| (?P<str>"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*")
| (?P<path>[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*)
| (?P<punct>[()\[\],:])
""", re.VERBOSE)


def _tokens(text: str):
    pos, line, line_start = 0, 1, 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise KoineSyntaxError(f"unexpected {text[pos]!r}", line, pos - line_start + 1)
        kind = m.lastgroup
        if kind in ("int", "real") and m.end() < len(text) \
                and (text[m.end()].isalnum() or text[m.end()] in "_."):
            raise KoineSyntaxError(f"malformed number {text[pos:m.end() + 1]!r}", line,
                                   pos - line_start + 1)
        if kind != "skip":
            yield kind, m.group(), line, pos - line_start + 1
        newlines = m.group().count("\n")
        if newlines:
            line += newlines
            line_start = m.start() + m.group().rfind("\n") + 1
        pos = m.end()
    yield "end", "", line, pos - line_start + 1


class _Parser:
    def __init__(self, text: str):
        self.tokens = list(_tokens(text))
        self.i = 0

    def peek(self):
        return self.tokens[self.i]

    def take(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect(self, value: str):
        kind, text, line, col = self.take()
        if text != value or kind not in ("punct",):
            raise KoineSyntaxError(f"expected {value!r}, found {text or 'end of input'!r}", line, col)

    def at(self, value: str) -> bool:
        kind, text, _, _ = self.peek()
        return kind == "punct" and text == value

    def node(self) -> Node:
        kind, text, line, col = self.take()
        if kind == "int":
            return Int(int(text))
        if kind == "real":
            return Real(text)
        if kind == "str":
            return Str(json.loads(text))
        if kind == "punct" and text == "[":
            return List(tuple(self.sequence("]")))
        if kind == "path":
            if text in ("true", "false") and not self.at("("):
                return Bool(text == "true")
            if self.at("("):
                self.take()
                args, named = self.arguments()
                return Term(text, tuple(args), tuple(named))
            if "::" in text:
                return Term(text)
            return Name(text)
        raise KoineSyntaxError(f"expected a term, found {text or 'end of input'!r}", line, col)

    def sequence(self, close: str) -> list:
        items = []
        while not self.at(close):
            items.append(self.node())
            if not self.at(","):
                break
            self.take()
        self.expect(close)
        return items

    def arguments(self):
        args, named, seen = [], [], set()
        while not self.at(")"):
            kind, text, line, col = self.peek()
            nxt = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else None
            if kind == "path" and "::" not in text and nxt and nxt[0] == "punct" and nxt[1] == ":":
                self.take()
                self.take()
                if text in seen:
                    raise KoineSyntaxError(f"argument {text!r} given twice", line, col)
                seen.add(text)
                named.append((text, self.node()))
            else:
                if named:
                    raise KoineSyntaxError("a positional argument after a named one", line, col)
                args.append(self.node())
            if not self.at(","):
                break
            self.take()
        self.expect(")")
        return args, named


def parse(text: str) -> tuple:
    """Intent:
        The terms of a KOINE document, in order.

    Raises:
        KoineSyntaxError: the text is not KOINE.
    """
    p = _Parser(text)
    out = []
    while p.peek()[0] != "end":
        out.append(p.node())
    return tuple(out)


def parse_node(text: str) -> Node:
    """Intent:
        Exactly one term from `text`.

    Raises:
        KoineSyntaxError: the text is not exactly one KOINE term.
    """
    nodes = parse(text)
    if len(nodes) != 1:
        raise KoineSyntaxError(f"expected one term, found {len(nodes)}", 1, 1)
    return nodes[0]


# --- printers --------------------------------------------------------

def _atom(node) -> str:
    if isinstance(node, Name):
        return node.id
    if isinstance(node, Int):
        return str(node.value)
    if isinstance(node, Real):
        return node.text
    if isinstance(node, Str):
        return json.dumps(node.value, ensure_ascii=False)
    if isinstance(node, Bool):
        return "true" if node.value else "false"
    raise TypeError(f"not a KOINE node: {node!r}")


def _needs_parens(term: Term) -> bool:
    return bool(term.args or term.named) or "::" not in term.head


def compact(node) -> str:
    """Intent:
        `node` with no whitespace at all: the canonical spelling.
    """
    if isinstance(node, Term):
        if not _needs_parens(node):
            return node.head
        parts = [compact(a) for a in node.args]
        parts += [f"{k}:{compact(v)}" for k, v in node.named]
        return f"{node.head}({','.join(parts)})"
    if isinstance(node, List):
        return "[" + ",".join(compact(x) for x in node.items) + "]"
    return _atom(node)


def inline(node) -> str:
    """Intent:
        `node` on one line with a space after each separator.
    """
    if isinstance(node, Term):
        if not _needs_parens(node):
            return node.head
        parts = [inline(a) for a in node.args]
        parts += [f"{k}: {inline(v)}" for k, v in node.named]
        return f"{node.head}({', '.join(parts)})"
    if isinstance(node, List):
        return "[" + ", ".join(inline(x) for x in node.items) + "]"
    return _atom(node)


def pretty(node, indent: int = 0, width: int = 88) -> str:
    """Intent:
        `node` inline when it fits in `width` from `indent`, otherwise
        broken one argument per line, each indented two spaces further,
        with a trailing comma.
    """
    flat = inline(node)
    if indent + len(flat) <= width or not isinstance(node, (Term, List)):
        return flat
    pad = " " * (indent + 2)
    if isinstance(node, List):
        if not node.items:
            return "[]"
        lines = [pad + pretty(x, indent + 2, width) + "," for x in node.items]
        return "[\n" + "\n".join(lines) + "\n" + " " * indent + "]"
    lines = [pad + pretty(a, indent + 2, width) + "," for a in node.args]
    for k, v in node.named:
        lines.append(f"{pad}{k}: {pretty(v, indent + 2 + len(k) + 2, width)},")
    return node.head + "(\n" + "\n".join(lines) + "\n" + " " * indent + ")"


def format_document(terms, width: int = 88) -> str:
    """Intent:
        The file form of a document: one pretty-printed top-level term
        per line group, ending in a newline.
    """
    return "".join(pretty(t, 0, width) + "\n" for t in terms)


def compact_document(terms) -> str:
    """Intent:
        The canonical spelling of a document: its terms compact, one
        per line.
    """
    return "\n".join(compact(t) for t in terms)
