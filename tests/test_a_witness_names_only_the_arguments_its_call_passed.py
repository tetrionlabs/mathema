# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness prints the arguments of the call that failed: a parameter
the claim's call leaves out runs at its default, so the witness never
names a drawn value for it, over vectors as over scalars."""
import math

import pytest

from mathema.claims import check_conjectures, claim


def short_window(xs: list[float], k: int = 3) -> float:
    if len(xs) < k:
        return math.nan
    return 0.0


def scaled_window(x: float, k: int = 3) -> float:
    return math.nan if k > 2 else x


@pytest.mark.parametrize("route", [{}, {"route": "probe"}])
def test_a_vector_claim_leaving_out_a_defaulted_parameter_never_names_it(route):
    (p,) = check_conjectures(short_window, [claim("for xs in R^n, f(xs) >= 0", **route)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("xs = "), p.counterexample
    assert "k = " not in p.counterexample, p.counterexample
    # the witness reproduces: the call it names, run as written, fails
    xs = eval(p.counterexample.split(":")[0].split("=", 1)[1])
    assert math.isnan(short_window(xs))


def test_a_vector_claim_passing_the_defaulted_parameter_names_it():
    (p,) = check_conjectures(short_window, [claim(
        "for xs in R^n, k in {5}, f(xs, k) >= 0", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "k = 5" in p.counterexample, p.counterexample


def test_a_scalar_claim_leaving_out_a_defaulted_parameter_never_names_it():
    (p,) = check_conjectures(scaled_window, [claim("f(x) >= 0", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "k = " not in p.counterexample, p.counterexample


def test_a_library_methods_defaulted_parameters_stay_out_of_its_witness():
    pd = pytest.importorskip("pandas")
    (p,) = check_conjectures(pd.Series.corr, [claim(
        "for self in R^n, other in R^n, abs(f(self, other)) <= 1 + 1e-9",
        route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "method = " not in p.counterexample, p.counterexample
    assert "min_periods = " not in p.counterexample, p.counterexample


def test_a_library_functions_held_defaults_are_named_at_the_values_they_ran_at():
    np = pytest.importorskip("numpy")
    (p,) = check_conjectures(np.ptp, [claim("for a in R^n, f(a) <= max(a)",
                                            route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    # a bundled library key keeps its defaulted parameters at their
    # defaults, so the call ran with them and the witness says so
    assert ", axis = None, out = None, keepdims = <no value>: " in p.counterexample, \
        p.counterexample
