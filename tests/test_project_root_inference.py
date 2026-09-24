# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""How the CLI infers a project root when `--root` is not given: the
nearest ancestor holding `.mathema/` inside the enclosing git
repository, else that repository's top level, else the working
directory. The search never leaves the git repository the working
directory is in, and the home directory is never a root merely
because user-level `~/.mathema` exists there."""
import os
import shutil
import subprocess

import pytest

from mathema.cli import _resolve_root

pytestmark = pytest.mark.skipif(shutil.which("git") is None,
                                reason="needs the git executable")


def _git_init(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True,
                   capture_output=True)
    return path


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".mathema").mkdir(parents=True)
    (home / ".mathema" / "config.json").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    return home


def _real(p):
    return os.path.realpath(str(p))


def test_git_repo_below_home_wins_over_home_store(fake_home, monkeypatch):
    repo = _git_init(fake_home / "code" / "proj")
    (repo / "pkg").mkdir()
    monkeypatch.chdir(repo / "pkg")
    assert _real(_resolve_root(None)) == _real(repo)


def test_store_above_git_repo_is_not_climbed_to(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    (outer / ".mathema").mkdir(parents=True)
    repo = _git_init(outer / "repo")
    monkeypatch.chdir(repo)
    assert _real(_resolve_root(None)) == _real(repo)


def test_store_inside_git_repo_is_found_from_a_subfolder(fake_home,
                                                         monkeypatch):
    repo = _git_init(fake_home / "proj")
    (repo / "lib" / ".mathema").mkdir(parents=True)
    (repo / "lib" / "sub").mkdir()
    monkeypatch.chdir(repo / "lib" / "sub")
    assert _real(_resolve_root(None)) == _real(repo / "lib")


def test_home_is_not_a_root_outside_any_git_repo(fake_home, monkeypatch):
    work = fake_home / "scratch" / "notes"
    work.mkdir(parents=True)
    monkeypatch.chdir(work)
    assert _real(_resolve_root(None)) == _real(work)


def test_store_outside_git_is_still_found_from_a_subfolder(fake_home,
                                                           monkeypatch):
    proj = fake_home / "proj"
    (proj / ".mathema").mkdir(parents=True)
    (proj / "sub").mkdir()
    monkeypatch.chdir(proj / "sub")
    assert _real(_resolve_root(None)) == _real(proj)


def test_explicit_root_is_verbatim(fake_home, monkeypatch):
    monkeypatch.chdir(fake_home)
    assert _resolve_root(".") == os.path.abspath(".")
