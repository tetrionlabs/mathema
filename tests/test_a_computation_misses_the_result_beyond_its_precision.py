# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A computation line is falsified where the float result misses the
mathematics beyond the representation's honest precision of the result:
the absolute part of the allowance (the fixed 1e-9, and an array draw's
round-off) never exceeds the relative part of the result, so a result
of 0.0 for an exact 1.0 at inputs of magnitude 1e16 is a miss, on an
unbound list exactly as on a bounded box. The note computes the
condition number at the witness and says whether the miss is inherent
(no float64 computation can deliver the result there) or the code's,
and offers narrowing the domain or accepting the discovery (ruling of
2026-10-06 on G94, option a)."""
import numpy as np
import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


def running_total(xs: list, y0: float) -> float:
    total = y0
    for v in xs:
        total = v + total
    return total


def ident(x: float) -> float:
    return x


def nearly_zero(x: float) -> float:
    return (x + 1.0) - 1.0 - x


def shifted_back(x: float) -> float:
    return (x + 1e16) - 1e16


_SHIFT = "f(xs, y0) == f(xs, 0) + y0"


def _kappa_note(p) -> str:
    return (p.note or "") + " " + (p.sketch or "")


def test_a_cancelling_pair_falsifies_the_shift_on_an_unbound_list():
    (p,) = check_conjectures(running_total, [claim(
        f"for xs in R^n, y0 in [-10, 10], {_SHIFT}", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ill-conditioned here (κ ≈" in _kappa_note(p), p.note
    assert "no float64 computation can deliver this result at inputs of " \
           "magnitude" in _kappa_note(p), p.note
    found = p.meta["mathema.conditioning"]
    assert found["inherent"] is True
    assert found["narrow"].startswith("for xs in [-1e"), found


def test_the_bounded_box_and_the_unbound_list_agree():
    rows = {p.name: p for p in mathema.check(running_total, claims=[
        mathema.claim(f"for xs in [-1e16, 1e16]^2, y0 in {{1}}, {_SHIFT}",
                      name="shift")]).probes}
    assert rows["shift"].verdict == "proven"
    computation = rows["shift[float]"]
    assert computation.verdict == "falsified", computation.note
    assert computation.counterexample.startswith("xs = [1e+16, -1e+16], y0 = 1")
    assert "ill-conditioned here (κ ≈ 2e16)" in _kappa_note(computation), \
        computation.sketch
    (p,) = check_conjectures(running_total, [claim(
        f"for xs in [-1e16, 1e16]^2, y0 in {{1}}, {_SHIFT}", route="probe")])
    assert p.verdict == "falsified"
    assert p.counterexample.startswith("xs = [1e+16, -1e+16], y0 = 1")


def test_a_wrong_claim_at_a_large_magnitude_is_falsified():
    (p,) = check_conjectures(ident, [claim(
        "for x in [0, 1], f(x) == (x + 1e16) - 1e16 + 1", route="probe")])
    assert p.verdict == "falsified"


def test_a_result_near_zero_is_judged_against_the_inputs_not_zero():
    # the exact result is 0 and the float result is round-off of inputs
    # near 1: the input-scaled part alone decides, and the claim holds
    (p,) = check_conjectures(nearly_zero, [claim(
        "for x in [0, 1], f(x) == 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_a_loss_the_conditioning_does_not_explain_is_the_codes():
    # the mathematics is x, well conditioned (κ = 1); the code loses it
    # by taking a detour through 1e16
    (p,) = check_conjectures(shifted_back, [claim(
        "for x in [1, 2], f(x) == x", route="probe")])
    assert p.verdict == "falsified"
    assert "f loses more than the conditioning explains (κ ≈ 1" in \
        _kappa_note(p), p.note
    assert p.meta["mathema.conditioning"]["inherent"] is False


def wrong_slope(x: float) -> float:
    return x * 2


def test_a_claim_false_in_exact_arithmetic_carries_no_conditioning_note():
    # f run on the exact numbers violates the claim too: the claim is
    # false at the point, which no conditioning explains
    (p,) = check_conjectures(wrong_slope, [claim(
        "for x in [1, 2], f(x) == x", route="probe")])
    assert p.verdict == "falsified"
    assert "mathema.conditioning" not in (p.meta or {}), p.note


def test_the_remedies_narrow_the_domain_or_accept_the_discovery():
    rec = mathema.check(running_total, claims=[mathema.claim(
        f"for xs in [-1e16, 1e16]^2, y0 in {{1}}, {_SHIFT}", name="shift")])
    text = repr(rec)
    assert "(i) if inputs this large are out of scope, narrow the domain: " \
           "for xs in [-1e8, 1e8]^2" in text, text
    assert "(ii) if the loss is accepted, run: mathema accept " in text
    assert "shift --as discovery" in text


@pytest.fixture
def bundled_compendium(tmp_path):
    # the bundled library rows alone, so numpy's functions carry their
    # library keys as `mathema check` gives them
    from mathema import compendium
    compendium.uninstall()
    compendium.install(str(tmp_path))
    yield
    compendium.uninstall()


def test_a_near_singular_matrix_is_a_conditioning_finding_on_a_definition_row(
        bundled_compendium):
    # numpy.linalg.solve loses about cond(a) units of round-off, as any
    # backward-stable solver does: the row is not a wrong model, the
    # axiom stands with the finding recorded
    hilbert = "[" + ", ".join(
        "[" + ", ".join(f"1/{i + j + 1}" for j in range(9)) + "]"
        for i in range(9)) + "]"
    (p,) = check_conjectures(np.linalg.solve, [claim(
        f"for b in [1, 2]^9, f({hilbert}, b) == solve({hilbert}, b)",
        name="definition", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
    finding = p.meta["mathema.conditioning_finding"]
    assert finding.startswith("numpy.linalg.solve loses")
    assert "ill-conditioned" in finding


def test_a_wrong_row_is_still_revoked_at_a_well_conditioned_draw(
        bundled_compendium):
    (p,) = check_conjectures(np.std, [claim(
        "for a in [-10, 10]^n, assuming dim(a) >= 2, f(a) ~= std(a, ddof=1)",
        name="definition", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "mathema.conditioning_finding" not in (p.meta or {})


def doubled(x: float) -> float:
    return 2 * x


def test_a_literal_in_one_call_does_not_pin_a_parameter_the_claim_quantifies():
    # `f(1)` passes a literal where the claim also quantifies x: x is
    # still drawn over [1, 2], so the false shift is falsified rather
    # than tested at x = 1 alone, where it is trivially true
    (p,) = check_conjectures(doubled, [claim(
        "for x in [1, 2], f(x) == f(1) + (x - 1)", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def not_a_shift(xs: list, y0: float) -> float:
    total = 2 * y0
    for v in xs:
        total = v + total
    return total


def test_a_literal_in_one_call_does_not_narrow_the_proof_either():
    # `f(xs, 0)` passes a literal where the claim also quantifies y0: the
    # proof must range over y0, where this shift is false
    (p,) = check_conjectures(not_a_shift, [claim(
        "for xs in R^n, y0 in R, f(xs, y0) == f(xs, 0) + y0", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)
    rows = {p.name: p for p in mathema.check(not_a_shift, claims=[
        mathema.claim("f(xs, y0) == f(xs, 0) + y0", name="shift")]).probes}
    assert rows["shift"].verdict == "falsified", (rows["shift"].verdict,
                                                   rows["shift"].note)
