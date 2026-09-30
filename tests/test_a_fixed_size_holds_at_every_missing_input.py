# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A literal dimension in a binding (`^30`, `^(30,15)`, `^(n,15)`) is the
size of every value the claim hands the function, the degenerate
containers carrying a hole, a proof's companion and the calls a policy
row makes included: a hole changes what a slot holds, never how many
slots there are."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.policy import batch

np = pytest.importorskip("numpy")


def total(xs: list) -> float:
    return sum(xs)


def gram(A: np.ndarray) -> float:
    return float(np.trace(A @ A.T))


def _shapes(fn, text, *more):
    """The shape of every value a probe row drew, and of every argument
    at a missing input f was called with (the degenerate containers of
    the probe and of a proof's companion)."""
    with batch() as calls:
        rows = check_conjectures(fn, [claim(text, name="c"), *[claim(m) for m in more]],
                                 float_companions=True)
    shapes = set()
    for p in rows:
        drawn = (p.meta or {}).get("mathema.drawn")
        if drawn and p.route == "probe" and not (p.meta or {}).get("mathema.companion_of"):
            shapes |= {tuple(drawn["smallest"]), tuple(drawn["largest"])}
    for call in calls.calls:
        for v in call.point.values():
            if isinstance(v, (list, tuple)) or hasattr(v, "shape"):
                s = tuple(np.shape(np.asarray(v, dtype=object)))
                shapes.add(s if len(s) == 2 else (s[0], 1))
    return rows, shapes


def test_a_fixed_length_is_kept_at_every_missing_input():
    rows, shapes = _shapes(total, "for xs in [0, 1]^30, f(xs) >= 0")
    assert any(p.name == "c[float]" for p in rows), [p.name for p in rows]
    assert shapes == {(30, 1)}, sorted(shapes)


def test_a_fixed_matrix_shape_is_kept_at_every_missing_input():
    rows, shapes = _shapes(gram, "for A in [-1, 1]^(30,15), f(A) >= 0")
    assert any(p.name.startswith("c[") for p in rows), [p.name for p in rows]
    assert shapes == {(30, 15)}, sorted(shapes)


def test_a_fixed_axis_beside_a_free_one_is_kept():
    _rows, shapes = _shapes(gram, "for A in [-1, 1]^(n,15), f(A) >= 0")
    assert shapes and all(s[1] == 15 for s in shapes), sorted(shapes)


def length(xs: list) -> float:
    return float(len(xs))


def length_plus_total(xs: list) -> float:
    return float(len(xs) + sum(v for v in xs if v == v))


def test_a_policy_row_alone_calls_f_at_the_fixed_size():
    # the size reaches a policy row, which binds nothing, through the
    # function's domain: 30 holes and nothing to add give 30
    space = claim("for xs in [0, 1]^30, len(xs) == 30").domain
    (row,) = check_conjectures(length_plus_total,
                               [claim("missing(f, xs, nan) raises", name="p")],
                               domain=space)
    assert row.verdict == "falsified"
    assert row.counterexample.endswith("f returned 30.0"), row.counterexample


def test_a_policy_row_on_a_function_that_never_reads_the_hole_is_unknown():
    space = claim("for xs in [0, 1]^30, len(xs) == 30").domain
    (row,) = check_conjectures(length, [claim("missing(f, xs, nan) raises", name="p")],
                               domain=space)
    assert row.verdict == "unknown", (row.verdict, row.note)


pd = pytest.importorskip("pandas")


def col_mean(df: pd.DataFrame) -> float:
    return float(df["r"].mean())


def test_a_column_binding_bounds_the_column_it_names():
    (row,) = [p for p in check_conjectures(
        col_mean, [claim("for df.r in [0, 1]^n, 0 <= f(df) <= 1", name="c", route="probe")])
        if p.name == "c"]
    assert row.verdict == "holds", (row.verdict, row.counterexample)
