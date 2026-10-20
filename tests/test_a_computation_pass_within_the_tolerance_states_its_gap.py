# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A computation line that passes with a non-zero gap says so: its note
states the largest gap and the tolerance it fell within, for `==` as for
`<=` and `>=`, so a reader can tell a bit-exact pass from one the
tolerance absorbed. The verdict does not change. A pass with no gap
carries no such clause."""
import mathema
from mathema.conjecture import check_conjectures, claim
from tests._equivalence_rows import claim_row, computation_row


def lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def lerp_weighted(a: float, b: float, t: float) -> float:
    return (1 - t) * a + t * b


def _probe(fn, text, **kwargs):
    (p,) = check_conjectures(fn, [claim(text, name="point", route="probe",
                                        **kwargs)])
    return p


_SAMPLED = "for b in [0.29, 0.31], f(-0.1, b, 1) == b"


def test_an_equality_the_default_tolerance_absorbed_states_its_gap():
    # lerp(-0.1, b, 1) misses b by a rounding at many b, as at b = 0.3,
    # where it gives 0.30000000000000004
    p = _probe(lerp, _SAMPLED)
    assert p.verdict == "holds", p
    clause = next(c for c in p.note.split("; ") if c.startswith("differs by"))
    assert " at b = " in clause, clause
    assert "within the default tolerance (" in clause, clause
    gap = float(clause.split()[2])
    assert 0 < gap < 1e-15, clause


def test_the_record_prints_the_gap_on_the_computation_line():
    rec = mathema.check(lerp, claims=[mathema.claim(
        _SAMPLED, name="point", route="probe")])
    line = next(ln for ln in str(rec).splitlines()
                if "computation" in ln and "draws" in ln)
    assert "differs by " in line and "within the default tolerance" in line, \
        str(rec)


def test_a_declared_tolerance_is_named():
    p = _probe(lerp, _SAMPLED, tolerance=1e-12)
    assert p.verdict == "holds", p
    assert "within the tolerance (declared 1e-12)" in p.note, p.note


def test_an_inequality_with_a_declared_tolerance_states_its_gap():
    p = _probe(lerp, "for b in [0.29, 0.31], f(-0.1, b, 1) <= b",
               tolerance=1e-12)
    assert p.verdict == "holds", p
    assert "fails by " in p.note, p.note
    assert "within the tolerance (declared 1e-12)" in p.note, p.note


def test_an_inequality_names_the_default_allowance_at_its_point():
    # the default allowance against b near 0.3 is relative to b, about
    # 3e-08 there (1e-7 * 0.31 + 1e-9 = 3.2e-08 at the largest counted
    # gap), not its absolute floor 1e-09
    p = _probe(lerp, "for b in [0.29, 0.31], f(-0.1, b, 1) <= b")
    assert p.verdict == "holds", p
    assert "within the default tolerance (3.2e-08)" in p.note, p.note


def test_a_bit_exact_pass_carries_no_gap():
    p = _probe(lerp_weighted, _SAMPLED)
    assert p.verdict == "holds", p
    assert "differs by" not in (p.note or ""), p.note
    assert "within the" not in (p.note or ""), p.note


def _shifted(x: float) -> float:
    return (x + 0.1) - 0.1


def _same(x: float) -> float:
    return x


def test_the_equivalence_computation_row_states_its_largest_gap():
    rows = check_conjectures(_shifted, [claim(
        "for x in [0, 1], f =:= g", funcs={"g": _same})])
    main, computation = claim_row(rows), computation_row(rows)
    assert main.verdict == "proven", main
    assert computation.verdict == "holds", computation
    clause = next(c for c in computation.note.split("; ")
                  if c.startswith("differs by"))
    assert " at x = " in clause, clause
    assert "within the default tolerance (" in clause, clause


def test_an_equivalence_that_agrees_bit_for_bit_carries_no_gap():
    rows = check_conjectures(_same, [claim(
        "for x in [0, 1], f =:= g", funcs={"g": _same})])
    computation = computation_row(rows)
    assert computation.verdict == "holds", computation
    assert "differs by" not in computation.note, computation.note
