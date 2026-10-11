# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An acceptance writes the claims file and the function's verified
record together, so a `mathema verify` straight after it finds the
function unchanged and does not check it again. An edit to the claims
that the acceptance did not make is still checked."""
import subprocess
import sys

from tests.test_cli_verify import _env_with_repo_on_path

_KEEP = ("def keep(x: float) -> float:\n"
         "    return abs(x)\n")
_CLAIMS = ("funcs.keep:\n  claims:\n"
           "    - name: wrong\n"
           "      statement: \"for x in [-5, 5], f(x) == x\"\n"
           "      route: probe\n"
           "    - name: nonneg\n"
           "      statement: \"for x in [-5, 5], f(x) >= 0\"\n"
           "      route: probe\n")


def _main(root, *argv):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(argv) + ['--root', str(root)]!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True,
                          env=_env_with_repo_on_path())


def _project(tmp_path):
    (tmp_path / "funcs.py").write_text(_KEEP)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "funcs.claims.yaml").write_text(_CLAIMS)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _main(tmp_path, "verify", "--lenient")
    return tmp_path


def _summary(r) -> str:
    return next(ln for ln in r.stdout.splitlines()
                if "unchanged since the last run" in ln)


def test_verify_after_a_discovery_does_not_check_the_function_again(tmp_path):
    root = _project(tmp_path)
    r = _main(root, "accept", "funcs.keep", "wrong", "--as", "discovery",
              "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    r = _main(root, "verify", "--lenient")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _summary(r).startswith("1 unchanged since the last run"), r.stdout
    assert "0 checked" in _summary(r), r.stdout


def test_verify_after_a_corrected_discovery_does_not_check_it_again(tmp_path):
    root = _project(tmp_path)
    r = _main(root, "accept", "funcs.keep", "wrong", "--as", "discovery",
              "--corrected", "for x in [-5, 5], f(x) >= x", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    r = _main(root, "verify", "--lenient")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _summary(r).startswith("1 unchanged since the last run"), r.stdout


def test_a_claim_added_before_the_acceptance_is_still_checked(tmp_path):
    root = _project(tmp_path)
    path = root / "claims" / "funcs.claims.yaml"
    path.write_text(path.read_text()
                    + "    - name: bounded\n"
                      "      statement: \"for x in [-5, 5], f(x) <= 5\"\n"
                      "      route: probe\n")
    r = _main(root, "accept", "funcs.keep", "wrong", "--as", "discovery",
              "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    r = _main(root, "verify", "--lenient")
    assert "1 checked" in _summary(r), r.stdout


def test_verify_after_several_discoveries_does_not_check_again(tmp_path):
    (tmp_path / "claims").mkdir()
    (tmp_path / "funcs.py").write_text(_KEEP)
    (tmp_path / "claims" / "funcs.claims.yaml").write_text(
        _CLAIMS + "    - name: negated\n"
                  "      statement: \"for x in [-5, 5], f(x) == -x\"\n"
                  "      route: probe\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _main(tmp_path, "verify", "--lenient")
    r = _main(tmp_path, "accept", "funcs.keep", "wrong", "negated",
              "--as", "discovery", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    r = _main(tmp_path, "verify", "--lenient")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _summary(r).startswith("1 unchanged since the last run"), r.stdout
