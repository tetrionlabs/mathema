# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The statement grammar: normalization, quantifier lifting, LaTeX
rendering, function bindings, and the raises(...) predicate."""
import pytest

import ast

import sympy

from mathema._math_vocab import _SYMPY_FUNCS
from mathema.conjecture import check_conjectures, claim
from mathema.grammar import (MISSING, Domain, Interval, NoRelation,
                             is_missing, _node_to_sympy, normalize,
                             parse_raises, render_domain_bound,
                             split_quantifier, split_relation,
                             to_canonical, to_latex)


def clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def halve(x: float) -> float:
    return x / 2.0


def halve_twin(x: float) -> float:
    return 0.5 * x


def gated_sqrt(x: float) -> float:
    if x < 0:
        raise ValueError("x must be nonnegative")
    return x ** 0.5


def test_normalize_spellings_converge():
    assert normalize("f(x)^2 ≥ 0") == "f(x)**2 >= 0"
    assert normalize("f(x)**2 >= 0") == "f(x)**2 >= 0"
    assert normalize("π · x") == "pi * x"


def test_split_relation_single_equals():
    assert split_relation("f(-x) = -f(x)") == ("f(-x)", "==", "-f(x)")
    with pytest.raises(NoRelation):
        split_relation("f(x) + 1")


def test_quantifier_lifts_into_domain():
    dom, law = split_quantifier(normalize("∀x ∈ [0, 1], f(x) <= 1"))
    assert dom == {"x": (0.0, 1.0)} and law == "f(x) <= 1"
    dom, law = split_quantifier("for x in [0, 1], c in [-2, 2], f(x + c) <= 1 + c")
    assert dom == {"x": (0.0, 1.0), "c": (-2.0, 2.0)}
    assert split_quantifier("raises(f(x))") == ({}, "raises(f(x))")


def test_quantifier_intensity_modifier_lifts_into_domain_n():
    dom, law = split_quantifier("for x in [0, 1], n=500, f(x) <= 1")
    assert dom == {"x": (0.0, 1.0), "n": 500} and law == "f(x) <= 1"
    dom, law = split_quantifier("for n=50, f(x) <= 1")
    assert dom == {"n": 50}


def test_claim_carries_lifted_domain():
    c = claim("for x in [0, 1], f(x) <= 1")
    assert c.domain == {"x": (0.0, 1.0)}
    assert (c.lhs, c.relation, c.rhs) == ("f(x)", "<=", "1")


def test_quantified_claim_adjudicated_inside_domain():
    # f(x) <= 1 is false on all reals but true on [0, 1]
    results = check_conjectures(clamp01, [claim("for x in [0, 1], f(x) <= 1")])
    assert results[0].verdict == "proven"   # default best route: it lifts
    results = check_conjectures(clamp01, [claim("f(x) >= 1")])
    assert results[0].verdict == "falsified"


def test_parse_raises_forms():
    assert parse_raises("raises(f(x))") == ("f(x)", None)
    assert parse_raises("raises(f(x), ValueError)") == ("f(x)", "ValueError")
    assert parse_raises("f(x) == 1") is None


def test_raises_claim_verdicts():
    results = check_conjectures(gated_sqrt, [
        claim("for x in [-10, -1], raises(f(x), ValueError)"),
        claim("for x in [-10, -1], raises(f(x), KeyError)"),
        claim("for x in [1, 10], raises(f(x))"),
    ])
    assert [r.verdict for r in results] == ["proven", "falsified", "falsified"]
    # best-route falsifications may come back symbolic (sketch) or
    # empirical (counterexample); the reason is carried either way
    def reason(r):
        return (r.counterexample or "") + (r.sketch or "")
    assert "ValueError" in reason(results[1])
    assert ("instead of raising" in reason(results[2])
            or "rather than raising" in reason(results[2]))


def test_funcs_binding_relates_two_implementations():
    results = check_conjectures(
        halve, [claim("f(x) == g(x)", funcs={"g": halve_twin})])
    assert results[0].verdict == "proven"   # both lift on the best route
    results = check_conjectures(
        halve, [claim("f(x) == g(x) + 1", funcs={"g": halve_twin})])
    assert results[0].verdict == "falsified"


def test_to_latex_renders_relations_and_raises():
    assert to_latex("f(x) <= 1") == r"f{\left(x \right)} \leq 1"
    assert r"\uparrow_{\mathrm{ValueError}}" in to_latex("raises(f(x), ValueError)")


def test_to_latex_renders_matrix_vocabulary():
    # the matrix vocabulary renders through sympy's matrix printing:
    # transpose as a superscript, determinant as |A|, matmul as
    # juxtaposition, trace as tr(...), from names found under a matrix op.
    assert to_latex("A.T == A") == r"A^{T} = A"
    assert to_latex("det(A @ B) == det(A) * det(B)") == \
        r"\left|{A B}\right| = \left|{A}\right| \left|{B}\right|"
    assert to_latex("(A @ B).T == B.T @ A.T") == \
        r"\left(A B\right)^{T} = B^{T} A^{T}"
    assert to_latex("x.T @ A @ x >= 0") == r"x^{T} A x \geq 0"
    # a matrix name added to its own transpose reads as one matrix
    assert to_latex("(A + B).T == A.T + B.T") == \
        r"\left(A + B\right)^{T} = A^{T} + B^{T}"


def test_to_latex_leaves_scalar_claims_untouched():
    # a claim with no matrix operator is rendered exactly as before: no
    # name is lifted to a matrix, so the scalar reading is unchanged.
    assert to_latex("f(x) == x**2") == r"f{\left(x \right)} = x^{2}"
    assert "\\neq" in to_latex("f(x) != f(y)")
    # the derivative-at-point `@` is not a matmul and must not trigger
    # matrix rendering
    assert r"\frac{d}{d x}" in to_latex("d(f(x), x) @ {x = 1} == 2")


def test_to_canonical_uses_mathema_spelling_not_sympys_own():
    x, y = sympy.symbols("x y")
    assert to_canonical(sympy.Abs(x)) == "abs(x)"
    assert to_canonical(sympy.Min(x, y)) == "min(x, y)"
    assert to_canonical(sympy.Max(x, y)) == "max(x, y)"
    assert to_canonical(sympy.ceiling(x)) == "ceil(x)"
    assert to_canonical(sympy.E) == "e"
    assert to_canonical(sympy.sqrt(x)) == "sqrt(x)"


def test_to_canonical_refuses_piecewise():
    x = sympy.Symbol("x")
    with pytest.raises(ValueError, match="Piecewise"):
        to_canonical(sympy.Piecewise((x, x > 0), (0, True)))


def test_to_canonical_refuses_an_unbound_function_not_in_funcs():
    x = sympy.Symbol("x")
    with pytest.raises(ValueError, match="'g'"):
        to_canonical(sympy.Function("g")(x))
    assert to_canonical(sympy.Function("g")(x), funcs=frozenset({"g"})) == "g(x)"


def test_render_domain_bound_covers_every_domain_shape():
    assert render_domain_bound(Interval(0.0, 1.0)) == "[0.0, 1.0]"
    assert render_domain_bound(Interval(0.0, 1.0, closed_lo=False)) == "(0.0, 1.0]"
    assert render_domain_bound((0.0, 1.0)) == "[0.0, 1.0]"
    assert render_domain_bound("Z") == "Z"
    assert render_domain_bound(frozenset({"b", "a"})) == '{"a", "b"}'


def _sample_law(name: str) -> str:
    if name in ("min", "max", "minimum", "maximum",
                "atan2", "gcd", "besselj", "bessely"):
        return f"{name}(x, y)"
    if name == "polygamma":
        # polygamma's order argument must be a nonnegative literal for
        # sympy to construct the function at all
        return "polygamma(1, x)"
    if name == "clip":
        return "clip(x, 0, 1)"
    return f"{name}(x)"


@pytest.mark.parametrize("name,target", list(_SYMPY_FUNCS.items()))
def test_to_canonical_round_trips_every_known_math_function(name, target):
    # every _SYMPY_FUNCS entry must survive a real round trip through
    # the same law-text pipeline a claim actually goes through: law
    # text -> _node_to_sympy -> to_canonical -> normalize ->
    # _node_to_sympy again -> exactly the original expression. Both
    # sides are built by parsing law text (never a hand-built sympy
    # object) so their symbols carry the same assumptions
    # _node_to_sympy itself always attaches, a hand-built Symbol('x')
    # is not `==` to _node_to_sympy's own real=True 'x', even though
    # both print identically. Holds even for a target ("float"/"clip")
    # whose own printed text doesn't literally say "float"/"clip",
    # sympify(x) reduces to the bare symbol x, and clip expands to
    # nested Min/Max at parse time, but reparsing either printed form
    # still lands on the same expression, which is all this asserts.
    original = _node_to_sympy(ast.parse(normalize(_sample_law(name)), mode="eval"))
    text = to_canonical(original)
    reparsed = _node_to_sympy(ast.parse(normalize(text), mode="eval"))
    assert reparsed == original


@pytest.mark.parametrize("law", [
    "abs(x) + max(x, y) - min(x, y)*sqrt(x)",
    "sin(x) + cos(x) - exp(x)*log(x)",
    "d(f(x), x)",
    "lim(f(x), x, 0)",
    "integrate(f(x), x, 0, 1)",
    "Sum(x, x, 0, 5)",
    "Prod(x, x, 0, 5)",
])
def test_to_canonical_round_trips_representative_law_text(law):
    first = _node_to_sympy(ast.parse(normalize(law), mode="eval"))
    text = to_canonical(first)
    second = _node_to_sympy(ast.parse(normalize(text), mode="eval"))
    assert first == second


def double(n: float) -> float:
    return 2 * n


def pick(x: float) -> float:
    return x


def test_set_membership_domain_parsing():
    # a bare named-set spelling (R/Z/N) is a deliberate, stated type
    # choice; same as an explicit ⊂ R/Z/N would be, so it always
    # produces a real Domain entry (rather than the old bare string, or
    # for R, no entry at all), with `explicit_type=True`, but stating
    # a type never excludes missing by default. See grammar.py's
    # parse_binding().
    dom, law = split_quantifier(normalize("for x in R, f(x) == x"))
    assert dom == {"x": Domain(base_type="R", explicit_type=True)}
    assert law == "f(x) == x"
    dom, law = split_quantifier(normalize("for n in Z, f(n) >= 0"))
    assert dom == {"n": Domain(base_type="Z", explicit_type=True)}
    assert law == "f(n) >= 0"
    dom, law = split_quantifier(normalize("for n in N, f(n) >= 0"))
    assert dom == {"n": Domain(base_type="N", explicit_type=True)}
    assert law == "f(n) >= 0"
    dom, law = split_quantifier(normalize("for x in {1, 2, 3}, f(x) == x"))
    assert dom == {"x": frozenset({1.0, 2.0, 3.0})} and law == "f(x) == x"


def test_set_membership_domain_mixes_with_interval_bindings():
    dom, _ = split_quantifier(
        normalize("for x in {0, 1}, y in [0, 1], f(x, y) >= 0"))
    assert dom == {"x": frozenset({0.0, 1.0}), "y": (0.0, 1.0)}


def test_integer_domain_probe_route_samples_negative_integers():
    results = check_conjectures(
        double, [claim("for n in Z, f(n) == 2 * n", route="probe")])
    assert results[0].verdict == "holds"


def test_natural_domain_derive_route_uses_integer_assumption():
    results = check_conjectures(
        double, [claim("for n in N, f(n) >= 0", route="derive")])
    assert results[0].verdict == "proven"


def test_discrete_set_domain_probe_route():
    results = check_conjectures(
        pick, [claim("for x in {1, 2, 3}, f(x) == x", route="probe")])
    assert results[0].verdict == "holds"


def test_boolean_literal_set_domain_parses_to_real_bools():
    # `True`/`False` must resolve to actual Python bools, not strings
    # ("True" == "true") or floats (bool is an int subclass, so a naive
    # _bound() parse would silently succeed with the wrong type)
    dom, law = split_quantifier(normalize("for flag in {True}, f(flag) == flag"))
    assert dom == {"flag": frozenset({True})} and law == "f(flag) == flag"
    value = next(iter(dom["flag"]))
    assert value is True and not isinstance(value, str)

    dom, _ = split_quantifier(normalize("for flag in {False}, f(flag) >= 0"))
    assert dom == {"flag": frozenset({False})}


def test_implies_spellings_normalize_to_one_canonical_form():
    # Symbol normalization only; what => means (mathema.data's band
    # mapping) is not core's concern; split_relation() doesn't recognize
    # it as a relation.
    assert normalize("psi(a, b) --> quality") == "psi(a, b) => quality"
    assert normalize("psi(a, b) \\implies quality") == "psi(a, b) => quality"
    assert normalize("psi(a, b) ⟹ quality") == "psi(a, b) => quality"
    assert normalize("psi(a, b) => quality") == "psi(a, b) => quality"


def test_abs_norm_floor_ceil_bars():
    assert normalize("|x| < 1") == "abs(x) < 1"
    assert normalize("|x| + |y| <= 1") == "abs(x) + abs(y) <= 1"
    assert normalize("|f(x)| < 1") == "abs(f(x)) < 1"
    assert normalize("||x|| < 1") == "norm(x) < 1"
    assert normalize("||f(x)|| < 1") == "norm(f(x)) < 1"
    assert normalize("⌊x⌋ <= x") == "floor(x) <= x"
    assert normalize("⌈x⌉ >= x") == "ceil(x) >= x"


def test_bar_content_restricted_to_single_token():
    # a composite expression inside bars is not accepted; it has to go
    # through `let` first (see below). normalize leaves the literal bars,
    # and claim() rejects the residual bar with an actionable message
    # rather than letting it reach rendering as invalid Python.
    assert "|" in normalize("|a + b| < 1")
    from mathema.conjecture import InvalidConjecture
    with pytest.raises(InvalidConjecture, match="wraps a single term"):
        claim("|a + b| < 1")
    with pytest.raises(InvalidConjecture, match="wraps a single term"):
        claim("|A @ B| == |A| * |B|")
    # a single-token bar still folds and is accepted
    assert claim("|x| < 1").lhs == "abs(x)"


def test_let_single_and_comma_chained_bindings():
    assert normalize("let y = a + b in |y| < 1") == "abs((a + b)) < 1"
    assert (normalize("let y = a - b, z = c + d in |y| <= |z|")
           == "abs((a - b)) <= abs((c + d))")
    assert (normalize("let a = 1 in let b = a + 1 in b >= 0")
           == "((1) + 1) >= 0")


def test_not_equal_relation():
    assert normalize("f(x) != g(x)") == "f(x) != g(x)"
    assert normalize("f(x) ≠ g(x)") == "f(x) != g(x)"
    assert normalize("f(x) \\neq g(x)") == "f(x) != g(x)"
    assert split_relation(normalize("f(x) != g(x)")) == ("f(x)", "!=", "g(x)")
    assert "\\neq" in to_latex("f(x) != f(y)")


def test_approx_equal_is_its_own_relation_not_collapsed_into_equality():
    # ≈/\approx normalize to a distinct `~=` token (not a bare `=`) so
    # to_latex() can still render \approx, but it evaluates exactly
    # like a toleranced == (see conjecture.py/symbolic.py).
    assert normalize("f(x) ≈ g(x)") == "f(x) ~= g(x)"
    assert normalize("f(x) \\approx g(x)") == "f(x) ~= g(x)"
    assert split_relation(normalize("f(x) ≈ g(x)")) == ("f(x)", "~=", "g(x)")
    assert "approx" in to_latex("f(x) ≈ f(y)")


def test_infinity_alias():
    assert normalize("x < ∞") == "x < oo"
    assert normalize("x < \\infty") == "x < oo"


def test_lim_arrow_sugar():
    assert (normalize("lim(f(x), x -> 0) == 0")
           == normalize("lim(f(x), x, 0) == 0"))
    assert (normalize("lim(f(x), x → 0) == 0")
           == normalize("lim(f(x), x, 0) == 0"))
    assert normalize("\\lim(f(x), x, 0) == 0") == "lim(f(x), x, 0) == 0"


def test_partial_call_alias_for_d():
    assert normalize("∂(f(t, x), t) == 0") == "d(f(t, x), t) == 0"
    assert normalize("\\partial(f(t, x), t) == 0") == "d(f(t, x), t) == 0"


def test_sum_prod_subscript_superscript_sugar():
    assert (normalize("Sum(f(i))_{i=0}^n >= 0")
           == "Sum(f(i), i, 0, n) >= 0")
    assert (normalize("Sum(f(i))_{i=0}^{n+1} >= 0")
           == "Sum(f(i), i, 0, n+1) >= 0")
    assert (normalize("Prod(f(i))_{i=1}^n > 0")
           == "Prod(f(i), i, 1, n) > 0")
    # nested parens inside the summand must not confuse the paren-depth scan
    assert (normalize("Sum(f(i) + g(i))_{i=0}^n >= 0")
           == "Sum(f(i) + g(i), i, 0, n) >= 0")
    # the already-expanded 4-argument form is untouched
    assert (normalize("Sum(f(i), i, 0, n) >= 0")
           == "Sum(f(i), i, 0, n) >= 0")


def test_d_evaluation_at_sugar():
    assert (normalize("d(f(v0,theta,g), theta)@{theta=pi/4} == 0")
           == "d(f(v0,theta,g), theta, __at__, theta, pi/4) == 0")
    # the word "at" is a synonym for "@", with optional whitespace
    assert (normalize("d(f(v0,theta,g), theta) at {theta=pi/4} == 0")
           == "d(f(v0,theta,g), theta, __at__, theta, pi/4) == 0")
    assert (normalize("d(f(v0,theta,g), theta)  at  {theta=pi/4} == 0")
           == "d(f(v0,theta,g), theta, __at__, theta, pi/4) == 0")
    # multiple (var, value) pairs
    assert (normalize("d(f(x,y), x)@{x=1, y=2} == 5")
           == "d(f(x,y), x, __at__, x, 1, y, 2) == 5")
    # the ∂ alias is resolved before the evaluation-bar sugar runs, so
    # it's recognized the same as the literal `d(` spelling
    assert (normalize("∂(f(t, x), t)@{t=0} == 0")
           == "d(f(t, x), t, __at__, t, 0) == 0")
    # nested parens inside the differentiated expression don't confuse
    # the paren-depth scan
    assert (normalize("d(f(x) + g(x), x)@{x=0} == 0")
           == "d(f(x) + g(x), x, __at__, x, 0) == 0")
    # no evaluation marker; the plain differentiation form is untouched
    assert normalize("d(f(x), x) >= 0") == "d(f(x), x) >= 0"
    # a |_{...} bar suffix is not an evaluation marker for d(...)
    assert (normalize("d(f(x,y), x)|_{x=1, y=2} == 5")
           == "d(f(x,y), x)|_{x=1, y=2} == 5")




def test_integrate_evaluation_bar_sugar():
    assert (normalize("integrate(f(x, mu, sigma), x)|_{-oo}^{oo} == 1")
           == "integrate(f(x, mu, sigma), x, -oo, oo) == 1")
    # bare-token bounds, no braces needed
    assert (normalize("integrate(f(x), x)|_0^1 == 1")
           == "integrate(f(x), x, 0, 1) == 1")
    # the already-expanded 4-argument form is untouched
    assert (normalize("integrate(f(x), x, 0, 1) == 1")
           == "integrate(f(x), x, 0, 1) == 1")


def test_normalize_is_idempotent_on_new_forms():
    for text in ("|x| + |y| <= 1", "||f(x)|| < 1", "⌊x⌋ <= ⌈x⌉",
                "let y = a + b in |y| < 1", "f(x) ≈ g(x)",
                "Sum(f(i))_{i=0}^n >= 0",
                "d(f(v0,theta,g), theta)@{theta=pi/4} == 0",
                "d(f(x,y), x, y) == 0", "d(f(x), x, x, x)@{x=0} == 0",
                "integrate(f(x, mu, sigma), x)|_{-oo}^{oo} == 1",
                "f'(x) == 2*x", "f''(x) == 2", "d(f(x)) == 2*x",
                "integral f(x)|_0^1 == 1/2",
                "integral f(x,y) dx|_0^1 dy|_0^2 == 1",
                "lim f(x), x -> a >= 0", "lim f(x) as x -> a >= 0"):
        once = normalize(text)
        assert normalize(once) == once


def test_foreign_grammar_claim_is_skipped_and_tagged_not_conflated():
    # A claim declared for a different grammar (mathema.data's, mixed
    # into the same key/file) isn't a genuine skip; it must be tagged
    # in meta so a caller sweeping many claims (cli.py's cmd_verify) can
    # tell "not this grammar" apart from an actual unverifiable claim.
    cj = claim("a + b >= 0", route="observe", grammar="mathema-data")
    results = check_conjectures(halve, [cj])
    assert results[0].verdict == "skipped"
    assert results[0].meta.get("mathema.foreign_grammar") == "mathema-data"


def test_native_grammar_claim_is_not_tagged_foreign():
    results = check_conjectures(halve, [claim("f(x) == x / 2")])
    assert "mathema.foreign_grammar" not in results[0].meta


def test_is_missing_recognizes_the_grammar_module_sentinel():
    # MISSING is its own object, equal to itself (unlike NaN), so the
    # self-inequality check alone never catches it; it needs its own
    # identity check.
    assert is_missing(MISSING)
    assert not is_missing(0)
    assert not is_missing(float("inf"))


def test_probe_route_sampling_a_domains_missing_piece_does_not_crash():
    # a domain that unions in {missing} (written directly, or via
    # spec.render_claim_text, which always states the resolved
    # missing-value policy explicitly) can sample the MISSING sentinel
    # itself as a probe-route candidate value; a function that returns
    # it unchanged (identity) used to crash the raw numeric comparison
    # (`TypeError: '>=' not supported between instances of
    # '_MissingType' and 'float'`) instead of treating the sample as
    # inconclusive.
    def identity(x: float) -> float:
        return x

    cj = claim("for x in [0, 1] | {missing}, f(x) >= 0")
    result = check_conjectures(identity, [cj])[0]
    assert result.verdict == "proven"   # best-route proof over the piece
