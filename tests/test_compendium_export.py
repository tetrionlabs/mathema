# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Exporting a library's verified claims into a compendium SKELETON: a
transfer from the verified layer to a declared compendium pack. Verified
bound claims -> claims, verified raises(...) -> raises_when, AST-detected
nan/inf returns -> nan_when, limitations left as a TODO. A partial
skeleton, declared until a consumer verifies or trusts it."""
import ast
import textwrap

from mathema.compendium.export import (ast_nan_regions, export_compendium,
                                       write_compendium)


def _tree(src):
    return ast.parse(textwrap.dedent(src)).body[0]


def test_ast_nan_regions_reads_guarded_and_unconditional_returns():
    guarded = _tree('''
        def f(x, y):
            if y == 0:
                return float('nan')
            return x / y
    ''')
    assert ast_nan_regions(guarded) == ["y == 0"]

    unconditional = _tree('''
        def g(x):
            return float('inf')
    ''')
    assert ast_nan_regions(unconditional) == ["True"]

    clean = _tree('''
        def h(x):
            return x * 2
    ''')
    assert ast_nan_regions(clean) == []


def _seed_verified(tmp_path, key, claims):
    from mathema.spec import verified_dir, write_yaml
    import os
    os.makedirs(verified_dir(str(tmp_path)), exist_ok=True)
    write_yaml(os.path.join(verified_dir(str(tmp_path)), f"{key}.yaml"),
               {key: {"name": key.rsplit(".", 1)[-1], "claims": claims}})


def test_export_transfers_verified_claims_and_filters_pseudo_claims(tmp_path):
    _seed_verified(tmp_path, "lib.mod.f", [
        {"name": "bounded", "statement": "0 <= f(x) <= 1",
         "verdict": "holds", "route": "probe"},
        {"name": "guards", "statement": "raises(f(x), ValueError)",
         "verdict": "proven", "route": "derive", "condition": "x < 0"},
        {"name": "unknown_one", "statement": "f(x) >= 0", "verdict": "unknown"},
        {"name": "dependencies_current", "statement": "dependencies_current",
         "verdict": "proven", "route": "derive"},
    ])
    pack = export_compendium("lib", root=str(tmp_path))
    assert pack["_skeleton"] is True
    fn = pack["functions"]["lib.mod.f"]
    names = [c["name"] for c in fn.get("claims", [])]
    assert names == ["bounded"]                       # only the verified bound
    assert fn["raises_when"] == [{"condition": "x < 0", "exception": "ValueError"}]
    assert fn["limitations"] == ["TODO: review and complete this skeleton entry"]
    assert fn["provenance"] == "exported-skeleton"
    # unknown and the dependencies_current pseudo-claim are dropped
    assert "unknown_one" not in names and "dependencies_current" not in names


def test_write_compendium_marks_it_a_skeleton_and_suffixes_the_version(tmp_path):
    _seed_verified(tmp_path, "lib.mod.f", [
        {"name": "bounded", "statement": "0 <= f(x) <= 1", "verdict": "holds",
         "route": "probe"}])
    path = write_compendium("lib", root=str(tmp_path))
    text = open(path).read()
    assert "PARTIAL SKELETON" in text
    assert "DECLARED until" in text
    # a library with no importable version suffixes nothing; the file is
    # still under compendium/<library>/
    assert path.endswith(".yaml") and "/compendium/lib/" in path


def test_exported_skeleton_is_valid_yaml_with_every_header_line_commented(tmp_path):
    import yaml
    _seed_verified(tmp_path, "lib.mod.f", [
        {"name": "bounded", "statement": "0 <= f(x) <= 1", "verdict": "holds",
         "route": "probe"}])
    path = write_compendium("lib", root=str(tmp_path))
    text = open(path).read()
    header = text.split("\npackage:", 1)[0].splitlines()
    assert header and all(line.startswith("#") for line in header)
    loaded = yaml.safe_load(text)
    assert loaded["package"] == "lib"
    assert loaded["functions"]["lib.mod.f"]["provenance"] == "exported-skeleton"
