# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The assumptions family: claims over languages of texts, whose proofs
rest on the stated definition of each language. The ground truth
cannot enumerate a language, so each case lists members of it by
construction."""

F = "tests.families.functions.assumptions"
SETUP = f"{F}:serve_languages"
SLUGS = ("a", "b", "c", "ab", "a-b", "c---", "abca", "b-c")
TWO_DIGITS = ("00", "07", "42", "99")
ANY_TEXT = ("", "a", "z", "a-b", "ab\n", "p:12", "ABC")

CASES: list = [
    dict(name="slug.over_slugs", function=f"{F}:check_slug",
         claim="for text in L[slugs], f(text) == text", truth=True,
         points={"text": SLUGS}, setup=SETUP, shows="every slug passes the validator unchanged"),
    dict(name="slug.over_anytext_assuming", function=f"{F}:check_slug",
         claim="for text in L[anytext], assuming f is defined, f(text) == text", truth=True,
         points={"text": ANY_TEXT}, setup=SETUP,
         shows="where the validator returns, it returns its input"),
    dict(name="slug.over_anytext", function=f"{F}:check_slug",
         claim="for text in L[anytext], f(text) == text", truth=False,
         points={"text": ANY_TEXT}, setup=SETUP, shows="the empty text is refused"),
    dict(name="person.two_digits", function=f"{F}:is_person",
         claim='let h be L[twodigits], f("p:" + h) == True', truth=True,
         points={"h": TWO_DIGITS}, setup=SETUP, shows="p: and two digits is a person"),
    dict(name="person.three_digits", function=f"{F}:is_person",
         claim='let h be L[twodigits], f("p:" + h + "0") == True', truth=False,
         points={"h": TWO_DIGITS}, setup=SETUP, shows="a third digit breaks the full match"),
    dict(name="person.anytext", function=f"{F}:is_person",
         claim="for actor in L[anytext], f(actor) == True", truth=False,
         points={"actor": ANY_TEXT}, setup=SETUP, shows="most texts are not persons"),
    dict(name="same.alnums", function=f"{F}:same",
         claim="for text in L[alnums], f(text) == text", truth=True,
         points={"text": ("", "a1", "Z9z")}, setup=SETUP, shows="identity over a language"),
    dict(name="shout.alnums", function=f"{F}:shout",
         claim="for text in L[alnums], f(text) == text", truth=False,
         points={"text": ("", "a1", "Z9z")}, setup=SETUP, shows="upper case changes a1"),
    dict(name="relation.subset", function=f"{F}:same",
         claim="L[twodigits] subset L[anytext]", truth=True, setup=SETUP,
         shows="every two-digit text is a text"),
    dict(name="relation.subset_reversed", function=f"{F}:same",
         claim="L[anytext] subset L[twodigits]", truth=False, setup=SETUP,
         shows="the empty text is not two digits"),
    dict(name="relation.slugs_alnums", function=f"{F}:same",
         claim="L[slugs] subset L[alnums]", truth=False, setup=SETUP,
         shows="a slug may hold a hyphen"),
]
