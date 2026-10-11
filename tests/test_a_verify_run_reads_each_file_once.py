# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `mathema verify` run reads what it needs once.

Each verified record file is read once per run, however many functions
the store holds, so a run on an unchanged project grows with the store
rather than with its square. The project tree is scanned for claims
files once, and the scan never enters an environment, tool or build
directory such as `.venv`. A claim stated again with the same text and
arguments is parsed once, and the library claims are read once.

Within a run, a record or claims file written by the run is read again
afterwards, so sharing never hides a write.
"""
import os
import sys
import textwrap

import pytest

from mathema import _run_scope, spec


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


_FUNCS = 4


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """A package of a few functions with one claim each, a stray claims
    file inside `.venv` and `build`, and a store seeded by one run."""
    from mathema.verify import verify_project
    body = "".join(
        f"def f{i}(x: float) -> float:\n"
        f"    \"\"\"Shifted square.\"\"\"\n"
        f"    return x * x + {i}\n\n\n" for i in range(_FUNCS))
    body += ("def g(x: float) -> float:\n"
             "    \"\"\"Calls f0.\"\"\"\n"
             "    return f0(x) + 1\n")
    _write(tmp_path / "readonce_pkg" / "__init__.py", "")
    _write(tmp_path / "readonce_pkg" / "m.py", body)
    claims = "".join(
        f"readonce_pkg.m.f{i}:\n"
        f"  claims:\n"
        f"    - name: atleast\n"
        f"      statement: 'for x in [-3, 3], f(x) >= {i}'\n"
        for i in range(_FUNCS))
    claims += ("readonce_pkg.m.g:\n"
               "  claims:\n"
               "    - name: pos\n"
               "      statement: 'for x in [-3, 3], f(x) >= 1'\n")
    _write(tmp_path / "claims" / "m.claims.yaml", claims)
    stray = "readonce_pkg.m.f0:\n  claims:\n    - statement: 'f(x) <= -1'\n"
    for skipped in (".venv/lib/site-packages/dep/claims", "build/claims"):
        _write(tmp_path / skipped / "dep.claims.yaml", stray)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("readonce_pkg", "readonce_pkg.m"):
        sys.modules.pop(name, None)
    first = verify_project(str(tmp_path))
    assert first.adjudicated == _FUNCS + 1, first.lines
    yield tmp_path
    for name in ("readonce_pkg", "readonce_pkg.m"):
        sys.modules.pop(name, None)


def _counting(monkeypatch, module, name, counts: dict, key):
    real = getattr(module, name)

    def wrapper(*args, **kwargs):
        k = key(*args, **kwargs)
        counts[k] = counts.get(k, 0) + 1
        return real(*args, **kwargs)
    monkeypatch.setattr(module, name, wrapper)


def test_an_unchanged_run_reads_each_record_file_once(project, monkeypatch):
    from mathema.verify import verify_project
    reads: dict = {}
    _counting(monkeypatch, spec, "read_verified_file", reads,
              lambda path: os.path.basename(path))
    result = verify_project(str(project))
    assert result.fresh == _FUNCS + 1 and result.adjudicated == 0, \
        result.lines
    records = sorted(os.listdir(project / ".mathema" / "verified"))
    assert sorted(reads) == records
    assert set(reads.values()) == {1}, reads


def test_the_claims_file_scan_walks_the_tree_once_and_skips_venv(
        project, monkeypatch):
    from mathema.verify import verify_project
    entered: list = []
    real_walk = os.walk

    store = os.path.realpath(project / ".mathema")

    def walk(top, *args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(top, *args, **kwargs):
            # the record store's own listing walks .mathema/verified;
            # the claims-file scan is every other walk
            if not os.path.realpath(str(top)).startswith(store):
                entered.append(dirpath)
            yield dirpath, dirnames, filenames
    monkeypatch.setattr(os, "walk", walk)
    verify_project(str(project))
    inside = [d for d in entered
              if os.path.realpath(d).startswith(
                  os.path.realpath(project) + os.sep)
              or os.path.realpath(d) == os.path.realpath(project)]
    assert inside.count(str(project)) == 1, inside
    for d in inside:
        parts = os.path.relpath(d, project).split(os.sep)
        assert not {".venv", "build", "site-packages",
                    ".mathema"} & set(parts), d


def test_each_claim_is_parsed_once_and_the_library_read_once(
        project, monkeypatch):
    from mathema import compendium, conjecture
    from mathema.verify import verify_project
    parses: dict = {}
    _counting(monkeypatch, conjecture, "_claim_parse", parses,
              lambda *a, **k: repr(a))
    library_reads: dict = {}
    _counting(monkeypatch, compendium, "_read_library_claims",
              library_reads, lambda root: root)
    verify_project(str(project))
    stated = [f"for x in [-3, 3], f(x) >= {i}" for i in range(_FUNCS)]
    for law in stated:
        same_call = {k: n for k, n in parses.items() if repr(law) in k}
        assert same_call and set(same_call.values()) == {1}, same_call
    assert set(library_reads.values()) == {1}, library_reads


def test_a_record_written_in_a_run_is_read_again(project):
    store = project / ".mathema" / "verified"
    key = "readonce_pkg.m.f1"
    with _run_scope.run_scope():
        before = spec.load_verified(str(project))[key]["entry"]
        assert spec._verified_view(str(project))[key]["entry"] == before
        changed = dict(before, intent="Changed in the run.")
        spec.save_verified_entry(key, changed, root=str(project))
        after = spec.load_verified(str(project))[key]["entry"]
        assert after["intent"] == "Changed in the run."
        assert spec._verified_view(str(project))[key]["entry"][
            "intent"] == "Changed in the run."
    assert (store / f"{key}.yaml").exists()


def test_a_copy_from_the_store_can_be_changed_freely(project):
    key = "readonce_pkg.m.f2"
    with _run_scope.run_scope():
        first = spec.load_verified(str(project))
        first[key]["entry"]["intent"] = "scribbled"
        first[key]["entry"]["claims"].clear()
        again = spec.load_verified(str(project))[key]["entry"]
        assert again["intent"] != "scribbled" and again["claims"]
        assert spec._verified_view(str(project))[key]["entry"][
            "claims"]


def test_a_claims_file_written_in_a_run_is_found(project):
    root = str(project)
    with _run_scope.run_scope():
        before = spec.claims_file_paths(root)
        spec.write_yaml(os.path.join(root, "extra.claims.yaml"),
                        {"readonce_pkg.m.f3": {"claims": [
                            {"statement": "f(x) >= 3"}]}})
        after = spec.claims_file_paths(root)
    assert os.path.join(root, "extra.claims.yaml") in after
    assert os.path.join(root, "extra.claims.yaml") not in before


def test_a_parsed_claim_can_be_changed_without_touching_the_next(project):
    from mathema.conjecture import claim
    law = "for x in [0, 1], f(x) >= 0"
    with _run_scope.run_scope():
        first = claim(law, meta={"note": ["a"]})
        first.domain.clear()
        first.meta["note"].append("b")
        first.pins.append({"args": [0.5]})
        second = claim(law, meta={"note": ["a"]})
    fresh = claim(law, meta={"note": ["a"]})
    assert second == fresh
    assert second.meta == {"note": ["a"]} and second.domain


def test_outside_a_run_nothing_is_kept():
    assert _run_scope.kept("verified_file") is None
    with _run_scope.run_scope():
        assert _run_scope.kept("verified_file") == {}
        with _run_scope.run_scope():
            _run_scope.kept("verified_file")["x"] = 1
        assert _run_scope.kept("verified_file") == {"x": 1}
    assert _run_scope.kept("verified_file") is None
