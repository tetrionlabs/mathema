# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The triangle is drawn on three spokes from a common centre, 120 degrees
apart: CLARITY straight up, IMPL down-left, INTENT down-right. The frame
is three wedges of area R^2 * sin(120) / 2, and the scored triangle has
wedges a*b, b*c and c*a of the same, so the shaded share of the frame is
(ab + bc + ca) / 3, the overall number."""
import itertools
import math
import re

import pytest

from mathema.badges import (BadgeScores, render_svg, render_triangle,
                            triangle_area)

_TRIPLES = [(88, 71, 52), (89, 75, 28), (100, 31, 37), (60, 60, 60),
            (100, 100, 0), (100, 0, 50), (5, 5, 5), (100, 100, 100),
            (7, 93, 58)]


def _polygons(svg: str) -> list:
    out = []
    for pts in re.findall(r'<polygon points="([^"]+)"', svg):
        out.append([tuple(float(v) for v in p.split(","))
                    for p in pts.split()])
    return out


def _area(poly) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                   in zip(poly, poly[1:] + poly[:1]))) / 2.0


def _svg(a, b, c):
    return render_svg(BadgeScores(a, b, c, triangle_area(a, b, c)))


def test_the_svg_frame_has_three_spokes_120_degrees_apart():
    frame, _shaded = _polygons(_svg(88, 71, 52))
    cx = sum(x for x, _ in frame) / 3
    cy = sum(y for _, y in frame) / 3
    radii = [math.hypot(x - cx, y - cy) for x, y in frame]
    assert max(radii) - min(radii) < 0.1
    angles = sorted(math.degrees(math.atan2(cy - y, x - cx)) % 360
                    for x, y in frame)
    assert angles == pytest.approx([90.0, 210.0, 330.0], abs=0.05)


@pytest.mark.parametrize("triple", _TRIPLES)
def test_the_svg_shaded_share_is_the_overall_number(triple):
    a, b, c = (s / 100.0 for s in triple)
    frame, shaded = _polygons(_svg(*triple))
    share = 100 * _area(shaded) / _area(frame)
    # vertices are written to 0.1 px, so the share is exact to about that
    assert share == pytest.approx(100 * (a * b + b * c + c * a) / 3, abs=0.1)


def test_permuting_the_scores_leaves_the_shaded_area_unchanged():
    for triple in ((88, 71, 52), (100, 0, 50), (7, 93, 58)):
        shares = []
        for p in itertools.permutations(triple):
            frame, shaded = _polygons(_svg(*p))
            shares.append(100 * _area(shaded) / _area(frame))
        # the same 0.1 px vertex resolution as the share itself
        assert max(shares) - min(shares) <= 0.1


def test_each_svg_score_point_sits_on_its_own_spoke():
    svg = _svg(88, 71, 52)
    frame, shaded = _polygons(svg)
    cx = sum(x for x, _ in frame) / 3
    cy = sum(y for _, y in frame) / 3
    r = math.hypot(frame[0][0] - cx, frame[0][1] - cy)
    for (x, y), f, deg in zip(shaded, (0.52, 0.88, 0.71), (90, 210, 330)):
        assert x == pytest.approx(cx + f * r * math.cos(math.radians(deg)),
                                  abs=0.06)
        assert y == pytest.approx(cy - f * r * math.sin(math.radians(deg)),
                                  abs=0.06)


def _cells(text: str, ch: str) -> set:
    lines = text.split("\n")[1:]           # below the CLARITY label
    return {(x, y) for y, line in enumerate(lines)
            for x, c in enumerate(line) if c == ch}


def test_the_ascii_points_land_on_their_spokes():
    # radius 10 rows, columns scaled by sqrt(3), centre at column 15, row
    # 10: a score s on the spoke at angle t sits at
    # (15 + sqrt(3) * 10 * s * cos t, 10 - 10 * s * sin t), rounded, so
    # CLARITY at (15, 10 - 10s), IMPL at (15 - 15s, 10 + 5s) and INTENT
    # at (15 + 15s, 10 + 5s)
    assert _cells(render_triangle(100, 100, 100), "●") == \
        {(15, 0), (0, 15), (30, 15)}
    assert _cells(render_triangle(40, 40, 40), "●") == \
        {(15, 6), (9, 12), (21, 12)}
    assert _cells(render_triangle(88, 71, 52), "●") == \
        {(15, 5), (2, 14), (26, 14)}
    assert _cells(render_triangle(88, 71, 52), "+") == {(15, 10)}
    assert _cells(render_triangle(60, 60, 60), "◆") == \
        {(15, 0), (0, 15), (30, 15)}


def test_each_ascii_edge_steps_one_column_per_row():
    rows = render_triangle(60, 60, 60).split("\n")[1:16]
    for y, line in enumerate(rows[:-1]):
        assert line[15 - y] in "·◆" and line[15 + y] in "·◆"


def test_the_ascii_labels_sit_outside_the_frame():
    out = render_triangle(88, 71, 52).split("\n")
    assert out[0].strip() == "CLARITY 52"
    assert "◆" not in out[0] and "·" not in out[0]
    assert re.fullmatch(r"\s*IMPL 88\s+INTENT 71", out[-2])
    assert out[-1].strip() == "overall 48"
    for line in out[1:-2]:
        assert not re.search(r"[A-Z0-9]", line)


def test_the_ascii_is_byte_stable_and_keeps_the_degenerate_rule():
    for triple in _TRIPLES:
        assert render_triangle(*triple) == render_triangle(*triple)
    assert "below 5%" in render_triangle(100, 100, 0)
    assert "below 5%" in render_triangle(100, 0, 50)
    assert "●" in render_triangle(5, 5, 5)
