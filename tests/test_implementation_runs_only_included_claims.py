# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Implementation coverage runs a function only through the claims
included for it. A function nobody wrote a claim for is never called
while it is scored: its lines come from the tests alone, and code with
effects (writing a file, removing a directory) is left alone."""
import textwrap

from mathema.impl_coverage import function_coverage


def _load(tmp_path, body: str, name: str):
    import importlib.util

    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_function_with_no_claims_is_never_called_while_scored(tmp_path):
    mod = _load(tmp_path, '''
        CALLS = []

        def note(x: float) -> float:
            """Record x and return it."""
            CALLS.append(x)
            return x
    ''', name="unclaimed_effect")
    fc = function_coverage(mod.note, root=str(tmp_path), coverage_data={})
    assert mod.CALLS == []
    assert "probe" not in fc.by_source
    assert fc.covered == set()


def test_a_function_with_an_included_claim_is_probed_through_it(tmp_path):
    mod = _load(tmp_path, '''
        CALLS = []

        def note(x: float) -> float:
            """Record x and return it.

            Claims:
                same: f(x) == x
            """
            CALLS.append(x)
            return x
    ''', name="claimed_effect")
    fc = function_coverage(mod.note, root=str(tmp_path), coverage_data={})
    assert mod.CALLS
    assert "probe" in fc.by_source


def test_scoring_a_repository_leaves_its_files_alone(tmp_path, monkeypatch):
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "file.txt").write_text("x")
    for name in ("a", "abc", "0"):
        (tmp_path / name).mkdir()
    (tmp_path / "effects_demo.py").write_text(textwrap.dedent('''
        import os
        import shutil


        def save_note(name: str, text: str) -> str:
            """Write text to notes/<name> and return the path."""
            os.makedirs("notes", exist_ok=True)
            path = os.path.join("notes", name)
            with open(path, "w") as fh:
                fh.write(text)
            return path


        def clear_dir(path: str) -> None:
            """Remove the directory at path when it exists."""
            if os.path.isdir(path) and path not in (".", "/", ""):
                shutil.rmtree(path)
    '''))
    monkeypatch.chdir(tmp_path)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")
                    if ".mathema" not in p.parts and "__pycache__" not in p.parts)
    from mathema.badges import repo_badges
    repo_badges(["effects_demo"], root=str(tmp_path), cache=False)
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")
                   if ".mathema" not in p.parts and "__pycache__" not in p.parts)
    assert after == before
