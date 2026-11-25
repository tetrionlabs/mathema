# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record written by a build that already carried reasoning version 2
but stored a claim naming a missing value under the text of the plain
interval is moved by its stored text, whatever its reasoning version:
the claim is checked again as written, re-recorded with the note once,
and fresh on the next run. The record is written by that build's own
code, exported from git and run in a child interpreter."""
import importlib
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

#: the commit this branch started from: origin/develop with reasoning
#: version 2 and the stored text that did not keep a named value
EARLIER = "2f74cb3f"
REPO = Path(__file__).resolve().parent.parent

NAMED = "dvpkg.mod.unit"
OPT = "dvpkg.mod.opt"
PLAIN = "dvpkg.mod.square"
_NOTE = "a missing value (such as None or nan) that the earlier stored text"

_MOD = '''
from typing import Optional


def unit(x=None):
    """x squared, 0.0 where x is not there."""
    return 0.0 if x is None else x * x


def opt(x: Optional[float]) -> Optional[float]:
    """x squared, None where x is not there."""
    return None if x is None else x * x


def square(x):
    """x squared."""
    return x * x
'''

_CLAIMS = {
    NAMED: {"claims": [{"name": "non_negative",
                        "statement": "for x in [0, 1] | {None}, f(x) >= 0"}]},
    OPT: {"claims": [{"name": "non_negative",
                      "statement": "for x in [0, 1] | {None}, f(x) >= 0"}]},
    PLAIN: {"claims": [{"name": "non_negative",
                        "statement": "for x in [0, 1], f(x) >= 0"}]},
}


def _earlier_tree(scratch: Path) -> Path:
    found = subprocess.run(["git", "-C", str(REPO), "cat-file", "-e",
                            f"{EARLIER}^{{commit}}"], capture_output=True)
    if found.returncode != 0:
        pytest.skip(f"commit {EARLIER} is not in this clone's history")
    tree = scratch / "earlier"
    tree.mkdir()
    archive = subprocess.run(["git", "-C", str(REPO), "archive", EARLIER, "mathema"],
                             capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
    return tree


def _forget():
    for name in [m for m in sys.modules if m == "dvpkg" or m.startswith("dvpkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    root = tmp_path / "proj"
    (root / "dvpkg").mkdir(parents=True)
    (root / "dvpkg" / "__init__.py").write_text("")
    (root / "dvpkg" / "mod.py").write_text(textwrap.dedent(_MOD))
    (root / "claims").mkdir()
    (root / "claims" / "d.claims.yaml").write_text(yaml.safe_dump(_CLAIMS))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    tree = _earlier_tree(tmp_path)
    script = ("import sys, mathema\n"
              f"assert mathema.__file__.startswith({str(tree)!r}), mathema.__file__\n"
              "from mathema.verify import verify_project\n"
              f"out = verify_project(root={str(root)!r})\n"
              "assert not out.problems, out.problems\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(tree), str(root)])
    subprocess.run([sys.executable, "-c", script], cwd=root, env=env, check=True,
                   capture_output=True)
    monkeypatch.syspath_prepend(str(root))
    yield root
    _forget()


def _why(out):
    return {r["key"]: r["why"] for r in out.keys}


def _row(root, key):
    entry = yaml.safe_load((root / ".mathema" / "verified" / f"{key}.yaml")
                           .read_text())[key]
    return {r["name"]: r for r in entry["claims"]}["non_negative"]


def test_the_earlier_record_holds_the_plain_text(project):
    assert _row(project, NAMED)["statement"] == (
        "for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0")


def test_an_earlier_record_naming_a_value_is_moved_once_then_fresh(project):
    from mathema.verify import verify_project
    once = verify_project(root=str(project))
    assert not any("re-authored" in p for p in once.problems), once.problems
    notes = [ln for ln in once.lines if _NOTE in ln]
    assert len(notes) == 1 and notes[0].startswith("note: 2 claims "), once.lines
    assert _why(once)[PLAIN] in ("fresh", "unchanged since the last run"), _why(once)
    assert "mathema.pending_supersession" not in (_row(project, NAMED).get("meta") or {})
    again = verify_project(root=str(project))
    assert not again.problems, again.problems
    assert set(_why(again).values()) == {"fresh"}, _why(again)
    assert not any(_NOTE in ln for ln in again.lines), again.lines
