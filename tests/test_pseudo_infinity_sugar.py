# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The pseudo-infinity grammar sugar: `let |inf| be 1e6` is the ONE
claim-text spelling of the operational meaning of infinity, the
bars mean magnitude, applied symmetrically. A bare or signed `inf`
before `be` is refused with guidance (it reads too much like the
domain-endpoint spelling), and the declared layer's `pseudo_infinity`
key keeps working unchanged."""
import pytest

from mathema.conjecture import InvalidConjecture, claim
from mathema.spec import declare, entry_claims, render_claim_text


def test_bars_spelling_binds_the_magnitude():
    cj = claim("let |inf| be 1e12, for x in [0, oo], f(x) >= 0")
    assert cj.pseudo_infinity == 1e12


def test_unicode_bars_spelling_is_accepted():
    cj = claim("let |∞| be 1e6, f(x) >= 0")
    assert cj.pseudo_infinity == 1e6


def test_keyword_magnitude_still_works_unchanged():
    cj = claim("f(x) >= 0", pseudo_infinity=1e10)
    assert cj.pseudo_infinity == 1e10


@pytest.mark.parametrize("law", [
    "let inf be 1e12, f(x) >= 0",        # bare word: ambiguous, refused
    "let oo be 1e12, f(x) >= 0",         # the endpoint spelling itself
    "let +-inf be [-1e6, 1e6], f(x) >= 0",   # no asymmetric form exists
    "let ±∞ be 1e6, f(x) >= 0",          # signed unicode, same refusal
])
def test_non_bars_spellings_are_refused_with_guidance(law):
    with pytest.raises(InvalidConjecture, match=r"\|inf\|"):
        claim(law)


@pytest.mark.parametrize("law", [
    "let |inf| be -3, f(x) >= 0",        # magnitude must be positive
    "let |inf| be oo, f(x) >= 0",        # and finite
    "let |inf| be banana, f(x) >= 0",    # and numeric at all
])
def test_misspecified_magnitudes_refuse_loudly(law):
    with pytest.raises(InvalidConjecture):
        claim(law)


def test_binding_and_keyword_must_agree():
    with pytest.raises(InvalidConjecture, match="twice"):
        claim("let |inf| be 1e12, f(x) >= 0", pseudo_infinity=5.0)
    cj = claim("let |inf| be 1e12, f(x) >= 0", pseudo_infinity=1e12)
    assert cj.pseudo_infinity == 1e12


def test_declared_record_carries_the_magnitude():
    entry = declare(claim("let |inf| be 1e12, f(x) >= 0"))
    assert entry["pseudo_infinity"] == 1e12


def test_round_trip_through_the_declared_layer():
    cj = claim("let |inf| be 1e6, for x in [0, oo], f(x) >= 0",
               name="capped")
    (back,) = entry_claims({"claims": [declare(cj)]})
    assert back.pseudo_infinity == 1e6


def test_rendered_text_states_the_binding_in_both_modes():
    cj = claim("let |inf| be 1e12, for x in [0, oo], f(x) >= 0")
    assert "let |inf| be 1e+12" in render_claim_text(cj, unicode=False)
    assert "let |∞| be 1e+12" in render_claim_text(cj, unicode=True)


def test_rendered_text_reparses_to_the_same_magnitude():
    cj = claim("let |inf| be 1e6, for x in [0, oo], f(x) >= 0")
    again = claim(render_claim_text(cj, unicode=False))
    assert again.pseudo_infinity == 1e6


def doubled(x: float) -> float:
    return 2.0 * x


def test_empirical_record_calls_out_the_approximation_derive_does_not():
    from mathema.analysis import analyze_source
    from mathema.conjecture import check_conjectures
    facts = analyze_source(doubled)
    law = "let |inf| be 1e6, for x in [0, oo], f(x) >= 0"
    (probed,) = check_conjectures(doubled, [claim(law, route="probe")],
                                  facts=facts)
    assert probed.verdict == "holds"
    assert ("approximate infinity as the pseudo-infinity 1e+06"
            in probed.note)
    assert "symbolic proof region keeps the declared oo" in probed.note
    # the derive route never sees the rewrite: its proof covers the
    # actual infinity and its record carries no approximation note
    (derived,) = check_conjectures(doubled, [claim(law, route="derive")],
                                   facts=facts)
    assert derived.verdict == "proven"
    assert "pseudo-infinity" not in (derived.note or "")
