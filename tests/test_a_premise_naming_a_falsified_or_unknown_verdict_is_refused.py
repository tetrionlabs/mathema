# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A premise rests a claim on another claim that holds or is proven
(`assuming X holds`, `assuming X is proven`). `assuming X is
falsified` and `assuming X is unknown` are not premises mathema reads,
so the claim is refused with a message saying so, and naming the
missing claim when X names none; it is never adjudicated as if the
premise were not there."""
import pytest

import mathema
from mathema.conjecture import claim


def _square(x: float) -> float:
    return x * x


@pytest.mark.parametrize("word", ["falsified", "unknown"])
def test_a_premise_on_a_claim_that_does_not_exist_is_refused(word):
    rec = mathema.check(_square, claims=[claim(
        f"assuming no_such_claim is {word}, for x in [0, 1], f(x) >= 0",
        name="c")])
    row = next(p for p in rec.probes if p.name == "c")
    assert row.verdict.startswith("skipped"), (row.verdict, row.note)
    assert f"is {word}" in row.note, row.note
    assert "no_such_claim" in row.note and "no claim" in row.note, row.note


@pytest.mark.parametrize("word", ["falsified", "unknown"])
def test_a_premise_on_an_existing_claim_is_refused_with_the_readable_forms(
        word):
    rec = mathema.check(_square, claims=[
        claim("for x in [-1, 1], f(x) <= -1", name="wrong"),
        claim(f"assuming wrong is {word}, for x in [0, 1], f(x) >= 0",
              name="c")])
    row = next(p for p in rec.probes if p.name == "c")
    assert row.verdict.startswith("skipped"), (row.verdict, row.note)
    assert "holds" in row.note and "is proven" in row.note, row.note
    assert "no claim" not in row.note, row.note
