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
    assert ('to decide it, restate the row, then run: mathema check '
            'math.log --claim "..."') in r1.stdout, r1.stdout
    assert "let mathema verify adjudicate it" not in r1.stdout
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


def test_a_trusted_row_stands_until_a_verdict_contradicts_it(
        tmp_path, monkeypatch):
    # a library outside the project; its first release defines the
    # function with no Python source, so a derivative row cannot be
    # settled here, and its next release has source, so it can
    import sys

    import mathema.compendium as comp
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.verify import verify_project
    real = comp._installed_version
    monkeypatch.setattr(comp, "_installed_version",
                        lambda lib, aliases=(): "1.0" if lib == "extlib" else real(lib, aliases))
    site = tmp_path / "site"
    source = site / "extlib" / "__init__.py"
    _write(source, '''
        exec("def scaled(x):\\n    return 2.0 * x\\n")
    ''')
    monkeypatch.syspath_prepend(str(site))
    proj = tmp_path / "proj"
    _write(proj / "claims" / "extlib.claims.yaml", """
        compendium: extlib
        versions: ">=1.0"
        extlib.scaled:
          claims:
            - name: rising
              statement: 'for x in (0, 100], d(f(x), x) > 0'
              meta: {mathema.compendium_claimed: proven}
    """)

    def sweep(**kw):
        sys.modules.pop("extlib", None)
        comp.uninstall()
        return verify_project(str(proj), **kw)

    sweep()
    assert _rows(proj, "extlib.scaled")["rising"]["verdict"] == "unknown"
    apply_acceptance(plan_acceptance(str(proj), "extlib.scaled", "rising",
                                     "trusted", by="test"))
    # the forced sweep still cannot settle it: the acceptance stands
    forced = sweep(all=True)
    row = _rows(proj, "extlib.scaled")["rising"]
    assert row["verdict"] == "proven", row
    assert row["accepted"]["as"] == "trusted"
    assert not row["accepted"].get("stale")
    assert not forced.problems, forced.lines
    line = next(x for x in forced.lines if "extlib.scaled" in x)
    assert "stays trusted at its accepted level" in line, line
    # the next release has source: the local verdict replaces the trust
    _write(source, '''
        def scaled(x: float) -> float:
            """Twice x."""
            return 2.0 * x
    ''')
    sweep(all=True)
    row = _rows(proj, "extlib.scaled")["rising"]
    assert row["verdict"] == "proven"
    assert row["accepted"].get("stale") is True
    assert "mathema.trusted_unsettled" not in (row.get("meta") or {})


def _trusted_row(level, fresh, route="probe"):
    from mathema.acceptance import _carry_trust
    c = {"name": "rising", "statement": "for x in (0, 100], d(f(x), x) > 0",
         "verdict": fresh, "route": route, "note": "sampled 200 points",
         "meta": {"mathema.surface": "compendium"}}
    accepted = {"as": "trusted", "by": "test", "level": level,
                "verdict": level}
    _carry_trust(c, accepted, [])
    return c


def test_a_weaker_consistent_local_verdict_leaves_the_trust_standing():
    row = _trusted_row("proven", "holds")
    assert row["verdict"] == "proven"
    assert not row["accepted"].get("stale")
    assert row["note"] == "trusted as: proven, strongest evidence seen: holds"
    assert row["meta"]["mathema.strongest_evidence"] == "holds"
    assert "mathema.trusted_unsettled" not in row["meta"]


def test_a_contradicting_local_verdict_replaces_the_trust():
    row = _trusted_row("proven", "falsified")
    assert row["verdict"] == "falsified"
    assert row["accepted"]["stale"] is True
    assert "mathema.strongest_evidence" not in row["meta"]
    assert row["acceptance_history"][-1]["event"] == "stale"


@pytest.mark.parametrize("level, fresh", [("holds", "proven"),
                                          ("proven", "proven"),
                                          ("holds", "holds")])
def test_a_local_verdict_at_least_as_strong_replaces_the_trust(level, fresh):
    row = _trusted_row(level, fresh)
    assert row["verdict"] == fresh
    assert row["accepted"]["stale"] is True
    assert "mathema.strongest_evidence" not in row["meta"]
    assert row["note"] == "sampled 200 points"


def test_an_unsettled_local_verdict_keeps_todays_reading():
    row = _trusted_row("proven", "unknown")
    assert row["verdict"] == "proven"
    assert row["meta"]["mathema.trusted_unsettled"] == "unknown"
    assert "mathema.strongest_evidence" not in row["meta"]


def test_a_sweep_keeps_a_trusted_proof_over_a_local_holds(
        tmp_path, monkeypatch):
    # a row the probe route can only sample (derive cannot read the
    # body), accepted as trusted at the proven level it claims while it
    # was unsettled: the local holds leaves the trust standing
    import sys

    import mathema.compendium as comp
    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.spec import integrity_checksum
    from mathema.verify import verify_project
    real = comp._installed_version
    monkeypatch.setattr(comp, "_installed_version",
                        lambda lib, aliases=(): "1.0" if lib == "extlib" else real(lib, aliases))
    site = tmp_path / "site"
    _write(site / "extlib" / "__init__.py", '''
        def squared(x: float) -> float:
            """x squared, through its decimal text."""
            return float(format(x * x, ".17g"))
    ''')
    monkeypatch.syspath_prepend(str(site))
    proj = tmp_path / "proj"
    _write(proj / "claims" / "extlib.claims.yaml", """
        compendium: extlib
        versions: ">=1.0"
        extlib.squared:
          claims:
            - name: nonneg
              statement: 'for x in [0, 10], f(x) >= 0'
              meta: {mathema.compendium_claimed: proven}
    """)

    def sweep(**kw):
        sys.modules.pop("extlib", None)
        comp.uninstall()
        return verify_project(str(proj), **kw)

    sweep()
    assert _rows(proj, "extlib.squared")["nonneg"]["verdict"] == "holds"
    # the row as an earlier sweep left it, unsettled
    path = proj / ".mathema" / "verified" / "extlib.squared.yaml"
    doc = yaml.safe_load(path.read_text())
    entry = doc["extlib.squared"]
    for c in entry["claims"]:
        if c["name"] == "nonneg":
            c["verdict"] = "unknown"
    entry["identity"]["integrity"] = integrity_checksum(entry)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    apply_acceptance(plan_acceptance(str(proj), "extlib.squared", "nonneg",
                                     "trusted", by="test"))
    result = sweep(all=True)
    row = _rows(proj, "extlib.squared")["nonneg"]
    assert row["meta"]["mathema.strongest_evidence"] == "holds", row
    assert row["verdict"] == "proven"
    assert not row["accepted"].get("stale")
    assert row["note"] == "trusted as: proven, strongest evidence seen: holds"
    assert not result.problems, result.lines
    line = next(x for x in result.lines if "extlib.squared" in x)
    assert "nonneg trusted as: proven, strongest evidence seen: holds" in \
        line, line
