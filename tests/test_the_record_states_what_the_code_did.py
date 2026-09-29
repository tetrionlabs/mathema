# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""At every missing input it executed, the record states what the code
did, per parameter and member: `meta["mathema.missing"]["executed"]`
maps each parameter to `{member: outcome}`, the outcome one of
`propagates (<value>)`, `raised <Exception>`, `returned <value>` or
`replaced`; `behaviour` names the one behaviour per member (or
`mixed`). A note says it in words only where a verdict needs it."""
import math

from mathema.conjecture import check_conjectures, claim
from mathema.probing import ExecutedMissing, execution_outcome, executed_words

NAN = float("nan")


def plus_one(x: float) -> float:
    return x + 1.0


def doubled(x: "float | None") -> float:
    return x * 2.0


def zero_for_none(x: "float | None") -> float:
    return 0.0 if x is None else x


def _executed(row):
    return ((row.meta or {}).get("mathema.missing") or {}).get("executed")


def test_an_outcome_is_named_in_the_record_vocabulary():
    assert execution_outcome(value=NAN) == "propagates (nan)"
    assert execution_outcome(value=None) == "propagates (None)"
    assert execution_outcome(raised="TypeError") == "raised TypeError"
    assert execution_outcome(value=0.0) == "returned 0.0"
    assert execution_outcome(value=[1.0, NAN]) == "propagates ([1.0, nan])"
    assert execution_outcome(value=[1.0, 0.0], holed_input=True) == "replaced"


def test_a_missing_input_is_recorded_under_its_member():
    record = ExecutedMissing()
    record.add_call({"x": None}, raised="TypeError")
    record.add_call({"xs": [1.0, NAN, None]}, output=NAN)
    record.add_call({"y": 0.5}, output=1.0)
    assert record.meta()["executed"] == {
        "x": {"None": "raised TypeError"},
        "xs": {"nan": "propagates (nan)", "null": "propagates (nan)"}}


def test_the_record_keeps_the_first_outcome_per_member():
    record = ExecutedMissing()
    record.add_call({"x": NAN, "y": 1.0}, output=NAN)
    record.add_call({"x": math.nan}, raised="ValueError")
    record.add_call({"x": None}, raised="TypeError")
    meta = record.meta()
    assert meta["executed"] == {"x": {"nan": "propagates (nan)",
                                      "None": "raised TypeError"}}
    assert meta["behaviour"] == {"x": {"nan": "mixed", "None": "raises"}}
    assert meta["mixed"] == {"x": {"nan": {"propagates": "x=nan, y=1.0",
                                           "raises": "x=nan"}}}


def test_the_words_are_a_sentence_per_parameter_and_member():
    assert executed_words({"x": {"nan": "propagates (nan)",
                                 "None": "raised TypeError"}}) \
        == "at x=nan the function returned nan; at x=None the function raised TypeError"


def test_a_proof_over_listed_sentinels_states_what_the_code_did():
    (row,) = check_conjectures(
        doubled, [claim("for x in {1.0, None, nan}, f(x) == 2*x")])
    assert row.verdict == "proven", (row.verdict, row.note)
    assert _executed(row) == {"x": {"None": "raised TypeError",
                                    "nan": "propagates (nan)"}}
    assert "raised" not in (row.note or "")


def test_a_value_returned_at_a_missing_input_is_stated():
    (row,) = check_conjectures(
        zero_for_none, [claim("for x in {1.0, None}, f(x) >= 0")])
    assert _executed(row) == {"x": {"None": "returned 0.0"}}


def test_a_propagated_hole_is_stated_on_the_proven_row():
    (row,) = check_conjectures(
        plus_one, [claim("for x in {1.0, nan}, f(x) == x + 1")])
    assert row.verdict == "proven"
    assert _executed(row) == {"x": {"nan": "propagates (nan)"}}


def test_a_row_that_executed_no_missing_input_states_none():
    (row,) = check_conjectures(
        plus_one, [claim("for x in {1.0, 2.0}, f(x) == x + 1")])
    assert _executed(row) is None
