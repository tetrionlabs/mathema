# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's bound on a field of a dataclass parameter (`r.w in [0, 1]`)
bounds every instance the probe draws, whether the parameter's language
is inferred from its annotation or bound in the claim: a witness never
lies outside the bounds the claim states. A field the claim leaves
unbound is drawn as its type is, an int field stays an int."""
import importlib.util
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mathema_language") is None,
    reason="the dataclass language adaptor comes with mathema-language")

RECT = '''
    from dataclasses import dataclass


    @dataclass
    class Rect:
        w: float
        h: float


    @dataclass
    class Tiles:
        n: int
        side: float


    def rect_area(r: Rect) -> float:
        return r.w * r.h


    def tiled(t: Tiles) -> float:
        if not isinstance(t.n, int):
            raise TypeError("a tile count is a whole number")
        return t.n * t.side
'''


@pytest.fixture
def rects(tmp_path, monkeypatch):
    name = "bounded_rects"
    (tmp_path / f"{name}.py").write_text(
        "# SPDX-License-Identifier: BUSL-1.1\n# Copyright 2026 Tetrion Ltd\n"
        + textwrap.dedent(RECT))
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


@pytest.mark.parametrize("statement", [
    "for r.w in [0, 1], r.h in [0, 1], f(r) >= 0",
    "for r in L[bounded_rects.Rect], r.w in [0, 1], r.h in [0, 1], f(r) >= 0",
])
def test_bounded_fields_hold_their_claim(rects, statement):
    (p,) = check_conjectures(rects.rect_area, [claim(statement, route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
    assert p.n > 0, p.note


def test_the_bounded_fields_bound_the_upper_side_too(rects):
    (p,) = check_conjectures(rects.rect_area, [claim(
        "for r.w in [0, 1], r.h in [0, 1], f(r) <= 1", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_an_unbound_field_keeps_its_draw_and_the_bound_one_its_bound(rects):
    (p,) = check_conjectures(rects.rect_area, [claim(
        "for r.w in [0, 1], f(r) >= 0", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    witness = p.counterexample
    w = float(witness.split("w=")[1].split(",")[0])
    h = float(witness.split("h=")[1].split(")")[0])
    assert 0 <= w <= 1, witness
    assert h < 0, witness


def test_a_bounded_int_field_is_drawn_as_an_int(rects):
    (p,) = check_conjectures(rects.tiled, [claim(
        "for t.n in [1, 3], t.side in [0, 1], f(t) <= 3", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
    assert p.n > 0, p.note
