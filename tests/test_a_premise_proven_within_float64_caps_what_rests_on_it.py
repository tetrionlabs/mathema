# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A proof capped at within_float64 (an exhaustive sweep that could not
be decided exactly at every point, `derive:brute_force:within_float64`)
caps whatever rests on it, wherever the premise comes from: a premise
resolved outside the batch (a verified row under another key, a
compendium row), a row exported to a compendium claims file, and a
compendium row accepted as trusted. The resting proof's route ends
`:within_float64`, its note says why, and `mathema.capped_by` names the
premise; it is never promoted to an exact proof."""
import os
import subprocess
import sys
import textwrap

import yaml

from mathema.conjecture import check_conjectures, claim

WITHIN = "derive:brute_force:within_float64"


def zero_at_zero(x: float) -> float:
    return x * x


def _rest_on(route):
    known = {"other.sq": {"verdict": "proven", "key": "other",
                          "provenance": "other/sq", "route": route}}
    (p,) = check_conjectures(zero_at_zero, [claim(
        "assuming other.sq is proven, for x in {0}, f(x) == 0")],
        known_premises=known)
    return p


def test_an_external_premise_proven_within_float64_caps_the_proof():
    p = _rest_on(WITHIN)
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
    assert p.route.endswith(":within_float64"), p.route
    assert p.meta["mathema.capped_by"] == "other/sq", p.meta
    assert "capped at within_float64" in (p.note or ""), p.note


def test_an_external_premise_proven_exactly_caps_nothing():
    p = _rest_on("derive:brute_force")
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
    assert not p.route.endswith(":within_float64"), p.route
    assert "mathema.capped_by" not in p.meta, p.meta


def test_a_verified_row_resolved_as_a_premise_keeps_its_route():
    from mathema.compendium import external_premises
    verified = {"other": {"entry": {"claims": [
        {"name": "sq", "statement": "for x in {0}, f(x) == 0",
         "verdict": "proven", "route": WITHIN}]}}}
    out = external_premises(".", verified=verified, library_claims={})
    assert out["other.sq"]["route"] == WITHIN, out
    assert out["other.sq"]["verdict"] == "proven", out


def _seed_verified(root, key, claims):
    from mathema.spec import verified_dir, write_yaml
    os.makedirs(verified_dir(str(root)), exist_ok=True)
    write_yaml(os.path.join(verified_dir(str(root)), f"{key}.yaml"),
               {key: {"name": key.rsplit(".", 1)[-1], "claims": claims}})


def test_an_exported_row_carries_its_within_float64_route(tmp_path):
    from mathema.compendium.export import export_compendium
    _seed_verified(tmp_path, "lib.mod.f", [
        {"name": "swept", "statement": "for x in {1, 2}, f(x) == x / 10",
         "verdict": "proven", "route": WITHIN},
        {"name": "exact", "statement": "for x in {1, 2}, f(x) == x / 2",
         "verdict": "proven", "route": "derive:brute_force"}])
    rows = {r["name"]: r for r in
            export_compendium("lib", root=str(tmp_path))["lib.mod.f"]["claims"]}
    assert rows["swept"]["meta"] == {
        "mathema.compendium_claimed": "proven",
        "mathema.compendium_route": WITHIN}, rows["swept"]
    assert rows["exact"]["meta"] == {
        "mathema.compendium_claimed": "proven"}, rows["exact"]


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _sweep(root):
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


def test_a_trusted_row_claimed_within_float64_caps_what_rests_on_it(tmp_path):
    _write(tmp_path / "spkg" / "__init__.py", "")
    _write(tmp_path / "spkg" / "mod.py", '''
        def widened(x: float) -> float:
            """x, widened a little."""
            return 1.1 * x
    ''')
    _write(tmp_path / "claims" / "math.claims.yaml", f"""
        compendium: math
        versions: "*"
        math.log:
          claims:
            - name: log_increasing
              statement: 'for x in (0, 100], d(f(x), x) > 0'
              meta:
                mathema.compendium_claimed: proven
                mathema.compendium_route: {WITHIN}
    """)
    _write(tmp_path / "claims" / "c.claims.yaml", """
        spkg.mod.widened:
          claims:
            - name: rests
              statement: 'assuming log_increasing is proven, for x in [0, 4], f(x) <= 5'
    """)
    first = _sweep(tmp_path)
    assert (tmp_path / ".mathema" / "verified" / "math.log.yaml").exists(), \
        first.stdout + first.stderr
    from mathema.acceptance import apply_acceptance, plan_acceptance
    plan = plan_acceptance(str(tmp_path), "math.log", "log_increasing",
                           "trusted", by="test")
    assert plan["new_verdict"] == "proven"
    assert plan["accepted"]["route"] == WITHIN, plan["accepted"]
    apply_acceptance(plan)
    row = _rows(tmp_path, "math.log")["log_increasing"]
    assert (row["verdict"], row["route"]) == ("proven", WITHIN), row
    for other in ("log_monotone",):
        if other in _rows(tmp_path, "math.log"):
            apply_acceptance(plan_acceptance(str(tmp_path), "math.log",
                                             other, "trusted", by="test"))
    _sweep(tmp_path)
    resting = _rows(tmp_path, "spkg.mod.widened")["rests"]
    assert resting["verdict"] == "proven", (resting["verdict"],
                                            resting.get("note"))
    assert resting["route"].endswith(":within_float64"), resting["route"]
    assert resting["meta"]["mathema.capped_by"], resting["meta"]
