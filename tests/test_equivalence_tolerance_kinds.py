# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The tolerance of an `f =:= g` claim has a kind: `{abs: x}` allows
`|a - b| <= x`, `{rel: x}` allows `|a - b| <= x * max(|a|, |b|)`,
`{ulp: n}` allows n units in the last place of `max(|a|, |b|)`, and an
optional `floor: x` is an absolute allowance beside any of them. A bare
number stays an absolute tolerance. The kind governs the computation
row only, the record shows it as written, and a registered equivalence
family receives it as the claim states it."""
import pytest

from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.spec import ClaimsFileError, declare, entry_claims, validate_claims_file
from tests._equivalence_rows import claim_row, computation_row


def _scaled(x: float) -> float:
    return x * 1.000000000001


def _shifted(x: float) -> float:
    return x + 1e-10


def _thirds(x: float) -> float:
    return (x * 3) / 3


def _identity(x: float) -> float:
    return x


def _rows(f, law, tolerance):
    return check_conjectures(f, [claim(law, funcs={"g": _identity},
                                       tolerance=tolerance)])


def test_a_relative_tolerance_scales_with_the_values():
    law = "for x in [1, 1e6], f =:= g"
    absolute = computation_row(_rows(_scaled, law, 1e-9))
    relative = computation_row(_rows(_scaled, law, {"rel": 1e-9}))
    assert absolute.verdict == "falsified", absolute.note
    assert relative.verdict == "holds", (relative.verdict, relative.note)
    assert claim_row(_rows(_scaled, law, {"rel": 1e-9})).verdict \
        == "falsified"


def test_a_floor_allows_a_fixed_gap_beside_a_relative_tolerance():
    law = "for x in [0, 1], f =:= g"
    bare = computation_row(_rows(_shifted, law, {"rel": 1e-12}))
    floored = computation_row(_rows(_shifted, law,
                                    {"rel": 1e-12, "floor": 1e-9}))
    assert bare.verdict == "falsified", bare.note
    assert floored.verdict == "holds", (floored.verdict, floored.note)


def _offset(x: float) -> float:
    return x + 1.5e-9


def test_a_floor_adds_to_the_relative_part():
    from mathema._tolerance import ToleranceKind
    kind = ToleranceKind("rel", 1e-9, 1e-9)
    # gap 1.5e-9 at 1.0: past the relative part (1e-9) and past the
    # floor (1e-9) alone, within their sum (2e-9)
    assert kind.allows(1.0, 1.0 + 1.5e-9)
    assert not kind.allows(1.0, 1.0 + 2.5e-9)
    # 1.0 + 1e-12 lies 1.00009e-12 from 1.0, past the floor alone and
    # within it plus two ulps of 1.0 (4.4e-16)
    ulps = ToleranceKind("ulp", 2, 1e-12)
    assert ulps.allows(1.0, 1.0 + 1e-12)
    assert not ulps.allows(1.0, 1.0 + 1.0006e-12)
    assert ToleranceKind("abs", 1e-9, 1e-9).allows(0.0, 1.9e-9)


def test_a_floor_adds_on_the_computation_row():
    law = "for x in [1, 2], f =:= g"
    rel = computation_row(_rows(_offset, law, {"rel": 1e-9}))
    floor = computation_row(_rows(_offset, law, {"floor": 1e-9, "abs": 0}))
    both = computation_row(_rows(_offset, law, {"rel": 1e-9,
                                                "floor": 1e-9}))
    assert rel.verdict == "falsified", rel.note
    assert floor.verdict == "falsified", floor.note
    assert both.verdict == "holds", (both.verdict, both.note)


def test_units_in_the_last_place_count_the_rounding():
    law = "for x in [-10, 10], f =:= g"
    exact = _rows(_thirds, law, {"ulp": 0})
    assert claim_row(exact).verdict == "proven"
    assert computation_row(exact).verdict == "falsified"
    one = computation_row(_rows(_thirds, law, {"ulp": 1}))
    assert one.verdict == "holds", (one.verdict, one.note)


def test_the_record_shows_the_tolerance_as_written():
    rows = _rows(_scaled, "for x in [1, 1e6], f =:= g",
                 {"rel": 1e-9, "floor": 1e-15})
    for row in rows:
        assert row.tolerance == {"rel": 1e-9, "floor": 1e-15}, row
    cj = claim("for x in [1, 1e6], f =:= g", funcs={"g": _identity},
               tolerance={"floor": 1e-15, "rel": 1e-9})
    written = declare(cj)
    assert written["tolerance"] == {"rel": 1e-9, "floor": 1e-15}
    (back,) = entry_claims({"claims": [written]})
    assert back.tolerance == cj.tolerance


def test_a_bare_number_is_an_absolute_tolerance_as_before():
    cj = claim("for x in [1, 1e6], f =:= g", funcs={"g": _identity},
               tolerance=1e-4)
    assert cj.tolerance == 1e-4
    rows = _rows(_scaled, "for x in [1, 1e6], f =:= g", 1e-4)
    assert all(row.tolerance == 1e-4 for row in rows)


@pytest.mark.parametrize("tolerance", [
    {"rel": -1e-9}, {"rel": 1e-9, "abs": 1e-9}, {"close": 1e-9},
    {"floor": 1e-9}, {"ulp": 1.5}, {"rel": "small"}, {"abs": float("nan")}])
def test_a_tolerance_that_is_not_one_kind_is_refused(tolerance):
    with pytest.raises(InvalidConjecture, match="tolerance"):
        claim("f =:= g", funcs={"g": _identity}, tolerance=tolerance)


def test_a_tolerance_kind_on_a_value_claim_is_refused():
    with pytest.raises(InvalidConjecture, match="=:="):
        claim("for x in [0, 1], f(x) ~= x", tolerance={"rel": 1e-9})


def test_a_claims_file_states_the_kind():
    good = {"pkg.f": {"claims": [
        {"statement": "f =:= g", "tolerance": {"rel": 1e-12,
                                                "floor": 1e-15}}]}}
    validate_claims_file(good, "claims.yaml")
    bad = {"pkg.f": {"claims": [
        {"statement": "f =:= g", "tolerance": {"rel": 1e-12,
                                                "ulp": 4}}]}}
    with pytest.raises(ClaimsFileError, match="tolerance"):
        validate_claims_file(bad, "claims.yaml")


def test_a_registered_family_receives_the_tolerance_as_the_claim_states_it():
    from mathema import families
    seen = []

    class _Family:
        def can_handle(self, fn, facts, claim_name):
            return True

        def routes(self):
            def decide(fn, facts, gfn, gfacts, **kwargs):
                seen.append(kwargs)
                return None
            return {"equivalence": decide}
    families.register("equivalence", _Family())
    try:
        _rows(_scaled, "for x in [1, 2], f =:= g", {"ulp": 4})
        _rows(_scaled, "for x in [1, 2], f =:= g", 1e-4)
    finally:
        families._REGISTRY.pop("equivalence", None)
    kinds, bare = seen
    assert set(kinds) == {"domain", "tolerance", "statement"}
    assert (kinds["tolerance"].kind, kinds["tolerance"].value,
            kinds["tolerance"].floor) == ("ulp", 4, None)
    assert bare["tolerance"] == 1e-4
