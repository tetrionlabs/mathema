# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Sum/Prod subscript-sugar accepts subscript/superscript in either
order, a single bare character instead of a `{...}`-wrapped group, an
upper bound that repeats the index (`i=n`) instead of a bare bound, and
a bare trailing expression (no parens around the summand at all),
`Σ`/`Π` normalize to the same `Sum`/`Prod` word forms before any of
this runs. `d`/`lim`/`integrate`/`Sum`/`Prod` (and their normalized
symbol spellings `Σ`/`Π`) are reserved for their own call form and
rejected as plain variables, consistently across rendering
(grammar.render_law_expr), the derive route (symbolic._prove.try_prove),
and the probe route (conjecture.check_conjectures)."""
from mathema.conjecture import check_conjectures, claim
from mathema.grammar import (greek_symbol_for_name, is_reserved, normalize,
                             render_law_expr, reserved_names)


def identity(x: float) -> float:
    return x


def test_leading_parenthesized_form_unchanged():
    assert normalize("Sum(f(i))_{i=0}^n >= 0") == "Sum(f(i), i, 0, n) >= 0"
    assert normalize("Sum(f(i))_{i=0}^{n+1} >= 0") == "Sum(f(i), i, 0, n+1) >= 0"


def test_four_argument_call_form_unchanged():
    assert normalize("Sum(f(i), i, 0, n) >= 0") == "Sum(f(i), i, 0, n) >= 0"


def test_trailing_bare_expression_form():
    assert normalize("Sum_{i=0}^n f(i) >= 0") == "Sum(f(i), i, 0, n)>= 0"


def test_sigma_and_pi_symbols_normalize_to_sum_and_prod():
    assert normalize("Σ_{i=0}^n f(i) >= 0") == "Sum(f(i), i, 0, n)>= 0"
    assert normalize("Π_{i=0}^n f(i) >= 0") == "Prod(f(i), i, 0, n)>= 0"


def test_superscript_before_subscript():
    assert normalize("Σ^{i=n}_{i=0} f(i) >= 0") == "Sum(f(i), i, 0, n)>= 0"


def test_repeated_index_upper_bound():
    assert normalize("Σ_{i=1}^{i=n} f(i) >= 0") == "Sum(f(i), i, 1, n)>= 0"


def test_summand_with_its_own_comma_is_not_split_early():
    assert (normalize("Sum(f(i,j))_{i=0}^n >= 0")
           == "Sum(f(i,j), i, 0, n) >= 0")
    assert (normalize("Sum_{i=0}^n f(i,j) >= 0")
           == "Sum(f(i,j), i, 0, n)>= 0")


def test_bare_index_with_no_bound_is_left_unexpanded():
    # resolving i's bound from a separately-declared domain is not
    # supported, so the expression is left as literal text rather
    # than misread as something else.
    assert normalize("Sum_i f(i) >= 0") == "Sum_i f(i) >= 0"


def test_sum_prefix_does_not_false_positive_on_unrelated_identifiers():
    assert normalize("Summary >= 0") == "Summary >= 0"
    assert normalize("Sum2 >= 0") == "Sum2 >= 0"


def test_reserved_names_lists_the_call_forms():
    names = reserved_names()
    assert {"d", "lim", "integrate", "Sum", "Prod"} <= names
    assert {"sin", "sqrt", "abs", "factorial", "gamma", "erf"} <= names
    assert is_reserved("Sum") and is_reserved("d") and is_reserved("sin")
    assert not is_reserved("x") and not is_reserved("summary")


def test_rendering_itself_does_not_reserved_check():
    # render_law_expr has no concept of a specific function's real
    # parameter names (a bare call isn't tied to any one function), so
    # it can't safely tell "d used because some function's own real
    # parameter happens to be named d" apart from a genuine
    # misspecification; that distinction needs param_names, which
    # only check_conjectures()'s own early check, _validate, and
    # _law_to_sympy actually have. Rendering stays permissive; those
    # three enforce the reservation, tested elsewhere in this file.
    for bad in ("Sum", "Prod", "d", "lim", "integrate"):
        render_law_expr(f"a1 + {bad}")   # must not raise
    assert render_law_expr(normalize("a1 + Σ")) == "Sum + a1"


def test_reserved_name_rejected_on_probe_route():
    result = check_conjectures(
        identity, [claim("f(x) == Sum", route="probe")], extensive=False)[0]
    assert result.verdict == "skipped:misspecified"
    assert "reserved" in result.note


def test_reserved_name_rejected_on_derive_route():
    # caught once, early, in check_conjectures() itself, both routes
    # get the identical verdict/note now, not each route separately
    # discovering the same mistake through its own differently-shaped
    # internal error path.
    result = check_conjectures(
        identity, [claim("f(x) == Sum", route="derive")], extensive=False)[0]
    assert result.verdict == "skipped:misspecified"
    assert "reserved" in result.note


def test_greek_letter_backslash_names_normalize_to_unicode_symbols():
    assert normalize(r"f(\alpha) + \lambda") == "f(α) + λ"
    assert normalize(r"\epsilon") == "ε"


def test_math_italic_greek_lookalikes_merge_to_the_plain_letter():
    assert normalize("f(𝛼) + 𝜎") == "f(α) + σ"
    assert normalize("f(ς)") == "f(σ)"   # final sigma -> sigma


def test_pi_constant_handling_is_unaffected_by_greek_letter_work():
    assert normalize(r"f(x) == \pi") == "f(x) == pi"
    assert normalize("f(x) == 𝜋") == "f(x) == pi"


def test_greek_symbol_for_name_matches_the_english_spelling_case_sensitively():
    assert greek_symbol_for_name("theta") == "θ"
    assert greek_symbol_for_name("Theta") == "Θ"
    assert greek_symbol_for_name("alpha") == "α"
    assert greek_symbol_for_name("THETA") is None   # wrong case, no match
    assert greek_symbol_for_name("omicron") is None  # no symbol for this word
    assert greek_symbol_for_name("x") is None


def test_alias_reused_as_a_for_binding_name_resolves_through_the_alias():
    # a key use case for let is renaming a complicated real parameter to
    # something shorter, writing the short name consistently
    # everywhere, including the for-binding's own name, should resolve
    # through the alias rather than break.
    cj = claim("let alpha = param1, for alpha in [0,10], f(alpha) >= 0",
              route="probe")
    assert list(cj.domain) == ["param1"]
    assert tuple(cj.domain["param1"]) == (0.0, 10.0)
    assert cj.lhs == "f((param1))"


def test_alias_reused_as_a_for_binding_name_works_with_unicode_membership():
    cj = claim("let alpha = param1, for alpha ∈ [0,10], f(alpha) >= 0",
              route="probe")
    assert list(cj.domain) == ["param1"]
    assert tuple(cj.domain["param1"]) == (0.0, 10.0)


def test_backslash_greek_name_as_the_let_alias_itself():
    # a real function parameter is always the plain ASCII word (Python
    # source can't easily type a literal Greek letter), so `let` is the
    # bridge between the notation a claim wants to use and the name the
    # parameter actually has; including when the notation itself is
    # spelled as a backslash command rather than the Unicode letter.
    law = r"let \alpha = alpha, for alpha in [0,10], f(\alpha) >= 0"
    cj = claim(law, route="probe")
    assert list(cj.domain) == ["alpha"]
    assert cj.lhs == "f((alpha))"


def test_backslash_greek_name_as_both_the_alias_and_its_own_for_binding():
    # combines both fixes at once: the backslash form has to resolve to
    # a real name before extract_let_bindings' own \w+ matching can see
    # it as a binding name at all, *and* that same name is then reused
    # as the for-binding's own name (not the real parameter's name),
    # which must resolve through the alias rather than break. No bare
    # "alpha" appears anywhere except as the alias's own target.
    law = r"let \alpha = alpha, for \alpha in [0,10], f(\alpha) >= 0"
    cj = claim(law, route="probe")
    assert list(cj.domain) == ["alpha"]
    assert cj.lhs == "f((alpha))"
