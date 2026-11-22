# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function is read as a pattern validator only when its whole
behaviour is one regular-expression match on its parameter, and only
through the objects its names are bound to: a name that merely looks
like `re` or like a compiled pattern is not read."""
import re
import re as regex

import pytest

from mathema._validators import Validator, read_validator

SLUG = re.compile(r"[a-z0-9][a-z0-9-]*$")
PATTERN_TEXT = r"[a-z]+"


class Lookalike:
    """Has the methods of a compiled pattern and is not one."""

    def fullmatch(self, text):
        return text == "ok"

    match = search = fullmatch


FAKE = Lookalike()


def refuses(text):
    """Return text if it is a slug, else raise ValueError."""
    if not SLUG.match(text):
        raise ValueError(text)
    return text


def refuses_is_none(text):
    if SLUG.fullmatch(text) is None:
        raise TypeError
    return text


def predicate_bool(s):
    return bool(SLUG.search(s))


def predicate_is_not_none(s):
    return SLUG.fullmatch(s) is not None


def predicate_is_none(s):
    return SLUG.fullmatch(s) is None


def predicate_not(s):
    return not SLUG.fullmatch(s)


def inline_compile(s):
    return bool(re.compile(r"[a-z]+", re.IGNORECASE | re.DOTALL).fullmatch(s))


def module_call(s):
    return re.fullmatch(r"\d+", s, re.ASCII) is not None


def module_call_aliased(s):
    if not regex.search(PATTERN_TEXT, s):
        raise ValueError(s)
    return s


def uses_lookalike(s):
    return bool(FAKE.fullmatch(s))


def shadows_re(re):
    return bool(re.fullmatch("a", re))


def pattern_parameter(SLUG):  # noqa: N803
    return bool(SLUG.fullmatch(SLUG))


def strips_first(s):
    return bool(SLUG.fullmatch(s.strip()))


def does_more(s):
    if not SLUG.match(s):
        raise ValueError(s)
    return s.lower()


def two_tests(s):
    return bool(SLUG.match(s)) and len(s) < 10


def from_position(s):
    return bool(SLUG.match(s, 1))


def returns_the_match(s):
    return SLUG.match(s)


def computed_flags(s):
    return bool(re.fullmatch("a", s, 2))


def raises_on_a_match(s):
    if SLUG.match(s):
        raise ValueError(s)
    return s


@pytest.mark.parametrize("fn,pattern,flags,mode,raises,negated", [
    (refuses, r"[a-z0-9][a-z0-9-]*$", 0, "match", ValueError, False),
    (refuses_is_none, r"[a-z0-9][a-z0-9-]*$", 0, "fullmatch", TypeError, False),
    (predicate_bool, r"[a-z0-9][a-z0-9-]*$", 0, "search", None, False),
    (predicate_is_not_none, r"[a-z0-9][a-z0-9-]*$", 0, "fullmatch", None, False),
    (predicate_is_none, r"[a-z0-9][a-z0-9-]*$", 0, "fullmatch", None, True),
    (predicate_not, r"[a-z0-9][a-z0-9-]*$", 0, "fullmatch", None, True),
    (inline_compile, r"[a-z]+", re.IGNORECASE | re.DOTALL, "fullmatch", None, False),
    (module_call, r"\d+", re.ASCII, "fullmatch", None, False),
    (module_call_aliased, r"[a-z]+", 0, "search", ValueError, False),
])
def test_a_validator_is_read_with_its_pattern_flags_mode_and_refusal(
        fn, pattern, flags, mode, raises, negated):
    read = read_validator(fn)
    assert isinstance(read, Validator), read
    assert read.pattern.pattern == pattern
    assert read.pattern.flags & ~re.UNICODE == flags
    assert (read.mode, read.raises, read.negated) == (mode, raises, negated)
    assert read.accepts.__self__ is read.pattern


def test_a_named_pattern_is_the_object_the_name_is_bound_to():
    assert read_validator(refuses).pattern is SLUG


@pytest.mark.parametrize("fn,reason", [
    (uses_lookalike, "FAKE is not a compiled re.Pattern"),
    (shadows_re, "'re' is a parameter or is assigned in the function"),
    (pattern_parameter, "'SLUG' is a parameter or is assigned in the function"),
    (strips_first, "the match is on s.strip(), not on the parameter 's' as passed"),
    (does_more, "its body is more than one test of one match on the parameter"),
    (two_tests, "bool(SLUG.match(s)) and len(s) < 10 is not a fullmatch, match or search"),
    (from_position, "SLUG.match(s, 1) passes a position or an end, so it does not match "
                    "the whole parameter"),
    (returns_the_match, "it returns the match object, not its truth"),
    (computed_flags, "the flags 2 are not `re` constants joined by `|`"),
    (raises_on_a_match, "it raises when the match succeeds"),
    (len, "its source is not available"),
])
def test_anything_else_is_declined_with_the_part_that_stopped_it(fn, reason):
    assert read_validator(fn) == reason
