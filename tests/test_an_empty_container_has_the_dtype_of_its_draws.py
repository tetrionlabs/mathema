# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An empty Series, DataFrame or ndarray realised for a float parameter
has the float dtype its non-empty draws have, on every path that builds
one: a literal `[]` in a claim, the empty-input line under a value
claim, and `is_empty_safe`. A function that answers a real empty float
Series therefore reads the same on all three."""
import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

import mathema  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.runtime_types import adapter  # noqa: E402
from mathema.runtime_types._abstract import AbstractTable, AbstractVec  # noqa: E402


def exposure(returns: pd.Series) -> float:
    held = returns[np.isfinite(returns)]
    return float((held != 0).sum() / len(held)) if len(held) else 0.0


def column_exposure(df: pd.DataFrame) -> float:
    held = df["r"][np.isfinite(df["r"])]
    return float((held != 0).sum() / len(held)) if len(held) else 0.0


def test_the_series_adapter_realises_an_empty_vector_as_a_float_series():
    s = adapter("pandas.Series").realise(AbstractVec(()), {})
    assert len(s) == 0 and s.dtype == np.float64, s.dtype


def test_the_frame_adapter_realises_zero_rows_as_float_columns():
    df = adapter("pandas.DataFrame").realise(
        AbstractTable({"r": AbstractVec(())}), {})
    assert len(df) == 0 and df["r"].dtype == np.float64, df.dtypes


def test_the_array_adapter_realises_an_empty_vector_as_a_float_array():
    a = adapter("numpy.ndarray").realise(AbstractVec(()), {})
    assert a.shape == (0,) and a.dtype == np.float64, a.dtype


def test_a_literal_empty_list_is_an_empty_float_series():
    (p,) = check_conjectures(exposure, [claim("f([]) == 0")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample, p.note)


def test_the_empty_input_line_meets_an_empty_float_series():
    rows = {p.name: p for p in mathema.check(
        exposure, claims=["for returns in R^n, 0 <= f(returns) <= 1"]).probes}
    line = rows["is_empty_safe[returns]"]
    assert line.verdict == "holds", (line.verdict, line.counterexample, line.note)
    assert "returns 0.0" in line.note, line.note


def test_every_path_reads_the_empty_series_alike():
    (direct,) = check_conjectures(exposure, [claim("is_empty_safe(returns)")])
    (literal,) = check_conjectures(exposure, [claim("f([]) == 0")])
    assert direct.verdict in ("holds", "proven"), (direct.verdict, direct.note)
    assert literal.verdict in ("holds", "proven"), (literal.verdict, literal.note)


def test_a_frames_empty_input_line_meets_float_columns():
    rows = {p.name: p for p in mathema.check(
        column_exposure, claims=["0 <= f(df) <= 1"]).probes}
    lines = [p for name, p in rows.items() if name.startswith("is_empty_safe")]
    for line in lines:
        assert line.verdict == "holds", (line.verdict, line.counterexample, line.note)
