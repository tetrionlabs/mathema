# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Non-positional claim-section parsing: `let`/`for` may appear in
either relative order (a
retry loop tries each on whatever's left after the other last ran,
with no change to either function's own entry condition), and two new
stub sections, `assuming <...>,` and a trailing `=> <...>` outcome
marker, are recognized and captured verbatim, with no adjudication
semantics yet. Also covers the backtick-escaped display-symbol alias
(`` let `<token>` = <name> ``) both directions: parsing it as input,
and spec.render_claim_text's own auto-backtick-wrapping when a
(currently only synthetic, pre-mathema-symbology) rename symbol isn't
`.isidentifier()`-safe."""
from mathema.conjecture import claim


def identity(x: float) -> float:
    return x


def test_for_before_let_matches_lets_before_for():
    cj_let_first = claim("let m = m1, for m1 in [0.1,1000], x1 in [-100,100], f(m,x1) >= 0")
    cj_for_first = claim("for m1 in [0.1,1000], x1 in [-100,100], let m = m1, f(m,x1) >= 0")
    assert set(cj_let_first.domain) == set(cj_for_first.domain)
    assert cj_let_first.lhs == cj_for_first.lhs
    assert cj_let_first.relation == cj_for_first.relation


def test_for_before_let_with_backslash_greek_alias():
    cj = claim(r"for alpha in [0,10], let \alpha = alpha, f(\alpha) >= 0")
    assert cj.domain["alpha"] == (0.0, 10.0)
    assert cj.lhs == "f((alpha))"


def test_for_before_let_be_free_variable():
    cj = claim("for x in [0,10], let c be [-1e6,1e6], f(x) + c >= 0")
    assert set(cj.domain) == {"x", "c"}
    assert cj.free_vars == frozenset({"c"})


def test_bare_trailing_equality_statement_is_never_mistaken_for_a_let_continuation():
    # "x = 0" (single "=", read as "==" per split_relation) must stay
    # the statement, not get swept up as a let-continuation just
    # because it superficially matches "name = expr" shape. Safe by
    # construction: extract_let_bindings only ever fires on text
    # literally starting with "let", never on an arbitrary later
    # "name = expr" segment with no preceding "let" to continue from.
    cj = claim("for x in [0, 10], x = 0")
    assert cj.relation == "=="
    assert cj.lhs == "x"
    assert cj.rhs == "0"


def test_deeply_nested_let_for_still_terminates_quickly():
    # a real termination guarantee, not just empirically fast: each
    # loop iteration either makes progress (consumes a segment) or
    # breaks, and substitution always wraps in parens, so no new
    # top-level comma can ever be introduced, the number of
    # iterations is bounded by the original comma count.
    import time
    text = "for " + ", ".join(f"x{i} in [0, 1]" for i in range(20))
    text += ", " + ", ".join(f"let y{i} = x{i}" for i in range(20))
    text += ", f(" + ", ".join(f"y{i}" for i in range(20)) + ") >= 0"
    start = time.monotonic()
    cj = claim(text)
    assert time.monotonic() - start < 5.0
    assert len(cj.domain) == 20


def test_assuming_clause_captured_verbatim_no_semantics():
    cj = claim("assuming spec_key:claim_name is proven and claim_name holds, "
              "for x in [0, 10], f(x) >= 0")
    assert cj.assuming == "assuming spec_key:claim_name is proven and claim_name holds"
    assert cj.domain == {"x": (0.0, 10.0)}
    assert cj.lhs == "f(x)"


def test_assuming_clause_absent_is_empty_string():
    cj = claim("f(x) >= 0")
    assert cj.assuming == ""


def test_outcome_clause_captured_verbatim_for_each_accepted_spelling():
    for marker in ("=>", "-->", r"\implies"):
        cj = claim(f"for x in [0, 10], f(x) >= 0 {marker} self.claim_name holds via derive")
        assert cj.outcome == "self.claim_name holds via derive"
        assert cj.domain == {"x": (0.0, 10.0)}
        assert cj.lhs == "f(x)"


def test_outcome_clause_absent_is_empty_string():
    cj = claim("f(x) >= 0")
    assert cj.outcome == ""


def test_outcome_marker_inside_parens_is_not_mistaken_for_the_section_marker():
    # depth-aware, the same way _split_commas is, a claim quoting an
    # arrow inside a nested call/collection never gets misread.
    cj = claim("for s in {'a=>b', 'c'}, f(s) >= 0")
    assert cj.outcome == ""


def test_assuming_and_outcome_compose_with_reordered_let_for():
    cj = claim(
        "assuming spec_key:claim_name is proven and claim_name holds and "
        "spec_key:claim_name is falsified, "
        "for x in [0, 10], let z be [0, 1], f(x/z) >= 1 => self.claim_name holds via derive")
    assert cj.assuming == ("assuming spec_key:claim_name is proven and claim_name holds and "
                          "spec_key:claim_name is falsified")
    assert cj.outcome == "self.claim_name holds via derive"
    assert set(cj.domain) == {"x", "z"}
    assert cj.lhs == "f(x/z)"


def test_raises_and_is_pole_safe_still_compose_with_for_and_let():
    # confirms the statement recognizer (parse_raises/parse_domain_
    # safety/split_relation, unchanged, already shape- not position-
    # based) keeps working identically after the let/for retry-loop
    # change; these were never positional in the first place.
    from mathema.conjecture import check_conjectures

    cj1 = claim("for x in [0, 100], is_pole_safe(x)", route="derive")
    assert cj1.domain == {"x": (0.0, 100.0)}
    cj2 = claim("for x in [0, 100], raises(f(x), ValueError)")
    assert cj2.domain == {"x": (0.0, 100.0)}
    cj3 = claim("let y = x, for y in [0, 100], is_pole_safe(y)", route="derive")
    assert cj3.domain == {"x": (0.0, 100.0)}
    result = check_conjectures(identity, [claim("for x in [0, 100], f(x) >= 0")])[0]
    assert result.verdict == "proven"   # default best route: it lifts


def test_backtick_alias_substitutes_and_reparses_to_the_real_name():
    cj = claim("let `σ1` = sigma1, for `σ1` in [0, 100], f(`σ1`) >= 0")
    assert cj.domain == {"sigma1": (0.0, 100.0)}
    assert cj.lhs == "f((sigma1))"


def test_backtick_alias_token_need_not_be_a_valid_identifier():
    # the whole point: a token with characters .isidentifier() would
    # reject (a literal "%", a true Unicode digit-subscript) is fine,
    # since it's replaced away by literal string match, never fed to
    # ast.parse as a bare token.
    cj = claim("let `%ΔEBIT` = pct_change_ebit, for `%ΔEBIT` in [-1, 1], "
              "f(`%ΔEBIT`) >= 0")
    assert cj.domain == {"pct_change_ebit": (-1.0, 1.0)}
    assert cj.lhs == "f((pct_change_ebit))"


def test_alias_used_as_a_for_binding_name_before_its_own_definition_raises():
    # a real hazard non-positional let/for ordering makes newly
    # reachable: "for m in [...], let m = m1, ..." would silently bind
    # the declared domain to the alias name "m" instead of the real
    # parameter "m1" it resolves to (the for-clause is already
    # committed by the time the later let-clause reveals "m" is an
    # alias), caught and rejected rather than left to silently
    # produce a domain key that can never match a real parameter.
    # Backtick and bare-word aliases hit this the same way; the
    # backtick case surfaces as split_quantifier's own generic parse
    # error first, since a backtick token was never a recognized bare
    # binding-name shape in the first place.
    import pytest
    from mathema.conjecture import ConflictingDomainBinding, InvalidConjecture

    with pytest.raises(ConflictingDomainBinding):
        claim("for m in [0.1, 1000], let m = m1, f(m) >= 0")
    with pytest.raises(InvalidConjecture):
        claim("for `σ1` in [0, 100], let `σ1` = sigma1, f(`σ1`) >= 0")


def test_render_claim_text_auto_backtick_wraps_an_unsafe_rename_symbol(monkeypatch):
    # nothing in today's built-in auto-let logic ever produces an
    # unsafe symbol (Greek letters and the positional pool are both
    # always plain-identifier-safe by construction); this simulates
    # what a future mathema-symbology-supplied symbol would need,
    # confirming spec.render_claim_text's own backtick-wrapping (not
    # grammar.py's input-side parsing, already covered above) actually
    # fires and the result still reparses correctly.
    from mathema.grammar import domain_contains
    import mathema.grammar as grammar_module
    from mathema.spec import render_claim_text

    real_fn = grammar_module.greek_symbol_for_name

    def fake(name: str):
        if name == "sigma1":
            return "σ₁"   # a real Unicode digit-subscript, NOT .isidentifier()
        return real_fn(name)

    monkeypatch.setattr(grammar_module, "greek_symbol_for_name", fake)
    cj = claim("for sigma1 in [0, 100], f(sigma1) >= 0")
    rendered = render_claim_text(cj, unicode=True)
    assert "let `σ₁` = sigma1" in rendered
    assert "`σ₁` ∈" in rendered and "f(`σ₁`)" in rendered
    reparsed = claim(rendered)
    assert reparsed.lhs == "f((sigma1))"
    for value in (0.0, 50.0, 100.0, 100.5, float("nan")):
        assert domain_contains(value, reparsed.domain["sigma1"]) == \
               domain_contains(value, cj.domain["sigma1"])


def test_render_claim_text_backtick_wraps_an_identifier_safe_but_nfkc_unstable_symbol(monkeypatch):
    # "Mₛ" (a letter-category Unicode subscript) satisfies .isidentifier()
    #, so a naive safety check would classify it "safe" and substitute
    # it directly into law text before render_law_expr's own ast.parse.
    # CPython normalizes every identifier to NFKC at parse time (PEP
    # 3131), silently flattening "Mₛ" to "Ms" inside that round trip;
    # the law would come back out reading "Ms" while the let/domain
    # clauses (plain f-string text, never touching ast.parse) still read
    # "Mₛ", the same symbol spelled two different ways in one rendered
    # line, reparsing into a claim that lost track of "money_supply"
    # entirely with no error raised anywhere. _is_safe_rename_symbol's
    # extra NFKC-stability check is what catches this.
    import mathema.grammar as grammar_module
    from mathema.spec import render_claim_text

    real_fn = grammar_module.greek_symbol_for_name

    def fake(name: str):
        if name == "money_supply":
            return "Mₛ"
        return real_fn(name)

    monkeypatch.setattr(grammar_module, "greek_symbol_for_name", fake)
    cj = claim("for money_supply in (0, 1000], f(money_supply) >= 0")
    rendered = render_claim_text(cj, unicode=True)
    assert "let `Mₛ` = money_supply" in rendered
    assert "`Mₛ` ∈" in rendered and "f(`Mₛ`)" in rendered
    assert "Ms" not in rendered
    reparsed = claim(rendered)
    assert reparsed.lhs == "f((money_supply))"
    assert list(reparsed.domain) == ["money_supply"]
