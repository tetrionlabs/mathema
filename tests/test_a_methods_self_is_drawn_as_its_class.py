# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An unbound method is called with an instance of its own class as
`self`: pandas.Series.corr is checked on two Series, never on a plain
list that has no `.corr` and raises AttributeError."""
import pytest

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.runtime_types import realised_parameters

pd = pytest.importorskip("pandas")


def test_self_of_a_series_method_is_realised_as_a_series():
    facts = analyze_source(pd.Series.corr)
    assert realised_parameters(facts)["self"].adapter == \
        realised_parameters(facts)["other"].adapter


def test_a_series_method_is_never_falsified_by_its_own_self():
    (p,) = check_conjectures(pd.Series.corr, [claim(
        "for self in R^n, other in R^n, assuming dim(self) == dim(other) "
        "and dim(self) >= 3, abs(f(self, other)) <= 1 + 1e-9",
        route="probe")])
    assert "AttributeError" not in (p.counterexample or ""), p.counterexample
    assert "AttributeError" not in (p.note or ""), p.note
