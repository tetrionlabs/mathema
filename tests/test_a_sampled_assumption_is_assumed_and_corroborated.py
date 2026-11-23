# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Agreement on the values tried is not a proof of an assumption. A
definition, a reading of a validator, or `holds only texts`, compared
with a language's own membership on drawn and enumerated values, has
the status `assumed`, and carries a `corroboration` record: how many
values were drawn, compared and skipped, how many disagreed, the seed
and caps of the run, and its outcome, beside its `axiom`: the statement and a stable id.
The proof outline of a row says `assuming <statement> (assumed)` for
each definition, and the printed record says the same under a proven
row. A stored assumption with the earlier status `checked` reads as
`assumed` with no corroboration record."""
import pytest

import _text_validators as T
import mathema
import test_a_definition_check_never_reports_checked_for_what_it_skipped as S
from mathema import domain_relations
from mathema.domain import parse_binding
from mathema.languages import register_language, unregister_language

pytest.importorskip("z3")

COUNTS = {"values drawn", "values compared", "values skipped", "disagreed", "seed",
          "draws", "outcome"}


@pytest.fixture(autouse=True)
def served():
    for language in (S.OVER_AB, S.PARTIAL):
        register_language(language.name, language)
    T.serve()
    try:
        yield
    finally:
        T.unserve()
        for language in (S.OVER_AB, S.PARTIAL):
            unregister_language(language.name)


def _same(s: str) -> str:
    return s


def _checked(name):
    defined = domain_relations.defined_bound(parse_binding(f"s in L[{name}]")[1])
    (text, language, most, least), = defined.read
    return domain_relations.check_definition(text, language, most, least, defined.alphabet)


def test_a_definition_that_agreed_on_every_value_tried_is_assumed():
    result = _checked("overab")
    assert result["status"] == "assumed", result
    record = result["corroboration"]
    assert COUNTS <= set(record), record
    assert record["values compared"] == result["artefact"]["strings compared"] > 0
    assert record["values skipped"] == 0 and record["disagreed"] == 0
    assert record["values drawn"] == record["values compared"] + record["values skipped"]
    assert record["seed"] == result["artefact"]["seed"]
    assert record["draws"] == domain_relations.GUARD_DRAWS
    assert record["outcome"] == "none disagreed"
    assert _checked("overab") == result


def test_the_corroboration_counts_what_was_skipped():
    result = _checked("partial")
    assert result["status"] == "assumed"
    record = result["corroboration"]
    assert record["values skipped"] == result["artefact"]["strings skipped"] > 0
    assert record["values compared"] > 0 and record["disagreed"] == 0


def test_holds_only_texts_is_assumed_with_its_corroboration():
    defined = domain_relations.defined_bound(parse_binding("s in L[overab]")[1])
    (entry,), refuted = domain_relations.check_holds_only_texts(defined)
    assert refuted is None
    assert entry["status"] == "assumed", entry
    record = entry["corroboration"]
    assert record["values compared"] == entry["artefact"]["values run"] > 0
    assert record["disagreed"] == 0 and record["outcome"] == "none disagreed"


def test_the_reading_of_a_validator_is_assumed_with_its_corroboration():
    row = T.row(T.is_person, 'let h be L[twodigits], f("p:" + h) == True')
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    (reading,) = [a for a in row.meta["mathema.assumptions"]["definitions"]
                  if a["statement"].startswith("is_person accepts a text")]
    assert reading["status"] == "assumed", reading
    record = reading["corroboration"]
    assert COUNTS <= set(record), record
    assert record["values compared"] == reading["artefact"]["texts run"] >= 100
    assert record["seed"] == reading["artefact"]["seed"]
    assert record["disagreed"] == 0


def test_no_assumption_of_a_proven_row_is_checked():
    (row,) = mathema.check(_same, claims=["L[overab] subset L[overab]"]).probes
    assert row.verdict == "proven", (row.verdict, row.note)
    assumptions = row.meta["mathema.assumptions"]
    for entry in [*assumptions["definitions"], *assumptions["texts"]]:
        assert entry["status"] == "assumed", entry
        assert entry["corroboration"]["values compared"] > 0
    assert row.sketch.endswith("proven, assuming L[overab] == its stated definition (assumed)")


def test_each_assumption_carries_its_axiom():
    (row,) = mathema.check(_same, claims=["L[overab] subset L[partial]"]).probes
    assumptions = row.meta["mathema.assumptions"]
    entries = [*assumptions["definitions"], *assumptions["texts"]]
    assert len(entries) == 4
    for entry in entries:
        assert entry["axiom"]["statement"] == entry["statement"]
        assert entry["axiom"]["id"] == domain_relations.axiom_id(
            entry["statement"], S.AB_STAR["language"], S.AB_STAR["language"])
        assert entry["axiom"]["id"].startswith("ax-") and len(entry["axiom"]["id"]) == 19
    assert len({entry["axiom"]["id"] for entry in entries}) == 4


def test_the_axiom_id_follows_the_statement_and_the_term():
    star = S.AB_STAR["language"]
    other = S.LOWER_UP_TO_SIX["language"]
    one = domain_relations.axiom_id("L[x] == its stated definition", star, star)
    assert one == domain_relations.axiom_id("L[x] == its stated definition", star, star)
    assert one != domain_relations.axiom_id("L[y] == its stated definition", star, star)
    assert one != domain_relations.axiom_id("L[x] == its stated definition", other, other)


def test_a_proven_row_prints_each_definition_it_assumes():
    record = mathema.check(_same, claims=["L[overab] subset L[partial]"])
    lines = str(record).split("\n")[1:]
    assert lines == [
        "  proven    L_overab_subset_L_partial: L[overab] subset L[partial]",
        "           assuming L[overab] == its stated definition (assumed)",
        "           assuming L[partial] == its stated definition (assumed)"], lines


def test_a_stored_assumption_with_the_status_checked_reads_as_assumed():
    record = mathema.check(_same, claims=["L[overab] subset L[overab]"])
    (row,) = record.probes
    stored = {"language": "L[overab]", "statement": "L[overab] == its stated definition",
              "status": "checked", "artefact": {"seed": 1, "strings compared": 9}}
    row.meta = {**row.meta, "mathema.assumptions": {"standard": {}, "definitions": [stored],
                                                    "texts": []}}
    printed = str(record)
    assert "assuming L[overab] == its stated definition (assumed)" in printed, printed
    assert "(checked)" not in printed, printed
    assert domain_relations.assumption_status(stored) == "assumed"
    assert domain_relations.assuming_text([stored]) == \
        "proven, assuming L[overab] == its stated definition (assumed)"
    assert stored["status"] == "checked" and "corroboration" not in stored
