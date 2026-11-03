# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two parameters a claim binds to one dimension name (`xs in [-1, 1]^n,
ys in [-1, 1]^n`) have one length at every point the claim is executed
at: the corners, the degenerate containers and the admitted missing
inputs of a proof's `[float]` companion included. A point where they
differ is outside the claim's domain, so the code is never judged
there."""
import random
from types import SimpleNamespace
from typing import Annotated

import pytest

from mathema.analysis import analyze_source
from mathema.conjecture import (_admitted_container_points, check_conjectures,
                                claim)
from mathema.dimensions import DimResolver, ParamShape, resolve
from mathema.gates import _point_evaluator
from mathema.policy import batch
from mathema.types import Shape, shapes_from_signature


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


def _kit(fn, text):
    cj = claim(text, name="c")
    facts = analyze_source(fn)
    return (_point_evaluator(cj, fn, facts, cj.domain, {}, sequences=True),
            resolve(facts, shapes_from_signature(fn), claim_domain=cj.domain))


def _rows_of(value) -> int:
    return len(next(iter(value.values())))


def test_a_table_is_measured_by_its_rows():
    def over_table(df, w):
        return df["a"][0] + df["b"][0] + w[0]
    _kit_, resolver = _kit(over_table, "for df in [0, 1]^n, w in [0, 1]^n, f(df, w) >= -1")
    three_rows = {"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0]}
    assert resolver.measure(three_rows, 0) == 3
    assert resolver.agrees({"df": three_rows, "w": [1.0, 2.0, 3.0]}) is True
    assert resolver.agrees({"df": three_rows, "w": [1.0, 2.0]}) is False


def test_a_dict_holding_no_table_has_no_size():
    resolver = DimResolver()
    with pytest.raises(TypeError):
        resolver.measure({"a": 1.0}, 0)
    with pytest.raises(TypeError):
        resolver.measure({"a": [1.0], "b": [1.0, 2.0]}, 0)


def test_a_table_past_its_row_axis_has_no_size():
    with pytest.raises(IndexError):
        DimResolver().measure({"a": [1.0, 2.0]}, 1)


def test_a_dimension_read_off_a_table_is_its_row_count():
    resolver = DimResolver(shapes={"df": ParamShape(("n",))})
    env: dict = {}
    resolver.bind_env(env, {"df": {"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0]}})
    assert env["n"] == 3


def test_a_table_beside_a_vector_is_admitted_at_every_corner():
    pd = pytest.importorskip("pandas")

    def table_and_vector(df: pd.DataFrame, w: list) -> float:
        return float(df["a"].sum()) + float(df["b"].sum()) + sum(w)
    deps, _resolver = _kit(table_and_vector,
                           "for df in [0, 1]^n, w in [0, 1]^n, f(df, w) >= -1")
    assert deps["corners"]
    assert all(deps["admits"](corner) for corner in deps["corners"])


def test_a_table_drawn_beside_a_vector_has_the_vector_length():
    pd = pytest.importorskip("pandas")

    def table_and_vector(df: pd.DataFrame, w: list) -> float:
        return float(df["a"].sum()) + float(df["b"].sum()) + sum(w)
    deps, _resolver = _kit(table_and_vector,
                           "for df in [0, 1]^n, w in [0, 1]^n, f(df, w) >= -1")
    rng = random.Random(0)
    points = [{name: deps["sample"](name, rng) for name in deps["names"]}
              for _ in range(40)]
    assert {_rows_of(p["df"]) == len(p["w"]) for p in points} == {True}
    assert len({len(p["w"]) for p in points}) > 1


def test_a_table_at_a_literal_size_keeps_it_at_a_corner():
    pd = pytest.importorskip("pandas")

    def table_and_vector(df: pd.DataFrame, w: list) -> float:
        return float(df["a"].sum()) + sum(w)
    deps, _resolver = _kit(table_and_vector,
                           "for df in [0, 1]^2, w in [0, 1]^2, f(df, w) >= -1")
    assert {_rows_of(c["df"]) for c in deps["corners"]} == {2}
    assert all(deps["admits"](corner) for corner in deps["corners"])


@pytest.mark.needs_full_proof_budget
def test_a_companion_over_two_tables_on_one_n_finds_its_witness():
    pd = pytest.importorskip("pandas")

    def two_tables(a: pd.DataFrame, b: pd.DataFrame) -> float:
        return float(a["x"].sum()) + float(a["y"].sum()) + float(b["z"].sum())
    rows, calls = _rows_and_calls(
        two_tables,
        "for a in [-1e308, 1e308]^n, b in [-1e308, 1e308]^n, f(a, b) - f(a, b) == 0")
    assert rows["c"].verdict == "proven", rows["c"]
    companion = next(p for name, p in rows.items() if name.startswith("c[float"))
    assert companion.verdict == "falsified", (companion.verdict, companion.note)


@pytest.mark.needs_full_proof_budget
def test_two_tables_on_one_n_have_one_row_count_at_every_companion_call():
    pd = pytest.importorskip("pandas")

    def two_tables(a: pd.DataFrame, b: pd.DataFrame) -> float:
        return float(a["x"].sum()) + float(a["y"].sum()) + float(b["z"].sum())
    rows, calls = _rows_and_calls(
        two_tables, "for a in [-1, 1]^n, b in [-1, 1]^n, f(a, b) - f(a, b) == 0")
    companion = next(p for name, p in rows.items() if name.startswith("c[float"))
    assert companion.verdict == "holds", (companion.verdict, companion.note)
    lengths = {(_rows_of(call.point["a"]), _rows_of(call.point["b"])) for call in calls
               if isinstance(call.point.get("a"), dict)
               and isinstance(call.point.get("b"), dict)}
    assert lengths and all(x == y for x, y in lengths), sorted(lengths)
    assert len(lengths) > 1, sorted(lengths)
