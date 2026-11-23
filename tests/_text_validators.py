# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Small pattern validators and the languages their claims range over,
for the tests of the validator route.

The definitions are written by hand: a predicate word made for these
tests, `spelled as`, reads the bound method `PAT.match` or
`PAT.fullmatch` of a pattern in `PATTERNS` (each pattern under one
mode) and states the whole-text
language that call accepts, met with the parameter's language. No
pattern dialect is compiled here.

`enumerated` and `replays` are the solver-free cross-check of a
verdict: every text up to a length over a small alphabet, placed by
core's derivative matcher, run through the validator."""
import itertools
import json
import re
import warnings

from mathema import regular
from mathema.conjecture import check_conjectures, claim
from mathema.languages import (PredicateWord, StringLanguage, register_language,
                               register_predicate, unregister_language, unregister_predicate)

from _elsewhere_errors import ElsewhereError

ALL = [[0, 0x10FFFF]]


def exact(node):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node}


def chars(*ranges):
    return {"op": "chars", "ranges": [[ord(lo), ord(hi)] for lo, hi in ranges]}


def lit(text):
    return {"op": "literal", "codes": [ord(c) for c in text]}


def rep(node, lo, hi):
    return {"op": "repeat", "arg": node, "min": lo, "max": hi}


def cat(*nodes):
    return {"op": "concat", "args": list(nodes)}


ANY = rep({"op": "chars", "ranges": ALL}, 0, None)
DIGIT = chars(("0", "9"))
ALNUM = rep(chars(("0", "9"), ("A", "Z"), ("a", "z")), 0, None)
SLUG_NODE = cat(chars(("a", "c")), rep(chars(("-", "-"), ("a", "c")), 0, 3))

SLUG = re.compile(r"[a-c][a-c-]{0,3}\Z")
SLUG_DOLLAR = re.compile(r"[a-c][a-c-]{0,3}$")
PERSON = re.compile(r"p:[0-9]{2}")

#: the whole-text language each bound method accepts, by pattern and mode
PATTERNS = {
    (SLUG.pattern, "match"): SLUG_NODE,
    (SLUG_DOLLAR.pattern, "match"): cat(SLUG_NODE, rep(lit("\n"), 0, 1)),
    (PERSON.pattern, "fullmatch"): cat(lit("p:"), rep(DIGIT, 2, 2)),
}
_COMPILED = {p.pattern: p for p in (SLUG, SLUG_DOLLAR, PERSON)}


class Defined:
    """A language of strings stating `definition` in its persisted
    form, membership decided by `accepts`."""

    def __init__(self, name, accepts, definition):
        self._base = StringLanguage(name, char_ok=lambda c: True, pool="abc-:01\n")
        self.name, self._accepts, self._definition = name, accepts, definition

    def __getattr__(self, attr):
        return getattr(self._base, attr)

    def contains(self, value):
        return isinstance(value, str) and bool(self._accepts(value))

    def to_json(self):
        return {"name": self.name, "term": self._definition}


def _reads(callee):
    pattern = getattr(callee, "__self__", None)
    if not isinstance(pattern, re.Pattern):
        return None
    if (pattern.pattern, getattr(callee, "__name__", "")) not in PATTERNS:
        return None
    return (json.dumps(pattern.pattern),)


def _spelled_as(language, arguments, negated):
    pattern = _COMPILED[json.loads(arguments[0])]
    (mode,) = [m for p, m in PATTERNS if p == pattern.pattern]
    node = PATTERNS[(pattern.pattern, mode)]
    base = language.to_json()["term"]["language"]
    call = getattr(pattern, mode)
    return Defined(f"{language.name}, spelled as ({arguments[0]})",
                   lambda s: language.contains(s) and (call(s) is not None) != negated,
                   exact({"op": "inter", "args": [base, node]}))


SPELLED_AS = PredicateWord("spelled as", _spelled_as, reads_call=_reads)

LANGUAGES = (
    Defined("anytext", lambda s: True, exact(ANY)),
    Defined("alnums", lambda s: all(c.isascii() and c.isalnum() for c in s), exact(ALNUM)),
    Defined("twodigits", lambda s: len(s) == 2 and all("0" <= c <= "9" for c in s),
            exact(rep(DIGIT, 2, 2))),
    Defined("slugs", lambda s: SLUG.match(s) is not None, exact(SLUG_NODE)),
)
#: a language of texts stating no definition
PLAIN = StringLanguage("plaintext", char_ok=lambda c: True, pool="ab")


class _Records(Defined):
    """A language stating a definition whose values are not texts."""
    kind = "object"


#: a language that states a definition and is not a language of texts
RECORDS = _Records("records", lambda s: True, exact(ANY))


def serve():
    register_predicate(SPELLED_AS)
    for language in (*LANGUAGES, PLAIN, RECORDS):
        register_language(language.name, language)


def unserve():
    for language in (*LANGUAGES, PLAIN, RECORDS):
        unregister_language(language.name)
    unregister_predicate(SPELLED_AS.word)


def row(fn, text, route="derive", **kwargs):
    """The first row `check_conjectures` gives for one claim."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return check_conjectures(fn, [claim(text, route=route)], **kwargs)[0]


def on_smt(found):
    """Whether a row was decided on the solver route."""
    return (found.meta or {}).get("mathema.derive_route") == "smt"


def definition(name):
    return next(lang for lang in LANGUAGES if lang.name == name).to_json()["term"]


def enumerated(alphabet, longest):
    """Every text over `alphabet` up to `longest` characters."""
    for n in range(longest + 1):
        for letters in itertools.product(alphabet, repeat=n):
            yield "".join(letters)


def in_language(name, text):
    """Whether core's derivative matcher puts `text` in the language
    `name` defines (no solver)."""
    return regular.contains(definition(name)["language"], text)


def accepted_by(pattern, mode, text):
    """Whether core's derivative matcher puts `text` in the language the
    call `pattern.<mode>` accepts, as `PATTERNS` defines it."""
    return regular.contains(PATTERNS[(pattern.pattern, mode)], text)


# the validators: each a plain module-level function of one text


def check_slug(text):
    if not SLUG.match(text):
        raise ValueError(text)
    return text


def check_slug_dollar(text):
    if not SLUG_DOLLAR.match(text):
        raise ValueError(text)
    return text


def is_person(actor):
    return PERSON.fullmatch(actor) is not None


def is_person_or_empty(actor):
    return PERSON.fullmatch(actor or '') is not None


def check_slug_or_empty(text):
    if not SLUG.match(text or ''):
        raise ValueError(text)
    return text


def check_slug_or_other(text):
    if not SLUG.match(text or 'a'):
        raise ValueError(text)
    return text


def check_slug_empty_or(text):
    if not SLUG.match('' or text):
        raise ValueError(text)
    return text


class SlugError(ValueError):
    """A text that is not a slug."""


class SlugErrorWithCode(ValueError):
    code = 3


class SlugErrorWithInit(ValueError):
    def __init__(self, *args):
        super().__init__(*args)


class SlugErrorTwoBases(ValueError, LookupError):
    pass


class _Meta(type):
    pass


class SlugErrorWithMeta(ValueError, metaclass=_Meta):
    pass


class SlugErrorOfAnError(SlugError):
    pass


def check_slug_own_error(text):
    if not SLUG.match(text):
        raise SlugError(text)
    return text


def check_slug_own_error_or_empty(text):
    if not SLUG.match(text or ''):
        raise SlugError(text)
    return text


def check_slug_error_with_code(text):
    if not SLUG.match(text):
        raise SlugErrorWithCode(text)
    return text


def check_slug_error_with_init(text):
    if not SLUG.match(text):
        raise SlugErrorWithInit(text)
    return text


def check_slug_error_two_bases(text):
    if not SLUG.match(text):
        raise SlugErrorTwoBases(text)
    return text


def check_slug_error_with_meta(text):
    if not SLUG.match(text):
        raise SlugErrorWithMeta(text)
    return text


def check_slug_error_of_an_error(text):
    if not SLUG.match(text):
        raise SlugErrorOfAnError(text)
    return text


def check_slug_error_elsewhere(text):
    if not SLUG.match(text):
        raise ElsewhereError(text)
    return text
