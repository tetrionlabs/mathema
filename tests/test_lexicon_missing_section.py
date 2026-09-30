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
    "is_missing_safe_gate": "holds",
    "is_missing_safe_gate_falsified": "falsified",
    "is_absent_safe_gate": "holds",
    "is_absent_safe_gate_falsified": "falsified",
    "is_empty_safe_hole": "falsified",
    "is_empty_safe_identity": "proven",
    "absent_field_raises": "holds",
    "is_absent_safe_field": "falsified",
    "absent_key_left_out": "holds",
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
    "is_absent_safe_field": "trade.memo = null (absent): f raised TypeError",
}


@pytest.mark.parametrize("key", sorted(WITNESSES))
def test_a_falsified_row_names_its_witness(key):
    (row,) = check_conjectures(_function_for(key), [claim(lexicon.LEXICON[key])])
    assert row.counterexample.startswith(WITNESSES[key]), row.counterexample


def side_or_blank(order: dict) -> str:
    """A side in capitals, and a blank for an order with no side key."""
    return order["side"].upper() if "side" in order else ""


#: the negative control of every row: the same case on the same function
#: (or the row's claim on the function that fails it) lands on the other
#: verdict. `(key, function or None for the row's own, claims, verdicts)`;
#: the last claim is the one judged.
CONTROLS = [
    ("missing_propagates", None, ["missing(f, variance) drops"], ("falsified",)),
    ("missing_drops", None, ["missing(f, rate) raises"], ("falsified",)),
    ("missing_trap_silent_drop", None, ["missing(f, rate) drops"], ("holds", "proven")),
    ("missing_raises", None, ["missing(f, ratio) propagates"], ("falsified",)),
    ("missing_converts", None, ["missing(f, price) propagates"], ("falsified",)),
    ("missing_introduces", None,
     ["assuming count(weights) >= 1, missing(f, weights) propagates"], ("falsified",)),
    ("missing_introduces_by_shape", None,
     ["assuming count(prices) >= 1, missing(f, prices) propagates"], ("falsified",)),
    ("absent_raises", None, ["absent(f, score) drops"], ("falsified",)),
    ("absent_drops", None, ["absent(f, fx_rate) raises"], ("falsified",)),
    ("absent_propagates", None, ["absent(f, amount) raises"], ("falsified",)),
    ("absent_converts", None, ["absent(f, price) propagates"], ("falsified",)),
    ("missing_member_null", None, ["missing(f, positions, null) propagates"],
     ("falsified",)),
    ("missing_member_nan", None, ["missing(f, positions, nan) raises"], ("falsified",)),
    ("missing_class_row_contradicted", None, ["missing(f, positions, nan) propagates"],
     ("holds", "proven")),
    ("missing_premise_values_remain", None,
     ["assuming count(xs) >= 1, missing(f, xs) propagates"], ("falsified",)),
    ("missing_premise_no_values", None,
     ["assuming count(xs) == 0, missing(f, xs, nan) drops"], ("falsified",)),
    ("missing_premise_all_na_raises", None,
     ["assuming count(xs) == 0, missing(f, xs, NA) propagates"], ("falsified",)),
    ("missing_member_defined", None,
     ["assuming count(xs) >= 1, missing(f, xs, null) propagates"], ("falsified",)),
    ("missing_trap_comparison", None, ["missing(f, score) propagates"], ("falsified",)),
    ("missing_predicate_sugar", None, ["missing_drops(f, variance)"], ("falsified",)),
    ("absent_none_spelling", None, ["None(f, score) drops"], ("falsified",)),
    ("is_missing_safe_gate", lexicon.total_exposure, ["is_missing_safe(f)"],
     ("falsified",)),
    ("is_missing_safe_gate_falsified", None,
     ["missing(f, positions, null) raises(TypeError)", "is_missing_safe(f)"],
     ("holds", "proven")),
    ("is_absent_safe_gate", lexicon.risk_label, ["is_absent_safe(f)"], ("falsified",)),
    ("is_absent_safe_gate_falsified", None,
     ["absent(f, score) raises(TypeError)", "is_absent_safe(f)"], ("holds", "proven")),
    ("is_empty_safe_hole", lexicon.session_volume, ["is_empty_safe(volumes)"],
     ("proven",)),
    ("is_empty_safe_identity", lexicon.average_return, ["is_empty_safe(returns)"],
     ("falsified",)),
    ("absent_field_raises", None, ["absent(f, trade.memo) drops"], ("falsified",)),
    ("is_absent_safe_field", None,
     ["absent(f, trade.memo) raises(TypeError)", "is_absent_safe(f)"], ("proven",)),
    ("absent_key_left_out", side_or_blank,
     ['for order.side in {"buy", "sell"} | {None} \\ {null}, len(f(order)) >= 1'],
     ("falsified",)),
]


def test_every_row_of_the_section_has_a_negative_control():
    assert {key for key, *_ in CONTROLS} == set(lexicon.SECTIONS["missing"])


@pytest.mark.parametrize("key, fn, texts, verdicts", CONTROLS,
                         ids=[c[0] for c in CONTROLS])
def test_the_negative_control_lands_on_the_other_verdict(key, fn, texts, verdicts):
    """The row's verdict is the function's, not the text's: the other
    word on the same function, or the row's claim on the function that
    fails it, lands elsewhere."""
    rows = check_conjectures(fn or _function_for(key), [claim(t) for t in texts])
    row = next(r for r in rows if r.name == claim(texts[-1]).name)
    assert row.verdict in verdicts, (key, texts[-1], row.verdict, row.note)
    assert (row.verdict in ("holds", "proven")) != (VERDICTS[key] in ("holds", "proven"))


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
