# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A probe's sampling note says how the sequences it checked were drawn.

The note (`meta["mathema.sampling"]`) states, per sequence parameter,
the lengths the checked samples actually had, how their elements were
drawn (the declared element domain, where the special shapes are not
used, or the free draw with its shapes), and when a premise drew the
parameter directly. A premise that fixes the length is visible as that
one length.
"""
from mathema.claims import check_conjectures, claim


def total(xs: list) -> float:
    return sum(xs)


def _note(law):
    (p,) = check_conjectures(total, [claim(law, route="probe")])
    assert p.verdict in ("holds", "falsified"), (p.verdict, p.note)
    return p.meta["mathema.sampling"]


def test_a_premise_fixed_length_is_reported_as_that_length():
    note = _note("for xs in R^n, assuming dim(xs) == 20, "
                 "f(xs) == f(xs)")
    assert "len=20" in note, note
    assert "len∈[1,8]" not in note, note


def test_the_free_draw_reports_the_lengths_it_used_and_its_shapes():
    note = _note("f(xs) == f(xs)")
    assert "len∈[1,8]" in note, note
    assert "shape∈{" in note, note


def test_an_element_bound_is_reported_and_the_shapes_are_not():
    note = _note("for xs in [0, 1]^n, f(xs) >= 0")
    assert "shape∈{" not in note, note
    assert "elem~U(0,1)" in note, note
    note = _note("for xs in R^n, f(xs) == f(xs)")
    assert "shape∈{" not in note, note
    assert "elem~U(-10,10)" in note, note


def test_a_length_floor_reports_the_lengths_drawn_above_it():
    note = _note("for xs in R^n, assuming dim(xs) >= 5, f(xs) == f(xs)")
    lengths = note.split("len∈[", 1)[1].split("]", 1)[0].split(",")
    assert int(lengths[0]) >= 5, note


def test_a_premise_directed_draw_is_named():
    note = _note("for xs in R^n, assuming dim(xs) == 0, f(xs) == 0")
    assert "len=0" in note, note
    assert "drawn on the premise" in note, note
