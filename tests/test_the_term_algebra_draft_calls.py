# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The document-level calls of `mathema.regular`: `validate` names the
rule a document breaks; `member` and `matcher` read a definition over
its own alphabet, take the bound of a definition that is not exact,
remember the prepared term by the definition's hash, work within a
budget and report the work spent; `atoms` gives each atom's ranges and
a character standing for it; `shortest_member` finds a shortest member
without a solver, and finds none only when none is that short. A bare
node is still read by the private node readers, and a document
holding only its node is refused."""
import itertools

import pytest

from mathema import regular

FULL = [[0, 0x10FFFF]]
LETTERS = {"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 122]]}, "min": 1,
           "max": None}


def exact(language, alphabet=None):
    return {"kind": "regular_language", "version": 1, "alphabet": alphabet or FULL,
            "exact": True, "language": language}


def pair(at_least, at_most, alphabet=None):
    return {"kind": "regular_language", "version": 1, "alphabet": alphabet or FULL,
            "exact": False, "at_least": at_least, "at_most": at_most}


@pytest.mark.parametrize("document,said", [
    ({**exact(LETTERS), "at_most": LETTERS}, "not both"),
    (exact({"op": "chars", "ranges": [[98, 97]]}), "ends before it starts"),
    (exact({"op": "sometimes"}), "is not a regular-language operation"),
    ({**exact(LETTERS), "version": True}, "version"),
])
def test_validate_names_the_rule_a_document_breaks(document, said):
    with pytest.raises(regular.InvalidTerm, match=said):
        regular.validate(document)


def test_validate_accepts_a_well_formed_document_of_any_version():
    assert regular.validate(exact(LETTERS)) is None
    assert regular.validate({**exact(LETTERS), "version": 2}) is None


def test_member_reads_the_document_over_its_alphabet():
    not_a = exact({"op": "complement", "arg": {"op": "literal", "codes": [97]}}, [[97, 122]])
    assert regular.contains(not_a, "b") and not regular.contains(not_a, "a")
    assert not regular.contains(not_a, "!")
    assert regular._node_member(not_a["language"], "!")


def test_a_definition_that_is_not_exact_needs_its_bound():
    loose = pair(LETTERS, {"op": "literal", "codes": [97]})
    assert regular.contains(loose, "b", bound="at_least")
    assert not regular.contains(loose, "b", bound="at_most")
    assert regular.contains(loose, "a", bound="at_most")
    with pytest.raises(regular.InvalidTerm, match="at_least or at_most"):
        regular.contains(loose, "a")
    with pytest.raises(regular.InvalidTerm):
        regular.contains(exact(LETTERS), "a", bound="neither")


@pytest.mark.parametrize("document", [
    {"language": {"op": "epsilon"}},
    {**exact(LETTERS), "version": 2},
    {**exact(LETTERS), "kind": "other"},
])
def test_membership_is_refused_for_a_document_that_is_no_definition(document):
    with pytest.raises(regular.InvalidTerm):
        regular.contains(document, "a")


def test_matcher_answers_many_texts_and_reports_its_work():
    holds = regular.matcher(exact(LETTERS))
    assert holds("abc") and not holds("") and not holds("a1")
    assert holds.spent > 0 and holds.budget == regular._MATCH_STEPS


def test_the_prepared_term_is_remembered_by_the_definitions_hash():
    first = regular.matcher(exact(LETTERS))
    again = regular.matcher({**exact(LETTERS), "source": {"spelled": "another way"}})
    assert first is again
    assert regular.matcher(exact(LETTERS), budget=50) is not first


def test_a_budget_too_small_stops_with_the_work_spent():
    holds = regular.matcher(exact({"op": "concat", "args": [LETTERS, LETTERS, LETTERS]}),
                            budget=3)
    with pytest.raises(regular.MatchBudget) as stopped:
        holds("abcdefghij")
    assert stopped.value.budget == 3 and stopped.value.spent > 3
    with pytest.raises(regular.MatchBudget):
        regular.contains(exact(LETTERS), "abcdef", budget=0)


def test_the_private_node_readers_read_a_bare_node():
    assert regular._node_member(LETTERS, "ab")
    assert regular._node_matcher(LETTERS)("ab")
    assert not regular._node_matcher(LETTERS)("")


def test_atoms_give_each_atoms_ranges_and_a_character_of_it():
    nodes = [{"op": "chars", "ranges": [[97, 122]]}, {"op": "literal", "codes": [98]}]
    found = regular.atoms(nodes, [[0, 127]])
    assert sorted(found, key=lambda a: a[0]) == sorted(found, key=lambda a: a[0])
    covered = sorted(c for ranges, _ in found for lo, hi in ranges for c in range(lo, hi + 1))
    assert covered == list(range(128))
    for ranges, shown in found:
        assert any(lo <= ord(shown) <= hi for lo, hi in ranges)
    by_shown = {shown: ranges for ranges, shown in found}
    assert by_shown["b"] == [[98, 98]]
    assert [[97, 97], [99, 122]] in by_shown.values()
    assert len(found) == 3


@pytest.mark.parametrize("node,shortest", [
    (LETTERS, 1),
    ({"op": "concat", "args": [{"op": "literal", "codes": [120, 121]}, LETTERS]}, 3),
    ({"op": "epsilon"}, 0),
    ({"op": "repeat", "arg": {"op": "chars", "ranges": [[48, 57]]}, "min": 5, "max": 5}, 5),
])
def test_shortest_member_is_a_shortest_member(node, shortest):
    found = regular.shortest_member(exact(node))
    assert found is not None and len(found) == shortest
    assert regular.contains(exact(node), found)


def test_shortest_member_is_none_only_when_no_member_is_that_short():
    nothing = exact({"op": "inter", "args": [LETTERS, {"op": "chars", "ranges": [[48, 57]]}]})
    assert regular.shortest_member(nothing) is None
    long = exact({"op": "repeat", "arg": {"op": "literal", "codes": [97]}, "min": 13,
                  "max": None})
    assert regular.shortest_member(long) is None
    assert regular.shortest_member(long, limit=13) == "a" * 13


def test_shortest_member_reads_the_alphabet_and_the_bound():
    outside = exact({"op": "complement", "arg": {"op": "epsilon"}}, [[100, 100]])
    assert regular.shortest_member(outside) == "d"
    loose = pair(LETTERS, {"op": "literal", "codes": [122, 122]})
    assert regular.shortest_member(loose, bound="at_most") == "zz"
    assert len(regular.shortest_member(loose, bound="at_least")) == 1


def test_shortest_member_agrees_with_enumeration_on_the_matcher():
    nodes = [
        {"op": "inter", "args": [LETTERS, {"op": "complement", "arg": {"op": "literal",
                                                                         "codes": [97]}}]},
        {"op": "concat", "args": [{"op": "chars", "ranges": [[97, 98]]},
                                  {"op": "complement", "arg": LETTERS}]},
        {"op": "union", "args": [{"op": "literal", "codes": [99, 99, 99]},
                                 {"op": "literal", "codes": [98, 98]}]},
    ]
    for node in nodes:
        document = exact(node, [[97, 99], [48, 48]])
        enumerated = next((len(t) for n in range(5)
                           for t in map("".join, itertools.product("abc0", repeat=n))
                           if regular.contains(document, t)), None)
        found = regular.shortest_member(document, limit=4)
        assert (None if found is None else len(found)) == enumerated, node
