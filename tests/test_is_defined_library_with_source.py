# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_defined` on a library function that HAS Python source
(`numpy.linalg.inv`, `statistics.mean`): region equivalence over the
library's own body does not decide, so the claim is adjudicated by
execution. A region reading `det(a)` draws square matrices and a
singular one on its boundary; a region reading `dim(data)` draws
sequences and the empty one below its boundary."""
import statistics

import pytest

import mathema

np = pytest.importorskip("numpy")


def _declared(fn, statement):
    c = mathema.claim(statement, name="is_defined")
    (p,) = [p for p in mathema.check(fn, claims=[c]).probes
            if p.meta.get("mathema.surface") == "declared"]
    return p


def test_inv_is_defined_where_the_determinant_is_nonzero():
    p = _declared(np.linalg.inv, "det(a) != 0")
    assert p.verdict == "holds", p.note
    assert p.route == "probe:algorithmic"
    assert "outside it returned no value" in p.note
    # at least one singular matrix was executed and returned no value
    assert "and 0 outside" not in p.note


def test_a_wrong_region_for_inv_is_falsified_at_an_executed_matrix():
    p = _declared(np.linalg.inv, "det(a) > 0")
    assert p.verdict == "falsified", p.note
    assert "a value outside the stated region" in p.counterexample


def test_statistics_mean_is_defined_on_a_non_empty_sequence():
    p = _declared(statistics.mean, "dim(data) >= 1")
    assert p.verdict == "holds", p.note
    assert "and 0 outside" not in p.note


def test_a_space_binding_shapes_the_draws():
    p = _declared(np.linalg.inv, "for a in R^(n,n), det(a) != 0")
    assert p.verdict == "holds", p.note
