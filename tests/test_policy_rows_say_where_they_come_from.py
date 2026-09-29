# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A policy row on the record names itself (`missing[x]`, `absent[x]`),
says where it came from with one of four openers (the default for the
type, a library's own policy row or a guard in the body, what was
observed, what was stated) and the draws that confirm it, and carries
the one next step when it does not hold. A value claim's note says only
what f did at each missing input; the remedy is on the row, once."""
import math
import re
from typing import Optional


import pytest

import mathema
from mathema.authoring import _fn_key


def lin(x: float) -> float:
    return 2.0 * x + 1.0


def root_opt(x: Optional[float]) -> float:
    return math.sqrt(x)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def total(xs: list) -> float:
    return sum(xs)


def root_guarded(x: float) -> float:
    if x != x:
        raise ValueError("x is nan")
    return math.sqrt(x)


def zero_if_gone(x: Optional[float]) -> float:
    if x is None or x != x:
        return 0.0
    return 2.0 * x


def scaled(x: float, scale: Optional[float] = None) -> float:
    if scale is None:
        scale = 1.0
    return x * scale


def pick(x: float) -> Optional[float]:
    return None if x > 0.5 else x


def _lines(rec) -> list:
    return repr(rec).splitlines()


def _policy(rec) -> dict:
    return {p.name: p for p in rec.probes if (p.meta or {}).get("mathema.policy")}


def test_a_default_row_names_itself_and_its_confirmation():
    rec = mathema.check(lin, claims=[mathema.claim("for x in R, f(x) == 2*x + 1",
                                                   name="c")])
    lines = _lines(rec)
    assert any(line.startswith("           the float64 computation of c ran at 43 "
                               "points: nan, every corner and 40 interior points;")
               and line.endswith("; at x = nan f gave nan back") for line in lines)
    assert (f"  holds   missing[x]: missing(f, x) propagates   [default for a float, "
            f"which may be nan; confirmed on the 43 draws of c[float]. Keep it by "
            f"writing it (mathema claims {_fn_key(lin)} --write), or change the word "
            f"to raises or drops if f should do otherwise]") in lines


def test_an_unaccounted_raise_is_a_named_sentence_row():
    rec = mathema.check(root_opt, claims=[mathema.claim("for x in [0, 4], f(x) >= 0",
                                                        name="c")])
    lines = _lines(rec)
    assert ("           the float64 computation of c ran at 44 points: None, nan, "
            "every corner and 40 interior points; at x = None f raised TypeError; "
            "at x = nan f gave nan back") in lines
    assert ("  proven  missing[x]: missing(f, x) propagates   [from math.sqrt's own "
            "policy row, which f calls; confirmed on the 44 draws of c[float]]") in lines
    at = lines.index("  FALSIFY absent[x]: f raised TypeError at x = None, and no claim "
                     "says it may")
    assert lines[at + 1] == (
        "           x is Optional[float], so f promised to take None. If the raise is "
        "intended, state `absent(f, x) raises(TypeError)`; otherwise handle None in f, "
        "or annotate x as float; or accept the raise as a discovery (mathema accept "
        "test_policy_rows_say_where_they_come_from.root_opt absent[x] --as discovery) "
        "and state `absent(f, x) raises(TypeError)`")


def test_a_silent_drop_keeps_its_remedy_on_the_row_only():
    rec = mathema.check(clamp01, claims=[mathema.claim("for x in R, 0 <= f(x) <= 1",
                                                       name="c")])
    lines = _lines(rec)
    assert ("           the float64 computation of c ran link by link, and every link "
            "holds; at x = nan f returned 1.0, so it drops the hole") in lines
    at = lines.index("  FALSIFY missing[x]: missing(f, x) propagates   [default for a "
                     "float; f drops instead: nan in, 1.0 out]")
    assert lines[at + 1] == (
        "           if 1.0 is the answer f should give for a missing x, write "
        "`missing(f, x) drops`; if not, make f raise or give nan back; or accept it as "
        "a discovery: mathema accept test_policy_rows_say_where_they_come_from.clamp01 "
        "missing[x] --as discovery --corrected \"missing(f, x) drops\"")


def test_a_list_slot_row_names_only_its_member():
    rec = mathema.check(total, claims=[mathema.claim("for xs in [0, 1]^n, f(xs) >= 0",
                                                     name="c")])
    rows = _policy(rec)
    null = rows["missing[xs, null]"]
    assert null.meta["mathema.policy"]["reason"] == (
        "default for a list slot that may be null; f raises instead: a null slot in, "
        "TypeError")
    assert null.meta["mathema.policy"]["next"] == (
        "if the raise is intended, write `missing(f, xs, null) raises(TypeError)`; if "
        "not, make f skip or fill the null slot; or accept it as a discovery: mathema "
        "accept test_policy_rows_say_where_they_come_from.total missing[xs, null] --as "
        "discovery --corrected \"missing(f, xs, null) raises(TypeError)\"")
    nan = rows["missing[xs, nan]"]
    assert nan.meta["mathema.policy"]["reason"].startswith(
        "default for a list slot that may be nan; confirmed on the ")


def test_a_note_carries_no_remedy():
    for fn, text in ((total, "for xs in [0, 1]^n, f(xs) >= 0"),
                     (root_opt, "for x in [0, 4], f(x) >= 0"),
                     (root_guarded, "for x in [0, 4], f(x) >= 0"),
                     (clamp01, "for x in R, 0 <= f(x) <= 1"),
                     (root_opt, "for x in {0.25, None}, f(x) >= 0")):
        rec = mathema.check(fn, claims=[mathema.claim(text, name="c")])
        for p in rec.probes:
            if (p.meta or {}).get("mathema.policy"):
                continue
            assert "`" not in (p.note or ""), (fn.__name__, p.name, p.note)
            assert "no claim" not in (p.note or ""), (fn.__name__, p.name, p.note)


def test_a_guard_on_absence_derives_the_row_as_it_does_for_a_hole():
    rows = _policy(mathema.check(zero_if_gone, claims=[
        mathema.claim("for x in [0, 1], f(x) >= 0", name="c")]))
    assert rows["absent[x]"].statement == "absent(f, x) drops"
    assert rows["absent[x]"].verdict == "proven"
    assert rows["absent[x]"].meta["mathema.policy"]["reason"].startswith(
        "from the guard on line 2; confirmed ")
    assert rows["missing[x]"].meta["mathema.policy"]["reason"].startswith(
        "from the guard on line 2; confirmed ")


def test_none_as_a_flag_gets_its_drop_row():
    rows = _policy(mathema.check(scaled, claims=[
        mathema.claim("for x in [0, 1], f(x) >= 0", name="c")]))
    assert rows["absent[scale]"].statement == "absent(f, scale) drops"
    assert rows["absent[scale]"].verdict == "proven"
    assert rows["absent[scale]"].meta["mathema.policy"]["reason"].startswith(
        "from the guard on line 2")


def test_a_stated_row_replaces_only_its_own_case():
    rec = mathema.check(total, claims=[
        mathema.claim("for xs in [0, 1]^n, f(xs) >= 0", name="c"),
        mathema.claim("missing(f, xs, null) raises(TypeError)", name="mine")])
    rows = {p.statement: p.verdict for p in rec.probes
            if (p.meta or {}).get("mathema.policy")}
    assert rows == {"missing(f, xs, null) raises(TypeError)": "holds",
                    "missing(f, xs, nan) propagates": "holds"}


def test_a_stated_return_absence_is_decided_on_the_calls():
    rec = mathema.check(pick, claims=[mathema.claim("for x in [0, 1], f(x) <= 1",
                                                    name="c"),
                                      mathema.claim("absent(f) introduces", name="r")])
    (row,) = [p for p in rec.probes if p.name == "r"]
    assert row.verdict == "holds", (row.verdict, row.note)
    assert row.meta["mathema.policy"]["reason"].startswith(
        "stated; f returned None at x = ")


def test_an_unknown_policy_row_says_why_on_the_record():
    rec = mathema.check(lin, claims=[mathema.claim("for x in [0, 1], f(x) >= 1", name="c"),
                                     mathema.claim("assuming x >= 0, missing(f, x) "
                                                   "propagates", name="p")])
    (row,) = [p for p in rec.probes if p.name == "p"]
    assert row.verdict == "unknown"
    assert row.meta["mathema.policy"]["reason"] == (
        "the premise x >= 0 cannot be decided at x = nan; a policy row's premise is "
        "about the other parameters or about count(...)")
    assert any(line.startswith("           the premise x >= 0 cannot be decided")
               for line in _lines(rec))


def test_every_row_name_on_a_record_is_its_own():
    rec = mathema.check(total, claims=[mathema.claim("for xs in [0, 1]^n, f(xs) >= 0",
                                                     name="c")])
    names = [p.name for p in rec.probes]
    assert len(names) == len(set(names)), names


def test_a_policy_row_name_is_a_claims_file_name(tmp_path):
    from mathema.spec import entry_claims
    entry = {"claims": [
        {"name": "missing[xs, count >= 1]",
         "statement": "assuming count(xs) >= 1, missing(f, xs) drops"},
        {"name": "missing[xs, count == 0]",
         "statement": "assuming count(xs) == 0, missing(f, xs) propagates"}]}
    names = [c.name for c in entry_claims(entry)]
    assert names == ["missing[xs, count >= 1]", "missing[xs, count == 0]"]


def test_a_let_bound_function_is_not_f():
    rec = mathema.check(total, claims=[mathema.claim(
        "let g = mathema.f.reverse_seq, for xs in [0, 1]^n, f(xs) == f(g(xs))",
        name="c")])
    text = repr(rec)
    assert "HoledArray" not in text
    for p in rec.probes:
        for line in (p.note or "", (p.meta or {}).get("mathema.policy", {}).get("reason", "")):
            assert not re.search(r"f returned \[", line or ""), line


def test_no_internal_row_name_reaches_a_bracket():
    def root(x: float) -> float:
        return math.sqrt(x)
    rec = mathema.check(root, claims=[mathema.claim("for x in [0, 4], 0 <= f(x) <= 2",
                                                    name="c")])
    for p in _policy(rec).values():
        assert "[link" not in p.meta["mathema.policy"]["reason"], p.meta
        assert "its own floor" not in p.meta["mathema.policy"]["reason"]


def test_a_floor_confirmation_names_the_point():
    rec = mathema.check(root_guarded, claims=[mathema.claim(
        "absent(f, x) raises(TypeError)", name="s")])
    (row,) = [p for p in rec.probes if p.name == "s"]
    assert row.meta["mathema.policy"]["reason"] == \
        "stated; confirmed by calling f at x = None"


def test_a_clash_says_which_premises_tell_cases_apart():
    from mathema.policy import contradicting_policies
    found = contradicting_policies(["missing(f, x) propagates", "missing(f, x) drops"])
    assert found == (
        "`missing(f, x) propagates` and `missing(f, x) drops` state two behaviours for "
        "one case. Keep one (the record shows which f follows), or give each a premise "
        "on another parameter or on count(...) that tells the cases apart, e.g. "
        "`assuming count(xs) >= 1, ...` beside `assuming count(xs) == 0, ...`")


def test_a_premised_library_row_remedy_keeps_its_premise():
    pd = pytest.importorskip("pandas")

    def mean_pd(xs: pd.Series) -> float:
        return float(xs.mean())
    rec = mathema.check(mean_pd, claims=[mathema.claim(
        "for xs in [0, 1]^n, 0 <= f(xs) <= 1", name="c")])
    row = _policy(rec)["missing[xs, count == 0]"]
    nxt = row.meta["mathema.policy"]["next"]
    remedies = re.findall(r"`([^`]+)`", nxt)
    assert remedies and all(r.startswith("assuming count(xs) == 0, ") for r in remedies)
    again = mathema.check(mean_pd, claims=[mathema.claim(
        "for xs in [0, 1]^n, 0 <= f(xs) <= 1", name="c")] + [
        mathema.claim(r) for r in remedies])
    stated = [p for p in again.probes if p.statement in remedies]
    assert stated and all(p.verdict in ("holds", "proven") for p in stated), \
        [(p.statement, p.verdict, p.note) for p in stated]


def test_one_switch_makes_mathemas_policy_rows_gate(monkeypatch):
    from mathema import verify
    rec = mathema.check(clamp01, claims=[mathema.claim("for x in R, 0 <= f(x) <= 1",
                                                       name="c")])
    report = verify.gate(rec.probes, strict=False)
    assert report.falsified == 1
    assert report.problems == [
        "missing[x]: f drops a missing x (nan in, 1.0 out), the row says propagates; "
        "change the word or the code"]
    monkeypatch.setattr(verify, "POLICY_ROWS_GATE", False)
    assert verify.gate(rec.probes, strict=False).problems == []


def test_a_bare_raises_beside_a_named_one_is_no_clash():
    from mathema.policy import contradicting_policies
    assert contradicting_policies(["absent(f, x) raises(TypeError)",
                                   "absent(f, x) raises"]) is None
    assert contradicting_policies(["absent(f, x) raises(TypeError)",
                                   "absent(f, x) raises(ValueError)"]) is not None
