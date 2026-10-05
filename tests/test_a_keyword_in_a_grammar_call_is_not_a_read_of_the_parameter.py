# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library row's statement may name a keyword argument of a grammar
word (`var(m, ddof=1)`). That keyword is not the library function's own
parameter `ddof`, so the call to f still holds `ddof` at its default:
numpy.cov's `of_a_vector` row is never run with a drawn `ddof`."""
import pytest

np = pytest.importorskip("numpy")


def test_the_defaulted_parameter_stays_at_its_default():
    from mathema.compendium import ensure_bundled
    from mathema.conjecture import call_defaults, claim
    ensure_bundled()
    cj = claim("for m in R^n, assuming dim(m) >= 2, f(m) ~= var(m, ddof=1)",
               name="of_a_vector")
    kept, pins, problem = call_defaults(np.cov, cj)
    assert "ddof" in kept and kept["ddof"] is None, kept
    assert pins == {} and problem is None


def test_a_parameter_the_statement_reads_is_not_held():
    from mathema.compendium import ensure_bundled
    from mathema.conjecture import call_defaults, claim
    ensure_bundled()
    cj = claim("for a in R^n, ddof in [0, 0], f(a, ddof=ddof) >= 0",
               name="reads")
    kept, _pins, _problem = call_defaults(np.std, cj)
    assert "ddof" not in kept, kept
