# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A call can hold a hole in one argument and an absence in another. When
it raises and still raises with the hole filled, the raise is the
absence's: it is filed under the absence, and is no evidence about what
f does with the hole."""
import textwrap

import pytest

from tests.test_definition_rows import _record_rows

pytest.importorskip("numpy")


def test_a_raise_from_b_being_none_is_not_held_against_a_hole_in_a(tmp_path):
    from mathema import compendium
    from mathema.verify import verify_project
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "numpy.claims.yaml").write_text(textwrap.dedent("""\
        compendium: numpy
        versions: "*"
        numpy.dot:
          claims:
            - name: of_matrices
              statement: "for a in R^(m,k), b in R^(k,n), f(a, b) ~= a @ b"
        """))
    try:
        verify_project(str(tmp_path), files=[str(claims / "numpy.claims.yaml")])
    finally:
        compendium.uninstall()
    row = _record_rows(tmp_path, "numpy.dot")["missing[a]"]
    assert row["verdict"] == "holds", row
    assert "b = None" not in (row.get("note") or ""), row["note"]


def weigh(a: list, b):
    return sum(x * y for x, y in zip(a, b))


def test_a_policy_rows_own_call_files_the_absences_raise_under_the_absence():
    from mathema import analyze
    from mathema.conjecture import claim
    from mathema.policy import _run_floor
    nan = float("nan")
    domain = claim("for a in [0, 1]^n, b in [0, 1]^n, f(a, b) >= 0").domain
    (call,) = _run_floor(weigh, analyze(weigh), [{"a": [nan, 0.5], "b": None}], domain)
    assert call.raised == "TypeError"
    assert call.keys == [("b", "absent", "None")], call.keys
