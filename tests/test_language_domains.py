# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Language domains, `for s in L[letters]`: a binding over a named
language parses to a language domain, renders back as a fixed point in
both spellings, round-trips through the JSON codec, judges membership
through the language, and has no real-set reading on the derive side.
Core ships no language of its own, so these tests register two: an
alphabet built with the `StringLanguage` kit, and a finite one. A
language's hazards and samples are members of it, and a value outside
it never is."""
import json
import random

import pytest
import sympy

from mathema.domain import (MISSING, Domain, InvalidDomain, LanguageRef,
                            bound_assumptions, bound_context, bound_is_empty,
                            bound_pin, bound_to_sympy_set, canonical_bound,
                            domain_bound_from_json, domain_bound_to_json,
                            domain_contains, finite_members, parse_binding,
                            render_domain, split_bound_at, split_quantifier)
from mathema.languages import (HAZARD_KINDS, Problem, StringLanguage,
                               language_problems, register_language,
                               unregister_language)

LETTERS = StringLanguage("letters", char_ok=str.isalpha,
                         pool="abcXYZéΩ", outside_pool="1 -.",
                         schema={"pattern": "^[^\\\\W\\\\d_]*$"})


class _Colours:
    """A finite language, three words."""
    name = "colours"
    kind = "string"
    level = "finite"
    WORDS = ("red", "green", "blue")

    def contains(self, value):
        return value in self.WORDS

    def explain(self, value):
        return None if self.contains(value) else [Problem("", "colours", value)]

    def sample(self, rng):
        return rng.choice(self.WORDS)

    def members(self, limit):
        return self.WORDS if len(self.WORDS) <= limit else None

    def hazards(self):
        return ()

    def outside(self, rng):
        return "purple"

    def shrink(self, value):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return "L[colours]"

    def to_json(self):
        return {"type": "string", "enum": list(self.WORDS)}


class _Prefix(_Colours):
    """A language that answers `members` with more than asked for."""
    name = "prefix"

    def members(self, limit):
        return tuple(f"w{i}" for i in range(limit + 5))


@pytest.fixture(autouse=True, scope="module")
def _languages():
    register_language("letters", LETTERS)
    register_language("colours", _Colours())
    register_language("prefix", _Prefix())
    try:
        yield
    finally:
        for name in ("letters", "colours", "prefix"):
            unregister_language(name)


SPELLINGS = [
    "s in L[letters]",
    's in L[letters] \\ {""}',
    's in L[letters] | {"n/a"}',
    "s in L[colours] ∪ {∅}",
    "s in L[letters] \\ {∅}",
    's in L[letters] \\ {"", missing}',
    "s ∈ L[unicode]",
    "s in L[letters]|missing",
    "s in L[letters] \\ {missing}",
    "s in L[letters] | L[colours]",
    "s in L[latin-1]",
    "s in L[myapp.models.Order]",
    "s ∈ 𝕃[letters]",
]


def _bound(text):
    return parse_binding(text)[1]


@pytest.mark.parametrize("text", SPELLINGS)
def test_a_language_binding_parses_to_a_language_domain(text):
    name, bound = parse_binding(text)
    assert name == "s"
    assert isinstance(bound, Domain)
    assert bound.base_type == "L" and bound.explicit_type
    assert any(isinstance(p, LanguageRef) for p in bound.pieces)


@pytest.mark.parametrize("text", SPELLINGS)
@pytest.mark.parametrize("ascii_mode", [True, False])
def test_the_rendered_domain_is_a_fixed_point(text, ascii_mode):
    bound = _bound(text)
    rendered = render_domain(bound, ascii_mode=ascii_mode)
    again = _bound(f"s in {rendered}")
    assert again == bound
    assert render_domain(again, ascii_mode=ascii_mode) == rendered


def test_rendering_states_what_the_language_domain_admits():
    bare = _bound("s in L[letters]")
    assert render_domain(bare, ascii_mode=True) == "L[letters]"
    assert render_domain(bare, ascii_mode=False) == "L[letters]"
    absent = _bound("s in L[letters]|None")
    assert render_domain(absent, ascii_mode=True) == "L[letters]|None"
    assert render_domain(absent, ascii_mode=False) == "L[letters]|None"
    excluded = _bound("s in L[letters] \\ {∅}")
    assert render_domain(excluded, ascii_mode=True) == "L[letters]"


def test_a_union_with_a_finite_set_and_an_exclusion_render_as_written():
    bound = _bound('s in L[letters] | {"n/a"} \\ {""}')
    assert render_domain(bound, ascii_mode=False) == \
        'L[letters] ∪ {"n/a"} \\ {""}'


@pytest.mark.parametrize("text", SPELLINGS)
def test_json_round_trip(text):
    bound = _bound(text)
    encoded = json.loads(json.dumps(domain_bound_to_json(bound)))
    assert domain_bound_from_json(encoded) == bound


def test_the_double_struck_glyph_is_input_only():
    from mathema.grammar import normalize
    assert normalize("for s in 𝕃[letters], f(s) == s") == \
        normalize("for s in L[letters], f(s) == s")
    bound = _bound("s in 𝕃[letters]")
    assert "𝕃" not in render_domain(bound, ascii_mode=False)
    assert "𝕃" not in render_domain(bound, ascii_mode=True)


def test_a_bare_language_ref_round_trips_through_json():
    assert domain_bound_from_json(domain_bound_to_json(LanguageRef("letters"))) \
        == LanguageRef("letters")


def test_a_quantifier_over_a_language_leaves_the_law_alone():
    domain, law = split_quantifier("for s in L[letters], f(s) == s")
    assert law == "f(s) == s"
    assert domain["s"] == Domain(base_type="L", pieces=(LanguageRef("letters"),),
                                 explicit_type=True)


@pytest.mark.parametrize("text,reason", [
    ("for s in L[letters]^n, f(s) == s", "no dimension power"),
    ("for s in L[letters] subset Z, f(s) == s", "contradicts"),
    ("for s in L[letters] ⊂ R, f(s) == s", "contradicts"),
    ("for s in L[letters] | [0, 1], f(s) == s", "finite set of members"),
    ("for s in L[letters] | Z, f(s) == s", "finite set of members"),
    ("for s in L, f(s) == s", "isn't a recognized"),
])
def test_a_refused_spelling_says_why(text, reason):
    with pytest.raises(InvalidDomain, match=reason):
        split_quantifier(text)


def test_membership_is_the_language_s_own():
    bound = _bound("s in L[letters]")
    assert domain_contains("abc", bound)
    assert domain_contains("", bound)
    assert domain_contains("café", bound)
    assert not domain_contains("ab1", bound)
    assert not domain_contains(3, bound)
    assert not domain_contains(b"abc", bound)


def test_a_language_admits_absence_only_when_it_says_so():
    assert not domain_contains(None, _bound("s in L[letters]"))
    assert domain_contains(None, _bound("s in L[letters]|None"))
    assert not domain_contains(None, _bound("s in L[letters] \\ {∅}"))


def test_exclusion_and_union_apply_to_a_language():
    assert not domain_contains("", _bound('s in L[letters] \\ {""}'))
    assert domain_contains("n/a", _bound('s in L[letters] | {"n/a"}'))
    assert domain_contains("red", _bound("s in L[letters] | L[colours]"))
    assert not domain_contains("1", _bound("s in L[letters] | L[colours]"))


def test_an_unhashable_value_is_not_a_member_and_does_not_crash():
    bound = _bound('s in L[letters] \\ {""}')
    assert not domain_contains({"a": 1}, bound)
    assert not domain_contains([1, 2], bound)


def test_an_unresolvable_name_refuses_membership_with_the_remedy():
    with pytest.raises(InvalidDomain, match=r"unknown language L\[nope\].*mathema\[language\]"):
        domain_contains("abc", _bound("s in L[nope]"))


def test_an_alphabet_language_has_no_finite_members():
    assert finite_members(_bound("s in L[letters]"), 10_000) is None


def test_a_finite_language_enumerates_its_members_minus_exclusions():
    assert finite_members(_bound("s in L[colours]"), 10) == ("blue", "green", "red")
    assert finite_members(_bound('s in L[colours] \\ {"green"}'), 10) == ("blue", "red")
    assert finite_members(_bound('s in L[colours] | {"black"}'), 10) == \
        ("black", "blue", "green", "red")
    assert finite_members(_bound("s in L[colours]"), 2) is None


def test_members_past_the_limit_is_none_never_a_prefix():
    assert finite_members(_bound("s in L[prefix]"), 10) is None


def test_projections_have_no_real_reading():
    bound = _bound("s in L[letters]")
    assert bound_assumptions(bound) is None
    assert bound_context(sympy.Symbol("s"), bound) is None
    with pytest.raises(InvalidDomain, match="no real-set reading"):
        bound_to_sympy_set(bound)
    with pytest.raises(InvalidDomain):
        bound_to_sympy_set(LanguageRef("letters"))
    with pytest.raises(InvalidDomain):
        bound_to_sympy_set("L")


def test_the_numeric_helpers_are_untouched_by_a_language():
    bound = _bound("s in L[letters]")
    assert bound_pin(bound) == (False, None)
    assert split_bound_at(bound, [0.5]) is None
    assert canonical_bound(bound) == (bound, None)
    assert not bound_is_empty(bound)


# --- the StringLanguage kit -------------------------------------------

def test_the_kit_satisfies_the_protocol():
    assert language_problems(LETTERS) == []
    assert LETTERS.kind == "string" and LETTERS.level == "alphabet"


def test_the_kit_s_hazards_are_members():
    for hazard in LETTERS.hazards():
        assert hazard.kind in HAZARD_KINDS
        assert LETTERS.contains(hazard.value), hazard
    assert any(h.kind == "length" for h in LETTERS.hazards())
    assert any(h.value == "" for h in LETTERS.hazards())


def test_the_kit_s_samples_are_members():
    rng = random.Random(7)
    for _ in range(200):
        assert LETTERS.contains(LETTERS.sample(rng))


def test_the_kit_s_outside_is_never_a_member():
    rng = random.Random(7)
    for _ in range(50):
        value = LETTERS.outside(rng)
        assert value is None or not LETTERS.contains(value)
    everything = StringLanguage("everything", accepts=lambda s: True)
    assert everything.outside(rng) is None


def test_an_alphabet_contains_the_empty_string_and_a_predicate_may_not():
    assert LETTERS.contains("")
    identifiers = StringLanguage("identifier", level="predicate",
                                 accepts=str.isidentifier, pool="ab_1")
    assert not identifiers.contains("") and identifiers.contains("a_1")
    rng = random.Random(3)
    for _ in range(100):
        assert identifiers.contains(identifiers.sample(rng))


def test_explain_names_the_offending_character():
    assert LETTERS.explain("abc") is None
    assert LETTERS.explain("ab1") == [Problem("[2]", "letters alphabet", "1")]
    assert LETTERS.explain(3) == [Problem("", "str", 3)]


def test_shrink_offers_smaller_members_only():
    smaller = list(LETTERS.shrink("abcd"))
    assert smaller and all(LETTERS.contains(s) and len(s) <= 4 for s in smaller)
    assert "" in smaller


def test_the_persisted_form_names_the_language():
    assert LETTERS.to_json()["language"] == "letters"
    assert LETTERS.to_json()["type"] == "string"
    assert LETTERS.to_json()["pattern"].startswith("^")


def test_a_frozen_language_ref_is_never_read_as_an_interval():
    ref = LanguageRef("letters")
    assert not isinstance(ref, tuple)
    assert hash(ref) == hash(LanguageRef("letters"))
    assert repr(ref) == "L[letters]"


def test_a_missing_member_of_a_language_set_piece_is_the_policy():
    bound = _bound('s in L[letters] | {"x", missing}')
    assert domain_contains(float("nan"), bound)
    assert not domain_contains(None, bound)
    assert MISSING not in bound.excluded
