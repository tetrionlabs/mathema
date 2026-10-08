# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `len` refinement for core's own tests, built from the
`RefinedLanguage` kit the way the mathema-language package builds its
own: the measure is `len`, the plain member of length `n` repeats one
simple character the base admits, and a built member cuts a run of
base members to length `n`. mathema registers no refinement key; the
suite registers this one so its `L[..., len <= n]` claims resolve."""
from mathema.languages import RefinedLanguage


def _plain(base):
    def plain(n):
        for ch in ("a", "0", "x", "A", " "):
            if base.contains(ch * n):
                return ch * n
        return None
    return plain


def _build(base):
    def build(rng, n):
        for _ in range(100):
            s = base.sample(rng)
            if isinstance(s, str) and len(s) == n:
                return s
        for _ in range(100):
            run = ""
            while len(run) < n:
                piece = base.sample(rng)
                if not isinstance(piece, str):
                    return None
                run += piece or "a"
            if base.contains(run[:n]):
                return run[:n]
        return None
    return build


def length(language, interval):
    """The members of `language` whose length in code points lies in
    `interval`."""
    from mathema.domain import refinement_range
    lo, hi = refinement_range(interval)
    schema = {"minLength": lo, **({"maxLength": hi} if hi is not None else {})}
    return RefinedLanguage(language, "len", interval, measure=len,
                           plain=_plain(language), build=_build(language),
                           schema=schema, hazard_kind="length")
