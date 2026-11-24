# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's identity leaves out its pinned regions, and nothing else.

`fingerprint_text` strips each advisory `--> <region>` pin from the
premise, since the region is recomputed evidence and not part of what
the author asserted. An arrow inside a string literal is part of the
literal's value: the premise is cut only at an arrow outside every
literal, so two premises that differ inside a literal after an arrow
are two claims with two identities.
"""
import pytest

from mathema.conjecture import claim
from mathema.spec import fingerprint_text


@pytest.mark.parametrize("arrow", ["=>", "-->", "⟹"])
def test_premises_differing_after_an_arrow_in_a_literal_are_two_claims(arrow):
    one = fingerprint_text(claim(f'assuming x != "a{arrow}b", f(x) >= 0'))
    two = fingerprint_text(claim(f'assuming x != "a{arrow}c", f(x) >= 0'))
    assert one != two
    assert f'"a{arrow}b"' in one, one


@pytest.mark.parametrize("statement, identity", [
    ("assuming f is defined --> x != 0, f(x) >= 0",
     "assuming f is defined, f(x) >= 0"),
    ('assuming f is defined --> x != "a", f(x) >= 0',
     "assuming f is defined, f(x) >= 0"),
    ('assuming x > 0 and f is defined --> x != "a=>b", f(x) >= 0',
     "assuming x > 0 and f is defined, f(x) >= 0"),
    ('assuming x != "a and b" and f is defined --> x > 1, f(x) >= 0',
     'assuming x != "a and b" and f is defined, f(x) >= 0'),
    ('assuming x != "a=>b" and f is defined --> x > 1, f(x) >= 0',
     'assuming x != "a=>b" and f is defined, f(x) >= 0'),
])
def test_a_pin_outside_every_literal_is_stripped(statement, identity):
    assert fingerprint_text(claim(statement)) == identity


def test_a_premise_with_no_arrow_is_its_own_identity():
    assert fingerprint_text(claim("assuming x > 0, f(x) >= 0")) \
        == "assuming x > 0, f(x) >= 0"
