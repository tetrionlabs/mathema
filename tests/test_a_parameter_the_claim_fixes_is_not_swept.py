# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter the claim never reads (filled by a literal, positionally
or by keyword, or left at its default) is not one of the claim's
coordinates: no domain is inferred for it, no route sweeps it, and a
witness does not name it. The verdict is the claim's own."""
from mathema.conjecture import check_conjectures, claim


def tagged(s: str, upper: bool = False) -> str:
    """s, upper-cased when asked."""
    return s.upper() if upper else s


def test_a_keyword_fixed_parameter_is_not_swept_or_shown():
    (p,) = check_conjectures(tagged, [claim('for s in {"a", "b"}, tagged(s, upper=True) == s')])
    assert p.verdict == "falsified"
    assert "upper" not in (p.counterexample or ""), p.counterexample
    assert "inferred upper" not in (p.note or ""), p.note


def test_a_positionally_fixed_parameter_is_not_swept_or_shown():
    (p,) = check_conjectures(tagged, [claim('for s in {"a", "b"}, tagged(s, True) == s')])
    assert p.verdict == "falsified"
    assert "upper" not in (p.counterexample or ""), p.counterexample
    assert "inferred upper" not in (p.note or ""), p.note


def test_a_fixed_parameter_does_not_cost_the_proof():
    (p,) = check_conjectures(tagged, [claim(
        'for s in {"a", "b"}, tagged(s, True) == tagged(tagged(s, True), True)')])
    assert p.verdict == "proven", p.note


def test_a_parameter_the_claim_reads_is_still_swept():
    (p,) = check_conjectures(tagged, [claim('for s in {"a", "b"}, tagged(s, upper) == s')])
    assert p.verdict == "falsified"
    assert "upper=True" in (p.counterexample or ""), p.counterexample
