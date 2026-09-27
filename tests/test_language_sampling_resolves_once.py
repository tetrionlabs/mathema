# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's draws from a language resolve it and build its hazards
once, not once per draw: a language whose hazards are costly to build
(a spine past the recursion limit, members at a refinement's bounds)
is sampled at the cost of one build. Registering or removing a
language or a refinement is seen by the next draw."""
from mathema.conjecture import check_conjectures, claim
from mathema.languages import (StringLanguage, register_language, unregister_language)

BUILDS: list = []


class _Counted(StringLanguage):
    """Letters, counting how often their hazards are built."""

    def hazards(self):
        BUILDS.append(1)
        return super().hazards()


def letters(s) -> int:
    """How many characters s has."""
    return len(s)


def test_one_claim_builds_the_hazards_once():
    register_language("counted_letters", _Counted("counted_letters", char_ok=str.isalpha,
                                                  pool="ab"))
    BUILDS.clear()
    try:
        (p,) = check_conjectures(letters, [claim("for s in L[counted_letters], f(s) >= 0")])
    finally:
        unregister_language("counted_letters")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert len(BUILDS) <= 3, len(BUILDS)


def test_a_language_registered_again_is_seen_by_the_next_draw():
    text = "for s in L[swapped_letters], f(s) >= 1"
    cj = claim(text)
    register_language("swapped_letters", StringLanguage("swapped_letters", char_ok=str.isalpha,
                                                        pool="ab"))
    try:
        (first,) = check_conjectures(letters, [cj])
        unregister_language("swapped_letters")
        register_language("swapped_letters", StringLanguage(
            "swapped_letters", level="predicate", accepts=lambda s: s.isalpha(), pool="ab"))
        (second,) = check_conjectures(letters, [cj])
    finally:
        unregister_language("swapped_letters")
    assert first.verdict == "falsified", (first.verdict, first.note)
    assert second.verdict == "holds", (second.verdict, second.note)
