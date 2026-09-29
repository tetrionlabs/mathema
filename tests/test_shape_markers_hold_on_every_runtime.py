# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `Shape`, `Vec` or `Mat` marker with integers, or a binding with a
fixed dimension, is honoured on every runtime type: nested lists,
numpy, pandas, polars, and a table whose columns a vector domain
bounds. The `callable` probe builds the marker's rank, so a body that
needs a matrix is called with one."""
import importlib.util
import textwrap

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


def _load(tmp_path, name, body):
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a_matrix_marker_with_a_numpy_runtime_is_drawn_at_its_size(tmp_path):
    pytest.importorskip("numpy")
    m = _load(tmp_path, "mat_np_mod", '''
        import numpy as np

        from mathema.types import Mat

        SEEN = []


        def gram(A: Mat(30, 15, runtime="numpy.ndarray")) -> float:
            """Trace of A A^T; needs a matrix."""
            SEEN.append((type(A).__name__, tuple(np.shape(A))))
            return float(np.trace(A @ A.T))
    ''')
    rec = mathema.check(m.gram, claims=["f(A) >= 0"])
    # the battery reports the call only when it could not be made
    assert not [p.note for p in rec.probes if p.name == "callable"]
    assert set(m.SEEN) == {("ndarray", (30, 15))}, sorted(set(m.SEEN))


def test_a_matrix_marker_on_nested_lists_reaches_the_callable_probe(tmp_path):
    m = _load(tmp_path, "mat_list_mod", '''
        from mathema.types import Mat

        SEEN = []


        def diag_sum(A: Mat(30, 15)) -> float:
            """Sum of the diagonal; indexes rows and columns."""
            SEEN.append((len(A), len(A[0])))
            return float(sum(A[i][i] for i in range(15)))
    ''')
    rec = mathema.check(m.diag_sum, claims=["f(A) == f(A)"])
    # the battery reports the call only when it could not be made
    assert not [p.note for p in rec.probes if p.name == "callable"]
    assert set(m.SEEN) == {(30, 15)}, sorted(set(m.SEEN))


def test_a_vector_marker_with_a_pandas_runtime_is_drawn_at_its_length(tmp_path):
    pytest.importorskip("pandas")
    m = _load(tmp_path, "vec_pd_mod", '''
        import pandas as pd

        from mathema.types import Vec

        SEEN = []


        def total(xs: Vec(30, runtime="pandas.Series")) -> float:
            """Sum of a Series."""
            SEEN.append((type(xs).__name__, len(xs)))
            return float(xs.sum())
    ''')
    rec = mathema.check(m.total, claims=["f(xs) == f(xs)"])
    # the battery reports the call only when it could not be made
    assert not [p.note for p in rec.probes if p.name == "callable"]
    assert set(m.SEEN) == {("Series", 30)}, sorted(set(m.SEEN))


def test_a_vector_marker_with_a_polars_runtime_is_drawn_at_its_length(tmp_path):
    pytest.importorskip("polars")
    m = _load(tmp_path, "vec_pl_mod", '''
        import polars as pl

        from mathema.types import Vec

        SEEN = []


        def total(xs: Vec(30, runtime="polars.Series")) -> float:
            """Sum of a Series."""
            SEEN.append((type(xs).__name__, len(xs)))
            return float(xs.sum())
    ''')
    (p,) = check_conjectures(m.total, [claim("f(xs) == f(xs)", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert set(m.SEEN) == {("Series", 30)}, sorted(set(m.SEEN))


def test_a_fixed_length_binding_reaches_a_pandas_series_parameter(tmp_path):
    pytest.importorskip("pandas")
    m = _load(tmp_path, "series_binding_mod", '''
        import pandas as pd

        SEEN = []


        def total(xs: pd.Series) -> float:
            """Sum of a Series."""
            SEEN.append((type(xs).__name__, len(xs)))
            return float(xs.sum())
    ''')
    rec = mathema.check(m.total, claims=["for xs in [0, 1]^30, f(xs) >= 0"])
    # the battery reports the call only when it could not be made
    assert not [p.note for p in rec.probes if p.name == "callable"]
    assert set(m.SEEN) == {("Series", 30)}, sorted(set(m.SEEN))


def test_a_vector_domain_on_a_table_fixes_every_column_length(tmp_path):
    pytest.importorskip("pandas")
    m = _load(tmp_path, "table_binding_mod", '''
        import pandas as pd

        SEEN = []


        def grand_total(df: pd.DataFrame) -> float:
            """Sum of every cell."""
            SEEN.append((type(df).__name__, len(df), len(df.columns)))
            return float(df.sum().sum())
    ''')
    (p,) = check_conjectures(m.grand_total, [claim(
        "for df in [0, 1]^30, f(df) >= 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert {(t, n) for t, n, _c in m.SEEN} == {("DataFrame", 30)}, sorted(set(m.SEEN))
