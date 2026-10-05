# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library row verified on one release of the library is evidence
about that release. When the installed version moves (an upgrade, a
downgrade) the next `mathema verify` re-adjudicates the library key
against the version now installed and says why, even where the
function's own form did not change, so a row never reads "verified
locally" on the strength of a release that is no longer installed."""
import sys
import textwrap

import yaml


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_an_upgrade_re_adjudicates_the_library_key(tmp_path, monkeypatch):
    import mathema.compendium as comp
    from mathema.verify import verify_project
    version = {"extlib": "1.0"}
    real = comp._installed_version
    monkeypatch.setattr(
        comp, "_installed_version",
        lambda lib, aliases=(): version.get(lib) or real(lib, aliases))
    site = tmp_path / "site"
    _write(site / "extlib" / "__init__.py", '''
        def scaled(x: float) -> float:
            """Twice x."""
            return 2.0 * x
    ''')
    monkeypatch.syspath_prepend(str(site))
    proj = tmp_path / "proj"
    _write(proj / "claims" / "extlib.claims.yaml", """
        compendium: extlib
        versions: ">=1.0"
        extlib.scaled:
          claims:
            - name: grows
              statement: 'for x in [0, 10], f(x) >= x'
    """)

    def sweep():
        sys.modules.pop("extlib", None)
        comp.uninstall()
        return verify_project(str(proj))

    sweep()
    assert next(x for x in sweep().lines
                if "extlib.scaled" in x).startswith("ok   extlib.scaled: fresh")
    version["extlib"] = "1.1"
    line = next(x for x in sweep().lines if "extlib.scaled" in x)
    assert "library version changed (extlib-1.0 to extlib-1.1)" in line, line
    doc = yaml.safe_load((proj / ".mathema" / "verified"
                          / "extlib.scaled.yaml").read_text())
    (row,) = [c for c in doc["extlib.scaled"]["claims"]
              if c["name"] == "grows"]
    assert row["meta"]["mathema.compendium"] == "compendium:extlib-1.1"
