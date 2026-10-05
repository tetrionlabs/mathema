# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The families decision A renames keep their old spellings as
accepted input: `is_builtin_safe` is `is_number_set_safe`,
`is_extremity_safe` is `is_overflow_safe` and `is_arbitrary_input_safe`
is `is_language_defined`. A claim written with the old spelling is the
claim under the new name, and its record says the spelling was
accepted and what it resolved to."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim


def root(x: float) -> float:
    return math.sqrt(x)


def first_word(s: str) -> str:
    return s.split()[0]


@pytest.mark.parametrize("old, new", [
    ("is_builtin_safe", "is_number_set_safe"),
    ("is_extremity_safe", "is_overflow_safe"),
    ("is_arbitrary_input_safe", "is_language_defined"),
])
def test_the_old_spelling_parses_as_the_new_family(old, new):
    cj = claim(f"{old}(x)")
    assert cj.relation == new
    assert cj.name == f"{new}[x]"
    named = claim(f"{old}(x)", name=f"{old}[x]")
    assert named.name == f"{new}[x]"


@pytest.mark.parametrize("fn, old, new, target", [
    (root, "is_builtin_safe", "is_number_set_safe", "x"),
    (first_word, "is_arbitrary_input_safe", "is_language_defined", "s"),
])
def test_the_record_says_the_spelling_was_accepted(fn, old, new, target):
    (by_old,) = check_conjectures(fn, [claim(f"{old}({target})")])
    (by_new,) = check_conjectures(fn, [claim(f"{new}({target})")])
    assert by_old.name == by_new.name == f"{new}[{target}]"
    assert by_old.verdict == by_new.verdict
    assert f"{old} is an accepted spelling of {new}" in (by_old.note or "")
    assert (by_old.meta or {}).get("mathema.accepted_spelling") == old
    assert "accepted spelling" not in (by_new.note or "")
