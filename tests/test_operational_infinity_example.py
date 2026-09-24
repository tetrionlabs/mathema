# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The operational-infinity example in docs/grammar.md, run as written:
the integral of the normal density over the whole line is proven, the
unbounded pointwise claim is falsified where `x ** 2` overflows, and the
same claim under `let |inf| be 1e100` is proven over the stated region."""
import math
import re

import mathema


def gauss(x: float) -> float:
    """The standard normal density."""
    return math.exp(-x ** 2 / 2) / math.sqrt(2 * math.pi)


def _shown_rows():
    with open("docs/grammar.md") as fh:
        page = fh.read()
    block = page.split("### Operational infinity", 1)[1].split("```text\n", 1)[1]
    return block.split("```", 1)[0].strip().splitlines()


def test_the_page_shows_exactly_what_the_example_prints():
    rows = []
    for law in ["∫(f(x), x, -oo, oo) == 1",
                "f(x) >= 0",
                "let |inf| be 1e100, f(x) >= 0"]:
        (p,) = mathema.claims.check(gauss, [law])
        rows.append(f"{law:31} {p.verdict:9} "
                    f"{p.counterexample or p.condition or ''}".rstrip())
    assert rows == _shown_rows()


def test_the_overflow_witness_really_raises():
    (p,) = mathema.claims.check(gauss, ["f(x) >= 0"])
    x = float(re.search(r"x = (\S+)", p.counterexample).group(1))
    try:
        gauss(x)
    except OverflowError:
        return
    raise AssertionError(f"gauss({x}) returned without raising")


def test_the_half_line_spelling_stops_oo_at_the_operational_bound():
    (p,) = mathema.claims.check(gauss, ["let |inf| be 1e12, for x in [0, oo], f(x) >= 0"])
    assert p.verdict == "proven", (p.verdict, p.note)
    hi = float(re.search(r", ([^\]]+)\]", p.condition).group(1))
    assert hi == 1e12, p.condition
