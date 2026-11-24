# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The cases the reviews of the validator route and the definition check
probed, and the claim shapes the route proves, each with its claim and
the verdict mathema gives. A `proven` case is cross-checked with no
solver: every short text over a small alphabet that its domain holds,
as core's derivative matcher reads the domain's definition, is run
through the function, and none breaks the claim. A `falsified` case's
counterexample is run and breaks it. A `not proven` case is one where
the function's real behaviour, or a definition wrong on a string the
claim names, contradicts what a proof would say."""
import ast
import re

import pytest

import _message_validators as M
import _text_validators as T
import test_a_definition_check_never_reports_checked_for_what_it_skipped as S
from mathema.languages import register_language, unregister_language

pytest.importorskip("z3")

_B_STAR = re.compile(r"b*")


def check_ude(s):
    if not _B_STAR.fullmatch(s):
        raise UnicodeDecodeError(s)
    return s


def _returns_itself(fn, text):
    try:
        return fn(text) == text
    except Exception:
        return False


def _refuses(fn, text, exc=ValueError):
    try:
        fn(text)
    except exc:
        return True
    except Exception:
        return False
    return False


def _equals(fn, text, value):
    try:
        return fn(text) is value
    except Exception:
        return False


def _defined_then_itself(fn, text):
    try:
        returned = fn(text)
    except Exception:
        return True
    return returned == text


#: (id, function, claim, expected, the language enumerated, the claim's
#: truth at one text of it); expected is a verdict or "not proven"
CASES = [
    ("defined_slug", T.check_slug,
     "for text in L[anytext], assuming f is defined, f(text) == text", "proven",
     "anytext", lambda t: _defined_then_itself(T.check_slug, t)),
    ("defined_dollar_slug", T.check_slug_dollar,
     "for text in L[anytext], assuming f is defined, f(text) == text", "proven",
     "anytext", lambda t: _defined_then_itself(T.check_slug_dollar, t)),
    ("slug_on_every_text", T.check_slug,
     "for text in L[anytext], f(text) == text", "falsified",
     "anytext", lambda t: _returns_itself(T.check_slug, t)),
    ("or_empty_no_person", T.is_person_or_empty,
     "for actor in L[alnums], f(actor) == False", "proven",
     "alnums", lambda t: _equals(T.is_person_or_empty, t, False)),
    ("package_error_newline", T.check_slug_own_error,
     'for text in L[anytext], raises(f(text + "\\n"), ValueError)', "proven",
     "anytext", lambda t: _refuses(T.check_slug_own_error, t + "\n")),
    ("let_variable_suffix", T.is_person,
     'let h be L[anytext], f("p:" + h + "z") == False', "proven",
     "anytext", lambda t: _equals(T.is_person, "p:" + t + "z", False)),
    ("let_variable_prefix_wrong", T.is_person,
     'let h be L[anytext], f("p:" + h) == False', "falsified",
     "anytext", lambda t: _equals(T.is_person, "p:" + t, False)),
    ("outside_the_variables_language", T.is_person,
     'let h be L[twodigits], f("p:" + h) == True', "proven",
     "twodigits", lambda t: _equals(T.is_person, "p:" + t, True)),
    ("seventh_digit", T.is_person,
     'let h be L[twodigits], f("p:" + h + "0") == True', "falsified",
     "twodigits", lambda t: _equals(T.is_person, "p:" + t + "0", True)),
    ("dollar_newline", T.check_slug_dollar,
     'let h be L[slugs], raises(f("a" + h + "\\n"), ValueError)', "falsified",
     "slugs", lambda t: _refuses(T.check_slug_dollar, "a" + t + "\n")),
    ("message_constant", M.check_name,
     "for name in L[anytext], assuming f is defined, f(name) == name", "proven",
     "anytext", lambda t: _defined_then_itself(M.check_name, t)),
    ("unicode_decode_error_cannot_be_built", check_ude,
     "for s in L[anytext], raises(f(s + \"a\"), UnicodeDecodeError)", "not proven",
     None, None),
    ("literal_the_definition_misses", T.check_slug,
     'L[tail] disjoint {"a-xyz"}', "not proven", None, None),
    ("literal_not_in_a_wrong_definition", T.check_slug,
     '"a-xyz" not in L[tail]', "not proven", None, None),
]


@pytest.fixture(autouse=True)
def served():
    T.serve()
    for language in (S.TAIL, S.OVER_AB, S.PARTIAL):
        register_language(language.name, language)
    try:
        yield
    finally:
        for language in (S.TAIL, S.OVER_AB, S.PARTIAL):
            unregister_language(language.name)
        T.unserve()


def _counterexample(row):
    return ast.literal_eval(row.counterexample.partition(" = ")[2].split(":")[0]
                            if ": raised" in row.counterexample
                            else row.counterexample.partition(" = ")[2])


@pytest.mark.parametrize("name,fn,text,expected,language,holds_at", CASES,
                         ids=[c[0] for c in CASES])
def test_each_review_case_gives_its_verdict(name, fn, text, expected, language, holds_at):
    row = T.row(fn, text, route="best")
    if expected == "not proven":
        assert row.verdict != "proven", (row.verdict, row.sketch)
        return
    assert row.verdict == expected, (row.verdict, row.note, row.sketch)
    if expected == "proven":
        texts = [t for t in T.enumerated("abz-:0\n", 4) if T.in_language(language, t)]
        assert texts, language
        assert all(holds_at(t) for t in texts), name
    else:
        value = row.meta["mathema.counterexample_args"][0] \
            if "mathema.counterexample_args" in (row.meta or {}) else _counterexample(row)
        assert T.in_language(language, value)
        assert not holds_at(value), value


def test_a_definition_skipped_on_a_string_is_assumed_and_shown():
    import mathema

    def same(s: str) -> str:
        return s
    printed = str(mathema.check(same, claims=["L[overab] subset L[partial]"]))
    assert "assuming L[partial] == its stated definition (assumed)" in printed, printed
