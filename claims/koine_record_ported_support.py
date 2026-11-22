# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims ported to the KOINE route from the oracle's
solver claims are stated over: the laws of inclusion, disjointness and
equality between record languages, that a text of any character is
found, that a value the solver gives is returned only when the
interpreter places it, that no answer is no answer, and that numbers
are told from truth values.

The modules under claim are `mathema.koine.record_relations` and
`mathema.koine.solver_question`, over membership documents
(`mathema.koine.record_membership`). Each function takes indices into
`TERMS` (the terms the KOINE claims range over), `TEXTS` or `SCALARS`,
and returns the truth of one statement, so a claim reads `f(...) ==
True`. The oracle's `member` (`tests/_record_language_oracle.py`) places
a witness."""
from __future__ import annotations

import importlib.util
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
TERMS = L.TERMS
#: texts at the edges of what a text may hold: NUL, the last code
#: point, a surrogate on its own, a character beyond ASCII, the empty text
TEXTS = ["\x00", "\U0010ffff", "\ud800", "é", ""]
#: scalars a choice may list, numbers written as integers and as floats
SCALARS = [0, 1, True, False, 0.0, 1.0, -0.0, 2, "0", "1", None]


def _rr():
    from mathema.koine import record_relations
    return record_relations


def _sq():
    from mathema.koine import solver_question
    return solver_question


def _rm():
    from mathema.koine import record_membership
    return record_membership


def _rl():
    return REF._load()


def _exact(node):
    return REF._exact(node)


def _verdict(word, a, b) -> str:
    return _rr().decide(word, _exact(a), _exact(b)).verdict


def a_term_is_inside_itself_and_disjoint_from_its_complement(t: int) -> bool:
    """Whether term `t` is a subset of itself, and disjoint from its
    complement, both proven."""
    a = TERMS[int(t)]
    return (_verdict("subset", a, a) == "proven"
            and _verdict("disjoint", a, REF.complement(a)) == "proven")


def a_term_is_inside_its_union_and_around_its_intersection(t: int, u: int) -> bool:
    """Whether term `t` is a subset of its union with term `u`, and their
    intersection a subset of `t`, both proven."""
    a, b = TERMS[int(t)], TERMS[int(u)]
    return (_verdict("subset", a, REF.union(a, b)) == "proven"
            and _verdict("subset", REF.inter(a, b), a) == "proven")


def inclusion_is_transitive(t: int, u: int, w: int) -> bool:
    """Whether, when term `t` is proven a subset of `u` and `u` of `w`,
    `t` is proven a subset of `w`."""
    a, b, c = TERMS[int(t)], TERMS[int(u)], TERMS[int(w)]
    if _verdict("subset", a, b) != "proven" or _verdict("subset", b, c) != "proven":
        return True
    return _verdict("subset", a, c) == "proven"


def a_term_equals_its_canonical_form(t: int) -> bool:
    """Whether the membership document of term `t` as written and that of
    its canonical form hold the same values: the solver finds no value
    in one and outside the other, either way."""
    rm, sq = _rm(), _sq()
    a = TERMS[int(t)]
    written = rm.membership_document(a)
    canonical = rm.membership_document(_rl().canonical(a))
    return (sq.find_member([written], [canonical]).status == "none"
            and sq.find_member([canonical], [written]).status == "none")


def a_text_of_any_character_is_found(i: int) -> bool:
    """Whether the one member of a choice of text `i`, and of the text
    node whose language is that text alone, is found: the member is
    that text."""
    rm, sq = _rm(), _sq()
    text = TEXTS[int(i)]
    for node in (REF.choice(text),
                 {"op": "text", "language": {"op": "literal",
                                             "codes": [ord(c) for c in text]}}):
        found = sq.find_member([rm.membership_document(node)], [])
        if not (found.status == "member" and found.member == text
                and type(found.member) is str):
            return False
    return True


def an_unconfirmed_solver_value_is_unknown(t: int) -> bool:
    """Whether, when the value read from the solver's model is replaced
    by one the interpreter does not place as asked (a number that is not
    whole, in no term of the catalogue but `any` and complements), the
    answer for a member of term `t` is unknown with the reason, never a
    member."""
    sq = _sq()
    a = TERMS[int(t)]
    document = _rm().membership_document(a)
    if _rl().member(a, 1.5):
        return True
    reading, read = sq._Reading, sq._Reading.read
    reading.read = lambda self, model, place=None: 1.5
    try:
        found = sq.find_member([document], [])
    finally:
        reading.read = read
    return found.status in ("none", "unknown") and (found.status == "none" or bool(found.reason))


def no_answer_is_unknown(t: int) -> bool:
    """Whether, when the solver gives no answer, the question for a
    member of term `t`, and for a point where its document has no value,
    is unknown with the reason."""
    import z3
    sq = _sq()
    document = _rm().membership_document(TERMS[int(t)])
    checked = sq._checked
    sq._checked = lambda z3_, solver, timeout_ms: z3.unknown
    try:
        answers = [sq.find_member([document], []), sq.find_point_without_value(document)]
    finally:
        sq._checked = checked
    return all(a.status == "unknown" and "no answer" in a.reason for a in answers)


def the_solver_tells_numbers_from_booleans(c: int, d: int) -> bool:
    """Whether the question "in the choice of scalar `c`, outside the
    choice of scalar `d`" finds no value exactly when the two are one
    value by kind and then by value (so 1 and 1.0 are one, and true is
    not 1), and a value it finds is placed by the oracle's `member`."""
    rm, sq, rl = _rm(), _sq(), _rl()
    a, b = REF.choice(SCALARS[int(c)]), REF.choice(SCALARS[int(d)])
    found = sq.find_member([rm.membership_document(a)], [rm.membership_document(b)])
    same = _rl()._scalar_key(SCALARS[int(c)]) == _rl()._scalar_key(SCALARS[int(d)])
    if same:
        return found.status == "none"
    return found.status == "member" and rl.member(a, found.member) \
        and not rl.member(b, found.member)
