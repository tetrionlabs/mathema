# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""KOINE: the Kernel Of Interoperable Numerical Expressions.

The engine's internal representation of a function body. `.koi` files
hold its text (`syntax`), a `Document` its parsed form; `vocabulary` is
the closed set of terms, `validate` checks a document against it, and
`canonical` gives the bytes `koine_hash` is taken over.
"""
from __future__ import annotations

from .canonical import canonical_text, koine_hash
from .document import Document
from .syntax import KoineSyntaxError, format_document, parse
from .validate import validate
from .vocabulary import KOINE_VERSION

FILE_EXTENSION = ".koi"

__all__ = ["FILE_EXTENSION", "KOINE_VERSION", "Document", "KoineSyntaxError",
           "canonical_text", "format_document", "koine_hash", "parse", "validate"]
