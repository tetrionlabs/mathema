# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`assuming is_defined(f)`: the claim quantifies over the exact region
where every call to f returns. The region is computed (negated raise
guards, per call) and rendered into the statement, never an opaque
"wherever defined", and both routes honor it: derive excludes the
raise regions by construction and gains their negations as algebraic
assumptions, probe rejects raising samples as outside the quantifier."""
import math

from mathema.conjecture import claim, check_conjectures
from mathema.spec import render_claim_text


def oscillator_amplitude(F0, k, m, w, c):
    return F0 / math.sqrt((k - m*w*w)**2 + (c*w)**2)


_LAW = ("assuming is_defined(f), for F0 in [0.1,10], k in [0.1,100], "
        "m in [0.1,10], w in [-50,50], c in [0,5], "
        "f(F0,k,m,-w,c) == f(F0,k,m,w,c)")


def test_symmetry_proves_under_is_defined_with_the_exact_region_rendered():
    (p,) = check_conjectures(oscillator_amplitude,
                             [claim(_LAW, route="derive")])
    assert p.verdict == "proven"
    assert "assuming f is defined" in p.statement
    assert "!= 0" in p.statement   # the computed region, spelled out


def test_without_the_clause_no_proof_only_empirical_evidence():
    # the undamped-resonance raise region (c = 0, k = m*w^2) sits
    # inside this box, so the unconditional claim can't prove; the
    # probe fallback supplies holds-strength evidence only
    bare = _LAW.replace("assuming is_defined(f), ", "")
    (p,) = check_conjectures(oscillator_amplitude,
                             [claim(bare, route="derive")])
    assert p.verdict != "proven"


def test_probe_route_rejects_raising_samples_as_outside_the_quantifier():
    (p,) = check_conjectures(oscillator_amplitude,
                             [claim(_LAW, route="probe")])
    assert p.verdict == "holds"


def test_postfix_natural_language_form_is_equivalent():
    (p,) = check_conjectures(
        oscillator_amplitude,
        [claim(_LAW.replace("is_defined(f)", "f is defined"), route="derive")])
    assert p.verdict == "proven"
    assert "f is defined" in p.statement


def test_bare_defined_is_not_a_recognized_spelling():
    # only `is_defined(f)` and `f is defined` are the accepted forms
    (p,) = check_conjectures(
        oscillator_amplitude,
        [claim(_LAW.replace("is_defined(f)", "defined(f)"), route="derive")])
    assert p.verdict == "skipped"
    assert "assuming" in (p.note or "")


def test_rendered_statement_round_trips_with_the_pinned_region():
    # the record's statement pins the resolved region behind `-->`;
    # reparsing consumes that region VERBATIM, never recomputing from
    # the (possibly changed) body, and reaches the same verdict
    (p,) = check_conjectures(oscillator_amplitude,
                             [claim(_LAW, route="derive")])
    assert p.verdict == "proven"
    assert "f is defined -->" in p.statement

    (rp,) = check_conjectures(oscillator_amplitude,
                              [claim(p.statement, route="derive")])
    assert rp.verdict == "proven"
    assert "f is defined -->" in rp.statement

    # a pin is validated, not trusted: against a DIFFERENT body (a
    # total function, no raise regions) the recorded region no longer
    # matches, so it is recomputed and the note says so; the premise
    # itself survives, arrow-free, because there is no region to state
    def other_body(F0, k, m, w, c):
        return F0 + k + m + w + c

    (rp2,) = check_conjectures(other_body, [claim(p.statement, route="derive")])
    assert "assuming f is defined" in rp2.statement
    assert "-->" not in rp2.statement
    assert "no longer matches the code" in (rp2.note or "")


def test_conjunction_assumptions_thread_through_both_routes():
    def scaled(x, k, j):
        return x / (k * j)

    law = ("assuming k != 0 and j > 0, for x in [1, 5], "
           "f(x, k, j) * k * j == x")
    (p,) = check_conjectures(scaled, [claim(law, route="derive")])
    assert p.verdict == "proven"
    (p,) = check_conjectures(scaled, [claim(law, route="probe")])
    assert p.verdict == "holds"


def test_named_reference_renders_pinned_with_the_arrow():
    def quad(a, b, c):
        return a + b + c

    rs = check_conjectures(quad, [
        claim("b^2 - 4*a*c >= 0.01", name="real_roots"),
        claim("assuming real_roots, for a in [1,2], f(a,b,c) == a + b + c",
              route="derive"),
    ])
    assert "real_roots --> b**2 - 4*a*c >= 0.01" in rs[1].statement


def test_the_definedness_premise_has_one_spelling_everywhere():
    """`is_defined(f)` and `f is defined` are the same premise, so they
    must not produce two statements, two fingerprints, or two claims.
    The postfix spelling is the canonical one; it reads as the claim
    it stands for."""
    from mathema.grammar import normalize

    written_as_call = claim("assuming is_defined(f), f(x) == f(x)")
    written_postfix = claim("assuming f is defined, f(x) == f(x)")
    assert written_as_call.assuming == written_postfix.assuming
    assert written_as_call.assuming == "assuming f is defined"

    for unicode_mode in (True, False):
        text = render_claim_text(written_as_call, unicode=unicode_mode)
        assert "f is defined" in text
        assert claim(text).assuming == written_as_call.assuming

    # the safety-predicate vocabulary still round-trips its spaced form
    assert "is_pole_safe(x)" in normalize("is pole safe(x)")


def test_is_defined_family_region_equivalence():
    # a declared claim NAMED is_defined adjudicates as region
    # equivalence against the current body: match -> proven; a drifted
    # statement -> falsified naming the fresh region; a total function
    # -> falsified (the region is the whole domain)
    rs = check_conjectures(oscillator_amplitude, [
        claim("sqrt(c^2*w^2 + (k - m*w^2)^2) != 0", name="is_defined",
              route="derive")])
    assert rs[0].verdict == "proven"
    assert rs[0].meta.get("mathema.derive_route") == "definedness_equivalence"

    rs = check_conjectures(oscillator_amplitude, [
        claim("sqrt(c^2*w^2 + (k - m*w^2)^2) != 1", name="is_defined",
              route="derive")])
    assert rs[0].verdict == "falsified"
    assert "fresh region" in rs[0].sketch

    def total_fn(x):
        return x + 1

    rs = check_conjectures(total_fn, [claim("x != 0", name="is_defined",
                                            route="derive")])
    assert rs[0].verdict == "falsified"
    assert "no raise regions" in rs[0].sketch


def test_assuming_references_the_declared_is_defined_claim():
    rs = check_conjectures(oscillator_amplitude, [
        claim("sqrt(c^2*w^2 + (k - m*w^2)^2) != 0", name="is_defined",
              route="derive"),
        claim("assuming is_defined, " + _LAW.split(", ", 1)[1],
              route="derive"),
    ])
    assert rs[1].verdict == "proven"
    assert "is_defined --> " in rs[1].statement


def test_is_defined_is_suggested_for_a_partial_function():
    from mathema.suggest import suggest_claims

    names = {c.name: c for c in suggest_claims(oscillator_amplitude)}
    assert "is_defined" in names
    assert names["is_defined"].source == "mathema"
    assert "!=" in f"{names['is_defined'].lhs} {names['is_defined'].relation}"


def test_outcome_marker_still_splits_outcome_shaped_text_only():
    from mathema.grammar import extract_outcome_clause

    outcome, rest = extract_outcome_clause("f(x) == x => self.foo proven")
    assert outcome == "self.foo proven" and rest == "f(x) == x"
    outcome, rest = extract_outcome_clause(
        "assuming a >= 0 --> b >= 0, f(a) == a")
    assert outcome is None


def test_multi_conjunct_region_suggests_and_adjudicates_per_conjunct():
    from mathema.suggest import suggest_claims

    def two_guards(x, y):
        if x <= 0:
            raise ValueError("x must be positive")
        return math.sqrt(y) / x

    names = sorted(c.name for c in suggest_claims(two_guards)
                   if c.name.startswith("is_defined"))
    # the minimal region: x > 0 (the explicit guard) and y >= 0 (the
    # sqrt lemma, recovered from its And-shaped path guard); the
    # division's Eq(x, 0) conjunct simplifies away as unsatisfiable
    # under x > 0
    assert names == ["is_defined[1]", "is_defined[2]"]

    # membership in the fresh region proves; drift falsifies; and an
    # is_defined claim NEVER falls through to the raw relation reading
    rs = check_conjectures(two_guards, [
        claim("y >= 0", name="is_defined[2]", route="derive"),
        claim("y >= 1", name="is_defined[2]", route="derive"),
    ])
    assert rs[0].verdict == "proven"
    assert "conjunct" in rs[0].sketch
    assert rs[1].verdict == "falsified"
    assert "fresh region" in rs[1].sketch

    (p,) = check_conjectures(two_guards, [
        claim("y >= 0", name="is_defined[2]", route="probe")])
    assert p.verdict == "skipped"
    assert "region equivalence" in p.note


def _guarded(x):
    if x < 0:
        raise ValueError("negative")
    return x ** 0.5


def _total(x):
    return x * 2.0


def test_bare_is_defined_claims_totality_not_a_restriction():
    # the same predicate carries both readings, told apart by whether a
    # region is stated: `is_defined(f)` with no region asserts the
    # function is defined EVERYWHERE (total), while a stated region
    # asserts definedness is restricted to exactly it. Overloaded
    # deliberately: one name, and the English reads right either way.
    (p,) = check_conjectures(_total, [claim("is_defined(f)", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    # a function-wide predicate aggregates per parameter, so the
    # summary rides the note
    assert "is_defined" in (p.sketch or p.note or "")

    # the postfix spelling is the same claim
    (p,) = check_conjectures(_total, [claim("f is defined", route="derive")])
    assert p.verdict == "proven"

    # a function that raises is NOT total: falsified, naming where
    (p,) = check_conjectures(_guarded, [claim("is_defined(f)",
                                              route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert "x >= 0" in p.sketch          # the region it is actually defined on


def test_stated_region_still_reads_as_a_restriction():
    # the restriction reading is untouched by the overload
    (p,) = check_conjectures(_guarded, [claim("x >= 0", name="is_defined",
                                              route="derive")])
    assert p.verdict == "proven"
    (p,) = check_conjectures(_total, [claim("x >= 0", name="is_defined",
                                            route="derive")])
    assert p.verdict == "falsified"
    assert "no raise regions" in p.sketch
    # and the message says WHY the claim does not apply to a total function
    assert "restriction" in p.sketch
