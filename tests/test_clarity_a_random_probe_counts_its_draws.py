# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A holds from random sampling is scaled by how many failure-free
draws it rests on: at 95% confidence, n draws without a failure leave
up to 3/n of what they sample possibly failing, so a holds over 13
draws credits less than one over 1,000. A row that records no count
keeps the random probe's grade, and a structured probe or a
counterfactual one, which runs chosen points, is not scaled."""
import pytest

from mathema.badges import _HOLDS_STRENGTH, _strength


def test_fewer_draws_credit_less():
    assert _strength("holds", "probe", 13) < _strength("holds", "probe", 1000) \
        < _strength("holds", "probe")
    assert _strength("holds", "probe", 13) == pytest.approx(
        _HOLDS_STRENGTH["probe"] * (1 - 3 / 13))


def test_three_draws_or_fewer_credit_nothing():
    assert _strength("holds", "probe", 3) == 0.0


def test_a_structured_probe_is_not_scaled_by_its_draws():
    assert _strength("holds", "probe:algorithmic", 13) == \
        _HOLDS_STRENGTH["probe:algorithmic"]
    assert _strength("holds", "probe:counterfactual", 5) == \
        _HOLDS_STRENGTH["probe"]
