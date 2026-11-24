# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about the verdict family runner
(`mathema._devtools.verdict_families`) are stated over. Each takes small
integers a claim can enumerate, maps them to the runner's inputs, and
returns a value a claim can compare.

`VERDICTS` and `TRUTHS` index the verdicts and truths a row can carry;
`classify_code` and the `is_*` functions read the runner's
`classify`; `stated_class` states the same classification a second
way, as an ordered list of conditions.

`TABLE` is a fixed table of tiny cases over the functions below; the
ground truth of each is known by construction."""
from __future__ import annotations

from mathema._devtools import verdict_families as V

VERDICTS = ("proven", "holds", "unknown", "skipped", "falsified")
TRUTHS = (None, True, False)


def classify_code(base: int, base_wrong: int, head: int, head_wrong: int, truth: int) -> int:
    """The index in `V.CLASSES` of the runner's class for one row."""
    cls = V.classify(VERDICTS[base], bool(base_wrong), VERDICTS[head], bool(head_wrong),
                     TRUTHS[truth])
    return V.CLASSES.index(cls)


def stated_class(base: int, base_wrong: int, head: int, head_wrong: int, truth: int) -> int:
    """The class the runner's documentation states, as the first
    condition of an ordered list that a row meets."""
    b, h, t = VERDICTS[base], VERDICTS[head], TRUTHS[truth]
    rules = [
        (base_wrong == 1 and head_wrong == 0, "fixed"),
        (head_wrong == 1 and base_wrong == 0, "newly wrong"),
        (b == h, "unchanged"),
        (base_wrong == 1, "still wrong"),
        (b == "proven" and t in (None, True), "lost"),
        (b == "falsified" and t in (None, False), "lost"),
        (h in ("proven", "falsified"), "gained"),
        (h == "holds" and b in ("unknown", "skipped"), "gained"),
        (True, "moved"),
    ]
    return V.CLASSES.index(next(name for met, name in rules if met))


def is_fixed(base: int, base_wrong: int, head: int, head_wrong: int, truth: int) -> bool:
    return classify_code(base, base_wrong, head, head_wrong, truth) == V.CLASSES.index(V.FIXED)


def is_newly_wrong(base: int, base_wrong: int, head: int, head_wrong: int, truth: int) -> bool:
    return classify_code(base, base_wrong, head, head_wrong, truth) == V.CLASSES.index(V.NEWLY_WRONG)


def is_lost(base: int, base_wrong: int, head: int, head_wrong: int, truth: int) -> bool:
    return classify_code(base, base_wrong, head, head_wrong, truth) == V.CLASSES.index(V.LOST)


# the tiny cases

def successor(x):
    return x + 1


def refuses_negative(x):
    if x < 0:
        raise ValueError("n")
    return x


def same_text(text):
    return text


_HERE = "claims.verdict_families_support"
TABLE = (
    # (function, claim, ground truth kind, the failing x or None)
    ("successor", "for x in [0, 1], f(x) == x + 1", V.TRUE_EVERYWHERE, None),
    ("successor", "for x in [0, 1], f(x) > 1", V.FALSE_AT, 0),
    ("refuses_negative", "for x in [-2, -1], raises(f(x), ValueError)", V.TRUE_EVERYWHERE, None),
    ("refuses_negative", "for x in [-2, 0], raises(f(x), ValueError)", V.FALSE_AT, 0),
    ("successor", "for x in {1, None}, f(x) == x + 1", V.FALSE_AT, None),
    # the float just below 1, plus 1, rounds to 2.0
    ("successor", "for x in (0, 1), f(x) < 2", V.FALSE_AT, 0.9999999999999999),
    ("same_text", "for text in L[anytext], f(text) == text", V.CANNOT, None),
    ("successor", "for x in {1, ..., 5}, f(x) > 1", V.CANNOT, None),
    ("successor", "for x in [0, 1], f(x) =:= x + 1", V.CANNOT, None),
    ("successor", "for x in Z, f(x) > x", V.TRUE_EVERYWHERE, None),
)
KINDS = (V.TRUE_EVERYWHERE, V.FALSE_AT, V.TRUE_AT, V.NOT_WITNESSED, V.CANNOT)


def _case(i: int) -> V.Case:
    fn, text, _kind, _x = TABLE[i]
    return V.Case(f"table.{i}", f"{_HERE}:{fn}", text, "table")


def ground_truth_kind(i: int) -> int:
    """The index in `KINDS` of the ground truth of table row `i`."""
    return KINDS.index(V.ground_truth(_case(i)).kind)


def stated_kind(i: int) -> int:
    """The index in `KINDS` the table states for row `i`."""
    return KINDS.index(TABLE[i][2])


def failing_point_found(i: int) -> bool:
    """Whether a row stated false is found false at the stated x (or at
    None), and a row stated otherwise carries no point."""
    found = V.ground_truth(_case(i))
    if TABLE[i][2] != V.FALSE_AT:
        return found.point is None
    return found.point is not None and found.point.get("x") == TABLE[i][3]


def witness_replays(i: int, x: int) -> bool:
    """Whether a printed witness `x = <x>` of table row `i` fails the
    claim when called, read back by the runner."""
    case = _case(i)
    point = V.witness_point(f"x = {x}: 0 vs 1", ["x"])
    return point is not None and V.witness_fails(case, point) is True


def ground_truth_as_stated(i: int) -> bool:
    """Whether table row `i` has the ground truth the table states."""
    return ground_truth_kind(i) == stated_kind(i)


def false_point_as_stated(i: int) -> bool:
    """`failing_point_found`, as one call a claim can enumerate."""
    return failing_point_found(i) == True  # noqa: E712


def replays(i: int, x: int) -> bool:
    """`witness_replays`, as one call a claim can enumerate."""
    return witness_replays(i, x) == True  # noqa: E712


# domains, as the ground truth reads them from a claim's text

DOMAINS = ("[0, 1]", "(0, 1)", "[0, 1)", "(0, 1]", "[-5, -1]", "{0, 1}", "{1, None}",
           "{1, nan}", "[0, 1] | absent", "[0, 1] ∪ [3, 4]", "[0, 10] subset Z", "Z", "N", "R",
           "[0, oo)", "(-oo, oo)", "[0, 2] \\ {1}")
CLOSED_ENDS = {0: (0, 1), 2: (0,), 3: (1,), 4: (-5, -1), 9: (0, 1, 3, 4), 10: (0, 10), 14: (0,),
               16: (0, 2)}
OPEN_ENDS = {1: (0, 1), 2: (1,), 3: (0,), 14: (), 15: ()}


def _domain(i: int):
    return V.parse_domain(DOMAINS[i], 0)[0]


def tried_points_inside(i: int) -> bool:
    """Whether every point tried for domain `i` lies inside it."""
    dom = _domain(i)
    return all(dom.contains(p) for p in dom.points())


def outside_points_outside(i: int) -> bool:
    """Whether every point tried outside domain `i` lies outside it, and
    none of them is a missing value."""
    dom = _domain(i)
    return all(not dom.contains(p) and p is not None and p == p for p in dom.outside())


def closed_ends_tried(i: int) -> bool:
    """Whether each closed finite end of domain `i` is among the points
    tried, and no open end is."""
    pts = _domain(i).points()
    closed = CLOSED_ENDS.get(i, ())
    opened = OPEN_ENDS.get(i, ())
    return all(any(p == e for p in pts) for e in closed) and not any(
        any(p == e for p in pts) for e in opened)


def missing_listed_tried(i: int) -> bool:
    """Whether each missing value a domain names is among its points."""
    pts = _domain(i).points()
    has_none = any(p is None for p in pts)
    has_nan = any(isinstance(p, float) and p != p for p in pts)
    text = DOMAINS[i]
    return has_none == ("None" in text or "absent" in text) and has_nan == ("nan" in text)


WITNESSES = (
    ("x = 1.0: 2.0 vs 3.0", ("x",), {"x": 1.0}),
    ("x = -5, y = None: KeyError", ("x", "y"), {"x": -5, "y": None}),
    ("x = nan: 1.0 vs 0", ("x",), {"x": float("nan")}),
    ("text = 'a, b': 'A' vs 'a'", ("text",), {"text": "a, b"}),
    ("x = 0.5", ("x",), {"x": 0.5}),
    ("f changes the module-level _log", ("x",), None),
    ("fn = <function g at 0x1>: 'g' vs 'h'", ("fn",), None),
    ("x = 1, y = 2", ("x",), {"x": 1}),
)


def witness_reads_back(i: int) -> bool:
    """Whether printed witness `i` reads back as the stated point (or as
    nothing, where it names no point)."""
    text, names, stated = WITNESSES[i]
    found = V.witness_point(text, list(names))
    if stated is None or found is None:
        return found is None and stated is None
    return set(found) == set(stated) and all(V.same_value(found[k], stated[k]) for k in stated)
