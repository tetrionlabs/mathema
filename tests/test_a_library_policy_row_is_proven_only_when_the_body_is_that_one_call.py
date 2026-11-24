# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A missing-value policy row a function inherits from a library
function's own row is `proven` only when the function's body is read as
handing the parameter to that library call on every path: the body, a
docstring and an `import` of the called module aside, is the one
statement `return <library call>`, the call takes the bare parameter,
and nothing wraps the call's result. Any
other body that reaches the same call (a guard before it, a statement
before it, a conversion around it) has the row at `holds`: the calls
made agreed with the library's row, and a path no call took is not
covered. The gate `is_missing_safe(f)` reads the same level.
"""
from __future__ import annotations

import math

import pytest

import mathema


def narrow_raise(x: float, y: float) -> float:
    if x != x and 0.6180 < y < 0.6181:
        raise ValueError("narrow")
    return math.sqrt(x)


def one_call(x):
    return math.sqrt(x)


def one_call_documented(x: float) -> float:
    """The square root of x."""
    return math.sqrt(x)


def imports_the_module_first(x: float) -> float:
    """The square root of x."""
    import math
    return math.sqrt(x)


def imports_another_name_first(x: float) -> float:
    import cmath as math  # noqa: F811
    return math.sqrt(x)


def guard_on_another_parameter(x: float, y: float) -> float:
    if y > 0.5:
        raise ValueError("y is too large")
    return math.sqrt(x)


def converted_result(x: float) -> float:
    return float(math.sqrt(x))


def statement_before(x: float, y: float) -> float:
    scale = 1 / (y - 0.61805)
    del scale
    return math.sqrt(x)


def _rows(fn, law):
    return {p.name: p for p in mathema.check(fn, claims=[
        mathema.claim(law, name="c"),
        mathema.claim("is_missing_safe(f)")]).probes}


def _reason(row) -> str:
    return row.meta["mathema.policy"]["reason"]


ONE = "for x in [0, 1], f(x) >= 0"
TWO = "for x in [0, 1], y in [0, 1], f(x, y) >= 0"


def test_the_narrow_raise_is_real():
    with pytest.raises(ValueError):
        narrow_raise(math.nan, 0.61805)
    assert math.isnan(narrow_raise(math.nan, 0.5))


def test_a_guard_before_the_call_leaves_the_row_at_holds():
    row = _rows(narrow_raise, TWO)["missing[x]"]
    assert row.statement == "missing(f, x) propagates"
    assert row.verdict == "holds", (row.verdict, row.note)
    assert row.route == "probe:counterfactual"
    assert "from math.sqrt's own policy row, which f calls; confirmed on the" \
        in _reason(row)
    assert "a path no call took is not covered" in _reason(row)


def test_the_one_call_body_stays_proven():
    rows = _rows(one_call, ONE)
    for name in ("missing[x]", "absent[x]"):
        assert rows[name].verdict == "proven", (name, rows[name].verdict)
        assert rows[name].route == "examine"
        assert "a path no call took" not in _reason(rows[name])
    assert rows["is_missing_safe[f]"].verdict == "proven"
    assert rows["is_missing_safe[f]"].route == "examine"


def test_a_docstring_and_annotations_keep_the_row_proven():
    rows = _rows(one_call_documented, ONE)
    assert rows["missing[x]"].verdict == "proven"
    assert rows["is_missing_safe[f]"].verdict == "proven"


def test_an_import_of_the_called_module_before_the_call_keeps_the_row_proven():
    rows = _rows(imports_the_module_first, ONE)
    assert rows["missing[x]"].verdict == "proven"
    assert rows["is_missing_safe[f]"].verdict == "proven"


def test_an_import_under_another_name_is_not_that_reading():
    rows = _rows(imports_another_name_first, ONE)
    assert not any(
        p.verdict == "proven" and "math.sqrt's own policy row" in
        (((p.meta or {}).get("mathema.policy") or {}).get("reason") or "")
        for p in rows.values()), [(p.name, p.verdict) for p in rows.values()]


def test_a_method_call_on_the_parameter_stays_proven():
    pd = pytest.importorskip("pandas")

    def series_mean(xs: pd.Series) -> float:
        return xs.mean()

    rows = _rows(series_mean, "for xs in [-1, 1]^n, -1 <= f(xs) <= 1")
    library = [p for p in rows.values()
               if "pandas.Series.mean's own policy row" in
               (((p.meta or {}).get("mathema.policy") or {}).get("reason") or "")]
    assert len(library) == 2, sorted(rows)
    assert all(p.verdict == "proven" for p in library), \
        [(p.name, p.verdict) for p in library]
    assert rows["is_missing_safe[f]"].verdict == "proven"


@pytest.mark.parametrize("fn, law", [
    (guard_on_another_parameter, "for x in [0, 1], y in [0, 0.4], f(x, y) >= 0"),
    (statement_before, TWO),
])
def test_a_statement_before_the_call_leaves_the_row_at_holds(fn, law):
    # at y > 0.5 the guard raises whatever x is; at y = 0.61805 the
    # division raises: a missing x does not propagate on those paths
    row = _rows(fn, law)["missing[x]"]
    assert row.verdict == "holds", (row.verdict, row.note)
    assert "math.sqrt's own policy row" in _reason(row)


def test_a_conversion_around_the_call_leaves_the_row_at_holds():
    row = _rows(converted_result, ONE)["missing[x]"]
    assert row.verdict == "holds", (row.verdict, row.note)
    assert "math.sqrt's own policy row" in _reason(row)


def test_the_gate_is_no_higher_than_the_row_it_reads():
    assert _rows(converted_result, ONE)["is_missing_safe[f]"].verdict == "holds"
    gate = _rows(narrow_raise, TWO)["is_missing_safe[f]"]
    assert gate.verdict != "proven"
    assert "from math.sqrt's own policy row, confirmed at the points tried" \
        in gate.note


def test_a_guard_that_decides_the_missing_value_takes_the_row_from_the_library():
    def refuses(x: float) -> float:
        if x != x:
            raise ValueError("no value")
        return math.sqrt(x)

    rows = _rows(refuses, ONE)
    assert not any(
        p.verdict == "proven" and "math.sqrt's own policy row" in
        (((p.meta or {}).get("mathema.policy") or {}).get("reason") or "")
        for p in rows.values()), [(p.name, p.verdict) for p in rows.values()]


def early_return(x: float, y: float) -> float:
    if y > 2:
        return 0.0
    return math.sqrt(x)


def call_in_a_try(x: float) -> float:
    try:
        return math.sqrt(x)
    except ValueError:
        return 0.0


def parameter_rebound(x: float) -> float:
    x = x + 0
    return math.sqrt(x)


def call_in_a_conditional(x: float, y: float) -> float:
    return math.sqrt(x) if y < 2 else 0.0


def two_library_calls(x: float, y: float) -> float:
    return math.sqrt(x) + math.sqrt(y)


def call_of_a_call(x: float) -> float:
    return math.sqrt(math.sqrt(x))


def library_call_without_a_row(x: float) -> float:
    return math.exp(x)


@pytest.mark.parametrize("fn", [
    early_return, call_in_a_try, parameter_rebound, call_in_a_conditional,
    two_library_calls, call_of_a_call, library_call_without_a_row,
])
def test_a_body_that_is_more_than_the_one_call_proves_no_library_row(fn):
    law = TWO if fn.__code__.co_argcount == 2 else ONE
    rows = _rows(fn, law)
    assert not any(
        p.verdict == "proven" for p in rows.values()
        if p.name.startswith(("missing[", "absent[", "is_missing_safe["))), \
        [(p.name, p.verdict) for p in rows.values()]


def test_a_stated_row_beside_a_library_row_leaves_the_gate_at_holds():
    # the gate reads the library's row for the premise no claim states:
    # a guard on another parameter before the call caps it as it caps
    # the row itself
    pd = pytest.importorskip("pandas")

    def guarded_mean(xs: pd.Series, k: int) -> float:
        if k > 5:
            raise ValueError("k is too large")
        return xs.mean()

    def plain_mean(xs: pd.Series) -> float:
        return xs.mean()

    stated = "assuming count(xs) >= 1, missing(f, xs) drops"
    for fn, law, want in [
            (guarded_mean, "for xs in [-1, 1]^n, k in {0, 1, 2}, "
                           "-1 <= f(xs, k) <= 1", "holds"),
            (plain_mean, "for xs in [-1, 1]^n, -1 <= f(xs) <= 1", "proven")]:
        rows = {p.name: p for p in mathema.check(fn, claims=[
            mathema.claim(law, name="c"), mathema.claim(stated, name="d"),
            mathema.claim("is_missing_safe(f)")]).probes}
        assert rows["missing[xs, count == 0]"].verdict == want
        gate = rows["is_missing_safe[f]"]
        assert gate.verdict == want, (fn.__name__, gate.verdict, gate.note)
        assert ("confirmed at the points tried" in gate.note) == (want == "holds")
