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

from mathema.badges import (TRIANGLE_HIDE_BELOW, TRIANGLE_HIDE_WHEN_COUNT,
                            BadgeScores, _triangle_hidden, render_svg,
                            render_triangle, triangle_area)

_TRIPLES = [(88, 71, 52), (89, 75, 28), (100, 31, 37), (60, 60, 60),
            (100, 100, 0), (100, 0, 50), (5, 5, 5), (100, 100, 100),
            (7, 93, 58)]


def _polygons(svg: str, kind: str) -> list:
    """The polygons of class `kind` in `svg`, each a list of points."""
    out = []
    for pts in re.findall(rf'<polygon class="{kind}" points="([^"]+)"', svg):
        out.append([tuple(float(v) for v in p.split(","))
                    for p in pts.split()])
    return out


def _frame_and_head(svg: str):
    (frame,), (head,) = _polygons(svg, "frame"), _polygons(svg, "head")
    return frame, head


def _area(poly) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                   in zip(poly, poly[1:] + poly[:1]))) / 2.0


def _svg(a, b, c):
    return render_svg(BadgeScores(a, b, c, triangle_area(a, b, c)))


def test_the_svg_frame_has_three_spokes_120_degrees_apart():
    frame, _head = _frame_and_head(_svg(88, 71, 52))
    # centre (100, 100), radius 80, y growing downwards
    assert sorted(frame) == sorted([(100.0, 20.0), (169.3, 140.0),
                                    (30.7, 140.0)])
    angles = sorted(math.degrees(math.atan2(100 - y, x - 100)) % 360
                    for x, y in frame)
    assert angles == pytest.approx([90.0, 210.0, 330.0], abs=0.05)
    spokes = re.findall(r'<line x1="100" y1="100" x2="([^"]+)" y2="([^"]+)"',
                        _svg(88, 71, 52))
    assert sorted((float(x), float(y)) for x, y in spokes) == sorted(frame)


def test_the_svg_rings_sit_at_a_quarter_a_half_and_three_quarters():
    rings = _polygons(_svg(88, 71, 52), "ring")
    radii = sorted(round(math.hypot(x - 100, y - 100), 1)
                   for ring in rings for x, y in ring[:1])
    assert radii == [20.0, 40.0, 60.0]


@pytest.mark.parametrize("triple", _TRIPLES)
def test_the_svg_shaded_share_is_the_overall_number(triple):
    a, b, c = (s / 100.0 for s in triple)
    frame, head = _frame_and_head(_svg(*triple))
    share = 100 * _area(head) / _area(frame)
    # vertices are written to 0.1 px, so the share is exact to about that
    assert share == pytest.approx(100 * (a * b + b * c + c * a) / 3, abs=0.1)


def test_permuting_the_scores_leaves_the_shaded_area_unchanged():
    for triple in ((88, 71, 52), (100, 0, 50), (7, 93, 58)):
        shares = []
        for p in itertools.permutations(triple):
            frame, head = _frame_and_head(_svg(*p))
            shares.append(100 * _area(head) / _area(frame))
        # the same 0.1 px vertex resolution as the share itself
        assert max(shares) - min(shares) <= 0.1


def test_each_svg_score_point_sits_on_its_own_spoke():
    _frame, head = _frame_and_head(_svg(88, 71, 52))
    want = {90: 0.52, 210: 0.88, 330: 0.71}      # clarity, impl, intent
    seen = set()
    for x, y in head:
        deg = round(math.degrees(math.atan2(100 - y, x - 100)) % 360)
        seen.add(deg)
        f = want[deg]
        assert x == pytest.approx(100 + f * 80 * math.cos(math.radians(deg)),
                                  abs=0.06)
        assert y == pytest.approx(100 - f * 80 * math.sin(math.radians(deg)),
                                  abs=0.06)
    assert seen == set(want)


def _texts(svg: str) -> list:
    """Each `<text>` as `(x, y, font_size, anchor, words)`."""
    out = []
    for attrs, body in re.findall(r"<text([^>]*)>(.*?)</text>", svg):
        get = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        out.append((float(get["x"]), float(get["y"]),
                    float(get.get("font-size", 11)),
                    get.get("text-anchor", "start"),
                    re.sub(r"<[^>]+>", "", body)))
    return out


def _box(x, y, size, anchor, words):
    """A text's box, its advance taken as 0.6 em per character (a
    monospace face) and its height from 0.8 em above the baseline to
    0.25 em below."""
    w = 0.6 * size * len(words)
    left = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
    return left, y - 0.8 * size, left + w, y + 0.25 * size


def _overlap(p, q) -> bool:
    return p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3]


def test_the_svg_labels_sit_where_the_layout_puts_them():
    texts = {words.split()[0]: (x, y) for x, y, _s, _a, words
             in _texts(_svg(88, 71, 52))}
    assert texts["CLARITY"] == (100.0, 10.0)       # 10 above the apex
    assert texts["IMPL"] == (30.7, 158.0)          # 18 below its corner
    assert texts["INTENT"] == (169.3, 158.0)
    assert texts["48%"][1] > 168 and texts["overall"][1] > 168


@pytest.mark.parametrize("scores", [
    BadgeScores(None, None, None, None), BadgeScores(100, 100, 100, 100),
    BadgeScores(None, 71, None, None), BadgeScores(88, 71, 52, 48)])
def test_the_svg_labels_never_overlap_even_when_unknown(scores):
    svg = render_svg(scores)
    vx, vy, vw, vh = (float(v) for v in
                      re.search(r'viewBox="([^"]+)"', svg).group(1).split())
    boxes = [_box(*t) for t in _texts(svg)]
    frame = _polygons(svg, "frame")[0]
    figure = (min(x for x, _ in frame), min(y for _, y in frame),
              max(x for x, _ in frame), max(y for _, y in frame))
    for i, b in enumerate(boxes):
        assert vx <= b[0] and b[2] <= vx + vw and vy <= b[1] \
            and b[3] <= vy + vh
        assert not _overlap(b, figure)
        for other in boxes[i + 1:]:
            assert not _overlap(b, other)


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


def _line(x0, y0, x1, y1, ys):
    """The cells of a line stepped along x, with the row for each step
    given by hand in `ys` (offsets from y0)."""
    step = 1 if x1 > x0 else -1
    return {(x0 + step * k, y0 + dy) for k, dy in enumerate(ys)}


def test_the_ascii_score_triangle_is_an_outline_between_its_points():
    # 60/60/60: points (15, 4), (6, 13), (24, 13); the slanted edges step
    # one column per row and the third edge is row 13
    want = ({(15 - k, 4 + k) for k in range(10)}
            | {(15 + k, 4 + k) for k in range(10)}
            | {(x, 13) for x in range(6, 25)})
    out = render_triangle(60, 60, 60)
    assert _cells(out, "•") | _cells(out, "●") == want
    assert _cells(out, "●") == {(15, 4), (6, 13), (24, 13)}
    # 88/71/52: points (15, 5), (2, 14), (26, 14); each slanted edge steps
    # one column at a time, its row the nearest to the true line
    left = _line(15, 5, 2, 14, (0, 1, 1, 2, 3, 3, 4, 5, 6, 6, 7, 8, 8, 9))
    right = _line(15, 5, 26, 14, (0, 1, 2, 2, 3, 4, 5, 6, 7, 7, 8, 9))
    want = left | right | {(x, 14) for x in range(2, 27)}
    out = render_triangle(88, 71, 52)
    assert _cells(out, "•") | _cells(out, "●") == want
    # 100/100/100: the outline is the frame itself, which keeps its dots,
    # with a point at each tip
    full = render_triangle(100, 100, 100)
    assert _cells(full, "•") == set()
    assert _cells(full, "●") == {(15, 0), (0, 15), (30, 15)}
    frame = ({(15 - k, k) for k in range(16)} | {(15 + k, k)
             for k in range(16)} | {(x, 15) for x in range(31)})
    assert _cells(full, "·") | _cells(full, "●") == frame


def test_the_ascii_inside_of_the_score_triangle_is_left_empty():
    # row 10 of 60/60/60 meets the outline at columns 9 and 21
    row = render_triangle(60, 60, 60).split("\n")[1:17][10]
    assert row[9] == "•" and row[21] == "•"
    assert row[10:21].replace("+", " ").strip() == ""
    assert _cells(render_triangle(60, 60, 60), "+") == {(15, 10)}


def test_the_ascii_labels_sit_outside_the_frame():
    out = render_triangle(88, 71, 52).split("\n")
    assert out[0].strip() == "CLARITY 52"
    assert "◆" not in out[0] and "·" not in out[0]
    assert re.fullmatch(r"\s*IMPL 88\s+INTENT 71", out[-2])
    assert out[-1].strip() == "overall 48"
    for line in out[1:-2]:
        assert not re.search(r"[A-Z0-9]", line)


def test_the_ascii_is_byte_stable():
    for triple in _TRIPLES:
        assert render_triangle(*triple) == render_triangle(*triple)


def test_the_triangle_is_hidden_only_when_two_scores_are_under_5():
    assert TRIANGLE_HIDE_BELOW == 5 and TRIANGLE_HIDE_WHEN_COUNT == 2
    assert _triangle_hidden(100, 4, 4) and _triangle_hidden(4, 100, 0)
    assert _triangle_hidden(0, 0, 0)
    assert not _triangle_hidden(100, 100, 0)
    assert not _triangle_hidden(100, 0, 50)        # one zero leaves a wedge
    assert not _triangle_hidden(5, 5, 5)
    assert "no triangle" in render_triangle(100, 4, 4)
    assert "●" not in render_triangle(100, 4, 4)
    assert '<polygon class="head"' not in _svg(100, 4, 4)


def test_one_zero_draws_a_wedge_with_a_corner_at_the_centre():
    frame, head = _frame_and_head(_svg(100, 100, 0))
    assert (100.0, 100.0) in head                  # clarity 0 is the centre
    assert 100 * _area(head) / _area(frame) == pytest.approx(100 / 3,
                                                             abs=0.1)
    out = render_triangle(100, 100, 0)
    assert _cells(out, "●") == {(15, 10), (0, 15), (30, 15)}


def test_both_renderers_hide_the_same_triangles():
    for triple in itertools.product((0, 4, 5, 50, 100), repeat=3):
        shown = not _triangle_hidden(*triple)
        assert ("●" in render_triangle(*triple)) == shown, triple
        assert ('<polygon class="head"' in _svg(*triple)) == shown, triple
