# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The head of `L[...]` may be an alphabet expression: named alphabets
and single quoted characters joined by `+`, meaning every string over
the combined alphabet. Core reads the shape, writes it one way, and
hands the pieces to a registered constructor, which builds the language
and decides the order the pieces are written in. The constructor here
is made up for these tests."""
import pytest

from mathema.conjecture import claim
from mathema.domain import (InvalidDomain, alphabet_pieces, domain_bound_from_json,
                            domain_bound_to_json, parse_binding, read_call, render_alphabet)
from mathema.languages import (AlphabetConstructor, StringLanguage, UnknownLanguage,
                               register_alphabet_constructor, resolve_language,
                               unregister_alphabet_constructor)
from mathema.spec import fingerprint_text, render_claim_text

_NAMED = {"lower": "abcdefghijklmnopqrstuvwxyz", "digit": "0123456789"}


def _build(pieces):
    chars = set()
    for kind, value in pieces:
        if kind == "name" and value not in _NAMED:
            raise ValueError(f"{value!r} is not an alphabet")
        chars |= set(_NAMED[value]) if kind == "name" else {value}
    return StringLanguage(render_alphabet(pieces), char_ok=chars.__contains__,
                          pool="".join(sorted(chars)))


def _order(pieces):
    """Names in name order, then characters in code point order."""
    return tuple(sorted(set(pieces), key=lambda p: (p[0] != "name", p[1])))


CONSTRUCTOR = AlphabetConstructor(build=_build, order=_order)


@pytest.fixture
def constructor():
    register_alphabet_constructor(CONSTRUCTOR)
    try:
        yield
    finally:
        unregister_alphabet_constructor()


def _ref(text):
    return parse_binding(f"s in {text}")[1].pieces[0]


@pytest.mark.parametrize("text,canonical", [
    ('L[lower + digit + "_" + "-"]', 'L[digit + lower + "-" + "_"]'),
    ('L[lower+digit+"_"]', 'L[digit + lower + "_"]'),
    ('L[digit + lower + "_-"]', 'L[digit + lower + "-" + "_"]'),
    ("L[lower + '_']", 'L[lower + "_"]'),
    ('L[lower + lower + "a" + "a"]', 'L[lower + "a"]'),
    ('L["a" + "b"]', 'L["a" + "b"]'),
    ('L["ab"]', 'L["a" + "b"]'),
    ('L[lower + "+" + "," + "]" + "|"]', 'L[lower + "+" + "," + "]" + "|"]'),
    ('L[lower + "\\"" + "\\\\"]', 'L[lower + "\\"" + "\\\\"]'),
    ('L[lower + digit + "_" + "-", len in [3, 32]]', 'L[digit + lower + "-" + "_", len in [3, 32]]'),
])
def test_an_alphabet_expression_is_written_in_the_constructors_order(constructor, text, canonical):
    ref = _ref(text)
    assert repr(ref) == canonical
    assert repr(_ref(canonical)) == canonical


def test_without_a_constructor_the_pieces_keep_their_written_order_once_each():
    assert repr(_ref('L[lower + digit + "_" + lower]')) == 'L[lower + digit + "_"]'


def test_the_pieces_are_names_and_single_characters():
    assert alphabet_pieces('lower + digit + "_-"') == (
        ("name", "lower"), ("name", "digit"), ("char", "_"), ("char", "-"))
    assert alphabet_pieces("lower") is None
    assert alphabet_pieces("app.models.Order") is None
    assert alphabet_pieces('lower + ""') is None
    assert alphabet_pieces("lower + 3") is None
    assert alphabet_pieces("lower + f(x)") is None


def test_a_named_language_and_a_union_of_languages_read_as_before(constructor):
    assert repr(_ref("L[lower]")) == "L[lower]"
    assert _ref("L[lower]").name == "lower"
    bound = parse_binding("s in L[lower] | L[digit]")[1]
    assert [repr(p) for p in bound.pieces] == ["L[lower]", "L[digit]"]


def test_the_constructor_builds_every_string_over_the_combined_alphabet(constructor):
    language = resolve_language(_ref('L[lower + digit + "_"]'))
    assert language.contains("a_9") and language.contains("")
    assert not language.contains("A") and not language.contains("a-b")


def test_an_expression_with_no_constructor_registered_is_refused_at_resolution():
    with pytest.raises(UnknownLanguage, match="no alphabet constructor is registered"):
        resolve_language(_ref('L[lower + "_"]'))


def test_a_piece_the_constructor_refuses_is_refused_with_its_reason(constructor):
    with pytest.raises(UnknownLanguage, match="'upper' is not an alphabet"):
        resolve_language(_ref('L[upper + "_"]'))


def test_a_claim_over_an_alphabet_expression_round_trips_with_one_fingerprint(constructor):
    spellings = ['for s in L[lower + digit + "_"], f(s) == s',
                 'for s in L[digit+lower+"_"], f(s) == s']
    assert {fingerprint_text(claim(t)) for t in spellings} == {
        'for s in L[digit + lower + "_"], f(s) = s'}
    for unicode in (False, True):
        rendered = render_claim_text(claim(spellings[0]), unicode=unicode)
        assert fingerprint_text(claim(rendered)) == 'for s in L[digit + lower + "_"], f(s) = s'


def test_an_alphabet_expression_persists_and_loads_back(constructor):
    ref = _ref('L[lower + "_", len <= 8]')
    assert domain_bound_from_json(domain_bound_to_json(ref)) == ref


def test_a_refinement_after_an_expression_is_still_checked(constructor):
    with pytest.raises(InvalidDomain):
        _ref('L[lower + "_", len <= ]')


@pytest.mark.parametrize("text,read", [
    ('shape("AW{0+}", W = alnum + "_")',
     ("shape", '"AW{0+}"', (), (("W", (("name", "alnum"), ("char", "_"))),))),
    ('shape("AW", python, W = alnum + "_", A = lower)',
     ("shape", '"AW"', ("python",), (("W", (("name", "alnum"), ("char", "_"))),
                                      ("A", (("name", "lower"),))))),
    ('shape("A", ignoreCase)', ("shape", '"A"', ("ignore case",), ())),
])
def test_a_call_argument_list_may_bind_names_to_alphabets(text, read):
    assert read_call(text) == read


def test_a_binding_that_is_no_alphabet_expression_is_not_read():
    assert read_call('shape("A", W = 3)') is None
    assert read_call('shape("A", W = f(x))') is None
