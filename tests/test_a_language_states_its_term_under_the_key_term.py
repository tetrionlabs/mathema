# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language's persisted form states its regular-language term under
the key `term`. Core reads that key; a form carrying only the earlier
key `definition` is still read, and a form carrying both is read by
`term`. The language core builds itself writes `term`."""
import pytest

from mathema import regular
from mathema.conjecture import check_conjectures, claim, language_definition_stamp
from mathema.domain import parse_binding
from mathema.domain_relations import defined_bound
from mathema.languages import StringLanguage, register_language, unregister_language
from mathema.domain_relations import agreed_on_every_value as _agreed_on_every_value

pytest.importorskip("z3")

ALL = [[0, 0x10FFFF]]


def _exact(ranges, lo=1):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": {"op": "repeat", "arg": {"op": "chars", "ranges": ranges},
                         "min": lo, "max": None}}


LOWER = _exact([[97, 122]])
DIGITS = _exact([[48, 57]])


def _lower(s):
    return isinstance(s, str) and s != "" and all("a" <= c <= "z" for c in s)


def _language(name, schema):
    return StringLanguage(name, level="predicate", accepts=_lower, pool="abc",
                          generate=lambda rng: "".join(rng.choice("abc")
                                                       for _ in range(rng.randint(1, 4))),
                          schema=schema)


LANGUAGES = {
    "byterm": _language("byterm", {"term": LOWER}),
    "byold": _language("byold", {"definition": LOWER}),
    "byboth": _language("byboth", {"term": LOWER, "definition": DIGITS}),
}


@pytest.fixture(autouse=True)
def served():
    for name, language in LANGUAGES.items():
        register_language(name, language)
    try:
        yield
    finally:
        for name in LANGUAGES:
            unregister_language(name)


@pytest.mark.parametrize("name", ["byterm", "byold", "byboth"])
def test_the_term_is_read_and_decides_a_relation(name):
    defined = defined_bound(parse_binding(f"s in L[{name}]")[1])
    assert defined is not None
    assert defined.hashes == {f"L[{name}]": regular.term_hash(LOWER)}
    (row,) = check_conjectures(lambda s: s, [claim(f"L[{name}] subset L[{name}]",
                                                   route="derive")])
    assert row.verdict == "proven", (row.verdict, row.note)
    statuses = {a["status"] for a in row.meta["mathema.assumptions"]["definitions"]}
    assert statuses == {"assumed"}
    assert all(_agreed_on_every_value(a)
               for a in row.meta["mathema.assumptions"]["definitions"])


@pytest.mark.parametrize("name", ["byterm", "byold", "byboth"])
def test_the_staleness_stamp_hashes_the_term_read(name):
    cj = claim(f"for s in L[{name}], s == s")
    assert language_definition_stamp(cj) == {f"L[{name}]": regular.term_hash(LOWER)}


def test_a_form_with_neither_key_states_no_term():
    register_language("plainform", _language("plainform", {}))
    try:
        assert defined_bound(parse_binding("s in L[plainform]")[1]) is None
    finally:
        unregister_language("plainform")


def test_the_language_core_builds_writes_term():
    from mathema.conjecture import _every_text_language
    form = _every_text_language().to_json()
    assert regular.is_definition(form["term"]) and form["definition"] == form["term"]
