# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema issue`: a structured failure report for one function, built
on reason_codes.issue()/build_issue_record(). Real subprocess per
invocation, same reasoning as test_cli_audit_init.py's own docstring."""
import json
import os
import subprocess
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_with_repo_on_path(pkg_root):
    env = dict(os.environ)
    parts = [_repo_root(), str(pkg_root)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _write_pkg(tmp_path, body):
    pkg = tmp_path / "trialpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(body)
    return tmp_path


def _run(root, *args, stdin_text=None):
    script = ("import sys; from mathema.cli import main; "
             f"sys.exit(main({list(args)!r} + ['--root', {str(root)!r}]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, input=stdin_text,
                          env=_env_with_repo_on_path(root))


_BODY = '''
import math

def calls_unmapped(x: float) -> float:
    return math.hypot(x, x)


def linear_fn(x: float) -> float:
    return 2.0 * x + 1.0


def const_fn(x: float) -> float:
    return 5.0
'''


def test_issue_prints_the_payload_and_declines_on_no(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "--issue", "trialpkg.mod:calls_unmapped", stdin_text="n\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"error_code": "unsupported-construct"' in r.stdout
    assert "not written" in r.stdout
    assert not os.path.exists(os.path.join(str(root), ".mathema", "issues"))


def test_issue_writes_the_file_on_yes(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "--issue", "trialpkg.mod:calls_unmapped", stdin_text="y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "wrote" in r.stdout
    assert "Attach this file to a new GitHub issue" in r.stdout
    issues_dir = os.path.join(str(root), ".mathema", "issues")
    files = os.listdir(issues_dir)
    assert len(files) == 1
    with open(os.path.join(issues_dir, files[0])) as f:
        payload = json.load(f)
    assert payload["meta"]["mathema.diagnostic_report"]["error_code"] == "unsupported-construct"
    assert "source" not in payload["meta"]["mathema.issue"]


def test_issue_include_source_flag_adds_source_this_run_only(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "--issue", "trialpkg.mod:calls_unmapped", "--include-source",
             stdin_text="y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    issues_dir = os.path.join(str(root), ".mathema", "issues")
    files = os.listdir(issues_dir)
    with open(os.path.join(issues_dir, files[0])) as f:
        payload = json.load(f)
    assert "math.hypot" in payload["meta"]["mathema.issue"]["source"]["text"]


def test_issue_reports_nothing_for_a_liftable_function(tmp_path):
    # const_fn's return doesn't depend on x at all, so every suggested
    # monotonic/affine/convex/concave claim holds (derivative 0 satisfies
    # both directions of each), a genuinely clean, liftable function
    # reports nothing.
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "--issue", "trialpkg.mod:const_fn", stdin_text="n\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "nothing to report" in r.stdout


def test_issue_unresolvable_target_fails_cleanly(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "--issue", "trialpkg.mod:does_not_exist", stdin_text="n\n")
    assert r.returncode == 2
    # the shared resolver's message, printed by main()'s error handler
    assert "no function named" in r.stderr
