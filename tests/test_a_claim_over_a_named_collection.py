# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim may range over a named finite collection, a module-level
tuple, list, frozenset or dict: `for fn in pkg.mod.STAGES, describe(fn)
== "(float) -> float"`. It is decided by judging every member, proven
only when every member is, falsified naming the first member that
breaks it, and never decided by a sample: a collection larger than the
budget leaves the claim unknown. The row's record lists the members by
position, name and hash. The collections are in
`tests/_collection_examples.py`."""
import pytest

from mathema import _collection
from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.spec import canonical_claim_text, claims_fingerprint
from tests import _collection_examples as ex

_PATH = "tests._collection_examples"


def _row(fn, text):
    (row,) = [r for r in check_conjectures(fn, [claim(text)]) if "[" not in r.name]
    return row


# --- a tool over a collection of programs, and its false twin -------------

def test_a_describe_claim_over_three_stages_is_proven_by_enumeration():
    row = _row(ex.describe, f'for fn in {_PATH}.STAGES, describe(fn) == "(float) -> float"')
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.route == "derive:collection"
    assert row.n == 3
    record = row.meta[_collection.COLLECTION_META]
    assert record["path"] == f"{_PATH}.STAGES"
    assert record["kind"] == "tuple" and record["size"] == 3
    assert [m["name"] for m in record["members"]] == [
        f"{_PATH}.percent_to_fraction", f"{_PATH}.fraction_to_growth_factor", f"{_PATH}.halve"]
    assert [m["index"] for m in record["members"]] == [0, 1, 2]
    assert all(m["hash"].startswith("cd:") for m in record["members"])
    assert record["hash"].startswith("cl:")
    assert record["verdicts"] == ["proven", "proven", "proven"]


def test_the_false_twin_is_falsified_naming_the_member_that_breaks_it():
    row = _row(ex.describe,
               f'for fn in {_PATH}.MAPS_WITH_CLAMP, describe(fn) == "(float) -> float"')
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.counterexample == f"fn = {_PATH}.clamp (member 1)"
    assert "member 1 of" in row.note and f"{_PATH}.clamp" in row.note
    # the witness names the member, never a value the call returned
    assert "(float, float, float)" not in (row.counterexample + row.note)
    assert row.meta[_collection.COLLECTION_META]["verdicts"] == [
        "proven", "falsified", "proven"]


# --- collections of numbers, texts and records -------------------------------

def test_a_collection_of_numbers_is_enumerated():
    assert _row(ex.square, f"for n in {_PATH}.SMALL, square(n) <= 9").verdict == "proven"
    twin = _row(ex.square, f"for n in {_PATH}.SMALL_AND_FOUR, square(n) <= 9")
    assert twin.verdict == "falsified"
    assert twin.counterexample == "n = 4 (member 3)"


def test_a_collection_of_texts_is_enumerated():
    row = _row(ex.shout, f'for word in {_PATH}.WORDS, shout(word) != ""')
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.meta[_collection.COLLECTION_META]["kind"] == "list"


def test_a_collection_of_records_is_enumerated():
    row = _row(ex.area, f"for box in {_PATH}.BOXES, area(box) >= 2")
    assert row.verdict == "proven", (row.verdict, row.note)
    twin = _row(ex.area, f"for box in {_PATH}.BOXES_WITH_A_FLAT_ONE, area(box) >= 2")
    assert twin.verdict == "falsified"
    assert twin.counterexample.startswith("box = Box(width=0, height=4) (member 1)")


def test_a_dict_ranges_over_its_values_each_named_by_its_key():
    row = _row(ex.describe,
               f'for fn in {_PATH}.STAGES_BY_STEP, describe(fn) == "(float) -> float"')
    assert row.verdict == "proven", (row.verdict, row.note)
    names = [m["name"] for m in row.meta[_collection.COLLECTION_META]["members"]]
    assert names == [f"'scale': {_PATH}.percent_to_fraction",
                     f"'grow': {_PATH}.fraction_to_growth_factor"]
    twin = _row(ex.describe,
                f'for fn in {_PATH}.STEPS_WITH_CLAMP, describe(fn) == "(float) -> float"')
    assert twin.verdict == "falsified"
    assert twin.counterexample == f"fn = 'hold': {_PATH}.clamp (member 1)"


def test_a_frozenset_lists_its_members_in_one_order_by_name():
    row = _row(ex.describe,
               f'for fn in {_PATH}.STAGE_SET, describe(fn) == "(float) -> float"')
    assert row.verdict == "proven", (row.verdict, row.note)
    names = [m["name"] for m in row.meta[_collection.COLLECTION_META]["members"]]
    assert names == sorted(names)


# --- the members as functions under test, called functions and arguments ----

def test_a_member_bound_to_f_is_the_function_under_test():
    row = _row(ex.square, f"for f in {_PATH}.STAGES, f(50) >= 0")
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.meta[_collection.COLLECTION_META]["reading"] == "subject"
    twin = _row(ex.square, f"for f in {_PATH}.STAGES, f(50) >= 1")
    assert twin.verdict == "falsified"
    assert twin.counterexample.startswith(f"f = {_PATH}.percent_to_fraction (member 0)")


def test_a_member_bound_to_a_called_name_is_called_as_a_let_binding_is():
    row = _row(ex.square, f"for g in {_PATH}.STAGES, g(50) >= 0")
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.meta[_collection.COLLECTION_META]["reading"] == "function"


def test_a_member_passed_to_another_call_is_a_point_of_the_claim():
    text = f'for fn in {_PATH}.STAGES, decline_category(emit(fn)) == "text-key"'
    row = _row(ex.decline_category, text)
    assert row.verdict == "proven", (row.verdict, row.note)
    assert row.meta[_collection.COLLECTION_META]["reading"] == "argument"
    twin = _row(ex.decline_category, text.replace("STAGES", "MAPS_WITH_CLAMP"))
    assert twin.verdict == "falsified"
    assert twin.counterexample == f"fn = {_PATH}.clamp (member 1)"


def test_a_called_name_over_a_member_that_is_not_a_function_is_misspecified():
    row = _row(ex.square, f"for g in {_PATH}.SMALL, g(50) >= 0")
    assert row.verdict == "skipped:misspecified"
    assert row.note == (f"g is called in the claim, but member 0 of {_PATH}.SMALL (1) "
                        f"is not a function")


# --- empty, over the budget, and not a collection -----------------------------

def test_a_claim_over_an_empty_collection_is_proven_vacuously_and_says_so():
    row = _row(ex.square, f"for n in {_PATH}.NOTHING, square(n) <= 9")
    assert row.verdict == "proven"
    assert row.note == f"the collection {_PATH}.NOTHING is empty"
    assert row.meta[_collection.COLLECTION_META]["size"] == 0


def test_a_collection_over_the_budget_is_unknown_and_never_sampled():
    row = _row(ex.square, f"for n in {_PATH}.MANY, square(n) >= 0")
    assert row.verdict == "unknown"
    assert row.note == (f"the collection has 1500 members, more than the budget of "
                        f"{_collection.COLLECTION_MEMBER_BUDGET}")
    assert row.n == 0 and row.route is None


def test_a_name_that_is_not_a_collection_is_misspecified_with_its_type():
    row = _row(ex.square, f"for n in {_PATH}.ONE_NUMBER, square(n) >= 0")
    assert row.verdict == "skipped:misspecified"
    assert row.note == (f"n ranges over {_PATH}.ONE_NUMBER, which is not a named "
                        f"collection: {_PATH}.ONE_NUMBER is an int, not a tuple, list, "
                        f"frozenset or dict")


def test_a_path_that_does_not_resolve_is_misspecified():
    row = _row(ex.square, f"for n in {_PATH}.NO_SUCH_NAME, square(n) >= 0")
    assert row.verdict == "skipped:misspecified"
    assert row.note.endswith(f"{_PATH}.NO_SUCH_NAME does not resolve")


def test_a_path_that_reaches_the_system_is_refused():
    row = _row(ex.square, "for n in os.environ, square(n) >= 0")
    assert row.verdict == "skipped:misspecified"
    assert "reaches the system" in row.note


def test_a_collection_stands_alone_in_its_binding():
    with pytest.raises(InvalidConjecture, match="stands alone"):
        claim(f"for n in {_PATH}.SMALL : int, square(n) >= 0")


# --- the claim's text and identity name the path, never the members ------

def test_the_canonical_text_writes_the_path_and_reads_back():
    text = f'for fn in {_PATH}.STAGES, describe(fn) == "(float) -> float"'
    assert canonical_claim_text(claim(text)) == (
        f'for fn in {_PATH}.STAGES, describe(fn) = "(float) -> float"')
    assert _row(ex.describe, text).statement == canonical_claim_text(claim(text))


def test_editing_the_collection_moves_its_hash_and_not_the_claims_fingerprint(monkeypatch):
    text = f'for fn in {_PATH}.STAGES, describe(fn) == "(float) -> float"'
    raw = [{"name": "each_stage", "statement": text}]
    before_fp = claims_fingerprint(raw)
    before = _row(ex.describe, text).meta[_collection.COLLECTION_META]["hash"]
    monkeypatch.setattr(ex, "STAGES", ex.STAGES[:2])
    after = _row(ex.describe, text).meta[_collection.COLLECTION_META]["hash"]
    assert claims_fingerprint(raw) == before_fp
    assert after != before


def test_a_claim_ranges_over_one_named_collection():
    row = _row(ex.clamp, f"for x in {_PATH}.SMALL, lo in {_PATH}.SMALL, clamp(x, lo, 9) >= lo")
    assert row.verdict == "skipped:misspecified"
    assert row.note == "x, lo each range over a named collection; a claim ranges over one"


def test_a_collection_beside_a_finite_binding_is_enumerated_with_it():
    row = _row(ex.clamp, f"for x in {_PATH}.SMALL, lo in {{-5, -4}}, clamp(x, lo, 9) >= lo")
    assert row.verdict == "proven", (row.verdict, row.note)
    twin = _row(ex.clamp, f"for x in {_PATH}.SMALL, lo in {{-5, 2}}, clamp(x, lo, 9) == x")
    assert twin.verdict == "falsified"
    assert twin.counterexample == "x = 1 (member 0): lo = 2"
