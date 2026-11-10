# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Verdict transitions: a claim keeps the verdict its latest run found,
and a move from the one before is kept beside it, with its kind and
cause, until a person acknowledges it or the claim recovers; the gate
acts on each open transition by kind and mode; and a record written
before 0.6.5 with the verdict `invalidated` reads as the verdict it
fell to plus the regression."""
import pytest

import mathema
from mathema.records import Probe
from mathema.transitions import (carry, cause_of, kind_of, load_actions,
                                 open_transitions, read_invalidated_verdict,
                                 transition)
from mathema.verify import gate


@pytest.mark.parametrize("before, after, changed, kind", [
    ("proven", "falsified", False, "regressed"),
    ("holds", "falsified", True, "regressed"),
    ("proven", "holds", False, "weakened"),
    ("holds", "unknown", False, "weakened"),
    ("proven", "skipped:timeout", False, "weakened"),
    ("holds", "proven", False, "strengthened"),
    ("unknown", "holds", False, "strengthened"),
    ("falsified", "holds", True, "fixed"),
    ("falsified", "proven", False, "strengthened"),
    ("unknown", "falsified", False, None),
    ("falsified", "unknown", True, None),
    ("holds", "holds", False, None),
    ("unknown", "skipped", False, None),
])
def test_the_kind_of_a_move(before, after, changed, kind):
    assert kind_of(before, after, function_changed=changed) == kind


@pytest.mark.parametrize("triggers, cause", [
    (["form"], "this function changed"),
    (["dependency", "claims"], "this function changed"),
    (["dependency"], "a callee changed"),
    ([], "nothing changed"),
])
def test_the_cause_of_a_move(triggers, cause):
    assert cause_of(triggers) == cause


def test_a_drop_stays_open_until_the_claim_is_back_at_its_level():
    t = transition("proven", "unknown", ["dependency"], commit="abc", at="2026-11-10")
    assert t == {"from": "proven", "to": "unknown", "kind": "weakened",
                 "cause": "a callee changed", "at": "2026-11-10", "commit": "abc"}
    still = carry([t], None, "holds", commit="def", at="2026-11-11")
    assert open_transitions({"mathema.transitions": still}) == [t]
    back = carry([t], None, "proven", commit="def", at="2026-11-11")
    assert open_transitions({"mathema.transitions": back}) == []
    assert back[0]["recovered"] == {"at": "2026-11-11", "commit": "def"}
    assert carry(back, None, "proven", commit="ghi", at="2026-11-12") == []


def test_an_old_invalidated_verdict_reads_as_where_it_fell_plus_the_regression():
    verdict, meta = read_invalidated_verdict("invalidated", {
        "mathema.previous_verdict": "proven", "mathema.regressed_to": "unknown",
        "mathema.last_supported_commit": "abc"})
    assert verdict == "unknown"
    (t,) = open_transitions(meta)
    assert (t["from"], t["to"], t["kind"], t["since"]) == ("proven", "unknown", "weakened", "abc")
    assert read_invalidated_verdict("holds", {}) == ("holds", {})


def _probe(verdict, *transitions):
    return Probe("c", "f(x) >= 0", verdict, route="probe",
                 meta={"mathema.transitions": list(transitions)})


_WEAK = {"from": "proven", "to": "holds", "kind": "weakened",
         "cause": "a callee changed", "at": "2026-11-10"}
_REG = {"from": "holds", "to": "falsified", "kind": "regressed",
        "cause": "nothing changed", "at": "2026-11-10"}


def test_the_gate_fails_a_weakening_in_strict_and_warns_in_lenient():
    actions = load_actions("/nonexistent")
    strict = gate([_probe("holds", _WEAK)], strict=True, transition_actions=actions)
    assert any("weakened proven to holds" in p for p in strict.problems), strict.problems
    lenient = gate([_probe("holds", _WEAK)], strict=False, transition_actions=actions)
    assert lenient.problems == [] and any("weakened" in w for w in lenient.warnings)
    assert lenient.transitions == 1


def test_a_regression_with_nothing_changed_is_said_as_a_contradiction():
    r = gate([_probe("falsified", _REG)], strict=False,
             transition_actions=load_actions("/nonexistent"))
    assert any("two runs disagree" in p for p in r.problems), r.problems


def test_an_acknowledged_transition_does_not_gate():
    done = dict(_WEAK, acknowledged={"by": "aaron", "at": "2026-11-10"})
    r = gate([_probe("holds", done)], strict=True,
             transition_actions=load_actions("/nonexistent"))
    assert r.problems == [] and r.transitions == 0


def test_the_policy_sets_the_action_per_kind_and_mode(tmp_path):
    meta = tmp_path / ".mathema" / "meta"
    meta.mkdir(parents=True)
    (meta / "policy.yaml").write_text(
        "transitions:\n  weakened: pass\n  regressed: {lenient: warn}\n")
    actions = load_actions(str(tmp_path))
    assert actions["weakened"] == {"strict": "pass", "lenient": "pass"}
    assert actions["regressed"] == {"strict": "fail", "lenient": "warn"}
    (meta / "policy.yaml").write_text("transitions:\n  weakened: ignore\n")
    with pytest.raises(ValueError, match="weakened"):
        load_actions(str(tmp_path))


def test_an_old_invalidated_claim_in_a_record_still_gates_as_its_regression():
    stored = {"name": "c", "statement": "f(x) >= 0", "verdict": "invalidated",
              "meta": {"mathema.previous_verdict": "proven",
                       "mathema.regressed_to": "unknown"}}
    r = gate([stored], strict=False, transition_actions=load_actions("/nonexistent"))
    assert r.unknown == 1 and r.problems


def _record(fn, key, root, verdict):
    from mathema.spec import record
    facts = mathema.analyze(fn)
    return record(mathema.Record(facts=facts, probes=[
        Probe("nonneg", "f(x) >= 0", verdict, route="derive")]), key=key, root=root)


def _stored(root, key):
    import yaml
    from pathlib import Path
    doc = yaml.safe_load((Path(root) / ".mathema" / "verified" / f"{key}.yaml").read_text())
    return {c["name"]: c for c in doc[key]["claims"]}["nonneg"]


def _square(x: float) -> float:
    """Square."""
    return x * x


def test_a_record_keeps_the_fresh_verdict_and_the_transition_beside_it(tmp_path):
    f = _square
    root = str(tmp_path)
    _record(f, "t.f", root, "proven")
    _record(f, "t.f", root, "unknown")
    c = _stored(root, "t.f")
    assert c["verdict"] == "unknown"
    (t,) = open_transitions(c["meta"])
    assert (t["from"], t["to"], t["kind"], t["cause"]) == \
        ("proven", "unknown", "weakened", "nothing changed")
    _record(f, "t.f", root, "unknown")
    assert len(open_transitions(_stored(root, "t.f")["meta"])) == 1
    _record(f, "t.f", root, "proven")
    assert open_transitions(_stored(root, "t.f")["meta"]) == []


def test_accept_transition_acknowledges_the_open_ones_and_the_gate_stops(tmp_path):
    from mathema.acceptance import (AcceptanceError, apply_transition_acknowledgement,
                                    plan_transition_acknowledgement)
    root = str(tmp_path)
    _record(_square, "t.f", root, "proven")
    _record(_square, "t.f", root, "holds")
    plan = plan_transition_acknowledgement(root, "t.f", ["nonneg"], by="aaron")
    assert any("weakened proven to holds" in line for line in plan["lines"])
    assert apply_transition_acknowledgement(plan) == ["nonneg"]
    c = _stored(root, "t.f")
    assert open_transitions(c["meta"]) == []
    assert c["meta"]["mathema.transitions"][0]["acknowledged"]["by"] == "aaron"
    with pytest.raises(AcceptanceError, match="no open transition"):
        plan_transition_acknowledgement(root, "t.f", ["nonneg"])
    _record(_square, "t.f", root, "holds")
    assert "mathema.transitions" not in _stored(root, "t.f")["meta"]


def test_the_cli_acknowledges_a_transition(tmp_path, capsys):
    from mathema.cli import main
    root = str(tmp_path)
    _record(_square, "t.f", root, "proven")
    _record(_square, "t.f", root, "unknown")
    assert main(["accept", "t.f", "nonneg", "--transition", "--yes",
                 "--by", "aaron", "--root", root]) == 0
    out = capsys.readouterr().out
    assert "weakened proven to unknown" in out and "written." in out
    assert open_transitions(_stored(root, "t.f")["meta"]) == []
    assert main(["accept", "t.f", "nonneg", "--transition", "--yes", "--root", root]) == 1
