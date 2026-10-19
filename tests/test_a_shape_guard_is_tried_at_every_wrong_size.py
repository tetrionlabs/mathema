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


# --- a fixed size ------------------------------------------------------

def head_sum(v: Vec(3)) -> float:
    if len(v) > 3:
        raise ValueError("at most three entries")
    return float(sum(v))


def first_two(v: Vec(3)) -> float:
    if len(v) > 3:
        raise ValueError("at most three entries")
    return float(v[0] + v[1])


@pytest.mark.parametrize("fn, smallest", [(head_sum, 0), (first_two, 2)],
                         ids=lambda v: getattr(v, "__name__", str(v)))
def test_a_fixed_size_accepted_smaller_is_found(fn, smallest):
    row = _row(fn, "size_enforced")
    assert row.verdict == "falsified", (row.verdict, row.n, row.note)
    m = re.search(r"v has length (\d+) where the shape fixes length 3",
                  row.counterexample or "")
    assert m and int(m.group(1)) < 3, row.counterexample
    assert f"v has length {smallest} " in row.counterexample, \
        row.counterexample


def exact_three(v: Vec(3)) -> float:
    if len(v) != 3:
        raise ValueError("exactly three entries")
    return float(sum(v))


def test_a_function_that_refuses_every_wrong_fixed_size_holds():
    row = _row(exact_three, "size_enforced")
    assert row.verdict == "holds", (row.verdict, row.counterexample)


_SIZES: list = []


def recording_grid(A: Mat(4, 3)) -> float:
    _SIZES.append((len(A), len(A[0]) if A else None))
    if len(A) != 4 or any(len(r) != 3 for r in A):
        raise ValueError("expected 4 by 3")
    return 0.0


def test_each_fixed_axis_is_tried_larger_smaller_and_at_zero():
    _SIZES.clear()
    row = _row(recording_grid, "size_enforced")
    assert row.verdict == "holds", (row.verdict, row.counterexample)
    rows = {r for r, c in _SIZES if c == 3}
    cols = {c for r, c in _SIZES if r == 4}
    assert {5, 3, 1} <= rows, sorted(rows)
    assert {4, 2, 1, 0} <= cols, sorted(cols)
    # a matrix with no rows has no column count to keep: never drawn
    assert (0, None) not in _SIZES, _SIZES
