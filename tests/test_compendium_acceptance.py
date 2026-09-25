# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The compendium-premise loop end to end: a library row a project's
claim rests on is adjudicated by `mathema verify` against the installed
library; a row verify cannot settle is recorded as such, fails the
sweep like an unsettled project claim, and satisfies nothing (the
verify line and the resting claim's note name both paths), `accept --as
trusted` raises it to its claimed level so the premise resolves with
the compendium named as provenance, and a dotted reference resolves the
same row. A project that never touches a library adjudicates none of
its rows."""
import textwrap

import pytest
import yaml


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


@pytest.fixture()
def project(tmp_path):
    _write(tmp_path / "spkg" / "__init__.py", "")
    _write(tmp_path / "spkg" / "mod.py", '''
        def widened(x: float) -> float:
            """x, widened a little."""
            return 1.1 * x
    ''')
    # a derivative claim about a function with no Python source: the
    # installed library cannot settle it here, only testimony can
    _write(tmp_path / "claims" / "math.claims.yaml", """
        compendium: math
        versions: "*"
        math.log:
          claims:
            - name: log_increasing
              statement: 'for x in (0, 100], d(f(x), x) > 0'
              meta: {mathema.compendium_claimed: proven}
    """)
    _write(tmp_path / "claims" / "c.claims.yaml", """
        spkg.mod.widened:
          claims:
            - name: rests
              statement: 'assuming log_increasing holds, for x in [0, 4], f(x) <= 5'
    """)
    return tmp_path


def _sweep(root):
    import os
    import subprocess
    import sys
    env = dict(os.environ, PYTHONPATH=str(root))
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(root)!r}]))"],
        capture_output=True, text=True, env=env)


def _rows(root, key):
    path = root / ".mathema" / "verified" / f"{key}.yaml"
    return {c["name"]: c for c in
            yaml.safe_load(path.read_text())[key]["claims"]}


def test_the_loop_end_to_end(project):
    # run 1: verify adjudicates the library row against the installed
    # library and cannot settle it; the resting claim is unknown and
    # its note names both paths forward
    r1 = _sweep(project)
    rec = project / ".mathema" / "verified" / "math.log.yaml"
    assert rec.exists(), r1.stdout + r1.stderr
    row = _rows(project, "math.log")["log_increasing"]
    assert row["verdict"] == "unknown"
    assert row["meta"]["mathema.surface"] == "compendium"
    assert row["meta"]["mathema.compendium_claimed"] == "proven"
    assert row["meta"]["mathema.compendium"] == "compendium:math"
    # an unsettled library row gates like the project's own claims,
    # and the line names both ways to settle it
    assert "FAIL math.log: library claims from claims/math.claims.yaml" \
        in r1.stdout, r1.stdout
    assert r1.returncode == 1
    assert ("mathema accept math.log log_increasing --as trusted"
            in r1.stdout), r1.stdout
    assert "adjudicate it against the installed library" in r1.stdout
    resting = _rows(project, "spkg.mod.widened")["rests"]
    assert resting["verdict"] == "unknown"
    assert "--as trusted" in (resting["note"] or "")

    # accept as trusted: the row takes its claimed level
    from mathema.acceptance import apply_acceptance, plan_acceptance
    plan = plan_acceptance(str(project), "math.log",
                           "log_increasing", "trusted", by="test")
    assert plan["new_verdict"] == "proven"
    assert plan["accepted"]["source"] == "compendium:math"
    assert any("on the word of compendium:math" in a
               for a in plan["actions"]), plan["actions"]
    apply_acceptance(plan)
    row = _rows(project, "math.log")["log_increasing"]
    assert row["verdict"] == "proven"
    assert row["accepted"]["as"] == "trusted"

    # run 2: the premise resolves; claimed proven passes the
    # conclusion through uncapped: a resolved premise is trusted at
    # the claimed level, not held to a fixed holds ceiling
    r2 = _sweep(project)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    resting = _rows(project, "spkg.mod.widened")["rests"]
    assert resting["verdict"] in ("proven", "holds"), resting["note"]


def test_a_dotted_reference_resolves_the_same_row(project):
    _write(project / "claims" / "c.claims.yaml", """
        spkg.mod.widened:
          claims:
            - name: rests
              statement: 'assuming math.log.log_increasing holds, for x in [0, 4], f(x) <= 5'
    """)
    r1 = _sweep(project)
    assert (project / ".mathema" / "verified" / "math.log.yaml").exists(), \
        r1.stdout + r1.stderr


def test_verify_adjudicates_the_library_functions_a_project_calls(tmp_path):
    pytest.importorskip("numpy")
    _write(tmp_path / "npkg" / "__init__.py", "")
    _write(tmp_path / "npkg" / "mod.py", '''
        import numpy as np

        def root(x: float) -> float:
            """Square root through numpy."""
            return float(np.sqrt(x))

        def plain(x: float) -> float:
            """No library call."""
            return x + 1.0
    ''')
    _write(tmp_path / "claims" / "c.claims.yaml", """
        npkg.mod.root:
          claims:
            - name: nonneg
              statement: 'for x in [0, 4], f(x) >= 0'
        npkg.mod.plain:
          claims:
            - name: grows
              statement: 'for x in [0, 4], f(x) >= x'
    """)
    r = _sweep(tmp_path)
    store = tmp_path / ".mathema" / "verified"
    assert (store / "numpy.sqrt.yaml").exists(), r.stdout + r.stderr
    row = _rows(tmp_path, "numpy.sqrt")["is_defined"]
    assert row["meta"]["mathema.compendium"].startswith("compendium:numpy-")
    # only what the project calls: no other numpy key is adjudicated
    assert sorted(p.name for p in store.glob("numpy.*.yaml")) == \
        ["numpy.sqrt.yaml"]


def test_a_project_that_calls_no_library_adjudicates_none(tmp_path):
    _write(tmp_path / "ppkg" / "__init__.py", "")
    _write(tmp_path / "ppkg" / "mod.py", '''
        def plain(x: float) -> float:
            """No library call."""
            return x + 1.0
    ''')
    _write(tmp_path / "claims" / "c.claims.yaml", """
        ppkg.mod.plain:
          claims:
            - name: grows
              statement: 'for x in [0, 4], f(x) >= x'
    """)
    r = _sweep(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    store = tmp_path / ".mathema" / "verified"
    assert sorted(p.name for p in store.glob("*.yaml")) == \
        ["ppkg.mod.plain.yaml"]
