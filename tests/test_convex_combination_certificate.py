# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The convex-combination certificate: a from-first-element fold whose
update weights are nonnegative and sum to 1 keeps every accumulator
state a convex combination of the elements, so the min/max bounds are
proven by induction, no closed form needed. Outside the certificate's
side conditions the general machinery decides, and a genuinely false
bound falsifies with an executed witness."""
import textwrap

import pytest


@pytest.fixture(scope="module")
def ema(tmp_path_factory):
    p = tmp_path_factory.mktemp("cc") / "emamod.py"
    p.write_text(textwrap.dedent('''
        def ema(x: list, alpha: float) -> float:
            """Exponentially weighted moving average."""
            y = x[0]
            for v in x[1:]:
                y = alpha * v + (1 - alpha) * y
            return y
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("emamod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.ema


def _one(fn, law):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, route="best")])
    return p


def test_the_bounds_prove_under_convex_weights(ema):
    lower = _one(ema, "for alpha in [0, 1], min(x) <= f(x, alpha)")
    upper = _one(ema, "for alpha in [0, 1], f(x, alpha) <= max(x)")
    for p in (lower, upper):
        assert p.verdict == "proven", (p.verdict, p.note)
        assert "convex-combination certificate" in (p.sketch or "")
        assert "by induction on the fold" in (p.sketch or "")


def test_mirrored_spellings_prove_too(ema):
    p = _one(ema, "for alpha in [0, 1], f(x, alpha) >= min(x)")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_outside_the_weight_conditions_the_certificate_declines(ema):
    # alpha up to 2: a weight exceeds 1, the state can overshoot the
    # band, and the claim is genuinely false; the certificate declines
    # and the general machinery falsifies with an executed witness
    p = _one(ema, "for alpha in [0, 2], f(x, alpha) <= max(x)")
    assert p.verdict == "falsified"
    assert p.counterexample
    assert "convex-combination" not in (p.sketch or "")


def test_strict_bounds_are_not_certified(ema):
    # at alpha = 1 the fold returns the last element, which can BE the
    # maximum, so the strict claim is false and must not be certified
    p = _one(ema, "for alpha in [0, 1], f(x, alpha) < max(x)")
    assert p.verdict == "falsified"
    assert p.counterexample
    assert "convex-combination" not in (p.sketch or "")
