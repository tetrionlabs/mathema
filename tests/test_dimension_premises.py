# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A sequence is non-empty by default (`R^n` already says at least one
element), and a dimension bound beyond that is written as a premise:
`assuming n >= 5, for xs in R^n` for a vector, `assuming n >= 3` over
`R^(n,n)` for a square matrix, `assuming min(m, n) >= 3` over `R^(m,n)`
for a rectangular one. Each premise round-trips and is honoured on the
probe: the claim holds with it and falsifies without it. Two `assuming`
clauses are one premise, their conjunction."""
import pytest

from mathema.conjecture import InvalidConjecture, claim
from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON
from mathema.spec import canonical_claim_text
from tests.test_claim_text_soundness import _verdict, assert_round_trips


def first(xs: list) -> float:
    return xs[0]


def _paired(key):
    (fn,) = [fn for fn, keys in EXAMPLE_FUNCTIONS.values() if key in keys]
    return fn


def test_a_sequence_is_never_empty_by_default():
    law = "for xs in R^n, f(xs) == xs[0]"
    assert_round_trips(law, first)
    assert _verdict(first, claim(law)) == "holds"
    assert "n >= 1" not in canonical_claim_text(claim(law))


@pytest.mark.parametrize("key, without", [
    ("dim_premise_vector_bound", "for xs in R^n, f(xs) == xs[4]"),
    ("dim_premise_square_matrix", "for a in R^(n,n), f(a) == a[2][2]"),
    ("dim_premise_rectangular_matrix", "for a in R^(m,n), f(a) == a[2][2]"),
])
def test_a_dimension_premise_is_honoured_and_round_trips(key, without):
    fn = _paired(key)
    law = LEXICON[key]
    canon = assert_round_trips(law, fn)
    assert canon.startswith("assuming ")
    assert _verdict(fn, claim(law)) == "holds"
    assert _verdict(fn, claim(without)) == "falsified"


def test_the_lexicon_premises_read_as_written():
    assert LEXICON["dim_premise_vector_bound"].startswith(
        "assuming n >= 5, for xs in R^n,")
    assert LEXICON["dim_premise_square_matrix"].startswith(
        "assuming n >= 3, for a in R^(n,n),")
    assert LEXICON["dim_premise_rectangular_matrix"].startswith(
        "assuming min(m, n) >= 3, for a in R^(m,n),")


# two assuming clauses

_TWO = "assuming m >= 3, assuming n >= 3, for a in R^(m,n), f(a) == a[2][2]"


def test_two_assuming_clauses_keep_both_premises():
    fn = _paired("dim_premise_rectangular_matrix")
    canon = assert_round_trips(_TWO, fn)
    assert canon.startswith("assuming m >= 3 and n >= 3, ")
    assert canon == canonical_claim_text(claim(
        "assuming m >= 3 and n >= 3, for a in R^(m,n), f(a) == a[2][2]"))
    assert _verdict(fn, claim(_TWO)) == "holds"


def test_the_order_of_two_assuming_clauses_is_kept():
    canon = canonical_claim_text(claim(
        "assuming n >= 3, for a in R^(m,n), assuming m >= 3, f(a) == a[2][2]"))
    assert canon.startswith("assuming n >= 3 and m >= 3, ")


@pytest.mark.parametrize("law", [
    "assuming f is defined, assuming n >= 3, for a in R^(n,n), f(a) >= 0",
    "assuming base holds, assuming n >= 3, for a in R^(n,n), f(a) >= 0",
    "assuming A is symmetric, assuming n >= 3, for A in R^(n,n), f(A) >= 0",
])
def test_two_assuming_clauses_that_are_not_both_relations_are_refused(law):
    with pytest.raises(InvalidConjecture, match="one `assuming` clause"):
        claim(law)


def test_a_parenthesised_conjunction_says_how_to_write_it():
    from mathema.conjecture import check_conjectures
    fn = _paired("dim_premise_rectangular_matrix")
    (probe,) = check_conjectures(fn, [claim(
        "assuming (m >= 3 and n >= 3), for a in R^(m,n), f(a) == a[2][2]")])
    assert probe.verdict == "skipped"
    assert "not supported yet" in probe.note
    assert "assuming m >= 3 and n >= 3" in probe.note
