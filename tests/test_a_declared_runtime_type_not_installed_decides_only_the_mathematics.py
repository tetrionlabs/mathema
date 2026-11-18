# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claims file's `runtime_types: {xs: pandas.Series}` on a machine
without pandas: the claim's mathematics is decided as usual, reading the
domain per element, and every row that would run the code on a Series
(the float companion, the empty-input line, a probe standing in for an
undecided derive) is skipped and names the library. No row passes on
lists standing in for the Series. The companion keeps the name it has
where pandas is installed."""
import warnings

import pytest

import mathema
import mathema.runtime_types as runtime_types


def _sum_builtin(xs):
    return sum(xs)


def _sum_loop(xs):
    t = 0.0
    for v in xs:
        t += v
    return t


@pytest.fixture
def no_pandas(monkeypatch):
    real = runtime_types.installed

    def installed(found):
        if "pandas" in tuple(getattr(found, "requires", ())):
            return False
        return real(found)
    monkeypatch.setattr(runtime_types, "installed", installed)


def _rows(fn, claim):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        record = mathema.check(fn, claims=[claim],
                               runtime_types={"xs": "pandas.Series"})
    return {p.name: p for p in record.probes}


def test_the_mathematics_is_proven_and_the_computation_skipped(no_pandas):
    rows = _rows(_sum_builtin, "for xs in [0, 10] : float, f(xs) >= 0")
    assert rows["f_xs_ge_0"].verdict == "proven", rows["f_xs_ge_0"]
    computation = rows["f_xs_ge_0[float, pandas.Series]"]
    assert computation.verdict == "skipped", computation
    assert "pandas.Series is not installed here" in computation.note


def test_the_empty_input_line_is_not_run_on_a_list(no_pandas):
    rows = _rows(_sum_builtin, "for xs in [0, 10] : float, f(xs) >= 0")
    line = rows["is_empty_safe[xs]"]
    assert line.verdict == "skipped", line
    assert "pandas.Series is not installed here" in line.note


def test_an_undecided_mathematics_is_not_probed_on_lists(no_pandas):
    rows = _rows(_sum_loop, "for xs in [0, 10] : float, f(xs) >= 0")
    row = rows["f_xs_ge_0"]
    assert row.verdict == "skipped", row
    assert row.counterexample is None
    assert "pandas.Series is not installed here" in row.note
