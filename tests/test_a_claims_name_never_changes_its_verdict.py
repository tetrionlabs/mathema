# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's name is a label. The question a built-in claim asks is
read from its statement, so `is_repeatable(f)` reaches the same verdict
unnamed, named after itself, or named anything else, and a docstring
`Claims:` line (which always carries a name) is judged the same way."""
import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


def half(x: float) -> float:
    return x / 2


def documented_half(x: float) -> float:
    """Half of x.

    Claims:
        repeatable: is_repeatable(f)
        same_answer: is_deterministic(f)
        no_side_effects: is_state_safe(f)
    """
    return x / 2


STATELESS = ("is_repeatable", "is_deterministic", "is_reproducible",
             "is_state_safe")


@pytest.mark.parametrize("family", STATELESS)
def test_the_verdict_is_the_same_under_any_name(family):
    text = f"{family}(f)"
    verdicts = {}
    for name in (None, family, "repeatable", "c"):
        (p,) = check_conjectures(half, [claim(text, name=name)])
        verdicts[name] = (p.verdict, p.note)
    assert verdicts[None][0] == "proven", verdicts
    assert {v for v, _ in verdicts.values()} == {"proven"}, verdicts


def test_a_docstring_claim_line_is_judged_by_its_statement():
    record = mathema.check(documented_half)
    rows = {p.name: p.verdict for p in record.probes
            if p.name in ("repeatable", "same_answer", "no_side_effects")}
    assert rows == {"repeatable": "proven", "same_answer": "proven",
                    "no_side_effects": "proven"}, rows
