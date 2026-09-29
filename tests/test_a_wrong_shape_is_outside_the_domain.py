# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value of the wrong shape is outside a space domain: `domain_contains`
reads the rank and the fixed sizes of `R^(30,15)`, `[0, 1]^30` and
`R^(n,15)` before it reads the elements, a wrong rank counts as a wrong
shape, and a runtime type's shape is read the way its adapter reads it.
The same reading decides a claim that states the output's space
(`f(A) in R^(4,3)`) and gives the `excluded_outside_domain` probe a
wrong-shaped value to try."""
import importlib.util
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.domain import domain_contains, parse_binding


def _space(text):
    return parse_binding(text)[1]


def test_a_matrix_of_the_fixed_shape_is_inside():
    dom = _space("A in R^(30,15)")
    rows = [[0.5] * 15 for _ in range(30)]
    assert domain_contains(rows, dom)


def test_a_matrix_of_another_shape_is_outside():
    dom = _space("A in R^(30,15)")
    assert not domain_contains([[0.5] * 3 for _ in range(2)], dom)
    assert not domain_contains([[0.5] * 15 for _ in range(31)], dom)


def test_a_wrong_rank_is_a_wrong_shape():
    assert not domain_contains([0.5] * 30, _space("A in R^(30,15)"))
    assert not domain_contains([[0.5] * 30], _space("xs in [0, 1]^30"))


def test_a_vector_is_judged_by_its_length_and_its_elements():
    dom = _space("xs in [0, 1]^30")
    assert domain_contains([0.5] * 30, dom)
    assert not domain_contains([0.5] * 31, dom)
    assert not domain_contains([0.5] * 29 + [1.5], dom)


def test_a_shared_name_leaves_its_axis_free():
    dom = _space("A in R^(n,15)")
    assert domain_contains([[0.0] * 15 for _ in range(7)], dom)
    assert domain_contains([[0.0] * 15 for _ in range(2)], dom)
    assert not domain_contains([[0.0] * 14 for _ in range(7)], dom)


def test_an_element_is_still_judged_against_the_element_domain():
    # the callers that check one element at a time keep working
    dom = _space("xs in [0, 1]^30")
    assert domain_contains(0.5, dom)
    assert not domain_contains(1.5, dom)


def test_a_numpy_array_reports_its_shape_through_its_adapter():
    np = pytest.importorskip("numpy")
    dom = _space("A in R^(30,15)")
    assert domain_contains(np.zeros((30, 15)), dom)
    assert not domain_contains(np.zeros((2, 3)), dom)
    assert not domain_contains(np.zeros(30), dom)


def test_a_pandas_series_reports_its_length_through_its_adapter():
    pd = pytest.importorskip("pandas")
    dom = _space("xs in [0, 1]^30")
    assert domain_contains(pd.Series([0.5] * 30), dom)
    assert not domain_contains(pd.Series([0.5] * 8), dom)


def test_a_polars_series_reports_its_length_through_its_adapter():
    pl = pytest.importorskip("polars")
    dom = _space("xs in [0, 1]^30")
    assert domain_contains(pl.Series([0.5] * 30), dom)
    assert not domain_contains(pl.Series([0.5] * 8), dom)


_MODULE = '''
import numpy as np


def same(A: np.ndarray) -> np.ndarray:
    """The matrix itself."""
    return A


def first_row(A: np.ndarray) -> np.ndarray:
    """The first row."""
    return A[0]


def frob(A: np.ndarray) -> float:
    """Sum of squares of every entry, whatever the shape."""
    return float((A * A).sum())


def frob_checked(A: np.ndarray) -> float:
    """Sum of squares, refusing any shape but 30 by 15."""
    if A.shape != (30, 15):
        raise ValueError("expected a 30 by 15 matrix")
    return float((A * A).sum())
'''


@pytest.fixture()
def mod(tmp_path):
    pytest.importorskip("numpy")
    p = tmp_path / "wrong_shape_mod.py"
    p.write_text(textwrap.dedent(_MODULE))
    spec = importlib.util.spec_from_file_location("wrong_shape_mod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a_claim_stating_the_output_space_is_judged_by_shape(mod):
    (right,) = check_conjectures(mod.same, [claim(
        "for A in R^(3,4), f(A) in R^(3,4)", route="probe")])
    assert right.verdict == "holds", (right.verdict, right.note)
    (wrong,) = check_conjectures(mod.same, [claim(
        "for A in R^(3,4), f(A) in R^(4,3)", route="probe")])
    assert wrong.verdict == "falsified", (wrong.verdict, wrong.note)
    (row,) = check_conjectures(mod.first_row, [claim(
        "for A in R^(3,4), f(A) in R^4", route="probe")])
    assert row.verdict == "holds", (row.verdict, row.note)
    (row_wrong,) = check_conjectures(mod.first_row, [claim(
        "for A in R^(3,4), f(A) in R^3", route="probe")])
    assert row_wrong.verdict == "falsified", (row_wrong.verdict, row_wrong.note)


def test_a_number_is_not_a_member_of_a_matrix_space(mod):
    (p,) = check_conjectures(mod.frob, [claim(
        "for A in R^(3,4), f(A) in R^(3,4)", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_exclusion_probe_tries_a_wrong_shape(mod):
    (accepting,) = check_conjectures(mod.frob, [claim(
        "for A in R^(30,15), excluded_outside_domain(A)", route="best")])
    assert accepting.verdict == "falsified", (accepting.verdict, accepting.note)
    assert "shape" in (accepting.counterexample or ""), accepting.counterexample
    assert "R^(30,15)" in (accepting.counterexample or ""), accepting.counterexample
    (refusing,) = check_conjectures(mod.frob_checked, [claim(
        "for A in R^(30,15), excluded_outside_domain(A)", route="best")])
    assert refusing.verdict == "holds", (refusing.verdict, refusing.note)
