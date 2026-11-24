# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record whose stored text did not keep a missing value its claim
names is re-recorded as a change to mathema's rules, not to the claims.

Releases up to 0.6.6.2 stored `x in [0, 1] | {None}` with the text of
the plain interval. The claim is checked again as written and
re-recorded once, with a note; a claim the author edited is still a
change to the claims.
"""
import importlib
import subprocess
import sys
import textwrap

import pytest
import yaml

NAMED = "nvpkg.mod.unit"
PLAIN = "nvpkg.mod.square"

_MOD = '''
def unit(x=None):
    """x squared, 0.0 where x is not there."""
    return 0.0 if x is None else x * x


def square(x):
    """x squared."""
    return x * x
'''

_NAMED_CLAIM = "for x in [0, 1] | {None}, f(x) >= 0"
_PLAIN_CLAIM = "for x in [0, 1], f(x) >= 0"
_OLD_TEXT = "for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0"
_NEW_TEXT = "for x in [0.0, 1.0] | {absent}, f(x) >= 0"
_NOTE = "names a missing value"


def _forget():
    for name in [m for m in sys.modules if m == "nvpkg" or m.startswith("nvpkg.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


def _write_claims(root, named=_NAMED_CLAIM, plain=_PLAIN_CLAIM):
    (root / "claims" / "n.claims.yaml").write_text(yaml.safe_dump({
        NAMED: {"claims": [{"name": "non_negative", "statement": named}]},
        PLAIN: {"claims": [{"name": "non_negative", "statement": plain}]}}))


@pytest.fixture
def project(tmp_path, monkeypatch):
    _forget()
    pkg = tmp_path / "nvpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    _write_claims(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def _why(out):
    return {r["key"]: r["why"] for r in out.keys}


def _record(root, key):
    return yaml.safe_load((root / ".mathema" / "verified"
                           / f"{key}.yaml").read_text())[key]


def _statement(root, key):
    return {r["name"]: r for r in _record(root, key)["claims"]}[
        "non_negative"]["statement"]


def _old_records(root):
    from mathema._scan import legacy_named_filled
    from mathema.verify import verify_project
    with legacy_named_filled():
        out = verify_project(root=str(root))
    assert not out.problems, out.problems
    return out


def test_the_old_record_holds_the_text_of_the_plain_interval(project):
    _old_records(project)
    assert _statement(project, NAMED) == _OLD_TEXT
    assert _statement(project, PLAIN) == _OLD_TEXT


def test_an_old_record_of_a_claim_naming_none_is_a_rules_change(project):
    from mathema.verify import verify_project
    _old_records(project)
    out = verify_project(root=str(project))
    assert not out.problems, out.problems
    assert _why(out)[NAMED] == "mathema's claim rules changed", _why(out)
    notes = [ln for ln in out.lines if _NOTE in ln]
    assert len(notes) == 1 and "1 claim " in notes[0], out.lines
    entry = _record(project, NAMED)
    assert "claims" not in (entry.get("meta") or {}).get("mathema.invalidated_by", [])
    row = {r["name"]: r for r in entry["claims"]}["non_negative"]
    assert row["statement"] == _NEW_TEXT
    assert "mathema.pending_supersession" not in (row.get("meta") or {})


def test_it_is_re_recorded_once_then_fresh(project):
    from mathema.verify import verify_project
    _old_records(project)
    once = verify_project(root=str(project))
    assert not once.problems, once.problems
    assert "fresh" not in _why(once).values(), _why(once)
    again = verify_project(root=str(project))
    assert set(_why(again).values()) == {"fresh"}, _why(again)
    assert not any(_NOTE in ln for ln in again.lines), again.lines


def test_a_claim_that_names_nothing_is_untouched(project):
    from mathema.verify import verify_project
    _old_records(project)
    before = _statement(project, PLAIN)
    out = verify_project(root=str(project))
    assert _statement(project, PLAIN) == before == _OLD_TEXT
    notes = [ln for ln in out.lines if _NOTE in ln]
    assert all(PLAIN not in ln for ln in notes), notes
    assert "claims" not in (_record(project, PLAIN).get("meta") or {}).get(
        "mathema.invalidated_by", [])


def test_a_record_written_now_gets_no_note(project):
    from mathema.verify import verify_project
    assert not verify_project(root=str(project)).problems
    assert _statement(project, NAMED) == _NEW_TEXT
    out = verify_project(root=str(project))
    assert set(_why(out).values()) == {"fresh"}, _why(out)
    assert not any(_NOTE in ln for ln in out.lines), out.lines


def test_a_claim_its_author_changed_is_still_a_claims_change(project):
    from mathema.verify import verify_project
    _old_records(project)
    _write_claims(project, named="for x in [0, 2] | {None}, f(x) >= 0")
    out = verify_project(root=str(project))
    assert any(NAMED in p and "re-authored" in p for p in out.problems), out.problems
    assert not any(_NOTE in ln for ln in out.lines), out.lines
    assert _statement(project, NAMED) == _OLD_TEXT


def test_a_changed_relation_beside_the_named_value_is_a_claims_change(project):
    from mathema.verify import verify_project
    _old_records(project)
    _write_claims(project, named="for x in [0, 1] | {None}, f(x) <= 1")
    out = verify_project(root=str(project))
    assert any(NAMED in p and "re-authored" in p for p in out.problems), out.problems
    assert not any(_NOTE in ln for ln in out.lines), out.lines


def test_the_old_text_cannot_tell_a_named_value_added_since(project):
    """The old text of `[0, 1] | {None}` is the text of plain `[0, 1]`,
    so a record of the plain claim whose author has since named None
    reads as the same move: checked again as written, with the note."""
    from mathema.verify import verify_project
    _old_records(project)
    _write_claims(project, plain="for x in [0, 1] | {None}, f(x) >= 0")
    out = verify_project(root=str(project))
    assert not any("re-authored" in p for p in out.problems), out.problems
    assert _why(out)[PLAIN] == "mathema's claim rules changed", _why(out)
    assert sum(_NOTE in ln for ln in out.lines) == 1, out.lines
    row = {r["name"]: r for r in _record(project, PLAIN)["claims"]}["non_negative"]
    assert row["statement"] == _NEW_TEXT
    assert row["verdict"] == "falsified", row


def test_the_move_is_named_for_the_row_it_explains():
    from mathema._scan import legacy_named_filled, uses_legacy_rendering
    from mathema.sync import _legacy_move, _legacy_renderings
    assert _legacy_renderings()["named-missing-value"] is legacy_named_filled
    with legacy_named_filled():
        assert uses_legacy_rendering()
    assert not uses_legacy_rendering()
    old = {"name": "c", "statement": _OLD_TEXT}
    assert _legacy_move({"name": "c", "statement": _NAMED_CLAIM}, old) == (
        "named-missing-value",)
    assert _legacy_move({"name": "c", "statement": _PLAIN_CLAIM}, old) is None
    assert _legacy_move({"name": "c", "statement": "for x in [0, 1] | {nan}, f(x) >= 0"},
                        {"name": "c", "statement":
                         "for x in [0.0, 1.0] : float|absent|nan, f(x) >= 0"}) == (
        "named-missing-value",)
    assert _legacy_move({"name": "c", "statement": "for x in R | {None}, f(x) >= 0"},
                        {"name": "c", "statement":
                         "for x in R|absent|missing, f(x) >= 0"}) == (
        "named-missing-value",)
    assert _legacy_move({"name": "c", "statement": "for x in [0, 2] | {None}, f(x) >= 0"},
                        old) is None
