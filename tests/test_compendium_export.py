# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Exporting a library's verified claims as a compendium claims file:
the proven and held rows of every `<library>.*` key, each carrying the
verdict it reached as its claimed level, under `compendium:` and
`versions:`, written where the claims-file discovery reads it and read
back by the library loader."""
import os

from mathema.compendium.export import (default_export_path,
                                       export_compendium, write_compendium)


def _seed_verified(tmp_path, key, claims, intent=None):
    from mathema.spec import verified_dir, write_yaml
    os.makedirs(verified_dir(str(tmp_path)), exist_ok=True)
    entry = {"name": key.rsplit(".", 1)[-1], "claims": claims}
    if intent:
        entry["intent"] = intent
    write_yaml(os.path.join(verified_dir(str(tmp_path)), f"{key}.yaml"),
               {key: entry})


def test_export_keeps_the_verified_rows_and_their_levels(tmp_path):
    _seed_verified(tmp_path, "lib.mod.f", [
        {"name": "bounded", "statement": "0 <= f(x) <= 1",
         "verdict": "holds", "route": "probe"},
        {"name": "guards", "statement": "for x in [-1, 0), raises(f(x), ValueError)",
         "verdict": "proven", "route": "derive"},
        {"name": "unknown_one", "statement": "f(x) >= 0", "verdict": "unknown"},
        {"name": "dependencies_current", "statement": "dependencies_current",
         "verdict": "proven", "route": "derive"},
        {"name": "callable", "statement": "f(x) can be called",
         "verdict": "proven", "meta": {"mathema.surface": "builtin"}},
    ], intent="Squashes x into the unit interval.")
    _seed_verified(tmp_path, "other.g", [
        {"name": "b", "statement": "f(x) >= 0", "verdict": "holds"}])
    data = export_compendium("lib", root=str(tmp_path))
    assert data["compendium"] == "lib"
    # a library with no installed version ranges over every version
    assert data["versions"] == "*"
    assert set(data) == {"compendium", "versions", "lib.mod.f"}
    entry = data["lib.mod.f"]
    assert entry["intent"] == "Squashes x into the unit interval."
    assert entry["claims"] == [
        {"name": "bounded", "statement": "0 <= f(x) <= 1", "route": "probe",
         "meta": {"mathema.compendium_claimed": "holds"}},
        {"name": "guards",
         "statement": "for x in [-1, 0), raises(f(x), ValueError)",
         "route": "derive",
         "meta": {"mathema.compendium_claimed": "proven"}},
    ]


def test_an_installed_library_is_ranged_from_its_installed_version(tmp_path):
    import numpy
    _seed_verified(tmp_path, "numpy.tanh", [
        {"name": "tanh_bounded",
         "statement": "for x in [-1, 1], -1 <= f(x) <= 1",
         "verdict": "holds"}], intent="tanh(x, /, out=None) Hyperbolic "
                                      "tangent.")
    from mathema.spec import load_verified, verified_dir, write_yaml
    entry = load_verified(str(tmp_path))["numpy.tanh"]["entry"]
    entry["identity"] = {"source_available": False}
    write_yaml(os.path.join(verified_dir(str(tmp_path)), "numpy.tanh.yaml"),
               {"numpy.tanh": entry})
    # a source-less function's recorded intent is its docstring's
    # first line, which is not a statement about it worth exporting
    assert "intent" not in export_compendium("numpy", str(tmp_path))[
        "numpy.tanh"]
    major_minor = ".".join(numpy.__version__.split(".")[:2])
    assert export_compendium("numpy", str(tmp_path))["versions"] == \
        f">={major_minor}"


def test_the_written_file_is_a_claims_file_the_loader_reads(tmp_path):
    import yaml

    from mathema.compendium import load_library_claims
    from mathema.spec import validate_claims_file
    _seed_verified(tmp_path, "numpy.tanh", [
        {"name": "tanh_bounded",
         "statement": "for x in [-1, 1], -1 <= f(x) <= 1",
         "verdict": "holds"}])
    path = write_compendium("numpy", root=str(tmp_path))
    assert path == default_export_path("numpy", str(tmp_path))
    assert path == os.path.join(str(tmp_path), "claims", "numpy.claims.yaml")
    text = open(path).read()
    header = text.split("\ncompendium:", 1)[0].splitlines()
    assert header and all(line.startswith("#") for line in header)
    data = yaml.safe_load(text)
    validate_claims_file(data, "claims/numpy.claims.yaml")
    info = load_library_claims(str(tmp_path))["numpy.tanh"]
    assert info["source"] == "claims/numpy.claims.yaml"
    (row,) = info["entry"]["claims"]
    assert row["meta"]["mathema.compendium_claimed"] == "holds"


def test_export_writes_where_it_is_told(tmp_path):
    _seed_verified(tmp_path, "lib.f", [
        {"name": "b", "statement": "f(x) >= 0", "verdict": "holds"}])
    out = tmp_path / "elsewhere" / "lib.claims.yaml"
    assert write_compendium("lib", root=str(tmp_path), out=str(out)) == \
        str(out)
    assert out.exists()


def test_a_library_key_records_and_exports_the_curated_intent(tmp_path):
    # a key from a compendium file carries its curator's `intent:`, not
    # the library docstring's first line (a signature for a ufunc, a
    # paragraph for numpy.mean)
    import subprocess
    import sys
    import textwrap

    import pytest
    import yaml
    pytest.importorskip("numpy")
    (tmp_path / "qpkg").mkdir()
    (tmp_path / "qpkg" / "__init__.py").write_text("")
    (tmp_path / "qpkg" / "mod.py").write_text(textwrap.dedent('''
        import numpy as np

        def angle(x: float) -> float:
            """Arcsine through numpy."""
            return float(np.arcsin(x))

        def avg(xs: list) -> float:
            """Mean through numpy."""
            return float(np.mean(xs))
    '''))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(textwrap.dedent("""
        qpkg.mod.angle:
          claims:
            - name: bounded
              statement: 'for x in [-1, 1], -2 <= f(x) <= 2'
        qpkg.mod.avg:
          claims:
            - name: finite
              statement: 'for xs in R^n, min(xs) <= f(xs) <= max(xs)'
    """))
    env = dict(__import__("os").environ, PYTHONPATH=str(tmp_path))
    subprocess.run([sys.executable, "-c",
                    "import sys; from mathema.cli import main; "
                    f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))"],
                   capture_output=True, text=True, env=env)
    from mathema.compendium import load_library_claims
    curated = {k: load_library_claims(".")[k]["entry"]["intent"]
               for k in ("numpy.arcsin", "numpy.mean")}
    store = tmp_path / ".mathema" / "verified"
    for key, intent in curated.items():
        entry = yaml.safe_load((store / f"{key}.yaml").read_text())[key]
        assert entry["intent"] == intent
        assert entry["meta"]["mathema.intent_provenance"] == "compendium"
    data = export_compendium("numpy", root=str(tmp_path))
    for key, intent in curated.items():
        assert data[key]["intent"] == intent
