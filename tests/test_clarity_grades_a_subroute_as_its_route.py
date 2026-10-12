# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A holds reached by a subroute with no grade of its own is graded as
the route it refines: `derive:extensive` and `derive:brute_force` as
derive, `probe:counterfactual` as a random probe, while a subroute with
its own grade (`probe:semi_analytical`) keeps it."""
import pytest

from mathema.badges import _HOLDS_STRENGTH, _strength


@pytest.mark.parametrize("route, graded_as", [
    ("derive:extensive", "derive"), ("derive:brute_force", "derive"),
    ("examine:anything", "examine"), ("probe:counterfactual", "probe"),
    ("probe:semi_analytical", "probe:semi_analytical")])
def test_a_subroute_is_graded_as_the_route_it_refines(route, graded_as):
    assert _strength("holds", route) == _HOLDS_STRENGTH[graded_as]
