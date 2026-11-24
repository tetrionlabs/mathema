# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A verdict that rests on a language's stated definition is given only
after the definition is checked against the language's own membership
by drawing: members drawn through the language must lie in the
definition, and strings the solver takes from the definition must be
members. A disagreement reads unknown and names the language and the
string. The row lists each definition it read as an assumption with its
status, and a validator's reading is checked the same way by running
the real function on drawn members."""
import json
import re

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.domain_relations import agreed_on_every_value as _agreed_on_every_value
from mathema.languages import (PredicateWord, StringLanguage, register_language,
                               register_predicate, unregister_language, unregister_predicate)

pytest.importorskip("z3")

ALL = [[0, 0x10FFFF]]


def _exact(node):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node}


def _star(*ranges):
    return {"op": "repeat", "arg": {"op": "chars", "ranges": [list(r) for r in ranges]},
            "min": 0, "max": None}


A_STAR = _exact(_star((97, 97)))
AB_STAR = _exact(_star((97, 98)))
ABC_STAR = _exact(_star((97, 99)))


def _over(letters, definition, name):
    """Every string over `letters`, stating `definition`."""
    return StringLanguage(
        name, level="predicate", accepts=lambda s: set(s) <= set(letters), pool=letters,
        generate=lambda rng: "".join(rng.choice(letters) for _ in range(rng.randint(0, 3))),
        schema={"term": definition})


#: accepts every string over a and b and states a*: the definition misses members
WRONG = _over("ab", A_STAR, "wrong")
#: accepts every string over a and b and states (a|b|c)*: the definition is too wide
WIDE = _over("ab", ABC_STAR, "wide")
RIGHT = _over("ab", AB_STAR, "right")
ONLY_A = _over("a", A_STAR, "onlya")

PAT = re.compile(r"a*")
OTHER = re.compile(r"b*")


def check(s):
    if not PAT.fullmatch(s):
        raise ValueError(s)
    return s


def _reads(callee):
    pattern = getattr(callee, "__self__", None)
    if isinstance(pattern, re.Pattern) and callee.__name__ == "fullmatch":
        return (json.dumps(pattern.pattern),)
    return None


def _reads_wrongly(callee):
    """Names the pattern b* whatever the function matches."""
    return (json.dumps(OTHER.pattern),) if _reads(callee) else None


def _refine(language, arguments, negated):
    pattern = re.compile(json.loads(arguments[0]))
    letter = {"a*": 97, "b*": 98}[pattern.pattern]
    base = language.to_json()["term"]["language"]
    return StringLanguage(
        f"{language.name}, spelled ({arguments[0]})", level="predicate",
        accepts=lambda s: language.contains(s) and pattern.fullmatch(s) is not None,
        pool="ab", generate=lambda rng: "",
        schema={"term": _exact({"op": "inter", "args": [base, _star((letter, letter))]})})


SPELLED = PredicateWord("spelled", _refine, reads_call=_reads)
MISREAD = PredicateWord("spelled", _refine, reads_call=_reads_wrongly)


@pytest.fixture
def served():
    for language in (WRONG, WIDE, RIGHT, ONLY_A):
        register_language(language.name, language)
    register_predicate(SPELLED)
    try:
        yield
    finally:
        for language in (WRONG, WIDE, RIGHT, ONLY_A):
            unregister_language(language.name)
        unregister_predicate("spelled")


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    return row


def test_a_definition_missing_a_member_proves_nothing(served):
    related = _row(check, 'L[wrong] disjoint {"b"}')
    assert related.verdict == "unknown", (related.verdict, related.sketch)
    assert "is a member of L[wrong] and is outside its stated definition" in related.note
    validated = _row(check, "for s in L[wrong], f(s) == s")
    assert validated.verdict != "proven", (validated.verdict, validated.sketch)
    assert "is a member of L[wrong] and is outside its stated definition" in (
        (validated.note or "") + (validated.sketch or ""))


def test_a_definition_holding_a_string_that_is_no_member_proves_nothing(served):
    row = _row(check, "L[right] subset L[wide]")
    assert row.verdict == "unknown", (row.verdict, row.sketch)
    assert "is in the stated definition of L[wide] and is not a member" in row.note


def test_a_proven_row_lists_each_definition_it_read_and_how_it_stands(served):
    row = _row(check, "L[onlya] subset L[right]")
    assert row.verdict == "proven", (row.verdict, row.note)
    assumptions = row.meta["mathema.assumptions"]
    assert set(assumptions["standard"]) == {"z3", "canonical form"}
    assert assumptions["standard"]["z3"]["version"]
    stated = {a["language"]: a for a in assumptions["definitions"]}
    assert set(stated) == {"L[onlya]", "L[right]"}
    for text, entry in stated.items():
        assert entry["statement"] == f"{text} == its stated definition"
        assert entry["status"] == "assumed"
        assert _agreed_on_every_value(entry)
        assert entry["artefact"]["members drawn"] >= 1
        assert isinstance(entry["artefact"]["seed"], int)
    assert row.sketch.endswith(
        "proven, assuming L[onlya] == its stated definition (assumed), "
        "L[right] == its stated definition (assumed)")


def test_a_validators_proof_lists_its_reading_as_an_assumption(served):
    row = _row(check, "for s in L[onlya], f(s) == s")
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    statements = [a["statement"] for a in row.meta["mathema.assumptions"]["definitions"]]
    assert 'check accepts a text exactly when it is in L[onlya, spelled ("a*")]' in statements
    assert "L[onlya] == its stated definition" in statements
    assert "proven, assuming " in row.sketch


def test_a_reading_the_function_does_not_bear_out_is_declined(served):
    unregister_predicate("spelled")
    register_predicate(MISREAD)
    # read as b*, the claim "f refuses every text of a's" would be
    # proven; the function accepts them
    row = _row(check, "for s in L[onlya, len >= 1], raises(f(s), ValueError)")
    assert row.verdict != "proven", (row.verdict, row.sketch)


def test_a_falsified_with_no_executed_string_says_what_it_assumes(served):
    row = _row(check, "L[onlya] not subset L[right]")
    assert row.verdict == "falsified", (row.verdict, row.note)
    ending = ("falsified, assuming L[onlya] == its stated definition (assumed), "
              "L[right] == its stated definition (assumed)")
    assert row.sketch.endswith(ending) and row.note.endswith(ending)
    assert len(row.meta["mathema.assumptions"]["definitions"]) == 2
    assert "mathema.rests_on_membership" not in row.meta


def test_a_falsified_by_an_executed_string_assumes_nothing(served):
    row = _row(check, "L[right] subset L[onlya]")
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert "assuming" not in (row.note or "") + (row.sketch or "")
    assert row.meta["mathema.rests_on_membership"] == ["L[onlya]", "L[right]"]


LOWER_UP_TO_SIX = _exact({"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 122]]},
                          "min": 0, "max": 6})


def _line_accepts(s):
    body = s[:-2] if s.endswith("-x") else s
    return len(body) <= 6 and set(body) <= set("abcdefghijklmnopqrstuvwxyz")


#: up to six lower-case letters, optionally followed by -x; it samples
#: letters only and states [a-z]{0,6}
LINE = StringLanguage(
    "line", level="predicate", accepts=_line_accepts, pool="abcdefghijklmnopqrstuvwxyz",
    generate=lambda rng: "".join(rng.choice("abcxyz") for _ in range(rng.randint(0, 6))),
    schema={"term": LOWER_UP_TO_SIX})


@pytest.fixture
def line():
    register_language("line", LINE)
    try:
        yield
    finally:
        unregister_language("line")


def test_a_member_the_sampler_never_draws_is_found_by_enumeration(served, line):
    row = _row(check, 'L[line] disjoint {"a-x"}')
    assert row.verdict == "unknown", (row.verdict, row.sketch)
    assert "'-x' is a member of L[line] and is outside its stated definition" in row.note
    negative = _row(check, "L[line] not subset L[right]")
    assert negative.verdict != "falsified" or "assuming" not in (negative.note or "")


def test_a_checked_definition_says_what_was_enumerated(served):
    from mathema import domain_relations
    from mathema.domain import parse_binding
    defined = domain_relations.defined_bound(parse_binding("s in L[right]")[1])
    (text, language, most, least), = defined.read
    checked = domain_relations.check_definition(text, language, most, least, defined.alphabet)
    assert checked["status"] == "assumed" and _agreed_on_every_value(checked)
    artefact = checked["artefact"]
    assert artefact["atoms"] == 2 and artefact["length bound"] >= 6
    assert artefact["strings compared"] > 9000 and artefact["members drawn"] >= 1
    again = domain_relations.check_definition(text, language, most, least, defined.alphabet)
    assert again == checked


def test_the_check_of_a_definition_asks_no_solver(served, monkeypatch):
    from mathema import domain_relations, regular
    from mathema.domain import parse_binding
    defined = domain_relations.defined_bound(parse_binding("s in L[right]")[1])
    (text, language, most, least), = defined.read

    def no_solver(*args, **kwargs):
        raise AssertionError("the check of a definition asked the solver")
    monkeypatch.setattr(regular, "find_member", no_solver)
    assert domain_relations.check_definition(
        text, language, most, least, defined.alphabet)["status"] == "assumed"


def test_a_check_that_does_not_finish_claims_no_status(served, monkeypatch):
    from mathema import domain_relations, regular
    from mathema.domain import parse_binding
    defined = domain_relations.defined_bound(parse_binding("s in L[right]")[1])
    (text, language, most, least), = defined.read
    monkeypatch.setattr(regular, "_MATCH_STEPS", 0)
    unfinished = domain_relations.check_definition(text, language, most, least,
                                                   defined.alphabet)
    assert unfinished.get("unfinished") == "the check of the definition of L[right] did not finish"
    row = _row(check, "L[onlya] subset L[right]")
    assert row.verdict == "unknown"
    assert "did not finish" in row.note


def test_a_solver_string_the_matcher_reads_otherwise_is_not_reported(served, monkeypatch):
    from mathema import regular
    monkeypatch.setattr(regular, "_places", lambda text, inside, outside: False)
    row = _row(check, "L[right] subset L[onlya]")
    assert row.verdict == "unknown", (row.verdict, row.counterexample)
