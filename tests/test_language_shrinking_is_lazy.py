# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language's shrink candidates come one at a time, the largest
deletions first, and the witness shrinker takes them as they come, so a
long failing value shrinks in a number of membership checks that grows
with its length's logarithm, not with its square."""
from mathema.conjecture import check_conjectures, claim
from mathema.languages import (HazardValue, StringLanguage, register_language,
                               unregister_language)

CHECKS: list = []


class _Counted(StringLanguage):
    """Letters, counting membership checks, with one long hazard."""

    def contains(self, value):
        CHECKS.append(1)
        return super().contains(value)

    def hazards(self):
        return (HazardValue("length", "a" * 20000 + "é", "a long run then an accent"),)


def has_accent(s: str) -> bool:
    """Whether s has no accented e."""
    return "é" not in s


def test_the_first_candidate_comes_before_the_rest_are_checked():
    language = _Counted("counted_letters", char_ok=str.isalpha, pool="ab")
    CHECKS.clear()
    first = next(iter(language.shrink("a" * 20000 + "é")))
    assert len(first) < 20001 and len(CHECKS) <= 3, len(CHECKS)


def test_a_long_witness_shrinks_in_few_checks():
    register_language("counted_letters", _Counted("counted_letters", char_ok=str.isalpha,
                                                  pool="ab"))
    CHECKS.clear()
    try:
        (p,) = check_conjectures(has_accent, [claim(
            "for s in L[counted_letters], f(s) == True")])
    finally:
        unregister_language("counted_letters")
    assert p.verdict == "falsified" and p.counterexample.startswith("s = 'é':"), p.counterexample
    assert len(CHECKS) < 5000, len(CHECKS)
