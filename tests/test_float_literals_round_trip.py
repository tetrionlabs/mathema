# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A float written in a claim reads back as the same float from every text
mathema renders for it: the canonical statement in a verified record, a
side of a claim, and the operational infinity binding. A value whose short
spelling is already exact keeps it (`1e+100`, `30`); a value that needs
all of its digits gets the shortest spelling that reads back exactly."""
import re
import textwrap

import pytest
import sympy

from mathema.conjecture import claim
from mathema.grammar import render_law_expr, to_canonical
from mathema.records import PseudoInfinity
from mathema.spec import canonical_claim_text

MAX = 1.7976931348623157e308
LONG = 1.2345678901234567e200


def _floats(text):
    """Every float literal in `text`, read the way Python reads it."""
    return [float(m) for m in re.findall(
        r"\d+\.\d+(?:e[+-]?\d+)?|\d+e[+-]?\d+", text)]


@pytest.mark.parametrize("value", [MAX, LONG, 0.1 + 0.2])
def test_canonical_text_keeps_every_digit_a_float_needs(value):
    x = sympy.Symbol("x")
    text = to_canonical(sympy.Float(value) * x)
    assert _floats(text) == [value], text


def test_a_claim_side_keeps_the_largest_float():
    text = render_law_expr("1.7976931348623157e308 * abs(x2)")
    assert _floats(text) == [MAX], text


def test_a_short_float_keeps_its_short_spelling():
    x = sympy.Symbol("x")
    assert to_canonical(sympy.Float(0.5) * x) == "0.5*x"
    assert render_law_expr("2.5 * x") == "2.5*x"


@pytest.mark.parametrize("value", [MAX, LONG])
def test_the_operational_infinity_binding_reads_back_exactly(value):
    text = PseudoInfinity(value, "claim").render()
    assert _floats(text) == [value], text


def test_a_short_operational_infinity_keeps_its_short_spelling():
    assert PseudoInfinity(1e100, "claim").render() == "let |inf| be 1e+100"


def test_rendered_claim_text_keeps_the_operational_infinity():
    cj = claim(f"let |inf| be {LONG!r}, for x in R, f(x) > 0")
    text = canonical_claim_text(cj)
    assert LONG in _floats(text), text


def test_a_verified_record_statement_keeps_every_digit(tmp_path, monkeypatch):
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "halves.py").write_text(textwrap.dedent('''
        def half(a: float) -> float:
            """Half of a."""
            return a / 2
    '''))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "halves.claims.yaml").write_text(textwrap.dedent("""
        halves.half:
          claims:
            - name: below_max
              statement: 'for a in [1, 2], f(a) <= 1.7976931348623157e308'
    """))
    verify_project(str(tmp_path))
    record = (tmp_path / ".mathema" / "verified" / "halves.half.yaml").read_text()
    lines = [ln for ln in record.splitlines() if "statement:" in ln
             and "f(a) <=" in ln]
    assert lines, record
    for line in lines:
        assert _floats(line.split("f(a) <=")[1]) == [MAX], line
