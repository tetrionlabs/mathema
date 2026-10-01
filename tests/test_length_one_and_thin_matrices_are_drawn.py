# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`R^n` means n >= 1 and `R^(m,n)` means m, n >= 1, so a length-1
vector and a 1-by-1, 1-by-n or n-by-1 matrix are ordinary members of a
claim's domain. Each is drawn at least once per claim, and a failure
there is a failure of the claim itself: a sample standard deviation of
one element has no value, so `std(x, ddof=1) >= 0` is falsified at a
single element.
"""
from __future__ import annotations

import numpy as np

from mathema.claims import check_conjectures, claim


def sample_std(x: np.ndarray) -> float:
    return float(np.std(x, ddof=1))


def second_or(x: list) -> float:
    return x[1] if len(x) > 1 else -1.0


def needs_two_rows(A: np.ndarray) -> float:
    if A.shape[0] == 1:
        raise ValueError("one row")
    return 0.0


def needs_two_columns(A: np.ndarray) -> float:
    if A.shape[1] == 1:
        raise ValueError("one column")
    return 0.0


def needs_two_by_two(A: np.ndarray) -> float:
    if A.shape == (1, 1):
        raise ValueError("one entry")
    return 0.0


def _probe(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="probe")])
    return p


def test_a_sample_statistic_of_one_element_is_falsified():
    p = _probe(sample_std, "for x in R^n, f(x) >= 0")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("x=[") \
        and p.counterexample.count(",") == 0, p.counterexample


def test_an_unbound_list_of_one_element_is_drawn():
    p = _probe(second_or, "for x in [0, 1]^n, f(x) >= 0")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_one_row_a_one_column_and_a_one_entry_matrix_are_drawn():
    for fn in (needs_two_rows, needs_two_columns):
        p = _probe(fn, "for A in R^(m,n), f(A) == 0")
        assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    p = _probe(needs_two_by_two, "for A in R^(n,n), f(A) == 0")
    assert p.verdict == "falsified", (p.verdict, p.note)
