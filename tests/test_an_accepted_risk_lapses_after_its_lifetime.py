# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A risk acceptance can carry a lifetime. With
`acceptance: {accepted_risk_lifetime_days: N}` in
`.mathema/meta/policy.yaml`, every risk acceptance written from then on
(`accept --as risk`, and a risk sign-off on a transition) records the
date it expires, N days after it is written. From that date the
acceptance has lapsed: the claim fails again in both modes, and its
line names the date and the command that accepts it again. Without the
key nothing expires, an acceptance written before the key was set
keeps no expiry, and evidence acceptances never expire."""
import datetime
from pathlib import Path

import yaml

import mathema
from mathema.auth import accepted_risk_expiry
from mathema.records import Probe
from mathema.transitions import load_actions, open_transitions
from mathema.verify import _accepted_risk, _lapsed_risk, gate

_ACTIONS = load_actions("/nonexistent")


def _square(x: float) -> float:
    """Square."""
    return x * x


def _record(root, verdict, key="t.f"):
    from mathema.spec import record
    facts = mathema.analyze(_square)
    return record(mathema.Record(facts=facts, probes=[
        Probe("nonneg", "f(x) >= 0", verdict, route="derive")]),
        key=key, root=root)


def _stored(root, key="t.f"):
    doc = yaml.safe_load((Path(root) / ".mathema" / "verified"
                          / f"{key}.yaml").read_text())
    return doc[key]


def _claim(root, key="t.f"):
    return {c["name"]: c for c in _stored(root, key)["claims"]}["nonneg"]


def _policy(root, text):
    meta = Path(root) / ".mathema" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "policy.yaml").write_text(text)


def _in(days):
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


# --- the policy key --------------------------------------------------------

def test_the_lifetime_gives_the_date_an_acceptance_written_today_expires():
    assert accepted_risk_expiry({}, "2026-11-11") is None
    assert accepted_risk_expiry({"accepted_risk_lifetime_days": 30},
                                "2026-11-11") == "2026-12-11"


# --- writing ---------------------------------------------------------------

def test_accept_as_risk_records_its_expiry_under_a_lifetime(tmp_path):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    root = str(tmp_path)
    _record(root, "unknown")
    _policy(root, "acceptance:\n  accepted_risk_lifetime_days: 30\n")
    apply_acceptance(plan_acceptance(root, "t.f", "nonneg", "risk", by="aaron"))
    assert _claim(root)["accepted"]["expires"] == _in(30)


def test_accept_as_risk_records_no_expiry_without_a_lifetime(tmp_path):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    root = str(tmp_path)
    _record(root, "unknown")
    apply_acceptance(plan_acceptance(root, "t.f", "nonneg", "risk", by="aaron"))
    assert "expires" not in _claim(root)["accepted"]


def test_an_evidence_acceptance_records_no_expiry_under_a_lifetime(tmp_path):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    root = str(tmp_path)
    _record(root, "holds")
    _policy(root, "acceptance:\n  accepted_risk_lifetime_days: 30\n")
    apply_acceptance(plan_acceptance(root, "t.f", "nonneg", "evidence",
                                     by="aaron"))
    assert "expires" not in _claim(root)["accepted"]


def test_a_risk_sign_off_records_its_expiry_under_a_lifetime(tmp_path):
    from mathema.acceptance import (apply_transition_acknowledgement,
                                    plan_transition_acknowledgement)
    root = str(tmp_path)
    _record(root, "proven")
    _record(root, "unknown")
    _policy(root, "acceptance:\n  accepted_risk_lifetime_days: 7\n")
    apply_transition_acknowledgement(
        plan_transition_acknowledgement(root, "t.f", ["nonneg"], by="aaron"))
    (t,) = _claim(root)["meta"]["mathema.transitions"]
    assert t["acknowledged"]["expires"] == _in(7)


def test_a_plain_acknowledgement_records_no_expiry_under_a_lifetime(tmp_path):
    from mathema.acceptance import (apply_transition_acknowledgement,
                                    plan_transition_acknowledgement)
    root = str(tmp_path)
    _record(root, "proven")
    _record(root, "holds")
    _policy(root, "acceptance:\n  accepted_risk_lifetime_days: 7\n")
    apply_transition_acknowledgement(
        plan_transition_acknowledgement(root, "t.f", ["nonneg"], by="aaron"))
    (t,) = _claim(root)["meta"]["mathema.transitions"]
    assert "expires" not in t["acknowledged"]


# --- reading ---------------------------------------------------------------

_ENTRY = {"claims": [
    {"name": "old", "verdict": "skipped:unknown_but_accepted",
     "accepted": {"as": "risk", "at": "2026-01-01"}},
    {"name": "live", "verdict": "skipped:unknown_but_accepted",
     "accepted": {"as": "risk", "at": "2026-11-01", "expires": "2026-12-01"}},
    {"name": "gone", "verdict": "skipped:unknown_but_accepted",
     "accepted": {"as": "risk", "at": "2026-10-01", "expires": "2026-11-01"}}]}


def test_an_acceptance_lapses_on_its_expiry_date_and_one_without_never_does():
    assert _accepted_risk(_ENTRY, today="2026-11-11") == {"old", "live"}
    assert _lapsed_risk(_ENTRY, today="2026-11-11") == {"gone": "2026-11-01"}
    assert _lapsed_risk(_ENTRY, today="2026-10-31") == {}
    assert _lapsed_risk(_ENTRY, today="2026-12-01") == {
        "live": "2026-12-01", "gone": "2026-11-01"}


def test_a_lapsed_accepted_risk_fails_in_both_modes_naming_date_and_command():
    for strict in (True, False):
        for claims in ([Probe("gone", "s", "unknown")], _ENTRY["claims"][2:]):
            r = gate(claims, strict=strict, key="t.f",
                     accepted_risk=_accepted_risk(_ENTRY, today="2026-11-11"),
                     lapsed_risk=_lapsed_risk(_ENTRY, today="2026-11-11"),
                     today="2026-11-11")
            assert r.owned == 0 and r.unknown == 1
            assert r.problems == [
                "gone accepted risk expired on 2026-11-01; to accept it "
                "again, run: mathema accept t.f gone --as risk"]


def test_a_current_and_an_unexpiring_accepted_risk_pass():
    r = gate(_ENTRY["claims"][:2], strict=True, key="t.f",
             accepted_risk=_accepted_risk(_ENTRY, today="2026-11-11"),
             lapsed_risk=_lapsed_risk(_ENTRY, today="2026-11-11"),
             today="2026-11-11")
    assert r.problems == [] and r.owned == 2


def _signed(expires=None):
    ack = {"at": "2026-10-01", "by": "aaron", "as": "risk", "level": "proven"}
    if expires:
        ack["expires"] = expires
    return {"name": "c", "verdict": "unknown", "meta": {"mathema.transitions": [
        {"from": "proven", "to": "unknown", "kind": "weakened",
         "cause": "this function changed", "at": "2026-10-01",
         "acknowledged": ack}]}}


def test_a_lapsed_risk_sign_off_reopens_and_fails_in_both_modes():
    for strict in (True, False):
        r = gate([_signed("2026-11-01")], strict=strict, key="t.f",
                 transition_actions=_ACTIONS, today="2026-11-11")
        assert r.owned == 0 and r.transitions == 1
        assert ("c accepted risk at proven expired on 2026-11-01; to accept "
                "it again, run: mathema accept t.f c --transition") in r.problems


def test_a_current_or_unexpiring_risk_sign_off_stays_accepted_risk():
    for c in (_signed("2026-12-01"), _signed()):
        r = gate([c], strict=True, key="t.f", transition_actions=_ACTIONS,
                 today="2026-11-11")
        assert r.problems == [] and r.owned == 1


def test_a_lapsed_risk_sign_off_is_open_to_accept_again():
    meta = _signed("2026-11-01")["meta"]
    assert open_transitions(meta) == []
    assert len(open_transitions(meta, today="2026-11-11")) == 1
    assert open_transitions(meta, today="2026-10-31") == []


def test_accepting_a_lapsed_sign_off_again_writes_a_fresh_one(tmp_path):
    from mathema.acceptance import (apply_transition_acknowledgement,
                                    plan_transition_acknowledgement)
    root = str(tmp_path)
    _record(root, "proven")
    _record(root, "unknown")
    path = Path(root) / ".mathema" / "verified" / "t.f.yaml"
    doc = yaml.safe_load(path.read_text())
    (t,) = doc["t.f"]["claims"][0]["meta"]["mathema.transitions"]
    t["acknowledged"] = {"at": "2026-01-01", "by": "aaron", "as": "risk",
                         "level": "proven", "expires": "2026-02-01"}
    path.write_text(yaml.safe_dump(doc))
    apply_transition_acknowledgement(
        plan_transition_acknowledgement(root, "t.f", ["nonneg"], by="aaron"))
    (t,) = _claim(root)["meta"]["mathema.transitions"]
    assert t["acknowledged"]["at"] == datetime.date.today().isoformat()
    assert "expires" not in t["acknowledged"]


def test_accepting_a_lapsed_risk_again_writes_a_fresh_one(tmp_path):
    from mathema.acceptance import apply_acceptance, plan_acceptance
    root = str(tmp_path)
    _record(root, "unknown")
    _policy(root, "acceptance:\n  accepted_risk_lifetime_days: 30\n")
    apply_acceptance(plan_acceptance(root, "t.f", "nonneg", "risk", by="aaron"))
    path = Path(root) / ".mathema" / "verified" / "t.f.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["t.f"]["claims"][0]["accepted"]["expires"] = "2026-01-01"
    path.write_text(yaml.safe_dump(doc))
    assert _lapsed_risk(_stored(root)) == {"nonneg": "2026-01-01"}
    apply_acceptance(plan_acceptance(root, "t.f", "nonneg", "risk", by="aaron"))
    assert _claim(root)["accepted"]["expires"] == _in(30)
    assert _lapsed_risk(_stored(root)) == {}
