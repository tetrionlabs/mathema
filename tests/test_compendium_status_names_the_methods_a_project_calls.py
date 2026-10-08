# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium status` counts a method called on a value with a
runtime type (`s.mean()` on a `pandas.Series` parameter is
`pandas.Series.mean`) like a function called through an import alias,
so a library the project reaches only through methods is reported, the
same library keys `mathema verify` adjudicates."""
import textwrap

import pytest

pytest.importorskip("pandas")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_a_series_method_counts_as_a_call_into_pandas(tmp_path, monkeypatch):
    from mathema.compendium.status import compendium_status
    _write(tmp_path / "mpkg" / "__init__.py", "")
    _write(tmp_path / "mpkg" / "series.py", '''
        import pandas as pd


        def average(s: pd.Series) -> float:
            """The mean of s."""
            return float(s.mean())
    ''')
    _write(tmp_path / "claims" / "mpkg.claims.yaml", """
        mpkg.series.average:
          claims: []
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    data = compendium_status(str(tmp_path))
    libraries = {lib["library"]: lib for lib in data["libraries"]}
    assert "pandas" in libraries, data
    assert "pandas.Series.mean" in libraries["pandas"]["functions"]
