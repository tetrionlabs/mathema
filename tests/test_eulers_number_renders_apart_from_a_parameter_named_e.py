# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Euler's number never renders as a name the claim binds. In a claim
over a parameter (or a `let` name) called `e`, the rendered statement
writes the constant as `exp(1)`, so reading the statement or the
canonical text back gives the same claim, not one where the constant
became the parameter."""
from mathema.conjecture import check_conjectures, claim
from mathema.spec import canonical_claim_text, entry_claims, render_claim_text


def ident(e: float) -> float:
    return e


def _reread(text):
    (rebuilt,) = entry_claims({"claims": [{"name": "c", "statement": text}]})
    return rebuilt


def test_a_claim_over_e_compared_with_eulers_number_keeps_its_meaning():
    cj = claim("for e in [1, 5], f(e) == exp(1)")
    (p,) = check_conjectures(ident, [cj])
    assert p.verdict == "falsified"
    for text in (p.statement, canonical_claim_text(cj),
                 render_claim_text(cj, unicode=True)):
        assert "exp(1)" in text
        (again,) = check_conjectures(ident, [_reread(text)])
        assert again.verdict == "falsified", text


def test_the_parameter_itself_still_renders_as_e():
    cj = claim("for e in [1, 5], f(e) == e")
    text = canonical_claim_text(cj)
    assert "exp(1)" not in text
    (p,) = check_conjectures(ident, [_reread(text)])
    assert p.verdict == "proven"


def test_a_let_name_e_keeps_eulers_number_apart():
    cj = claim("let e be [1, 5], for x in [0, 1], f(x) + e >= exp(1)")
    text = canonical_claim_text(cj)
    assert "exp(1)" in text
    assert canonical_claim_text(_reread(text)) == text


def test_eulers_number_without_a_parameter_named_e_still_reads_e():
    cj = claim("for x in [1, 5], f(x) == exp(1)")
    assert canonical_claim_text(cj).endswith("f(x) = e")
