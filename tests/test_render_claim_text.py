# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`spec.render_claim_text()` reassembles a `Conjecture` back into one
parseable string, in either of two equivalent spellings (`unicode=True`/
`False`), the fix for a claim never round-tripping through a verified
record as one string (`declare()`'s own `statement`/`domain`/`funcs`
split can't do that alone). `grammar.render_domain()`/`render_law_expr()`
are the two lower-level renderers it's built from; both also respect a
process-wide default (`grammar.get_unicode_output()`/
`set_unicode_output()`) when a caller doesn't state a preference."""
import mathema
from mathema.conjecture import claim
from mathema.grammar import (get_unicode_output, normalize, render_domain,
                             render_law_expr, set_unicode_output)
from mathema.spec import render_claim_text


def identity(x: float) -> float:
    return x


def test_render_claim_text_round_trips_a_plain_relation():
    cj = claim("f(x)^2 >= 0")
    for unicode in (True, False):
        reparsed = claim(render_claim_text(cj, unicode=unicode))
        assert (reparsed.lhs, reparsed.relation, reparsed.rhs) == \
               (cj.lhs, cj.relation, cj.rhs)


def test_render_claim_text_reassembles_for_and_let_clauses():
    from mathema.grammar import domain_contains

    cj = claim("let g = math.sqrt, for x in (0,100], g(x) >= 0")
    unicode_text = render_claim_text(cj, unicode=True)
    ascii_text = render_claim_text(cj, unicode=False)
    assert "let g = math.sqrt" in unicode_text
    assert "let g = math.sqrt" in ascii_text
    for text in (unicode_text, ascii_text):
        reparsed = claim(text)
        assert reparsed.funcs == cj.funcs
        assert set(reparsed.domain) == set(cj.domain)
        # the rendered domain now always states its resolved type and
        # missing-value policy explicitly (`:float`, `∪ {∅}`), which
        # reparses into a differently-shaped but semantically identical
        # Domain object (an explicit MISSING piece where the original
        # had none at all), compare membership behavior, the real
        # notion of "the same domain", not the raw representation.
        for name in cj.domain:
            for value in (0.0, 50.0, 100.0, 100.5, float("nan"), None):
                assert domain_contains(value, reparsed.domain[name]) == \
                       domain_contains(value, cj.domain[name])


def test_render_claim_text_defaults_to_the_global_unicode_setting():
    cj = claim("for n in [0, 100] subset Z, f(n) >= 0")
    prior = get_unicode_output()
    try:
        set_unicode_output(True)
        assert "⊂" in render_claim_text(cj)
        set_unicode_output(False)
        assert ":int" in render_claim_text(cj) and "⊂" not in render_claim_text(cj)
    finally:
        set_unicode_output(prior)   # restore what was actually set before


def test_explicit_unicode_argument_overrides_the_global_setting():
    cj = claim("for n in [0, 100] subset Z, f(n) >= 0")
    prior = get_unicode_output()
    try:
        set_unicode_output(False)
        assert "⊂" in render_claim_text(cj, unicode=True)
    finally:
        set_unicode_output(prior)


def test_get_unicode_output_reflects_set_unicode_output():
    prior = get_unicode_output()
    try:
        set_unicode_output(False)
        assert get_unicode_output() is False
        set_unicode_output(True)
        assert get_unicode_output() is True
    finally:
        set_unicode_output(prior)


def test_top_level_reexport_matches_grammar_module():
    assert mathema.set_unicode_output is set_unicode_output
    assert mathema.get_unicode_output is get_unicode_output


def test_integer_typed_bound_renders_without_decimal_points():
    text = render_domain(claim("for n in [1, 100] subset Z, f(n) >= 0").domain["n"],
                         ascii_mode=True, show_missing=False)
    assert text == "[1, 100]:int"


def test_fractional_endpoint_in_an_integer_domain_is_not_silently_truncated():
    from mathema.grammar import Domain, Interval
    dom = Domain(base_type="Z", pieces=(Interval(0.5, 100.0),))
    assert render_domain(dom, ascii_mode=True, show_missing=False) == "[0.5, 100]:int"


def test_ascii_mode_prefers_a_python_style_type_annotation_over_the_word():
    from mathema.grammar import Domain, Interval
    dom = Domain(base_type="Z", pieces=(Interval(0.0, 1.0),))
    assert render_domain(dom, ascii_mode=True, show_missing=False) == "[0, 1]:int"
    assert render_domain(dom, ascii_mode=False, show_missing=False) == "[0, 1] ⊂ ℤ"


def test_ascii_mode_keeps_the_worded_clause_for_n_with_no_python_type_name():
    from mathema.grammar import Domain, Interval
    dom = Domain(base_type="N", pieces=(Interval(0.0, 1.0),))
    assert render_domain(dom, ascii_mode=True, show_missing=False) == "[0, 1] subset N"


def test_open_integer_interval_does_not_collapse_to_a_shifted_closed_one():
    from mathema.grammar import Domain, Interval
    dom = Domain(base_type="Z", pieces=(Interval(0.0, 10.0, closed_lo=False,
                                                 closed_hi=False),))
    assert render_domain(dom, ascii_mode=True, show_missing=False) == "(0, 10):int"


def test_greek_letter_round_trips_through_all_three_input_spellings():
    # plain Greek, math-italic, and \name all collapse to the same
    # internal symbol, so ascii-mode output is identical regardless of
    # which one was typed.
    for spelling in (r"f(\alpha) + 1", "f(α) + 1", "f(𝛼) + 1"):
        text = normalize(spelling)
        assert render_law_expr(text, unicode=True) == "f(α) + 1"
        assert render_law_expr(text, unicode=False) == "f(\\alpha) + 1"


def test_nu_round_trips_and_vega_synonym_does_not_corrupt_it():
    # \vega is a pseudo-Greek addition sharing nu's own glyph (ν),
    # confirms adding it never hijacks nu's own reverse ASCII spelling.
    for spelling in (r"f(\nu) + 1", "f(ν) + 1", "f(𝜈) + 1"):
        text = normalize(spelling)
        assert render_law_expr(text, unicode=True) == "f(ν) + 1"
        assert render_law_expr(text, unicode=False) == "f(\\nu) + 1"

    vega_text = normalize(r"f(\vega) + 1")
    assert render_law_expr(vega_text, unicode=True) == "f(ν) + 1"
    # \vega and \nu both parse to the identical internal symbol ν, so
    # ASCII-mode output always reverses to \nu, never \vega.
    assert render_law_expr(vega_text, unicode=False) == "f(\\nu) + 1"


def test_real_parameter_spelling_a_greek_letter_is_auto_lettered_in_unicode():
    from mathema.conjecture import claim

    cj = claim("for theta in [0, 1], f(theta) >= 0")
    unicode_text = render_claim_text(cj, unicode=True)
    assert "let θ = theta" in unicode_text
    assert "θ ∈" in unicode_text and "f(θ)" in unicode_text
    ascii_text = render_claim_text(cj, unicode=False)
    assert "theta" in ascii_text and "θ" not in ascii_text


def test_auto_lettered_unicode_text_reparses_to_an_equivalent_claim():
    from mathema.conjecture import claim
    from mathema.grammar import domain_contains

    cj = claim("for theta in [0, 1], f(theta) >= 0")
    reparsed = claim(render_claim_text(cj, unicode=True))
    # the alias substitution wraps the real parameter in parens
    # ("f((theta))"), same known, accepted lossiness render_claim_text's
    # own docstring already documents for an alias, not a byte-for-byte
    # match; compare relation/domain, not lhs text.
    assert reparsed.relation == cj.relation
    assert set(reparsed.domain) == set(cj.domain)
    for value in (0.0, 0.5, 1.0, 1.5, float("nan")):
        assert domain_contains(value, reparsed.domain["theta"]) == \
               domain_contains(value, cj.domain["theta"])


def test_a_function_alias_or_free_variable_named_like_a_greek_letter_is_not_relettered():
    # auto-let is for real *parameters* only; a `let name = ...`
    # function binding or free variable that happens to share a Greek
    # letter's English spelling keeps its own plain name untouched.
    from mathema.conjecture import claim

    alias = claim("let alpha = math.sqrt, for x in (0, 100], alpha(x) >= 0")
    assert "let α" not in render_claim_text(alias, unicode=True)

    free_var = claim("let phi be [0, 1], for x in [0, 10], f(x) + phi >= 0")
    assert "let φ" not in render_claim_text(free_var, unicode=True)


# NOTE for anyone running the suite with a `"symbology"` capability
# provider genuinely installed (e.g. the mathema-symbology package from
# PyPI): this test and the two below it
# (test_long_real_parameter_threshold_is_configurable,
# test_two_long_real_parameters_get_distinct_symbols_starting_with_x)
# fail in that environment BY DESIGN, not as a regression, a provider
# resolves names like `velocity`/`acceleration` to its own symbols ahead
# of the positional x/y/z pool, regardless of length. That precedence is
# an accepted consequence of the capability design. The reference suite
# runs provider-free; uninstall the provider before treating a failure
# here as real.
def test_long_real_parameter_name_auto_lets_in_unicode_only():
    # the default threshold is 8 characters; "velocity" (8) stays put,
    # "acceleration" (12) doesn't. Unicode only: ASCII has no
    # single-letter convention for an ordinary variable the way f/g/h
    # already is for a function, so ASCII always keeps the plain word.
    from mathema.conjecture import claim

    short = claim("for velocity in [0, 100], f(velocity) >= 0")
    assert render_claim_text(short, unicode=True) == \
        "∀ velocity ∈ [0.0, 100.0] ⊂ ℝ ∪ {∅}, f(velocity) ≥ 0"

    long = claim("for acceleration in [0, 100], f(acceleration) >= 0")
    unicode_text = render_claim_text(long, unicode=True)
    assert "let x = acceleration" in unicode_text
    assert "x ∈" in unicode_text and "f(x)" in unicode_text
    ascii_text = render_claim_text(long, unicode=False)
    assert "acceleration" in ascii_text and "let x" not in ascii_text


def test_long_real_parameter_threshold_is_configurable():
    from mathema.conjecture import claim

    cj = claim("for velocity in [0, 100], f(velocity) >= 0")
    text = render_claim_text(cj, unicode=True, long_param_threshold=4)
    assert "let x = velocity" in text


def test_two_long_real_parameters_get_distinct_symbols_starting_with_x():
    from mathema.conjecture import claim

    cj = claim("for acceleration in [0, 10], deceleration in [0, 10], "
              "f(acceleration, deceleration) >= 0")
    text = render_claim_text(cj, unicode=True)
    assert "let x = acceleration" in text
    assert "let y = deceleration" in text


def test_long_function_alias_auto_lets_in_both_modes_using_real_numpy_functions():
    # grounded in real, importable numpy functions (a genuine mathema
    # dependency) rather than a fictional module path, so this exercises
    # the actual dotted-path/callable resolution machinery, not just
    # string substitution.
    from mathema.conjecture import claim

    cj = claim("let compute_square_root = numpy.sqrt, for x in [0, 100], "
              "compute_square_root(x) >= 0")
    unicode_text = render_claim_text(cj, unicode=True)
    ascii_text = render_claim_text(cj, unicode=False)
    assert "let g = numpy.sqrt" in unicode_text and "g(x)" in unicode_text
    assert "let g = numpy.sqrt" in ascii_text and "g(x)" in ascii_text
    # no extra "let g = compute_square_root" clause, the alias text
    # itself isn't a real identity worth preserving, unlike a real
    # parameter's actual name.
    assert "compute_square_root" not in unicode_text
    assert "compute_square_root" not in ascii_text


def test_long_function_alias_with_a_deep_dotted_path_still_resolves(tmp_path):
    # numpy.linalg.norm, a 3-segment dotted path, exercises real
    # callable resolution end to end, not just rendering: the renamed
    # claim must still actually check successfully.
    from mathema.conjecture import claim, check_conjectures

    fixture = tmp_path / "fixture_numpy_norm.py"
    fixture.write_text("def identity(x: float) -> float:\n    return x\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        from fixture_numpy_norm import identity
        cj = claim("let vector_norm_function = numpy.linalg.norm, "
                  "for x in [1, 100], vector_norm_function(x) >= 0")
        rendered = render_claim_text(cj, unicode=False)
        assert "let g = numpy.linalg.norm" in rendered
        result = check_conjectures(identity, [claim(rendered)])[0]
        assert result.verdict == "holds"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("fixture_numpy_norm", None)


def test_short_function_alias_is_never_renamed():
    from mathema.conjecture import claim

    cj = claim("let g = numpy.exp, for x in [0, 10], g(x) >= 1")
    assert render_claim_text(cj, unicode=True) == \
        "let g = numpy.exp, ∀ x ∈ [0.0, 10.0] ⊂ ℝ ∪ {∅}, g(x) ≥ 1"


def test_long_function_alias_threshold_is_configurable():
    from mathema.conjecture import claim

    cj = claim("let sqrt = numpy.sqrt, for x in [0, 100], sqrt(x) >= 0")
    text = render_claim_text(cj, unicode=False, long_func_threshold=3)
    assert "let g = numpy.sqrt" in text


def test_long_name_auto_let_is_deterministic_across_repeated_renders():
    # every pool involved is a fixed ordered string, and candidate order
    # comes from first-occurrence-in-text / dict order, never a `set`;
    # repeated renders of the same claim must always agree.
    from mathema.conjecture import claim

    cj = claim("let compute_square_root = numpy.sqrt, "
              "for acceleration in [0, 10], deceleration in [0, 10], "
              "compute_square_root(acceleration) + deceleration >= 0")
    renders = {render_claim_text(cj, unicode=True) for _ in range(20)}
    assert len(renders) == 1
    ascii_renders = {render_claim_text(cj, unicode=False) for _ in range(20)}
    assert len(ascii_renders) == 1


def test_a_real_parameter_named_pi_or_oo_suppresses_the_glyph_not_renamed():
    # grammar._node_to_sympy has no concept of a specific function's
    # real parameters, so a domain-declared "pi"/"oo" parameter and the
    # math constant become the identical sympy object by render time;
    # renaming was tried and rejected (no safe replacement symbol
    # exists, see _auto_renames), so this just suppresses the glyph and
    # prints the plain word, no "let" clause, no rename.
    from mathema.conjecture import claim

    cj = claim("for pi in [0, 100], f(pi) >= 0")
    unicode_text = render_claim_text(cj, unicode=True)
    assert unicode_text == "∀ pi ∈ [0.0, 100.0] ⊂ ℝ ∪ {∅}, f(pi) ≥ 0"
    assert "π" not in unicode_text and "let" not in unicode_text

    cj2 = claim("for oo in [0, 100], f(oo) >= 0")
    unicode_text2 = render_claim_text(cj2, unicode=True)
    assert "∞" not in unicode_text2 and "let" not in unicode_text2


def test_a_real_parameter_named_e_is_untouched_no_glyph_to_suppress():
    # "e" never gets a distinct unicode glyph at all (_print_Exp1 always
    # prints "e" in both modes), so there's nothing to disambiguate,
    # unlike pi/oo, no special handling applies here.
    from mathema.conjecture import claim

    cj = claim("for e in [0, 100], f(e) >= 0")
    assert render_claim_text(cj, unicode=True) == \
        "∀ e ∈ [0.0, 100.0] ⊂ ℝ ∪ {∅}, f(e) ≥ 0"


def test_pi_used_only_as_the_constant_is_unaffected_by_the_suppression():
    # a bare "pi" with no domain declaration at all is the constant, not
    # a parameter, nobody writes "for pi in [...]" meaning a fixed
    # constant, so an explicit domain declaration is what actually
    # signals "this is a genuine varying parameter", not mere text
    # presence. Without one, the glyph must still show normally.
    from mathema.conjecture import claim

    cj = claim("f(x) <= pi")
    assert render_claim_text(cj, unicode=True) == "f(x) ≤ π"

    cj2 = claim("integral f(x) dx|_0^pi/2 >= 0")
    assert render_claim_text(cj2, unicode=True) == "∫(f(x), x, 0, π/2) ≥ 0"


def test_real_parameters_named_sum_prod_or_d_render_safely_as_bare_names():
    # Sum/Prod/d are reserved *call-form* names (grammar.is_reserved()),
    # unlike pi/oo/e; they only get special interpretation when
    # actually called (Sum(...), d(...)), so a bare reference (no call)
    # falls straight through to an ordinary Symbol with no _MATH_ATTRS-
    # style unconditional collision. Confirms these stay safe without
    # needing the same suppress-glyph treatment pi/oo needed.
    from mathema.conjecture import claim

    for name in ("Sum", "Prod", "d"):
        cj = claim(f"for {name} in [0, 100], f({name}) >= 0")
        unicode_text = render_claim_text(cj, unicode=True)
        assert unicode_text == f"∀ {name} ∈ [0.0, 100.0] ⊂ ℝ ∪ {{∅}}, f({name}) ≥ 0"


def test_non_greek_unicode_identifier_is_left_alone_in_ascii_mode():
    text = normalize("f(参数) + 1")
    assert render_law_expr(text, unicode=False) == "f(参数) + 1"


def test_floor_ceil_always_render_as_the_plain_call_never_brackets():
    # accepted as input in either spelling, but never emitted as output:
    # a small rendered floor/ceil bracket reads too easily as a bare `|`,
    # indistinguishable from abs.
    for spelling in ("floor(f(x)) + 1", "⌊f(x)⌋ + 1"):
        text = normalize(spelling)
        assert render_law_expr(text, unicode=True) == "floor(f(x)) + 1"
        assert render_law_expr(text, unicode=False) == "floor(f(x)) + 1"
    for spelling in ("ceil(f(x)) - 1", "⌈f(x)⌉ - 1"):
        text = normalize(spelling)
        assert render_law_expr(text, unicode=True) == "ceil(f(x)) - 1"
        assert render_law_expr(text, unicode=False) == "ceil(f(x)) - 1"
