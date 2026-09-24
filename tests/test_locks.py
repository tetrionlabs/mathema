# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Locking: a function's form hash pinned so the body cannot change
under a CDD loop.

The contract under test: verify refuses to re-adjudicate a locked
function whose form moved and leaves the record byte-identical;
docstring edits never trip a lock (the form hash strips them); the
lock survives the sweep it blocks; deleting the meta entry by hand is
detected against the record's stamp; and unlock is prompted,
PIN-verified when one is set, and leaves an audit event.
"""
import pytest
import yaml

from mathema.locks import LockError, load_locks, lock, lock_state, unlock

_BODY = '''\
def settle(x: float) -> float:
    """Settlement amount for a signed exposure."""
    return abs(x)
'''

_CLAIMS = '''\
lockfix.settle:
  claims:
    - name: nonneg
      statement: "for x in [-5, 5], f(x) >= 0"
      route: probe
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    import importlib
    import sys

    from mathema.verify import verify_project
    # each test gets its own tmp_path copy of the module; a cached
    # import from a previous test's directory is cross-test
    # contamination waiting to happen
    sys.modules.pop("lockfix", None)
    importlib.invalidate_caches()
    (tmp_path / "lockfix.py").write_text(_BODY)
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "demo.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    out = verify_project(root=str(tmp_path))
    assert not out.problems
    return tmp_path


def _reload(tmp_path):
    """Intent:
        Force a re-import so the sweep sees the edited source; the
        module object is cached per test session otherwise.
    """
    import importlib
    import sys
    importlib.invalidate_caches()
    if "lockfix" in sys.modules:
        importlib.reload(sys.modules["lockfix"])


def _record_bytes(project):
    return (project / ".mathema" / "verified" / "lockfix.settle.yaml").read_bytes()


def _form(project):
    doc = yaml.safe_load((project / ".mathema" / "verified"
                          / "lockfix.settle.yaml").open())
    return doc["lockfix.settle"]["identity"]["form"]


# --- the store --------------------------------------------------------------

def test_lock_round_trip_and_relock_rules(project):
    entry = lock(str(project), "lockfix.settle", "abc123", by="tester",
                 note="settled")
    assert load_locks(str(project))["lockfix.settle"]["form"] == "abc123"
    # same form: idempotent
    assert lock(str(project), "lockfix.settle", "abc123") == entry
    # different form: refused, that is what unlock is for
    with pytest.raises(LockError, match="already locked"):
        lock(str(project), "lockfix.settle", "def456")
    assert unlock(str(project), "lockfix.settle")["form"] == "abc123"
    with pytest.raises(LockError, match="not locked"):
        unlock(str(project), "lockfix.settle")


def test_lock_state_vocabulary():
    locks = {"k": {"form": "aaa"}}
    assert lock_state("k", "aaa", locks, {}) == "held"
    assert lock_state("k", "bbb", locks, {}) == "changed"
    assert lock_state("k", "aaa", {}, {}) is None
    assert lock_state("k", "aaa", {}, {"locked": {"form": "aaa"}}) \
        == "removed-outside"


# --- verify enforcement -----------------------------------------------------

def test_locked_body_change_fails_and_record_is_untouched(project):
    from mathema.verify import verify_project
    lock(str(project), "lockfix.settle", _form(project), by="tester")
    verify_project(root=str(project))          # stamps the lock
    before = _record_bytes(project)
    src = project / "lockfix.py"
    src.write_text(src.read_text().replace("return abs(x)", "return x"))
    _reload(project)
    out = verify_project(root=str(project))
    assert any("locked at form" in p for p in out.problems)
    assert _record_bytes(project) == before, \
        "the record moved onto code a human never sanctioned"


def test_docstring_edit_does_not_trip_the_lock(project):
    from mathema.verify import verify_project
    lock(str(project), "lockfix.settle", _form(project), by="tester")
    src = project / "lockfix.py"
    src.write_text(src.read_text().replace(
        "Settlement amount for a signed exposure.",
        "A completely rewritten docstring."))
    _reload(project)
    out = verify_project(root=str(project))
    assert not any("locked" in p for p in out.problems)


def test_hand_deleted_lock_entry_is_detected(project):
    from mathema.verify import verify_project
    lock(str(project), "lockfix.settle", _form(project), by="tester")
    verify_project(root=str(project))          # record now carries the stamp
    (project / ".mathema" / "meta" / "locks.yaml").unlink()
    out = verify_project(root=str(project))
    assert any("removed" in p and "unlock" in p for p in out.problems)


def test_a_hand_deleted_lock_keeps_failing_until_unlocked(project):
    # re-adjudication must not rebuild the record without its stamp,
    # which would leave the removal invisible from the next sweep on
    from mathema.verify import verify_project
    lock(str(project), "lockfix.settle", _form(project), by="tester")
    verify_project(root=str(project))
    (project / ".mathema" / "meta" / "locks.yaml").unlink()
    for _ in range(2):
        out = verify_project(root=str(project), all=True)
        assert any("removed" in p and "unlock" in p for p in out.problems)


def test_a_lock_moved_by_hand_is_detected(project):
    # pointing the meta entry at the edited body's form, without
    # unlocking, is a lock moved outside `mathema unlock`
    from mathema.verify import verify_project
    lock(str(project), "lockfix.settle", _form(project), by="tester")
    verify_project(root=str(project))
    src = project / "lockfix.py"
    src.write_text(src.read_text().replace("return abs(x)", "return x"))
    _reload(project)
    from mathema import analyze
    import lockfix
    path = project / ".mathema" / "meta" / "locks.yaml"
    locks = yaml.safe_load(path.read_text())
    locks["lockfix.settle"]["form"] = analyze(lockfix.settle).form
    path.write_text(yaml.safe_dump(locks))
    before = _record_bytes(project)
    out = verify_project(root=str(project))
    assert any("moved" in p and "unlock" in p for p in out.problems), \
        out.problems
    assert _record_bytes(project) == before


def test_lock_state_names_a_moved_lock():
    locks = {"k": {"form": "bbb"}}
    assert lock_state("k", "bbb", locks, {"locked": {"form": "aaa"}}) \
        == "moved-outside"
    assert lock_state("k", "bbb", locks, {"locked": {"form": "bbb"}}) \
        == "held"
    assert lock_state("k", "bbb", locks, {}) == "held"


def test_lock_survives_the_sweep_it_blocks(project):
    from mathema.verify import verify_project
    lock(str(project), "lockfix.settle", _form(project), by="tester")
    src = project / "lockfix.py"
    src.write_text(src.read_text().replace("return abs(x)", "return x"))
    _reload(project)
    verify_project(root=str(project))
    verify_project(root=str(project))
    # two failing sweeps later the lock entry is exactly as written
    assert load_locks(str(project))["lockfix.settle"]["by"] == "tester"


# --- the verbs --------------------------------------------------------------

def test_cli_lock_stamps_the_record(project, monkeypatch, capsys):
    from mathema.cli import main
    monkeypatch.chdir(project)
    assert main(["lock", "lockfix.settle", "--root", str(project),
                 "--note", "settled"]) == 0
    doc = yaml.safe_load((project / ".mathema" / "verified"
                          / "lockfix.settle.yaml").open())
    stamped = doc["lockfix.settle"]["locked"]
    assert stamped["form"] == _form(project)
    from mathema.spec import integrity_checksum
    assert doc["lockfix.settle"]["identity"]["integrity"] == \
        integrity_checksum(doc["lockfix.settle"])


def test_cli_unlock_prompts_verifies_and_leaves_an_event(project, monkeypatch):
    import getpass as getpass_mod

    from mathema import auth
    from mathema.cli import main
    monkeypatch.setenv("XDG_CONFIG_HOME", str(project / "xdg"))
    info = auth.set_pin("4321")
    main(["lock", "lockfix.settle", "--root", str(project)])
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    monkeypatch.setattr(auth, "_tty_available", lambda: True)
    monkeypatch.setattr(getpass_mod, "getpass", lambda prompt="": "4321")
    assert main(["unlock", "lockfix.settle", "--root", str(project)]) == 0
    assert "lockfix.settle" not in load_locks(str(project))
    doc = yaml.safe_load((project / ".mathema" / "verified"
                          / "lockfix.settle.yaml").open())
    entry = doc["lockfix.settle"]
    assert "locked" not in entry
    event = entry["lock_history"][-1]
    assert event["event"] == "unlocked"
    assert event["verified_by"]["key"] == info["key"]


def test_cli_unlock_declined_keeps_the_lock(project, monkeypatch):
    from mathema.cli import main
    main(["lock", "lockfix.settle", "--root", str(project)])
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert main(["unlock", "lockfix.settle", "--root", str(project)]) == 1
    assert "lockfix.settle" in load_locks(str(project))


def test_cli_unlock_refused_without_a_terminal(project, monkeypatch):
    from mathema import auth
    from mathema.cli import main
    monkeypatch.setenv("XDG_CONFIG_HOME", str(project / "xdg"))
    auth.set_pin("4321")
    main(["lock", "lockfix.settle", "--root", str(project)])
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    monkeypatch.setattr(auth, "_tty_available", lambda: False)
    assert main(["unlock", "lockfix.settle", "--root", str(project)]) == 1
    assert "lockfix.settle" in load_locks(str(project))


# --- the agent surface ------------------------------------------------------

def test_mcp_lock_target_locks_and_refuses_a_moved_relock(project, monkeypatch):
    from mathema.interfaces.mcp.tools import lock_target
    monkeypatch.chdir(project)
    out = lock_target("lockfix.settle", note="agent settled it",
                      root=str(project))
    assert out["locked"] is True
    assert load_locks(str(project))["lockfix.settle"]["by"] == "agent"
    src = project / "lockfix.py"
    src.write_text(src.read_text().replace("return abs(x)", "return x"))
    _reload(project)
    out2 = lock_target("lockfix.settle", root=str(project))
    assert out2["locked"] is False and "unlock" in out2["error"]


def test_pending_decisions_surfaces_locked_changed(project, monkeypatch):
    from mathema.interfaces.mcp.tools import pending_decisions
    lock(str(project), "lockfix.settle", _form(project))
    src = project / "lockfix.py"
    src.write_text(src.read_text().replace("return abs(x)", "return x"))
    _reload(project)
    monkeypatch.syspath_prepend(str(project))
    rows = pending_decisions(root=str(project))["rows"]
    kinds = {r[2] for r in rows}
    assert "locked-changed" in kinds


# --- the audit surface ------------------------------------------------------

def test_audit_shows_the_locked_column_only_when_something_is(project, monkeypatch):
    from mathema.audit import COMPACT_COLUMNS, audit_rows
    monkeypatch.chdir(project)
    rows = audit_rows(["lockfix"], root=str(project))
    (row,) = [r for r in rows if r["key"] == "lockfix.settle"]
    assert row["locked"] is None
    assert COMPACT_COLUMNS["locked"](row) == ""
    lock(str(project), "lockfix.settle", _form(project), by="tester")
    rows = audit_rows(["lockfix"], root=str(project))
    (row,) = [r for r in rows if r["key"] == "lockfix.settle"]
    assert row["locked"]["by"] == "tester"
    assert COMPACT_COLUMNS["locked"](row) == _form(project)


def test_cli_audit_grid_carries_the_lock(project, monkeypatch, capsys):
    from mathema.cli import main
    monkeypatch.chdir(project)
    lock(str(project), "lockfix.settle", _form(project), by="tester")
    main(["audit", "lockfix", "--root", str(project)])
    out = capsys.readouterr().out
    assert "yes (tester)" in out
    assert "1 locked" in out
    # and an unlocked population never pays for the column
    unlock(str(project), "lockfix.settle")
    main(["audit", "lockfix", "--root", str(project)])
    out = capsys.readouterr().out
    assert "yes (tester)" not in out
    assert "1 locked" not in out
