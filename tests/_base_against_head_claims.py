# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Thirty ordinary claims of varied shapes, over small functions, whose
verdict, route, canonical text and fingerprint a change to the claim
language must leave as they were: intervals, integer ranges, finite
sets of numbers and texts, `let` bindings, premises, chains,
`raises`, membership, a tolerance, and named functions.

`rows()` adjudicates them with whichever mathema is first on the path,
so the same module run against an earlier tree and against this one
gives the two tables to compare. Run as a script it prints the table
as JSON."""
from __future__ import annotations

import json
import math


def square(x: float) -> float:
    """`x` times itself."""
    return x * x


def cube(x: float) -> float:
    """`x` to the third power."""
    return x * x * x


def absolute(x: float) -> float:
    """The magnitude of `x`."""
    return x if x >= 0 else -x


def mean(a: float, b: float) -> float:
    """The midpoint of `a` and `b`."""
    return (a + b) / 2


def clip(x: float, lo: float, hi: float) -> float:
    """`x` held to the interval from `lo` to `hi`."""
    return min(max(x, lo), hi)


def count_up(n: int) -> int:
    """The sum of the whole numbers up to `n`."""
    return n * (n + 1) // 2


def parity(n: int) -> int:
    """0 for an even `n`, 1 for an odd one."""
    return n % 2


def reciprocal(x: float) -> float:
    """One over `x`, refused at zero."""
    if x == 0:
        raise ValueError("x")
    return 1 / x


def root(x: float) -> float:
    """The square root of `x`."""
    return math.sqrt(x)


def shout(word: str) -> str:
    """The word in capitals."""
    return word.upper()


def grade(score: int) -> str:
    """`pass` at 50 or more, else `fail`."""
    return "pass" if score >= 50 else "fail"


def shifted(x: float, c: float) -> float:
    """`x` moved by `c`."""
    return x + c


#: (function name, claim text)
CLAIMS = [
    ("square", "for x in [-10, 10], square(x) >= 0"),
    ("square", "for x in [-10, 10], f(-x) == f(x)"),
    ("square", "for x in [0, 3], f(x) <= 8"),
    ("cube", "for x in [-5, 5], f(-x) == -f(x)"),
    ("cube", "for x in [0, 2], 0 <= f(x) <= 8"),
    ("absolute", "for x in [-100, 100], f(x) >= 0"),
    ("absolute", "for x in [-3, 3], f(x) == x"),
    ("mean", "for a in [0, 1], b in [0, 1], f(a, b) <= max(a, b)"),
    ("mean", "for a in [0, 1], b in [0, 1], f(a, b) == f(b, a)"),
    ("clip", "for x in [-10, 10], lo in [0, 1], hi in [2, 3], lo <= f(x, lo, hi) <= hi"),
    ("clip", "for x in [-10, 10], f(x, 0, 1) <= 1"),
    ("count_up", "for n in [0, 20] subset Z, f(n) >= n"),
    ("count_up", "for n in [0, 5] subset Z, f(n) == n * (n + 1) / 2"),
    ("count_up", "for n in [1, 5] subset Z, f(n) <= 10"),
    ("parity", "for n in {0, 2, 4, 6}, f(n) == 0"),
    ("parity", "for n in {1, 2, 3}, f(n) == 1"),
    ("reciprocal", "raises(f(0), ValueError)"),
    ("reciprocal", "for x in [1, 10], f(x) <= 1"),
    ("reciprocal", "for x in [1, 10], f(x) > 0"),
    ("root", "for x in [0, 100], f(x) >= 0"),
    ("root", "for x in [0, 100], f(x) ~= x ** 0.5"),
    ("root", "for x in [0, 1], f(x) in [0, 1]"),
    ("shout", 'for word in {"a", "bc"}, f(word) != ""'),
    ("shout", 'for word in {"a", "bc"}, f(word) == word'),
    ("grade", "for score in [50, 100] subset Z, f(score) == \"pass\""),
    ("grade", "for score in {0, 49, 50}, f(score) == \"pass\""),
    ("shifted", "let c be 2.0, for x in [0, 1], f(x, c) >= 2"),
    ("shifted", "assuming c > 0, for x in [0, 1], c in [-1, 1], f(x, c) > x"),
    ("square", "let g = tests._base_against_head_claims.cube, for x in [0, 1], f(x) >= g(x)"),
    ("mean", "for a in [0, 1], f(a, a) == a"),
]


def rows() -> list:
    """Each claim's name, verdict, route, canonical text and
    fingerprint, adjudicated by the mathema first on the path."""
    from mathema.conjecture import check_conjectures, claim
    from mathema.spec import canonical_claim_text, claims_fingerprint
    out = []
    for i, (name, text) in enumerate(CLAIMS):
        fn = globals()[name]
        written = claim(text, name=f"c{i}")
        (row,) = [r for r in check_conjectures(fn, [written]) if r.name == written.name]
        out.append({"index": i, "function": name, "claim": text,
                    "verdict": row.verdict, "route": row.route,
                    "statement": canonical_claim_text(claim(text, name=f"c{i}")),
                    "fingerprint": claims_fingerprint([{"name": f"c{i}", "statement": text}])})
    return out


def lexicon_texts() -> list:
    """Each lexicon row's key, canonical text and fingerprint."""
    from mathema.conjecture import claim
    from mathema.lexicon import LEXICON
    from mathema.spec import canonical_claim_text, claims_fingerprint
    out = []
    for key, text in sorted(LEXICON.items()):
        try:
            canonical = canonical_claim_text(claim(text, name=key))
        except Exception as e:
            canonical = f"refused: {type(e).__name__}"
        try:
            fp = claims_fingerprint([{"name": key, "statement": text}])
        except Exception as e:
            fp = f"refused: {type(e).__name__}"
        out.append({"key": key, "statement": canonical, "fingerprint": fp})
    return out


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "rows"
    print(json.dumps(rows() if which == "rows" else lexicon_texts(), indent=1))
