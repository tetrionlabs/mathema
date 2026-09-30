# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The lexicon's `missing` section: one policy row per behaviour and
kind, the member and premise forms, the traps and the gates, each
checked against the example function that demonstrates it, with the
verdict pinned."""
import pytest

from mathema import lexicon
from mathema.conjecture import check_conjectures, claim

pytest.importorskip("pandas")
pytest.importorskip("polars")

VERDICTS = {
    "missing_propagates": "holds",
    "missing_drops": "holds",
    "missing_trap_silent_drop": "falsified",
    "missing_raises": "proven",
    "missing_converts": "holds",
    "missing_introduces": "holds",
    "missing_introduces_by_shape": "holds",
    "absent_raises": "holds",
    "absent_drops": "proven",
    "absent_propagates": "holds",
    "absent_converts": "holds",
    "missing_member_null": "holds",
    "missing_member_nan": "holds",
    "missing_class_row_contradicted": "falsified",
    "missing_premise_values_remain": "holds",
    "missing_premise_no_values": "holds",
    "missing_premise_all_na_raises": "holds",
    "missing_member_defined": "holds",
    "missing_trap_comparison": "holds",
    "missing_predicate_sugar": "holds",
    "absent_none_spelling": "holds",
    "is_missing_safe_gate": "proven",
    "is_missing_safe_gate_falsified": "falsified",
    "is_absent_safe_gate": "proven",
    "is_absent_safe_gate_falsified": "falsified",
    "is_empty_safe_hole": "falsified",
    "is_empty_safe_identity": "proven",
}


def _function_for(key):
    return next(fn for fn, keys in lexicon.EXAMPLE_FUNCTIONS.values() if key in keys)


#: each falsified row with what the record names as the witness: a trap
#: shown, not only a verdict
WITNESSES = {
    "missing_trap_silent_drop": "rate = nan: f returned 1.0",
    "missing_class_row_contradicted": "positions = [null]: f raised TypeError",
    "is_missing_safe_gate_falsified": "positions = [null]: f raised TypeError",
    "is_absent_safe_gate_falsified": "score = None: f raised TypeError",
    "is_empty_safe_hole": "returns = [] (an empty numpy.ndarray): f returned nan for "
                          "the empty input; raise, or return a value",
}


@pytest.mark.parametrize("key", sorted(WITNESSES))
def test_a_falsified_row_names_its_witness(key):
    (row,) = check_conjectures(_function_for(key), [claim(lexicon.LEXICON[key])])
    assert row.counterexample.startswith(WITNESSES[key]), row.counterexample


@pytest.mark.parametrize("key, wrong", [
    ("missing_propagates", "missing(f, variance) drops"),
    ("missing_drops", "missing(f, rate) raises"),
    ("missing_raises", "missing(f, ratio) propagates"),
    ("missing_converts", "missing(f, price) propagates"),
    ("absent_drops", "absent(f, fx_rate) raises"),
    ("absent_converts", "absent(f, price) propagates"),
    ("missing_member_null", "missing(f, positions, null) propagates"),
])
def test_the_wrong_word_on_the_same_function_is_falsified(key, wrong):
    """The negative control: each holding row's function refutes a
    different word for the same case."""
    (row,) = check_conjectures(_function_for(key), [claim(wrong)])
    assert row.verdict == "falsified", (wrong, row.verdict, row.note)


def test_every_row_of_the_section_is_pinned():
    assert set(VERDICTS) == set(lexicon.SECTIONS["missing"])


@pytest.mark.parametrize("key", sorted(VERDICTS))
def test_the_row_reaches_its_verdict_on_its_function(key):
    (row,) = check_conjectures(_function_for(key), [claim(lexicon.LEXICON[key])])
    assert row.verdict == VERDICTS[key], (key, row.verdict, row.note)


def test_the_section_is_found_by_its_words():
    for word in ("absent", "missing", "nan", "null", "NA", "NaT", "hole", "optional",
                 "skipna", "propagates", "drops", "raises", "converts",
                 "introduces", "axiom"):
        assert any(word in tags for key, tags in lexicon.TAGS.items()
                   if key in VERDICTS), word
