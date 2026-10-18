# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim `a ~= b` takes the tolerance kinds `f =:= g` takes:
`{abs: x}`, `{rel: x}`, `{ulp: n}`, each with an optional `floor: x`
added to it. `a ~= b` then means `|a - b| <= bound + floor`, decided
exactly on the mathematics line (the kind's numbers read as the
decimals written, an ulp of the float64 nearest `max(|a|, |b|)`), and
in float64 on the computation line. A bare number keeps its absolute
meaning. Where a claim reads its tolerance as one number (`ε` in its
text, a premise comparing within it) or is not `~=`, a kind is
refused."""
from fractions import Fraction

import pytest

import mathema
from mathema.conjecture import InvalidConjecture, claim
from mathema.spec import declare, entry_claims, validate_claims_file


def scaled(x: float) -> float:
    return x * (1 + 1e-8)


def offset(x: float) -> float:
    return x + 1.5e-9


def thirds(x: float) -> float:
    return (x * 3) / 3


def nudged(x: float) -> float:
    return x + 1e-15


def square(x: float) -> float:
    return x * x


def _rows(fn, law, tolerance, **kw):
    return mathema.check(fn, claims=[claim(law, tolerance=tolerance,
                                           **kw)]).probes


def _main(rows):
    (row,) = [p for p in rows if "[" not in p.name
              and not p.name.startswith(("missing", "absent", "is_"))]
    return row


def _float(rows):
    found = [p for p in rows if p.name.endswith("[float]")]
    return found[0] if found else None


def test_a_relative_tolerance_holds_where_an_absolute_one_cannot():
    law = "for x in [1e-7, 190], f(x) ~= x"
    absolute = _main(_rows(scaled, law, 1e-9, route="probe"))
    relative = _main(_rows(scaled, law, {"rel": 1e-7}, route="probe"))
    assert absolute.verdict == "falsified", absolute.note
    assert relative.verdict == "holds", (relative.verdict, relative.note)


def test_a_relative_tolerance_is_proven_on_the_mathematics_line():
    rows = _rows(scaled, "for x in [1e-7, 190], f(x) ~= x", {"rel": 1e-7})
    main = _main(rows)
    assert (main.verdict, main.route) == ("proven", "derive"), main.note
    tight = _main(_rows(scaled, "for x in [1e-7, 190], f(x) ~= x",
                        {"rel": 1e-9}))
    assert tight.verdict == "falsified", tight.note


@pytest.mark.parametrize("route", ["probe", "best"])
def test_a_floor_adds_to_the_relative_part(route):
    law = "for x in [1, 2], f(x) ~= x"
    rel = _main(_rows(offset, law, {"rel": 1e-9}, route=route))
    floor = _main(_rows(offset, law, {"abs": 0, "floor": 1e-9},
                        route=route))
    both = _main(_rows(offset, law, {"rel": 1e-9, "floor": 1e-9},
                       route=route))
    assert rel.verdict == "falsified", rel.note
    assert floor.verdict == "falsified", floor.note
    assert both.verdict in ("holds", "proven"), (both.verdict, both.note)


def test_units_in_the_last_place_judge_the_computation_line():
    law = "for x in [-10, 10], f(x) ~= x"
    exact = _rows(thirds, law, {"ulp": 0})
    assert _main(exact).verdict == "proven", _main(exact).note
    assert _float(exact).verdict == "falsified", _float(exact).note
    one = _rows(thirds, law, {"ulp": 1})
    assert _float(one).verdict == "holds", _float(one).note


def test_units_in_the_last_place_decide_the_mathematics_exactly():
    # 1e-15 against 4 ulps of numbers in [1, 2) (8.9e-16) misses, and
    # against 8 (1.8e-15) holds
    law = "for x in [1, 1.5], f(x) ~= x"
    four = _main(_rows(nudged, law, {"ulp": 4}))
    eight = _main(_rows(nudged, law, {"ulp": 8}))
    assert four.verdict == "falsified", four.note
    assert eight.verdict == "holds", (eight.verdict, eight.note)


def test_the_kind_reads_the_decimals_written_exactly():
    from mathema._tolerance import ToleranceKind
    gap = Fraction(1, 10 ** 7)
    # the float 1e-7 is below one ten-millionth; the claim's 1e-7 is not
    assert ToleranceKind("abs", 1e-7).allows_exactly(Fraction(0), gap)
    assert not ToleranceKind("abs", 1e-7).allows_exactly(
        Fraction(0), gap + Fraction(1, 10 ** 30))
    assert ToleranceKind("rel", 1e-7, 1e-9).allows_exactly(
        Fraction(1), 1 + gap + Fraction(1, 10 ** 9))
    assert not ToleranceKind("rel", 1e-7, 1e-9).allows_exactly(
        Fraction(1), 1 + gap + Fraction(2, 10 ** 9))
    assert ToleranceKind("ulp", 2).allows_exactly(
        Fraction(1), Fraction(1) + Fraction(2, 2 ** 52))
    assert not ToleranceKind("ulp", 2).allows_exactly(
        Fraction(1), Fraction(1) + Fraction(3, 2 ** 52))


def test_the_record_shows_the_kind_as_written_and_how_it_read_it():
    rows = _rows(scaled, "for x in [1e-7, 190], f(x) ~= x",
                 {"floor": 1e-12, "rel": 1e-7})
    main = _main(rows)
    assert main.tolerance == {"rel": 1e-7, "floor": 1e-12}
    assert ("read as abs(f(x) - x) <= 1e-7 * max(abs(f(x)), abs(x)) "
            "+ 1e-12, the tolerance {rel: 1e-7, floor: 1e-12} (declared)"
            ) in main.note, main.note
    ulp = _main(_rows(thirds, "for x in [-10, 10], f(x) ~= x", {"ulp": 4}))
    assert ("read as abs(f(x) - x) <= 4 units in the last place of the "
            "float64 nearest max(abs(f(x)), abs(x)), the tolerance "
            "{ulp: 4} (declared)") in ulp.note, ulp.note


def test_a_claims_file_states_a_kind_on_approximate_equality():
    data = {"pkg.f": {"claims": [
        {"statement": "for x in [0, 1], f(x) ~= x",
         "tolerance": {"rel": 1e-9, "floor": 1e-12}}]}}
    validate_claims_file(data, "claims.yaml")
    (cj,) = entry_claims(data["pkg.f"])
    assert declare(cj)["tolerance"] == {"rel": 1e-9, "floor": 1e-12}


@pytest.mark.parametrize("law", [
    "for x in [0, 1], f(x) == x", "for x in [0, 1], f(x) <= x",
    "for x in [0, 1], f(x) != x"])
def test_a_kind_on_another_relation_is_refused(law):
    with pytest.raises(InvalidConjecture, match="~="):
        claim(law, tolerance={"rel": 1e-9})


@pytest.mark.parametrize("law", [
    "for x in [0, 1], f(x) ~= x + ε",
    "for x in [0, 1], abs(f(x) - x) ~= eps"])
def test_a_kind_where_the_claim_reads_epsilon_is_refused(law):
    with pytest.raises(InvalidConjecture, match="one number"):
        claim(law, tolerance={"rel": 1e-9})


def test_a_kind_on_a_chain_is_refused():
    with pytest.raises(InvalidConjecture, match="chain"):
        claim("for x in [0, 1], 0 <= f(x) <= 1", tolerance={"rel": 1e-9})


@pytest.mark.parametrize("premise", ["x == 1", "x ~= 1", "x != 1"])
def test_a_kind_beside_a_premise_compared_within_it_is_refused(premise):
    rows = _rows(square, f"for x in [0, 3], assuming {premise}, "
                         f"f(x) ~= x * x", {"rel": 1e-9}, route="probe")
    main = _main(rows)
    assert main.verdict.startswith("skipped"), (main.verdict, main.note)
    assert "one number" in main.note, main.note


def test_a_kind_beside_an_ordering_premise_is_read():
    rows = _rows(square, "for x in [0, 3], assuming x >= 1, "
                         "f(x) ~= x * x", {"rel": 1e-9}, route="probe")
    main = _main(rows)
    assert main.verdict == "holds", (main.verdict, main.note)
