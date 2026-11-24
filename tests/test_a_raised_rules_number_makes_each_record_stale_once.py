# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema's rules number is part of every claims fingerprint.

A record whose fingerprint was made under an earlier rules number
(including one made before the number existed) is stale: the next sweep
checks it again and re-records it, and the sweep after finds it fresh.
An unedited claim whose record an earlier release wrote in an old
rendering is re-recorded with no supersession; an edited one still
needs one. `verify --all` checks a fresh record again.
"""
import importlib
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema import _rules

_MOD = '''
def tag(x: str, body: str = "", t: str = "") -> int:
    """The length of `t`."""
    return len(t)


def twice(n: int) -> int:
    return 2 * n
'''

_CLAIMS = {
    "rlpkg.mod.tag": {"claims": [
        {"name": "two_literals",
         "statement": "for x in {\"a\"}, f(x, body='a: {\"c\":\"\"}', t=\"s\") == 1"},
        {"name": "plain", "statement": 'for x in {"a"}, f(x, t="ab") == 2'}]},
    "rlpkg.mod.twice": {"claims": [
        {"name": "doubles", "statement": "for n in [0, 10] subset Z, f(n) == n + n"}]},
}


def _forget():
    for name in [m for m in sys.modules if m == "rlpkg" or m.startswith("rlpkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / "rlpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "r.claims.yaml").write_text(yaml.safe_dump(_CLAIMS))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def _why(out):
    return {r["key"]: r["why"] for r in out.keys}


def _record(root, key):
    return yaml.safe_load((root / ".mathema" / "verified"
                           / f"{key}.yaml").read_text())[key]


def test_a_record_from_before_the_number_is_stale_once(project, monkeypatch):
    from mathema.verify import verify_project
    with monkeypatch.context() as m:
        m.setattr(_rules, "REASONING_VERSION", 0)
        assert not verify_project(root=str(project)).problems
    out = verify_project(root=str(project))
    assert not out.problems, out.problems
    assert set(_why(out).values()) == {"mathema's claim rules changed"}, _why(out)
    again = verify_project(root=str(project))
    assert set(_why(again).values()) == {"fresh"}, _why(again)


def test_an_unedited_claim_in_an_old_rendering_is_re_recorded(project):
    from mathema._scan import legacy_quoting
    from mathema.verify import verify_project
    with legacy_quoting():
        verify_project(root=str(project))
    old = _record(project, "rlpkg.mod.tag")
    out = verify_project(root=str(project))
    assert not any("re-authored" in p for p in out.problems), out.problems
    rows = {r["name"]: r for r in _record(project, "rlpkg.mod.tag")["claims"]}
    assert rows["two_literals"]["statement"] != {
        r["name"]: r for r in old["claims"]}["two_literals"]["statement"]
    assert "mathema.pending_supersession" not in (rows["two_literals"].get("meta") or {})
    assert set(_why(verify_project(root=str(project))).values()) == {"fresh"}


def test_an_edited_claim_under_an_earlier_number_is_a_supersession(project,
                                                                   monkeypatch):
    from mathema.verify import verify_project
    with monkeypatch.context() as m:
        m.setattr(_rules, "REASONING_VERSION", 0)
        verify_project(root=str(project))
    edited = {**_CLAIMS, "rlpkg.mod.twice": {"claims": [
        {"name": "doubles", "statement": "for n in [0, 10] subset Z, f(n) >= n"}]}}
    (project / "claims" / "r.claims.yaml").write_text(yaml.safe_dump(edited))
    out = verify_project(root=str(project))
    assert any("rlpkg.mod.twice" in p and "re-authored" in p
               for p in out.problems), out.problems


def test_all_checks_a_fresh_record_again(project):
    from mathema.verify import verify_project
    verify_project(root=str(project))
    assert set(_why(verify_project(root=str(project))).values()) == {"fresh"}
    forced = verify_project(root=str(project), all=True)
    assert "fresh" not in _why(forced).values(), _why(forced)


def test_raising_the_number_makes_every_record_stale(project, monkeypatch):
    from mathema.verify import verify_project
    verify_project(root=str(project))
    monkeypatch.setattr(_rules, "REASONING_VERSION", _rules.REASONING_VERSION + 1)
    out = verify_project(root=str(project))
    assert "fresh" not in _why(out).values(), _why(out)
    assert set(_why(verify_project(root=str(project))).values()) == {"fresh"}


def test_a_record_keeping_a_row_it_could_not_rewrite_stays_stale(project,
                                                                 monkeypatch):
    from mathema import grammar
    from mathema.verify import verify_project
    verify_project(root=str(project))
    monkeypatch.setattr(grammar, "_double_quoted", grammar._legacy_double_quoted)
    first = verify_project(root=str(project), all=True)
    (problem,) = [p for p in first.problems if "two_literals" in p]
    assert "checked again on every run" in problem, problem
    again = verify_project(root=str(project))
    assert _why(again)["rlpkg.mod.tag"] != "fresh", _why(again)
    assert _why(again)["rlpkg.mod.twice"] == "fresh", _why(again)
