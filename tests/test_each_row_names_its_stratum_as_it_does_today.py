# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""How a row names its stratum today.

Output: a claim with rows under it prints one line per aspect, labelled
`mathematics`, `computation` or `policy`. Records: a falsified row
carries a `stratum` mapping (which stratum is sound or unsound, whose
fault, the cause, the representation and the witness), and the record
writes it under the row's meta key `mathema.stratum`.
"""
import mathema
from mathema.spec import to_spec


def doubled(x: float) -> float:
    return 2.0 * x


def plus_one_minus(x: float) -> float:
    return (x + 1.0) - x


def _check(fn, law, route="derive"):
    return mathema.check(fn, claims=[mathema.claim(law, name="law", route=route)])


def _aspect_lines(rec):
    lines = [ln.split() for ln in str(rec).splitlines()]
    return [(ln[0], ln[1]) for ln in lines
            if len(ln) > 1 and ln[1] in ("mathematics", "computation", "policy")]


def test_a_proven_claim_prints_mathematics_computation_and_policy_lines():
    rec = _check(doubled, "for x in [-10, 10], f(x) == 2*x")
    assert _aspect_lines(rec) == [("proven", "mathematics"),
                                  ("holds", "computation"),
                                  ("holds", "policy")]


def test_a_probe_claim_prints_its_verdict_on_the_computation_line():
    rec = _check(doubled, "for x in [-10, 10], f(x) >= -20", route="probe")
    assert _aspect_lines(rec) == [("holds", "computation"), ("holds", "policy")]


def test_the_mathematics_line_states_the_claim_over_the_reals():
    text = str(_check(doubled, "for x in [-10, 10], f(x) == 2*x"))
    assert "for x in [-10.0, 10.0] ⊂ ℝ, f(x) = 2*x" in text
    assert "for x in [-10.0, 10.0] : float, f(x) = 2*x" in text


def test_a_row_with_no_finding_carries_no_stratum():
    rec = _check(doubled, "for x in [-10, 10], f(x) == 2*x")
    assert all(p.stratum is None for p in rec.probes)
    assert not any("mathema.stratum" in (c.get("meta") or {})
                   for c in to_spec(rec)["claims"])


def test_a_falsified_computation_row_names_its_strata_in_output_and_record():
    rec = _check(plus_one_minus, "for x in [0, 1e300], f(x) == 1")
    text = str(rec)
    assert "[mathematics sound, implementation:numerical-instability]" in text
    assert _aspect_lines(rec)[:2] == [("proven", "mathematics"),
                                      ("falsified", "computation")]
    expected = {"mathematics": "sound", "blame": "implementation",
                "cause": "implementation:numerical-instability",
                "representation": "f64", "witness": "x = 1e+300"}
    comp = next(p for p in rec.probes if p.name == "law[float]")
    assert comp.stratum == expected
    row = next(c for c in to_spec(rec)["claims"] if c["name"] == "law[float]")
    assert row["meta"]["mathema.stratum"] == expected


def test_a_claim_derive_falsifies_names_the_mathematics_unsound():
    rec = _check(doubled, "for x in [-10, 10], f(x) == 3*x")
    law = rec.probes[0]
    assert law.stratum["mathematics"] == "unsound"
    assert law.stratum["blame"] == "claim"
    assert "mathematics" in dict((n, v) for v, n in _aspect_lines(rec))
