# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A KOINE document: its terms, and the envelope read off them.

The envelope is the top-level terms other than `body`: the version,
features, who lifted it and from where, the function's name and key,
its parameters and return, how its runtime shows each non-value, and
the lifter's own structural counts.
"""
from __future__ import annotations

from dataclasses import dataclass

from .syntax import Name, Term, format_document, parse


@dataclass(frozen=True)
class Document:
    terms: tuple

    @classmethod
    def parse(cls, text: str) -> "Document":
        """Intent:
            The document `text` spells.

        Raises:
            KoineSyntaxError: the text is not KOINE.
        """
        return cls(parse(text))

    def text(self) -> str:
        return format_document(self.terms)

    def first(self, head: str) -> Term | None:
        return next((t for t in self.terms if isinstance(t, Term) and t.head == head), None)

    def all(self, head: str) -> list:
        return [t for t in self.terms if isinstance(t, Term) and t.head == head]

    @property
    def body(self) -> tuple:
        b = self.first("body")
        return b.args if b is not None else ()

    def with_body(self, statements) -> "Document":
        return Document(tuple(Term("body", tuple(statements)) if isinstance(t, Term)
                              and t.head == "body" else t for t in self.terms))

    @property
    def parameters(self) -> list:
        return self.all("parameter")

    @property
    def parameter_names(self) -> list:
        return [p.args[0].id for p in self.parameters
                if p.args and isinstance(p.args[0], Name)]

    def parameter_kind(self, name: str) -> str | None:
        for p in self.parameters:
            if p.args and isinstance(p.args[0], Name) and p.args[0].id == name:
                kind = p.args[1] if len(p.args) > 1 else None
                return kind.head if isinstance(kind, Term) else None
        return None

    @property
    def features(self) -> frozenset:
        return frozenset(t.args[0].id for t in self.all("feature")
                         if t.args and isinstance(t.args[0], Name))

    @property
    def manifestations(self) -> dict:
        """`{(non-value class, operation or None): as term}` for every
        `manifest` line."""
        out = {}
        for m in self.all("manifest"):
            if len(m.args) == 2 and isinstance(m.args[0], Term) and isinstance(m.args[1], Term):
                op = m.get("operation")
                out[(m.args[0].head, op.head if isinstance(op, Term) else None)] = m.args[1]
        return out

    def manifestation(self, cls: str, operation: str | None = None) -> Term | None:
        """The `as::` term for a non-value of `cls` raised by `operation`:
        the line naming that operation, else the line for the class."""
        table = self.manifestations
        return table.get((cls, operation)) or table.get((cls, None))

    def _named(self, head: str, key: str):
        t = self.first(head)
        v = t.get(key) if t is not None else None
        return getattr(v, "value", None)

    @property
    def key(self) -> str | None:
        return self._named("function", "key")

    @property
    def name(self) -> str | None:
        return self._named("function", "name")

    @property
    def language(self) -> str | None:
        return self._named("lifter", "language")
