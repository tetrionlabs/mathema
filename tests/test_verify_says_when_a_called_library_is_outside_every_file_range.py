# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When the project calls a library whose installed version lies outside
the range of every claims file about it (bundled or the project's),
none of those rows is used, and `mathema verify` says so once per
library: its installed version, each file's range, and where to look,
rather than adjudicating the project as if the rows applied."""
import sys
import textwrap


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_a_library_below_every_range_is_named(tmp_path, monkeypatch):
    import mathema.compendium as comp
    from mathema.verify import verify_project
    real = comp._installed_version
    monkeypatch.setattr(
        comp, "_installed_version",
        lambda lib, aliases=(): "0.9" if lib == "extlib" else real(lib, aliases))
    site = tmp_path / "site"
    _write(site / "extlib" / "__init__.py", '''
        def scaled(x: float) -> float:
            """Twice x."""
            return 2.0 * x
    ''')
    monkeypatch.syspath_prepend(str(site))
    proj = tmp_path / "proj"
    _write(proj / "upkg" / "__init__.py", "")
    _write(proj / "upkg" / "mod.py", '''
        import extlib


        def doubled(x: float) -> float:
            """Twice x, through extlib."""
            return extlib.scaled(x)
    ''')
    monkeypatch.syspath_prepend(str(proj))
    _write(proj / "claims" / "upkg.claims.yaml", """
        upkg.mod.doubled:
          claims:
            - name: grows
              statement: 'for x in [0, 10], f(x) >= x'
    """)
    _write(proj / "claims" / "extlib.claims.yaml", """
        compendium: extlib
        versions: ">=1.0,<2"
        extlib.scaled:
          claims:
            - name: grows
              statement: 'for x in [0, 10], f(x) >= x'
    """)
    sys.modules.pop("extlib", None)
    comp.uninstall()
    result = verify_project(str(proj))
    notes = [ln for ln in result.lines if ln.startswith("note extlib 0.9")]
    assert len(notes) == 1, result.lines
    assert "claims/extlib.claims.yaml (>=1.0,<2)" in notes[0]
    assert "mathema compendium status extlib" in notes[0]
