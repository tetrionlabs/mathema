# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The probe route evaluates under one pinned floating-point regime,
so a verdict and its witness do not depend on the caller's own numpy
error settings: a negative square root is a NaN under every ambient
`np.errstate`, never a FloatingPointError in one process and a NaN in
another."""
import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")


def root(x: float) -> float:
    return float(np.sqrt(x))


def _adjudicate(statement):
    (p,) = check_conjectures(root, [claim(statement, route="probe")])
    return p


@pytest.mark.parametrize("statement", [
    "for x in [-4, 4], f(x) >= 0",
    "for x in [-4, -1], f(x) != 5",
])
def test_the_verdict_and_witness_ignore_the_ambient_error_regime(statement):
    with np.errstate(all="raise"):
        raising = _adjudicate(statement)
    with np.errstate(all="warn"):
        warning = _adjudicate(statement)
    with np.errstate(all="ignore"):
        ignoring = _adjudicate(statement)
    assert raising.verdict == warning.verdict == ignoring.verdict \
        == "falsified"
    assert raising.counterexample == warning.counterexample \
        == ignoring.counterexample
    assert "nan" in raising.counterexample


def test_the_callers_regime_is_restored_after_a_check():
    with np.errstate(all="raise"):
        _adjudicate("for x in [-4, 4], f(x) >= 0")
        assert np.geterr()["invalid"] == "raise"
