# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two parameters a claim binds to one dimension name (`xs in [-1, 1]^n,
ys in [-1, 1]^n`) have one length at every point the claim is executed
at: the corners, the degenerate containers and the admitted missing
inputs of a proof's `[float]` companion included. A point where they
differ is outside the claim's domain, so the code is never judged
there."""
from types import SimpleNamespace
from typing import Annotated

import pytest

from mathema.analysis import analyze_source
from mathema.conjecture import (_admitted_container_points, check_conjectures,
                                claim)
from mathema.dimensions import resolve
from mathema.policy import batch
from mathema.types import Shape


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


def conflicting(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("n")]):
    return sum(a) + sum(b)


def by_length(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("n")]):
    return float(len(a)) + float(len(b))


@pytest.mark.parametrize("fn,main", [(conflicting, "proven"),
                                     (by_length, "unknown")])
def test_a_binding_the_signature_contradicts_runs_to_a_verdict(fn, main):
    # the claim gives a two axes and the signature one: no resolver ties
    # the sizes, and the companion's floor is still built
    rows, _calls = _rows_and_calls(
        fn, "for a in [0, 1]^(n,m), b in [0, 1]^n, f(a, b) == f(a, b)")
    assert rows["c"].verdict == main


def test_the_companion_floor_is_built_with_no_resolver():
    cj = claim("for xs in [0, 1]^n, ys in [0, 1]^n, f(xs, ys) >= 0")
    ctx = SimpleNamespace(cj_domain=cj.domain, record_domain=cj.domain,
                          missing={}, cj=cj)
    points, _holes = _admitted_container_points(ctx, analyze_source(dot), None)
    assert {param for param, _word, _value in points} == {"xs", "ys"}


def test_an_empty_container_constrains_its_length():
    cj = claim("for xs in [0, 1]^n, ys in [0, 1]^n, f(xs, ys) >= 0")
    resolver = resolve(analyze_source(dot), {}, claim_domain=cj.domain)
    assert resolver.agrees({"xs": [], "ys": []}) is True
    assert resolver.agrees({"xs": [], "ys": [1.0]}) is False
    assert resolver.agrees({"xs": None, "ys": [1.0]}) is True
