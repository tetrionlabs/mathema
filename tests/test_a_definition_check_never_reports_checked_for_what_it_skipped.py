# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The check of a language's stated definition compares the definition
with the language's own membership. A string on which `contains()`
raises is skipped, and a definition with any skipped string is not
`checked`: its status is `assumed` and the artefact names what was
skipped. The strings a claim itself writes are compared as well as
the enumerated ones, so a definition wrong only on a string the claim
names cannot stand behind a verdict about that string."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language

pytest.importorskip("z3")

ALL = [[0, 0x10FFFF]]


def _exact(node):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node}


AB_STAR = _exact({"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 98]]},
                  "min": 0, "max": None})
LOWER_UP_TO_SIX = _exact({"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 122]]},
                          "min": 0, "max": 6})


class _RaisesOnB(StringLanguage):
    """Every string of a's; `contains()` raises on any string holding a b."""

    def contains(self, value):
        if isinstance(value, str) and "b" in value:
            raise RuntimeError("cannot decide")
        return super().contains(value)


def _gen_ab(rng):
    return "".join(rng.choice("ab") for _ in range(rng.randint(0, 3)))


#: every string over a and b, stating (a|b)*: the definition is right
OVER_AB = StringLanguage("overab", level="predicate", accepts=lambda s: set(s) <= set("ab"),
                         pool="ab", generate=_gen_ab, schema={"term": AB_STAR})
#: states (a|b)* and accepts only a's, raising on every string with a b
PARTIAL = _RaisesOnB("partial", level="predicate", accepts=lambda s: set(s) <= {"a"},
                     pool="a", generate=lambda rng: "a" * rng.randint(0, 3),
                     schema={"term": AB_STAR})


def _long_tail(s):
    body = s[:-4] if s.endswith("-xyz") else s
    return len(body) <= 6 and set(body) <= set("abcdefghijklmnopqrstuvwxyz")


#: up to six lower-case letters, optionally followed by -xyz; it states
#: [a-z]{0,6}, so it is wrong only on strings longer than the guard enumerates
TAIL = StringLanguage("tail", level="predicate", accepts=_long_tail, pool="abcxyz",
                      generate=lambda rng: "".join(rng.choice("abcxyz")
                                                   for _ in range(rng.randint(0, 6))),
                      schema={"term": LOWER_UP_TO_SIX})
#: up to six lower-case letters, stating exactly that
SHORT = StringLanguage("short", level="predicate",
                       accepts=lambda s: len(s) <= 6 and set(s) <= set("abcdefghijklmnopqrstuvwxyz"),
                       pool="abcxyz",
                       generate=lambda rng: "".join(rng.choice("abcxyz")
                                                    for _ in range(rng.randint(0, 6))),
                       schema={"term": LOWER_UP_TO_SIX})


@pytest.fixture
def served():
    for language in (OVER_AB, PARTIAL, TAIL, SHORT):
        register_language(language.name, language)
    try:
        yield
    finally:
        for language in (OVER_AB, PARTIAL, TAIL, SHORT):
            unregister_language(language.name)


def _ident(s):
    return s


def _row(text):
    (row,) = check_conjectures(_ident, [claim(text, route="derive")])
    return row


def _definitions(row):
    return {a["language"]: a for a in row.meta["mathema.assumptions"]["definitions"]}


def test_a_definition_whose_membership_raised_on_a_string_is_not_checked(served):
    from mathema import domain_relations
    from mathema.domain import parse_binding
    defined = domain_relations.defined_bound(parse_binding("s in L[partial]")[1])
    (text, language, most, least), = defined.read
    result = domain_relations.check_definition(text, language, most, least, defined.alphabet)
    assert result["status"] == "assumed", result
    artefact = result["artefact"]
    assert artefact["strings skipped"] > 0
    assert artefact["strings compared"] > 0
    assert "'b'" in artefact["skipped"]
    assert len(artefact["skipped"]) <= domain_relations.GUARD_SKIPPED_SHOWN


def test_a_proof_resting_on_a_skipping_check_does_not_say_checked(served):
    row = _row("L[overab] subset L[partial]")
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    stated = _definitions(row)
    assert stated["L[partial]"]["status"] == "assumed", stated
    assert stated["L[partial]"]["corroboration"]["values skipped"] > 0, stated
    assert "L[partial] == its stated definition (assumed)" not in row.sketch, row.sketch
    assert "L[partial] == its stated definition (assumed, " in row.sketch, row.sketch
    assert stated["L[overab]"]["status"] == "assumed"
    assert stated["L[overab]"]["corroboration"]["disagreed"] == 0


def test_a_definition_with_nothing_skipped_reports_no_skips(served):
    from mathema import domain_relations
    from mathema.domain import parse_binding
    defined = domain_relations.defined_bound(parse_binding("s in L[overab]")[1])
    (text, language, most, least), = defined.read
    result = domain_relations.check_definition(text, language, most, least, defined.alphabet)
    assert result["status"] == "assumed" and result["corroboration"]["disagreed"] == 0
    assert result["artefact"]["strings skipped"] == 0
    assert result["artefact"]["skipped"] == []


@pytest.mark.parametrize("text", ['L[tail] disjoint {"a-xyz"}', '"a-xyz" not in L[tail]'])
def test_a_definition_wrong_on_the_claims_own_literal_proves_nothing(served, text):
    row = _row(text)
    assert row.verdict != "proven", (row.verdict, row.sketch)


def test_the_claims_literal_is_compared_and_named_in_the_disagreement(served):
    row = _row('L[tail] disjoint {"a-xyz"}')
    assert row.verdict == "unknown", (row.verdict, row.sketch)
    assert "'a-xyz' is a member of L[tail] and is outside its stated definition" in row.note


def test_a_right_definition_with_a_literal_still_proves(served):
    row = _row('L[short] disjoint {"a-xyz"}')
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    assert _definitions(row)["L[short]"]["status"] == "assumed"
    assert _definitions(row)["L[short]"]["corroboration"]["disagreed"] == 0


def test_the_literal_is_compared_by_the_check_itself(served):
    from mathema import domain_relations
    from mathema.domain import parse_binding
    defined = domain_relations.defined_bound(parse_binding("s in L[tail]")[1])
    (text, language, most, least), = defined.read
    plain = domain_relations.check_definition(text, language, most, least, defined.alphabet)
    assert plain["status"] == "assumed" and plain["corroboration"]["disagreed"] == 0
    with_literal = domain_relations.check_definition(text, language, most, least,
                                                     defined.alphabet, literals=("a-xyz",))
    assert with_literal["status"] == "refuted"
    assert "'a-xyz'" in with_literal["disagreement"]
