# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two parameters a claim binds to one dimension name (`xs in [-1, 1]^n,
ys in [-1, 1]^n`) have one length at every point the claim is executed
at: the corners, the degenerate containers and the admitted missing
inputs of a proof's `[float]` companion included. A point where they
differ is outside the claim's domain, so the code is never judged
there."""
import random
import re
import time
from types import SimpleNamespace
from typing import Annotated

import pytest

import mathema._timeout
from mathema import corroboration
from mathema._shapes import observed_shape
from mathema.analysis import analyze_source
from mathema.conjecture import (_admitted_container_points, check_conjectures,
                                claim)
from mathema.dimensions import (DimensionConflict, DimResolver, FixedSizeConflict,
                                ParamShape, _reconcile_dims, resolve)
from mathema.gates import _float_companion, _point_evaluator
from mathema.policy import batch
from mathema.probing import Probe
from mathema.types import Shape, shapes_from_signature


def dot(xs: list[float], ys: list[float]) -> float:
    total = 0.0
    for i in range(len(xs)):
        total += xs[i] * ys[i]
    return total


def _rows_and_calls(fn, text, **kw):
    with batch() as calls:
        rows = check_conjectures(fn, [claim(text, name="c", **kw)],
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


def test_a_dict_holding_no_table_is_measured_by_its_keys():
    resolver = DimResolver()
    assert resolver.measure({"a": 1.0, "b": 2.0, "c": 3.0}, 0) == 3
    assert resolver.measure({"a": [1.0], "b": [1.0, 2.0]}, 0) == 2
    assert resolver.measure({"x": {"y": 1.0}}, 0) == 1
    assert resolver.measure({}, 0) == 0
    with pytest.raises(IndexError):
        resolver.measure({"a": 1.0}, 1)


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


def len_minus_one(xs: list[float], ys: list[float]) -> float:
    total = 0.0
    for i in range(len(xs)):
        total += xs[i] * ys[i]
    return total / (len(xs) - 1)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("trials", [8, 12, 20])
def test_tied_vectors_reach_length_one_whatever_the_trials(trials):
    with batch():
        rows = check_conjectures(
            len_minus_one,
            [claim("for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)",
                   name="c", trials=trials)],
            float_companions=True)
    companion = next(p for p in rows if p.name == "c[float]")
    assert companion.verdict == "falsified", (companion.verdict, companion.note)
    assert re.search(r"xs = \[[^,\]]+\], ys = \[[^,\]]+\]", str(companion.counterexample)), (
        companion.counterexample)


def test_tied_keys_give_a_joint_point_at_their_least_size():
    deps, _resolver = _kit(dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)")
    assert [(len(p["xs"]), len(p["ys"])) for p in deps["evaluate"].small_points()] == [(1, 1)]
    assert all(deps["admits"](p) for p in deps["evaluate"].small_points())


def test_a_tied_matrix_reaches_one_by_one_one_by_m_and_n_by_one():
    def vector_and_matrix(w, A):
        return w[0] + A[0][0]
    deps, _resolver = _kit(
        vector_and_matrix, "for w in [-1, 1]^n, A in [-1, 1]^(n,m), f(w, A) == f(w, A)")
    shapes = [(len(p["w"]), len(p["A"]), len(p["A"][0])) for p in deps["evaluate"].small_points()]
    assert len(shapes) == 4
    assert shapes[0] == (1, 1, 1)
    assert shapes[1][:2] == (1, 1) and shapes[1][2] >= 2
    assert shapes[2][0] == shapes[2][1] >= 2 and shapes[2][2] == 1
    assert shapes[3] == (2, 2, 2)
    assert all(deps["admits"](p) for p in deps["evaluate"].small_points())


def test_a_tied_table_reaches_one_row_beside_a_vector():
    pd = pytest.importorskip("pandas")

    def table_and_vector(df: pd.DataFrame, w: list) -> float:
        return float(df["a"].sum()) + sum(w)
    deps, _resolver = _kit(table_and_vector,
                           "for df in [0, 1]^n, w in [0, 1]^n, f(df, w) >= -1")
    assert [(_rows_of(p["df"]), len(p["w"])) for p in deps["evaluate"].small_points()] == [(1, 1)]
    assert all(deps["admits"](p) for p in deps["evaluate"].small_points())


def test_a_small_point_keeps_a_premise_on_its_elements():
    def premised(xs, ys, c):
        return xs[0] + ys[0] + c
    cj = claim("for xs in [-1, 1]^n, ys in [-1, 1]^n, c in [0, 1], "
               "f(xs, ys, c) == f(xs, ys, c)", name="c")
    deps = _point_evaluator(cj, premised, analyze_source(premised), cj.domain, {},
                            assum=[("c", ">", "0.9")], sequences=True)
    assert deps["admits"]({"xs": [0.5], "ys": [0.5], "c": 0.1}) is False
    points = deps["evaluate"].small_points()
    assert points and all(deps["admits"](p) for p in points)


def test_no_small_point_where_every_size_is_fixed_or_free():
    fixed, _resolver = _kit(dot, "for xs in [-1, 1]^2, ys in [-1, 1]^2, f(xs, ys) == f(xs, ys)")
    assert fixed["evaluate"].small_points() == []
    free, _resolver = _kit(dot, "for xs in [-1, 1]^n, ys in [-1, 1]^m, f(xs, ys) == f(xs, ys)")
    assert free["evaluate"].small_points() == []


def aliased(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("k")]):
    return sum(a) + sum(b)


ALIASED = "for a in [-1, 1]^2, b in [-1, 1]^n, f(a, b) == f(a, b)"


def _floor_points(fn, text):
    cj = claim(text)
    ctx = SimpleNamespace(cj_domain=cj.domain, record_domain=cj.domain,
                          missing={}, cj=cj)
    facts = analyze_source(fn)
    resolver = resolve(facts, shapes_from_signature(fn), claim_domain=cj.domain)
    points, _holes = _admitted_container_points(ctx, facts, resolver)
    return points


def test_a_fixed_size_holds_through_an_aliased_name():
    cj = claim(ALIASED)
    resolver = resolve(analyze_source(aliased), shapes_from_signature(aliased),
                       claim_domain=cj.domain)
    assert resolver.key("a", 0) == resolver.key("b", 0) == "k"
    assert resolver.fixed["k"] == 2
    assert resolver.corner_sizes() == {"k": 2}
    assert resolver.tied_keys() == {"k"}
    assert resolver.draw_sizes(random.Random(0)) == {"k": 2}


def test_the_floor_keeps_a_fixed_size_through_an_aliased_name():
    lengths = {param: {len(value) for p, _word, value in _floor_points(aliased, ALIASED)
                       if p == param and value is not None}
               for param in ("a", "b")}
    assert lengths == {"a": {2}, "b": {2}}


def test_two_sizes_on_one_aliased_dimension_conflict():
    def three(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("k")],
              c: Annotated[list, Shape("k")]):
        return sum(a) + sum(b) + sum(c)
    cj = claim("for a in [-1, 1]^2, b in [-1, 1]^3, c in [-1, 1]^n, f(a, b, c) == 0")
    with pytest.raises(DimensionConflict):
        resolve(analyze_source(three), shapes_from_signature(three),
                claim_domain=cj.domain)


def differs_past_one(xs: list[float], ys: list[float]) -> float:
    # divides by zero once the two lengths differ by two or more
    return sum(x for x in xs) * 0.0 + 1.0 / (2 - min(abs(len(xs) - len(ys)), 2))


def plain_sums(xs: list[float], ys: list[float]) -> float:
    return sum(xs) + sum(ys)


def _companion(rows):
    return next(p for name, p in rows.items() if name.startswith("c[float"))


@pytest.mark.needs_full_proof_budget
def test_a_companion_judges_the_code_where_two_names_differ_in_length():
    rows, _calls = _rows_and_calls(
        differs_past_one,
        "for xs in [-1, 1]^n, ys in [-1, 1]^m, f(xs, ys) - f(xs, ys) == 0")
    companion = _companion(rows)
    assert companion.verdict == "falsified", (companion.verdict, companion.note)
    assert "xs = [" in str(companion.counterexample)


@pytest.mark.needs_full_proof_budget
def test_a_companion_never_runs_one_name_at_two_lengths():
    rows, _calls = _rows_and_calls(
        differs_past_one,
        "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) - f(xs, ys) == 0")
    assert _companion(rows).verdict == "holds", _companion(rows)


@pytest.mark.needs_full_proof_budget
def test_a_companion_over_two_names_is_called_at_unequal_lengths():
    rows, calls = _rows_and_calls(
        plain_sums, "for xs in [-1, 1]^n, ys in [-1, 1]^m, f(xs, ys) == f(xs, ys)")
    assert rows["c"].verdict == "proven", rows["c"]
    assert _companion(rows).verdict == "holds", _companion(rows)
    lengths = {(len(call.point["xs"]), len(call.point["ys"])) for call in calls
               if call.claim == "c[float]"
               and isinstance(call.point.get("xs"), list)
               and isinstance(call.point.get("ys"), list)}
    assert any(a != b for a, b in lengths), sorted(lengths)
    assert any(a == 1 or b == 1 for a, b in lengths), sorted(lengths)


def test_a_point_is_admitted_by_whether_its_names_agree():
    tied, _resolver = _kit(dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)")
    assert tied["admits"]({"xs": [0.5, 0.5], "ys": [0.5, 0.5]}) is True
    assert tied["admits"]({"xs": [0.5, 0.5], "ys": [0.5]}) is False
    free, _resolver = _kit(dot, "for xs in [-1, 1]^n, ys in [-1, 1]^m, f(xs, ys) == f(xs, ys)")
    assert free["admits"]({"xs": [0.5, 0.5], "ys": [0.5]}) is True


def test_agreement_is_per_name():
    _kit_, resolver = _kit(dot, "for xs in [-1, 1]^n, ys in [-1, 1]^m, f(xs, ys) == f(xs, ys)")
    assert resolver.agrees({"xs": [1.0, 2.0], "ys": [1.0]}) is True


@pytest.mark.parametrize("text,tied", [
    ("for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == 0", {"n"}),
    ("for xs in [-1, 1]^n, ys in [-1, 1]^m, f(xs, ys) == 0", set()),
    ("for xs in [-1, 1]^2, ys in [-1, 1]^m, f(xs, ys) == 0", {"2"}),
])
def test_only_a_shared_or_literal_name_is_tied(text, tied):
    cj = claim(text)
    assert resolve(analyze_source(dot), {}, claim_domain=cj.domain).tied_keys() == tied


def _lengths_by_param(points):
    out: dict = {}
    for param, _word, value in points:
        if value is not None:
            out.setdefault(param, set()).add(len(value))
    return out


def test_a_tied_vector_floor_holds_only_the_corner_length():
    lengths = _lengths_by_param(_floor_points(
        dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == 0"))
    assert lengths == {"xs": {3}, "ys": {3}}


def test_a_free_vector_floor_keeps_its_length_one_item():
    lengths = _lengths_by_param(_floor_points(
        dot, "for xs in [-1, 1]^n, ys in [-1, 1]^m, f(xs, ys) == 0"))
    assert 1 in lengths["xs"] and 1 in lengths["ys"], lengths


def test_a_matrix_floor_takes_the_row_count_its_vector_shares():
    def vector_and_matrix(w, A):
        return w[0] + A[0][0]
    lengths = _lengths_by_param(_floor_points(
        vector_and_matrix, "for w in [-1, 1]^n, A in [-1, 1]^(n,m), f(w, A) == 0"))
    assert lengths == {"w": {3}, "A": {3}}


def test_a_table_floor_takes_the_size_a_vector_fixes():
    pd = pytest.importorskip("pandas")

    def table_and_vector(df: pd.DataFrame, w: Annotated[list, Shape("n")]) -> float:
        return float(df["a"].sum()) + sum(w)
    points = _floor_points(table_and_vector,
                           "for df in [0, 1]^n, w in [0, 1]^2, f(df, w) >= -1")
    assert {_rows_of(v) for p, _w, v in points if p == "df" and v is not None} == {2}


def marked_dot(xs: Annotated[list, Shape("n")], ys: Annotated[list, Shape("n")]) -> float:
    total = 0.0
    for i in range(len(xs)):
        total += xs[i] * ys[i]
    return total


@pytest.mark.needs_full_proof_budget
def test_two_vectors_a_shape_marker_ties_agree_at_every_companion_call():
    rows, calls = _rows_and_calls(marked_dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, "
                                              "f(xs, ys) == f(xs, ys)")
    assert _companion(rows).verdict == "holds", _companion(rows)
    lengths = {(len(call.point["xs"]), len(call.point["ys"])) for call in calls
               if call.claim == "c[float]"
               and isinstance(call.point.get("xs"), list)
               and isinstance(call.point.get("ys"), list)}
    assert lengths and all(a == b for a, b in lengths), sorted(lengths)
    assert (1, 1) in lengths, sorted(lengths)


def test_a_marker_alone_ties_the_floor():
    points = _floor_points(marked_dot, "for xs in [-1, 1]^k, ys in [-1, 1]^k, f(xs, ys) == 0")
    assert _lengths_by_param(points) == {"xs": {3}, "ys": {3}}


def test_a_table_a_shape_marker_ties_is_drawn_at_the_vector_length():
    pd = pytest.importorskip("pandas")

    def marked_table(df: Annotated[pd.DataFrame, Shape("n")],
                     w: Annotated[list, Shape("n")]) -> float:
        return float(df["a"].sum()) + sum(w)
    deps, resolver = _kit(marked_table, "for w in [0, 1]^n, f(df, w) >= -1")
    assert resolver.key("df", 0) == resolver.key("w", 0) == "n"
    rng = random.Random(0)
    for _ in range(20):
        point = {name: deps["sample"](name, rng) for name in deps["names"]}
        assert _rows_of(point["df"]) == len(point["w"])


def fixed_beside_named(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("n")]):
    return sum(a) + sum(b)


FIXED = "for a in [-1, 1]^2, b in [-1, 1]^n, f(a, b) == f(a, b)"


def test_a_fixed_size_holds_at_every_corner():
    deps, resolver = _kit(fixed_beside_named, FIXED)
    assert resolver.corner_sizes() == {"n": 2}
    assert {(len(c["a"]), len(c["b"])) for c in deps["corners"]} == {(2, 2)}
    assert all(deps["admits"](c) for c in deps["corners"])


@pytest.mark.needs_full_proof_budget
def test_a_fixed_size_holds_at_every_companion_call():
    rows, calls = _rows_and_calls(fixed_beside_named, FIXED)
    assert _companion(rows).verdict == "holds", _companion(rows)
    lengths = {(len(call.point["a"]), len(call.point["b"])) for call in calls
               if call.claim == "c[float]"
               and isinstance(call.point.get("a"), list)
               and isinstance(call.point.get("b"), list)}
    assert lengths == {(2, 2)}, sorted(lengths)


@pytest.mark.needs_full_proof_budget
def test_a_contradicted_binding_still_reaches_its_companion():
    rows, _calls = _rows_and_calls(
        conflicting, "for a in [0, 1]^(n,m), b in [0, 1]^n, f(a, b) == f(a, b)")
    assert rows["c"].meta["mathema.float_companion"] == "c[float]"
    assert "c[float]" in rows


def size_of(d: dict) -> int:
    return len(d)


def test_a_dimension_read_off_a_plain_dict_is_its_key_count():
    resolver = DimResolver(shapes={"d": ParamShape(("n",))})
    env: dict = {}
    resolver.bind_env(env, {"d": {"k0": 0.0, "k1": 0.5}})
    assert env["n"] == 2


def test_the_next_anchor_binds_a_dimension_the_first_cannot_measure():
    resolver = DimResolver(shapes={"a": ParamShape(("n",)), "b": ParamShape(("n",))})
    env: dict = {}
    resolver.bind_env(env, {"a": None, "b": [1.0, 2.0, 3.0]})
    assert env["n"] == 3
    env = {}
    resolver.bind_env(env, {"b": [1.0, 2.0]})
    assert env["n"] == 2


def test_a_plain_dict_constrains_no_shared_dimension():
    resolver = DimResolver(shapes={"cfg": ParamShape(("n",)), "xs": ParamShape(("n",))})
    assert resolver.agrees({"cfg": {"k0": 0.0}, "xs": [1.0, 2.0]}) is True
    assert resolver.agrees({"cfg": {"k0": [1.0]}, "xs": [1.0, 2.0]}) is False


@pytest.mark.parametrize("text,verdict", [
    ("for d in [0, 1]^n, f(d) == n", "holds"),
    ("assuming n >= 2, for d in [0, 1]^n, f(d) >= 2", "holds"),
    ("assuming n >= 2, for d in [0, 1]^n, f(d) >= 100", "falsified"),
])
def test_a_plain_dict_binds_its_dimension_in_a_claim(text, verdict):
    rows, _calls = _rows_and_calls(size_of, text)
    assert rows["c"].verdict == verdict, (rows["c"].verdict, rows["c"].counterexample)


def marked_size_of(d: Annotated[dict, Shape("n")]) -> int:
    return len(d)


@pytest.mark.parametrize("text", ["f(d) == n", "assuming n >= 2, f(d) >= 2"])
def test_a_marked_plain_dict_binds_its_dimension_in_a_claim(text):
    rows, _calls = _rows_and_calls(marked_size_of, text)
    assert rows["c"].verdict == "holds", (rows["c"].verdict, rows["c"].counterexample)


def test_a_one_element_array_of_a_hole_has_a_shape():
    np = pytest.importorskip("numpy")
    assert observed_shape(np.array([np.nan])) == (1,)
    assert observed_shape({"a": np.array([np.nan])}) == (1,)
    assert observed_shape({"a": np.array([np.nan]), "b": np.array([0.5])}) == (1,)
    assert observed_shape(np.array(np.nan)) == ()
    assert observed_shape(float("nan")) == ()
    assert observed_shape(None) == ()


def test_a_one_element_nullable_array_of_a_hole_has_a_shape():
    pd = pytest.importorskip("pandas")
    assert observed_shape(pd.array([pd.NA], dtype="Float64")) == (1,)
    assert observed_shape({"a": pd.array([pd.NA], dtype="Float64"),
                           "b": pd.array([pd.NA], dtype="Float64")}) == (1,)
    assert observed_shape(pd.NA) == ()


def test_a_one_row_table_of_holes_binds_its_dimension():
    np = pytest.importorskip("numpy")
    resolver = DimResolver(shapes={"df": ParamShape(("n",))})
    env: dict = {"n": 9.5}
    resolver.bind_env(env, {"df": {"a": np.array([np.nan]), "b": np.array([np.nan])}})
    assert env["n"] == 1


def test_a_table_law_on_its_row_count_holds_through_a_hole():
    pd = pytest.importorskip("pandas")

    def rows_of(df: pd.DataFrame) -> float:
        return float(len(df["a"])) + 0 * len(df["b"])
    rows, _calls = _rows_and_calls(rows_of, "for df in [0, 1]^n, f(df) == n")
    assert rows["c"].verdict == "holds", (rows["c"].verdict, rows["c"].counterexample)


def _companion_lists(calls, *params):
    return [tuple(call.point[p] for p in params) for call in calls
            if str(call.claim).startswith("c[float")
            and all(isinstance(call.point.get(p), list) for p in params)]


def _all_holes(values) -> bool:
    return all(v is None or v != v for v in values)


@pytest.mark.needs_full_proof_budget
def test_an_all_hole_vector_runs_at_its_partners_length():
    _rows, calls = _rows_and_calls(
        dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)")
    lengths = {(len(xs), len(ys)) for xs, ys in _companion_lists(calls, "xs", "ys")
               if _all_holes(xs)}
    assert (3, 3) in lengths, sorted(lengths)


@pytest.mark.needs_full_proof_budget
def test_a_small_point_counts_toward_the_trials():
    rows, _calls = _rows_and_calls(
        plain_sums, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)",
        trials=20)
    assert _companion(rows).n == 20, _companion(rows).note


def test_a_small_point_the_premises_refuse_does_not_count(monkeypatch):
    swept = _swept(monkeypatch)
    _bare_companion(plain_sums, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)",
                    budget=16, assum=[("len(xs)", ">=", "2")])
    assert not [c for c in swept["corners"] if len(c["xs"]) == 1]
    assert swept["budget"] + len(swept["corners"]) == 16


def test_a_small_point_nothing_admits_is_left_out():
    deps, _resolver = _kit(dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == 0")
    assert deps["evaluate"].small_points(lambda point: False) == []


def test_two_tied_tables_with_no_vector_reach_one_row():
    pd = pytest.importorskip("pandas")

    def two_tables(a: pd.DataFrame, b: pd.DataFrame) -> float:
        return float(a["x"].sum()) + float(b["z"].sum())
    deps, _resolver = _kit(two_tables, "for a in [0, 1]^n, b in [0, 1]^n, f(a, b) >= -9")
    assert [(_rows_of(p["a"]), _rows_of(p["b"])) for p in deps["evaluate"].small_points()] \
        == [(1, 1)]


def test_a_square_matrix_floor_takes_the_size_its_vector_shares():
    def vector_and_square(w, A):
        return w[0] + A[0][0]
    points = _floor_points(vector_and_square,
                           "for w in [-1, 1]^n, A in [-1, 1]^(n,n), f(w, A) == 0")
    assert _lengths_by_param(points) == {"w": {3}, "A": {3}}


def trace_of(A) -> float:
    return sum(A[i][i] for i in range(len(A)))


def test_a_square_matrix_reaches_one_by_one_and_two_by_two_once_each():
    deps, _resolver = _kit(trace_of, "for A in [-1, 1]^(n,n), f(A) == f(A)")
    shapes = [(len(p["A"]), len(p["A"][0])) for p in deps["evaluate"].small_points()]
    assert shapes == [(1, 1), (2, 2)]


def test_a_square_matrix_runs_at_two_by_two_whatever_the_trials():
    seen = set()

    def trace_seen(A) -> float:
        seen.add((len(A), len(A[0])))
        return 0.0
    _bare_companion(trace_seen, "for A in [-1, 1]^(n,n), f(A) == f(A)", budget=6)
    assert seen >= {(1, 1), (2, 2)}, sorted(seen)


def test_a_name_a_binding_fixes_is_tied_with_one_use():
    def one(a: Annotated[list, Shape("n")]):
        return sum(a)
    cj = claim("for a in [-1, 1]^2, f(a) == 0")
    resolver = resolve(analyze_source(one), shapes_from_signature(one), claim_domain=cj.domain)
    assert resolver.tied_keys() == {"n"}


SCALED = "for xs in [-1, 1]^n, ys in [-1, 1]^n, c in [-1, 1], f(xs, ys, c) == f(xs, ys, c)"


def _bare_companion(fn, text, **kw):
    cj = claim(text, name="c")
    with batch() as calls:
        line = _float_companion(Probe("c", text, "proven"), cj, fn, analyze_source(fn),
                                cj.domain, {}, **kw)
    return line, calls.calls


def _swept(monkeypatch) -> dict:
    swept: dict = {}
    sweep = corroboration.sweep_stability

    def spy(*args, **kwargs):
        swept.update(kwargs)
        return sweep(*args, **kwargs)
    monkeypatch.setattr(corroboration, "sweep_stability", spy)
    return swept


def test_a_small_point_is_drawn_inside_what_the_companion_excludes(monkeypatch):
    swept = _swept(monkeypatch)

    def scaled(xs: list[float], ys: list[float], c: float) -> float:
        return c * dot(xs, ys)
    _bare_companion(scaled, SCALED, excluded=lambda point: point["c"] > -0.9)
    small = [c for c in swept["corners"] if len(c["xs"]) == 1 and len(c["ys"]) == 1]
    assert small and all(c["c"] <= -0.9 for c in small), small


def test_drawing_small_points_stops_at_the_wall_clock_cap(monkeypatch):
    monkeypatch.setattr(mathema._timeout, "FAST_TIMEOUT_SECONDS", 0.2)
    at_length_one = []

    def slow(xs: list[float], ys: list[float]) -> float:
        if len(xs) == 1 and len(ys) == 1:
            at_length_one.append(1)
        time.sleep(0.05)
        return 0.0
    _bare_companion(slow, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)",
                    assum=[("f(xs, ys)", ">", "1000")])
    assert len(at_length_one) < 32, len(at_length_one)


def direct_sizes(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("n")]):
    return sum(a) + sum(b)


def aliased_sizes(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("k")],
                  c: Annotated[list, Shape("k")]):
    return sum(a) + sum(b) + sum(c)


@pytest.mark.parametrize("route", ["best", "derive", "probe"])
@pytest.mark.parametrize("fn,text", [
    (direct_sizes, "for a in [-1, 1]^2, b in [-1, 1]^3, f(a, b) == f(a, b)"),
    (direct_sizes, "for a in [0, 1]^2, b in [0, 1]^3, f(a, b) < 0"),
    (aliased_sizes, "for a in [-1, 1]^2, b in [-1, 1]^3, c in [-1, 1]^n, f(a, b, c) == f(a, b, c)"),
    (aliased_sizes, "for a in [0, 1]^2, b in [0, 1]^3, c in [0, 1]^n, f(a, b, c) < 0"),
])
def test_one_dimension_fixed_to_two_sizes_is_misspecified_on_every_route(fn, text, route):
    rows, calls = _rows_and_calls(fn, text, route=route)
    assert rows["c"].verdict == "skipped:misspecified", (rows["c"].verdict, rows["c"].note)
    assert "is fixed to two sizes" in str(rows["c"].note), rows["c"].note
    assert not [name for name in rows if name.startswith("c[")], sorted(rows)
    assert not [call for call in calls if str(call.claim).startswith("c")]


def square_marked(A: Annotated[list, Shape("n", "n")]) -> float:
    return sum(sum(r) for r in A)


def square_and_vector(A: Annotated[list, Shape("n", "n")],
                      v: Annotated[list, Shape("n")]) -> float:
    return sum(sum(r) for r in A) + sum(v)


def test_two_sizes_on_one_name_inside_one_binding_conflict():
    with pytest.raises(FixedSizeConflict):
        _reconcile_dims("A", ("n", "n"), ("2", "3"))
    assert _reconcile_dims("A", ("n", "n"), ("2", "2")) == ({}, {"n": 2})
    assert _reconcile_dims("A", ("n", "m"), ("2", "3")) == ({}, {"n": 2, "m": 3})


@pytest.mark.parametrize("route", ["best", "derive", "probe"])
@pytest.mark.parametrize("fn,text", [
    (square_marked, "for A in [0, 1]^(2,3), f(A) >= 0"),
    (square_marked, "for A in [0, 1]^(2,3), f(A) < 0"),
    (square_and_vector, "for A in [0, 1]^(2,3), v in [0, 1]^2, f(A, v) >= 0"),
    (square_and_vector, "for A in [0, 1]^(3,2), v in [0, 1]^2, f(A, v) >= 0"),
])
def test_a_square_marker_fixed_to_two_sizes_is_misspecified(fn, text, route):
    rows, calls = _rows_and_calls(fn, text, route=route)
    assert rows["c"].verdict == "skipped:misspecified", (rows["c"].verdict, rows["c"].note)
    assert "is fixed to two sizes" in str(rows["c"].note), rows["c"].note
    assert not [call for call in calls if str(call.claim).startswith("c")]


def pair_marked(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("n")]) -> float:
    return sum(a) + sum(b)


@pytest.mark.parametrize("fn,text", [
    (square_marked, "for A in [0, 1]^(2,2), f(A) >= 0"),
    (pair_marked, "for a in [0, 1]^2, b in [0, 1]^2, f(a, b) >= 0"),
    (pair_marked, "for a in [0, 1]^0, b in [0, 1]^0, f(a, b) >= 0"),
    (pair_marked, "for a in [0, 1]^2, b in [0, 1]^n, f(a, b) >= 0"),
])
def test_one_size_on_one_name_is_not_misspecified(fn, text):
    rows, _calls = _rows_and_calls(fn, text)
    assert rows["c"].verdict != "skipped:misspecified", (rows["c"].verdict, rows["c"].note)
    assert "is fixed to two sizes" not in str(rows["c"].note)


def test_agreement_is_read_on_every_axis():
    resolver = DimResolver(shapes={"A": ParamShape(("n", "m")), "v": ParamShape(("m",))})
    two_by_three = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert resolver.agrees({"A": two_by_three, "v": [1.0, 2.0, 3.0]}) is True
    assert resolver.agrees({"A": two_by_three, "v": [1.0, 2.0]}) is False


def test_small_points_are_the_same_in_every_run():
    first, _resolver = _kit(dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)")
    second, _resolver = _kit(dot, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)")
    assert first["evaluate"].small_points() == second["evaluate"].small_points()
    assert first["evaluate"].small_points()


@pytest.mark.needs_full_proof_budget
def test_the_companion_note_names_its_small_points():
    rows, _calls = _rows_and_calls(
        plain_sums, "for xs in [-1, 1]^n, ys in [-1, 1]^n, f(xs, ys) == f(xs, ys)")
    assert "1 small point" in str(_companion(rows).note), _companion(rows).note


def test_a_matrix_floor_takes_the_column_size_its_vector_fixes():
    def vector_and_matrix(w: Annotated[list, Shape("n")],
                          A: Annotated[list, Shape("m", "n")]) -> float:
        return w[0] + A[0][0]
    points = _floor_points(vector_and_matrix,
                           "for w in [-1, 1]^2, A in [-1, 1]^(m,n), f(w, A) == 0")
    columns = {len(value[0]) for p, _w, value in points if p == "A" and value is not None
               and value and isinstance(value[0], list)}
    assert columns == {2}, columns


def test_a_table_at_the_wrong_row_count_is_not_admitted():
    pd = pytest.importorskip("pandas")

    def table_and_vector(df: pd.DataFrame, w: list) -> float:
        return float(df["a"].sum()) + sum(w)
    deps, _resolver = _kit(table_and_vector, "for df in [0, 1]^n, w in [0, 1]^n, f(df, w) >= -1")
    assert deps["admits"]({"df": {"a": [0.5, 0.5, 0.5]}, "w": [0.5, 0.5, 0.5]}) is True
    assert deps["admits"]({"df": {"a": [0.5, 0.5, 0.5]}, "w": [0.5, 0.5]}) is False


def test_a_dimension_is_read_off_its_first_measurable_anchor():
    resolver = DimResolver(shapes={"a": ParamShape(("n",)), "b": ParamShape(("n",))})
    env: dict = {}
    resolver.bind_env(env, {"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0]})
    assert env["n"] == 3
