# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""KOINE: the Kernel Of Interoperable Numerical Expressions.

The engine's internal representation of a function body. `.koi` files
hold its text (`syntax`), a `Document` its parsed form; `vocabulary` is
the closed set of terms, `validate` checks a document against it,
`canonical` gives the bytes `koine_hash` is taken over (`nominal_hash`
keeps the parameter names and every call's locator), `siblings`
gathers the documents a sibling-aware hash needs, `interpret` is its
meaning at a point, and `facts_from_koine` reads a document into the
`Facts` the engine derives from.
"""
from __future__ import annotations

from .canonical import (
    canonical_text,
    koine_hash,
    nominal_hash,
    nominal_text,
    unresolved_calls,
)
from .document import Document
from .facts import KoineDeclined, facts_from_koine
from .interpret import interpret
from .siblings import gather_siblings
from .syntax import KoineSyntaxError, format_document, parse
from .validate import validate
from .vocabulary import KOINE_VERSION

FILE_EXTENSION = ".koi"

__all__ = ["FILE_EXTENSION", "KOINE_VERSION", "Document", "KoineDeclined",
           "KoineSyntaxError", "canonical_text", "facts_from_koine",
           "format_document", "gather_siblings", "interpret", "koine_hash",
           "nominal_hash", "nominal_text", "parse", "unresolved_calls", "validate"]
