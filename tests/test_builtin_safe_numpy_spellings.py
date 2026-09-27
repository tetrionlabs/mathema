# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_builtin_safe` knows numpy's spellings of the restricted-domain
functions (`arcsin`, `arccos`, `log2`, `log10`, `log1p`, `arccosh`,
`arctanh`) as well as `math`'s, so a numpy call outside its real
domain is a hazard with its own edge points, and a claim over a
domain that crosses the edge is falsified with an executed witness."""
import pytest

import mathema
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.hazards import _SAFE_RANGE, hazard_points

np = pytest.importorskip("numpy")


def log10_of(x: float) -> float:
    return float(np.log10(x))


def arcsin_of(x: float) -> float:
    return float(np.arcsin(x))


def test_is_builtin_safe_on_numpy_log10_is_falsified_with_a_witness():
    (p,) = [p for p in mathema.check(
        log10_of, claims=["for x in [-1, 1], is_builtin_safe(x)"]).probes
        if p.meta.get("mathema.surface") == "declared"]
    assert p.verdict == "falsified", (p.verdict, p.note, p.sketch)
    assert p.counterexample


def test_is_builtin_safe_on_numpy_log10_inside_its_domain_is_proven():
    (p,) = check_conjectures(
        log10_of, [claim("for x in [1, 10], is_builtin_safe(x)")])
    assert p.verdict == "proven"


def test_the_builtin_domain_hazard_points_at_arcsins_unit_edges():
    points = hazard_points(arcsin_of, analyze_source(arcsin_of),
                           kinds=["builtin_domain"])
    edges = {p.value for p in points if p.param == "x"
             and p.source == "arcsin"}
    assert edges == {-1.0, 1.0}


@pytest.mark.parametrize("name, safe_range", [
    ("arcsin", (-1.0, True, 1.0, True)),
    ("arccos", (-1.0, True, 1.0, True)),
    ("log2", (0.0, False, float("inf"), True)),
    ("log10", (0.0, False, float("inf"), True)),
    ("log1p", (-1.0, False, float("inf"), True)),
    ("arccosh", (1.0, True, float("inf"), True)),
    ("arctanh", (-1.0, False, 1.0, False)),
])
def test_each_numpy_spelling_carries_its_real_domain(name, safe_range):
    assert _SAFE_RANGE[name] == safe_range
