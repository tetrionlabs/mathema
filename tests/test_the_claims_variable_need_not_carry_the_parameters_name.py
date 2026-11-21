# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The variable a claim binds need not carry the validator's parameter
name: a variable passed whole (`f(h)`) or inside a literal
concatenation (`f("p:" + h + "0")`), bound by `let`, is the text the
function is called on. A claim binding a second variable, or
calling the function on more than one copy of the variable, is left to
the other routes."""
import dataclasses

import pytest

import _text_validators as T

pytest.importorskip("z3")


@pytest.fixture(autouse=True)
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


@pytest.mark.parametrize("fn,text,verdict", [
    (T.check_slug, "let h be L[slugs], f(h) == h", "proven"),
    (T.check_slug, "let h be L[anytext], f(h) == h", "falsified"),
    (T.is_person, 'let h be L[anytext], f("p:" + h + "z") == False', "proven"),
    (T.is_person, 'let h be L[anytext], f("p:" + h) == False', "falsified"),
    (T.is_person, "let h be L[alnums], f(h) == False", "proven"),
])
def test_a_differently_named_variable_is_the_text_called_on(fn, text, verdict):
    row = T.row(fn, text)
    assert row.verdict == verdict, (row.verdict, row.note, row.sketch)
    assert T.on_smt(row)


@pytest.mark.parametrize("text", [
    'let k be L[anytext], for h in L[anytext], f("p:" + h) == True',
    'let h be L[anytext], f("p:" + h + h) == True',
])
def test_a_second_variable_or_a_second_copy_is_not_decided_on_this_route(text):
    row = T.row(T.is_person, text, route="best")
    assert not T.on_smt(row), (row.verdict, row.sketch)


def test_a_prefix_outside_the_variables_language_is_decided_over_all_text():
    row = T.row(T.is_person, 'let h be L[twodigits], f("p:" + h) == True', route="best")
    assert row.verdict == "proven" and T.on_smt(row), (row.verdict, row.sketch)


def test_text_added_by_more_than_a_literal_still_declines():
    row = T.row(T.is_person, 'let h be L[twodigits], f("p:" + h.upper()) == True',
                route="best")
    assert not T.on_smt(row), (row.verdict, row.sketch)


def test_a_free_variable_other_than_the_one_called_on_still_declines():
    from mathema.conjecture import _validator_proof, claim
    plain = claim("let h be L[slugs], f(h) == h", route="derive")
    assert _validator_proof(plain, T.check_slug, plain.domain).status == "proven"
    more = dataclasses.replace(plain, free_vars=frozenset({"h", "k"}))
    assert _validator_proof(more, T.check_slug, more.domain).status == "undecided"
