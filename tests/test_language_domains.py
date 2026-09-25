# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Language domains, `for s in L[ascii]`: a binding over a named
language parses to a language domain, renders back as a fixed point in
both spellings, round-trips through the JSON codec, judges membership
through the language, and has no real-set reading on the derive side.
Every built-in alphabet's hazards and samples are members of it, and a
value outside it is never one."""
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
from mathema.languages import (BUILTIN_LANGUAGES, HAZARD_KINDS, Problem,
                               register_language, unregister_language)

SPELLINGS = [
    "s in L[ascii]",
    's in L[ascii] \\ {""}',
    's in L[ascii] | {"special"}',
    "s in L[latin-1] ∪ {∅}",
    "s in L[ascii] \\ {∅}",
    's in L[ascii] \\ {"", missing}',
    "s ∈ L[unicode]",
    "s in L[digit]|missing",
    "s in L[ascii] \\ {missing}",
    "s in L[ascii] | L[digit]",
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


def test_rendering_states_the_resolved_missing_policy():
    included = _bound("s in L[ascii]")
    assert render_domain(included, ascii_mode=True) == "L[ascii]|missing"
    assert render_domain(included, ascii_mode=False) == "L[ascii] ∪ {∅}"
    excluded = _bound("s in L[ascii] \\ {∅}")
    assert render_domain(excluded, ascii_mode=True) == "L[ascii] \\ {missing}"
    assert render_domain(excluded, ascii_mode=False) == "L[ascii] \\ {∅}"


def test_a_union_with_a_finite_set_and_an_exclusion_render_as_written():
    bound = _bound('s in L[ascii] | {"special"} \\ {""}')
    assert render_domain(bound, ascii_mode=False) == \
        'L[ascii] ∪ {"special"} \\ {""} ∪ {∅}'


@pytest.mark.parametrize("text", SPELLINGS)
def test_json_round_trip(text):
    bound = _bound(text)
    encoded = json.loads(json.dumps(domain_bound_to_json(bound)))
    assert domain_bound_from_json(encoded) == bound


def test_a_bare_language_ref_round_trips_through_json():
    assert domain_bound_from_json(domain_bound_to_json(LanguageRef("ascii"))) \
        == LanguageRef("ascii")


def test_a_quantifier_over_a_language_leaves_the_law_alone():
    domain, law = split_quantifier("for s in L[ascii], f(s) == s")
    assert law == "f(s) == s"
    assert domain["s"] == Domain(base_type="L", pieces=(LanguageRef("ascii"),),
                                 explicit_type=True)


@pytest.mark.parametrize("text,reason", [
    ("for s in L[ascii]^n, f(s) == s", "no dimension power"),
    ("for s in L[ascii] subset Z, f(s) == s", "contradicts"),
    ("for s in L[ascii] ⊂ R, f(s) == s", "contradicts"),
    ("for s in L[ascii] | [0, 1], f(s) == s", "finite set of members"),
    ("for s in L[ascii] | Z, f(s) == s", "finite set of members"),
    ("for s in L, f(s) == s", "isn't a recognized"),
])
def test_a_refused_spelling_says_why(text, reason):
    with pytest.raises(InvalidDomain, match=reason):
        split_quantifier(text)


def test_membership_is_the_language_s_own():
    bound = _bound("s in L[ascii]")
    assert domain_contains("abc", bound)
    assert domain_contains("", bound)
    assert not domain_contains("café", bound)
    assert not domain_contains(3, bound)
    assert not domain_contains(b"abc", bound)


def test_missing_is_allowed_unless_excluded():
    assert domain_contains(None, _bound("s in L[ascii]"))
    assert not domain_contains(None, _bound("s in L[ascii] \\ {∅}"))


def test_exclusion_and_union_apply_to_a_language():
    assert not domain_contains("", _bound('s in L[ascii] \\ {""}'))
    assert domain_contains("café", _bound('s in L[ascii] | {"café"}'))
    assert domain_contains("1", _bound("s in L[alpha] | L[digit]"))
    assert not domain_contains("1a", _bound("s in L[alpha] | L[digit]"))


def test_an_unhashable_value_is_not_a_member_and_does_not_crash():
    bound = _bound('s in L[ascii] \\ {""}')
    assert not domain_contains({"a": 1}, bound)
    assert not domain_contains([1, 2], bound)


def test_an_alphabet_language_has_no_finite_members():
    assert finite_members(_bound("s in L[ascii]"), 10_000) is None


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


@pytest.fixture
def colours():
    register_language("colours", _Colours())
    register_language("prefix", _Prefix())
    try:
        yield
    finally:
        unregister_language("colours")
        unregister_language("prefix")


def test_a_finite_language_enumerates_its_members_minus_exclusions(colours):
    assert finite_members(_bound("s in L[colours]"), 10) == ("blue", "green", "red")
    assert finite_members(_bound('s in L[colours] \\ {"green"}'), 10) == ("blue", "red")
    assert finite_members(_bound('s in L[colours] | {"black"}'), 10) == \
        ("black", "blue", "green", "red")
    assert finite_members(_bound("s in L[colours]"), 2) is None


def test_members_past_the_limit_is_none_never_a_prefix(colours):
    assert finite_members(_bound("s in L[prefix]"), 10) is None


def test_projections_have_no_real_reading():
    bound = _bound("s in L[ascii]")
    assert bound_assumptions(bound) is None
    assert bound_context(sympy.Symbol("s"), bound) is None
    with pytest.raises(InvalidDomain, match="no real-set reading"):
        bound_to_sympy_set(bound)
    with pytest.raises(InvalidDomain):
        bound_to_sympy_set(LanguageRef("ascii"))
    with pytest.raises(InvalidDomain):
        bound_to_sympy_set("L")


def test_the_numeric_helpers_are_untouched_by_a_language():
    bound = _bound("s in L[ascii]")
    assert bound_pin(bound) == (False, None)
    assert split_bound_at(bound, [0.5]) is None
    assert canonical_bound(bound) == (bound, None)
    assert not bound_is_empty(bound)


@pytest.mark.parametrize("name", sorted(BUILTIN_LANGUAGES))
def test_builtin_hazards_are_members(name):
    language = BUILTIN_LANGUAGES[name]
    for hazard in language.hazards():
        assert hazard.kind in HAZARD_KINDS
        assert language.contains(hazard.value), (name, hazard)


@pytest.mark.parametrize("name", sorted(BUILTIN_LANGUAGES))
def test_builtin_samples_are_members(name):
    language = BUILTIN_LANGUAGES[name]
    rng = random.Random(7)
    for _ in range(200):
        assert language.contains(language.sample(rng))


@pytest.mark.parametrize("name", sorted(BUILTIN_LANGUAGES))
def test_builtin_outside_is_never_a_member(name):
    language = BUILTIN_LANGUAGES[name]
    rng = random.Random(7)
    for _ in range(50):
        value = language.outside(rng)
        assert value is None or not language.contains(value)


def test_every_string_is_a_member_of_unicode_and_nothing_lies_outside():
    unicode = BUILTIN_LANGUAGES["unicode"]
    assert unicode.contains("\ud800") and unicode.contains("")
    assert unicode.outside(random.Random(1)) is None


def test_an_alphabet_contains_the_empty_string_and_a_predicate_may_not():
    for name in ("ascii", "latin-1", "unicode", "printable", "digit",
                 "alpha", "alnum"):
        assert BUILTIN_LANGUAGES[name].contains("")
        assert BUILTIN_LANGUAGES[name].level == "alphabet"
    assert not BUILTIN_LANGUAGES["identifier"].contains("")
    assert not BUILTIN_LANGUAGES["json"].contains("")
    assert BUILTIN_LANGUAGES["json"].contains("[1, {\"a\": null}]")


def test_explain_names_the_offending_character():
    ascii = BUILTIN_LANGUAGES["ascii"]
    assert ascii.explain("abc") is None
    assert ascii.explain("abé") == [Problem("[2]", "ascii alphabet", "é")]
    assert ascii.explain(3) == [Problem("", "str", 3)]
    assert BUILTIN_LANGUAGES["json"].explain("{") == [Problem("", "json", "{")]


def test_shrink_offers_smaller_members_only():
    digit = BUILTIN_LANGUAGES["digit"]
    smaller = digit.shrink("1234")
    assert smaller and all(digit.contains(s) and len(s) <= 4 for s in smaller)
    assert "" in smaller
    assert all(c in "0123456789" for s in smaller for c in s)


def test_the_persisted_form_names_the_language():
    assert BUILTIN_LANGUAGES["ascii"].to_json()["language"] == "ascii"
    assert BUILTIN_LANGUAGES["ascii"].to_json()["type"] == "string"
    assert BUILTIN_LANGUAGES["digit"].to_json()["pattern"] == "^[0-9]*$"


def test_a_frozen_language_ref_is_never_read_as_an_interval():
    ref = LanguageRef("ascii")
    assert not isinstance(ref, tuple)
    assert hash(ref) == hash(LanguageRef("ascii"))
    assert repr(ref) == "L[ascii]"


def test_a_missing_member_of_a_language_set_piece_is_the_policy():
    bound = _bound('s in L[ascii] | {"x", missing}')
    assert domain_contains(None, bound)
    assert MISSING not in bound.excluded
