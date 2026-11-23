# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Agreement on the values tried is not a proof of an assumption. A
definition, a reading of a validator, or `holds only texts`, compared
with a language's own membership on drawn and enumerated values, has
the status `assumed`, and carries a `corroboration` record: how many
values were drawn, compared and skipped, how many disagreed, the seed
and caps of the run, and its outcome. A proven row prints each
assumption it rests on with that corroboration beside it. A stored
assumption with the earlier status `checked` reads as `assumed` with no
corroboration record."""
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


def test_a_proven_row_prints_each_sampled_assumption_it_rests_on():
    record = mathema.check(_same, claims=["L[overab] subset L[overab]"])
    printed = str(record)
    assert "proven" in printed, printed
    compared = _checked("overab")["corroboration"]["values compared"]
    assert (f"assuming L[overab] == its stated definition (assumed); corroborated: "
            f"{compared} draws against contains, none disagreed") in printed, printed
    assert "assuming L[overab] holds only texts (assumed); corroborated: " in printed, printed
    assert "(checked)" not in printed, printed


def test_the_printed_corroboration_says_what_was_skipped():
    printed = str(mathema.check(_same, claims=["L[overab] subset L[partial]"]))
    record = _checked("partial")["corroboration"]
    assert (f"assuming L[partial] == its stated definition (assumed); corroborated: "
            f"{record['values compared']} draws against contains, none disagreed, "
            f"{record['values skipped']} skipped where contains raised") in printed, printed


def test_a_stored_assumption_with_the_status_checked_reads_as_assumed():
    record = mathema.check(_same, claims=["L[overab] subset L[overab]"])
    (row,) = record.probes
    stored = {"language": "L[overab]", "statement": "L[overab] == its stated definition",
              "status": "checked", "artefact": {"seed": 1, "strings compared": 9}}
    row.meta = {**row.meta, "mathema.assumptions": {"standard": {}, "definitions": [stored],
                                                    "texts": []}}
    printed = str(record)
    assert "assuming L[overab] == its stated definition (assumed)" in printed, printed
    assert "corroborated" not in printed and "(checked)" not in printed, printed
    assert domain_relations.assumption_status(stored) == "assumed"
    assert domain_relations.assuming_text([stored]) == \
        "proven, assuming L[overab] == its stated definition (assumed)"
    assert domain_relations.corroboration_text(stored) is None
    assert stored["status"] == "checked"
