# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Shrinking a failing witness to a minimal one.

When a property-testing probe finds an input that triggers a failure,
the raw input is usually incidental (a long random unicode string), and
a minimal witness (the shortest, simplest input that still triggers it)
is far more useful to read and to fix against. `shrink` takes a failing
value and a `still_fails` predicate and returns a locally-minimal value
that still satisfies it, by delta-debugging: remove as much as possible,
then simplify what remains. Strings first; the same two-phase shape
extends to sequences.
"""
from __future__ import annotations

from typing import Callable

_SIMPLEST_CHARS = ("a", " ", "0")     # tried in order when simplifying


def shrink(value, still_fails: Callable[[object], bool],
           max_steps: int = 2000):
    """Intent:
        A locally-minimal value that still satisfies `still_fails` (True
        when the reduced value still triggers the failure), reached from
        `value` by removing and simplifying. `max_steps` caps the number
        of candidate evaluations so a pathological predicate cannot run
        unbounded. A non-string value is returned unchanged for now.
    Notes:
        `still_fails` must be deterministic on the value: it is called
        many times and the search assumes a stable answer. It should
        capture the SAME failure the original triggered (e.g. the same
        exception type), not merely any failure.
    """
    if isinstance(value, str):
        return _shrink_str(value, still_fails, max_steps)
    return value


def _shrink_str(s: str, still_fails, max_steps: int) -> str:
    steps = 0

    def fails(cand: str) -> bool:
        nonlocal steps
        steps += 1
        return still_fails(cand)

    changed = True
    while changed and steps < max_steps:
        changed = False
        # Phase 1: remove chunks, largest first (halving down to 1), so a
        # long witness collapses fast, then single characters.
        size = max(1, len(s) // 2)
        while size >= 1 and steps < max_steps:
            i = 0
            while i < len(s) and steps < max_steps:
                candidate = s[:i] + s[i + size:]
                if fails(candidate):
                    s = candidate
                    changed = True
                else:
                    i += size
            size //= 2
        # Phase 2: simplify each remaining character toward the plainest
        # one that still triggers the failure (unicode -> ascii -> a/space).
        for i in range(len(s)):
            if steps >= max_steps:
                break
            for simpler in _SIMPLEST_CHARS:
                if s[i] == simpler:
                    break
                candidate = s[:i] + simpler + s[i + 1:]
                if fails(candidate):
                    s = candidate
                    changed = True
                    break
    return s
