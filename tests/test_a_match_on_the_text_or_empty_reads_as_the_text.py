# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A validator matching `x or ''` is read as matching `x` when the
claim's domain for `x` is a language of texts: for every text, `x or
''` is `x`. Over a domain admitting a missing value, or one that is not
a language of texts, the route declines. Any other fallback (`x or
'a'`, `'' or x`) is not read."""
import pytest

import _text_validators as T
from mathema._validators import read_validator

pytest.importorskip("z3")


@pytest.fixture(autouse=True)
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


def test_the_reader_reads_the_text_or_empty_and_says_so():
    read = read_validator(T.is_person_or_empty)
    assert not isinstance(read, str), read
    assert read.param == "actor" and read.or_empty
    assert not read_validator(T.is_person).or_empty


@pytest.mark.parametrize("fn", [T.check_slug_or_other, T.check_slug_empty_or])
def test_another_fallback_is_not_read(fn):
    assert isinstance(read_validator(fn), str)


@pytest.mark.parametrize("fn,text,verdict", [
    (T.is_person_or_empty, "for actor in L[alnums], f(actor) == False", "proven"),
    (T.is_person_or_empty, 'for actor in L[anytext], f("p:" + actor + "z") == False',
     "proven"),
    (T.is_person_or_empty, 'for actor in L[anytext], f("p:" + actor) == False', "falsified"),
    (T.check_slug_or_empty, "for text in L[slugs], f(text) == text", "proven"),
    (T.check_slug_or_empty, "for text in L[anytext], f(text) == text", "falsified"),
])
def test_over_a_text_language_the_validator_is_decided(fn, text, verdict):
    row = T.row(fn, text)
    assert row.verdict == verdict, (row.verdict, row.note, row.sketch)
    assert T.on_smt(row)


@pytest.mark.parametrize("text", [
    "for actor in L[alnums] | {None}, f(actor) == False",
    'for actor in {"ab", "p:12"}, f(actor) == False',
    "for actor in L[records], f(actor) == False",
])
def test_over_a_missing_value_or_a_domain_of_other_values_it_declines(text):
    row = T.row(T.is_person_or_empty, text, route="best")
    assert not T.on_smt(row), (row.verdict, row.sketch)
    assert row.verdict != "proven" or not T.on_smt(row)


def test_a_domain_that_is_not_texts_is_named_in_the_sketch():
    from mathema.conjecture import _validator_proof, claim
    over = claim("for actor in L[records], f(actor) == False", route="derive")
    found = _validator_proof(over, T.is_person_or_empty, over.domain)
    assert found.status == "undecided"
    assert "or ''" in found.sketch and "not a language of texts" in found.sketch
