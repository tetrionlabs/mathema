# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A derive disproof reproduced against the real function indicts the
mathematics, so the record shows it on the mathematics line whichever
decider found the witness: z3's exact point (the `smt` extra) or the
interval refinement that runs without it."""
import pytest

import mathema


def discounted(price: float, rate: float) -> float:
    return price * (1 - rate)


def _lines(monkeypatch, with_z3: bool) -> list:
    if with_z3:
        pytest.importorskip("z3")
    else:
        import mathema.symbolic._smt as smt
        monkeypatch.setattr(smt, "available", lambda: False)
    record = mathema.check(discounted, claims=[
        mathema.claim("for rate in [0, 1], f(price, rate) <= price",
                      name="at_most_price"),
        mathema.claim("for price in [0, 1e6], rate in [0, 1], "
                      "f(price, rate) <= price",
                      name="at_most_price_when_positive"),
    ])
    return str(record).splitlines()


@pytest.mark.parametrize("with_z3", [True, False])
def test_the_falsified_mathematics_line_is_shown(monkeypatch, with_z3):
    lines = _lines(monkeypatch, with_z3)
    falsified = [ln.split() for ln in lines
                 if ln.strip().startswith("falsified ")]
    assert [words[1] for words in falsified] == ["mathematics"], lines
