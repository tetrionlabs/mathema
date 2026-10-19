# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A stated `is_defined` region that reads `det(a)` or `dim(b)` is
tried on its boundary: a singular matrix, and the empty vector below
`dim(b) >= 1`. When the parameters share a dimension by name
(`Mat("n", "n")` and `Vec("n")`), every boundary point keeps it
shared: the singular matrix is n by n for the vector's n, and the
empty vector is the dimension n at zero, so every parameter sized by
n is empty with it. A function that returns a value on the boundary
is then falsified for the right reason, not saved by a shape mismatch
the boundary point made up."""
import pytest

import mathema
from mathema.types import Mat, Vec

np = pytest.importorskip("numpy")

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


def _declared(fn, statement):
    c = mathema.claim(statement, name="is_defined")
    (p,) = [p for p in mathema.check(fn, claims=[c]).probes
            if p.meta.get("mathema.surface") == "declared"]
    return p


def pinv_solve(a: Mat("n", "n"), b: Vec("n")) -> list:
    return list(np.linalg.pinv(np.asarray(a, dtype=float))
                @ np.asarray(b, dtype=float))


def test_a_singular_matrix_on_the_boundary_shares_n_with_the_vector():
    # the pseudo-inverse answers a singular matrix too, so the region
    # `det(a) != 0` is wrong: a singular n-by-n matrix with an n-vector
    # returns a value outside it
    p = _declared(pinv_solve, "det(a) != 0")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "outside the stated region" in p.counterexample, p.counterexample


def square_side(a: Mat("n", "n"), b: Vec("n")) -> float:
    n = len(b)
    return float(np.asarray(a, dtype=float).reshape(n, n).shape[0])


def test_the_empty_boundary_empties_every_parameter_sized_by_n():
    # at n = 0 the function returns 0.0, a value outside `dim(b) >= 1`
    p = _declared(square_side, "dim(b) >= 1")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "outside the stated region" in p.counterexample, p.counterexample


_SEEN: list = []


def recorded(a: Mat("n", "n"), b: Vec("n")) -> float:
    _SEEN.append((a, b))
    return 1.0


@pytest.mark.parametrize("statement", [
    "for a in [-10, 10]^(n,n), b in [-10, 10]^n, det(a) != 0",
    "dim(b) >= 1"])
@pytest.mark.parametrize("seed", range(4))
def test_every_point_tried_shares_n(statement, seed):
    import random

    from mathema.analysis import analyze_source
    from mathema.claim_families import _region_probe
    facts = analyze_source(recorded)
    _SEEN.clear()
    c = mathema.claim(statement, name="is_defined")
    _region_probe(recorded, facts, c, dict(c.domain or {}),
                  random.Random(seed), 40, "is_defined")
    assert _SEEN
    mismatched = [(a, b) for a, b in _SEEN
                  if len(a) != len(b) or any(len(row) != len(b) for row in a)]
    assert not mismatched, mismatched[:2]
    if "det" in statement:
        singular = [a for a, _b in _SEEN
                    if len(a) and abs(np.linalg.det(np.asarray(a))) == 0.0]
        assert singular, "no singular matrix was tried"
    else:
        assert any(len(b) == 0 and len(a) == 0 for a, b in _SEEN), \
            "the empty boundary was not tried"
