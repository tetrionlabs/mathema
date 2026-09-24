# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a `mathema verify` sweep prints for one function must agree with
what the sweep wrote to that function's record: a regression the record
stores as `invalidated` is reported as invalidated, a tripped lock is
one failing row rather than a failing row and a passing one, and a risk
a person accepted is reported as accepted risk whether or not the
function was re-adjudicated.

Each run is a real subprocess, as in test_cli_verify, so an edited
fixture is re-read from disk rather than from a cached module."""
import subprocess
import sys

from tests.test_cli_verify import _env_with_repo_on_path, _run

_SETTLE_OK = ("def settle(x: float) -> float:\n"
              "    \"\"\"Settlement amount for a signed exposure.\"\"\"\n"
              "    return abs(x)\n")
_SETTLE_BROKEN = _SETTLE_OK.replace("return abs(x)", "return x")

_CLAIMS = """funcs.settle:
  claims:
    - name: nonneg
      statement: "for x in [-5, 5], f(x) >= 0"
      route: probe
"""


def _project(tmp_path):
    (tmp_path / "funcs.py").write_text(_SETTLE_OK)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(_CLAIMS)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    first = _run(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    return tmp_path


def _rows_for(stdout, key):
    return [ln for ln in stdout.splitlines()
            if ln[:5].strip() in ("ok", "FAIL") and f" {key}:" in ln[:60]]


def test_a_regression_is_reported_as_invalidated_not_falsified(tmp_path):
    root = _project(tmp_path)
    (root / "funcs.py").write_text(_SETTLE_BROKEN)
    r = _run(root)
    assert r.returncode == 1, r.stdout
    stored = (root / ".mathema" / "verified" / "funcs.settle.yaml").read_text()
    assert 'verdict: "invalidated"' in stored
    (row,) = [ln for ln in _rows_for(r.stdout, "funcs.settle")
              if "form changed" in ln]
    assert "1 invalidated" in row and "1 invalidated claim(s)" in row
    assert "falsified claim" not in row


def test_a_tripped_lock_is_one_failing_row(tmp_path):
    root = _project(tmp_path)
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['lock', 'funcs.settle', '--root', {str(root)!r}]))")
    locked = subprocess.run([sys.executable, "-c", script], cwd=str(root),
                            capture_output=True, text=True,
                            env=_env_with_repo_on_path())
    assert locked.returncode == 0, locked.stdout + locked.stderr
    (root / "funcs.py").write_text(_SETTLE_BROKEN)
    r = _run(root)
    assert r.returncode == 1, r.stdout
    rows = _rows_for(r.stdout, "funcs.settle")
    assert len(rows) == 1, r.stdout
    assert rows[0].startswith("FAIL") and "locked at form" in rows[0]


def test_accepted_risk_on_a_fresh_record_is_reported_as_accepted_risk():
    from mathema.records import Probe
    from mathema.verify import gate

    stored = [{"name": "grows", "verdict": "proven"},
              {"name": "owned", "verdict": "skipped:unknown_but_accepted"}]
    strict = gate(stored, strict=True)
    assert strict.owned == 1 and strict.skipped == 0
    assert strict.problems == ["1 accepted-risk claim(s)"]
    lenient = gate(stored, strict=False)
    assert lenient.problems == []
    # a fresh adjudication of the same claim reaches the same count
    fresh = gate([Probe("grows", "s", "proven"), Probe("owned", "s", "unknown")],
                 strict=True, accepted_risk=frozenset({"owned"}))
    assert (fresh.owned, fresh.skipped) == (strict.owned, strict.skipped)


def test_a_lock_is_checked_even_without_a_record(tmp_path):
    (tmp_path / "funcs.py").write_text(_SETTLE_OK)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['lock', 'funcs.settle', '--root', {str(tmp_path)!r}]))")
    locked = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                            capture_output=True, text=True,
                            env=_env_with_repo_on_path())
    assert locked.returncode == 0, locked.stdout + locked.stderr
    untouched = _run(tmp_path)
    assert untouched.returncode == 0, untouched.stdout
    (tmp_path / "funcs.py").write_text(_SETTLE_BROKEN)
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    rows = _rows_for(r.stdout, "funcs.settle")
    assert len(rows) == 1 and rows[0].startswith("FAIL"), r.stdout
    assert "locked at form" in rows[0]


def test_a_discovery_reports_the_claims_file_it_rewrote(tmp_path):
    (tmp_path / "funcs.py").write_text(_SETTLE_OK)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(
        "funcs.settle:\n  claims:\n"
        "    - name: negative_exposure_negative\n"
        "      statement: \"for x in [-5, -1], f(x) <= 0\"\n"
        "      route: probe\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    first = _run(tmp_path)
    assert first.returncode == 1, first.stdout
    script = ("import sys; from mathema.cli import main; "
              "sys.exit(main(['accept', 'funcs.settle', "
              "'negative_exposure_negative', '--as', 'discovery', '--yes', "
              f"'--by', 'Ada Lovelace', '--root', {str(tmp_path)!r}]))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True,
                       env=_env_with_repo_on_path())
    assert r.returncode == 0, r.stdout + r.stderr
    rewritten = (tmp_path / "claims" / "demo.claims.yaml").read_text()
    assert "name: negative_exposure_negative\n" not in rewritten
    assert "REPLACE" not in r.stdout
    assert "claims/demo.claims.yaml" in r.stdout
    printed = [ln.strip() for ln in r.stdout.splitlines()
               if ln.strip().startswith("route:")]
    written = [ln.strip() for ln in rewritten.splitlines()
               if ln.strip().startswith("route:")]
    assert printed == written


def test_an_unreadable_authored_claim_names_its_file_not_the_record(tmp_path):
    (tmp_path / "funcs.py").write_text(_SETTLE_OK)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(
        "funcs.settle:\n  claims:\n"
        "    - name: broken\n"
        "      statement: \"f(x) >= 1 +\"\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    r = _run(tmp_path)
    (row,) = _rows_for(r.stdout, "funcs.settle")
    assert row.startswith("FAIL") and "claims/demo.claims.yaml" in row
    assert "delete .mathema/verified" not in row
    assert "Traceback" not in r.stdout + r.stderr
