# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A relation between record languages broken only by values holding a
surrogate pair carries its witness with that said in its reason, since
JSON text reads such a pair back as another value; a relation broken by
a value with no pair says nothing of it."""
import pytest

from mathema.koine import record_relations, solver_question

pytest.importorskip("z3")


def _text(*codes):
    return {"kind": "record_language", "version": 1, "exact": True,
            "language": {"op": "text", "language": {"op": "literal", "codes": list(codes)}}}


def test_a_witness_every_breaking_value_forces_to_hold_a_pair_is_said_to():
    decided = record_relations.decide("subset", _text(0xD83D, 0xDE00), _text(0x1F600))
    assert decided.verdict == "falsified"
    assert decided.witness == {"value": "\ud83d\ude00"}
    assert solver_question.ONLY_PAIRS in decided.reason


def test_a_witness_with_no_pair_says_nothing_of_pairs():
    decided = record_relations.decide("subset", _text(0x1F600), _text(0xD83D, 0xDE00))
    assert decided.verdict == "falsified"
    assert decided.witness == {"value": "\U0001f600"}
    assert "surrogate" not in decided.reason
