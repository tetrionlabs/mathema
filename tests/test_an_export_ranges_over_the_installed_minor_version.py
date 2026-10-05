# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium export` writes the installed minor version as the
file's range (`>=1.24,<1.25` on numpy 1.24.4), since its rows were
checked against that release only. At or above the supported floor
(`compendium.SUPPORTED_FLOORS`) the bundled rows already cover the
library, so exporting them is refused with a note; a project's own rows
are still exported. A package exporting its own claims keeps its
open-ended `>=<major.minor>` range."""
import os

import pytest

from mathema.compendium.export import export_compendium


def _seed(tmp_path, key, rows):
    from mathema.spec import verified_dir, write_yaml
    os.makedirs(verified_dir(str(tmp_path)), exist_ok=True)
    write_yaml(os.path.join(verified_dir(str(tmp_path)), f"{key}.yaml"),
               {key: {"name": key.rsplit(".", 1)[-1], "claims": rows}})


def _installed(monkeypatch, versions):
    import mathema.compendium as comp
    real = comp._installed_version
    monkeypatch.setattr(comp, "_installed_version",
                        lambda lib, aliases=(): versions.get(lib)
                        or real(lib, aliases))


_TANH = [{"name": "tanh_bounded",
          "statement": "for x in [-1e6, 1e6], -1 <= f(x) <= 1",
          "verdict": "holds"},
         {"name": "tanh_own", "statement": "for x in [0, 1], f(x) <= x",
          "verdict": "holds"}]


def test_an_older_numpy_exports_its_minor_range_and_the_bundled_rows(
        tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    _installed(monkeypatch, {"numpy": "1.24.4"})
    _seed(tmp_path, "numpy.tanh", _TANH)
    notes: list = []
    data = export_compendium("numpy", str(tmp_path), notes=notes)
    assert data["versions"] == ">=1.24,<1.25"
    names = [r["name"] for r in data["numpy.tanh"]["claims"]]
    assert names == ["tanh_bounded", "tanh_own"]
    assert notes == []


def test_at_the_floor_the_bundled_rows_are_refused_with_a_note(
        tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    _installed(monkeypatch, {"numpy": "2.3.1"})
    _seed(tmp_path, "numpy.tanh", _TANH)
    notes: list = []
    data = export_compendium("numpy", str(tmp_path), notes=notes)
    assert data["versions"] == ">=2.3,<2.4"
    assert [r["name"] for r in data["numpy.tanh"]["claims"]] == ["tanh_own"]
    assert len(notes) == 1, notes
    assert notes[0].startswith("bundled rows already cover numpy 2.3")


def test_a_library_without_bundled_rows_takes_its_minor_range(
        tmp_path, monkeypatch):
    _installed(monkeypatch, {"extlib": "3.7.2"})
    _seed(tmp_path, "extlib.f", [{"name": "b", "statement": "f(x) >= 0",
                                  "verdict": "holds"}])
    assert export_compendium("extlib", str(tmp_path))["versions"] == \
        ">=3.7,<3.8"


def test_a_package_exporting_its_own_claims_keeps_an_open_range(
        tmp_path, monkeypatch):
    _installed(monkeypatch, {"mylib": "0.4.1"})
    (tmp_path / "mylib").mkdir()
    (tmp_path / "mylib" / "__init__.py").write_text("")
    _seed(tmp_path, "mylib.f", [{"name": "b", "statement": "f(x) >= 0",
                                 "verdict": "holds"}])
    assert export_compendium("mylib", str(tmp_path))["versions"] == ">=0.4"
