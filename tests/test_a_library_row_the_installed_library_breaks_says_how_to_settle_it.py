# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library row the installed library falsifies on its first
adjudication is wrong about that library, not a defect in the project's
code: the note names the row and the two ways to settle it, recording
the falsification as a discovery or correcting the row in the claims
file that states it, and never asks the project to fix the library."""
from mathema.records import Probe
from mathema.verify import _initially_falsified_hint


def _row(name, surface):
    return Probe(name, "for x in [0, 4], f(x) <= x", "falsified",
                 route="probe", counterexample="x = 0.25",
                 meta={"mathema.surface": surface})


def test_a_falsified_library_row_names_itself_and_both_exits():
    (line,) = _initially_falsified_hint(
        "numpy.sqrt", [_row("below_x", "compendium")], {},
        library_source="claims/numpy.claims.yaml")
    assert "below_x" in line
    assert "mathema accept numpy.sqrt below_x --as discovery" in line
    assert "claims/numpy.claims.yaml" in line
    assert "fix the code" not in line


def test_a_project_function_keeps_its_note():
    (line,) = _initially_falsified_hint("pkg.f", [_row("below_x", "declared")],
                                   {})
    assert "fix the code" in line
