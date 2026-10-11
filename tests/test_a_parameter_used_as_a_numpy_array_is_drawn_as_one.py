# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An unannotated parameter the body uses as a numpy array (`a.size`
beside `np.mean(a)`, in a module importing numpy) is drawn as a numpy
array, so the claim exercises the code as it is called, not a list
that has no `.size`."""

import pytest

pytest.importorskip("numpy")

import os  # noqa: E402
import sys  # noqa: E402

from mathema.analysis import analyze_source  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.runtime_types import realised_parameters  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))
import numpy_body  # noqa: E402


def test_the_parameter_is_realised_as_an_array():
    facts = analyze_source(numpy_body.scaled_mean)
    assert realised_parameters(facts)["a"].adapter == "numpy.ndarray"


def test_the_claim_holds_on_arrays():
    (p,) = check_conjectures(numpy_body.scaled_mean, [claim(
        "for a in [-1e6, 1e6]^n, f(a) ~= sum(a)", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_over_all_of_r_n_the_array_overflows_at_the_largest_doubles():
    # np.mean of two largest doubles sums to inf, so the array
    # computation gives no value there
    (p,) = check_conjectures(numpy_body.scaled_mean, [claim(
        "for a in R^n, f(a) ~= sum(a)", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.counterexample, p.note)
    assert p.counterexample == (
        "a = [1.7976931348623157e+308, 1.7976931348623157e+308]: f returned "
        "inf, and an infinity for a finite input is no value"), p.counterexample
