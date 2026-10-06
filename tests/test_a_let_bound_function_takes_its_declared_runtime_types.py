# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A let-bound function receives the runtime type its own claims-file
entry declares.

`let g = qpkg.stats.avg` calls `avg`, whose parameter has no
annotation but whose entry declares `runtime_types: {returns:
pandas.Series}`. The claim passes `g` a pandas Series, as the entry
says, so `f(returns) ~= 2 * g(returns)` holds instead of falsifying on
a list that has no `.mean()`. The mean of no returns is no value, which
the entry states as its empty-input policy.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

import yaml

pytest.importorskip("pandas")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_a_let_bound_function_is_called_with_its_declared_type(tmp_path,
                                                               monkeypatch):
    from mathema import compendium
    from mathema.verify import verify_project
    _write(tmp_path / "qpkg" / "__init__.py", "")
    _write(tmp_path / "qpkg" / "stats.py", '''
        def avg(returns):
            """The mean return."""
            return returns.mean()


        def doubled_avg(returns):
            """Twice the mean return."""
            return 2 * returns.mean()
    ''')
    _write(tmp_path / "claims" / "stats.claims.yaml", """
        qpkg.stats.avg:
          runtime_types:
            returns: pandas.Series
          claims:
            - name: bounded
              statement: "for returns in [-1, 1]^n \\\\ {∅}, -1 <= f(returns) <= 1"
        qpkg.stats.doubled_avg:
          runtime_types:
            returns: pandas.Series
          claims:
            - name: twice_avg
              statement: "let g = qpkg.stats.avg, for returns in [-1, 1]^n \\\\ {∅}, f(returns) ~= 2 * g(returns)"
            - name: no_value_for_no_data
              statement: "f([]) in {missing}"
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("qpkg", "qpkg.stats"):
        sys.modules.pop(name, None)
    try:
        verify_project(str(tmp_path))
    finally:
        compendium.uninstall()
    record = yaml.safe_load((tmp_path / ".mathema" / "verified"
                             / "qpkg.stats.doubled_avg.yaml").read_text())
    rows = {c["name"]: c for c in record["qpkg.stats.doubled_avg"]["claims"]}
    row = rows["twice_avg"]
    assert row["verdict"] in ("holds", "proven"), row
