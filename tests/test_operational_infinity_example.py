# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The operational-infinity example in docs/grammar.md, run as written:
the integral of the normal density over the whole line is proven, the
unbounded pointwise claim is proven over R with its `[float]` companion
falsified where `x ** 2` overflows, and under `let |inf| be 1e100` the
proof is the same proof over R while the companion, bounded at 1e100,
holds."""
import math

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


def gauss(x: float) -> float:
    """The standard normal density."""
    return math.exp(-x ** 2 / 2) / math.sqrt(2 * math.pi)


def _shown_rows():
    with open("docs/grammar.md") as fh:
        page = fh.read()
    block = page.split("### Operational infinity", 1)[1].split("```text\n", 1)[1]
    return block.split("```", 1)[0].strip().splitlines()


@pytest.mark.needs_full_proof_budget
def test_the_page_shows_exactly_what_the_example_prints():
    rows = []
    for law in ["∫(f(x), x, -oo, oo) == 1",
                "f(x) >= 0",
                "let |inf| be 1e100, f(x) >= 0"]:
        for p in mathema.check(gauss, claims=[law]).probes:
            label = ("  [float]" if (p.meta or {}).get("mathema.companion_of")
                     else law)
            rows.append(f"{label:31} {p.verdict:9} "
                        f"{p.counterexample or p.condition or ''}".rstrip())
    assert rows == _shown_rows()


def _companion(law):
    rows = {p.name: p for p in mathema.check(gauss, claims=[law]).probes}
    (comp,) = [p for p in rows.values()
               if (p.meta or {}).get("mathema.companion_of")]
    return rows[comp.meta["mathema.companion_of"]], comp


@pytest.mark.needs_full_proof_budget
def test_the_overflow_witness_really_raises():
    proof, companion = _companion("f(x) >= 0")
    assert proof.verdict == "proven"
    assert companion.verdict == "falsified"
    x = float(companion.counterexample.split("=", 1)[1])
    with pytest.raises(OverflowError):
        gauss(x)


@pytest.mark.needs_full_proof_budget
def test_the_half_line_bound_reaches_the_computation_and_not_the_proof():
    law = "let |inf| be 1e12, for x in [0, oo], f(x) >= 0"
    proof, companion = _companion(law)
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    for spelling in ("1e12", "1e+12", "1000000000000"):
        assert spelling not in proof.condition, proof.condition
    assert proof.condition.startswith("∀ x ∈ [0.0, inf]"), proof.condition
    assert companion.verdict == "holds", companion.note
    assert "run to let |inf| be 1e+12 (claim)" in companion.note, \
        companion.note
    assert "let |inf| be 1e+12" in companion.statement, companion.statement
    (probed,) = check_conjectures(gauss, [claim(law, route="probe")])
    assert "approximates infinity as 1e+12 (claim)" in probed.note, \
        probed.note
