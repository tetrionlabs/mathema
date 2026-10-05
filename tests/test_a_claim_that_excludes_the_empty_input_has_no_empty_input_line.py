# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim whose binding or premise excludes the empty input says
nothing about f([]), so it gets no empty-input line and is never
falsified at xs = []. What f does at the empty list is still reported
by is_empty_safe as its own family."""
import pytest

from mathema import check
from mathema.conjecture import check_conjectures, claim


def pair_sum(xs: list) -> float:
    return xs[0] + xs[1]


@pytest.mark.parametrize("law", [
    "assuming len(xs) >= 2, for xs in [-1, 1]^n, abs(f(xs)) <= 2",
    "assuming n >= 2, for xs in R^n, f(xs) == xs[0] + xs[1]",
    "for xs in R^30, f(xs) == xs[0] + xs[1]",
])
def test_no_empty_input_line_when_the_claim_excludes_the_empty_list(law):
    rows = check(pair_sum, claims=[law]).probes
    names = [p.name for p in rows]
    assert not any(n.startswith("is_empty_safe") for n in names), names
    (main,) = [p for p in rows if not (p.meta or {}).get("mathema.companion_of")
               and p.name not in ("callable",)][:1]
    assert main.verdict in ("proven", "holds"), (main.verdict, main.counterexample)


def test_is_empty_safe_still_reports_the_empty_list_as_its_own_family():
    (p,) = check_conjectures(pair_sum, [claim("is_empty_safe(xs)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
