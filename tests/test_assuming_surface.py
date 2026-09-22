# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An `assuming A == B` clause makes the feasible region a
measure-zero surface. Every counterexample hunt must respect it: the
derive deciders and the extensive ladder may not disprove from
off-surface points or whole-box interval facts, and the probe sampler
solves the equality for one coordinate so trials sit exactly on the
surface instead of being rejection-sampled to nothing."""
from mathema.claims import check_conjectures, claim


def prod2(x, y):
    return x * y


def _v(law, extensive=False):
    return check_conjectures(prod2, [claim(law, route="derive")],
                             extensive=extensive)[0]


def test_true_on_surface_claim_is_never_falsified():
    # AM-GM on the surface x+y == 2: x*y <= 1 with equality at (1,1).
    # The corpus recorded this exact shape falsified from an off-surface
    # "violation" under extensive; both budgets must stay sound now
    law = "assuming x + y == 2, for x in [0,2], y in [0,2], f(x,y) <= 1"
    assert _v(law).verdict != "falsified"
    assert _v(law, extensive=True).verdict != "falsified"


def test_false_on_surface_claim_falsifies_with_an_on_surface_witness():
    law = "assuming x + y == 2, for x in [0,2], y in [0,2], f(x,y) <= 0.5"
    p = _v(law)
    assert p.verdict == "falsified"
    assert p.counterexample
    # the witness coordinates must actually satisfy x + y == 2 (the
    # printed coords are :.6g-rounded, so allow display precision)
    nums = [float(t) for t in
            p.counterexample.split(":")[0].strip("() ").split(",")]
    assert abs(sum(nums) - 2.0) < 1e-4, p.counterexample


def test_awkward_surface_still_gets_real_samples():
    # a surface no special sampling point lands on: the solved-out
    # coordinate places every trial on it, so the claim gathers real
    # evidence instead of "no sampled point satisfied the assuming
    # clause"
    law = ("assuming x + y == 2.7182, for x in [0,3], y in [0,3], "
           "f(x,y) <= 1.9")
    p = _v(law)
    assert p.verdict == "holds"
    assert p.n and p.n > 10


def test_inequality_assuming_still_adjudicates():
    # a non-equality clause takes the ordinary rejection-sampling path
    law = "assuming x >= y, for x in [0,2], y in [0,2], f(x,y) >= y*y"
    p = _v(law)
    assert p.verdict in ("proven", "holds")


def test_tolerance_governs_the_symbolic_disproof_backstop():
    # a residual inside the claim's own declared tolerance must not
    # corroborate a disproof (the backstop threshold was hardcoded
    # 1e-9 and ignored tolerance=)
    def close_fn(x):
        return x + 1e-6
    (strict_p,) = check_conjectures(
        close_fn, [claim("for x in [0,10], f(x) == x", route="derive")])
    assert strict_p.verdict == "falsified"
    (loose_p,) = check_conjectures(
        close_fn, [claim("for x in [0,10], f(x) == x", route="derive",
                         tolerance=1e-3)])
    assert loose_p.verdict in ("proven", "holds")


def test_abs_under_negated_argument_proves_on_a_positive_domain():
    # the sign-assumption bake used to collapse abs(partial) to partial
    # BEFORE f(-partial, sigma) substituted, so the negated argument
    # landed in a body sign-resolved for the original, a false
    # disproof. A sign-sensitive body with a transformed call argument
    # now keeps plain symbols (the piecewise precedent)
    def lin_unc(partial, sigma):
        return abs(partial) * sigma
    (p,) = check_conjectures(lin_unc, [claim(
        "for partial in [0.1,5], sigma in [0.1,2], "
        "f(partial,sigma) == f(-partial,sigma)", route="derive")])
    assert p.verdict == "proven"
    assert (p.meta or {}).get("mathema.corroboration") is None


def test_literal_argument_inside_the_domain_still_bakes_the_sign():
    # the negated-argument fix above must not overreach: a numeric
    # LITERAL inside the parameter's own declared domain satisfies
    # every assumption the bake derives from that domain, so the bake
    # still fires and Abs clears, f(len1, 0) == len1 proves on a
    # nonnegative domain (the corpus's guarded edit-distance shape)
    def edit_distance_lower_bound(len1, len2):
        if len1 < 0:
            raise ValueError("first length cannot be negative")
        if len2 < 0:
            raise ValueError("second length cannot be negative")
        return abs(len1 - len2)
    (p,) = check_conjectures(edit_distance_lower_bound, [claim(
        "for len1 in [0,10000], f(len1,0) == len1", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_literal_argument_outside_the_domain_keeps_plain_symbols():
    # a literal the declared domain does NOT contain can contradict the
    # baked assumption exactly like a transformed expression, the
    # bake must stay off, and the claim must not falsely prove
    def abs_body(x):
        return abs(x)
    (p,) = check_conjectures(abs_body, [claim(
        "for x in [1, 5], f(-3) == -3", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_computed_argument_to_a_bound_function_keeps_the_bake():
    # a funcs= bound function's body is lifted with plain symbols, so a
    # COMPUTED argument to it substitutes in carrying its own true
    # assumptions; f's bake stays on, and the corpus's power-rule
    # uncertainty identity proves (the last of the three Abs shapes)
    def power_absolute_uncertainty(x, sigma_x, n):
        if x <= 0:
            raise ValueError("x must be positive")
        return abs(n) * x ** (n - 1) * sigma_x

    def linear_propagated(partial, sigma):
        return abs(partial) * sigma

    (p,) = check_conjectures(power_absolute_uncertainty, [claim(
        "for x in [0.1,10], sigma_x in [0,1000], n in [1,5], "
        "f(x,sigma_x,n) == g(n*x**(n-1),sigma_x)",
        funcs={"g": linear_propagated}, route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_negated_argument_to_a_bound_function_stays_sound():
    # the mirror check: routing a negated argument through a bound
    # function must not manufacture a proof of a false claim
    def base(x):
        return x

    def g_abs(partial, sigma):
        return abs(partial) * sigma

    (p,) = check_conjectures(base, [claim(
        "for x in [0.1,5], g(-x, 1.0) == -x",
        funcs={"g": g_abs}, route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_grammar_name_resolutions_are_rendered_never_silent():
    # a parameter always wins over the vocabulary; a bare constant
    # keeps its mathematical meaning, and in both directions the
    # claim's note states the resolution (the corpus reported these as
    # silent; the loud misspecification paths for let-bound d/gamma
    # already existed and stay)
    def takes_gamma(gamma, v):
        return gamma * v

    (p,) = check_conjectures(takes_gamma, [claim(
        "for gamma in [1,5], v in [1,5], f(gamma,v) == gamma*v",
        route="derive")])
    assert p.verdict == "proven"
    assert "shadowing the grammar's gamma" in p.note

    def takes_f(f, x):
        return f * x

    (p,) = check_conjectures(takes_f, [claim(
        "for f in [1,5], x in [1,5], f(f,x) == f*x", route="derive")])
    assert p.verdict == "proven"
    assert "names both the function under test and its own parameter" in p.note

    def plain(x):
        return 2.0 * x

    (p,) = check_conjectures(plain, [claim(
        "for x in [1,5], f(x) <= e*x", route="derive")])
    assert "bare 'e' reads as the mathematical constant" in p.note

    (p,) = check_conjectures(plain, [claim(
        "let d be [1,5], for x in [1,5], f(x) <= 2*x + d",
        route="derive")])
    assert p.verdict.startswith("skipped")
    assert "reserved for its call form" in p.note


# --- the premise must survive the declared layer ----------------------

def test_the_public_check_honours_a_premise():
    """`check()` routes claims through the declared layer, so a premise
    dropped by `declare()` came back as an unconditional claim and was
    refuted from a point the premise excludes. The internal entry point
    always honoured it; only the front door did not."""
    from mathema import check
    law = "assuming x + y == 2, for x in [0,2], y in [0,2], f(x,y) <= 1"
    p = check(prod2, claims=[claim(law, route="derive")]).probes[0]
    assert p.verdict != "falsified"
    assert p.statement.startswith("assuming x + y == 2")


def test_a_premise_survives_the_declared_round_trip():
    from mathema.spec import declare, entry_claims
    law = "assuming k != 0, for x in [1,10], k in [-5,5], f(x, k) == x*k"
    declared = declare(claim(law))
    assert declared["statement"].startswith("assuming k != 0")
    assert entry_claims({"claims": [declared]})[0].assuming == "assuming k != 0"


def test_a_conditional_claim_does_not_collide_with_its_unconditional_twin():
    """Same statement, different premise: docsync compared them equal
    and let one supersede the other."""
    from mathema.sync import _claim_identity as _claim_fingerprint
    from mathema.spec import declare
    bare = _claim_fingerprint(declare(claim("for x in [0,2], y in [0,2], f(x,y) <= 1")))
    cond = _claim_fingerprint(declare(
        claim("assuming x + y == 2, for x in [0,2], y in [0,2], f(x,y) <= 1")))
    assert bare != cond


# --- rendering round-trips --------------------------------------------

def test_every_assuming_spelling_renders_stably_in_both_modes():
    """A rendered claim is reparsed by docsync, by `entry_claims`, and
    by anyone reading a record. Render -> parse -> render must be a
    fixed point, or a claim drifts every time it passes through."""
    from mathema.lexicon import LEXICON
    from mathema.spec import render_claim_text

    spellings = {k: v for k, v in LEXICON.items() if k.startswith("assuming")}
    assert spellings, "the lexicon documents assuming spellings; none found"
    for name, law in spellings.items():
        for unicode_mode in (False, True):
            once = render_claim_text(claim(law), unicode=unicode_mode)
            twice = render_claim_text(claim(once), unicode=unicode_mode)
            assert once == twice, f"{name} drifts on reparse:\n{once}\n{twice}"


def test_a_rendered_premise_survives_reparse():
    from mathema.spec import render_claim_text
    for unicode_mode in (False, True):
        text = render_claim_text(
            claim("assuming k != 0, f(x, k) == x/k"), unicode=unicode_mode)
        assert "k != 0" in text
        assert claim(text).assuming


# --- premises resolve by dependency, not by declaration order ---------

def _grow(x):
    """Doubles its input."""
    return 2 * x


def _batch(laws):
    from mathema.claims import check_conjectures as _cc
    return {p.name: p for p in _cc(_grow, laws)}


def test_a_premise_declared_after_its_conclusion_still_resolves():
    """Declaration order is the author's, not a dependency statement.
    A forward reference used to skip for a reason that had nothing to
    do with the claim."""
    out = _batch([
        claim("assuming grows holds, for x in [0,10], f(x) == 2*x", name="doubles"),
        claim("for x in [0,10], f(x) >= x", name="grows"),
    ])
    assert out["doubles"].verdict in ("proven", "holds")
    assert "prerequisite" not in (out["doubles"].note or "")


def test_results_come_back_in_declaration_order():
    from mathema.claims import check_conjectures as _cc
    names = [p.name for p in _cc(_grow, [
        claim("assuming grows holds, for x in [0,10], f(x) == 2*x", name="doubles"),
        claim("for x in [0,10], f(x) >= x", name="grows"),
    ])]
    assert names == ["doubles", "grows"]


def test_a_premise_cycle_is_reported_as_one():
    from mathema.reason_codes import claim_reason_code
    out = _batch([
        claim("assuming b holds, for x in [0,10], f(x) == 2*x", name="a"),
        claim("assuming a holds, for x in [0,10], f(x) >= x", name="b"),
    ])
    for name in ("a", "b"):
        assert out[name].verdict == "skipped"
        assert claim_reason_code(out[name]) == "dependency-cycle"


def test_a_premise_naming_no_claim_is_undecided_not_blocked():
    from mathema.records import stance
    from mathema.reason_codes import claim_reason_code
    p = _batch([claim("assuming nowhere holds, for x in [0,10], f(x) == 2*x",
                      name="c")])["c"]
    assert p.verdict == "unknown" and stance(p.verdict) == "undecided"
    assert claim_reason_code(p) == "missing-prerequisite"


def test_an_ambiguous_premise_reference_refuses_to_guess():
    from mathema.reason_codes import claim_reason_code
    out = _batch([
        claim("for x in [0,10], f(x) >= x", name="twin"),
        claim("for x in [0,10], f(x) >= 0", name="twin"),
        claim("assuming twin holds, for x in [0,10], f(x) == 2*x", name="rests"),
    ])
    assert claim_reason_code(out["rests"]) == "ambiguous-reference"


def test_an_empirical_premise_caps_a_conclusion_on_either_route():
    """A claim is no better established than what it rests on, and the
    downgrade is machine-readable rather than prose only."""
    out = _batch([
        claim("for x in [0,10], f(x) >= x", name="grows", route="probe"),
        claim("assuming grows holds, for x in [0,10], f(x) == 2*x", name="doubles"),
    ])
    assert out["grows"].verdict == "holds"
    assert out["doubles"].verdict == "holds"
    assert out["doubles"].meta["mathema.capped_by"] == "grows"


def test_a_claim_may_rest_on_several_lemmas():
    """`assuming X is proven and Y holds` is in the grammar's own
    docstring and the section-parsing tests; it parsed and then failed
    interpretation, because the verdict matcher took a single name."""
    out = _batch([
        claim("assuming grows is proven and positive holds, "
              "for x in [0,10], f(x) == 2*x", name="both"),
        claim("for x in [0,10], f(x) >= x", name="grows"),
        claim("for x in [0,10], f(x) >= 0", name="positive"),
    ])
    assert out["both"].verdict in ("proven", "holds")
    assert "prerequisite" not in (out["both"].note or "")


def test_the_weakest_of_several_lemmas_bounds_the_conclusion():
    out = _batch([
        claim("assuming grows is proven and positive holds, "
              "for x in [0,10], f(x) == 2*x", name="both"),
        claim("for x in [0,10], f(x) >= x", name="grows"),
        claim("for x in [0,10], f(x) >= 0", name="positive", route="probe"),
    ])
    assert out["grows"].verdict == "proven"
    assert out["positive"].verdict == "holds"
    assert out["both"].verdict == "holds"
    assert out["both"].meta["mathema.capped_by"] == "positive"


def test_mixing_lemmas_and_conditions_in_one_clause_is_refused_clearly():
    p = _batch([claim("assuming grows holds and k != 0, "
                      "for x in [0,10], f(x) == 2*x", name="mixed")])["mixed"]
    assert p.verdict.startswith("skipped")
    assert "lemma references with other conditions" in p.note


# --- a discharged lemma lends its content, but only where it holds ----

def test_a_discharged_lemma_contributes_its_statement():
    """`assuming X holds` gated on X's verdict and then threw X away.
    A proven lemma is a true statement, so the proof may use it."""
    from mathema.conjecture import _lemma_conjuncts
    lemma = claim("for a in [-10,10], b in [-10,10], f(a,b) == b - a",
                  name="is_gap")
    target = claim("assuming is_gap holds, for a in [-10,10], "
                   "b in [-10,10], f(a,b) <= 20")
    lent = _lemma_conjuncts([lemma], target, dict(lemma.domain))
    assert [f"{r.lhs} {r.relation} {r.rhs}" for r in lent] == ["f(a,b) == b - a"]


def test_a_lemma_lends_nothing_outside_the_region_it_was_proven_over():
    """The soundness guard: a lemma established on [-10,10] says
    nothing at x = -100, so a claim quantified more widely must not
    borrow it."""
    from mathema.conjecture import _lemma_conjuncts
    from mathema.grammar import domain_bound_from_json
    lemma = claim("for a in [-10,10], b in [-10,10], f(a,b) == b - a",
                  name="is_gap")
    target = claim("assuming is_gap holds, for a in [-100,100], "
                   "b in [-100,100], f(a,b) <= 200")
    wider = {p: domain_bound_from_json([-100, 100]) for p in lemma.domain}
    assert _lemma_conjuncts([lemma], target, wider) == []


def test_a_lemma_that_cannot_lend_still_gates_and_still_caps():
    """Not lending content is not the same as not being a premise."""
    out = _batch([
        claim("for x in [0,5], f(x) >= x", name="grows", route="probe"),
        claim("assuming grows holds, for x in [0,10], f(x) == 2*x", name="doubles"),
    ])
    assert out["doubles"].meta["mathema.capped_by"] == "grows"


# --- every section must survive the declared round trip ---------------
#
# Reported from a real repository run: `adjudicate_target` and
# `verify_project` disagreed about the same claim, because the store
# held less than the author wrote.

def _roundtrip(law):
    from mathema.spec import declare, entry_claims
    return entry_claims({"claims": [declare(claim(law))]})[0]


def test_a_chained_comparison_keeps_both_links():
    """`0 <= f(x) < 1` was stored as `0 <= f(x)`, so the record stated
    a strictly weaker claim: adjudicate_target falsified it and
    verify_project, reading the record, proved it."""
    original = claim("for mi in [0,100], 0 <= f(mi) < 1")
    restored = _roundtrip("for mi in [0,100], 0 <= f(mi) < 1")
    assert restored.links == original.links
    assert len(restored.links) == 2


def test_a_free_variable_keeps_its_bound():
    """`let c be [a,b]` lost its bound in the store, so the probe route
    sampled from +-1e6 and falsified out of domain."""
    original = claim("let c be [-5,5], for x in [0,10], f(x) + c >= 0")
    restored = _roundtrip("let c be [-5,5], for x in [0,10], f(x) + c >= 0")
    assert set(restored.free_vars) == set(original.free_vars) == {"c"}
    assert restored.domain["c"] is not None


def test_a_bound_function_keeps_its_binding():
    restored = _roundtrip("let g = math.sqrt, for x in (0,100], g(x) >= 0")
    assert restored.funcs.get("g") == "math.sqrt"


def test_an_ordinary_claim_is_unchanged_by_all_this():
    from mathema.spec import declare
    assert declare(claim("for x in [0,1], f(x) >= 0"))["statement"] == "f(x) >= 0"
