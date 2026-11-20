# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `mathema docsync` run reads each store once.

The declared and verified stores are loaded a fixed number of times per
run, however many functions it syncs, each verified record file is read
once, and the concept-curation file is parsed once. What the run writes
and prints is the same as syncing each function on its own fresh reads.

Within a run, a record or curation file written by the run is read
again afterwards, and a write outside the verified layer keeps the
shared verified view.
"""
import os
import shutil
import sys
import textwrap

import pytest

from mathema import _run_scope, concepts, spec

_PKG = "dsync_pkg"
_SMALL, _BIG = 2, 6


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _module_source(prefix: str, count: int) -> str:
    return "".join(
        f"def {prefix}{i}(x: float) -> float:\n"
        f"    \"\"\"Shifted square.\n\n"
        f"    Claims:\n"
        f"        atleast: for x in [-3, 3], f(x) >= {i}\n"
        f"    \"\"\"\n"
        f"    return x * x + {i}\n\n\n" for i in range(count))


def _claims(module: str, prefix: str, count: int) -> str:
    return "".join(
        f"{_PKG}.{module}.{prefix}{i}:\n"
        f"  claims:\n"
        f"    - name: atleast\n"
        f"      statement: 'for x in [-3, 3], f(x) >= {i}'\n"
        f"    - name: nonneg\n"
        f"      statement: 'for x in [-3, 3], f(x) >= 0'\n"
        for i in range(count))


def _purge_modules():
    for name in list(sys.modules):
        if name == _PKG or name.startswith(_PKG + "."):
            sys.modules.pop(name, None)


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    """A package of a small and a big module, each function with a
    docstring claim and two claims-file claims, a store seeded by one
    verify run, then a re-authored verified claim (a supersession), a
    claim stated two ways on two surfaces (an authoring conflict), a
    function with no claims, and a concept dismissal."""
    from mathema.verify import verify_project
    root = tmp_path_factory.mktemp("dsync_pristine")
    _write(root / _PKG / "__init__.py", "")
    _write(root / _PKG / "small.py", _module_source("s", _SMALL))
    _write(root / _PKG / "big.py", _module_source("b", _BIG) + (
        "def g(x: float) -> float:\n"
        "    \"\"\"Bounded.\n\n"
        "    Claims:\n"
        "        ub: for x in [0, 1], f(x) <= 5\n"
        "    \"\"\"\n"
        "    return x\n\n\n"
        "def h(x: float) -> float:\n"
        "    return x + 1\n"))
    _write(root / "claims" / "small.claims.yaml", _claims("small", "s", _SMALL))
    _write(root / "claims" / "big.claims.yaml", _claims("big", "b", _BIG))
    sys.path.insert(0, str(root))
    try:
        _purge_modules()
        verify_project(str(root))
    finally:
        sys.path.remove(str(root))
        _purge_modules()
    big = (root / "claims" / "big.claims.yaml").read_text()
    big = big.replace("'for x in [-3, 3], f(x) >= 0'\n",
                      "'for x in [-2, 2], f(x) >= 0'\n", 1)
    big += (f"{_PKG}.big.g:\n"
            f"  claims:\n"
            f"    - name: ub\n"
            f"      statement: 'for x in [0, 1], f(x) <= 6'\n")
    (root / "claims" / "big.claims.yaml").write_text(big)
    _write(root / ".mathema" / "meta" / "concepts.yaml",
           f"{_PKG}.big.b1:\n  concepts_dismissed: [square]\n")
    return root


@pytest.fixture()
def project(pristine, tmp_path, monkeypatch):
    root = tmp_path / "proj"
    shutil.copytree(pristine, root)
    monkeypatch.syspath_prepend(str(root))
    _purge_modules()
    yield root
    _purge_modules()


def _counting(monkeypatch, module, name, counts: dict, key):
    real = getattr(module, name)

    def wrapper(*args, **kwargs):
        k = key(*args, **kwargs)
        counts[k] = counts.get(k, 0) + 1
        return real(*args, **kwargs)
    monkeypatch.setattr(module, name, wrapper)


def _store_reads(monkeypatch, root) -> dict:
    counts: dict = {}
    _counting(monkeypatch, spec, "load_verified", counts,
              lambda *a, **k: "load_verified")
    _counting(monkeypatch, spec, "load_declared", counts,
              lambda *a, **k: "load_declared")
    _counting(monkeypatch, spec, "read_verified_file", counts,
              lambda path: os.path.basename(path))
    curation = os.path.realpath(concepts.curation_path(str(root)))
    real_open = open

    def counting_open(file, *args, **kwargs):
        if isinstance(file, (str, os.PathLike)) \
                and os.path.realpath(file) == curation:
            counts["curation"] = counts.get("curation", 0) + 1
        return real_open(file, *args, **kwargs)
    monkeypatch.setattr(concepts, "open", counting_open, raising=False)
    return counts


def _sync_counts(project, monkeypatch, targets):
    from mathema.sync import sync
    with monkeypatch.context() as m:
        counts = _store_reads(m, project)
        report = sync(targets, root=str(project))
    return counts, report


def test_store_loads_do_not_grow_with_the_functions_synced(
        project, monkeypatch):
    small, small_report = _sync_counts(project, monkeypatch,
                                       [f"{_PKG}.small"])
    big, big_report = _sync_counts(project, monkeypatch, [f"{_PKG}.big"])
    assert len(small_report.materialized) == _SMALL
    assert len(big_report.materialized) == _BIG + 2
    for kind in ("load_verified", "load_declared"):
        assert big.get(kind, 0) == small.get(kind, 0), (kind, small, big)


def test_each_record_file_and_the_curation_file_is_read_once(
        project, monkeypatch):
    counts, report = _sync_counts(project, monkeypatch, [f"{_PKG}.big"])
    assert len(report.materialized) == _BIG + 2
    records = sorted(os.listdir(project / ".mathema" / "verified"))
    assert {k: v for k, v in counts.items() if k in records} \
        == {name: 1 for name in records}, counts
    assert counts.get("curation") == 1, counts


def test_a_rootwide_run_reads_each_record_file_once(project, monkeypatch):
    counts, report = _sync_counts(project, monkeypatch, [])
    records = sorted(os.listdir(project / ".mathema" / "verified"))
    assert sorted(report.materialized) == sorted(
        [name[:-len(".yaml")] for name in records] + [f"{_PKG}.big.g"])
    assert {k: v for k, v in counts.items() if k in records} \
        == {name: 1 for name in records}, counts


def _reference_sync(targets, root=".", write_docstrings=False):
    """The docsync pass with every function synced on its own fresh
    reads of the stores, outside any run scope."""
    from mathema.audit import write_index
    from mathema.authoring import _fn_key
    from mathema.conjecture import _resolve_func_ref
    from mathema.spec import load_declared, load_verified
    from mathema.sync import (SyncReport, claim_conflicts, docstring_drift,
                              materialize_entry, write_claims_into_docstring)
    from mathema.targets import resolve
    report = SyncReport()
    declared_store = load_declared(root)
    verified_store = load_verified(root)
    functions: dict = {}
    if targets:
        for target in targets:
            functions.update(resolve(target, root).functions)
    else:
        for key in sorted(set(declared_store) | set(verified_store)):
            fn = _resolve_func_ref(key)
            if fn is not None:
                functions[key] = fn
    for key, fn in sorted(functions.items()):
        key = _fn_key(fn) if key is None else key
        file_entry = (declared_store.get(key) or {}).get("entry", {})
        v_entry = (verified_store.get(key) or {}).get("entry")
        report.conflicts.extend(
            {"key": key, **c}
            for c in claim_conflicts(fn, file_entry, v_entry)
            if c.get("kind") != "release-move")
        entry = materialize_entry(fn, key, root)
        report.materialized.append(key)
        v_entry = (verified_store.get(key) or {}).get("entry")
        for d in docstring_drift(fn, entry, v_entry):
            report.drift.append({"key": key, **d})
            if write_docstrings and d["kind"] == "missing-from-docstring":
                by_name = {c.get("name"): c for c in entry.get("claims") or []}
                pairs = [(n, (by_name.get(n) or {}).get("statement") or "")
                         for n in d["names"]]
                pairs = [(n, st) for n, st in pairs if st]
                if write_claims_into_docstring(fn, pairs):
                    report.docstrings_written.append(key)
    try:
        report.index_path = write_index(list(targets), root=root)
    except Exception:
        report.index_path = None
    return report


def _tree_bytes(root) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, root)] = fh.read()
    return out


def _cli_run(pristine, root, argv, capsys, monkeypatch, reference: bool):
    from mathema import sync as sync_module
    from mathema.cli import main
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(pristine, root)
    _purge_modules()
    with monkeypatch.context() as m:
        m.syspath_prepend(str(root))
        if reference:
            m.setattr(sync_module, "sync", _reference_sync)
        capsys.readouterr()
        code = main(argv)
        out = capsys.readouterr()
    _purge_modules()
    return code, out.out, out.err, _tree_bytes(root)


@pytest.mark.parametrize("targets", [[], [f"{_PKG}.big"],
                                     [f"{_PKG}.small", f"{_PKG}.big"]])
def test_the_run_writes_and_prints_what_fresh_reads_give(
        pristine, tmp_path, capsys, monkeypatch, targets):
    root = tmp_path / "proj"
    argv = ["docsync", *targets, "--root", str(root), "--yes",
            "--write-docstrings"]
    expected = _cli_run(pristine, root, argv, capsys, monkeypatch,
                        reference=True)
    got = _cli_run(pristine, root, argv, capsys, monkeypatch,
                   reference=False)
    assert "SUPERSESSION" in expected[1] and "CONFLICT" in expected[1]
    assert "drift" in expected[1]
    assert got[:3] == expected[:3]
    assert sorted(got[3]) == sorted(expected[3])
    for path in expected[3]:
        assert got[3][path] == expected[3][path], path


def test_sync_leaves_the_stores_it_loaded_unchanged(project, monkeypatch):
    import copy

    from mathema.sync import sync
    loaded: list = []
    for name in ("load_declared", "load_verified"):
        real = getattr(spec, name)

        def wrapper(*args, _real=real, **kwargs):
            out = _real(*args, **kwargs)
            loaded.append((out, copy.deepcopy(out)))
            return out
        monkeypatch.setattr(spec, name, wrapper)
    sync([f"{_PKG}.big"], root=str(project))
    assert loaded
    for out, before in loaded:
        assert out == before


def _verified_view_kept(root) -> bool:
    return os.path.abspath(str(root)) in (
        _run_scope.kept("verified_view") or {})


def _verified_listing_kept(root) -> bool:
    return os.path.abspath(str(root)) in (
        _run_scope.kept("verified_listing") or {})


@pytest.mark.parametrize("relpath", [
    "claims/big.claims.yaml", ".mathema/declared/dsync_pkg.big.b0.yaml",
    ".mathema/index.yaml", ".mathema/meta/concepts.yaml", "notes.yaml"])
def test_a_write_outside_the_verified_layer_keeps_the_view(project, relpath):
    with _run_scope.run_scope():
        spec._verified_view(str(project))
        assert _verified_view_kept(project)
        assert _verified_listing_kept(project)
        _run_scope.wrote(str(project / relpath))
        assert _verified_view_kept(project)
        assert _verified_listing_kept(project)


@pytest.mark.parametrize("relpath", [
    ".mathema/verified/dsync_pkg.big.b0.yaml",
    ".mathema/verified/new.key.yaml",
    ".mathema/verified/nested/dsync_pkg.big.b0.yaml"])
def test_a_write_inside_the_verified_layer_drops_the_view(project, relpath):
    with _run_scope.run_scope():
        spec._verified_view(str(project))
        _run_scope.wrote(str(project / relpath))
        assert not _verified_view_kept(project)
        assert not _verified_listing_kept(project)


def _declared_file(root, key) -> str:
    return (root / ".mathema" / "declared" / f"{key}.yaml").read_text()


def test_writes_in_a_run_are_seen_by_a_later_sync_in_it(project):
    from mathema.sync import sync
    b2, b3 = f"{_PKG}.big.b2", f"{_PKG}.big.b3"
    with _run_scope.run_scope():
        sync([f"{_PKG}.big"], root=str(project))
        assert "concepts_dismissed" not in _declared_file(project, b2)
        assert "extra" not in _declared_file(project, b3)
        spec.atomic_write_text(
            concepts.curation_path(str(project)),
            f"{_PKG}.big.b1:\n  concepts_dismissed: [square]\n"
            f"{b2}:\n  concepts_dismissed: [square]\n")
        entry = spec.load_verified(str(project))[b3]["entry"]
        entry["claims"].append({"name": "extra",
                                "statement": "for x in [-1, 1], f(x) >= 0",
                                "verdict": "holds"})
        spec.save_verified_entry(b3, entry, root=str(project))
        sync([f"{_PKG}.big"], root=str(project))
        assert "concepts_dismissed" in _declared_file(project, b2)
        assert "extra" in _declared_file(project, b3)


def test_the_curation_file_is_read_afresh_outside_a_run(project):
    assert concepts.dismissed_concepts(str(project), f"{_PKG}.big.b2") == []
    spec.atomic_write_text(
        concepts.curation_path(str(project)),
        f"{_PKG}.big.b2:\n  concepts_dismissed: [square]\n")
    assert concepts.dismissed_concepts(str(project), f"{_PKG}.big.b2") \
        == ["square"]
