# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What mathema writes for this machine alone stays out of a commit: the
scoring cache is ignored in `.mathema/.gitignore`, an existing ignore
file gains the line it lacks, and the cached warnings name files
relative to the repository root, never an absolute local path."""
import warnings


def test_a_new_store_ignores_the_cache(tmp_path):
    from mathema.cli import _scaffold_git_files
    _scaffold_git_files(str(tmp_path))
    lines = (tmp_path / ".mathema" / ".gitignore").read_text().splitlines()
    assert "/cache/" in lines


def test_an_existing_ignore_file_gains_the_cache_line(tmp_path):
    from mathema.cli import _scaffold_git_files
    gi = tmp_path / ".mathema" / ".gitignore"
    gi.parent.mkdir()
    gi.write_text("/declared/\n/issues/\nmine/\n")
    _scaffold_git_files(str(tmp_path))
    lines = gi.read_text().splitlines()
    assert lines[:3] == ["/declared/", "/issues/", "mine/"]
    assert lines.count("/cache/") == 1
    _scaffold_git_files(str(tmp_path))
    assert gi.read_text().splitlines().count("/cache/") == 1


def test_cached_warnings_name_files_relative_to_the_root(tmp_path):
    from mathema.badges import _warning_rows
    src = tmp_path / "pkg" / "mod.py"
    src.parent.mkdir()
    src.write_text("")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.warn_explicit("reads SCALE", UserWarning, str(src), 3)
    rows = _warning_rows(caught, str(tmp_path))
    assert rows[0][3] == "pkg/mod.py"
    assert str(tmp_path) not in repr(rows)
