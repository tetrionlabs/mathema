# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema compendium export` writes each row as its claims file states
it, not as the record renders it: the record spells out the resolved
domain (`for x in [-1e6, 1e6] : float|absent|missing`), which read
back as a claim admits inputs the stated row never did. The route a row
was decided by is the record's; the exported row keeps the route its
claims file asked for. A bundled file outside the installed version's
range still supplies the stated text, so the rows verified from it on an
older version export as written."""
import os
import subprocess
import sys

import pytest
import yaml

pytest.importorskip("numpy")


def _verify(root, *args):
    env = dict(os.environ, PYTHONPATH=str(root))
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--root', {str(root)!r}"
              + "".join(f", {a!r}" for a in args) + "]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=env)


def _bundled_rows(name: str) -> dict:
    from mathema.compendium import _bundled_dir
    with open(os.path.join(_bundled_dir(), "numpy", name)) as fh:
        data = yaml.safe_load(fh)
    return {(k, r["name"]): r for k, e in data.items()
            if isinstance(e, dict) for r in e.get("claims") or []}


def test_exported_rows_are_the_stated_rows(tmp_path, monkeypatch):
    import mathema.compendium as comp
    from mathema.compendium.export import export_compendium
    r = _verify(tmp_path, "mathema/compendium/numpy/bounds.claims.yaml")
    assert "numpy.abs" in r.stdout, r.stdout + r.stderr
    # bundled rows export only below the supported floor
    real = comp._installed_version
    monkeypatch.setattr(comp, "_installed_version",
                        lambda lib, aliases=(): "1.24.4" if lib == "numpy"
                        else real(lib, aliases))
    stated = _bundled_rows("bounds.claims.yaml")
    data = export_compendium("numpy", root=str(tmp_path))
    exported = {(k, row["name"]): row for k, e in data.items()
                if isinstance(e, dict) for row in e.get("claims") or []}
    assert exported, data
    for (key, name), row in exported.items():
        assert row["statement"] == stated[(key, name)]["statement"]
        assert "route" not in row


def test_rows_verified_from_a_file_outside_its_range_export_as_written(
        tmp_path):
    from mathema.compendium.export import export_compendium
    future = tmp_path / "claims" / "future.claims.yaml"
    future.parent.mkdir()
    future.write_text(
        'compendium: numpy\n'
        'versions: ">=99"\n'
        'numpy.cos:\n'
        '  claims:\n'
        '    - name: cos_within_one\n'
        '      statement: "for x in [-1, 1], -1 <= f(x) <= 1"\n')
    _verify(tmp_path, "claims/future.claims.yaml")
    rows = {r["name"]: r for r in
            export_compendium("numpy", root=str(tmp_path))["numpy.cos"][
                "claims"]}
    assert rows["cos_within_one"]["statement"] == \
        "for x in [-1, 1], -1 <= f(x) <= 1"
