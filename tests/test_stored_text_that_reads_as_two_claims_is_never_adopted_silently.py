# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Stored text an earlier release wrote for two different claims.

Releases up to 0.6.6.1 wrote `f(s, '}"', 's') == 1` (two arguments) and
`f(s, '}"", "s') == 1` (one argument) as the same stored text,
`f(s, '}"", "s') = 1`. A record holding that text cannot say which
claim was checked. A row an earlier release wrote whose text holds a
string literal is checked again once against the claim as written and
re-recorded under this release's rules, so no verdict carries across
unchecked; and when the claim as written is not the claim the stored
text reads as now, the run says the text is ambiguous, names both
readings and the remedy, and does not call it a release move.
"""
import importlib
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema.spec import written_under_earlier_rules

KEY = "ampkg.mod.tag"

_MOD = '''
def tag(s: str, a: str = "", b: str = "") -> int:
    """One when b is "s"."""
    return int(b == "s")
'''

TWO = "for s in {\"a\"}, f(s, '}\"', 's') == 1"
ONE = "for s in {\"a\"}, f(s, '}\"\", \"s') == 1"
STORED = "for s in {\"a\"}, f(s, '}\"\", \"s') = 1"


def _forget():
    for name in [m for m in sys.modules if m == "ampkg" or m.startswith("ampkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / "ampkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def _claim(root, statement):
    (root / "claims" / "a.claims.yaml").write_text(yaml.safe_dump(
        {KEY: {"claims": [{"name": "c", "statement": statement}]}}))


def _row(root):
    entry = yaml.safe_load((root / ".mathema" / "verified"
                            / f"{KEY}.yaml").read_text())[KEY]
    return {r["name"]: r for r in entry["claims"]}["c"]


def _entry(root):
    return yaml.safe_load((root / ".mathema" / "verified"
                           / f"{KEY}.yaml").read_text())[KEY]


def _legacy_record(root, statement):
    from mathema._scan import legacy_quoting
    from mathema.verify import verify_project
    _claim(root, statement)
    with legacy_quoting():
        verify_project(root=str(root))
    row = _row(root)
    assert row["statement"] == STORED, row
    assert written_under_earlier_rules(_entry(root))
    return row


def test_an_edit_to_the_other_reading_is_reported_as_ambiguous(project):
    from mathema.verify import verify_project
    assert _legacy_record(project, ONE)["verdict"] == "falsified"
    _claim(project, TWO)
    out = verify_project(root=str(project))
    said = [ln for ln in out.lines if "ambiguous" in ln]
    assert len(said) == 1, out.lines
    assert STORED in said[0], said[0]
    assert "f(s, '}\"', \"s\") = 1" in said[0], said[0]
    assert f"mathema accept {KEY} c --as superseded" in said[0], said[0]
    assert not any("string literal is corrected" in ln for ln in out.lines), out.lines
    row = _row(project)
    assert row["verdict"] == "proven", row
    assert not written_under_earlier_rules(_entry(project))


def test_the_earlier_reading_is_superseded_when_the_author_says_so(project):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.verify import verify_project
    _legacy_record(project, ONE)
    _claim(project, TWO)
    verify_project(root=str(project))
    apply_acceptance(plan_acceptance(str(project), KEY, "c", "superseded"))
    entry = yaml.safe_load((project / ".mathema" / "verified"
                            / f"{KEY}.yaml").read_text())[KEY]
    (old,) = entry["superseded"]
    assert old["statement"] == STORED and old["verdict"] == "falsified", old
    live = {r["name"]: r for r in entry["claims"]}["c"]
    assert live["verdict"] == "proven", live
    assert "mathema.earlier_reading" not in (live.get("meta") or {})


def test_an_edit_onto_the_stored_text_is_checked_again(project):
    from mathema.verify import verify_project
    assert _legacy_record(project, TWO)["verdict"] == "proven"
    _claim(project, ONE)
    out = verify_project(root=str(project))
    rows = {r["key"]: r for r in out.keys}
    assert rows[KEY]["why"] != "fresh", rows[KEY]
    row = _row(project)
    assert row["verdict"] == "falsified", row
    assert not written_under_earlier_rules(_entry(project))
    again = verify_project(root=str(project))
    assert {r["key"]: r for r in again.keys}[KEY]["why"] == "fresh"


def test_an_unchanged_claim_is_checked_again_once(project):
    from mathema.verify import verify_project
    _legacy_record(project, ONE)
    out = verify_project(root=str(project))
    assert {r["key"]: r for r in out.keys}[KEY]["why"] != "fresh"
    assert not any("ambiguous" in ln for ln in out.lines), out.lines
    assert _row(project)["verdict"] == "falsified"
    again = verify_project(root=str(project))
    assert {r["key"]: r for r in again.keys}[KEY]["why"] == "fresh"
