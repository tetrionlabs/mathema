# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language that cannot produce a member (a schema whose checks
reject every record drawn) leaves the claim skipped with the
`input-synthesis` gap and the language's own reason, never an
exception out of adjudication."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import (HazardValue, StringLanguage, register_language,
                               unregister_language)


class _Barren(StringLanguage):
    """Letters whose random draws always fail, with `first` as its
    hazards."""

    first: tuple = ()

    def hazards(self):
        return tuple(HazardValue("text", v, "a hazard") for v in self.first)

    def sample(self, rng):
        raise ValueError("L[barren]: no member found in 50 draws")


def same(s: str) -> str:
    """The text, unchanged."""
    return s


@pytest.mark.parametrize("first", [(), ("a", "b")], ids=["no hazards", "hazards first"])
def test_a_language_that_cannot_draw_skips_the_claim(first):
    language = _Barren("barren", char_ok=str.isalpha, pool="ab")
    language.first = first
    register_language("barren", language)
    try:
        (p,) = check_conjectures(same, [claim("for s in L[barren], f(s) == s")])
    finally:
        unregister_language("barren")
    assert p.verdict == "skipped", (p.verdict, p.note)
    assert (p.meta or {}).get("mathema.probe_gap") == "input-synthesis"
    assert "no member found in 50 draws" in p.note
