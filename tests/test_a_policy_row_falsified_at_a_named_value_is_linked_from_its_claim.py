# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One written claim is a group of rows: the mathematics row, over the
printed domain with a named missing value left out, and the policy row
that judges that value. Where the function raises at the named value
and nothing covers it, the mathematics row stays proven over the
restated domain, its note points at the policy row, the policy row is
falsified, and the mathematics row carries a structured link to it."""
from typing import Optional

import pytest

import mathema
from mathema.conjecture import claim

TEXT = "for x in {1, None}, y in [0, 1], f(x, y) == 0"


def scaled(x: Optional[float], y: float) -> float:
    return (x - 1) * y


@pytest.mark.needs_smt
@pytest.mark.needs_full_proof_budget
def test_an_uncovered_raise_links_the_claim_to_its_falsified_policy_row():
    rec = mathema.check(scaled, claims=[claim(TEXT, name="c")])
    rows = {p.name: p for p in rec.probes}
    main, policy = rows["c"], rows["absent[x]"]
    assert main.verdict == "proven", (main.verdict, main.note)
    assert main.statement.startswith("for x in {1}, "), main.statement
    assert "judged by the policy row absent[x]" in main.note, main.note
    assert policy.verdict == "falsified", policy.note
    assert main.meta["mathema.claim_group"] == [
        {"row": "absent[x]", "verdict": "falsified", "value": "x = None"}]
