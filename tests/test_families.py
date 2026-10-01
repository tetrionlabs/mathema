# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/families.py: the claim-family registry, registration,
external discovery via entry points, and the built-ins-always-win
merge rule."""
from unittest.mock import MagicMock, patch

import numpy as np

from mathema import families
from mathema.conjecture import check_conjectures, claim
from mathema.symbolic import ProofResult

# mathema.symbolic._dot registers a real "dot_product" family the
# moment it's first imported, by anything, anywhere in the process,
# not just this file, so it's already present by the time these
# tests run. Snapshot it and restore exactly that state after each
# test, rather than clearing to empty, so this file never permanently
# erases a real built-in for every test that runs after it.
_BASELINE = dict(families._REGISTRY)


def setup_function(_fn):
    # every test starts from a known-empty registry, regardless of
    # what else has run in this process before it.
    families._REGISTRY.clear()
    families._discovered_external.cache_clear()


def teardown_function(_fn):
    families._REGISTRY.clear()
    families._REGISTRY.update(_BASELINE)
    families._discovered_external.cache_clear()


class _AlwaysDeclines:
    def can_handle(self, fn, facts, claim_name: str) -> bool:
        return False

    def routes(self) -> dict:
        return {"derive": self._derive}

    def _derive(self, fn, facts, lhs_src, rhs_src, relation,
               domain=None, tolerance=None):
        return None


class _AlwaysHandles:
    def can_handle(self, fn, facts, claim_name: str) -> bool:
        return True

    def routes(self) -> dict:
        return {"derive": self._derive}

    def _derive(self, fn, facts, lhs_src, rhs_src, relation,
               domain=None, tolerance=None):
        return "sentinel-result"


def test_families_empty_by_default():
    assert families.families() == {}


def test_register_makes_a_family_discoverable():
    fam = _AlwaysHandles()
    families.register("always", fam)
    assert families.families() == {"always": fam}


def test_reregistering_the_same_name_replaces_it():
    families.register("x", _AlwaysDeclines())
    second = _AlwaysHandles()
    families.register("x", second)
    assert families.families()["x"] is second


def test_external_entry_point_is_discovered():
    fam = _AlwaysHandles()
    ep = MagicMock()
    ep.name = "external_family"
    ep.load.return_value = fam
    with patch("mathema.families.entry_points", return_value=[ep]):
        assert families.families() == {"external_family": fam}


def test_broken_external_entry_point_is_skipped_not_raised():
    ep = MagicMock()
    ep.name = "broken"
    ep.load.side_effect = RuntimeError("boom")
    with patch("mathema.families.entry_points", return_value=[ep]):
        assert families.families() == {}


def test_builtin_wins_over_external_of_the_same_name():
    builtin = _AlwaysHandles()
    families.register("dot_product", builtin)
    ep = MagicMock()
    ep.name = "dot_product"
    ep.load.return_value = _AlwaysDeclines()
    with patch("mathema.families.entry_points", return_value=[ep]):
        assert families.families()["dot_product"] is builtin


def _dot_ab(a: list, b: list) -> float:
    return float(np.dot(a, b))


class _FakeDotFamily:
    """Declines to do any real symbolic work at all, a "proven"
    verdict from this family can only mean try_prove()'s dispatch
    genuinely went through the registry, not that lift_dot/
    try_prove_dot happened to prove the claim on their own."""

    def can_handle(self, fn, facts, claim_name: str) -> bool:
        return True

    def routes(self) -> dict:
        return {"derive": self._derive}

    def _derive(self, fn, facts, lhs_src, rhs_src, relation,
               domain=None, tolerance=None) -> ProofResult:
        return ProofResult("proven", sketch="routed through the test's fake family, not the real one")


def test_registering_a_replacement_dot_family_reroutes_try_prove():
    # this is the concrete proof the extension point is genuinely
    # pluggable, not just refactored-in-place: register a fake family
    # under the real family's own name and confirm try_prove, reached
    # through the ordinary public API, check_conjectures; returns
    # this fake family's own, otherwise-unreachable verdict.
    families.register("dot_product", _FakeDotFamily())
    results = check_conjectures(
        _dot_ab, [claim("f(a, b) == f(a, b)", route="derive")])
    assert results[0].verdict == "proven"
    assert "test's fake family" in results[0].sketch
