# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The one adjudication-outcome gate (verify.gate): provenance
population, accepted-risk exemption, strict/lenient split, and colon
subroutes classified through classify_verdict; one policy for check,
both verify paths, and any programmatic caller."""
from mathema.records import Probe
from mathema.verify import gate


def _probe(name, verdict, meta=None, note=""):
    return Probe(name, name, verdict, note=note, meta=meta or {})


def test_falsified_gates_in_every_mode():
    for strict in (True, False):
        r = gate([_probe("law", "falsified")], strict=strict)
        assert r.problems == ["1 falsified claim(s)"]
        assert r.refuted == 1


def test_subrouted_verdicts_classify_through_the_family():
    # exact-string matching used to let a subrouted verdict slip the
    # count; the gate classifies by verdict family
    r = gate([_probe("a", "falsified:uncorroborated"),
              _probe("b", "proven:construction"),
              _probe("c", "skipped:misspecified")], strict=True)
    assert r.refuted == 1 and r.proven == 1 and r.skipped == 1
    assert "1 falsified claim(s)" in r.problems


def test_unknown_gates_unless_risk_accepted():
    r = gate([_probe("law", "unknown")], strict=False)
    assert r.problems == ["1 unknown claim(s)"]
    r = gate([_probe("law", "unknown")], strict=False,
             accepted_risk=frozenset({"law"}))
    assert r.problems == [] and r.owned == 1


def test_strict_refuses_owned_risk_and_skips():
    claims = [_probe("a", "unknown"), _probe("b", "skipped")]
    r = gate(claims, strict=True, accepted_risk=frozenset({"a"}))
    assert r.problems == ["1 skipped claim(s)", "1 accepted-risk claim(s)"]
    r = gate(claims, strict=False, accepted_risk=frozenset({"a"}))
    assert r.problems == []


def test_suggestions_never_gate_by_provenance():
    volunteered = [
        _probe("s1", "falsified", meta={"mathema.surface": "mathema"}),
        _probe("s2", "unknown", note="conjectured by mathema (suggestion)")]
    r = gate(volunteered, strict=True)
    assert r.problems == []
    assert r.refuted == 0 and r.unknown == 0


def test_builtin_structural_probes_gate():
    # a built-in probe check() added on its own behalf carries no
    # suggestion provenance; it counts, exactly like an adopted claim
    r = gate([_probe("is_deterministic", "falsified",
                     note="conjectured by the author")], strict=False)
    assert r.problems == ["1 falsified claim(s)"]


def test_foreign_grammar_reported_never_gated():
    foreign = _probe("other", "skipped",
                     meta={"mathema.foreign_grammar": "mathema.data"})
    r = gate([foreign], strict=True)
    assert r.problems == [] and r.foreign == [foreign]


def test_stored_claim_dicts_gate_identically():
    stored = [{"name": "law", "verdict": "falsified", "note": "", "meta": {}},
              {"name": "dep", "verdict": "invalidated"},
              {"name": "s", "verdict": "unknown",
               "meta": {"mathema.surface": "mathema"}}]
    r = gate(stored, strict=False)
    assert r.refuted == 2 and r.unknown == 0
    assert r.problems == ["1 falsified claim(s)", "1 invalidated claim(s)"]


def test_unresolved_names_gate_in_every_mode():
    r = gate([], strict=False, unresolved=("np", "pd"))
    assert r.problems == ["unresolved names: np, pd"]
