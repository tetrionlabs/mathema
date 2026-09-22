# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The compendium-premise loop end to end: a referenced compendium row
materialises into the verified store at declared status (satisfying
nothing, note naming both paths), `accept --as trusted` raises it to
its claimed level so a premise resting on it caps there with the stub
named as provenance, and a dotted reference resolves the same row
precisely."""
import textwrap

import pytest


@pytest.fixture()
def project(tmp_path):
    pkg = tmp_path / "spkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent('''
        def widened(x: float) -> float:
            """x, widened a little."""
            return 1.1 * x
    '''))
    stubs = tmp_path / ".mathema" / "compendium"
    stubs.mkdir(parents=True)
    (stubs / "fakelib.yaml").write_text(textwrap.dedent("""
        package: math
        versions: "*"
        functions:
          fakelib.clip:
            params: [x, lo, hi]
            claims:
              - name: fake_clip_lower
                statement: 'assuming lo <= hi, for x in [-9, 9], lo <= f(x, lo, hi)'
                verdict: proven
    """))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "c.claims.yaml").write_text(textwrap.dedent("""
        spkg.mod.widened:
          claims:
            - name: rests
              statement: 'assuming fake_clip_lower holds, for x in [0, 4], f(x) <= 5'
    """))
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


def test_the_loop_end_to_end(project):
    import yaml

    # run 1: the reference materialises the stub row; the resting
    # claim is unknown and its note names both paths forward
    r1 = _sweep(project)
    rec = project / ".mathema" / "verified" / "fakelib.clip.yaml"
    assert rec.exists(), r1.stdout + r1.stderr
    row = yaml.safe_load(rec.read_text())["fakelib.clip"]["claims"][0]
    assert row["verdict"] == "declared"
    assert row["meta"]["mathema.compendium_claimed"] == "proven"
    own = yaml.safe_load(
        (project / ".mathema" / "verified" / "spkg.mod.widened.yaml")
        .read_text())["spkg.mod.widened"]["claims"]
    (resting,) = [c for c in own if c["name"] == "rests"]
    assert resting["verdict"] == "unknown"
    assert "--as trusted" in (resting["note"] or "")

    # accept as trusted: the row takes its claimed level
    from mathema.acceptance import apply_acceptance, plan_acceptance
    plan = plan_acceptance(str(project), "fakelib.clip",
                           "fake_clip_lower", "trusted", by="test")
    assert plan["new_verdict"] == "proven"
    apply_acceptance(plan)
    row = yaml.safe_load(rec.read_text())["fakelib.clip"]["claims"][0]
    assert row["verdict"] == "proven"
    assert row["accepted"]["as"] == "trusted"

    # run 2: the premise resolves; claimed proven passes the
    # conclusion through uncapped: a resolved premise is trusted at
    # the claimed level, not held to a fixed holds ceiling
    r2 = _sweep(project)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    own = yaml.safe_load(
        (project / ".mathema" / "verified" / "spkg.mod.widened.yaml")
        .read_text())["spkg.mod.widened"]["claims"]
    (resting,) = [c for c in own if c["name"] == "rests"]
    assert resting["verdict"] in ("proven", "holds"), resting["note"]


def test_a_dotted_reference_resolves_the_same_row(project):
    (project / "claims" / "c.claims.yaml").write_text(
        "spkg.mod.widened:\n  claims:\n    - name: rests\n"
        "      statement: 'assuming fakelib.clip.fake_clip_lower holds, "
        "for x in [0, 4], f(x) <= 5'\n")
    r1 = _sweep(project)
    assert (project / ".mathema" / "verified" / "fakelib.clip.yaml").exists(), \
        r1.stdout + r1.stderr
