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
         "verdict": "holds"}])
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
