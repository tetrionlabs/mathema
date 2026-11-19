# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The strings mathema draws for a text parameter test how code handles
awkward text (empty, whitespace, control characters, combining marks,
other scripts, a long string, format braces), never what it does with
an attack: no SQL statement, no path that climbs out of a directory, no
printf write directive."""
import random
import re

_ATTACK = re.compile(r"(?i)drop\s+table|;\s*--|\.\./|/etc/|%n")
#: what a random draw must never carry; a `%` beside an `n` can turn up
#: in random text by chance, so only the planted shapes are checked
_PLANTED = re.compile(r"(?i)drop\s+table|;\s*--|\.\./|/etc/")


def test_the_string_corpus_holds_no_attack_shaped_string():
    from mathema._sampling import _STRING_SPECIALS
    assert [s for s in _STRING_SPECIALS if _ATTACK.search(s)] == []


def test_the_string_hazards_hold_no_attack_shaped_string():
    from mathema.languages import STRING_HAZARDS
    assert [h.value for h in STRING_HAZARDS if _ATTACK.search(h.value)] == []


def test_a_text_language_never_draws_an_attack_shaped_string():
    from mathema.languages import resolve_language
    lang = resolve_language("unicode")
    rng = random.Random(0)
    drawn = [lang.sample(rng) for _ in range(2000)] + [h.value for h in lang.hazards()]
    assert [s for s in drawn if _PLANTED.search(s)] == []
