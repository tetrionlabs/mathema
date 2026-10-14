# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that binds no domain for a parameter `@enforce_domain`
guards is read over the enforced domain, and the record says so: the
note states the working domain and the meta carries it under
`mathema.working_domain`, as it does for a conditional raise. A domain
the claim binds itself is its own, and nothing is stated for it."""
import math

from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim


@enforce_domain({"rate": (0, 1)})
def discount(rate: float) -> float:
    return 1 / (1 + rate)


@enforce_domain({"x": (0, 10)})
def enforced_root(x: float) -> float:
    return math.sqrt(x)


def _one(fn, text):
    (p,) = check_conjectures(fn, [claim(text)])
    return p


def test_a_value_claim_states_the_enforced_domain():
    for text in ("0 < f(rate) <= 1", "f(rate) > 0"):
        p = _one(discount, text)
        assert p.verdict == "proven", (text, p.verdict, p.note)
        assert "for rate" not in p.statement, p.statement
        assert ("the working domain is rate in [0, 1]: f's own guard "
                "rejects the rest") in (p.note or ""), (text, p.note)
        assert (p.meta or {}).get("mathema.working_domain") \
            == {"rate": "[0, 1]"}, p.meta


def test_a_built_in_claim_states_the_enforced_domain():
    p = _one(enforced_root, "is_number_set_safe(x)")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert ("the working domain is x in [0, 10]: f's own guard rejects "
            "the rest") in (p.note or ""), p.note


def test_a_domain_the_claim_binds_is_not_restated():
    p = _one(discount, "for rate in [0, 1/2], f(rate) > 0")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "the working domain" not in (p.note or ""), p.note
    assert "mathema.working_domain" not in (p.meta or {}), p.meta


@enforce_domain({"rate": (0, 1)})
def capped_discount(rate: float) -> float:
    if rate > 0.5:
        raise ValueError("rate is above one half")
    return 1 - rate


def test_a_guard_inside_the_enforced_domain_cuts_the_working_domain():
    import mathema
    rec = mathema.check(capped_discount, claims=["f(rate) > 0"])
    rows = [p for p in rec.probes if p.name.startswith("f_rate_gt_0")]
    assert {p.name for p in rows} >= {"f_rate_gt_0", "f_rate_gt_0[float]"}, \
        [p.name for p in rec.probes]
    for p in rows:
        assert p.verdict in ("proven", "holds"), (p.name, p.verdict,
                                                  p.counterexample, p.note)
        assert p.counterexample is None, (p.name, p.counterexample)
        assert "the working domain is rate in [0, 1/2]" in (p.note or ""), \
            (p.name, p.note)
        assert (p.meta or {}).get("mathema.working_domain", {}).get("rate") \
            == "[0, 1/2]", p.meta
    (main,) = [p for p in rows if p.name == "f_rate_gt_0"]
    assert main.verdict == "proven", (main.verdict, main.note)


def test_a_stated_domain_past_the_guard_still_falsifies():
    p = _one(capped_discount, "for rate in [0, 1], f(rate) > 0")
    assert p.verdict == "falsified", (p.verdict, p.note)
