# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim decided on the route `derive:brute_force:within_float64`
(every point of a finite set run in float64, some point with no exact
value) is `holds`: the float sweep is the computation's result and does
not prove the mathematics. The route, the measurement and the note are
kept, and the note of an equality offers the tolerant relation `~=`. A
sweep whose every point has an exact value stays `proven` on
`derive:brute_force`. What rests on a row decided within float64 holds
too, and its `[float]` computation row keeps its own verdict.
"""
from __future__ import annotations

import math
import re

import mathema
from mathema.conjecture import check_conjectures, claim

WITHIN = "derive:brute_force:within_float64"
EPS = 1e-16
#: a float read from outside a body: no exact reading
RATE = 0.5


def _spin():
    i = 0
    while i < 3:
        i += 1


def tiny(n):
    return math.exp(EPS * n)


def tiny_unread(n):
    _spin()
    return math.exp(EPS * n)


def halve(x: float) -> float:
    _spin()
    return x * RATE


def half(x: float) -> float:
    _spin()
    return x * 0.5


def square(x: float) -> float:
    return x * x


def _check(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, name="c")], **kw)
    return p


def test_the_claim_is_false_in_exact_arithmetic_and_true_in_float64_at_one_point():
    assert tiny(1) == 1 and tiny(2) != 1
    assert tiny(2) - 1 == 2.220446049250313e-16


def test_a_sweep_within_float64_holds_and_keeps_its_route_and_note():
    p = _check(tiny, "for n in {1, 2, 3}, f(n) == 1")
    assert (p.verdict, p.route) == ("holds", WITHIN), (p.verdict, p.route, p.note)
    note = p.note or ""
    assert "all 3 points were run in float64 and the claim held at each" in note
    assert "capped at within_float64" in note, note
    assert "a difference below 2.2e-16 would not show" in note, note
    precision = p.meta["mathema.sweep_precision"]
    assert precision["points"] == 3 and precision["representation"] == "float64"
    assert p.meta["mathema.sweep_inexact"]["points"] == 3, p.meta


def test_the_note_of_an_equality_offers_the_tolerant_relation():
    p = _check(tiny, "for n in {1, 2, 3}, f(n) == 1")
    assert (p.note or "").endswith(
        "to state the value within a tolerance, write the claim with ~= in "
        "place of ==")
    q = _check(tiny_unread, "for n in {1, 2, 3}, f(n) <= 1")
    assert (q.verdict, q.route) == ("holds", WITHIN), (q.verdict, q.route)
    assert "~=" not in (q.note or ""), q.note


def test_the_tolerant_relation_is_proven_as_written():
    p = _check(tiny, "for n in {1, 2, 3}, f(n) ~= 1")
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
    assert not (p.route or "").endswith(":within_float64"), p.route


def test_a_sweep_with_an_exact_value_at_every_point_stays_proven():
    p = _check(half, "for x in {1, 2, 3}, f(x) == x / 2")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), \
        (p.verdict, p.route)
    assert "mathema.sweep_precision" not in p.meta, p.meta


def test_a_ground_claim_within_float64_holds():
    p = _check(tiny_unread, "f(1) == 1")
    assert (p.verdict, p.route) == ("holds", WITHIN), (p.verdict, p.route, p.note)
    assert "capped at within_float64" in (p.note or ""), p.note
    assert "~= in place of ==" in (p.note or ""), p.note


def test_a_membership_sweep_within_float64_holds():
    p = _check(halve, "for x in {1, 2}, f(x) in {0.5, 1}")
    assert (p.verdict, p.route) == ("holds", WITHIN), (p.verdict, p.route, p.note)
    assert p.meta["mathema.sweep_precision"]["largest_delta"] == 0.0


def test_the_record_line_says_holds_with_the_points_and_the_largest_delta():
    text = repr(mathema.check(tiny, claims=[mathema.claim(
        "for n in {1, 2, 3}, f(n) == 1", name="ones")]))
    assert re.search(r"holds +ones: .*\(all 3 points in float64, "
                     r"largest delta 2\.2e-16\)", text), text
    assert not re.search(r"proven +ones", text), text


def test_what_rests_on_a_row_within_float64_holds():
    out = {p.name: p for p in check_conjectures(tiny, [
        claim("for n in {1, 2, 3}, f(n) == 1", name="ones"),
        claim("assuming ones is proven, for n in {0}, f(n) >= 1", name="rests")])}
    assert (out["ones"].verdict, out["ones"].route) == ("holds", WITHIN)
    rests = out["rests"]
    assert rests.verdict == "holds", (rests.verdict, rests.route, rests.note)
    assert (rests.route or "").endswith(":within_float64"), rests.route


def _rest_on(stored_verdict, route):
    known = {"other.sq": {"verdict": stored_verdict, "key": "other",
                          "provenance": "other/sq", "route": route}}
    return {p.name: p for p in mathema.check(square, claims=[mathema.claim(
        "assuming other.sq is proven, for x in [0, 1], f(x) >= 0",
        name="rests")], known_premises=known).probes}


def test_a_stored_premise_on_the_route_caps_under_either_stored_word():
    # a record an earlier release wrote says proven on this route; one
    # written now says holds
    for stored in ("proven", "holds"):
        rests = _rest_on(stored, WITHIN)["rests"]
        assert rests.verdict == "holds", (stored, rests.verdict, rests.note)
        assert rests.route == "derive:within_float64", rests.route
        assert rests.meta["mathema.capped_by"] == "other/sq", rests.meta
        assert "capped at within_float64" in (rests.note or ""), rests.note


def test_the_float_row_of_a_capped_claim_keeps_its_own_verdict():
    capped = _rest_on("proven", WITHIN)
    exact = _rest_on("proven", "derive:brute_force")
    assert exact["rests"].verdict == "proven", exact["rests"].verdict
    assert capped["rests[float]"].verdict == exact["rests[float]"].verdict == "holds"
    assert capped["rests[float]"].route == exact["rests[float]"].route == "probe"


def test_a_sweep_within_float64_has_no_float_row_of_its_own():
    names = [p.name for p in mathema.check(tiny, claims=[mathema.claim(
        "for n in {1, 2, 3}, f(n) == 1", name="ones")]).probes]
    assert "ones" in names and "ones[float]" not in names, names


def test_no_row_is_proven_on_a_route_ending_within_float64():
    rows = [_check(tiny, "for n in {1, 2, 3}, f(n) == 1"),
            _check(tiny_unread, "for n in {1, 2, 3}, f(n) >= 1"),
            _check(tiny_unread, "f(2) == 1"),
            _check(halve, "for x in {1, 2}, f(x) in {0.5, 1}"),
            _rest_on("proven", WITHIN)["rests"]]
    assert all((p.route or "").endswith(":within_float64") for p in rows), \
        [p.route for p in rows]
    assert [p.verdict for p in rows] == ["holds"] * len(rows)
