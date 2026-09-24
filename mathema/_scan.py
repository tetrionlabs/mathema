# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Shared text-scanning primitives used by both the claim grammar's
sugar expanders and the domain parser. Stdlib-only leaf.
"""
from __future__ import annotations

import re
from typing import Callable

_QUOTES = "'\""
# a quoted literal's placeholder: an identifier, so every rewrite that
# runs while it stands in for the literal treats it as one opaque name
_STRING_MARK = "_mathema_str_{}_"
_STRING_MARK_RE = re.compile(r"_mathema_str_(\d+)_")


def _string_end(s: str, start: int) -> int:
    """Intent:
        The index just past the quoted literal opening at `s[start]`: the
        matching unescaped quote of the same kind, or the end of `s` when
        the literal is never closed.
    """
    quote = s[start]
    i = start + 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == quote:
            return i + 1
        i += 1
    return len(s)


def _opens_string(s: str, i: int) -> bool:
    """Intent:
        Whether the quote at `s[i]` opens a string literal. A single
        quote straight after a name, a closing paren or another quote is
        the prime of derivative notation (`f'(x)`, `f''(x)`), not a
        string.
    """
    if s[i] == "'" and i > 0 and (s[i - 1].isalnum() or s[i - 1] in "_')"):
        return False
    return s[i] in _QUOTES


def mask_strings(s: str) -> tuple[str, list[str]]:
    """Intent:
        `s` with every quoted literal replaced by a numbered placeholder
        identifier, and the literals in placeholder order. Rewriting the
        masked text and then calling `unmask_strings` leaves the
        literals exactly as written: text inside quotes is data, and no
        grammar rewrite reaches it.
    """
    out: list[str] = []
    literals: list[str] = []
    i = 0
    while i < len(s):
        if _opens_string(s, i):
            end = _string_end(s, i)
            out.append(_STRING_MARK.format(len(literals)))
            literals.append(s[i:end])
            i = end
            continue
        out.append(s[i])
        i += 1
    return "".join(out), literals


def unmask_strings(s: str, literals: list[str]) -> str:
    """Intent:
        The inverse of `mask_strings`: every placeholder back to the
        literal it stands for.
    """
    if not literals:
        return s
    return _STRING_MARK_RE.sub(
        lambda m: literals[int(m.group(1))]
        if int(m.group(1)) < len(literals) else m.group(0), s)


def blank_strings(s: str) -> str:
    """Intent:
        `s` with every quoted literal emptied to `""`, for scanning claim
        syntax (names, bars, comment marks) without reading string values.
    """
    masked, literals = mask_strings(s)
    return unmask_strings(masked, ['""'] * len(literals))


def outside_strings(transform: Callable[[str], str], s: str) -> str:
    """Intent:
        `transform` applied to `s` with its quoted literals held out of
        reach, so a rewrite of claim syntax never edits a string value.
    """
    masked, literals = mask_strings(s)
    return unmask_strings(transform(masked), literals)


def sub_outside_strings(pattern, repl, s: str, count: int = 0) -> str:
    """Intent:
        `re.sub(pattern, repl, s)` that leaves quoted literals untouched.
    """
    return outside_strings(lambda t: re.sub(pattern, repl, t, count=count), s)


def _split_commas(s: str) -> list[str]:
    """Split on top-level commas only: a comma nested inside any
    bracket pair (`[]`, `()`, `{}`) or inside a quoted literal stays
    inside its part."""
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if _opens_string(s, i):
            end = _string_end(s, i)
            cur.append(s[i:end])
            i = end
            continue
        if ch in "[({":
            depth += 1
        elif ch in "])}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return parts
