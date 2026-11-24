# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The notes for an earlier release's stored text say what holds for each.

The quoting note covers records whose old quoting read as another
value, did not read at all, or read as the same value spelled another
way; the negation note covers records whose `not` without its own
parentheses did not read (`f(x) = not (a < x and x < b)`) and ones
where it read as written (`g(not x)`, `-not x`). Each note says only
what is true of all of them: an earlier release spelled the text
another way, the claim is checked again and re-recorded, and nothing
the author wrote changed.
"""
import pytest

from mathema.verify import negation_moved_note, quoting_moved_note


@pytest.mark.parametrize("count, claims", [(1, "1 claim "), (3, "3 claims ")])
def test_the_quoting_note_claims_no_reading_of_the_old_text(count, claims):
    note = quoting_moved_note(count)
    assert note.startswith("note: the stored text of a string literal is corrected in ")
    assert claims in note
    assert "another value" not in note and "did not read" not in note
    assert "a spelling this release does not write" in note
    assert note.endswith("nothing the author wrote changed")


@pytest.mark.parametrize("count, claims", [(1, "1 claim "), (2, "2 claims ")])
def test_the_negation_note_does_not_say_the_old_text_failed_to_read(count, claims):
    note = negation_moved_note(count)
    assert "negated relation" in note and claims in note
    assert "needs" not in note and "read back" not in note
    assert "without parentheses of its own" in note
    assert note.endswith("nothing the author wrote changed")
