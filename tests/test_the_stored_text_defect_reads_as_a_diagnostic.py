# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The defect diagnostic for a claim mathema cannot store has the house
shape: a short summary line naming the function and the claim, the
title, where the claim is stated with the claim and function named,
the quoted line, and one sentence saying what to do."""
from mathema.conjecture import CanonicalTextError
from mathema.verify import canonical_text_defect_message

KEY = "cpkg.mod.tag"
WHERE = {"file": "claims/c.claims.yaml", "line": 5,
         "text": "statement: \"f(x, '}\\\"', t='s') == 1\""}


def _error():
    return CanonicalTextError("x", claim_name="two_literals",
                              problem="it reads back with other string "
                                      "literal values",
                              text="f(x, '}\"\", t=\"s') = 1")


def test_the_summary_line_is_short_and_names_the_defect():
    lines = canonical_text_defect_message(
        KEY, "two_literals", "claims/c.claims.yaml", _error(), WHERE).split("\n")
    assert lines[0] == (f"{KEY}: claim 'two_literals' was not checked: "
                        f"mathema cannot write its stored text, a defect in "
                        f"mathema's rendering of the claim"), lines[0]
    assert lines[1:6] == [
        "", "Error: mathema cannot write this claim's stored text", "",
        f"  on claims/c.claims.yaml line 5, claim two_literals of {KEY}:",
        f"  5:   {WHERE['text']}"], lines


def test_without_a_location_the_claim_and_function_are_named():
    lines = canonical_text_defect_message(
        KEY, "two_literals", None, _error(), None).split("\n")
    assert lines[4] == f"  claim two_literals of {KEY}, in its docstring or claims file:"
