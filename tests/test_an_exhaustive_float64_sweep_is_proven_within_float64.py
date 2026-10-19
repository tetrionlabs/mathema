# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An exhaustive sweep of a brute-forced finite domain whose points
cannot all be decided exactly (a library float, a module constant) is
`proven` with route `derive:brute_force:within_float64`: every point
was run in float64 and the claim held at each, and the record states
the largest delta the floats showed against the allowance applied. The
note states the cap for a reader downstream: a difference below that
delta would not show. Ground claims and membership sweeps take the
same spelling; a sampled claim never does. Clarity grades the rung
0.95, under an exact proof and above every holds, and a claim resting
on such a proof through `assuming X is proven` is capped at
within_float64 too, never promoted.

Each body runs a `while` loop so derive cannot read it and the sweep
decides the claim (mathema lifts `numpy.sqrt`, and would otherwise
prove `sqrt(x) ** 2 == x` exactly)."""
import re

import pytest

import mathema
from mathema.badges import _HOLDS_STRENGTH, _strength
from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")

#: a float read from outside a body: no exact reading
RATE = 0.5


def _spin():
    i = 0
    while i < 3:
        i += 1


def lib(x: float) -> float:
    _spin()
    return np.sqrt(x) ** 2


def lib_guarded(x: float) -> float:
    _spin()
    if x == 0:
        return 0.0
    return np.sqrt(x) ** 2


def halve(x: float) -> float:
    _spin()
    return x * RATE


def root_two_squared(xs: list) -> float:
    _spin()
    return float(np.sqrt(2.0) ** 2)


def half(x: float) -> float:
    _spin()
    return x * 0.5


def _check(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, **kw)])
    return p


def test_a_library_float_sweep_is_proven_within_float64():
    p = _check(lib, "for x in {2, 3, 5}, f(x) == x")
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
    assert p.route == "derive:brute_force:within_float64", p.route
    precision = p.meta["mathema.sweep_precision"]
    assert precision["points"] == 3, precision
    assert 0 < precision["largest_delta"] < 1e-15, precision
    assert precision["largest_delta"] < precision["allowance"], precision
    assert precision["representation"] == "float64", precision
    assert "largest_miss" not in precision, precision
    assert p.meta["mathema.sweep_inexact"]["points"] == 3, p.meta
    assert "mathema.sweep_holds" not in p.meta, p.meta


def test_the_record_line_states_the_points_and_the_largest_delta():
    text = repr(mathema.check(lib, claims=[mathema.claim(
        "for x in {2, 3, 5}, f(x) == x", name="squares")]))
    assert re.search(r"proven +squares: .*\(all 3 points in float64, "
                     r"largest delta [0-9.]+e-16\)", text), text


def test_the_note_states_the_cap_for_a_downstream_reader():
    p = _check(lib, "for x in {2, 3, 5}, f(x) == x")
    note = p.note or ""
    # the claim line already shows the set, so the note counts the
    # points rather than naming the claim's scope again
    assert "all 3 points were run in float64 and the claim held at each" \
        in note, note
    assert "finite scope" not in note, note
    assert re.search(r"the largest delta was [0-9.]+e-16 against an "
                     r"allowance of [0-9.e+-]+", note), note
    assert "could not be computed exactly (lib(2))" in note, note
    assert "capped at within_float64" in note, note
    assert re.search(r"a difference below [0-9.]+e-16 would not show", note), \
        note


def test_a_sampled_claim_never_takes_the_route():
    p = _check(lib, "for x in [2, 5], f(x) == x")
    assert not (p.route or "").endswith("within_float64"), (p.verdict, p.route)
    assert "mathema.sweep_precision" not in (p.meta or {}), p.meta


def test_a_ground_claim_is_proven_within_float64():
    # sqrt(2) ** 2 is 2.0000000000000004 in float64
    p = _check(root_two_squared, "f([]) == 2")
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
    assert p.route == "derive:brute_force:within_float64", p.route
    precision = p.meta["mathema.sweep_precision"]
    assert precision["points"] == 1 and 0 < precision["largest_delta"] < 1e-15, \
        precision
    assert "could not be computed exactly (xs = [])" in (p.note or ""), p.note


def test_a_membership_sweep_is_proven_within_float64():
    p = _check(halve, "for x in {1, 2}, f(x) in {0.5, 1}")
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
    assert p.route == "derive:brute_force:within_float64", p.route
    precision = p.meta["mathema.sweep_precision"]
    assert precision["largest_delta"] == 0.0 and precision["allowance"] == 0.0, \
        precision


def test_an_exact_sweep_keeps_the_exact_route():
    p = _check(half, "for x in {1, 2, 3}, f(x) == x / 2")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), \
        (p.verdict, p.route)
    assert "mathema.sweep_precision" not in p.meta, p.meta


def test_clarity_grades_the_rung_under_exact_proof_and_above_every_holds():
    graded = _strength("proven", "derive:brute_force:within_float64")
    assert graded == 0.95
    assert _strength("proven", "derive:brute_force") == 1.0
    assert graded < _strength("proven", "derive")
    assert graded > max(_HOLDS_STRENGTH.values())
    assert graded > _strength("holds", "derive:brute_force")


def test_a_premise_resting_on_the_rung_caps_the_conclusion():
    # at x = 0 the body returns the literal 0.0, exact: the conclusion
    # is proven exactly on its own and capped by what it rests on
    out = {p.name: p for p in check_conjectures(lib_guarded, [
        claim("for x in {2, 3, 5}, f(x) == x", name="squares"),
        claim("assuming squares is proven, for x in {0}, f(x) == 0",
              name="zero")])}
    assert out["squares"].route == "derive:brute_force:within_float64", \
        out["squares"].route
    zero = out["zero"]
    assert zero.verdict == "proven", (zero.verdict, zero.route, zero.note)
    assert zero.route.endswith(":within_float64"), zero.route
    assert zero.meta["mathema.capped_by"] == "squares", zero.meta
    assert "capped" in (zero.note or ""), zero.note


def test_a_premise_resting_on_the_rung_never_promotes():
    out = {p.name: p for p in check_conjectures(lib_guarded, [
        claim("for x in {2, 3, 5}, f(x) == x", name="squares"),
        claim("assuming squares is proven, for x in [2, 5], f(x) >= 0",
              name="nonneg", route="probe")])}
    assert out["nonneg"].verdict == "holds", out["nonneg"].verdict
    assert not (out["nonneg"].route or "").endswith("within_float64")


def test_the_conclusion_of_an_exact_premise_is_not_capped():
    out = {p.name: p for p in check_conjectures(lib_guarded, [
        claim("for x in {0}, f(x) == 0", name="zero"),
        claim("assuming zero is proven, for x in {0}, f(x) >= 0",
              name="nonneg")])}
    assert out["nonneg"].route == "derive:brute_force", out["nonneg"].route
    assert "mathema.capped_by" not in (out["nonneg"].meta or {})
