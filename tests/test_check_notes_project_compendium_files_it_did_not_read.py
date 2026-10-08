# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema.check()` reads the bundled compendium only; a project's own
compendium files apply once `mathema.compendium.install(root)` has run.
When the function checked lives in a project with compendium files that
were not installed, the record says so and names the call that reads
them; once they are installed, or when the project has none, it says
nothing."""
import sys
import textwrap

import pytest

pytest.importorskip("numpy")

_NOTE = "mathema.compendium_not_read"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _project(tmp_path, monkeypatch, with_file=True):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "notedpkg"\n')
    _write(tmp_path / "notedpkg" / "__init__.py", "")
    _write(tmp_path / "notedpkg" / "mod.py", '''
        import numpy as np


        def spread(a):
            """The spread of a."""
            return np.std(a)
    ''')
    if with_file:
        _write(tmp_path / "claims" / "numpy.claims.yaml", """
            compendium: numpy
            versions: ">=2.0"
            numpy.std:
              claims:
                - name: definition
                  statement: "for a in R^n, f(a) ~= std(a, ddof=0)"
        """)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("notedpkg", "notedpkg.mod"):
        sys.modules.pop(name, None)
    from notedpkg.mod import spread
    return spread


def test_an_uninstalled_project_compendium_is_noted(tmp_path, monkeypatch):
    import mathema
    spread = _project(tmp_path, monkeypatch)
    rec = mathema.check(spread, claims=[])
    note = rec.meta.get(_NOTE)
    assert note == (f"project compendium files under {tmp_path} were not "
                    f"read; to use them, call: "
                    f"mathema.compendium.install({str(tmp_path)!r})"), note
    assert "project compendium files" in repr(rec)


def test_no_note_once_installed(tmp_path, monkeypatch):
    import mathema
    from mathema import compendium
    spread = _project(tmp_path, monkeypatch)
    compendium.install(str(tmp_path))
    try:
        assert _NOTE not in mathema.check(spread, claims=[]).meta
    finally:
        compendium.uninstall()

def test_no_note_without_project_compendium_files(tmp_path, monkeypatch):
    import mathema
    spread = _project(tmp_path, monkeypatch, with_file=False)
    assert _NOTE not in mathema.check(spread, claims=[]).meta
