# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The named collections the claims about `mathema._collection` range
over, and the functions those claims compare against: every combination
of member verdicts up to three members, members with the names they are
reported by, pairs of members with the same and with different hashes,
and pairs of collection records with the sentence verify reports for
what moved between them."""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from mathema._collection import collection_record, listed_members


def first_stage(percent: float) -> float:
    """A percent as a fraction."""
    return percent / 100


def second_stage(fraction: float) -> float:
    """A fraction as the factor it grows a value by."""
    return 1 + fraction


@dataclass(frozen=True)
class Box:
    """A box of whole-number sides."""
    width: int
    height: int


#: the verdicts a member can come back with
VERDICTS = ("proven", "holds", "falsified", "unknown", "skipped:misspecified")

#: every sequence of member verdicts of length 0 to 3
OUTCOMES = tuple(combo for size in range(4)
                 for combo in itertools.product(VERDICTS, repeat=size))

#: how strongly each verdict supports a claim; anything unlisted is 1
_STRENGTH = {"falsified": 0, "holds": 2, "proven": 3}
_WORD = {0: "falsified", 1: "unknown", 2: "holds", 3: "proven"}


def roll_up_stated(verdicts: tuple) -> tuple:
    """The collection's verdict as the weakest member's, strength
    falsified < unknown < holds < proven, with the first member at that
    strength; proven with no member named when every member is proven,
    or there are none."""
    strengths = [_STRENGTH.get(v.split(":")[0], 1) for v in verdicts]
    weakest = min(strengths, default=3)
    if weakest == 3:
        return ("proven", None)
    return (_WORD[weakest], strengths.index(weakest))


#: members and the names they are reported by
NAMES = (
    (first_stage, "claims.collection_support.first_stage"),
    (Box, "claims.collection_support.Box"),
    (3, "3"),
    ("text", "'text'"),
    ((1, "a"), "(1, 'a')"),
    (Box(1, 2), "Box(width=1, height=2)"),
    ("x" * 70, "'" + "x" * 56 + "..."),
)

#: dict members, their keys and the names they are reported by
KEYED_NAMES = (
    ("scale", first_stage, "'scale': claims.collection_support.first_stage"),
    (2, 0.5, "2: 0.5"),
)

#: pairs of members that are the same value, so hash the same
SAME = (
    (Box(1, 2), Box(1, 2)),
    ((1, 2), (1, 2)),
    ("a", "a"),
    (first_stage, first_stage),
    ({"k": [1, 2]}, {"k": [1, 2]}),
)

#: pairs of members that differ, so hash differently
DIFFERENT = (
    (Box(1, 2), Box(2, 1)),
    ((1, 2), (2, 1)),
    ("a", "b"),
    (1, 1.0),
    (True, 1),
    (first_stage, second_stage),
    ({"k": [1, 2]}, {"k": [2, 1]}),
)


def _record(value) -> dict:
    kind, members = listed_members(value)
    return collection_record("p.C", kind, members)


_ONE = (first_stage, second_stage)

#: (recorded, now, the sentence verify reports): a member added,
#: removed, reordered, and a list for a tuple
MOVES = (
    (_record(_ONE), _record((first_stage,)),
     "the collection p.C moved: claims.collection_support.second_stage removed"),
    (_record((first_stage,)), _record(_ONE),
     "the collection p.C moved: claims.collection_support.second_stage added"),
    (_record(_ONE), _record((second_stage, first_stage)),
     "the collection p.C moved: its members reordered"),
    (_record(_ONE), _record(list(_ONE)), "the collection p.C moved: it is now a list"),
    (_record((1, 2)), _record((1, 3)), "the collection p.C moved: 3 added, 2 removed"),
)


#: collections listed twice over, so nothing moved between the two
UNMOVED = (_ONE, (1, 2), [first_stage], {"a": Box(1, 2)}, frozenset({"a", "b"}), ())


def unmoved(value) -> bool:
    """Whether a collection listed twice over moved between the two
    listings: the comparison verify makes finds nothing moved."""
    from mathema._collection import collection_moved
    return collection_moved(_record(value), _record(value)) is None


def listed_names(value) -> tuple:
    """The names of a collection's members, in the order it lists
    them."""
    return tuple(m.name for m in listed_members(value)[1])


#: collections and the names of their members in the order they are
#: listed: a tuple's and a list's in order, a dict's by key, a
#: frozenset's sorted
LISTINGS = (
    ((3, 1, 2), ("3", "1", "2")),
    ([second_stage, first_stage], ("claims.collection_support.second_stage",
                                   "claims.collection_support.first_stage")),
    ({"b": 1, "a": 2}, ("'b': 1", "'a': 2")),
    (frozenset({"b", "a", "c"}), ("'a'", "'b'", "'c'")),
    ((), ()),
)
