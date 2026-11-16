# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record stored with a `<name>[float]` computation row and an
acceptance on that row, written by the code of the day
(`scripts/make_companion_record_fixture.py`, records under
`tests/data/companion_record/verified/`), reads and verifies clean, and
its claims fingerprint, its integrity checksum and its acceptance key
are what they were when it was written.

The records were written by mathema 0.6.5 (the release tag v0.6.5; the
code of that tag and of the base this branch is on differ only in the
version string), schema 0.3.0; each carries `generated_by: "mathema 0.6.5"`.

`companionfix.scale` accepts `doubles[float]` as a risk and
`companionfix.scale_checked` accepts it as evidence.
"""
import pathlib
import shutil

import pytest
import yaml

from mathema.acceptance import (UnknownAcceptanceTarget, _claims_fingerprint_now,
                                carry_acceptance, plan_acceptance)
from mathema.spec import claims_fingerprint, integrity_checksum, integrity_matches
from mathema.verify import _accepted_risk, verify_project

FIXTURE = pathlib.Path(__file__).resolve().parent / "data" / "companion_record"
RISK = "companionfix.scale"
EVIDENCE = "companionfix.scale_checked"
ROW = "doubles[float]"

#: what the fixture's identity block holds
PINNED = {RISK: {"fingerprint": "54700bd9f595",
                 "integrity": "v2:4cbe0168e15be157",
                 "form": "py:d201b59da92d"},
          EVIDENCE: {"fingerprint": "54700bd9f595",
                     "integrity": "v2:961b7b370d0c2cdb",
                     "form": "py:5acc479746c6"}}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    root = tmp_path / "project"
    (root / ".mathema").mkdir(parents=True)
    shutil.copy(FIXTURE / "companionfix.py", root / "companionfix.py")
    shutil.copytree(FIXTURE / "verified", root / ".mathema" / "verified")
    monkeypatch.syspath_prepend(str(root))
    return root


def _record(root, key):
    path = root / ".mathema" / "verified" / f"{key}.yaml"
    return yaml.safe_load(path.read_text())[key]


def _row(entry, name):
    return next(c for c in entry["claims"] if c["name"] == name)


@pytest.mark.parametrize("key", [RISK, EVIDENCE])
def test_the_stored_identity_is_what_was_written(project, key):
    identity = _record(project, key)["identity"]
    assert identity["claims_fingerprint"] == PINNED[key]["fingerprint"]
    assert identity["integrity"] == PINNED[key]["integrity"]
    assert identity["form"] == PINNED[key]["form"]


@pytest.mark.parametrize("key", [RISK, EVIDENCE])
def test_the_integrity_checksum_matches_and_is_the_pinned_value(project, key):
    entry = _record(project, key)
    assert integrity_matches(entry) is True
    assert integrity_checksum(entry) == PINNED[key]["integrity"]


@pytest.mark.parametrize("key", [RISK, EVIDENCE])
def test_the_claims_fingerprint_recomputes_to_the_pinned_value(project, key):
    entry = _record(project, key)
    assert _claims_fingerprint_now(str(project), key, entry) == \
        PINNED[key]["fingerprint"]


def test_the_fingerprint_covers_the_claims_name_and_not_the_row_the_run_added():
    # the stored fingerprint is over the declared claim `doubles`; the
    # computation row `doubles[float]` the run added is not in it
    said = {"name": "doubles", "statement": "for x in [-10, 10], f(x) == 2 * x",
            "route": "derive"}
    assert claims_fingerprint([said]) != claims_fingerprint(
        [{**said, "name": "doubles[float]"}])


def test_a_sweep_leaves_the_records_as_they_were_and_finds_no_problem(project):
    before = {k: (project / ".mathema" / "verified" / f"{k}.yaml").read_bytes()
              for k in (RISK, EVIDENCE)}
    out = verify_project(root=str(project), strict=False)
    assert out.problems == []
    assert not any("checksum" in ln for ln in out.lines)
    assert any("fresh" in ln and RISK in ln for ln in out.lines)
    assert any("fresh" in ln and EVIDENCE in ln for ln in out.lines)
    for key, text in before.items():
        path = project / ".mathema" / "verified" / f"{key}.yaml"
        assert path.read_bytes() == text


def test_a_strict_sweep_counts_the_accepted_risk_on_the_computation_row(project):
    out = verify_project(root=str(project))
    assert any(RISK in ln and "1 accepted-risk claim(s)" in ln
               for ln in out.lines)


def test_the_acceptance_is_keyed_to_the_row_name_and_the_form(project):
    risk = _record(project, RISK)
    accepted = _row(risk, ROW)["accepted"]
    assert accepted["as"] == "risk"
    assert accepted["form"] == risk["identity"]["form"]
    assert _row(risk, ROW)["verdict"] == "skipped:unknown_but_accepted"
    assert _accepted_risk(risk) == frozenset({ROW})
    evidence = _record(project, EVIDENCE)
    assert _row(evidence, ROW)["accepted"]["as"] == "evidence"
    assert _row(evidence, ROW)["accepted"]["form"] == evidence["identity"]["form"]
    assert _accepted_risk(evidence) == frozenset()


def test_the_companion_row_carries_the_fields_that_name_its_claim(project):
    entry = _record(project, RISK)
    row = _row(entry, ROW)
    assert row["meta"]["mathema.companion_of"] == "doubles"
    assert row["meta"]["mathema.family"] == "is_numerically_stable"
    assert row["route"] == "probe"
    assert _row(entry, "doubles")["meta"]["mathema.float_companion"] == ROW
    assert row["statement"] == _row(entry, "doubles")["statement"]


def test_the_acceptance_resolves_to_its_row_by_name(project):
    plan = plan_acceptance(str(project), RISK, ROW, "risk")
    assert plan["claim"]["name"] == ROW
    assert plan["claim"]["accepted"]["as"] == "risk"
    with pytest.raises(UnknownAcceptanceTarget, match="no claim named"):
        plan_acceptance(str(project), RISK, "doubles[float32]", "risk")


def test_a_fresh_unknown_row_takes_the_stored_risk_acceptance_by_name(
        project, tmp_path):
    stored = project / ".mathema" / "verified" / f"{RISK}.yaml"
    fresh = {"identity": {"form": PINNED[RISK]["form"]},
             "claims": [{"name": ROW, "verdict": "unknown"}]}
    carry_acceptance(fresh, RISK, str(stored))
    row = fresh["claims"][0]
    assert row["verdict"] == "skipped:unknown_but_accepted"
    assert row["accepted"]["as"] == "risk"
    changed = {"identity": {"form": "py:other"},
               "claims": [{"name": ROW, "verdict": "unknown"}]}
    carry_acceptance(changed, RISK, str(stored))
    assert changed["claims"][0]["verdict"] == "unknown"
    assert changed["claims"][0]["accepted"]["stale"] is True

