# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The layered store's contracts: the verified layer
(.mathema/verified/) is append-only in
MEMBERSHIP; a claim deleted from every authoring surface is
repopulated from its verified row and keeps being adjudicated; its
exits are supersession or the human `historical` acceptance, never
silent removal. Records stamp the git commit and an integrity
checksum over (claim, verdict) pairs so hand-edits are detectable."""
import os
import shutil
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _project(tmp_path, fn_body, claims_yaml):
    pkg = tmp_path / "spkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(fn_body))
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        textwrap.dedent(claims_yaml))
    shutil.rmtree(pkg / "__pycache__", ignore_errors=True)
    return dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))


def _verify(tmp_path, env):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


_DOUBLE = """
def double(x: float) -> float:
    \"\"\"Doubles.\"\"\"
    return 2.0 * x
"""

_CLAIMS = """
spkg.mod.double:
  claims:
    - name: doubles
      statement: 'for x in [0,5], f(x) == 2*x'
      route: derive
"""


def test_membership_survives_declared_deletion(tmp_path):
    env = _project(tmp_path, _DOUBLE, _CLAIMS)
    r = _verify(tmp_path, env)
    assert r.returncode == 0, r.stdout + r.stderr
    key = "spkg.mod.double"
    rec = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    body = rec.read_text()
    assert "condition:" in body              # the region rides every row
    # delete the claim from the declared layer entirely
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "spkg.mod.double:\n  claims: []\n")
    r = _verify(tmp_path, env)
    assert r.returncode == 0, r.stdout + r.stderr
    body = rec.read_text()
    assert "doubles" in body                 # membership survived the deletion
    assert '"proven"' in body
    # the repopulated claim fingerprints identically to the declared
    # one it replaced, so unchanged code + unchanged effective claim
    # set is genuinely fresh: no busywork re-adjudication
    assert "fresh" in r.stdout
    # move the code, and the repopulated claim re-adjudicates like any
    # live claim; membership is a working claim, not a fossil
    (tmp_path / "spkg" / "mod.py").write_text(textwrap.dedent("""
def double(x: float) -> float:
    \"\"\"Doubles.\"\"\"
    return x + x
"""))
    shutil.rmtree(tmp_path / "spkg" / "__pycache__", ignore_errors=True)
    r = _verify(tmp_path, env)
    assert r.returncode == 0, r.stdout + r.stderr
    body = rec.read_text()
    assert "repopulated-from-verified" in body
    assert '"proven"' in body                # re-adjudicated, not fossilized


def test_integrity_checksum_detects_hand_edits(tmp_path):
    env = _project(tmp_path, _DOUBLE, _CLAIMS)
    _verify(tmp_path, env)
    key = "spkg.mod.double"
    rec = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    body = rec.read_text()
    assert "integrity:" in body
    # tamper: flip the verdict by hand
    rec.write_text(body.replace('"proven"', '"holds"', 1))
    r = _verify(tmp_path, env)
    # the mismatch is detected and names the fix, without accusing the
    # author of hand-editing (a merge/rebase trips it the same way).
    # The named fix must be the one that RE-CHECKS: reconciliation
    # vouches for contents unchecked, so it is not offered here as a
    # peer of re-adjudication
    assert "checksum no longer matches its contents" in r.stdout
    assert f"mathema verify {key}" in r.stdout
    assert "reconciled" not in r.stdout


def _accept(tmp_path, env, *args):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['accept', *{list(args)!r}, '--root', "
         f"{str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def test_reconcile_clears_the_mismatch_and_records_who(tmp_path):
    env = _project(tmp_path, _DOUBLE, _CLAIMS)
    _verify(tmp_path, env)
    key = "spkg.mod.double"
    rec = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    # a change mathema did not stamp (here a hand flip; a merge is the
    # real case) trips the mismatch
    rec.write_text(rec.read_text().replace('"proven"', '"holds"', 1))
    assert "checksum no longer matches" in _verify(tmp_path, env).stdout
    # a human vouches for the current contents; no pin configured, so no
    # gate, but the reconcile is recorded
    r = _accept(tmp_path, env, "spkg.mod.double", "--as", "reconciled", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "reconciled" in r.stdout
    body = rec.read_text()
    assert "reconciled:" in body                  # the vow is in the record
    # and the warning is gone on the next sweep
    assert "checksum no longer matches" not in _verify(tmp_path, env).stdout


def test_record_states_pin_none_when_unpinned(tmp_path):
    # a machine-verified record with no human sign-off says so explicitly,
    # rather than leaving the reader to infer it from a missing field
    env = _project(tmp_path, _DOUBLE, _CLAIMS)
    _verify(tmp_path, env)
    body = (tmp_path / ".mathema" / "verified"
            / "spkg.mod.double.yaml").read_text()
    assert 'pin: "none"' in body


def test_breaking_change_flows_to_historical_acceptance(tmp_path):
    env = _project(tmp_path, _DOUBLE, _CLAIMS)
    _verify(tmp_path, env)
    # the function changes out from under the claim (a rename alone no
    # longer breaks anything: `f(x) == 2*x` quantifies its own x and
    # applies f positionally, so it is true of any spelling of
    # doubling; the regression has to be real)
    _project(tmp_path, """
def double(value: float) -> float:
    \"\"\"Triples, these days.\"\"\"
    return 3.0 * value
""", "spkg.mod.double:\n  claims: []\n")
    r = _verify(tmp_path, env)
    key = "spkg.mod.double"
    rec = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    body = rec.read_text()
    assert "doubles" in body                 # membership survived the change
    # accept it as historical
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['accept', 'spkg.mod.double', 'doubles', "
         f"'--as', 'historical', '--by', 'lovelace', '--yes', "
         f"'--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    body = rec.read_text()
    assert "historical:" in body
    # and it never resurrects as a live claim
    r = _verify(tmp_path, env)
    import yaml
    doc = yaml.safe_load(rec.read_text())
    entry = doc["spkg.mod.double"]
    assert all(c.get("name") != "doubles" for c in entry.get("claims") or [])
    assert any(h.get("name") == "doubles"
               for h in entry.get("historical") or [])


def test_reauthored_verified_claim_needs_supersession(tmp_path):
    # the three-tier conflict model: once a claim is VERIFIED, the
    # record wins; re-authoring it (docstring or declared file) is
    # flagged, the verified version keeps adjudicating, and adopting
    # the change is the explicit `--as superseded` acceptance
    env = _project(tmp_path, _DOUBLE, _CLAIMS)
    _verify(tmp_path, env)
    # re-author the claim with a wider region
    (tmp_path / "claims" / "c.claims.yaml").write_text(
        "spkg.mod.double:\n"
        "  claims:\n"
        "    - name: doubles\n"
        "      statement: 'for x in [0,9], f(x) == 2*x'\n"
        "      route: derive\n")
    r = _verify(tmp_path, env)
    assert r.returncode == 1
    assert "--as superseded" in r.stdout
    # accept the supersession
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['accept', 'spkg.mod.double', 'doubles', "
         f"'--as', 'superseded', '--by', 'lovelace', '--yes', "
         f"'--root', {str(tmp_path)!r}]))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    import yaml
    key = "spkg.mod.double"
    rec = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    entry = yaml.safe_load(rec.read_text())["spkg.mod.double"]
    assert any(sup.get("name") == "doubles"
               for sup in entry.get("superseded") or [])
    # the authored version now adjudicates and becomes the live claim
    r = _verify(tmp_path, env)
    assert r.returncode == 0, r.stdout + r.stderr
    entry = yaml.safe_load(rec.read_text())["spkg.mod.double"]
    live = next(c for c in entry["claims"] if c.get("name") == "doubles")
    assert live["verdict"] == "proven"
    assert "9" in (live.get("condition") or "")     # the new region
    assert any(sup.get("name") == "doubles"         # history retained
               for sup in entry.get("superseded") or [])


def test_scope_intent_acceptance_module_and_project(tmp_path):
    env = _project(tmp_path, '''
"""Utilities.

Intent:
    Toy module for scope acceptance.
"""

def double(x: float) -> float:
    """Doubles."""
    return 2.0 * x
''', _CLAIMS)
    (tmp_path / "README.md").write_text(
        "# demo\n\n## Intent\n\nA toy project.\n")
    for key in ("spkg.mod", "__project__"):
        r = subprocess.run(
            [sys.executable, "-c",
             "import sys; from mathema.cli import main; "
             f"sys.exit(main(['accept', {key!r}, '--intent', "
             f"'--by', 'lovelace', '--yes', '--root', {str(tmp_path)!r}]))"],
            cwd=str(tmp_path), capture_output=True, text=True, env=env)
        assert r.returncode == 0, key + ": " + r.stdout + r.stderr
    meta = (tmp_path / ".mathema" / "meta" / "intent.yaml").read_text()
    assert "spkg.mod" in meta and "__project__" in meta
    # the index reports the rung
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['docsync', 'spkg', '--root', {str(tmp_path)!r}, "
         f"'--yes']))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    idx = (tmp_path / ".mathema" / "index.yaml").read_text()
    assert "accepted: \"documented\"" in idx or "accepted: documented" in idx


_FIELD_FN = """
from typing import Literal


def scale_law(r: float, scale: Literal["linear", "info"]) -> float:
    \"\"\"Distance on a named scale.\"\"\"
    if scale == "linear":
        return 1.0 - r
    return 1.0 - r * r
"""

_FIELD_CLAIMS = """
spkg.mod.scale_law:
  claims:
    - name: linear_scale
      statement: 'for r in [0,1], scale in {"linear"}, f(r, scale) == 1 - r'
      route: derive
    - name: bounded
      statement: 'assuming is_defined(f), for r in [0,1], scale in {"linear", "info"}, abs(f(r, scale)) <= 1'
"""


def _verify_all(tmp_path, env):
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}, '--all']))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def _claims_block(record_text: str) -> str:
    """The record with its run-stamped lineage lines removed, so two
    runs compare on what was adjudicated, not on when."""
    return "\n".join(line for line in record_text.splitlines()
                     if not line.strip().startswith(("date:", "commit:")))


def test_a_committed_store_survives_its_second_run(tmp_path):
    """The original field failure, end to end: a finite string domain
    and a definedness premise, verified against a committed store,
    twice. The second run (forced with --all) must reach the same
    verdicts with no supersession report; the record must not move
    except for the date stamp. Before the canonical-text work the
    second run reported the claims re-authored, adjudicated stripped
    versions, and falsified one from an input its domain excludes."""
    env = _project(tmp_path, _FIELD_FN, _FIELD_CLAIMS)
    (tmp_path / "claims" / "c.claims.yaml").write_text(_FIELD_CLAIMS)
    r1 = _verify(tmp_path, env)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    rec = tmp_path / ".mathema" / "verified" / "spkg.mod.scale_law.yaml"
    first = rec.read_text()
    import yaml
    rows = {c["name"]: c for c in
            yaml.safe_load(first)["spkg.mod.scale_law"]["claims"]}
    assert rows["linear_scale"]["verdict"] in ("proven", "holds")
    # the finite set survives into the self-contained statement
    assert 'scale in {"linear"}' in rows["linear_scale"]["statement"]
    # the premise survives, arrow-free: the function has no raise
    # region, so there is no region to pin and no prose stand-in
    assert rows["bounded"]["statement"].startswith("assuming f is defined,")
    assert "-->" not in rows["bounded"]["statement"]

    r2 = _verify_all(tmp_path, env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "re-authored" not in r2.stdout
    assert "invalidated" not in rec.read_text()
    assert _claims_block(rec.read_text()) == _claims_block(first)


def test_the_store_is_byte_identical_across_roots(tmp_path):
    """Two fresh checkouts of the same project write the same record,
    byte for byte, once the run-stamped lineage lines are set aside.
    A committed artifact that drifts between machines is worse than
    none."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    env_a = _project(a, _FIELD_FN, _FIELD_CLAIMS)
    env_b = _project(b, _FIELD_FN, _FIELD_CLAIMS)
    assert _verify(a, env_a).returncode == 0
    assert _verify(b, env_b).returncode == 0
    rec_a = (a / ".mathema" / "verified" / "spkg.mod.scale_law.yaml").read_text()
    rec_b = (b / ".mathema" / "verified" / "spkg.mod.scale_law.yaml").read_text()
    assert _claims_block(rec_a) == _claims_block(rec_b)


def test_records_carry_no_absolute_paths(tmp_path):
    """Every `file:` a record states is root-relative; a dependency
    outside the root (the stdlib, site-packages) states its dotted
    `key` and no file at all. Committed, an absolute path breaks on
    every other checkout and diffs per machine."""
    import os

    import yaml

    fn_body = """
import math


def _floor_margin(r: float) -> float:
    \"\"\"How far above the floor.\"\"\"
    return r + 1.0


def total(r: float) -> float:
    \"\"\"A helper call plus a stdlib call.\"\"\"
    return _floor_margin(r) + math.sqrt(r)
"""
    claims = """
spkg.mod._floor_margin:
  claims:
    - name: above_floor
      statement: 'for r in [0, 4], f(r) >= 1'
spkg.mod.total:
  claims:
    - name: floored
      statement: 'for r in [0, 4], f(r) >= 1'
"""
    env = _project(tmp_path, fn_body, claims)
    r = _verify(tmp_path, env)
    assert r.returncode == 0, r.stdout + r.stderr
    doc = yaml.safe_load(
        (tmp_path / ".mathema" / "verified" / "spkg.mod.total.yaml")
        .read_text())
    deps = doc["spkg.mod.total"].get("dependencies") or []
    assert deps, "the fixture calls a helper; dependency rows are expected"
    for dep in deps:
        f = dep.get("file")
        assert f is None or not os.path.isabs(f), dep
    in_repo = [d for d in deps if d.get("file")]
    assert any(d["file"].startswith("spkg") for d in in_repo), deps

    # the out-of-root branch, stated directly: a site-packages path
    # is dropped rather than written as a ../../.. walk
    from mathema.spec import _relativize_record_paths
    spec = {"dependencies": [
        {"key": "scipy.special.gamma",
         "file": "/usr/local/lib/python3.12/site-packages/scipy/special.py"},
        {"key": "spkg.mod._floor_margin",
         "file": str(tmp_path / "spkg" / "mod.py")}]}
    _relativize_record_paths(spec, str(tmp_path))
    outside, inside = spec["dependencies"]
    assert "file" not in outside and outside["key"] == "scipy.special.gamma"
    assert inside["file"] == os.path.join("spkg", "mod.py")
