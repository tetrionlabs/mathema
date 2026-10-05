# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An abstract vector is a vector of numbers, so the empty one realises
as an empty polars float column, never polars' untyped `Null` column
(on which polars 1.0's `std`, `min` and `max` raise rather than give
null): the empty-input rows are then about the library's float
reductions, as they state."""
import pytest

pl = pytest.importorskip("polars")


def test_the_empty_vector_is_a_float64_series():
    from mathema.runtime_types._abstract import AbstractVec
    from mathema.runtime_types._adapters import PolarsSeriesAdapter
    s = PolarsSeriesAdapter().realise(AbstractVec(()), {})
    assert isinstance(s, pl.Series) and len(s) == 0
    assert s.dtype == pl.Float64
    assert s.std() is None and s.min() is None and s.max() is None
