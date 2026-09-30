# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Missing values over strings and languages: every row of the language
battery. A string parameter can be absent (`None`), a member's field can
be absent, and a string has no hole of its own. Rows quantified over a
language (`L[...]`) need the mathema-language package, and the rows over
a pydantic model need pydantic too; each is skipped without them. A row
a later stage of the build owns carries a strict `xfail`."""
import importlib.util
from typing import Optional

import pytest

import mathema

from tests.test_missing_values_core import (FALSIFIED, PROVEN,
                                            PROVEN_OR_HOLDS, assert_row,
                                            run, stage, witness)

needs_language = pytest.mark.skipif(
    importlib.util.find_spec("mathema_language") is None,
    reason="needs the mathema-language package")
#: the rows that read an absence along a path, which the paths handoff
#: (absent members `null` and `unset`) re-authors
paths_handoff = pytest.mark.xfail(strict=True, reason="paths: absent members null, unset")
needs_pydantic = pytest.mark.skipif(
    importlib.util.find_spec("pydantic") is None, reason="needs pydantic")


def label(s: Optional[str]) -> str:
    if s is None:
        return "-"
    return s.strip().upper()


def label_any_missing(s: Optional[str]) -> str:
    if s is None or (isinstance(s, float) and s != s):
        return "-"
    return s.strip().upper()


def shout(s: str) -> str:
    return s.upper()


def first_line(doc: str) -> str:
    return doc.split("\n", 1)[0]


try:
    from pydantic import BaseModel

    class Order(BaseModel):
        sku: str
        qty: int
        note: Optional[str] = None

    def note_len(o: Order) -> int:
        return len(o.note)

    def note_len_guarded(o: Order) -> int:
        return 0 if o.note is None else len(o.note)

    ORDER = f"L[{__name__}.Order]"
except ImportError:  # pragma: no cover
    ORDER = "L[Order]"


def test_g1_a_listed_absence_is_handled():
    assert_row(label, 'for s in {"a", None}, f(s) != ""', PROVEN_OR_HOLDS)


def test_g2_a_listed_absence_is_called_with_none():
    assert_row(label_any_missing, 'for s in {"a", None}, f(s) != ""', PROVEN_OR_HOLDS)


@needs_language
def test_g3_a_str_annotation_infers_the_bare_language():
    probe, _ = run(shout, "f(f(s)) == f(s)")
    assert probe.verdict == "holds"
    assert "L[unicode]|" not in (probe.note or "")


def _absent_row(fn, text, param):
    """The value claim and the absence row a claim admitting None
    produces: a raise at the admitted None is classified (FM26), and the
    policy row carries it."""
    rec = mathema.check(fn, claims=[mathema.claim(text, name="c")])
    value = next(p for p in rec.probes if p.name == "c")
    row = next(p for p in rec.probes if p.name == f"absent[{param}]")
    return value, row


@needs_language
def test_g5_an_admitted_absence_is_drawn():
    value, row = _absent_row(shout, "for s in L[unicode] | {None}, f(f(s)) == f(s)", "s")
    assert value.verdict in PROVEN_OR_HOLDS, (value.verdict, value.note)
    assert "at s = None f raised AttributeError" in (value.note or "")
    assert row.verdict == "falsified"
    assert row.counterexample == "s = None: f raised AttributeError"


@needs_language
def test_g6b_an_admitted_absence_is_drawn_for_a_document():
    value, row = _absent_row(first_line,
                             "for doc in L[unicode] | {None}, len(f(doc)) <= len(doc)",
                             "doc")
    assert value.verdict in PROVEN_OR_HOLDS, (value.verdict, value.note)
    assert row.verdict == "falsified"
    assert row.counterexample == "doc = None: f raised AttributeError"


@needs_language
def test_g7_the_empty_string_is_a_value():
    probe, _ = assert_row(label, "for s in L[unicode] | {None}, len(f(s)) >= 1",
                          FALSIFIED)
    assert "''" in witness(probe)


def test_g8_a_string_has_no_hole():
    probe, _ = run(label, 'for s in {missing}, f(s) == "-"')
    assert probe.verdict.startswith("skipped"), (probe.verdict, probe.note)
    assert ("s is a string, and a string has no hole; to admit its absence write "
            "`|absent`") in (probe.note or "")
    assert probe.statement == 'for s in {missing}, f(s) = "-"'   # the whole claim


def test_g9_an_optional_string_that_handles_none_is_missing_safe():
    assert_row(label, "is_missing_safe(f)", PROVEN)


def test_g10_a_function_handling_every_missing_value_is_missing_safe():
    assert_row(label_any_missing, "is_missing_safe(f)", PROVEN)


@needs_language
@needs_pydantic
@paths_handoff
def test_o1_an_absent_optional_field_raising_falsifies():
    assert_row(note_len, f"for o in {ORDER}, f(o) >= 0", FALSIFIED)


@needs_language
@needs_pydantic
def test_o2_a_field_bound_present_holds():
    assert_row(note_len, f"for o in {ORDER}, o.note in L[unicode] \\ {{None}}, f(o) >= 0",
               PROVEN_OR_HOLDS)


@needs_language
@needs_pydantic
def test_o3_a_guarded_field_holds():
    assert_row(note_len_guarded, f"for o in {ORDER}, f(o) >= 0", PROVEN_OR_HOLDS)


@needs_language
@needs_pydantic
def test_o4_an_absent_field_raises_typeerror():
    assert_row(note_len, f"for o in {ORDER}, o.note in {{None}}, raises(f(o), TypeError)",
               PROVEN_OR_HOLDS)


@needs_language
@needs_pydantic
@paths_handoff
def test_o5_an_absent_optional_field_is_not_missing_safe():
    probe, _ = assert_row(note_len, "is_missing_safe(f)", FALSIFIED)
    assert "None" in witness(probe)


@needs_language
@needs_pydantic
def test_o6_an_admitted_absent_field_falsifies():
    assert_row(note_len, f"for o in {ORDER}, o.note in L[unicode] | {{None}}, f(o) >= 0",
               FALSIFIED)


@needs_language
@needs_pydantic
@paths_handoff
def test_a_path_bound_states_absence_where_it_narrows_an_optional_field():
    probe, _ = run(note_len, f"for o in {ORDER}, o.note in L[unicode] \\ {{None}}, f(o) >= 0")
    assert "o.note in L[unicode] \\ {None}" in probe.statement
    probe, _ = run(note_len, f"for o in {ORDER}, o.sku in L[unicode] \\ {{None}}, f(o) >= 0")
    assert "o.sku in L[unicode]," in probe.statement
