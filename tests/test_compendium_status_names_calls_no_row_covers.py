# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium status` names each library call that passes a
non-default argument no row speaks for (`np.var(a, ddof=3)`), with the
caller and line, and ends the line with the command that adds rows for
it; a call a row already covers is not named."""
import textwrap

import pytest

pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_an_uncovered_call_is_named_with_the_command(tmp_path, monkeypatch):
    from mathema.compendium.status import compendium_status, render_status
    _write(tmp_path / "cpkg" / "__init__.py", "")
    _write(tmp_path / "cpkg" / "mod.py", '''
        import numpy as np


        def wide(a):
            """The variance of a, three degrees of freedom removed."""
            return np.var(a, ddof=3)


        def sample(a):
            """The sample standard deviation of a."""
            return np.std(a, ddof=1)
    ''')
    _write(tmp_path / "claims" / "cpkg.claims.yaml", """
        cpkg.mod.wide:
          claims: []
        cpkg.mod.sample:
          claims: []
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    text = render_status(compendium_status(str(tmp_path)))
    lines = [ln for ln in text.splitlines() if "no row covers" in ln]
    assert len(lines) == 1, text
    assert "numpy.var ddof=3 (cpkg.mod.wide, line 7)" in lines[0]
    assert "numpy.std" not in lines[0]
    assert lines[0].rstrip().endswith("run: mathema compendium update")
