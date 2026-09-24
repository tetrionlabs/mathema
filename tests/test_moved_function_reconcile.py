# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function that moves to another module leaves its verified record
behind under a key that no longer resolves. `verify` notices when that
orphan's form hash matches a function with no record and prints the
remedy; `mathema accept NEW --as reconciled --from OLD` is the human
rename that carries the record (claims, acceptance history, lineage,
PIN stamp) to the new key and leaves no orphan behind. A `--from` whose
form differs from the live function is refused unless a human confirms
the difference."""
import os
import shutil
import subprocess
import sys
import textwrap

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OLD = "spkg.mod.double"
NEW = "spkg.other.double"

_DOUBLE = '''
def double(x: float) -> float:
    """Doubles.

    Claims:
        nonneg_on_unit [probe]: for x in [0, 5], f(x) >= 0
    """
    return 2.0 * x
'''

_TRIPLE = '''
def double(x: float) -> float:
    """Doubles.

    Claims:
        nonneg_on_unit [probe]: for x in [0, 5], f(x) >= 0
    """
    return 3.0 * x
'''


def _write(tmp_path, rel, body):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body))
    shutil.rmtree(path.parent / "__pycache__", ignore_errors=True)


@pytest.fixture
def env(tmp_path):
    (tmp_path / "spkg").mkdir()
    (tmp_path / "spkg" / "__init__.py").write_text("")
    _write(tmp_path, "spkg/mod.py", _DOUBLE)
    return dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / "xdg"),
                PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))


def _run(tmp_path, env, *argv, stdin=None):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main({list(argv) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env,
        input=stdin)


def _record(tmp_path, key):
    path = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    return (yaml.safe_load(path.read_text()) or {}).get(key) \
        if path.exists() else None


def _first_record(tmp_path, env):
    # a claims-file entry puts the key in the store; once recorded, the
    # docstring claims keep it there with the entry gone
    _write(tmp_path, "claims/c.claims.yaml", f"{OLD}:\n  claims: []\n")
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    (tmp_path / "claims" / "c.claims.yaml").unlink()


def _verified_then_moved(tmp_path, env, moved_body=_DOUBLE):
    _first_record(tmp_path, env)
    r = _run(tmp_path, env, "accept", OLD, "nonneg_on_unit", "--as",
             "evidence", "--by", "lovelace", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    (tmp_path / "spkg" / "mod.py").write_text("")
    _write(tmp_path, "spkg/other.py", moved_body)
    shutil.rmtree(tmp_path / "spkg" / "__pycache__", ignore_errors=True)


_REMEDY = f"mathema accept {NEW} --as reconciled --from {OLD}"


def test_verify_names_the_move_and_the_exact_remedy(tmp_path, env):
    _verified_then_moved(tmp_path, env)
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "cannot resolve to a live function" in r.stdout
    assert _REMEDY in r.stdout, r.stdout


def test_verify_json_carries_the_move(tmp_path, env):
    import json
    _verified_then_moved(tmp_path, env)
    r = _run(tmp_path, env, "verify", "--format", "json")
    assert r.returncode == 1, r.stdout + r.stderr
    rows = {k["key"]: k for k in json.loads(r.stdout)["keys"]}
    assert rows[OLD]["why"] == "unresolvable"
    assert rows[OLD]["moved_to"] == [NEW]
    assert rows[OLD]["remedy"] == [_REMEDY]


def test_no_remedy_when_the_form_differs(tmp_path, env):
    _verified_then_moved(tmp_path, env, moved_body=_TRIPLE)
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 1
    assert "--from" not in r.stdout


def test_a_declared_stanza_moved_with_it_waits_for_the_rename(tmp_path, env):
    # the claims file already names the new key: verify must not write
    # a fresh record for it, which would start the history over
    _write(tmp_path, "claims/c.claims.yaml", f"""
{OLD}:
  claims:
    - name: bounded
      statement: 'for x in [0, 1], f(x) <= 2'
      route: probe
""")
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    (tmp_path / "spkg" / "mod.py").write_text("")
    _write(tmp_path, "spkg/other.py", _DOUBLE)
    _write(tmp_path, "claims/c.claims.yaml",
           (tmp_path / "claims" / "c.claims.yaml").read_text()
           .replace(OLD, NEW))
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 1, r.stdout + r.stderr
    assert _REMEDY in r.stdout
    assert _record(tmp_path, NEW) is None
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_rename_carries_the_record_and_leaves_no_orphan(tmp_path, env):
    from mathema.spec import integrity_matches
    _verified_then_moved(tmp_path, env)
    before = _record(tmp_path, OLD)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, "--by", "babbage", "--note", "moved to other.py", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _record(tmp_path, OLD) is None
    assert not (tmp_path / ".mathema" / "verified" / f"{OLD}.yaml").exists()
    after = _record(tmp_path, NEW)
    row = next(c for c in after["claims"] if c["name"] == "nonneg_on_unit")
    assert row["accepted"]["as"] == "evidence"
    assert row["acceptance_history"][0]["by"] == "lovelace"
    assert after["identity"]["form"] == before["identity"]["form"]
    rec = after["identity"]["reconciled"]
    assert rec["from"] == OLD and rec["by"] == "babbage"
    assert rec["note"] == "moved to other.py"
    assert after["identity"]["pin"] == "none"
    assert after["lineage"]["generated_by"] == \
        before["lineage"]["generated_by"]
    assert integrity_matches(after) is True
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cannot resolve" not in r.stdout


def test_a_form_mismatch_is_refused_without_confirmation(tmp_path, env):
    _verified_then_moved(tmp_path, env, moved_body=_TRIPLE)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, "--yes")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "form" in (r.stdout + r.stderr)
    assert "--accept-form-change" in (r.stdout + r.stderr)
    assert _record(tmp_path, OLD) is not None
    assert _record(tmp_path, NEW) is None


def test_a_form_mismatch_declined_at_the_prompt_writes_nothing(tmp_path, env):
    _verified_then_moved(tmp_path, env, moved_body=_TRIPLE)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, stdin="y\nn\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert _record(tmp_path, NEW) is None
    assert _record(tmp_path, OLD) is not None


def test_a_form_mismatch_a_human_confirms_is_renamed(tmp_path, env):
    _verified_then_moved(tmp_path, env, moved_body=_TRIPLE)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, stdin="y\ny\n")
    assert r.returncode == 0, r.stdout + r.stderr
    after = _record(tmp_path, NEW)
    changed = after["identity"]["reconciled"]["form_changed"]
    assert changed["recorded"] == after["identity"]["form"]
    assert changed["live"] != changed["recorded"]
    assert _record(tmp_path, OLD) is None


def test_a_form_mismatch_confirmed_by_flag_is_renamed(tmp_path, env):
    _verified_then_moved(tmp_path, env, moved_body=_TRIPLE)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, "--accept-form-change", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _record(tmp_path, OLD) is None
    # the recorded form is the old one, so the next sweep re-adjudicates
    # the renamed record against the code it now names
    r = _run(tmp_path, env, "verify")
    assert "form changed" in r.stdout, r.stdout


def _one_line_exit_2(r, *words):
    assert r.returncode == 2, r.stdout + r.stderr
    lines = r.stderr.strip().splitlines()
    assert len(lines) == 1, r.stderr
    for w in words:
        assert w in lines[0], lines[0]


def test_from_an_unknown_record_is_exit_2(tmp_path, env):
    _verified_then_moved(tmp_path, env)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             "spkg.mod.nothing", "--yes")
    _one_line_exit_2(r, "spkg.mod.nothing")


def test_from_to_an_unresolvable_key_is_exit_2(tmp_path, env):
    _verified_then_moved(tmp_path, env)
    r = _run(tmp_path, env, "accept", "spkg.other.nothing", "--as",
             "reconciled", "--from", OLD, "--yes")
    _one_line_exit_2(r, "spkg.other.nothing")


def test_from_needs_reconciled(tmp_path, env):
    _verified_then_moved(tmp_path, env)
    r = _run(tmp_path, env, "accept", NEW, "nonneg_on_unit", "--as",
             "evidence", "--from", OLD, "--yes")
    _one_line_exit_2(r, "--from", "reconciled")


def test_from_with_all_is_exit_2(tmp_path, env):
    _verified_then_moved(tmp_path, env)
    r = _run(tmp_path, env, "accept", "--as", "reconciled", "--all",
             "--from", OLD, "--yes")
    _one_line_exit_2(r, "--from", "--all")


def test_from_a_record_whose_function_still_resolves_is_refused(tmp_path,
                                                                env):
    _first_record(tmp_path, env)
    _write(tmp_path, "spkg/other.py", _DOUBLE)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, "--yes")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "still resolves" in r.stdout + r.stderr
    assert _record(tmp_path, OLD) is not None


def test_onto_a_key_that_already_has_a_record_is_refused(tmp_path, env):
    _verified_then_moved(tmp_path, env)
    dest = tmp_path / ".mathema" / "verified" / f"{NEW}.yaml"
    src = tmp_path / ".mathema" / "verified" / f"{OLD}.yaml"
    dest.write_text(src.read_text().replace(OLD, NEW))
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, "--yes")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "already has a record" in r.stdout + r.stderr
    assert _record(tmp_path, OLD) is not None


def test_json_plan_previews_and_writes_nothing(tmp_path, env):
    import json
    _verified_then_moved(tmp_path, env)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, "--format", "json")
    assert r.returncode == 0, r.stdout + r.stderr
    body = json.loads(r.stdout)
    assert body["applied"] is False and body["from"] == OLD
    assert body["form_matches"] is True
    assert _record(tmp_path, OLD) is not None
    assert _record(tmp_path, NEW) is None


def test_the_lock_moves_with_the_record(tmp_path, env):
    _first_record(tmp_path, env)
    r = _run(tmp_path, env, "lock", OLD)
    assert r.returncode == 0, r.stdout + r.stderr
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    (tmp_path / "spkg" / "mod.py").write_text("")
    _write(tmp_path, "spkg/other.py", _DOUBLE)
    r = _run(tmp_path, env, "accept", NEW, "--as", "reconciled", "--from",
             OLD, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    locks = yaml.safe_load((tmp_path / ".mathema" / "meta"
                            / "locks.yaml").read_text())
    assert NEW in locks and OLD not in locks
    r = _run(tmp_path, env, "verify")
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_pin_stamp_rides_the_rename(tmp_path, monkeypatch):
    import getpass

    from mathema import auth
    from mathema.acceptance import apply_acceptance, plan_rename
    from mathema.verify import verify_project
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "spkg").mkdir()
    (tmp_path / "spkg" / "__init__.py").write_text("")
    _write(tmp_path, "spkg/mod.py", _DOUBLE)
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "claims/c.claims.yaml", f"{OLD}:\n  claims: []\n")
    verify_project(root=str(tmp_path))
    (tmp_path / "claims" / "c.claims.yaml").unlink()
    (tmp_path / "spkg" / "mod.py").write_text("")
    _write(tmp_path, "spkg/other.py", _DOUBLE)
    for mod in [m for m in sys.modules if m.startswith("spkg")]:
        del sys.modules[mod]
    auth.set_pin("4321")
    monkeypatch.setattr(auth, "_tty_available", lambda: True)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "4321")
    apply_acceptance(plan_rename(str(tmp_path), NEW, OLD, by="turing"))
    after = _record(tmp_path, NEW)
    stamp = after["identity"]["reconciled"]["verified_by"]
    assert stamp["method"] == "pin"
    assert after["identity"]["pin"]["methods"] == ["pin"]


def test_mcp_pending_decisions_lists_the_move(tmp_path, env, monkeypatch):
    from mathema.interfaces.mcp.tools import pending_decisions
    _verified_then_moved(tmp_path, env)
    monkeypatch.syspath_prepend(str(tmp_path))
    for mod in [m for m in sys.modules if m.startswith("spkg")]:
        del sys.modules[mod]
    rows = pending_decisions(root=str(tmp_path))["rows"]
    moved = [r for r in rows if r[2] == "moved"]
    assert moved and moved[0][0] == OLD
    assert _REMEDY in moved[0][3]
