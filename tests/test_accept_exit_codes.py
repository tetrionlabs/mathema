# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema accept` follows the shared exit-code table: naming a record
or claim that does not exist is a target that does not resolve (2),
while a refusal the acceptance rules make about a real claim stays 1."""
import subprocess
import sys

from tests.test_cli_verify import _env_with_repo_on_path, _run

_SETTLE = ("def settle(x: float) -> float:\n"
           "    \"\"\"Settlement amount for a signed exposure.\"\"\"\n"
           "    return x\n")
_CLAIMS = ("funcs.settle:\n  claims:\n"
           "    - name: nonneg\n"
           "      statement: \"for x in [-5, 5], f(x) >= 0\"\n"
           "      route: probe\n")


def _project(tmp_path):
    (tmp_path / "funcs.py").write_text(_SETTLE)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(_CLAIMS)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _run(tmp_path)
    return tmp_path


def _accept(root, *args):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['accept', *{list(args)!r}, '--yes', "
              f"'--root', {str(root)!r}]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True,
                          env=_env_with_repo_on_path())


def test_a_claim_that_does_not_exist_exits_2(tmp_path):
    r = _accept(_project(tmp_path), "funcs.settle", "no_such_claim",
                "--as", "evidence")
    assert r.returncode == 2, r.stdout + r.stderr


def test_a_record_that_does_not_exist_exits_2(tmp_path):
    r = _accept(_project(tmp_path), "funcs.nothing", "nonneg",
                "--as", "evidence")
    assert r.returncode == 2, r.stdout + r.stderr


def test_a_refused_acceptance_of_a_real_claim_stays_1(tmp_path):
    # a falsification is never accepted as risk
    r = _accept(_project(tmp_path), "funcs.settle", "nonneg", "--as", "risk")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "cannot accept" in r.stdout
