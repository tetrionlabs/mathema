# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A declared function whose module does not import (a library it uses
is not installed) fails its key in `mathema verify`, and the line says
why: the module and the import error, so the missing library is named
rather than left to guess."""
import textwrap


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_the_import_error_is_named(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    _write(tmp_path / "gpkg" / "__init__.py", "")
    _write(tmp_path / "gpkg" / "mod.py", '''
        import no_such_library_for_mathema as nl


        def total(x: float) -> float:
            """x through a library that is not installed."""
            return nl.f(x)
    ''')
    _write(tmp_path / "claims" / "gpkg.claims.yaml", """
        gpkg.mod.total:
          claims:
            - name: grows
              statement: 'for x in [0, 1], f(x) >= x'
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    result = verify_project(str(tmp_path))
    (line,) = [ln for ln in result.lines if "gpkg.mod.total" in ln]
    assert line.startswith("FAIL"), line
    assert "importing gpkg.mod raises ModuleNotFoundError" in line, line
    assert "no_such_library_for_mathema" in line
