# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema verify` adjudicates every kind of bundled library row a
project's code reaches: a definition row (`numpy.sum` is `sum(a)`), a
definition row pinned to an argument (`numpy.linalg.norm` with
`ord=1`), a property row a caller may rest on (`numpy.clip` stays above
its lower bound) and a region over the complex plane (`numpy.log` has a
value everywhere but 0). Each comes out holding against the installed
numpy. The `is_defined`, `is_overflow_safe` and machine-failure
`raises` rows are covered beside the division and exponential rows."""
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_verify_adjudicates_each_kind_of_row_a_project_reaches(tmp_path,
                                                               monkeypatch):
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path / "kinds.py", '''
        import numpy as np


        def total(x: np.ndarray) -> float:
            """The sum of a vector."""
            return float(np.sum(x))


        def manhattan(x: np.ndarray) -> float:
            """The 1-norm of a vector."""
            return float(np.linalg.norm(x, ord=1))


        def unit(x: float) -> float:
            """A number clipped into [0, 1]."""
            return float(np.clip(x, 0.0, 1.0))


        def ln(x: float) -> float:
            """The natural logarithm."""
            return float(np.log(x))
    ''')
    _write(tmp_path / "claims" / "kinds.claims.yaml", """
        kinds.total:
          claims:
            - name: shifts
              statement: 'for x in [0, 1]^n, f(x) >= 0'
        kinds.manhattan:
          claims:
            - name: nonneg
              statement: 'for x in [-1, 1]^n, f(x) >= 0'
        kinds.unit:
          claims:
            - name: in_range
              statement: 'for x in [-2, 2], 0 <= f(x) <= 1'
        kinds.ln:
          claims:
            - name: positive_above_one
              statement: 'for x in [2, 3], f(x) > 0'
    """)
    result = verify_project(str(tmp_path))
    rows = {entry["key"]: {c["claim"]: c["verdict"] for c in entry["claims"]}
            for entry in result.keys}
    for key, name in [("numpy.sum", "definition"),
                      ("numpy.linalg.norm", "definition@ord=1"),
                      ("numpy.clip", "clip_lower"),
                      ("numpy.log", "is_defined_over_complex")]:
        assert rows[key][name] in ("holds", "proven"), (key, rows[key])
