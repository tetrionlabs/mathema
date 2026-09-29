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
    "missing_raises": "proven",
    "missing_converts": "holds",
    "missing_introduces": "holds",
    "absent_raises": "holds",
    "absent_drops": "proven",
    "absent_propagates": "holds",
    "absent_converts": "holds",
    "missing_member_null": "holds",
    "missing_member_nan": "holds",
    "missing_premise_values_remain": "holds",
    "missing_premise_no_values": "holds",
    "missing_member_defined": "holds",
    "missing_trap_comparison": "holds",
    "missing_predicate_sugar": "holds",
    "absent_none_spelling": "holds",
    "is_missing_safe_gate": "proven",
    "is_absent_safe_gate": "proven",
}


def _function_for(key):
    return next(fn for fn, keys in lexicon.EXAMPLE_FUNCTIONS.values() if key in keys)


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
