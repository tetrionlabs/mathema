# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about two ways a KOINE-route answer could rest
on something false are stated over: a definition whose at_most is not
inside its at_least, which describes no language, and a witness holding
a surrogate pair, which JSON text reads back as another value.

The modules under claim are `mathema.koine.record_relations`,
`mathema.koine.record_claims` and `mathema.koine.solver_question`. Each
function takes an index into `INCONSISTENT` and `DEFINITIONS`, or into
`TEXT_QUESTIONS`, and returns the truth of one statement, so a claim
reads `f(...) == True`. The oracle's `member`
(`tests/_record_language_oracle.py`) places a value."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _language_support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_language_support", _HERE / "koine_record_language_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


L = _language_support()
REF = L.REF
DEFINITIONS = L.DEFINITIONS
WORDS = ["subset", "not subset", "disjoint", "=", "!="]
EMPTY, ANY = {"op": "empty"}, {"op": "any"}


def _pair(at_least, at_most):
    return {"kind": "record_language", "version": 1, "exact": False, "at_least": at_least,
            "at_most": at_most}


def _inverted() -> list:
    """Definitions whose at_most holds a value its at_least does not:
    the catalogue's pairs with their bounds swapped where they differ,
    and three written out."""
    out = [_pair(d["at_most"], d["at_least"]) for d in DEFINITIONS
           if not d["exact"] and d["at_most"] != d["at_least"]]
    return out + [_pair(REF.choice(1), REF.choice(1, 2)), _pair(EMPTY, ANY),
                  _pair(REF.record(("x", REF.FLAG, True)),
                        REF.record(("x", REF.FLAG, False)))]


INCONSISTENT = _inverted()


def _rl():
    return REF._load()


def _breaks_consistency(definition):
    """A value the oracle puts in the definition's at_most and outside
    its at_least, from the oracle's enumerator, or None."""
    found = _rl().find_by_enumeration([definition["at_most"]], [definition["at_least"]])
    return found.member if found.status == "member" else None


def an_inconsistent_definition_decides_nothing(i: int, d: int, w: int) -> bool:
    """Whether relation word `w` between inconsistent definition `i` and
    catalogue definition `d`, either way round, and "every key of every
    member is x" about definition `i`, are each unknown with a reason
    naming a value of its at_most outside its at_least."""
    from mathema.koine import record_claims, record_relations
    bad, other, word = INCONSISTENT[int(i)], DEFINITIONS[int(d)], WORDS[int(w)]
    if _breaks_consistency(bad) is None:
        return False
    decisions = [record_relations.decide(word, bad, other),
                 record_relations.decide(word, other, bad),
                 record_claims.decide_every_member(bad, record_claims.every_key_is_one_of(["x"]))]
    return all(d.verdict == "unknown" and d.witness is None
               and "at_most" in d.reason and "at_least" in d.reason for d in decisions)


def _text(*codes):
    return {"op": "text", "language": {"op": "literal", "codes": list(codes)}}


def _union(*nodes):
    return {"op": "union", "args": list(nodes)}


PAIR_CODES, ASTRAL = (0xD83D, 0xDE00), 0x1F600
#: questions whose members hold texts: (inside, outside, every member
#: holds a surrogate pair)
TEXT_QUESTIONS = [
    ([_text(*PAIR_CODES)], [], True),
    ([_text(*PAIR_CODES)], [_text(ASTRAL)], True),
    ([_union(_text(*PAIR_CODES), _text(ASTRAL))], [], False),
    ([_union(_text(*PAIR_CODES), _text(97))], [_text(ASTRAL)], False),
    ([REF.record(("x", _text(*PAIR_CODES), True))], [], True),
    ([REF.record(("x", _union(_text(*PAIR_CODES), _text(98)), True))], [], False),
    ([_union(_text(0xD800, 0xDC00), _text(0xD800))], [], False),
    ([_text(0xD800, 0xDC00, 97)], [], True),
]


def _holds_a_pair(value) -> bool:
    if isinstance(value, str):
        return any("\ud800" <= a <= "\udbff" and "\udc00" <= b <= "\udfff"
                   for a, b in zip(value, value[1:]))
    if isinstance(value, dict):
        return any(_holds_a_pair(k) or _holds_a_pair(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_holds_a_pair(v) for v in value)
    return False


def a_witness_holds_no_surrogate_pair_where_one_can_be_found(q: int) -> bool:
    """Whether the member found for question `q` is placed by the
    oracle's `member` as asked; holds no surrogate pair when some member
    holds none; and, when every member holds one, comes with a reason
    saying so, while one with no pair reads back from JSON text as
    itself."""
    from mathema.koine import record_membership, solver_question
    inside, outside, only_pairs = TEXT_QUESTIONS[int(q)]
    rl = _rl()
    found = solver_question.find_member(
        [record_membership.membership_document(n) for n in inside],
        [record_membership.membership_document(n) for n in outside])
    if found.status != "member":
        return False
    x = found.member
    if not (all(rl.member(n, x) for n in inside) and not any(rl.member(n, x) for n in outside)):
        return False
    if only_pairs:
        return _holds_a_pair(x) and "surrogate pair" in found.reason
    return not _holds_a_pair(x) and json.loads(json.dumps(x)) == x
