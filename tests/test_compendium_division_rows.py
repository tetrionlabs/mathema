# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""numpy's division functions carry an `is_defined` row: division has a
value exactly where the divisor is non-zero, and the reciprocal where its
argument is. `power` and `float_power` have no single-relation region and
carry no rows."""
import inspect
import textwrap

import pytest

np = pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _rows(key):
    from mathema.compendium import compendium_functions
    return compendium_functions()[key].get("claims") or []


@pytest.mark.parametrize("key, statement", [
    ("numpy.divide", "x2 != 0"),
    ("numpy.true_divide", "x2 != 0"),
    ("numpy.reciprocal", "x != 0"),
])
def test_division_rows_state_the_non_zero_divisor(key, statement):
    (row,) = [r for r in _rows(key) if r["name"] == "is_defined"]
    assert row["statement"] == statement
    assert row.get("note"), row
    params = list(inspect.signature(getattr(np, key.split(".")[1])).parameters)
    assert statement.split(" ")[0] in params


@pytest.mark.parametrize("key", ["numpy.divide", "numpy.true_divide"])
def test_division_states_where_the_quotient_stays_in_float_range(key):
    (row,) = [r for r in _rows(key) if r["name"] == "is_overflow_safe"]
    assert row["statement"] == "abs(x1) <= 1.79769313486231e308 * abs(x2)"


@pytest.mark.parametrize("key", ["numpy.power", "numpy.float_power"])
def test_power_keeps_no_rows(key):
    assert _rows(key) == []


def test_verify_adjudicates_the_division_rows_to_holds(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path / "ratios.py", '''
        import numpy as np


        def ratio(a: float, b: float) -> float:
            """Quotient through numpy."""
            return float(np.divide(a, b))


        def ratio_true(a: float, b: float) -> float:
            """Quotient through numpy's true_divide."""
            return float(np.true_divide(a, b))


        def inverse(x: float) -> float:
            """Reciprocal through numpy."""
            return float(np.reciprocal(x))
    ''')
    _write(tmp_path / "claims" / "ratios.claims.yaml", """
        ratios.ratio:
          claims:
            - name: unit
              statement: 'for a in [1, 2], b in [1, 2], f(a, b) > 0'
        ratios.ratio_true:
          claims:
            - name: unit
              statement: 'for a in [1, 2], b in [1, 2], f(a, b) > 0'
        ratios.inverse:
          claims:
            - name: unit
              statement: 'for x in [1, 2], f(x) > 0'
    """)
    result = verify_project(str(tmp_path))
    rows = {entry["key"]: {c["claim"]: c["verdict"] for c in entry["claims"]}
            for entry in result.keys}
    for key in ("numpy.divide", "numpy.true_divide", "numpy.reciprocal"):
        assert rows[key]["is_defined"] == "holds", (key, rows[key])
    for key in ("numpy.divide", "numpy.true_divide"):
        assert rows[key]["is_overflow_safe"] == "holds", (key, rows[key])
