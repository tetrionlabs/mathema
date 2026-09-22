# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Shared text-scanning primitives used by both the claim grammar's
sugar expanders and the domain parser. Stdlib-only leaf.
"""
from __future__ import annotations


def _split_commas(s: str) -> list[str]:
    """Split on top-level commas only: a comma nested inside any
    bracket pair (`[]`, `()`, `{}`) stays inside its part."""
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in s:
        if ch in "[({":
            depth += 1
        elif ch in "])}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts
