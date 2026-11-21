# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The witness of a falsified claim is a point the claim's premise
admits. Under `assuming f is defined` a point where the function raises
is outside the claim, so a witness shrunk inside a language never
lands on one; under a relation premise the witness satisfies the
relation. Without a premise, a raise is a witness like any other."""
import re

import pytest

import _text_validators as T

_LETTERS = re.compile(r"[a-c]+\Z")


def shout(text):
    if not _LETTERS.match(text):
        raise ValueError(text)
    return text.upper()


@pytest.fixture(autouse=True)
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


def _witness(row):
    (value,) = row.meta["mathema.counterexample_args"]
    return value


def test_under_f_is_defined_the_witness_is_a_point_where_f_returns():
    row = T.row(shout, "for text in L[anytext], assuming f is defined, f(text) == text",
                route="best")
    assert row.verdict == "falsified", (row.verdict, row.note)
    text = _witness(row)
    assert "raised" not in row.counterexample, row.counterexample
    assert shout(text) != text


def test_under_a_relation_premise_the_witness_satisfies_it():
    row = T.row(shout, "for text in L[anytext], assuming len(text) >= 2, f(text) == text",
                route="best")
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert len(_witness(row)) >= 2


def test_without_a_premise_a_raise_is_a_witness():
    row = T.row(shout, "for text in L[anytext], f(text) == text", route="best")
    assert row.verdict == "falsified", (row.verdict, row.note)
