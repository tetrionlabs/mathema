# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Relations between two domains: `A subset B`, `A = B`, `A != B`,
`A not subset B`, `A disjoint B` and `A = {}`, over number domains and
languages alike. Each relation has one canonical spelling and one
fingerprint; the other accepted spellings read as the same claim. A
relation between number domains is decided exactly, a negative one
(`not subset`, `!=`) by a member executed against both domains; a
relation over a language is not decided yet."""
import pytest

from mathema import claim
from mathema.conjecture import InvalidConjecture, check_conjectures
from mathema.spec import fingerprint_text, render_claim_text


def _f(x):
    return x


def _verdict(text):
    (row,) = check_conjectures(_f, [claim(text)])
    return row


@pytest.mark.parametrize("text,ascii_text,unicode_text", [
    ("[0, 1] subset [0, 2]", "[0.0, 1.0] subset [0.0, 2.0]", "[0.0, 1.0] ⊆ [0.0, 2.0]"),
    ("[0, 1] ⊆ R", "[0.0, 1.0] subset R", "[0.0, 1.0] ⊆ ℝ"),
    ("R supset Z", "Z subset R", "ℤ ⊆ ℝ"),
    ("R ⊇ Z", "Z subset R", "ℤ ⊆ ℝ"),
    ("{1, 2} == {2, 1}", "{1, 2} = {1, 2}", "{1, 2} = {1, 2}"),
    ("{1, 2} = {1, 2}", "{1, 2} = {1, 2}", "{1, 2} = {1, 2}"),
    ("[0, 1] : real != [0, 2] : real", "[0.0, 1.0] : real != [0.0, 2.0] : real",
     "[0.0, 1.0] : real ≠ [0.0, 2.0] : real"),
    ("[0, 1] : real ≠ [0, 2]", "[0.0, 1.0] : real != [0.0, 2.0] : real",
     "[0.0, 1.0] : real ≠ [0.0, 2.0] : real"),
    ("[0, 1) == [0, 1]", "[0.0, 1.0) : real = [0.0, 1.0] : real",
     "[0.0, 1.0) : real = [0.0, 1.0] : real"),
    ("Z != R", "Z != R", "ℤ ≠ ℝ"),
    ("N == Z", "N = Z", "ℕ = ℤ"),
    ("{1, 2} == [1, 2]", "{1, 2} = [1.0, 2.0] : real", "{1, 2} = [1.0, 2.0] : real"),
    ("[0, 2] not subset [0, 1]", "[0.0, 2.0] not subset [0.0, 1.0]",
     "[0.0, 2.0] ⊈ [0.0, 1.0]"),
    ("[0, 2] ⊈ [0, 1]", "[0.0, 2.0] not subset [0.0, 1.0]", "[0.0, 2.0] ⊈ [0.0, 1.0]"),
    ("not ([0, 2] subset [0, 1])", "[0.0, 2.0] not subset [0.0, 1.0]",
     "[0.0, 2.0] ⊈ [0.0, 1.0]"),
    ("[0, 1] disjoint [2, 3]", "[0.0, 1.0] disjoint [2.0, 3.0]",
     "[0.0, 1.0] disjoint [2.0, 3.0]"),
    ("[1, 0] : real == {}", "[1.0, 0.0] : real = {}", "[1.0, 0.0] : real = {}"),
    ("[1, 0] : real = ∅", "[1.0, 0.0] : real = {}", "[1.0, 0.0] : real = {}"),
    ("[0, 1] ⊊ [0, 2]", "[0.0, 1.0] subset [0.0, 2.0] and [0.0, 1.0] : real != [0.0, 2.0] : real",
     "[0.0, 1.0] ⊆ [0.0, 2.0] and [0.0, 1.0] : real ≠ [0.0, 2.0] : real"),
    ("Z ⊊ R", "Z subset R and Z != R", "ℤ ⊆ ℝ and ℤ ≠ ℝ"),
    ("Z subset R and Z != R", "Z subset R and Z != R", "ℤ ⊆ ℝ and ℤ ≠ ℝ"),
    ("[0, 10] : int subset Z", "[0, 10] : int subset Z", "[0, 10] : int ⊆ ℤ"),
    ("[0, 1] | {5} subset R \\ {7}", "[0.0, 1.0] | {5} subset R \\ {7}",
     "[0.0, 1.0] ∪ {5} ⊆ ℝ \\ {7}"),
    ("L[ascii] subset L[unicode]", "L[ascii] subset L[unicode]", "L[ascii] ⊆ L[unicode]"),
    ("L[ascii] ⊆ L[unicode]", "L[ascii] subset L[unicode]", "L[ascii] ⊆ L[unicode]"),
    ("L[ascii, len <= 8] not subset L[digit]", "L[ascii, len <= 8] not subset L[digit]",
     "L[ascii, len <= 8] ⊈ L[digit]"),
    ("L[ascii] disjoint L[digit]", "L[ascii] disjoint L[digit]", "L[ascii] disjoint L[digit]"),
    ("L[ascii] == L[ascii]", "L[ascii] = L[ascii]", "L[ascii] = L[ascii]"),
    ("L[ascii] ⊊ L[unicode]", "L[ascii] subset L[unicode] and L[ascii] != L[unicode]",
     "L[ascii] ⊆ L[unicode] and L[ascii] ≠ L[unicode]"),
])
def test_every_spelling_renders_as_the_one_canonical_text(text, ascii_text, unicode_text):
    cj = claim(text)
    assert render_claim_text(cj, unicode=False) == ascii_text
    assert render_claim_text(cj, unicode=True) == unicode_text
    assert fingerprint_text(cj) == ascii_text
    for rendered in (ascii_text, unicode_text):
        again = claim(rendered)
        assert render_claim_text(again, unicode=False) == ascii_text
        assert fingerprint_text(again) == ascii_text


def test_equal_sets_spelled_differently_are_different_claims():
    assert fingerprint_text(claim("[0, 2] | [1, 3] subset R")) != \
        fingerprint_text(claim("[0, 3] subset R"))


def test_a_relation_between_domains_is_its_own_kind_of_claim():
    cj = claim("[0, 1] subset [0, 2]")
    assert cj.relation == "domains"
    assert (cj.lhs, cj.rhs) == ("[0.0, 1.0]", "subset [0.0, 2.0]")
    assert not cj.domain


def test_the_proper_subset_glyph_is_refused_with_both_readings():
    with pytest.raises(InvalidConjecture) as raised:
        claim("L[a] ⊂ L[b]")
    assert str(raised.value) == (
        "`⊂` reads two ways: write `L[a] subset L[b]` for every member of "
        "L[a] is in L[b], equality included, or `L[a] subset L[b] and "
        "L[a] != L[b]` for a proper subset")


@pytest.mark.parametrize("text,kinds", [
    ("[0, 1] subset L[ascii]", "`[0.0, 1.0]` is a set of numbers and `L[ascii]` is a language"),
    ("L[ascii] disjoint Z", "`L[ascii]` is a language and `Z` is a set of numbers"),
    ('{"a"} == [0, 1]', '`{"a"}` is a language and `[0.0, 1.0]` is a set of numbers'),
])
def test_a_relation_across_kinds_is_refused_naming_both(text, kinds):
    with pytest.raises(InvalidConjecture) as raised:
        claim(text)
    assert str(raised.value) == (
        f"a relation between domains compares two of one kind: {kinds}")


@pytest.mark.parametrize("text", [
    "[0, 1] subset [0, 2] and [0, 2] subset [0, 3]",
    "[0, 1] subset [0, 2] and [0, 1] disjoint [5, 6]",
])
def test_the_only_conjunction_is_the_proper_subset(text):
    with pytest.raises(InvalidConjecture, match="the one conjunction of relations between "
                                                "domains is the proper subset"):
        claim(text)


def test_two_relations_in_a_row_are_refused():
    with pytest.raises(InvalidConjecture, match=r"one relation between two domains"):
        claim("[0, 5] subset Z subset R")


@pytest.mark.parametrize("text", [
    "[0, 1] | {None} subset R",
    "[0, 1]^3 subset R",
    "{1, missing} subset R",
])
def test_a_domain_stating_a_missing_value_or_a_shape_is_refused(text):
    with pytest.raises(InvalidConjecture, match="compares sets of values"):
        claim(text)


@pytest.mark.parametrize("text", [
    "for x in [0, 1], [0, 1] subset R",
    "assuming x > 0, [0, 1] subset R",
])
def test_a_relation_between_domains_takes_no_quantifier_or_premise(text):
    with pytest.raises(InvalidConjecture, match="takes no quantifier"):
        claim(text)


@pytest.mark.parametrize("text,meant", [
    ("[0, 1] == [0, 1]", "[0.0, 1.0] : real == [0.0, 1.0] : real"),
    ("(0, 1) != [0, 1]", "(0.0, 1.0) : real != [0.0, 1.0] : real"),
    ("[1, 0] == {}", "[1.0, 0.0] : real == {}"),
])
def test_two_bracket_pairs_alone_under_equality_are_refused_with_the_marked_spelling(
        text, meant):
    with pytest.raises(InvalidConjecture) as raised:
        claim(text)
    assert str(raised.value) == (
        f"`{text}` reads two ways: two lists of two numbers, or two intervals. Did you "
        f"mean the intervals, `{meant}`? A bracket pair is an interval where it carries "
        f"a type clause (`: real`, `: int`) and a list of values where the claim binds "
        f"or calls beside it")
    assert claim(meant).relation == "domains"


@pytest.mark.parametrize("text,relation,lhs,rhs", [
    ("f(x) == [0, 1]", "==", "f(x)", "[0, 1]"),
    ("[0, 1] == f(x)", "==", "[0, 1]", "f(x)"),
    ("f(x) in [0, 1]", "<=", "0", "f(x)"),
    ("[1, 2, 3] == [1, 2, 3]", "==", "[1, 2, 3]", "[1, 2, 3]"),
    ("x == Z", "==", "x", "Z"),
    ("for Z in [0, 1], R in [0, 1], Z != R", "!=", "Z", "R"),
    ("assuming Z != R, f(Z) == R", "==", "f(Z)", "R"),
    ("for x in [0, 1], x == [0, 1]", "==", "x", "[0, 1]"),
    ("let a be [0, 1], a != [0, 1]", "!=", "a", "[0, 1]"),
])
def test_a_side_that_is_a_value_keeps_the_claim_a_comparison_of_values(
        text, relation, lhs, rhs):
    cj = claim(text)
    assert (cj.relation, cj.lhs, cj.rhs) == (relation, lhs, rhs)


def test_a_premise_over_bound_set_names_is_a_premise_about_the_values():
    assert claim("assuming Z != R, f(Z) == R").assuming == "assuming Z != R"


def _two_inputs(Z, R):  # noqa: N803
    return Z


def test_a_set_name_that_is_also_a_parameter_is_refused_with_both_spellings():
    (row,) = check_conjectures(_two_inputs, [claim("Z != R")])
    assert row.verdict == "skipped:misspecified"
    assert row.note == (
        "`Z != R`: Z is a parameter of the function and also names a set. To compare "
        "the inputs, bind them, `for Z in ..., Z != R`; to relate the sets, write the "
        "glyphs, `ℤ ≠ ℝ`")
    (glyphs,) = check_conjectures(_two_inputs, [claim("ℤ ≠ ℝ")])
    assert glyphs.verdict == "proven"
    (plain,) = check_conjectures(_f, [claim("Z != R")])
    assert plain.verdict == "proven"


@pytest.mark.parametrize("text", [
    "[0, 1] subset [0, 2]",
    "[0, 1] subset R",
    "Z subset R",
    "N subset Z",
    "{1, 2} subset Z",
    "[0, 10] : int subset N",
    "(0, 1) subset [0, 1]",
    "[0, 1] | [2, 3] subset [0, 3]",
    "{1, 2} = {2, 1}",
    "[0, 1] | [1, 2] = [0, 2]",
    "[1, 0] : real = {}",
    "(0, 0) : real = {}",
    "[0, 1] disjoint (1, 2]",
    "{0.5} disjoint Z",
    "[0, 1] disjoint {}",
    "Z subset R and Z != R",
    "{} subset {}",
])
def test_a_true_relation_between_number_domains_is_proven(text):
    row = _verdict(text)
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.route == "derive"
    assert row.meta["mathema.derive_route"] == "domain_sets"


@pytest.mark.parametrize("text,witness", [
    ("[0, 2] not subset [0, 1]", "2"),
    ("R not subset Z", None),
    ("[0, 1] : real != [0, 2]", "2"),
    ("[0, 1) != [0, 1]", "1"),
    ("Z != [0, 1]", None),
    ("{1, 2} != {1, 3}", "2"),
])
def test_a_negative_relation_is_proven_by_an_executed_member(text, witness):
    row = _verdict(text)
    assert row.verdict == "proven", (row.verdict, row.note)
    executed = row.meta["mathema.domain_relation"]["witness"]
    assert executed["executed"] is True
    if witness is not None:
        assert executed["value"] == witness
    assert executed["value"] in row.sketch


@pytest.mark.parametrize("text,witness", [
    ("[0, 2] subset [0, 1]", "2"),
    ("R subset Z", None),
    ("[0, 1] : real = [0, 2]", "2"),
    ("[0, 1] disjoint [1, 2]", "1"),
    ("[0, 1] : real = {}", "1"),
    ("Z disjoint N", "0"),
    ("[0, 1] subset (0, 1]", "0"),
    ("{1, 2} subset {1}", "2"),
    ("[0, 1] subset [0, 1] and [0, 1] : real != [0, 1]", None),
    ("[0, 1] not subset [0, 2]", None),
    ("[0, 1] : real != [0, 1] : real", None),
])
def test_a_false_relation_between_number_domains_is_falsified(text, witness):
    row = _verdict(text)
    assert row.verdict == "falsified", (row.verdict, row.note)
    if witness is not None:
        assert row.meta["mathema.domain_relation"]["witness"]["value"] == witness
        assert witness in row.counterexample


@pytest.mark.parametrize("text", [
    "L[ascii] subset L[unicode]",
    "L[ascii] not subset L[digit]",
    "L[ascii] disjoint L[digit]",
    "L[ascii] = L[ascii]",
    'L[ascii] != {"a"}',
])
def test_a_relation_over_a_language_is_not_decided_yet(text):
    row = _verdict(text)
    assert row.verdict == "unknown"
    assert row.note == "a relation over a language has no solver lowering yet"


@pytest.mark.parametrize("text,verdict", [
    ('{"a", "b"} subset {"a", "b", "c"}', "proven"),
    ('{"a", "b"} disjoint {"c"}', "proven"),
    ('{"a"} != {"b"}', "proven"),
    ('{"a", "z"} subset {"a"}', "falsified"),
])
def test_two_finite_sets_of_any_values_are_decided_member_by_member(text, verdict):
    assert _verdict(text).verdict == verdict


def test_the_row_states_the_canonical_text_and_sits_beside_value_claims():
    rows = check_conjectures(_f, [claim("for x in [0, 1], f(x) == x"),
                                  claim("R supset Z")])
    assert [r.statement for r in rows][-1] == "Z subset R"
    assert len(rows) == 2
