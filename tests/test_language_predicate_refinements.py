# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Predicate refinements inside `L[...]`: beside a measure comparison
(`len <= 80`), a refinement may be a predicate applied to the member,
`word (arguments)`, negated by `not`, or written with an operator that
reads as a registered word. Core reads the shape and renders it one
way, lower-case words with a space before the brackets; every word,
what it means and how its arguments are written belong to whatever
registers it. The words here are made up for these tests."""
import dataclasses

import pytest

import mathema.languages as languages
from mathema.conjecture import claim
from mathema.domain import (InvalidDomain, LanguageRef, Predicate, domain_bound_from_json,
                            domain_bound_to_json, parse_binding)
from mathema.languages import (MeaninglessPredicate, PredicateWord, UnknownPredicate, StringLanguage, UnknownRefinement,
                               language_problems, register_language, register_predicate,
                               resolve_language, unregister_language, unregister_predicate)
from mathema.spec import fingerprint_text, render_claim_text

WORDS = StringLanguage("words", char_ok=str.isalpha, pool="ab")
NUMBERS = dataclasses.replace(StringLanguage("numbers", char_ok=str.isdigit, pool="12"),
                              kind="sequence")


class Kept:
    """The members of `base` that `keep` accepts, for these tests."""

    def __init__(self, base, keep):
        self.base, self.keep = base, keep

    def __getattr__(self, name):
        return getattr(self.base, name)

    def contains(self, value):
        return self.base.contains(value) and self.keep(value)


def _unquoted(arg):
    return arg[1:-1]


def _begins(language, args, negated):
    return Kept(language, lambda s: any(s.startswith(_unquoted(a)) for a in args) != negated)


def _has(language, args, negated):
    return Kept(language, lambda s: (_unquoted(args[0]) in s) != negated)


def _fits_arguments(args, sugar):
    if sugar == "==" and args[0].startswith("shape("):
        raise ValueError("a member is not equal to a shape; write `in shape(...)`")
    return tuple(a.replace("'", '"') for a in args)


def _fits(language, args, negated):
    return Kept(language, lambda s: (s == _unquoted(args[0])) != negated)


def _inside(language, args, negated):
    # the word reads its arguments by the kind of language it refines
    if language.kind == "sequence":
        return Kept(language, lambda s: (len(s) <= len(args)) != negated)
    return Kept(language, lambda s: any(s.startswith(_unquoted(a)) for a in args) != negated)


class Shape:
    """A stand-in for an object a predicate word claims."""


SHAPE = Shape()
_HERE = "tests.test_language_predicate_refinements"

_REGISTERED = (
    PredicateWord("begins with", _begins, sugar=("^=",)),
    PredicateWord("has", _has, sugar=("*=",)),
    PredicateWord("fits", _fits, sugar=("in", "=="), arguments=_fits_arguments,
                  suggest=lambda base, args: f"L[{base or 'words'}, fits ({', '.join(args)})]"),
    PredicateWord("inside", _inside, keyword=True),
)


@pytest.fixture(autouse=True)
def words():
    register_language("words", WORDS)
    register_language("numbers", NUMBERS)
    for word in _REGISTERED:
        register_predicate(word)
    try:
        yield
    finally:
        unregister_language("words")
        unregister_language("numbers")
        for word in _REGISTERED:
            unregister_predicate(word.word)


def _ref(text):
    return parse_binding(f"s in {text}")[1].pieces[0]


@pytest.mark.parametrize("text,canonical", [
    ('L[words, begins with ("ab")]', 'L[words, begins with ("ab")]'),
    ('L[words, begins with("ab")]', 'L[words, begins with ("ab")]'),
    ('L[words, beginsWith("ab")]', 'L[words, begins with ("ab")]'),
    ('L[words, begins_with("ab")]', 'L[words, begins with ("ab")]'),
    ('L[words, BeginsWith ("ab")]', 'L[words, begins with ("ab")]'),
    ('L[words, Begins With("ab")]', 'L[words, begins with ("ab")]'),
    ('L[words, beginswith("ab")]', 'L[words, begins with ("ab")]'),
    ('L[words, not begins with ("ab")]', 'L[words, not begins with ("ab")]'),
    ('L[words, not beginsWith("ab")]', 'L[words, not begins with ("ab")]'),
    ('L[words, ^= "ab"]', 'L[words, begins with ("ab")]'),
    ('L[words, *= "b"]', 'L[words, has ("b")]'),
    ('L[words, in shape("a+")]', 'L[words, fits (shape("a+"))]'),
    ('L[words, not in shape("a+")]', 'L[words, not fits (shape("a+"))]'),
    ('L[words, == "ab"]', 'L[words, fits ("ab")]'),
    ('L[words, != "ab"]', 'L[words, not fits ("ab")]'),
    ("L[words, fits ('ab')]", 'L[words, fits ("ab")]'),
    ('L[words, inside "a"]', 'L[words, inside ("a")]'),
    ('L[words, inside ("a", "b")]', 'L[words, inside ("a", "b")]'),
    ('L[words, has ("a|b"), has ("x, y")]', 'L[words, has ("a|b"), has ("x, y")]'),
    ('L[words, has ("b"), begins with ("a"), len <= 8]',
     'L[words, len <= 8, begins with ("a"), has ("b")]'),
    ('L[words, has (r"\\{b}")]', 'L[words, has (r"\\{b}")]'),
])
def test_every_spelling_of_a_predicate_renders_as_the_words(text, canonical):
    ref = _ref(text)
    assert repr(ref) == canonical
    assert repr(_ref(canonical)) == canonical


def test_a_predicate_is_a_word_its_arguments_and_whether_it_is_negated():
    ref = _ref('L[words, len <= 8, not begins with ("ab")]')
    assert ref.name == "words"
    assert [key for key, _ in ref.refinements] == ["len"]
    assert ref.predicates == (Predicate("begins with", ('"ab"',), True),)


def test_a_measure_comparison_reads_as_it_always_has():
    ref = _ref("L[words, len <= 8, depth in [1, 6]]")
    assert repr(ref) == "L[words, depth in [1, 6], len <= 8]"
    assert ref.predicates == ()


def test_a_claim_over_a_predicate_language_round_trips_with_one_fingerprint():
    spellings = ['for s in L[words, ^= "ab"], f(s) == s',
                 'for s in L[words, beginsWith("ab")], f(s) == s',
                 'for s in L[words, begins with ("ab")], f(s) == s']
    prints = {fingerprint_text(claim(t)) for t in spellings}
    assert prints == {'for s in L[words, begins with ("ab")], f(s) = s'}
    for unicode in (False, True):
        rendered = render_claim_text(claim(spellings[0]), unicode=unicode)
        assert 'L[words, begins with ("ab")]' in rendered
        assert fingerprint_text(claim(rendered)) in prints


def test_the_registered_word_decides_membership():
    language = resolve_language(_ref('L[words, begins with ("ab"), not has ("x")]'))
    assert not language_problems(language)
    assert language.contains("abc") and not language.contains("abx")
    assert not language.contains("ba") and not language.contains("ab1")


def test_a_word_reads_several_arguments_by_the_kind_of_its_base_language():
    assert resolve_language(_ref('L[words, inside ("a", "b")]')).contains("bz")
    assert not resolve_language(_ref('L[words, inside ("a", "b")]')).contains("zz")
    assert resolve_language(_ref('L[numbers, inside ("a", "b")]')).contains("12")
    assert not resolve_language(_ref('L[numbers, inside ("a", "b")]')).contains("123")


def test_the_word_owns_its_argument_text_and_may_refuse_an_operator():
    with pytest.raises(InvalidDomain, match=r"a member is not equal to a shape"):
        _ref('L[words, == shape("a")]')


def test_an_object_alone_as_a_refinement_is_refused_with_the_word_that_reads_in():
    with pytest.raises(InvalidDomain) as raised:
        _ref(f"L[words, {_HERE}.SHAPE]")
    assert str(raised.value) == (
        f"'L[words, {_HERE}.SHAPE]': the object '{_HERE}.SHAPE' alone is not a "
        f"refinement. Did you mean `fits ({_HERE}.SHAPE)`?")
    assert repr(_ref(f"L[words, fits ({_HERE}.SHAPE)]")) == f"L[words, fits ({_HERE}.SHAPE)]"
    assert repr(_ref(f"L[words, in {_HERE}.SHAPE]")) == f"L[words, fits ({_HERE}.SHAPE)]"


def test_an_object_named_as_a_language_parses_as_written_and_imports_nothing():
    import sys
    ref = _ref("L[no_such_package_anywhere.text.SLUG]")
    assert repr(ref) == "L[no_such_package_anywhere.text.SLUG]"
    assert ref.predicates == ()
    assert "no_such_package_anywhere" not in sys.modules
    assert repr(_ref(f"L[{_HERE}.SHAPE]")) == f"L[{_HERE}.SHAPE]"


def test_an_object_that_is_no_language_is_refused_at_resolution_with_what_was_meant():
    with pytest.raises(InvalidDomain) as raised:
        resolve_language(_ref(f"L[{_HERE}.SHAPE]"))
    assert str(raised.value).endswith(f"Did you mean L[words, fits ({_HERE}.SHAPE)]?)")
    assert repr(_ref(f"L[words, fits ({_HERE}.SHAPE)]")) == f"L[words, fits ({_HERE}.SHAPE)]"


def test_an_unregistered_word_parses_and_is_refused_at_resolution():
    ref = _ref('L[words, soundsLike("ab")]')
    assert repr(ref) == 'L[words, sounds like ("ab")]'
    with pytest.raises(UnknownRefinement, match="sounds like"):
        resolve_language(ref)


def test_an_operator_no_word_reads_is_refused_naming_the_operator():
    with pytest.raises(InvalidDomain, match=r"no registered predicate reads `\$=`"):
        _ref('L[words, $= "ab"]')


def test_a_keyword_spelling_is_read_only_for_a_word_that_allows_it():
    with pytest.raises(InvalidDomain):
        _ref('L[words, has "a"]')


def test_a_predicate_language_persists_and_loads_back():
    ref = _ref('L[words, len <= 8, not begins with ("ab"), has ("b")]')
    stored = domain_bound_to_json(ref)
    assert stored == {"language": "words", "len": domain_bound_to_json(ref.refinements[0][1]),
                      "predicates": [{"word": "begins with", "arguments": ['"ab"'],
                                      "negated": True},
                                     {"word": "has", "arguments": ['"b"'], "negated": False}]}
    assert domain_bound_from_json(stored) == ref
    plain = _ref("L[words, len <= 8]")
    assert "predicates" not in domain_bound_to_json(plain)
    assert isinstance(domain_bound_from_json(domain_bound_to_json(plain)), LanguageRef)


def test_core_registers_no_predicate_word():
    for word in _REGISTERED:
        unregister_predicate(word.word)
    assert not [w for w in languages.predicate_words() if w.word in
                {r.word for r in _REGISTERED}]


def _only_words(language):
    return language.kind == "string"


_COUNTED = PredicateWord(
    "ends in", lambda language, args, negated: Kept(
        language, lambda s: s.endswith(_unquoted(args[0])) != negated),
    sugar=("$=",), applies=_only_words, kinds=("text", "a file name"),
    examples={"text": 'L[words, ends in ("b")]'},
    suggest=lambda base, args: f"L[words, ends in ({', '.join(args)})]")


@pytest.fixture
def counted():
    register_predicate(_COUNTED)
    try:
        yield
    finally:
        unregister_predicate(_COUNTED.word)


def test_every_operator_survives_the_claim_grammar(counted):
    for text, said in (('L[words, ^= "ab"]', 'begins with ("ab")'),
                       ('L[words, $= "ab"]', 'ends in ("ab")'),
                       ('L[words, *= "ab"]', 'has ("ab")'),
                       ('L[words, in shape("a")]', 'fits (shape("a"))'),
                       ('L[words, not in shape("a")]', 'not fits (shape("a"))'),
                       ('L[words, != "ab"]', 'not fits ("ab")')):
        rendered = render_claim_text(claim(f"for s in {text}, f(s) == s"), unicode=False)
        assert rendered == f"for s in L[words, {said}], f(s) = s"


def test_a_word_with_no_meaning_over_the_base_is_refused_in_three_parts(counted):
    with pytest.raises(MeaninglessPredicate) as raised:
        resolve_language(_ref('L[numbers, ends in ("1")]'))
    assert str(raised.value) == (
        "L[numbers, ends in (\"1\")]: 'ends in' has no meaning for L[numbers]: "
        "it applies to text or a file name, for example L[words, ends in (\"b\")]. "
        "Did you mean L[words, ends in (\"1\")]?")


def test_a_word_with_a_meaning_over_the_base_is_served(counted):
    assert resolve_language(_ref('L[words, ends in ("b")]')).contains("ab")


@pytest.mark.parametrize("text,suggestion", [
    ('L[words, beginwith ("ab")]', 'L[words, begins with ("ab")]'),
    ('L[words, len <= 8, not hsa ("b")]', 'L[words, len <= 8, not has ("b")]'),
    ("L[words, fitz ('ab')]", 'L[words, fits ("ab")]'),
])
def test_an_unknown_word_near_a_registered_one_is_offered_as_it(text, suggestion):
    with pytest.raises(UnknownPredicate) as raised:
        resolve_language(_ref(text))
    assert raised.value.suggestion == suggestion
    assert str(raised.value).endswith(f"is not a registered predicate. Did you mean {suggestion}?")


def test_an_unknown_word_far_from_every_registered_one_lists_the_words():
    with pytest.raises(UnknownPredicate) as raised:
        resolve_language(_ref('L[words, rhymes with ("ab")]'))
    assert raised.value.suggestion is None
    assert "known predicates are begins with, fits, has, inside" in str(raised.value)


def test_every_suggestion_and_example_an_error_prints_renders_back_to_itself(counted):
    printed = []
    for text in ('L[numbers, ends in ("1")]', 'L[words, beginwith ("ab")]',
                 'L[words, len <= 8, not hsa ("b")]', "L[words, fitz ('ab')]"):
        with pytest.raises(InvalidDomain) as raised:
            resolve_language(_ref(text))
        printed.extend(t for t in (raised.value.suggestion,
                                   getattr(raised.value, "example", None)) if t)
    assert len(printed) == 5
    for text in printed:
        assert repr(_ref(text)) == text
        resolve_language(_ref(text))


_DIALECTS = {"py": "python", "python": "python", "js": "ecma", "ecma": "ecma"}


def _shaped_arguments(args, sugar):
    """Writes `shape(<pattern>, <dialect>, <flags sorted>)`, the dialect
    always stated."""
    from mathema.domain import read_call
    read = read_call(args[0])
    if read is None or read[0] != "shape":
        return args
    _, pattern, words, _ = read
    dialects = [_DIALECTS[w] for w in words if w in _DIALECTS] or ["python"]
    flags = sorted(w for w in words if w not in _DIALECTS)
    return (f"shape({', '.join([pattern, dialects[0], *flags])})",)


_SHAPED = PredicateWord("shaped like", lambda language, args, negated: language,
                        arguments=_shaped_arguments)


@pytest.mark.parametrize("written,canonical", [
    ('shape(r"[a-z]+")', 'shape(r"[a-z]+", python)'),
    ('shape(r"[a-z]+", py)', 'shape(r"[a-z]+", python)'),
    ('Shape(r"[a-z]+", js, ignoreCase)', 'shape(r"[a-z]+", ecma, ignore case)'),
    ('shape(r"a,b|c", Multi_Line, Ignore Case)', 'shape(r"a,b|c", python, ignore case, multi line)'),
    ('shape(app.text.SLUG, dot_all)', 'shape(app.text.SLUG, python, dot all)'),
    ('shape(r"[a-z]+", python, ignore case)', 'shape(r"[a-z]+", python, ignore case)'),
])
def test_a_call_inside_an_argument_is_written_by_the_word_that_owns_it(written, canonical):
    register_predicate(_SHAPED)
    try:
        ref = _ref(f"L[words, shaped like ({written})]")
        assert repr(ref) == f"L[words, shaped like ({canonical})]"
        assert repr(_ref(repr(ref))) == repr(ref)
        rendered = render_claim_text(claim(f"for s in L[words, shapedLike({written})], f(s) == s"),
                                     unicode=False)
        assert rendered == f"for s in L[words, shaped like ({canonical})], f(s) = s"
    finally:
        unregister_predicate(_SHAPED.word)


def test_a_call_with_anything_but_a_first_argument_and_words_is_not_read():
    from mathema.domain import read_call
    assert read_call('shape(r"a", flags=2)') is None
    assert read_call('shape(1 + 2)') is None
    assert read_call('shape(r"a", other("b"))') is None
    assert read_call('re(r"[a-z]+", python, ignoreCase)') == (
        "re", 'r"[a-z]+"', ("python", "ignore case"), ())
