# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A derivative claim cannot be run at a point, but the function can be
called at a named missing value: a None there that its return type does
not admit falsifies the claim at that value, as on every other claim."""
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim


def none_under_float(x: Optional[float], y: float) -> float:
    if x is None:
        return None  # type: ignore[return-value]
    return x * 0 + y


@pytest.mark.parametrize("domain", ["{1, None}", "[0, 1] | {None}"])
def test_none_under_a_float_return_falsifies_the_derivative_claim(domain):
    (row,) = check_conjectures(none_under_float, [claim(
        f"for x in {domain}, y in [0, 1], d(f(x, y), y) == 1")])
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert (row.counterexample or "").startswith("x = None"), row.counterexample
    assert "return type float does not admit" in (row.note or "") + (row.sketch or "")
