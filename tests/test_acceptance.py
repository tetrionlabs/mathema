# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The acceptance layer: human decisions over adjudicated evidence.
The vocabulary rules are the tests; holds accepts as evidence,
unknown/skipped as owned risk (strict mode still refuses), falsified
ONLY as a discovery (there is no accepting a bug: the code changes and
the recorded counterexample replays until the claim proves), proven
needs nothing. Acceptance survives re-adjudication, goes stale when
the function's form changes, and every classification change lands in
the history."""
import os
import subprocess
import sys

import pytest
import yaml

from mathema.acceptance import (
    AcceptanceError, apply_acceptance, carry_acceptance, invert_conjecture,
    plan_acceptance,
)


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = _repo_root() + (os.pathsep + env["PYTHONPATH"]
                                        if env.get("PYTHONPATH") else "")
    return env


def _verify(root):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--root', {str(root)!r}, '--lenient']))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=_env())


def _seed(root, funcs_path, names):
    script = (f"import sys\nsys.path.insert(0, {str(funcs_path.parent)!r})\n"
              "import mathema, funcs\n"
              + "\n".join(f"mathema.write_spec(funcs.{n}, root={str(root)!r})"
                          for n in names))
    r = subprocess.run([sys.executable, "-c", script], cwd=str(root),
                       capture_output=True, text=True, env=_env())
    assert r.returncode == 0, r.stderr


def _record(root, key):
    with open(os.path.join(str(root), ".mathema", "verified", f"{key}.yaml")) as fh:
        return (yaml.safe_load(fh) or {})[key]


def _claim_named(entry, name):
    return next(c for c in entry.get("claims") or [] if c.get("name") == name)


def _setup_repo(tmp_path, body="    return abs(x)\n", claims_yaml=None):
    funcs = tmp_path / "funcs.py"
    funcs.write_text("def keep(x: float) -> float:\n" + body)
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "keep.yaml").write_text(claims_yaml or "")
    _seed(tmp_path, funcs, ["keep"])
    r = _verify(tmp_path)
    # verify exits nonzero when a claim is a problem (falsified,
    # unverifiable-under-strict); what setup needs is the record
    assert os.path.exists(os.path.join(str(tmp_path), ".mathema", "verified",
                                       "funcs.keep.yaml")), r.stdout + r.stderr
    return funcs


def test_invert_conjecture_inverts_only_sound_shapes():
    # a bare single relation flips, quantifier prefix carried intact
    ok, why = invert_conjecture("for x in [-5, 5], f(x) >= 0", "nonneg")
    assert (ok, why) == ("for x in [-5, 5], f(x) < 0", None)
    ok, _ = invert_conjecture("f(x) == x", "id")
    assert ok == "f(x) != x"
    # a bare predicate inverts through the grammar's not form
    ok, _ = invert_conjecture("for x in [-1, 1], is_pole_safe(x)",
                              "is_pole_safe[x]")
    assert ok == "for x in [-1, 1], not is_pole_safe(x)"


def test_invert_conjecture_refuses_every_unsound_shape():
    # the shapes the old text-level flipper corrupted: each refuses
    # with its reason, and none can corrupt a statement any more
    ok, why = invert_conjecture("for mi in [0, 1], 0 <= f(mi) < 1",
                                "strictly_below_one")
    assert ok is None and "chained" in why
    ok, why = invert_conjecture(
        "assuming x > 1, for x in [0.1, 5], f(x) >= 1", "conditional")
    assert ok is None
    ok, why = invert_conjecture(
        "let c be [1, 2], for x in [0, 1], f(x) <= c", "let_bound")
    assert ok is None and "let" in why
    ok, why = invert_conjecture("not is_pole_safe(x)", "is_pole_safe[x]")
    assert ok is None and "negated" in why
    ok, why = invert_conjecture("just words", "odd")
    assert ok is None and "parse" in why
    ok, why = invert_conjecture("raises(f(x), ValueError)", "guard")
    assert ok is None
    ok, why = invert_conjecture("", "empty")
    assert ok is None


def test_holds_accepts_as_evidence_and_records_the_moment(tmp_path):
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: nonneg\n      statement: \"for x in [-5, 5], f(x) >= 0\"\n"
        "      route: probe\n"))
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "nonneg", "evidence",
                           by="lovelace", note="enough for release")
    summary = apply_acceptance(plan)
    assert "accepted evidence" in summary
    claim = _claim_named(_record(tmp_path, "funcs.keep"), "nonneg")
    assert claim["accepted"]["as"] == "evidence"
    assert claim["accepted"]["by"] == "lovelace"
    assert claim["accepted"]["n"] == claim["n"]
    assert claim["accepted"]["form"]
    assert claim["acceptance_history"][0]["verdict"] == "holds"
    # wrong vocabulary for a holds claim
    with pytest.raises(AcceptanceError, match="as evidence"):
        plan_acceptance(str(tmp_path), "funcs.keep", "nonneg", "risk")


def test_unknown_accepts_as_risk_and_reclassifies(tmp_path):
    # a derive claim the engine can't settle stays unknown
    _setup_repo(tmp_path, body=(
        "    total = x\n"
        "    while total > 1.0:\n"
        "        total = total / 2.0\n"
        "    return total\n"),
                claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: mystery\n"
        "      statement: \"for x in [-1, 1], f(x) == integrate(f(t), t, 0, x)\"\n"
        "      route: derive\n"))
    entry = _record(tmp_path, "funcs.keep")
    claim = _claim_named(entry, "mystery")
    assert claim["verdict"] == "unknown"
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "mystery", "risk", by="lovelace")
    apply_acceptance(plan)
    claim = _claim_named(_record(tmp_path, "funcs.keep"), "mystery")
    assert claim["verdict"] == "skipped:unknown_but_accepted"
    assert claim["meta"]["mathema.previous_verdict"] == "unknown"
    assert claim["accepted"]["as"] == "risk"


def test_falsified_accepts_only_as_discovery(tmp_path):
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: wrong\n      statement: \"for x in [-5, 5], f(x) == x\"\n"
        "      route: probe\n"))
    entry = _record(tmp_path, "funcs.keep")
    assert _claim_named(entry, "wrong")["verdict"] == "falsified"
    # the bug ruling: no accepting a falsification as anything but discovery
    with pytest.raises(AcceptanceError, match="no accepting a bug"):
        plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "evidence")
    with pytest.raises(AcceptanceError, match="never accepted\nas risk"
                       .replace("\n", " ")):
        plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "risk")
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "discovery",
                           by="lovelace", note="abs was the point")
    # abs(x) != x holds at no negative... at every x >= 0 it FAILS, so
    # the mechanical inverse falsifies and is NEVER offered: the
    # discovery records without inventing a wrong correction
    assert "corrected_statement" not in plan
    assert any("no corrected claim is written" in a for a in plan["actions"])
    assert any("--corrected" in a for a in plan["actions"])
    apply_acceptance(plan)
    entry = _record(tmp_path, "funcs.keep")
    assert all(c.get("name") != "wrong" for c in entry["claims"])
    (old,) = entry["discoveries"]
    assert old["name"] == "wrong"
    assert "superseded_by" not in old       # nothing replaced it
    assert all(c.get("name") != "wrong_corrected"
               for c in entry["claims"])
    assert old["counterexample"]            # the witness is retained


def test_discovery_offers_only_a_verified_correction(tmp_path):
    # f(x) < 0 on abs falsifies everywhere; its inverse f(x) >= 0 holds
    # everywhere, so the candidate is adjudicated, holds, and is offered
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: neg\n      statement: \"for x in [-5, 5], f(x) < 0\"\n"
        "      route: probe\n"))
    assert _claim_named(_record(tmp_path, "funcs.keep"), "neg")[
        "verdict"] == "falsified"
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "neg", "discovery",
                           by="lovelace")
    assert plan["corrected_statement"].endswith("f(x) >= 0")
    assert plan["corrected_name"] == "neg_corrected"
    from mathema.records import classify_verdict
    assert classify_verdict(plan["corrected_verdict"]) in ("proven", "holds")
    apply_acceptance(plan)
    entry = _record(tmp_path, "funcs.keep")
    (old,) = entry["discoveries"]
    assert old["superseded_by"] == "neg_corrected"
    new = _claim_named(entry, "neg_corrected")
    # the real adjudicated verdict, never an unadjudicated "declared"
    assert classify_verdict(new["verdict"]) in ("proven", "holds")
    assert new["meta"]["mathema.surface"] == "declared"
    assert new["meta"]["mathema.authored"] == {"by": "lovelace"}
    assert new["meta"]["mathema.supporting_witness"] == old["counterexample"]


def test_corrected_flag_adjudicates_and_refuses_a_false_correction(tmp_path):
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: wrong\n      statement: \"for x in [-5, 5], f(x) == x\"\n"
        "      route: probe\n"))
    # a human-stated correction that itself falsifies is refused, with
    # the counterexample named
    with pytest.raises(AcceptanceError, match="itself falsifies"):
        plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "discovery",
                        by="lovelace", corrected="for x in [-5, 5], f(x) < 0")
    # a true one adjudicates and is written with its real verdict
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "discovery",
                           by="lovelace",
                           corrected="for x in [-5, 5], f(x) >= 0")
    from mathema.records import classify_verdict
    assert classify_verdict(plan["corrected_verdict"]) in ("proven", "holds")
    apply_acceptance(plan)
    entry = _record(tmp_path, "funcs.keep")
    new = _claim_named(entry, "wrong_corrected")
    assert new["statement"] == "for x in [-5, 5], f(x) >= 0"


def test_discovery_of_an_uninvertible_claim_is_still_recordable(tmp_path):
    # a chained comparison falsifies (abs(2) = 2 breaks f(x) < 1); the
    # old inverter corrupted these, and worse, refused the acceptance
    # entirely. Now the discovery records, with no correction
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: unit\n      statement: \"for x in [-5, 5], 0 <= f(x) < 1\"\n"
        "      route: probe\n"))
    assert _claim_named(_record(tmp_path, "funcs.keep"), "unit")[
        "verdict"] == "falsified"
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "unit", "discovery")
    assert "corrected_statement" not in plan
    apply_acceptance(plan)
    entry = _record(tmp_path, "funcs.keep")
    (old,) = entry["discoveries"]
    assert old["name"] == "unit" and "superseded_by" not in old


def test_proven_needs_no_acceptance(tmp_path):
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: exact\n      statement: \"f(x) == abs(x)\"\n"
        "      route: derive\n"))
    with pytest.raises(AcceptanceError, match="proof is its own acceptance"):
        plan_acceptance(str(tmp_path), "funcs.keep", "exact", "evidence")


def test_acceptance_survives_reverification_and_goes_stale_on_form_change(tmp_path):
    funcs = _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: nonneg\n      statement: \"for x in [-5, 5], f(x) >= 0\"\n"
        "      route: probe\n"))
    apply_acceptance(plan_acceptance(str(tmp_path), "funcs.keep", "nonneg",
                                     "evidence", by="lovelace"))
    # unchanged code: a forced re-verification carries the acceptance
    # forward untouched
    subprocess.run([sys.executable, "-c",
                    ("import sys; from mathema.cli import main; "
                     f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}, "
                     "'--lenient', '--all']))")],
                   cwd=str(tmp_path), capture_output=True, text=True,
                   env=_env())
    claim = _claim_named(_record(tmp_path, "funcs.keep"), "nonneg")
    assert claim["accepted"]["as"] == "evidence"
    assert not claim["accepted"].get("stale")
    # a changed form: the acceptance was about a different function
    funcs.write_text("def keep(x: float) -> float:\n"
                     "    return abs(x) + 1.0\n")
    _verify(tmp_path)
    claim = _claim_named(_record(tmp_path, "funcs.keep"), "nonneg")
    assert claim["accepted"]["stale"] is True
    assert any(ev.get("event") == "stale" for ev in claim["acceptance_history"])


def test_risk_acceptance_reapplies_on_fresh_unknown_until_form_changes(tmp_path):
    entry = {"identity": {"form": "abc"},
             "claims": [{"name": "gap", "verdict": "unknown"}]}
    prior = {"identity": {"form": "abc"},
             "claims": [{"name": "gap", "verdict": "skipped:unknown_but_accepted",
                         "accepted": {"as": "risk", "form": "abc"},
                         "acceptance_history": [{"as": "risk"}]}]}
    path = tmp_path / "prior.yaml"
    path.write_text(yaml.safe_dump({"k": prior}))
    carry_acceptance(entry, "k", str(path))
    assert entry["claims"][0]["verdict"] == "skipped:unknown_but_accepted"
    # same prior, but the fresh form differs: stale, no reclassification
    entry2 = {"identity": {"form": "DIFFERENT"},
              "claims": [{"name": "gap", "verdict": "unknown"}]}
    carry_acceptance(entry2, "k", str(path))
    assert entry2["claims"][0]["verdict"] == "unknown"
    assert entry2["claims"][0]["accepted"]["stale"] is True


def test_evidence_drift_warns_on_materially_weaker_runs(tmp_path):
    entry = {"identity": {"form": "abc"},
             "claims": [{"name": "held", "verdict": "holds", "n": 12}]}
    prior = {"identity": {"form": "abc"},
             "claims": [{"name": "held", "verdict": "holds", "n": 4000,
                         "accepted": {"as": "evidence", "form": "abc",
                                      "n": 4000}}]}
    path = tmp_path / "prior.yaml"
    path.write_text(yaml.safe_dump({"k": prior}))
    carry_acceptance(entry, "k", str(path))
    drift = entry["claims"][0]["meta"]["mathema.acceptance_evidence_drift"]
    assert "n=4000" in drift and "n=12" in drift


def test_counterexample_replays_until_the_fix_proves(tmp_path):
    # the bug path: falsify, record the witness, fix the code, and the
    # exact witness replays first on re-verification, the old
    # counterexample becomes a claim that now passes.
    funcs = _setup_repo(tmp_path, body="    return x\n", claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: nonneg\n      statement: \"for x in [-5, 5], f(x) >= 0\"\n"
        "      route: probe\n"))
    claim = _claim_named(_record(tmp_path, "funcs.keep"), "nonneg")
    assert claim["verdict"] == "falsified"
    witness = claim["meta"]["mathema.counterexample_args"]
    assert len(witness) == 1 and witness[0] < 0
    funcs.write_text("def keep(x: float) -> float:\n    return abs(x)\n")
    _verify(tmp_path)
    claim = _claim_named(_record(tmp_path, "funcs.keep"), "nonneg")
    assert claim["verdict"] == "holds"
    assert claim["meta"]["mathema.previous_verdict"] == "falsified"


def test_not_form_predicate_adjudicates_by_inversion(tmp_path):
    from mathema.conjecture import check_conjectures, claim as make_claim

    cj = make_claim("not is_pole_safe(x)", route="derive")
    assert cj.relation == "is_pole_safe" and cj.negated

    def divides(x: float) -> float:
        return 1.0 / x

    # the domain includes the pole at 0: the positive claim falsifies,
    # so its not-form proves from the same evidence
    (positive,) = check_conjectures(
        divides, [make_claim("is_pole_safe(x)", name="is_pole_safe[x]",
                             route="derive")], domain={"x": (-1.0, 1.0)})
    (negative,) = check_conjectures(
        divides, [make_claim("not is_pole_safe(x)", name="is_pole_safe[x]",
                             route="derive")], domain={"x": (-1.0, 1.0)})
    assert positive.verdict == "falsified"
    assert negative.verdict == "proven"
    assert negative.statement.startswith("not ")
    # and over a pole-free domain the not-form falsifies
    (negative_safe,) = check_conjectures(
        divides, [make_claim("not is_pole_safe(x)", name="is_pole_safe[x]",
                             route="derive")], domain={"x": (1.0, 2.0)})
    assert negative_safe.verdict == "falsified"


def test_superseded_claim_never_regrows_as_live(tmp_path):
    # after a discovery, the old claim often remains in the DECLARED
    # layer until the author replaces it; re-verification must not
    # re-grow it as a live claim beside its own discovery entry.
    entry = {"identity": {"form": "abc"},
             "claims": [{"name": "old_belief", "verdict": "falsified"},
                        {"name": "kept", "verdict": "holds"}]}
    prior = {"identity": {"form": "abc"},
             "claims": [{"name": "kept", "verdict": "holds"}],
             "discoveries": [{"name": "old_belief", "verdict": "invalidated",
                              "superseded_by": "old_belief_corrected",
                              "accepted": {"as": "discovery"}}]}
    path = tmp_path / "prior.yaml"
    path.write_text(yaml.safe_dump({"k": prior}))
    carry_acceptance(entry, "k", str(path))
    assert [c["name"] for c in entry["claims"]] == ["kept"]
    assert entry["discoveries"][0]["name"] == "old_belief"


# ---- R002: the JSON transport (plan-only unless --yes) ---------------

def _accept_cli(root, *argv):
    import json
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(argv) + ['--root', str(root)]!r}))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(root),
                       capture_output=True, text=True, env=_env())
    return r, (json.loads(r.stdout) if r.stdout.strip() else None)


_RISK_CLAIMS = ("funcs.keep:\n  claims:\n"
                "    - name: nonneg\n"
                "      statement: \"for x in [-5, 5], f(x) >= 0\"\n"
                "      route: probe\n")


def test_accept_json_previews_without_writing_then_applies(tmp_path):
    import hashlib
    _setup_repo(tmp_path, claims_yaml=_RISK_CLAIMS)
    rec = os.path.join(str(tmp_path), ".mathema", "verified",
                       "funcs.keep.yaml")
    before = hashlib.sha256(open(rec, "rb").read()).hexdigest()

    # no --yes: the plan only, and the record untouched on disk
    r, doc = _accept_cli(tmp_path, "accept", "funcs.keep", "nonneg",
                         "--as", "evidence", "--by", "lovelace",
                         "--format", "json")
    assert doc["ok"] is True and doc["applied"] is False
    assert doc["written"] is None and doc["actions"]
    # plan_acceptance hands back the whole live YAML document under
    # "doc"; it must never reach the payload
    assert "doc" not in doc
    assert hashlib.sha256(open(rec, "rb").read()).hexdigest() == before

    # --yes: applied, and the record moves
    r, doc = _accept_cli(tmp_path, "accept", "funcs.keep", "nonneg",
                         "--as", "evidence", "--by", "lovelace", "--yes",
                         "--format", "json")
    assert doc["applied"] is True and doc["written"]
    assert hashlib.sha256(open(rec, "rb").read()).hexdigest() != before


def test_accept_json_reports_a_refusal_as_data(tmp_path):
    _setup_repo(tmp_path, claims_yaml=_RISK_CLAIMS)
    r, doc = _accept_cli(tmp_path, "accept", "funcs.keep", "no_such_claim",
                         "--as", "risk", "--format", "json")
    assert doc["ok"] is False and doc["applied"] is False
    assert "no_such_claim" in doc["error"]
    # a claim that does not exist is a target that does not resolve
    assert r.returncode == 2


def _verify_all(root):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--all', '--lenient', "
              f"'--root', {str(root)!r}]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=_env())


def test_discovery_cleanup_rewrites_the_claims_file(tmp_path):
    # the trap: after a discovery, the declared layer still stated the
    # old law, so the next real adjudication regenerated the
    # falsification a human had already dispositioned. Accepting now
    # rewrites the claims file itself: the retired stanza is replaced
    # by the corrected one
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: wrong\n      statement: \"for x in [-5, 5], f(x) == x\"\n"
        "      route: probe\n"))
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "discovery",
                           by="lovelace",
                           corrected="for x in [-5, 5], f(x) >= 0")
    assert any("rewrite" in a for a in plan["actions"])
    apply_acceptance(plan)
    doc = yaml.safe_load(open(tmp_path / "claims" / "keep.yaml"))
    names = [c["name"] for c in doc["funcs.keep"]["claims"]]
    assert "wrong" not in names and "wrong_corrected" in names
    r = _verify_all(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FAIL" not in r.stdout, r.stdout
    assert "falsified claim" not in r.stdout


def test_retirement_only_removes_the_declared_claim(tmp_path):
    # no correction exists (the mechanical inverse falsifies): the
    # stanza is simply removed, and the sweep stays clean
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: wrong\n      statement: \"for x in [-5, 5], f(x) == x\"\n"
        "      route: probe\n"))
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "discovery")
    assert "corrected_statement" not in plan
    apply_acceptance(plan)
    doc = yaml.safe_load(open(tmp_path / "claims" / "keep.yaml"))
    assert all(c["name"] != "wrong"
               for c in doc["funcs.keep"].get("claims") or [])
    r = _verify_all(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FAIL" not in r.stdout, r.stdout


def test_docstring_declared_discovery_gets_the_verify_note(tmp_path):
    # a docstring cannot be rewritten by an acceptance: verify skips
    # the retired law with a non-fatal note instead of regenerating
    # the falsification
    funcs = tmp_path / "funcs.py"
    funcs.write_text(
        "def keep(x: float) -> float:\n"
        '    """Absolute value.\n\n'
        "    Claims:\n"
        "        wrong [probe]: for x in [-5, 5], f(x) == x\n"
        '    """\n'
        "    return abs(x)\n")
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "keep.yaml").write_text("")
    _seed(tmp_path, funcs, ["keep"])
    _verify(tmp_path)
    assert _claim_named(_record(tmp_path, "funcs.keep"), "wrong")[
        "verdict"] == "falsified"
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "discovery")
    assert any("not declared in any claims file" in a
               for a in plan["actions"])
    apply_acceptance(plan)
    r = _verify_all(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "retired as a discovery" in r.stdout
    assert "FAIL" not in r.stdout, r.stdout


def test_restated_claim_under_a_retired_name_adjudicates(tmp_path):
    # a DIFFERENT law under the retired name is new authorship, not a
    # stale leftover: it adjudicates normally
    _setup_repo(tmp_path, claims_yaml=(
        "funcs.keep:\n  claims:\n"
        "    - name: wrong\n      statement: \"for x in [-5, 5], f(x) == x\"\n"
        "      route: probe\n"))
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "wrong", "discovery")
    apply_acceptance(plan)
    (tmp_path / "claims" / "keep.yaml").write_text(
        "funcs.keep:\n  claims:\n"
        "    - name: wrong\n      statement: \"for x in [-5, 5], f(x) >= 0\"\n"
        "      route: probe\n")
    r = _verify_all(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "retired as a discovery" not in r.stdout
    row = _claim_named(_record(tmp_path, "funcs.keep"), "wrong")
    assert row["verdict"] in ("holds", "proven")
