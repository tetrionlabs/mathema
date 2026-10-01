# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim over a language visits every hazard of that language before
it relies on chance: the first draws for a language-bound parameter
are one lap over the language's hazards (the members of an excluded
set left out), and only then does the probe mix hazards and random
members. So a member at a length bound, `L[unicode, len <= 81]`'s
member of length 81, is always tried."""
from dataclasses import dataclass

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.domain import parse_binding
from mathema.languages import (HazardValue, StringLanguage, register_language,
                               resolve_language, unregister_language)

ANY = StringLanguage("any_text", char_ok=lambda c: True, pool="abcXYZ \u00e9")


@pytest.fixture
def letters():
    register_language("any_text", ANY)
    try:
        yield
    finally:
        unregister_language("any_text")


def headline(s):
    """At most eighty characters of s."""
    return s[:80]


def test_the_member_at_the_bound_is_always_tried(letters):
    (p,) = check_conjectures(headline, [claim("for s in L[any_text, len <= 81], f(s) == s")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    (q,) = check_conjectures(headline, [claim("for s in L[any_text, len <= 80], f(s) == s")])
    assert q.verdict == "holds", (q.verdict, q.note)


def _hazards(text):
    bound = parse_binding(f"s in {text}")[1]
    return [h.value for piece in bound.pieces for h in resolve_language(piece).hazards()]


@pytest.mark.parametrize("text", ["L[any_text]", "L[any_text, len in [2, 40]]"])
def test_every_hazard_is_visited(letters, text):
    seen = []

    def spy(s):
        """The input, recorded."""
        seen.append(s)
        return s

    (p,) = check_conjectures(spy, [claim(f"for s in {text}, f(s) == s", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    missed = [h for h in _hazards(text) if h not in seen]
    assert not missed, missed


def test_an_excluded_hazard_is_not_visited(letters):
    seen = []

    def spy(s):
        """The input, recorded."""
        seen.append(s)
        return s

    assert len(_hazards("L[any_text]")) > 20
    assert "" in _hazards("L[any_text]")
    (p,) = check_conjectures(spy, [claim('for s in L[any_text] \\ {""}, f(s) == s',
                                         route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "" not in seen



@dataclass(frozen=True)
class _Crowded(StringLanguage):
    """Every string, with forty extra hazards and a needle last."""

    def hazards(self):
        extra = tuple(HazardValue("text", f"w{i}", "a word") for i in range(40))
        return super().hazards() + extra + (HazardValue("text", "needle", "the needle"),)


def flag(s):
    """Whether s is the needle."""
    return 1 if s == "needle" else 0


def test_a_small_trial_budget_still_finishes_the_lap():
    crowded = _Crowded("crowded", char_ok=lambda c: True, pool="abc")
    register_language("crowded", crowded)
    try:
        (p,) = check_conjectures(flag, [claim("for s in L[crowded], f(s) == 0", route="probe")])
        (q,) = check_conjectures(flag, [claim('for s in L[crowded] \\ {"needle"}, f(s) == 0',
                                              route="probe")])
    finally:
        unregister_language("crowded")
    assert p.verdict == "falsified", (p.verdict, p.n, p.note)
    assert "needle" in str(p.counterexample)
    assert q.verdict == "holds", (q.verdict, q.note)
    assert q.n >= len(crowded.hazards()) - 1


def test_the_members_at_a_bound_come_first_and_plain(letters):
    from mathema.probing import _language_lap
    import random
    bound = parse_binding("s in L[any_text, len in [3, 81]]")[1]
    lap = _language_lap(random.Random(0), bound)
    assert [lap.next(), lap.next()] == ["a" * 3, "a" * 81]
    (p,) = check_conjectures(headline, [claim("for s in L[any_text, len <= 81], f(s) == s")])
    assert p.verdict == "falsified"
    assert p.counterexample.startswith("s = '" + "a" * 81 + "':"), p.counterexample
