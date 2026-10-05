# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When derive cannot decide a value claim and the probe stands in for
the mathematics, a point where the float computation overflows (f
returns nan for finite inputs) while the claim holds there in exact
arithmetic is a failure of the computation: the `[float]` line carries
it and the mathematics line does not (ruling of 2026-10-01: tolerance
and pseudo-infinity belong to the computation)."""
import mathema
import mathema.conjecture as conjecture


def ema(x: list, alpha: float) -> float:
    if not x:
        raise ValueError("ema of an empty sequence")
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


TRANSLATION = mathema.claim(
    "for x in R^n, alpha in R, let c be [-5, 5], "
    "f(x, alpha) + c == f(g(x, c), alpha)",
    name="translation", funcs={"g": "mathema.f.shift_seq"})


def _rows(fn, monkeypatch):
    monkeypatch.setattr(conjecture, "_adjudicate_derive",
                        lambda *a, **k: None)
    return {p.name: p for p in mathema.check(fn, claims=[TRANSLATION]).probes
            if p.name.startswith("translation")}


def test_the_overflow_is_on_the_float_line_not_the_mathematics(monkeypatch):
    rows = _rows(ema, monkeypatch)
    assert rows["translation"].verdict == "holds", rows["translation"].counterexample
    computation = rows["translation[float]"]
    assert computation.verdict == "falsified"
    assert "returned nan" in computation.counterexample


def test_a_claim_false_in_exact_arithmetic_still_falls_on_the_mathematics(monkeypatch):
    def shifted(x: list, alpha: float) -> float:
        return ema(x, alpha) + (1.0 if x[0] > 0 else 0.0)
    rows = _rows(shifted, monkeypatch)
    assert rows["translation"].verdict == "falsified"
