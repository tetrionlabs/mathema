# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Gathering the siblings a document's calls reach.

The canonical form hashes a call to another function of the program by
what that function computes, which means it needs the callee's own
document. `call_function_locators` reads the keys a `call::function`
term names; `gather_siblings` follows them, and whatever they call in
turn, as far as `lift` resolves a locator to a document.
"""
from __future__ import annotations

from typing import Callable

from .document import Document
from .syntax import List, Term


def call_function_locators(doc: Document) -> set:
    """Intent:
        The key argument of every `call::function` term in `doc`'s
        body, however deep.
    """
    locators: set = set()

    def walk(node) -> None:
        if isinstance(node, Term):
            if node.head == "call::function" and node.args:
                locators.add(node.args[0].value)
            for a in node.args:
                walk(a)
            for _, v in node.named:
                walk(v)
        elif isinstance(node, List):
            for x in node.items:
                walk(x)

    for statement in doc.body:
        walk(statement)
    return locators


def gather_siblings(doc: Document, lift: Callable[[str], Document | None]) -> dict:
    """Intent:
        `{locator: Document}` for every function `doc`'s body calls by
        key, and every function those documents call in turn, as far
        as `lift` resolves a locator. `doc`'s own key is never a key of
        the result, whether or not it calls itself.

        `lift` takes one locator and returns its document, or anything
        that is not a `Document` (None, a decline) when the locator is
        not one of `doc`'s own siblings: another file, a library, a
        name it cannot resolve.
    """
    siblings: dict = {}
    seen = {doc.key}
    pending = call_function_locators(doc) - seen
    while pending:
        locator = pending.pop()
        seen.add(locator)
        found = lift(locator)
        if not isinstance(found, Document):
            continue
        siblings[locator] = found
        pending |= call_function_locators(found) - seen
    return siblings
