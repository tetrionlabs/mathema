# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness over a language names each argument the claim reads,
`name='ǆ': 2 vs 1`, and leaves out a parameter the claim never
mentions: a defaulted parameter the claim's call does not pass has
nothing to do with the failure. The structured arguments in the
record's meta are unchanged, every parameter included."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import StringLanguage, register_language, unregister_language

TEXT = StringLanguage("some_text", char_ok=lambda c: True, pool="abǆ")


@pytest.fixture(autouse=True)
def some_text():
    register_language("some_text", TEXT)
    try:
        yield
    finally:
        unregister_language("some_text")


def ascii_slug(value, keep_case=False):
    """value with every ǆ spelled dz."""
    return value.replace("ǆ", "dz")


def pad(value, width):
    """value padded to width."""
    return value.ljust(width)


def test_the_witness_names_the_argument_and_leaves_out_the_unmentioned_one():
    (p,) = check_conjectures(ascii_slug, [claim(
        "for value in L[some_text], len(ascii_slug(value)) <= len(value)")])
    assert p.verdict == "falsified"
    assert p.counterexample == "value = 'ǆ': 2 vs 1"
    assert p.meta["mathema.counterexample_args"][0] == "ǆ"


def test_every_argument_the_claim_reads_is_named():
    (p,) = check_conjectures(pad, [claim(
        "for value in L[some_text], width in {0}, len(pad(value, width)) <= len(value) - 1")])
    assert p.verdict == "falsified"
    assert p.counterexample.startswith("value = ''") and ", width = 0: " in p.counterexample, \
        p.counterexample
