# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema describe`'s careful lines: edges just outside a domain the
function's claims state, which mathema knows about from a covered
call's computation region, a restricted builtin's real domain, or a
pole.

An edge counts when it lies outside the declared domain but within a
factor of 10 of its nearest bound, or within 1 of a bound near zero.
The lines are information only: no verdict, no gate, and nothing in
`check` or `verify` output or in the record.
"""
import os
import subprocess
import sys

import pytest

pytest.importorskip("numpy")


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(pkg_root):
    env = dict(os.environ)
    parts = [_repo_root(), str(pkg_root)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env.pop("MATHEMA_PSEUDO_INFINITY", None)
    return env


def _write_pkg(tmp_path, body):
    pkg = tmp_path / "edgepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(body)
    return tmp_path


def _run(root, *args):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(args)!r} + ['--root', {str(root)!r}]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=_env(root))


def _exp_body(lo, hi):
    return f'''
import numpy as np


def grow(x: float) -> float:
    """Exponential growth.

    Claims:
        positive: for x in [{lo}, {hi}], f(x) >= 0
    """
    return float(np.exp(x))
'''


def _careful(out: str) -> list:
    return [line.strip() for line in out.splitlines()
            if line.strip().startswith("careful:")]


def test_an_overflow_edge_just_past_the_domain_is_named(tmp_path):
    root = _write_pkg(tmp_path, _exp_body(0, 700))
    r = _run(root, "describe", "edgepkg.mod:grow")
    assert r.returncode == 0, r.stderr
    assert _careful(r.stdout) == [
        "careful: numpy.exp overflows past x = 709.78 "
        "(the domain stops at 700)"]


def test_an_edge_far_from_the_domain_is_not_named(tmp_path):
    root = _write_pkg(tmp_path, _exp_body(0, 10))
    r = _run(root, "describe", "edgepkg.mod:grow")
    assert r.returncode == 0, r.stderr
    assert _careful(r.stdout) == []


def test_check_and_verify_output_carry_no_careful_line(tmp_path):
    root = _write_pkg(tmp_path, _exp_body(0, 700))
    for args in (("check", "edgepkg.mod:grow"), ("verify",)):
        r = _run(root, *args)
        assert "careful" not in r.stdout + r.stderr, args
    import glob
    for path in glob.glob(str(tmp_path / ".mathema" / "**" / "*.yaml"),
                          recursive=True):
        assert "careful" not in open(path).read(), path


def test_a_builtin_domain_edge_below_the_domain_is_named(tmp_path):
    root = _write_pkg(tmp_path, '''
import math


def root_of(x: float) -> float:
    """A square root.

    Claims:
        nonneg: for x in [0.5, 4], f(x) >= 0
    """
    return math.sqrt(x)
''')
    r = _run(root, "describe", "edgepkg.mod:root_of")
    assert r.returncode == 0, r.stderr
    assert _careful(r.stdout) == [
        "careful: sqrt needs x >= 0 (the domain starts at 0.5)"]


def test_a_pole_just_outside_the_domain_is_named(tmp_path):
    root = _write_pkg(tmp_path, '''
def recip(x: float) -> float:
    """A reciprocal.

    Claims:
        positive: for x in [2, 5], f(x) > 0
    """
    return 1.0 / (x - 1.0)
''')
    r = _run(root, "describe", "edgepkg.mod:recip")
    assert r.returncode == 0, r.stderr
    assert _careful(r.stdout) == [
        "careful: a pole at x = 1 (the domain starts at 2)"]
