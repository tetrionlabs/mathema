# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A definition compared with its language's membership on every value
and one on which some value was skipped are both `assumed`, and they
never read alike. The proof outline says `<statement> (assumed)` only
for a definition whose corroboration record shows at least one value
compared, none disagreeing and none skipped; any other says what fell
short inside the brackets (an entry stored with the earlier status
`checked`, which said every value compared agreed and none was skipped,
has no record and reads `(assumed)`). The printed record names the second and not
the first, and the record's own counts tell them apart."""
import itertools

import pytest

import mathema
import test_a_definition_check_never_reports_checked_for_what_it_skipped as S
from mathema import domain_relations
from mathema.languages import register_language, unregister_language

pytest.importorskip("z3")

FULL = "L[overab] == its stated definition"
PARTLY = "L[partial] == its stated definition"


@pytest.fixture(autouse=True)
def served():
    for language in (S.OVER_AB, S.PARTIAL):
        register_language(language.name, language)
    try:
        yield
    finally:
        for language in (S.OVER_AB, S.PARTIAL):
            unregister_language(language.name)


def _same(s: str) -> str:
    return s


@pytest.fixture
def proven():
    record = mathema.check(_same, claims=["L[overab] subset L[partial]"])
    (row,) = record.probes
    assert row.verdict == "proven", (row.verdict, row.note)
    stated = {a["language"]: a for a in row.meta["mathema.assumptions"]["definitions"]}
    return record, row, stated["L[overab]"], stated["L[partial]"]


def test_the_records_tell_a_skipping_check_from_a_full_one(proven):
    _, _, full, partly = proven
    assert full["corroboration"]["values skipped"] == 0
    assert full["corroboration"]["values compared"] > 0
    assert partly["corroboration"]["values skipped"] > 0
    assert domain_relations.agreed_on_every_value(full)
    assert not domain_relations.agreed_on_every_value(partly)


def test_the_outline_tells_a_skipping_check_from_a_full_one(proven):
    _, row, full, partly = proven
    assert domain_relations.assumption_entry_text(full) == f"{FULL} (assumed)"
    record = partly["corroboration"]
    assert domain_relations.assumption_entry_text(partly) == (
        f"{PARTLY} (assumed, {record['values skipped']} of {record['values drawn']} "
        f"values skipped)")
    assert row.sketch.endswith(
        f"proven, assuming {FULL} (assumed), {PARTLY} (assumed, {record['values skipped']} "
        f"of {record['values drawn']} values skipped)"), row.sketch
    assert f"{PARTLY} (assumed)" not in row.sketch


def test_the_printed_record_names_only_the_skipping_check(proven):
    record, _, _, _ = proven
    printed = str(record)
    assert f"assuming {PARTLY} (assumed)" in printed, printed
    assert FULL not in printed, printed


def test_status_alone_does_not_tell_them_apart(proven):
    _, _, full, partly = proven
    assert full["status"] == partly["status"] == "assumed"
    assert domain_relations.assumption_entry_text(full).removeprefix(FULL) != \
        domain_relations.assumption_entry_text(partly).removeprefix(PARTLY)


COUNTS = list(itertools.product(range(4), range(3), range(3)))


@pytest.mark.parametrize("compared,disagreed,skipped", COUNTS)
def test_agreement_is_every_value_compared_and_none_against(compared, disagreed, skipped):
    wanted = compared > 0 and disagreed == 0 and skipped == 0
    assert domain_relations.agreed_on_counts(compared, disagreed, skipped) is wanted
    entry = {"statement": "A", "status": "assumed", "corroboration": {
        "values drawn": compared + skipped, "values compared": compared,
        "values skipped": skipped, "disagreed": disagreed}}
    assert domain_relations.agreed_on_every_value(entry) is wanted
    assert (domain_relations.assumption_entry_text(entry) == "A (assumed)") is wanted
    assert (domain_relations.corroboration_shortfall(compared, disagreed, skipped) == "") \
        is wanted


@pytest.mark.parametrize("entry,said", [
    ({"statement": "A", "status": "assumed"}, "A (assumed, no corroboration record)"),
    ({"statement": "A", "status": "assumed", "unfinished": "the check did not finish"},
     "A (assumed, the comparison did not finish)"),
    ({"statement": "A", "status": "assumed", "corroboration": {
        "values drawn": 0, "values compared": 0, "values skipped": 0, "disagreed": 0}},
     "A (assumed, no value compared)"),
    ({"statement": "A", "status": "assumed", "corroboration": {
        "values drawn": 14, "values compared": 11, "values skipped": 3, "disagreed": 0}},
     "A (assumed, 3 of 14 values skipped)"),
    ({"statement": "A", "status": "assumed", "corroboration": {
        "values drawn": 5, "values compared": 5, "values skipped": 0, "disagreed": 0}},
     "A (assumed)")])
def test_an_entry_says_what_fell_short(entry, said):
    assert domain_relations.assumption_entry_text(entry) == said
    assert domain_relations.assuming_text([entry]) == f"proven, assuming {said}"
    assert (said == "A (assumed)") is domain_relations.agreed_on_every_value(entry)


def test_an_entry_stored_as_checked_keeps_what_that_status_said():
    stored = {"statement": "A", "status": "checked"}
    assert domain_relations.assumption_entry_text(stored) == "A (assumed)"


def test_an_unfinished_comparison_did_not_agree_on_every_value():
    counts = {"values drawn": 5, "values compared": 5, "values skipped": 0, "disagreed": 0}
    entry = {"statement": "A", "status": "assumed", "corroboration": counts}
    assert domain_relations.agreed_on_every_value(entry)
    unfinished = {**entry, "unfinished": "the check of the definition of A did not finish"}
    assert not domain_relations.agreed_on_every_value(unfinished)
    assert not domain_relations.agreed_on_every_value(
        {"statement": "A", "status": "checked", "unfinished": "did not finish"})
    assert domain_relations.assumption_entry_text(unfinished) == \
        "A (assumed, the comparison did not finish)"


class _NoSampler(S.StringLanguage):
    """Every string over a and b; its sampler and its hazards raise."""

    def sample(self, rng):
        raise RuntimeError("no sampler")

    def hazards(self):
        raise RuntimeError("no hazards")


class _RaisesAlways(_NoSampler):
    """The same language, whose `contains()` raises on every value."""

    def contains(self, value):
        raise RuntimeError("cannot decide")


def _defined(language):
    from mathema.domain import parse_binding
    register_language(language.name, language)
    try:
        defined = domain_relations.defined_bound(parse_binding(f"s in L[{language.name}]")[1])
        (text, served, most, least), = defined.read
        return domain_relations.check_definition(text, served, most, least, defined.alphabet)
    finally:
        unregister_language(language.name)


def _over_ab(kind, name):
    return kind(name, level="predicate", accepts=lambda s: set(s) <= set("ab"), pool="ab",
                generate=S._gen_ab, schema={"term": S.AB_STAR})


def test_the_record_states_the_draws_made():
    drawn = _defined(_over_ab(S.StringLanguage, "drawsmade"))["corroboration"]
    assert drawn["draws"] == domain_relations.GUARD_DRAWS == drawn["draws cap"]
    none = _defined(_over_ab(_NoSampler, "nosampler"))
    record = none["corroboration"]
    assert record["draws"] == 0 and record["draws cap"] == domain_relations.GUARD_DRAWS
    assert record["values compared"] > 0 and record["values skipped"] == 0
    assert none["artefact"]["members drawn"] == 0


def test_a_language_that_decides_no_value_reads_no_value_compared():
    entry = _defined(_over_ab(_RaisesAlways, "raisesalways"))
    record = entry["corroboration"]
    assert record["draws"] == 0 and record["values compared"] == 0
    assert record["values skipped"] == record["values drawn"] > 0
    assert domain_relations.assumption_entry_text(entry) == \
        "L[raisesalways] == its stated definition (assumed, no value compared)"
    assert not domain_relations.agreed_on_every_value(entry)
