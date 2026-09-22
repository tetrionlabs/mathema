# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`d(...)` ergonomics: the `d(<expr>/d<var>)` fraction spelling (scoped
to inside a `d(...)` call, deferred-checked against the real function's
parameters once known); `d(<expr>)`'s own variable-omitted inference and
prime notation (`f'(x)`/`f''(x)`), both purely textual; `@{...}`/`at
{...}`, an evaluation marker with optional whitespace around it, for
differentiating then substituting a value. `integrate(...)`'s own
`|_{lo}^{hi}` bar (bare tokens need no braces, only a bound with its own
space or comma does), `∫`/`integral` synonyms, and a bracket-free
multivariable form chaining one bound-bar per differential. `lim`'s own
bracket-free form, with the variable always named explicitly."""
from mathema.conjecture import check_conjectures, claim
from mathema.grammar import normalize


def square(x: float) -> float:
    return x ** 2


def gibbs_free_energy(dh: float, t: float, ds: float) -> float:
    return dh - t * ds


def prod2(x: float, y: float) -> float:
    return x * y


def recip(x: float) -> float:
    return 1 / x


# --- d(<expr>/d<var>) fraction sugar ----------------------------------------

def test_fraction_sugar_normalizes_to_the_comma_form():
    cj = claim("d(f(x)/dx) == 2*x", route="derive")
    assert cj.lhs == "d(f(x), x)"
    assert cj.ambiguous_diff_vars == frozenset({"dx"})


def test_fraction_sugar_only_the_last_top_level_division_is_the_marker():
    cj = claim("d((1 + f(x))/(2+3)/dx) == 2*x/5", route="derive")
    assert cj.lhs == "d((1 + f(x))/(2+3), x)"


def test_plain_comma_form_has_no_ambiguous_vars():
    cj = claim("d(f(x), x) == 2*x", route="derive")
    assert cj.ambiguous_diff_vars == frozenset()


def test_fraction_sugar_proves_correctly_end_to_end():
    result = check_conjectures(square, [claim("d(f(x)/dx) == 2*x", route="derive")])[0]
    assert result.verdict == "proven"


def test_fraction_sugar_division_escape_hatch_proves_correctly():
    result = check_conjectures(
        square, [claim("d((1 + f(x))/(2+3)/dx) == 2*x/5", route="derive")])[0]
    assert result.verdict == "proven"


def test_fraction_sugar_real_collision_is_skipped_misspecified():
    # dh is a genuine parameter of gibbs_free_energy; d(expr/dh) can't
    # safely be guessed as "differentiate w.r.t. h" without checking.
    result = check_conjectures(
        gibbs_free_energy, [claim("d(f(dh,t,ds)/dh) == -ds", route="derive")])[0]
    assert result.verdict == "skipped:misspecified"
    assert "dh" in result.note
    assert "d(expr, h)" in result.note


def test_fraction_sugar_no_collision_when_denominator_is_not_a_real_param():
    # h is not a real parameter of gibbs_free_energy; the guess is safe.
    def g(h: float, t: float) -> float:
        return h * t

    result = check_conjectures(g, [claim("d(f(h,t)/dh) == t", route="derive")])[0]
    assert result.verdict == "proven"


# --- d(<expr>) variable-omitted inference + prime notation ------------------

def test_d_single_arg_infers_the_sole_free_name():
    assert normalize("d(f(x)) == 2*x") == "d(f(x), x) == 2*x"


def test_d_single_arg_ambiguous_or_empty_is_left_unexpanded():
    assert normalize("d(f(x,y)) >= 0") == "d(f(x,y)) >= 0"
    assert normalize("d(3+4) >= 0") == "d(3+4) >= 0"


def test_d_single_arg_unaffected_when_a_variable_is_already_given():
    assert normalize("d(f(x), x) >= 0") == "d(f(x), x) >= 0"


def test_prime_notation_normalizes_to_the_comma_form():
    assert normalize("f'(x) == 2*x") == "d(f(x), x) == 2*x"
    assert normalize("f''(x) == 2") == "d(f(x), x, x) == 2"


def test_prime_notation_ambiguous_is_left_unexpanded():
    assert normalize("f'(x, y) >= 0") == "f'(x, y) >= 0"


def test_d_single_arg_and_prime_prove_correctly_end_to_end():
    r1 = check_conjectures(square, [claim("d(f(x)) == 2*x", route="derive")])[0]
    assert r1.verdict == "proven"
    r2 = check_conjectures(square, [claim("f'(x) == 2*x", route="derive")])[0]
    assert r2.verdict == "proven"
    r3 = check_conjectures(square, [claim("f''(x) == 2", route="derive")])[0]
    assert r3.verdict == "proven"


def test_d_call_is_still_derive_only():
    result = check_conjectures(square, [claim("d(f(x)) == 2*x", route="probe")])[0]
    assert result.verdict == "skipped"


# --- @{...}/at {...} evaluation marker --------------------------------------

def test_at_marker_normalizes_with_any_whitespace_around_it():
    expected = "d(f(x,y), x, __at__, x, 1, y, 2) == 5"
    for text in (
        "d(f(x,y), x)@{x=1, y=2} == 5",
        "d(f(x,y), x) @ {x=1, y=2} == 5",
        "d(f(x,y), x)@ {x=1, y=2} == 5",
        "d(f(x,y), x) at{x=1, y=2} == 5",
        "d(f(x,y), x)  at  {x=1, y=2} == 5",
    ):
        assert normalize(text) == expected


def test_bar_suffix_is_not_an_evaluation_marker_for_d():
    text = "d(f(x,y), x)|_{x=1, y=2} == 5"
    assert normalize(text) == text


def test_at_marker_composes_with_prime_and_proves_correctly():
    result = check_conjectures(square, [claim("f'(x) at {x=2} == 4", route="derive")])[0]
    assert result.verdict == "proven"


def test_at_marker_render_does_not_leak_the_sentinel():
    from mathema.spec import render_claim_text
    cj = claim("d(f(x,y), x) at {x=1, y=2} == 5", route="derive")
    rendered = render_claim_text(cj)
    assert "__at__" not in rendered
    assert "at {x=1, y=2}" in rendered or "at {y=2, x=1}" in rendered


# --- integrate: bar bound convention, ∫/integral synonyms -------------------

def test_integrate_bar_bare_token_needs_no_braces():
    assert (normalize("integrate(f(x), x)|_0^oo == 1")
           == "integrate(f(x), x, 0, oo) == 1")


def test_integrate_bar_multi_char_bound_with_no_space_needs_no_braces_either():
    assert (normalize("integrate(f(x, mu, sigma), x)|_{-oo}^{oo} == 1")
           == "integrate(f(x, mu, sigma), x, -oo, oo) == 1")


def test_integrate_single_arg_infers_the_sole_free_name():
    assert (normalize("integrate(f(x))|_0^oo == 1")
           == "integrate(f(x), x, 0, oo) == 1")


def test_integrate_single_arg_ambiguous_is_left_unexpanded():
    assert normalize("integrate(f(x,y))|_0^oo == 1").startswith("integrate(f(x,y))|_0")


def test_integral_and_symbol_are_synonyms_for_integrate():
    assert (normalize("∫(f(x), x) >= 0")
           == normalize("integral(f(x), x) >= 0")
           == normalize("integrate(f(x), x) >= 0"))


def test_integral_bracket_free_single_var_omitted():
    assert (normalize("integral f(x)|_0^oo >= 0")
           == "integrate(f(x), x, 0, oo) >= 0")


def test_integral_bracket_free_multivariable_chained_bounds():
    assert (normalize("integral f(x,y) dx|_0^1 dy|_0^2 >= 0")
           == "integrate(f(x,y), x, 0, 1, y, 0, 2) >= 0")


def test_integral_bound_accepts_an_unbraced_compound_expression():
    # a bare bound is the whole non-whitespace run, not just its
    # leading word/number, "pi/2" used to silently truncate to "pi",
    # leaving "/2" to apply to the whole integral instead
    # ("integrate(f(x), x, 0, pi)/2", a wrong answer, not a skip).
    assert (normalize("integral f(x) dx|_0^pi/2 >= 0")
           == "integrate(f(x), x, 0, pi/2) >= 0")
    assert (normalize("integral f(x) dx|_0^2*pi >= 0")
           == "integrate(f(x), x, 0, 2*pi) >= 0")
    # braces still work exactly the same as before.
    assert (normalize("integral f(x) dx|_0^{pi/2} >= 0")
           == "integrate(f(x), x, 0, pi/2) >= 0")


def test_integral_lower_bound_also_accepts_a_compound_expression():
    # the lower bound is scanned with the same function, must stop
    # at the "^" mark separating it from the upper bound, not swallow
    # it into the run (that would silently break the whole |_lo^hi
    # match, not just mis-scan the lower bound itself).
    assert (normalize("integral f(x) dx|_pi/2^pi >= 0")
           == "integrate(f(x), x, pi/2, pi) >= 0")
    assert (normalize("integral f(x) dx|_pi/4^pi/2 >= 0")
           == "integrate(f(x), x, pi/4, pi/2) >= 0")


def test_integral_compound_bound_renders_with_a_graceful_unicode_fallback():
    # _integral_bound_marker's decorative subscript/superscript digits
    # are plain-integer-only by design, a compound/fractional bound
    # falls back to the ordinary call form, same as a symbol or `oo`
    # bound already did before this fix, not a new gap. `pi` itself
    # still renders as the "π" glyph in that fallback (see
    # _print_Pi), so the bound reads "0, π/2", not "0, pi/2".
    from mathema.spec import render_claim_text

    cj = claim("integral f(x) dx|_0^pi/2 >= 0")
    assert render_claim_text(cj, unicode=True) == "∫(f(x), x, 0, π/2) ≥ 0"
    assert render_claim_text(cj, unicode=False) == "integrate(f(x), x, 0, pi/2) >= 0"


def test_pi_and_infinity_render_as_glyphs_in_unicode_only():
    from mathema.grammar import render_law_expr

    for expr, unicode_glyph, ascii_word in (
        ("pi", "π", "pi"), ("-pi", "-π", "-pi"), ("pi/2", "π/2", "pi/2"),
        ("-pi/2", "-π/2", "-pi/2"), ("oo", "∞", "oo"), ("-oo", "-∞", "-oo"),
    ):
        assert render_law_expr(expr, unicode=True) == unicode_glyph
        assert render_law_expr(expr, unicode=False) == ascii_word


def test_integral_compound_bound_proves_correctly_end_to_end():
    import math

    def cos_fn(x: float) -> float:
        return math.cos(x)

    result = check_conjectures(
        cos_fn, [claim("integral f(x) dx|_0^pi/2 == 1", route="derive")])[0]
    assert result.verdict == "proven"


def test_integrate_var_omitted_proves_correctly_end_to_end():
    result = check_conjectures(square, [claim("integral f(x)|_0^oo == oo", route="derive")])[0]
    assert result.verdict == "proven"


def test_integral_multivariable_proves_correctly_end_to_end():
    result = check_conjectures(
        prod2, [claim("integral f(x,y) dx|_0^1 dy|_0^2 == 1", route="derive")])[0]
    assert result.verdict == "proven"


# --- lim: bracket-free form, variable always explicit -----------------------

def test_lim_bracket_free_explicit_var():
    assert normalize("lim f(x), x -> a >= 0") == "lim(f(x), x, a)>= 0"


def test_lim_bracket_free_as_is_a_comma_synonym():
    assert normalize("lim f(x) as x -> a >= 0") == "lim(f(x), x, a)>= 0"


def test_lim_variable_omitted_forms_are_not_supported():
    # unlike d/integrate, lim never infers its own variable, `lim
    # f(x) -> a` reads ambiguously without it, so it's left unexpanded
    # (and the parenthesized 2-argument shape is likewise untouched).
    assert normalize("lim f(x) -> a >= 0") == "lim f(x) -> a >= 0"
    assert normalize("lim(f(x), a) >= 0") == "lim(f(x), a) >= 0"


def test_lim_bracket_free_prove_correctly_end_to_end():
    r1 = check_conjectures(recip, [claim("lim f(x), x -> oo == 0", route="derive")])[0]
    assert r1.verdict == "proven"
    r2 = check_conjectures(recip, [claim("lim f(x) as x -> oo == 0", route="derive")])[0]
    assert r2.verdict == "proven"


def test_infinity_word_is_a_real_constant_not_a_free_variable():
    # a real, silent-wrong-answer bug: "infinity" wasn't recognized
    # anywhere as a spelling of the "oo" constant, so `lim f(x) as x ->
    # infinity == 0` treated "infinity" as an ordinary free variable
    # (never taking a limit at all) and could return a confidently
    # wrong "falsified" with a sampled counterexample, not even a
    # "skipped". _math_vocab._MATH_ATTRS now recognizes it directly,
    # the same way "oo" itself already is.
    r = check_conjectures(recip, [claim("lim f(x) as x -> infinity == 0", route="derive")])[0]
    assert r.verdict == "proven"


def test_infinity_word_works_as_a_domain_bound_too():
    cj = claim("for x in [0, infinity], f(x) >= 0")
    assert cj.domain["x"] == (0.0, float("inf"))
    cj2 = claim("for x in [-infinity, 0], f(x) >= 0")
    assert cj2.domain["x"] == (float("-inf"), 0.0)


def test_pv_traditional_spelling_normalizes_and_renders():
    # `P.V.(...)` is the traditional principal-value spelling, not
    # valid Python call syntax, so normalize() folds it to the internal
    # `cauchy_pv(` form (deliberately not `PV(`: PV stays an ordinary
    # name, free for a present-value function's own parameter); the
    # rendered form prints `P.V.` again.
    from mathema.grammar import normalize
    assert normalize("f(c) == P.V.(integrate(1/(x - c), x, -1, 1))") \
        == normalize("f(c) == cauchy_pv(integrate(1/(x - c), x, -1, 1))")
    assert "cauchy_pv(" in normalize("P.V.(integrate(1/x, x, -1, 1)) == 0")


def test_pv_as_an_ordinary_parameter_name_never_collides():
    # a present-value function's parameter named PV is just a name: it
    # binds, proves, and renders with no reserved meaning anywhere
    from mathema.conjecture import claim, check_conjectures

    def present_value(PV, r, n):
        return PV / (1 + r) ** n

    (p,) = check_conjectures(present_value, [claim(
        "for PV in [100, 1000], r in [0.01, 0.2], n in [1, 10], "
        "f(PV, r, n) <= PV", route="derive")])
    assert p.verdict == "proven"


def periapsis(GM: float, a: float, e: float) -> float:
    # e is eccentricity, a genuine domain variable, not Euler's number
    return (GM / a) * (1 + e) / (1 - e)


def test_differentiate_wrt_a_param_named_e_does_not_resolve_to_eulers_number():
    # a parameter literally named `e`/`pi`/`oo` differentiated with
    # respect to is the variable, not the math constant the bare token
    # otherwise resolves to. Rendering built `Derivative(expr, E)`, which
    # sympy rejects ("Can't calculate derivative wrt E"); it must render
    # and adjudicate as the ordinary variable now.
    from mathema.spec import canonical_claim_text

    law = ("for GM in [1, 1000], a in [10, 100], e in [0, 0.9], "
           "d(f(GM, a, e), e) >= 0")
    (pr,) = check_conjectures(periapsis, [claim(law, route="derive")])
    assert pr.verdict == "proven"
    assert "d(f(GM, a, e), e)" in pr.statement        # rendered, not crashed
    # the evaluation-bar form differentiates then substitutes e too
    at = claim("for GM in [1, 1000], a in [10, 100], e in [0, 0.9], "
               "d(f(GM, a, e), e)@{e=0.5} >= 0")
    assert "e=0.5" in canonical_claim_text(at)

    # the bare token `e` in value position is still Euler's number
    assert canonical_claim_text(claim("for x in [1, 5], f(x) == e")).endswith("= e")
