# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim substituting a literal directly into a guarded parameter's
position (f(50, 0), the 0 landing on a guarded parameter) used to need
a *separate* domain quantifier just to make branch pruning aware of it
(`for code in [0, 0], raises(f(50, code), ValueError)`), try_prove_
raises() parsed call_src only far enough to confirm it's a bare f(...)
call, then discarded its own arguments entirely, using only the
explicitly-passed domain dict. check_conjectures() now scans a claim's
own lhs/rhs (and a raises() call source) for f(...) calls with a plain
numeric-literal argument and infers a degenerate single-point domain
for that parameter, terse input (no quantifier needed), explicit
output (the inferred value is still named in the resulting Probe's
note, never silently assumed). An explicitly declared domain always
wins over an inferred one."""
from mathema.conjecture import check_conjectures, claim


def price_with_discount(price: float, code: float) -> float:
    if code == 0:
        raise ValueError("discount code required")
    return price / code


def guarded(x: float, flag: float) -> float:
    if flag <= -1:
        raise ValueError("flag too low")
    return x


def test_literal_argument_infers_a_domain_for_the_guarded_parameter():
    results = check_conjectures(
        price_with_discount,
        [claim("raises(f(50, 0), ValueError)", route="derive")])
    assert results[0].verdict == "proven"
    assert "inferred" in results[0].note
    assert "code" in results[0].note


def test_no_literal_argument_still_stays_undecided_as_before():
    # code (the guarded parameter) passed as a bare name, not a literal,
    # nothing to infer for it specifically, so the guard must stay
    # undecided exactly as before this feature existed. price=50 is
    # still separately inferred (a harmless, expected side effect,
    # price plays no part in the guard), so check the note names price
    # but not code.
    results = check_conjectures(
        price_with_discount,
        [claim("raises(f(50, code), ValueError)", route="derive")])
    # nothing to infer for the bare-name argument, exactly as before,
    # the probe fallback then finds most sampled codes do NOT raise,
    # falsifying the unquantified raises claim; the inference note
    # still names price and not code
    assert results[0].verdict == "falsified"
    assert "price=50" in results[0].note
    assert "code=" not in results[0].note


def test_negative_literal_argument_also_infers_a_domain():
    # -1 parses as UnaryOp(USub, Constant(1)), must still be
    # recognized as a plain numeric literal for inference purposes.
    results = check_conjectures(
        guarded, [claim("raises(f(5, -1), ValueError)", route="derive")])
    assert results[0].verdict == "proven"
    assert "inferred" in results[0].note
    assert "flag" in results[0].note


def test_explicit_domain_wins_over_an_inferred_one():
    # an explicitly declared domain for code, [1, 5], excludes 0, if
    # the inferred literal (0, from f(50, 0)) illegitimately overrode
    # it, the guard would resolve as always-true and derive would come
    # back proven. Under the explicit domain derive reads code in
    # [1, 5], never reaches the guard, and disproves the raise; that
    # disproof has no executed witness (the literal call f(50, 0) does
    # raise), so it is reported uncorroborated rather than falsified,
    # and the probe route, which runs the call, holds.
    (p,) = check_conjectures(
        price_with_discount,
        [claim("for code in [1, 5], raises(f(50, 0), ValueError)", route="derive")])
    assert p.verdict != "proven"
    assert (p.meta or {}).get("mathema.corroboration") == "uncorroborated"
    assert p.verdict == "holds" and p.route == "probe"
    assert "code=" not in p.note


def test_literal_in_an_ordinary_relation_claim_also_infers_a_domain():
    results = check_conjectures(
        price_with_discount, [claim("f(50, 5) == 10", route="derive")])
    assert results[0].verdict == "proven"
    assert "inferred" in results[0].note
    assert "code" in results[0].note
    assert "price" in results[0].note
