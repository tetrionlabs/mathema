# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A computation line under a claim that only holds on the probe (no
proof) is offered `let |inf| be B` only from its conditioning, never by
searching for a B under which a rerun holds: without a proof, a failure
far out may be the mathematics failing."""
import mathema


def total(xs: list) -> float:
    return sum(xs)


def test_an_overflow_under_a_probe_only_claim_gets_no_searched_offer():
    rec = mathema.check(total, claims=["f(xs) >= min(xs) * len(xs)"])
    line = next(p for p in rec.probes if p.name.endswith("[float]"))
    main = next(p for p in rec.probes
                if p.name == line.meta["mathema.companion_of"])
    assert main.verdict == "holds" and main.route == "probe", main
    assert line.verdict == "falsified", line
    assert "mathema.infinity_offer" not in (line.meta or {}), line.meta
    assert "let |inf| be" not in str(rec), str(rec)
