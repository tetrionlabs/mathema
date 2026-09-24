# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A premise that no point of the declared domain satisfies leaves the
claim quantified over nothing. Every route reports that the same way,
`skipped` with the empty region named, never a proof, a falsification,
or a disproof flagged as an engine bug."""
import pytest

from mathema.conjecture import check_conjectures, claim


def sq(x: float) -> float:
    return x * x


@pytest.mark.parametrize("law", [
    "assuming x > 5, for x in [0, 1], f(x) >= 3",
    "assuming x > 5, for x in [0, 1], f(x) <= 3",
    "assuming x > 1, for x in [0, 1], f(x) >= 3",
    "assuming 5 < x, for x in [0, 1], f(x) >= 3",
])
@pytest.mark.parametrize("route", ["best", "derive", "probe"])
def test_an_empty_premise_region_is_skipped_on_every_route(law, route):
    r = check_conjectures(sq, [claim(law, route=route)])[0]
    assert r.verdict == "skipped", (r.verdict, r.route, r.note)
    assert "uncorroborated" not in r.note
    assert (r.meta or {}).get("mathema.corroboration") != "uncorroborated"


def test_a_premise_that_leaves_some_region_still_adjudicates():
    r = check_conjectures(sq, [claim(
        "assuming x >= 1, for x in [0, 1], f(x) >= 1", route="derive")])[0]
    assert r.verdict == "proven", (r.verdict, r.note)
