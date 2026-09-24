# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema review` sees every change that alters what a record
retires or states, not only verdict flips: a restated claim, and a
discoveries/historical/superseded row dropped (the usual trace of a
merge conflict resolved to one side). An unknown base ref is a bad
argument, never an empty comparison."""
import os
import subprocess

import pytest

from mathema.review import render, review
from mathema.spec import write_yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEY = "rev.fn"


def _git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    *args], cwd=str(root), check=True, capture_output=True)


def _write(root, entry):
    write_yaml(str(root / ".mathema" / "verified" / f"{_KEY}.yaml"),
               {_KEY: entry})


def _base():
    return {"identity": {"form": "abc"},
            "claims": [{"name": "bound", "statement": "f(x) >= 0",
                        "verdict": "proven"}],
            "discoveries": [{"name": "above", "statement": "f(x) >= 1",
                             "verdict": "falsified",
                             "accepted": {"as": "discovery"}}]}


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _write(tmp_path, _base())
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_a_dropped_discovery_row_is_reported(repo):
    entry = _base()
    entry.pop("discoveries")
    _write(repo, entry)
    result = review(str(repo))
    (change,) = result["changes"]
    assert change["retired_dropped"] == ["discoveries:above"]
    assert result["summary"]["retired_dropped"] == 1
    assert "discoveries row above dropped" in render(result)


def test_a_restated_claim_is_reported(repo):
    entry = _base()
    entry["claims"][0]["statement"] = "f(x) >= -1"
    _write(repo, entry)
    result = review(str(repo))
    (change,) = result["changes"]
    assert change["restated"] == [{"claim": "bound", "from": "f(x) >= 0",
                                   "to": "f(x) >= -1"}]
    assert "bound: restated" in render(result)


def test_an_unchanged_store_still_reads_as_no_change(repo):
    result = review(str(repo))
    assert result["changes"] == []
    assert render(result).startswith("No claim changes")


def test_an_unknown_ref_is_refused(repo):
    from mathema.review import UnknownRef
    with pytest.raises(UnknownRef, match="not-a-ref"):
        review(str(repo), ref="not-a-ref")


def test_the_cli_exits_2_on_an_unknown_ref(repo):
    import sys
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['review', 'not-a-ref', '--root', {str(repo)!r}]))"],
        cwd=str(repo), capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH=REPO))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "not-a-ref" in r.stderr
    assert len(r.stderr.strip().splitlines()) == 1
    assert "Traceback" not in r.stderr


def test_head_of_a_repository_with_no_commit_is_an_empty_base(tmp_path):
    _git(tmp_path, "init", "-q")
    _write(tmp_path, _base())
    result = review(str(tmp_path))
    assert result["summary"]["added"] == 1
