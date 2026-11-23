# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When the solver finds a member holding a surrogate pair and the second
search, for a member holding none, gets no answer, the member is given
with a reason that says no pair-free member was found within the
budget, and never that every member holds a pair, which only a search
with an answer can show."""
import pytest

from mathema.koine import record_membership, solver_question

pytest.importorskip("z3")

#: a high surrogate followed by a low one, two code units
PAIR = chr(0xD83D) + chr(0xDE00)


def _text(*codes):
    return {"op": "text", "language": {"op": "literal", "codes": list(codes)}}


def test_no_answer_to_the_pair_free_search_is_not_read_as_every_member_holding_a_pair(
        monkeypatch):
    import z3
    calls = []
    checked = solver_question._checked

    def first_then_no_answer(z3_, solver, timeout_ms):
        calls.append(1)
        return checked(z3_, solver, timeout_ms) if len(calls) == 1 else z3.unknown
    monkeypatch.setattr(solver_question, "_checked", first_then_no_answer)
    # the first member found is read as holding a pair, so the second
    # search runs, and it gets no answer
    monkeypatch.setattr(solver_question, "_holds_a_pair", lambda value: True)
    document = record_membership.membership_document(_text(97))
    found = solver_question.find_member([document], [], timeout_ms=500)
    assert len(calls) == 2
    assert found.status == "member" and found.member == "a"
    assert solver_question.ONLY_PAIRS not in found.reason
    assert "no member without a surrogate pair was found" in found.reason


def test_a_pair_free_search_that_finds_none_says_every_member_holds_a_pair():
    found = solver_question.find_member(
        [record_membership.membership_document(_text(0xD83D, 0xDE00))], [])
    assert found.status == "member" and found.member == PAIR
    assert found.reason == solver_question.ONLY_PAIRS
