# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Signal-engineering worked examples for the derive route: power vs.
energy signals, built entirely from primitives that already exist
(integrate, lim, Sum/Prod). A *literal* Fourier transform would still
need complex numbers, which the grammar doesn't support, not attempted
here."""
import math

from mathema.conjecture import claim, check_conjectures


def decaying_pulse(t: float) -> float:
    return math.e ** (-abs(t))


def cosine_signal(t: float) -> float:
    return math.cos(t)


def test_energy_signal_finite_total_energy():
    # An energy signal has finite total energy: integral of |x(t)|^2 over
    # all time. A decaying pulse is the textbook example, here exactly 1.
    results = check_conjectures(
        decaying_pulse,
        [claim("integrate(f(t)^2, t, -oo, oo) == 1", route="derive")])
    assert results[0].verdict == "proven"


def test_power_signal_finite_average_power():
    # A power signal has infinite energy but finite *average* power:
    # lim_{T->oo} (1/2T) * integral of x(t)^2 over [-T, T]. A periodic
    # signal is the textbook example; cos(t)'s average power is 1/2.
    # This is also the regression case for lim(...) accepting a bound
    # variable that isn't one of the function's own parameters (T here
    # only appears inside the nested integrate).
    results = check_conjectures(
        cosine_signal,
        [claim("lim(integrate(f(t)^2, t, -T, T) / (2 * T), T, oo) == 1/2",
              route="derive")])
    assert results[0].verdict == "proven"
