# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A plain domain (a finite set or an interval with no `^n`) on a
parameter binds the value itself. Only a parameter whose annotation, or
declared runtime type, states a sequence reads the domain as the domain
of each element; a body that indexes or iterates the parameter in one
branch does not make it a sequence."""
import warnings
from collections.abc import Sequence

import pytest

import mathema
from mathema.records import pseudo_infinity_range


def _row(fn, claim, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        record = mathema.check(fn, claims=[claim], **kw)
    rows = [p for p in record.probes if " in " in (p.statement or "")
            and p.statement.startswith("for ")]
    assert len(rows) == 1, [p.statement for p in record.probes]
    return rows[0]


def _first_or_self(value):
    if isinstance(value, (tuple, list)):
        return value[0]
    return value


def _total_unannotated(xs):
    t = 0.0
    for v in xs:
        t += v
    return t


def _total_list(xs: list) -> float:
    t = 0.0
    for v in xs:
        t += v
    return t


def _total_sequence(xs: Sequence[float]) -> float:
    t = 0.0
    for v in xs:
        t += v
    return t


def test_a_number_set_on_an_unannotated_pair_or_number_draws_the_numbers():
    row = _row(pseudo_infinity_range,
               "for value in {1, 2.5, 1e300}, f(value) == (-value, value)")
    assert row.verdict in ("holds", "proven"), (row.verdict, row.counterexample,
                                                row.note)


def test_an_interval_on_an_unannotated_parameter_indexed_in_one_branch_binds_the_value():
    row = _row(_first_or_self, "for value in [1, 5], f(value) == value")
    assert row.verdict in ("holds", "proven"), (row.verdict, row.counterexample,
                                                row.note)


def test_an_unannotated_iterated_parameter_bound_to_numbers_is_called_with_numbers():
    # a number is not iterable, so the value reading raises at every draw
    row = _row(_total_unannotated, "for xs in [0, 10] : float, f(xs) >= 0")
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert "TypeError" in (row.counterexample or "") + (row.note or "")


@pytest.mark.parametrize("fn", [_total_list, _total_sequence],
                         ids=["list", "Sequence[float]"])
def test_a_parameter_annotated_as_a_sequence_reads_the_domain_per_element(fn):
    row = _row(fn, "for xs in [0, 10] : float, f(xs) >= 0")
    assert row.verdict in ("holds", "proven"), (row.verdict, row.counterexample,
                                                row.note)


def test_a_declared_runtime_type_lifts_an_unannotated_parameter():
    row = _row(_total_unannotated, "for xs in [0, 10] : float, f(xs) >= 0",
               runtime_types={"xs": "pandas.Series"})
    assert row.verdict in ("holds", "proven"), (row.verdict, row.counterexample,
                                                row.note)


def test_an_explicit_space_lifts_an_unannotated_parameter():
    row = _row(_total_unannotated, "for xs in [0, 10]^n : float, f(xs) >= 0")
    assert row.verdict in ("holds", "proven"), (row.verdict, row.counterexample,
                                                row.note)


def test_the_canonical_text_keeps_the_domain_as_written():
    row = _row(_total_list, "for xs in [0, 10] : float, f(xs) >= 0")
    assert row.statement.startswith("for xs in [0.0, 10.0] : float, "), row.statement
