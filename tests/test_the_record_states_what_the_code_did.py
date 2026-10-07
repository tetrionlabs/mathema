# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""At every missing input it executed, the record states what the code
did, per parameter and member: `meta["mathema.missing"]["executed"]`
maps each parameter to `{member: outcome}` (`nan in, nan out
(propagates)`, `raised TypeError`, `nan in, 1.0 out (drops)`),
`behaviour` names the one behaviour per member (or `mixed`), and the
row's note says it in one sentence, with the claim to write where the
behaviour is not what the parameter's type leads a reader to expect."""
import pytest
import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.probing import ExecutedMissing
from mathema._missing_words import outcome_entry, said

NAN = float("nan")


def plus_one(x: float) -> float:
    return x + 1.0


def doubled(x: "float | None") -> float:
    return x * 2.0


def zero_for_none(x: "float | None") -> float:
    return 0.0 if x is None else x


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _executed(row):
    return ((row.meta or {}).get("mathema.missing") or {}).get("executed")


def test_an_outcome_is_one_entry_form():
    assert outcome_entry("nan", NAN, behaviour="propagates") == "nan in, nan out (propagates)"
    assert outcome_entry("None", raised="TypeError") == "raised TypeError"
    assert outcome_entry("nan", 1.0, behaviour="drops") == "nan in, 1.0 out (drops)"
    assert outcome_entry("null", [1.0, NAN], behaviour="propagates", in_slot=True) == \
        "null slot in, [1.0, nan] out (propagates)"


def test_what_happened_is_one_sentence():
    assert said("x", "nan", {"x": NAN}, NAN, behaviour="propagates") == \
        "at x = nan f gave nan back"
    assert said("x", "None", {"x": None}, raised="TypeError") == "at x = None f raised TypeError"
    assert said("x", "nan", {"x": NAN}, 1.0, behaviour="drops") == \
        "at x = nan f returned 1.0, so it drops the hole"


def test_a_missing_input_is_recorded_under_its_member():
    record = ExecutedMissing()
    record.add_call({"x": None}, raised="TypeError")
    record.add_call({"xs": [1.0, NAN, None]}, output=NAN)
    record.add_call({"y": 0.5}, output=1.0)
    assert record.meta()["executed"] == {
        "x": {"None": "raised TypeError"},
        "xs": {"nan": "nan slot in, nan out (propagates)",
               "null": "null slot in, nan out (propagates)"}}


def test_the_record_keeps_the_first_outcome_per_member():
    record = ExecutedMissing()
    record.add_call({"x": NAN, "y": 1.0}, output=NAN)
    record.add_call({"x": NAN}, raised="ValueError")
    record.add_call({"x": None}, raised="TypeError")
    meta = record.meta()
    assert meta["executed"] == {"x": {"nan": "nan in, nan out (propagates)",
                                      "None": "raised TypeError"}}
    assert meta["behaviour"] == {"x": {"nan": "mixed", "None": "raises"}}
    assert meta["mixed"] == {"x": {"nan": {"propagates": "x = nan, y = 1.0",
                                           "raises": "x = nan"}}}


def test_a_listed_raise_is_said_and_its_claim_is_on_the_policy_row():
    (row,) = check_conjectures(doubled, [claim("for x in {1.0, None, nan}, f(x) == 2*x")])
    assert row.verdict == "proven", (row.verdict, row.note)
    assert _executed(row) == {"x": {"None": "raised TypeError",
                                    "nan": "nan in, nan out (propagates)"}}
    assert "at x = None f raised TypeError" in row.note
    assert "`" not in row.note
    rec = mathema.check(doubled, claims=[claim("for x in {1.0, None, nan}, f(x) == 2*x",
                                               name="c")])
    (policy,) = [p for p in rec.probes if p.name == "absent[x]"]
    assert policy.meta["mathema.policy"]["sentence"] == (
        "f raised TypeError at x = None, a point the claim lists, and no claim says "
        "it may")
    assert policy.meta["mathema.policy"]["next"] == (
        "(i) if the raise is intended, state: absent(f, x) raises(TypeError)\n"
        "(ii) if not, handle None in f, or remove None from the set\n"
        "(iii) to accept the raise as a discovery, run: mathema accept "
        "test_the_record_states_what_the_code_did.doubled absent[x] --as discovery "
        "--corrected \"absent(f, x) raises(TypeError)\"")


def test_a_value_returned_at_a_missing_input_is_stated():
    (row,) = check_conjectures(zero_for_none, [claim("for x in {1.0, None}, f(x) >= 0")])
    assert _executed(row) == {"x": {"None": "None in, 0.0 out (drops)"}}
    assert "at x = None f returned 0.0, so it drops the absence" in row.note


def test_a_silent_drop_is_said_once_as_a_fact():
    rows = check_conjectures(clamp01, [claim("for x in R, 0 <= f(x) <= 1", name="c")],
                             float_companions=True)
    companion = next(p for p in rows if p.name.startswith("c["))
    # the computation line runs the numbers; the drop is the policy line's
    assert "nan" not in companion.note, companion.note
    assert _executed(companion) == {"x": {"nan": "nan in, 1.0 out (drops)"}}
    import mathema
    rec = mathema.check(clamp01, claims=[mathema.claim("for x in R, 0 <= f(x) <= 1",
                                                       name="c")])
    said = [ln for ln in repr(rec).splitlines() if "f(nan)" in ln]
    assert said == ["    falsified  policy       f(nan)   no missing policy stated; "
                    "returns 1.0"], said


def test_a_propagated_hole_is_stated_on_the_proven_row():
    (row,) = check_conjectures(plus_one, [claim("for x in {1.0, nan}, f(x) == x + 1")])
    assert row.verdict == "proven"
    assert _executed(row) == {"x": {"nan": "nan in, nan out (propagates)"}}
    assert "at x = nan f gave nan back" in row.note


def test_a_row_that_executed_no_missing_input_states_none():
    (row,) = check_conjectures(plus_one, [claim("for x in {1.0, 2.0}, f(x) == x + 1")])
    assert _executed(row) is None


def test_a_count_says_the_entries_then_the_draws_then_the_sizes():
    from mathema._missing_words import count_words
    assert count_words(43, None) == "43 draws"
    assert count_words(57, {"form": "vec", "smallest": [1, 1], "largest": [8, 1],
                            "entries": 257}) == \
        "257 entries across 57 draws, sizes (1, 1) to (8, 1)"
    assert count_words(1, {"form": "vec", "smallest": [30, 1], "largest": [30, 1],
                           "entries": 30}) == "30 entries across 1 draw, size (30, 1)"
    assert count_words(1, {"form": "vec", "smallest": [1, 1], "largest": [1, 1],
                           "entries": 1}) == "1 entry across 1 draw, size (1, 1)"


def mean_of(xs) -> float:
    import numpy as np
    return float(np.mean(xs))


def sum_both(xs, ys) -> float:
    import numpy as np
    return float(np.mean(xs) + np.mean(ys))


def _row(record, name):
    (row,) = [p for p in record.probes if p.name == name]
    return row


def test_the_entries_are_counted_over_the_draws_the_row_counts():
    pytest.importorskip("numpy")
    import numpy  # noqa: F401
    rec = mathema.check(mean_of, claims=[mathema.claim(
        "for xs in [0, 1]^3, 0 <= f(xs) <= 1", name="unit")])
    unit = _row(rec, "unit")
    assert unit.meta["mathema.drawn"]["entries"] == 3 * unit.n


def test_the_entries_are_counted_over_every_container():
    pytest.importorskip("numpy")
    import numpy  # noqa: F401
    rec = mathema.check(sum_both, claims=[mathema.claim(
        "for xs in [0, 1]^3, ys in [0, 1]^2, f(xs, ys) >= 0", name="nonneg")])
    row = _row(rec, "nonneg")
    assert row.meta["mathema.drawn"]["entries"] == 5 * row.n


def test_a_policy_row_cites_the_draw_count_its_claim_prints():
    pytest.importorskip("numpy")
    import numpy  # noqa: F401
    rec = mathema.check(mean_of, claims=[mathema.claim(
        "for xs in [0, 1]^n, 0 <= f(xs) <= 1", name="unit")])
    unit = _row(rec, "unit")
    assert f"on the {unit.n} draws of unit" in _row(rec, "missing[xs]").note


def test_a_chained_row_counts_entries_over_the_draws_it_prints():
    from mathema.conjecture import _combine_conjunction
    from mathema.probing import Probe

    def link(name, n, entries):
        return Probe(name, "", "holds", n=n, meta={"mathema.drawn": {
            "form": "vec", "smallest": [1, 1], "largest": [8, 1], "entries": entries}})
    row = _combine_conjunction([link("c[link1]", 111, 595), link("c[link2]", 100, 540)],
                               "c", "0 <= f(xs) <= 1", ["link 1", "link 2"])
    assert row.n == 100
    assert row.meta["mathema.drawn"]["entries"] == 540
