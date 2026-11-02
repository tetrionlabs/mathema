# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two parameters a claim binds to one dimension name (`xs in [-1, 1]^n,
ys in [-1, 1]^n`) have one length at every point the claim is executed
at: the corners, the degenerate containers and the admitted missing
inputs of a proof's `[float]` companion included. A point where they
differ is outside the claim's domain, so the code is never judged
there."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.policy import batch


def dot(xs: list[float], ys: list[float]) -> float:
    total = 0.0
    for i in range(len(xs)):
        total += xs[i] * ys[i]
    return total


def _rows_and_calls(fn, text):
    with batch() as calls:
        rows = check_conjectures(fn, [claim(text, name="c")],
                                 float_companions=True)
    return {p.name: p for p in rows}, calls.calls


@pytest.mark.needs_full_proof_budget
def test_two_vectors_bound_to_one_n_are_called_at_one_length():
    rows, calls = _rows_and_calls(
        dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)")
    assert rows["c"].verdict == "proven", rows["c"]
    companion = rows.get("c[float]")
    assert companion is not None, sorted(rows)
    assert companion.verdict == "holds", (companion.counterexample,
                                          companion.sketch)
    lengths = {(len(call.point["xs"]), len(call.point["ys"]))
               for call in calls
               if isinstance(call.point.get("xs"), list)
               and isinstance(call.point.get("ys"), list)}
    assert lengths and all(a == b for a, b in lengths), sorted(lengths)


@pytest.mark.needs_full_proof_budget
def test_a_vector_and_a_matrix_sharing_n_agree_on_n():
    np = pytest.importorskip("numpy")

    def gram_form(w: np.ndarray, A: np.ndarray) -> float:
        return float(w @ (A @ A.T) @ w)
    rows, calls = _rows_and_calls(
        gram_form, "for w in [-1, 1]^n, A in [-1, 1]^(n,m), f(w, A) >= 0")
    assert rows["c"].verdict == "proven", rows["c"]
    companion = next((p for name, p in rows.items()
                      if name.startswith("c[float")), None)
    assert companion is not None, sorted(rows)
    assert companion.verdict == "holds", (companion.counterexample,
                                          companion.sketch)
    sizes = {(np.shape(call.point["w"])[0], np.shape(call.point["A"])[0])
             for call in calls
             if np.ndim(call.point.get("w")) == 1
             and np.ndim(call.point.get("A")) == 2}
    assert sizes and all(a == b for a, b in sizes), sorted(sizes)


@pytest.mark.needs_full_proof_budget
def test_vectors_bound_to_different_names_keep_their_own_lengths():
    # `^n` and `^m` share nothing: a point where they differ is in the
    # domain, and the code that indexes one by the other's length is
    # judged there
    rows, _calls = _rows_and_calls(
        dot, "for xs in [-1, 1]^n, ys in [-1, 1]^m, f(xs, ys) == f(xs, ys)")
    lines = [p for p in rows.values() if p.verdict == "falsified"]
    assert lines, {n: p.verdict for n, p in rows.items()}
