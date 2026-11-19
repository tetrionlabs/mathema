# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema review` reads every verified record at the base ref with a
number of git calls that does not grow with the number of records, and
gets the same mapping a read of each file on its own gives."""
import os
import subprocess

import pytest
import yaml

from mathema import review
from mathema.review import _git, _records_at_ref


def _records_at_ref_per_file(root, ref):
    """The reading that forks one `git show` per record path."""
    listing = _git(root, "ls-tree", "-r", "--name-only", ref, "--",
                   ".mathema/verified")
    out = {}
    for path in (listing or "").splitlines():
        if not path.endswith(".yaml"):
            continue
        blob = _git(root, "show", f"{ref}:{path}")
        if blob is None:
            continue
        try:
            doc = yaml.safe_load(blob) or {}
        except Exception:
            continue
        for key, entry in doc.items():
            out[key] = entry
    return out


def _run(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True,
                   capture_output=True)


def _write(root, key, verdict):
    d = os.path.join(root, ".mathema", "verified")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{key}.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump({key: {"claims": [{"name": "c", "statement": "x",
                                          "verdict": verdict}]}}, fh,
                       allow_unicode=True)


def _repo(tmp_path, n):
    root = str(tmp_path)
    _run(root, "init", "-q")
    _run(root, "config", "user.email", "t@example.com")
    _run(root, "config", "user.name", "t")
    for i in range(n):
        _write(root, f"pkg.fn{i}", "holds")
    _write(root, "pkg.spaced name", "holds")
    _write(root, "pkg.naïve", "holds")
    with open(os.path.join(root, ".mathema", "verified", "bad.yaml"),
              "w") as fh:
        fh.write("a: [unclosed\n")
    with open(os.path.join(root, ".mathema", "verified", "notes.txt"),
              "w") as fh:
        fh.write("ignored")
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", "one")
    _write(root, "pkg.fn0", "falsified")
    _write(root, "pkg.added", "holds")
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", "two")
    return root


@pytest.mark.parametrize("ref", ["HEAD", "HEAD~1", "master", "main"])
def test_the_mapping_equals_the_per_file_reading(tmp_path, ref):
    root = _repo(tmp_path, 5)
    assert _records_at_ref(root, ref) == _records_at_ref_per_file(root, ref)


def test_the_two_commits_differ(tmp_path):
    root = _repo(tmp_path, 3)
    now, before = (_records_at_ref(root, r) for r in ("HEAD", "HEAD~1"))
    assert "pkg.added" in now and "pkg.added" not in before
    assert now["pkg.fn0"]["claims"][0]["verdict"] == "falsified"
    assert before["pkg.fn0"]["claims"][0]["verdict"] == "holds"
    assert "pkg.spaced name" in now


def test_a_bad_ref_reads_as_no_records(tmp_path):
    root = _repo(tmp_path, 2)
    assert _records_at_ref(root, "no-such-ref") == {}
    assert _records_at_ref_per_file(root, "no-such-ref") == {}


def test_a_ref_with_no_store_reads_as_no_records(tmp_path):
    root = str(tmp_path)
    _run(root, "init", "-q")
    _run(root, "config", "user.email", "t@example.com")
    _run(root, "config", "user.name", "t")
    with open(os.path.join(root, "a.txt"), "w") as fh:
        fh.write("x")
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", "x")
    assert _records_at_ref(root, "HEAD") == {}


def test_a_path_missing_at_the_ref_is_left_out(tmp_path):
    root = _repo(tmp_path, 2)
    got = review._blobs_at_ref(root, "HEAD~1",
                               [".mathema/verified/pkg.added.yaml",
                                ".mathema/verified/pkg.fn0.yaml"])
    assert list(got) == [".mathema/verified/pkg.fn0.yaml"]


def _git_calls(monkeypatch, fn):
    calls = []
    real = subprocess.run

    def spy(cmd, *a, **kw):
        calls.append(cmd)
        return real(cmd, *a, **kw)
    monkeypatch.setattr(review.subprocess, "run", spy)
    fn()
    return len(calls)


def test_git_is_called_a_fixed_number_of_times(tmp_path, monkeypatch):
    (tmp_path / "small").mkdir()
    (tmp_path / "large").mkdir()
    small = _repo(tmp_path / "small", 3)
    large = _repo(tmp_path / "large", 60)
    few = _git_calls(monkeypatch, lambda: _records_at_ref(small, "HEAD"))
    many = _git_calls(monkeypatch, lambda: _records_at_ref(large, "HEAD"))
    assert few == many
    assert many <= 3
