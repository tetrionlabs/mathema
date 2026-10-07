# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter the body could read as a sequence is drawn as the claim
binds it: `q in [0, 1]` is a number in [0, 1], so numpy.quantile is
exercised at a scalar q, the claim the record states, never at a list
of levels."""

import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402


def test_numpy_quantile_is_called_with_a_scalar_level(monkeypatch):
    (p,) = check_conjectures(np.quantile, [claim(
        "for a in [-1e6, 1e6]^n, q in [0, 1], min(a) <= f(a, q) <= max(a)",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    import mathema.probing as probing
    drawn = []
    original = probing._synth

    def spy(kind, rng, bounds=None, **kw):
        value = original(kind, rng, bounds, **kw)
        if bounds is not None and getattr(bounds, "dims", ()) == () \
                and not isinstance(value, (int, float)):
            drawn.append((kind, value))
        return value
    monkeypatch.setattr(probing, "_synth", spy)
    import mathema.conjecture as conjecture
    monkeypatch.setattr(conjecture, "_synth", spy, raising=False)
    check_conjectures(np.quantile, [claim(
        "for a in [-1e6, 1e6]^n, q in [0, 1], min(a) <= f(a, q) <= max(a)",
        route="probe")])
    assert not [v for k, v in drawn if isinstance(v, list)], drawn[:3]
