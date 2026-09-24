# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every point the probe route calls the function at lies inside the
claim's declared domain, so a counterexample is always an in-domain
point: integer sampling honours open ends and fractional bounds, an
open end near a subnormal does not round onto itself, a recorded
counterexample outside the domain is not replayed, and a range with no
members is refused as misspecified rather than sampled."""
import pytest

from mathema.conjecture import check_conjectures, claim


def reciprocal(n: int) -> float:
    return 1 / n


def reciprocal_real(x: float) -> float:
    return 1.0 / x


def identity(x: float) -> float:
    return x


@pytest.mark.parametrize("law", [
    "for n in (0, 5] ⊂ Z, f(n) > 0",
    "for n in (0, 5) ⊂ Z, f(n) >= 0.25",
    "for n in [1, 5) ⊂ Z, f(n) >= 0.25",
    "for n in (0, 5), f(n) > 0",
    "for n in (0, 5], f(n) > 0",
    "for n in [0.5, 5], f(n) > 0",
])
def test_integer_sampling_never_leaves_the_declared_range(law):
    (p,) = check_conjectures(reciprocal, [claim(law, route="probe")])
    assert p.verdict == "holds", p.counterexample


@pytest.mark.parametrize("law", [
    "for x in (0, 1e-320), f(x) > 0",
    "for x in (-1e-320, 0), f(x) < 0",
])
def test_an_open_end_beside_a_subnormal_is_never_sampled(law):
    (p,) = check_conjectures(identity, [claim(law, route="probe")])
    assert p.verdict == "holds", p.counterexample


def test_a_pinned_counterexample_outside_the_domain_is_not_replayed():
    cj = claim("for x in [0, 1], f(x) >= 0", route="probe")
    cj.pins = [{"args": [-5.0]}]
    (p,) = check_conjectures(identity, [cj])
    assert p.verdict == "holds", p.counterexample


def test_a_pinned_counterexample_inside_the_domain_still_replays():
    cj = claim("for x in [-10, 1], f(x) >= 0", route="probe")
    cj.pins = [{"args": [-5.0]}]
    (p,) = check_conjectures(identity, [cj])
    assert p.verdict == "falsified"
    assert p.meta["mathema.counterexample_args"] == [-5.0]


@pytest.mark.parametrize("route", ["probe", "derive", "best"])
@pytest.mark.parametrize("law", [
    "for x in (1, 1), f(x) == 5",
    "for x in (1, 1], f(x) == 5",
    "for x in [1, 1), f(x) == 5",
    "for n in (0, 1) ⊂ Z, f(n) == 7",
])
def test_a_range_with_no_members_is_refused_as_misspecified(law, route):
    (p,) = check_conjectures(identity, [claim(law, route=route)])
    assert p.verdict == "skipped:misspecified"
    assert "empty" in p.note


def count(n: int) -> int:
    return n


def test_an_unbounded_integer_range_samples_and_states_its_real_range():
    from mathema._sampling import _LARGE
    (p,) = check_conjectures(count, [claim("for n in [1, oo), f(n) >= 1",
                                           route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert f"n~U{{1..{int(_LARGE) + 1}}}" in p.meta["mathema.sampling"]
