# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""CLI exit-code conventions: 0 clean, 1 gate failure, 2 usage/target/
authoring error, 130 interrupt. Every error class the loop hits while
authoring, a malformed claim, a bad target, an unreadable store;
must produce a one-line message and exit 2, never a traceback."""
import os
import subprocess
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(*args, cwd, stdin_text=None):
    env = dict(os.environ)
    parts = [_repo_root(), str(cwd)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(args)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(cwd),
                          capture_output=True, text=True, input=stdin_text,
                          env=env)


def _write_funcs(tmp_path):
    (tmp_path / "funcs.py").write_text(
        "def add(a: float, b: float) -> float:\n    return a + b\n")


def test_invalid_claim_is_a_clean_exit_2(tmp_path):
    _write_funcs(tmp_path)
    r = _run("check", "funcs.py:add", "--claim", "this is not a claim (",
             cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    assert r.stderr.startswith("mathema: ")


def test_bad_target_is_a_clean_exit_2(tmp_path):
    r = _run("check", "no_such_module_anywhere", cwd=tmp_path)
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert r.stderr.startswith("mathema: ")


def test_missing_file_target_is_a_clean_exit_2(tmp_path):
    r = _run("check", "missing/thing.py", cwd=tmp_path)
    assert r.returncode == 2
    assert "no such file" in r.stderr


def test_malformed_claims_yaml_is_a_clean_exit_2(tmp_path):
    _write_funcs(tmp_path)
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "broken.claims.yaml").write_text("{{ not: yaml: at all\n")
    r = _run("verify", "--root", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    assert "malformed YAML" in r.stderr


def test_import_time_crash_in_target_is_a_clean_exit_2(tmp_path):
    (tmp_path / "explodes.py").write_text("raise RuntimeError('boom')\n")
    r = _run("check", "explodes.py", cwd=tmp_path)
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "boom" in r.stderr


def test_unknown_adopt_name_is_a_clean_exit_2(tmp_path):
    """`claims --adopt` naming a suggestion that doesn't exist is the
    same class of error as naming a key that doesn't exist, which
    `main`'s TargetError handler already exits 2 for."""
    _write_funcs(tmp_path)
    r = _run("claims", "funcs.add", "--adopt", "no_such_suggestion",
             "--root", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    assert "no suggestion named" in r.stdout


def test_adopting_an_already_declared_claim_is_a_clean_exit_2(tmp_path):
    _write_funcs(tmp_path)
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "adopted.claims.yaml").write_text(
        "funcs.add:\n"
        "  claims:\n"
        "    - name: commutative\n"
        "      law: \"f(a, b) == f(b, a)\"\n"
        "      route: derive\n")
    r = _run("claims", "funcs.add", "--adopt", "commutative",
             "--root", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "already declared" in r.stdout
