# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A falsified record keeps a witness that breaks the claim when read
back from the record. Every coordinate is stored at full precision (the
shortest text that reads back as the same float), so a failure that
lives on a single float, like `-(x^3 - 3x + 1)^2 < 0` at
0.34729635533386066, is reproduced by the stored point, not by a
six-digit rounding of it that satisfies the claim."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.gates import _fmt_point
from mathema.probing import _fmt


def negated_square(x: float) -> float:
    return -(x ** 3 - 3 * x + 1) ** 2


def _point(text):
    return {k.strip(): float(v) for k, v in
            (part.split("=") for part in text.split(","))}


@pytest.mark.needs_full_proof_budget
def test_the_stored_witness_breaks_the_claim():
    (p,) = check_conjectures(negated_square, [claim("for x in [0, 1], f(x) < 0")],
                             extensive=True)
    assert p.verdict == "falsified"
    for text in (p.counterexample, p.stratum["witness"]):
        x = _point(text)["x"]
        assert not negated_square(x) < 0, text


def test_a_witness_coordinate_keeps_every_digit():
    x = 0.34729635533386066
    assert _fmt_point({"x": x, "y": 0.5}, ["x", "y"]) == "x=0.34729635533386066, y=0.5"
    assert _fmt((x, 2.0), ("x", "n")) == "x=0.34729635533386066, n=2"
    assert float(_fmt_point({"x": math.pi}, ["x"]).split("=")[1]) == math.pi
