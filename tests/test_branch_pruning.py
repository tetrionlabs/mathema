# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Domain-conditioned branch pruning for the derive route: a branch over
an unmodified signature parameter, resolved when the claim's own declared
domain settles the condition's truth value throughout."""
import pytest
import math

from mathema.conjecture import claim, check_conjectures


def strength_to_distance(r: float, scale: str = "info") -> float:
    if scale == "info":
        return math.sqrt(1.0 - r ** 2)
    if scale == "linear":
        return 1.0 - r
    raise ValueError(f"unknown scale {scale!r}, use 'info' or 'linear'")


def sign_of(x: float) -> float:
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return 0.0


def clamp_floor(x: float) -> float:
    if x <= -1:
        raise ValueError("below floor")
    return x


def guard_on_equal_params(x1: float, x2: float) -> float:
    if x1 == x2:
        return 0.0
    return x1 - x2


def guard_on_affine_combo(r: float, g: float) -> float:
    if r - g <= 0:
        return 0.0
    return r - g


def dispatch_on_both_flags(x: float, x_discrete: bool, y_discrete: bool) -> float:
    if x_discrete and y_discrete:
        return 1.0
    if x_discrete and not y_discrete:
        return 2.0
    if y_discrete and not x_discrete:
        return 3.0
    return x


def test_value_claim_proven_when_domain_pins_one_branch():
    results = check_conjectures(
        strength_to_distance,
        [claim('for r in [0, 1], scale in {"info"}, f(r, scale) == sqrt(1.0 - r^2)',
              route="derive")])
    assert results[0].verdict == "proven"


def test_value_claim_proven_for_the_other_branch_too():
    results = check_conjectures(
        strength_to_distance,
        [claim('for r in [0, 1], scale in {"linear"}, f(r, scale) == 1 - r',
              route="derive")])
    assert results[0].verdict == "proven"


def test_wrong_formula_for_pinned_branch_is_falsified_not_silently_passed():
    results = check_conjectures(
        strength_to_distance,
        [claim('for r in [0, 1], scale in {"info"}, f(r, scale) == 1 - r',
              route="derive")])
    assert results[0].verdict == "falsified"


def test_no_domain_gets_empirical_adjudication_after_derive_declines():
    # no domain pins a path, so the derive route declines, and the
    # claim then quantifies over every string scale, almost all of
    # which raise: probing finds a raising sample, which falsifies a
    # value claim pedantically. Empirical evidence supersedes the old
    # resting "unknown".
    results = check_conjectures(
        strength_to_distance, [claim("f(r, scale) >= 0", route="derive")])
    assert results[0].verdict == "falsified"
    assert "raised" in results[0].counterexample


def test_unbounded_claim_over_a_raising_guard_is_pedantically_falsified():
    # with no domain, the claim quantifies over the whole line, which
    # includes the region where clamp_floor raises. A raise is not a
    # value, so the claim is false there: falsified, with the witness
    # found by solving the guard region, and the remedy named.
    results = check_conjectures(
        clamp_floor, [claim("f(x) >= -5", route="derive")])
    assert results[0].verdict == "falsified"
    assert "raises" in results[0].sketch
    assert "narrow the claim's domain" in results[0].sketch


@pytest.mark.needs_full_proof_budget
def test_ordinary_claim_names_both_params_for_a_two_param_guard():
    # derive declines with the two-param diagnosis; the claim is then
    # genuinely false over the unbounded plane (x1 - x2 < -100 exists)
    # and probing falsifies it. The derive-stage diagnosis survives in
    # the note.
    results = check_conjectures(
        guard_on_equal_params, [claim("f(x1, x2) >= -100", route="derive")])
    assert results[0].verdict == "falsified"
    assert "needs a domain specific enough for x1, x2" in results[0].note


def test_ordinary_claim_reports_a_structural_reason_not_a_domain_hint_when_blocked():
    # non-affine guard (x*y) over a domain where its hull straddles the
    # compared literal: neither corner evaluation nor interval
    # evaluation settles it, and the message must name that structural
    # reason, not the misleading "needs a domain" phrasing used for the
    # genuinely resolvable case above.
    def divides(x: float, y: float) -> float:
        denom = x * y
        if denom == 0.0:
            return 0.0
        return x / denom

    results = check_conjectures(
        divides, [claim("for x in [-1, 5], y in [1, 5], f(x, y) >= 0", route="derive")])
    # the structural diagnosis stays (in the note, since probing then
    # adjudicates the, true, claim empirically: 1/y > 0 on [1, 5])
    assert results[0].verdict == "holds"
    assert "isn't affine" in results[0].note
    assert "needs a domain" not in results[0].note


def test_nonaffine_guard_still_prunes_when_the_interval_settles_it():
    # the same guard over [1, 5] x [1, 5]: x*y's hull is [1, 25], so
    # `denom == 0.0` is decidably false, the guard prunes, and the
    # claim genuinely proves, a domain-interval fact, no affinity
    # needed.
    def divides(x: float, y: float) -> float:
        denom = x * y
        if denom == 0.0:
            return 0.0
        return x / denom

    results = check_conjectures(
        divides, [claim("for x in [1, 5], y in [1, 5], f(x, y) >= 0", route="derive")])
    assert results[0].verdict == "proven"


def test_domain_spanning_both_branches_proves_by_value_split():
    # scale in {"info", "linear"} doesn't settle which branch runs, and
    # guessing one is still forbidden, but a finite domain splits
    # exactly into its own values, and the claim is provable on each
    # (sqrt(1-r^2) and 1-r are both nonnegative on [0,1]), so the
    # whole claim proves piecewise instead of falling back to probe
    results = check_conjectures(
        strength_to_distance,
        [claim('for r in [0, 1], scale in {"info", "linear"}, f(r, scale) >= 0',
              route="derive")])
    assert results[0].verdict == "proven"
    assert "split into its stated values" in results[0].sketch
    assert results[0].meta.get("mathema.derive_route") == "domain_split"


def test_numeric_interval_domain_also_prunes_a_branch():
    # branch pruning isn't limited to string/discrete domains, a plain
    # numeric interval that lies entirely on one side of the condition
    # settles it the same way
    results = check_conjectures(
        sign_of, [claim("for x in [1, 10], f(x) == 1", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        sign_of, [claim("for x in [-10, -1], f(x) == -1", route="derive")])
    assert results[0].verdict == "proven"


def test_raises_claim_proven_when_domain_pins_the_fallback_case():
    results = check_conjectures(
        strength_to_distance,
        [claim('for r in [0, 1], scale in {"nonsense"}, raises(f(r, scale), ValueError)',
              route="derive")])
    assert results[0].verdict == "proven"


def test_raises_claim_falsified_when_pinned_branch_actually_returns():
    results = check_conjectures(
        strength_to_distance,
        [claim('for r in [0, 1], scale in {"info"}, raises(f(r, scale))',
              route="derive")])
    assert results[0].verdict == "falsified"


def test_raises_claim_with_no_domain_adjudicates_empirically():
    # derive needs a domain to pin the raising branch; probing then
    # samples arbitrary strings for scale, essentially all of which
    # take the raise path, empirical support for the raises claim
    results = check_conjectures(
        strength_to_distance, [claim("raises(f(r, scale))", route="derive")])
    assert results[0].verdict == "holds"


def test_negative_literal_guard_proven_when_domain_pins_the_raising_branch():
    # `x <= -1`, Python parses -1 as UnaryOp(USub, Constant(1)), not a
    # single negative Constant; _literal_value must still recognize it.
    results = check_conjectures(
        clamp_floor,
        [claim("for x in [-10, -2], raises(f(x), ValueError)", route="derive")])
    assert results[0].verdict == "proven"


def test_negative_literal_guard_proven_for_the_fallthrough_branch():
    results = check_conjectures(
        clamp_floor, [claim("for x in [0, 10], f(x) == x", route="derive")])
    assert results[0].verdict == "proven"


def test_param_vs_param_equality_guard_prunes_given_disjoint_domains():
    # x1 == x2 is algebraically x1 - x2 == 0, degree 1, squarely
    # inside _decide_affine_condition's existing capability once
    # _compare_truth actually reaches it (the fix this test exercises:
    # previously it never did, always deciding None on the first
    # "unmodified param vs literal" branch instead).
    results = check_conjectures(
        guard_on_equal_params,
        [claim("for x1 in [0, 1], x2 in [2, 3], f(x1, x2) == x1 - x2", route="derive")])
    assert results[0].verdict == "proven"


def test_param_vs_param_guard_with_agreeing_branches_proves_piecewise():
    # x1, x2 both in [0, 3]: the guard's truth genuinely isn't settled,
    # but it doesn't need to be, on the diagonal the guarded branch
    # returns 0.0 and x1 - x2 IS 0, so both branches agree with the
    # claim and the full piecewise lift proves it outright.
    results = check_conjectures(
        guard_on_equal_params,
        [claim("for x1 in [0, 3], x2 in [0, 3], f(x1, x2) == x1 - x2", route="derive")])
    assert results[0].verdict == "proven"


def test_param_vs_param_guard_with_disagreeing_branches_stays_undecided():
    # the genuinely ambiguous variant: the guarded branch returns a
    # value the claim contradicts, exactly on the undecidable diagonal;
    # must stay honestly unknown, never guess either way.
    def spiked(x1: float, x2: float) -> float:
        if x1 == x2:
            return 1.0
        return x1 - x2

    results = check_conjectures(
        spiked,
        [claim("for x1 in [0, 3], x2 in [0, 3], f(x1, x2) == x1 - x2", route="derive")])
    # the derive route honestly can't settle the diagonal, and the
    # claim IS false there (f(x, x) = 1.0 while x - x = 0), which the
    # probe's shared-special samples then witness
    assert results[0].verdict == "falsified"


def test_affine_combo_guard_already_resolves_given_both_domains():
    # confirms _compare_truth's existing inline-affine-expression path
    # (r - g <= 0, no need to bind it to a name first) already handles
    # this once both r and g have declared domains, a genuine
    # capability, not something this session needed to build. r in
    # [0, 1], g in [2, 3]: r - g is always <= -1, so the guard always
    # triggers and f always returns 0.0.
    results = check_conjectures(
        guard_on_affine_combo,
        [claim("for r in [0, 1], g in [2, 3], f(r, g) == 0", route="derive")])
    assert results[0].verdict == "proven"


def test_boolop_and_condition_prunes_to_the_first_branch():
    results = check_conjectures(
        dispatch_on_both_flags,
        [claim('for x_discrete in {True}, y_discrete in {True}, '
              'f(x, x_discrete, y_discrete) == 1.0', route="derive")])
    assert results[0].verdict == "proven"


def test_boolop_and_not_condition_prunes_to_the_second_branch():
    results = check_conjectures(
        dispatch_on_both_flags,
        [claim('for x_discrete in {True}, y_discrete in {False}, '
              'f(x, x_discrete, y_discrete) == 2.0', route="derive")])
    assert results[0].verdict == "proven"


def test_boolop_condition_prunes_to_the_fallthrough_branch():
    # neither flag set, none of the three BoolOp-guarded branches taken,
    # falls through to the final unconditional `return x`
    results = check_conjectures(
        dispatch_on_both_flags,
        [claim('for x_discrete in {False}, y_discrete in {False}, '
              'f(x, x_discrete, y_discrete) == x', route="derive")])
    assert results[0].verdict == "proven"


def test_boolop_condition_with_no_domain_stays_unliftable():
    results = check_conjectures(
        dispatch_on_both_flags,
        [claim("f(x, x_discrete, y_discrete) >= 0", route="derive")])
    # derive stays blocked without a domain; the probe fallback then
    # supplies (weak, sampling-limited) empirical evidence
    assert results[0].verdict in ("holds", "falsified")
    assert "routes attempted" in results[0].note
    assert "derive: underivable" in results[0].note


def test_wrong_formula_for_boolop_pinned_branch_is_falsified():
    results = check_conjectures(
        dispatch_on_both_flags,
        [claim('for x_discrete in {True}, y_discrete in {True}, '
              'f(x, x_discrete, y_discrete) == 2.0', route="derive")])
    assert results[0].verdict == "falsified"


def gate_bare(flag: bool, x: float) -> float:
    if flag:
        return x + 1.0
    return x - 1.0


def gate_is_true(flag: bool, x: float) -> float:
    if flag is True:
        return x + 1.0
    return x - 1.0


def gate_is_not_true(flag: bool, x: float) -> float:
    if flag is not True:
        return x + 1.0
    return x - 1.0


def gate_not_and(flag: bool, x: float) -> float:
    if not flag and x > 0:
        return x + 1.0
    return x - 1.0


def gate_ordered(flag: bool, x: float) -> float:
    if x > 0 and flag:
        return x + 1.0
    return x - 1.0


def test_bool_annotation_splits_and_proves_every_condition_spelling():
    # a bool parameter's annotation states its whole domain
    # ({False, True}, the real objects), so a claim that is true on
    # both branches proves by splitting into the stated values, with
    # nothing declared in the claim at all. Covers the truthiness
    # spelling, identity (is / is not), negation, and both orderings
    # inside a compound condition.
    for fn in (gate_bare, gate_is_true, gate_is_not_true,
               gate_not_and, gate_ordered):
        results = check_conjectures(
            fn, [claim("for x in [1, 5], f(flag, x) >= x - 1",
                       route="derive")])
        assert results[0].verdict == "proven", (fn.__name__, results[0].note)
        assert results[0].route == "derive"


def test_bool_literal_domain_pins_one_branch_of_an_identity_guard():
    # {True}/{False} in a claim are real boolean values, so an
    # `is True` guard decides exactly, and an authored INT domain
    # keeps honest identity semantics: 1 is not True, so the
    # else-branch runs and the then-branch claim falsifies
    results = check_conjectures(
        gate_is_true,
        [claim("for flag in {True}, x in [1, 5], f(flag, x) == x + 1",
               route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        gate_is_true,
        [claim("for flag in {1}, x in [1, 5], f(flag, x) == x + 1",
               route="derive")])
    assert results[0].verdict == "falsified"


def test_bool_probe_sampling_uses_real_booleans():
    # the probe route draws a bool parameter's values from the stated
    # {False, True}, never the numerically-equal 0/1, an identity
    # guard would mis-model under ints (`1 is True` is False)
    results = check_conjectures(
        gate_is_true,
        [claim("for x in [1, 5], abs(f(flag, x) - x) == 1",
               route="probe")])
    assert results[0].verdict == "holds", results[0].note
