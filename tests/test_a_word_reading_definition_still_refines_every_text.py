# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A predicate word whose `refine` reads the base language's term under
the earlier key `definition` still refines the language of every text
core builds: that language states its term under `term` and, for the
release the earlier key is read, under `definition` as well. A claim
decided over all text through such a word is proven as it is through a
word reading `term`, from the same definitions with the same hashes."""
import json
import re

import pytest

from mathema import regular
from mathema.conjecture import _every_text_language, check_conjectures, claim
from mathema.languages import (PredicateWord, StringLanguage, _term_of, register_language,
                               register_predicate, unregister_language, unregister_predicate)

pytest.importorskip("z3")

ALL = [[0, 0x10FFFF]]
LOWER_NODE = {"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 122]]},
              "min": 1, "max": None}


def _exact(node):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node}


def _lower(s):
    return isinstance(s, str) and s != "" and all("a" <= c <= "z" for c in s)


def _stating(name, key):
    return StringLanguage(name, level="predicate", accepts=_lower, pool="abc",
                          generate=lambda rng: "".join(rng.choice("abc")
                                                       for _ in range(rng.randint(1, 4))),
                          schema={key: _exact(LOWER_NODE)})


#: the same language, stating its term under each key
BASES = {"definition": _stating("byold", "definition"), "term": _stating("byterm", "term")}

PAT = re.compile(r"[a-z]+")


def check(s):
    if not PAT.fullmatch(s):
        raise ValueError(s)
    return s


def _reads(callee):
    pattern = getattr(callee, "__self__", None)
    if isinstance(pattern, re.Pattern) and callee.__name__ == "fullmatch":
        return (json.dumps(pattern.pattern),)
    return None


def _refining(key):
    def refine(language, arguments, negated):
        base = language.to_json()[key]["language"]
        return StringLanguage(
            f"{language.name}, lowercase ({arguments[0]})", level="predicate",
            accepts=lambda s: language.contains(s) and PAT.fullmatch(s) is not None,
            pool="ab1", generate=lambda rng: "a",
            schema={key: _exact({"op": "inter", "args": [base, LOWER_NODE]})})
    return refine


@pytest.fixture(params=["definition", "term"])
def key(request):
    base = BASES[request.param]
    register_language(base.name, base)
    register_predicate(PredicateWord("lowercase", _refining(request.param), reads_call=_reads))
    try:
        yield request.param
    finally:
        unregister_predicate("lowercase")
        unregister_language(base.name)


def _proven(key):
    text = f'for s in L[{BASES[key].name}], raises(f(s + "1"), ValueError)'
    (row,) = check_conjectures(check, [claim(text, route="derive")])
    assert row.verdict == "proven", (key, row.verdict, row.note, row.sketch)
    return sorted(row.meta["mathema.smt"]["definitions"].values())


def test_text_added_around_the_variable_is_proven_through_either_key(key):
    assert _proven(key)


def test_both_keys_prove_from_definitions_with_the_same_hashes():
    hashes = {}
    for key, base in BASES.items():
        register_language(base.name, base)
        register_predicate(PredicateWord("lowercase", _refining(key), reads_call=_reads))
        try:
            hashes[key] = _proven(key)
        finally:
            unregister_predicate("lowercase")
            unregister_language(base.name)
    assert hashes["definition"] == hashes["term"]


def test_the_language_of_every_text_states_one_term_under_both_keys():
    every = _every_text_language()
    form = every.to_json()
    assert form["definition"] == form["term"]
    assert _term_of(every) == form["term"]
    assert regular.term_hash(form["definition"]) == regular.term_hash(form["term"])
    assert regular.term_hash(form["term"]) == regular.term_hash(_exact(
        {"op": "repeat", "arg": {"op": "chars", "ranges": ALL}, "min": 0, "max": None}))
