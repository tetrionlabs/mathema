# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The documented CDD loop, end to end, on a package with relative
imports, the exact shape that used to be unreachable from the CLI
(file targets were loaded without package context, so `from .helpers
import ...` died before adjudication began). audit -> init -> check
(ad-hoc claim, by path and by dotted name) -> claims --adopt ->
verify, all through real subprocess CLI invocations."""
import os
import shutil
import subprocess
import sys

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


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


def _project(tmp_path):
    shutil.copytree(os.path.join(DATA, "relpkg"), tmp_path / "relpkg")
    return tmp_path


def test_cdd_loop_end_to_end_on_a_relative_import_package(tmp_path):
    root = _project(tmp_path)

    # audit sees the whole package, including the relative-import module
    r = _run("audit", "relpkg", "--root", str(root), cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr
    # the default layout is the key tree: module section line, leaf name
    assert "relpkg.geometry" in r.stdout
    assert "doubled" in r.stdout

    # init scaffolds stubs for the unclaimed functions
    r = _run("init", "relpkg", "--root", str(root), cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "wrote stub entries" in r.stdout

    # check by FILE PATH: the historically broken spelling, the
    # relative import must survive, and the ad-hoc claim adjudicate
    path = os.path.join("relpkg", "geometry.py")
    r = _run("check", f"{path}:doubled",
             "--claim", "for x in [-10, 10], f(x) == 2*x",
             cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr
    # the default layout is the key tree: module section line, leaf name
    assert "relpkg.geometry" in r.stdout
    assert "doubled" in r.stdout

    # check by dotted name lands on the same key
    r = _run("check", "relpkg.geometry:doubled",
             "--claim", "for x in [-10, 10], f(x) == 2*x",
             "--root", str(root), cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr
    # the default layout is the key tree: module section line, leaf name
    assert "relpkg.geometry" in r.stdout
    assert "doubled" in r.stdout

    # adopt a suggested claim under the dotted key
    r = _run("claims", "relpkg.geometry.doubled", "--suggest",
             "--root", str(root), cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr
    r = _run("claims", "relpkg.geometry.doubled", "--adopt", "odd",
             "--root", str(root), cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "adopted" in r.stdout

    # verify sweeps the stores and adjudicates the package-internal
    # function under the same dotted key the whole loop used
    r = _run("verify", "--root", str(root), "--lenient", cwd=root)
    # the default layout is the key tree: module section line, leaf name
    assert "relpkg.geometry" in r.stdout
    assert "doubled" in r.stdout
    assert "cannot resolve" not in r.stdout
    assert "Traceback" not in r.stderr
    spec = root / ".mathema" / "verified" / "relpkg.geometry.doubled.yaml"
    assert spec.exists(), r.stdout
