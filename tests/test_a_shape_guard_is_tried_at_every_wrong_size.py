# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`dimensions_enforced` and `size_enforced` say a function rejects
every input whose shape breaks its markers. They try the mismatches
they claim to rule out: each shared dimension wrong on each parameter
that carries it, one up and one down, at length one (where numpy
broadcasts) and where it happens to equal another dimension; and a
fixed size larger, smaller and zero where the value can hold that. A
function that accepts any one of these is falsified, with the sizes
that show it."""
import re

import pytest

from mathema import enforce_dimensions
from mathema.types import Mat, Vec, type_probes

np = pytest.importorskip("numpy")

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


def _row(fn, name):
    (row,) = [p for p in type_probes(fn) if p.name == name]
    return row


# --- a shared dimension ------------------------------------------------

def factor_exposure(weights: Vec("n"), betas: Mat("n", "k")) -> Vec("k"):
    # betas @ weights needs k == n, so a weights of length k is
    # accepted whatever n is
    return list(np.asarray(betas) @ np.asarray(weights))


def test_a_mismatch_equal_to_another_dimension_is_found():
    row = _row(factor_exposure, "dimensions_enforced")
    assert row.verdict == "falsified", (row.verdict, row.n, row.note)
    m = re.search(r"weights\[n\]=(\d+) vs n=(\d+) elsewhere \(k=(\d+)\)",
                  row.counterexample or "")
    assert m, row.counterexample
    wrong, n, k = map(int, m.groups())
    assert wrong != n and wrong == k, row.counterexample


def scaled(w: Vec("n"), x: Vec("n")) -> Vec("n"):
    return list(np.asarray(w, dtype=float) * np.asarray(x, dtype=float))


def test_a_mismatch_numpy_broadcasts_is_found():
    row = _row(scaled, "dimensions_enforced")
    assert row.verdict == "falsified", (row.verdict, row.n, row.note)
    # one side of length one, the other longer: numpy stretches it
    assert re.search(r"\w\[n\]=(1 vs n=[2-9]|[2-9] vs n=1)\b",
                     row.counterexample or ""), row.counterexample


def checked_scaled(w: Vec("n"), x: Vec("n")) -> Vec("n"):
    if len(w) != len(x):
        raise ValueError("w and x differ in length")
    return list(np.asarray(w, dtype=float) * np.asarray(x, dtype=float))


@enforce_dimensions()
def guarded_exposure(weights: Vec("n"), betas: Mat("n", "k")) -> Vec("k"):
    return list(np.asarray(weights) @ np.asarray(betas))


@pytest.mark.parametrize("fn", [checked_scaled, guarded_exposure],
                         ids=lambda fn: fn.__name__)
def test_a_function_that_rejects_every_mismatch_holds(fn):
    row = _row(fn, "dimensions_enforced")
    assert row.verdict == "holds", (row.verdict, row.counterexample)


_TRIED: list = []


def recording(w: Vec("n"), b: Mat("n", "k")) -> Vec("k"):
    _TRIED.append((len(w), len(b), len(b[0]) if b else None))
    if len(w) != len(b):
        raise ValueError("mismatch")
    return [0.0] * (len(b[0]) if b else 0)


def test_every_parameter_is_tried_up_down_at_one_and_at_the_other_dimension():
    _TRIED.clear()
    row = _row(recording, "dimensions_enforced")
    assert row.verdict == "holds", (row.verdict, row.counterexample)
    w_wrong = [(w, n, k) for w, n, k in _TRIED if w != n]
    assert any(w > n for w, n, _k in w_wrong), _TRIED
    assert any(w < n for w, n, _k in w_wrong), _TRIED
    assert any(w == 1 and n > 1 for w, n, _k in w_wrong), _TRIED
    assert any(w == k for w, n, k in w_wrong), _TRIED
    # the matrix carrying n is the wrong one as well, not only the vector
    assert any(n == 1 and w > 1 for w, n, _k in w_wrong), _TRIED
