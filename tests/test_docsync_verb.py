# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The docsync verb: authoring surfaces materialize into the declared
layer (.mathema/declared/), a claim name authored differently on two
surfaces is a CONFLICT resolved by accepting the docstring's version
into the declared file (structured, never display text), docstring
Claims:-block drift is reported, write-back into source is the
explicit --write-docstrings opt-in only, and the index regenerates.
verify treats an unresolved conflict as a gate problem."""
import os
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _project(tmp_path):
    pkg = tmp_path / "ypkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent('''
        def double(x: float) -> float:
            """Doubles the input.

            Intent:
                Return exactly twice x.

            Claims:
                doubles: for x in [0,9], f(x) == 2*x
            """
            return 2.0 * x
        '''))
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "ypkg.mod.double:\n"
        "  claims:\n"
        "    - name: doubles\n"
        "      statement: 'for x in [0,5], f(x) == 2*x'\n"
        "      route: derive\n"
        "    - name: nonneg\n"
        "      statement: 'for x in [0,5], f(x) >= 0'\n"
        "      route: derive\n")
    return dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))


def _run(tmp_path, env, *argv):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main({list(argv)!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def test_verify_flags_a_surface_conflict(tmp_path):
    env = _project(tmp_path)
    r = _run(tmp_path, env, "verify", "--root", str(tmp_path))
    assert r.returncode == 1
    assert "differs between" in r.stdout and "docsync" in r.stdout


def test_docsync_resolves_conflict_structurally_and_materializes(tmp_path):
    env = _project(tmp_path)
    r = _run(tmp_path, env, "docsync", "ypkg", "--root", str(tmp_path),
             "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CONFLICT" in r.stdout and "declared file updated" in r.stdout
    body = (tmp_path / "claims" / "c.claims.yaml").read_text()
    # the docstring's region won, written STRUCTURED (domain field),
    # never as rendered display text
    assert "hi: 9.0" in body
    assert "{'lo'" not in body
    assert (tmp_path / ".mathema" / "declared"
            / "ypkg.mod.double.yaml").exists()
    assert (tmp_path / ".mathema" / "index.yaml").exists()
    # and verify passes now
    r = _run(tmp_path, env, "verify", "--root", str(tmp_path))
    assert r.returncode == 0, r.stdout


def test_drift_reported_and_write_back_is_explicit(tmp_path):
    env = _project(tmp_path)
    r = _run(tmp_path, env, "docsync", "ypkg", "--root", str(tmp_path),
             "--yes")
    assert "missing-from-docstring" not in r.stdout   # rendered prose form
    assert "not listed in the docstring" in r.stdout
    src = (tmp_path / "ypkg" / "mod.py").read_text()
    assert "nonneg" not in src              # default never edits source
    r = _run(tmp_path, env, "docsync", "ypkg", "--root", str(tmp_path),
             "--yes", "--write-docstrings")
    src = (tmp_path / "ypkg" / "mod.py").read_text()
    assert "nonneg: for x in" in src        # explicit opt-in appended it
    assert "doubles: for x in [0,9]" in src  # the human's line untouched


def test_docstring_intent_wins_in_the_materialized_entry(tmp_path):
    env = _project(tmp_path)
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "ypkg.mod.double:\n"
        "  intent: 'planned: doubling utility'\n"
        "  claims: []\n")
    r = _run(tmp_path, env, "docsync", "ypkg", "--root", str(tmp_path),
             "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    body = (tmp_path / ".mathema" / "declared"
            / "ypkg.mod.double.yaml").read_text()
    assert "Doubles the input" in body      # the docstring's hand
    assert "planned: doubling utility" not in body.split("claims:")[0]


def test_declared_intent_is_the_skeleton_without_a_docstring(tmp_path):
    env = _project(tmp_path)
    (tmp_path / "ypkg" / "mod.py").write_text(
        "def double(x: float) -> float:\n"
        "    return 2.0 * x\n")
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "ypkg.mod.double:\n"
        "  intent: 'planned: doubling utility'\n"
        "  claims: []\n")
    r = _run(tmp_path, env, "docsync", "ypkg", "--root", str(tmp_path),
             "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    body = (tmp_path / ".mathema" / "declared"
            / "ypkg.mod.double.yaml").read_text()
    assert "planned: doubling utility" in body


def test_docsync_rootwide_without_a_target(tmp_path):
    # L11: `docsync --root .` with no target must not argparse-exit(2);
    # it syncs every function the store already knows, the rootwide
    # analogue of `verify`.
    env = _project(tmp_path)
    r = _run(tmp_path, env, "docsync", "ypkg", "--root", str(tmp_path), "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    # now rootwide: no positional target at all
    r = _run(tmp_path, env, "docsync", "--root", str(tmp_path), "--yes")
    assert r.returncode != 2, "argparse usage error: " + r.stderr
    assert r.returncode == 0, r.stdout + r.stderr
    assert "materialized" in r.stdout
