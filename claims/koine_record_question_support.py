# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about the solver question derived from KOINE
membership functions are stated over.

The modules under claim are `mathema.koine.solver_question` (the
formula a function of one JSON value is read as, and the one question
asked of such formulas) and `mathema.koine.record_relations` (the
relations between two record languages that follow from the question).

Each function takes indices into the catalogues of
`claims/koine_record_language_support.py` (`TERMS`, `VALUES`,
`DEFINITIONS`) and into `EXPRESSIONS`, single terms and small
combinations of them, some with no value at some points. Each returns
the truth of one statement. `mathema.record_language` is what the
answers are compared with: its `member` for a value, its `find_member`
for a question."""
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


BASE = _language_support()
REF = BASE.REF
TERMS = BASE.TERMS
VALUES = BASE.VALUES
DEFINITIONS = BASE.DEFINITIONS
CHILD, PARENT, WIDENED = REF.CHILD, REF.PARENT, REF.WIDENED
WORDS = ["subset", "not subset", "disjoint", "=", "!="]


def _sq():
    from mathema.koine import solver_question
    return solver_question


def _rr():
    from mathema.koine import record_relations
    return record_relations


def _rt():
    from mathema.koine import record_terms
    return record_terms


def _rm():
    from mathema.koine import record_membership
    return record_membership


def _rl():
    from mathema import record_language
    return record_language


def _document(t: int):
    return _rm().membership_document(TERMS[int(t)])


def _expressions() -> list:
    """Expressions of the one value: each term alone, equality with a
    constant of each kind with no test of kind before it, and
    conjunctions and disjunctions whose later part has no value where
    an earlier part does not stop the evaluation."""
    from mathema.koine import language_terms as lt
    from mathema.koine.syntax import Bool, Int, List, Name, Str, Term
    rt = _rt()
    v = Name(rt.PARAMETER)
    p = Term(rt.VALUE_OF_PRESENT, (v,))
    at_x = Term(rt.VALUE_AT_KEY, (p, Str("x")))
    def equal(a, b):
        return Term("operator::comparison::equal", (a, b))
    def kind(e, k):
        return Term(rt.IS_OF_KIND, (e, Term(k)))
    has_x = Term(rt.HAS_KEY, (p, Str("x")))
    a_map = kind(v, "kind::dict")
    return [
        Bool(True), Bool(False), Term(rt.IS_ABSENT, (v,)),
        *[kind(v, k) for k in rt.TESTED_KINDS],
        equal(p, Bool(True)), equal(p, Bool(False)), equal(p, Int(1)), equal(p, Int(0)),
        equal(p, Int(2)), equal(p, Str("a")), equal(p, Str("")), equal(Int(1), p),
        equal(v, Int(1)), equal(v, Bool(True)),
        Term("operator::comparison::not_equal", (p, Int(1))),
        has_x, Term(rt.IS_ABSENT, (at_x,)), kind(at_x, "kind::bool"),
        Term(rt.HAS_NO_KEY_OTHER_THAN, (p, List(()))),
        Term(rt.HAS_NO_KEY_OTHER_THAN, (p, List((Str("x"), Str("y"))))),
        lt.in_language(p, REF.DOLLAR), lt.in_language(p, REF.SHALLOW),
        Term("operator::logic::and", (a_map, has_x)),
        Term("operator::logic::and", (has_x, a_map)),
        Term("operator::logic::or", (Term("operator::logic::not", (a_map,)), has_x)),
        Term("operator::logic::or", (has_x, Term("operator::logic::not", (a_map,)))),
        Term("operator::logic::and", (a_map, has_x, equal(Term(rt.VALUE_OF_PRESENT, (at_x,)),
                                                          Bool(True)))),
        Term("operator::logic::and", (a_map, has_x, kind(at_x, "kind::dict"),
                                      Term(rt.HAS_KEY, (Term(rt.VALUE_OF_PRESENT, (at_x,)),
                                                        Str("z"))))),
        Term("operator::logic::not", (equal(p, Str("a")),)),
    ]


EXPRESSIONS = 35


def the_formula_of_a_term_is_its_meaning(e: int, v: int) -> bool:
    """Whether the formula expression `e` is read as has, at value `v`,
    the truth the interpreter gives the expression there, and no value
    where the interpreter gives none or does not run."""
    from mathema.koine.interpret import InterpretError, Value
    rt, sq, value = _rt(), _sq(), VALUES[int(v)]
    document = rt.function_of_one_value(_expressions()[int(e)])
    try:
        outcome = rt.interpret(document, [value])
    except InterpretError:
        outcome = None
    want = outcome.value if isinstance(outcome, Value) else None
    return sq.derived_truth_at(document, value) is want


def the_formula_of_a_membership_document_is_member(t: int, v: int) -> bool:
    """Whether the formula the membership document of term `t` is read
    as has, at value `v`, the truth `record_language.member` gives."""
    term, value = TERMS[int(t)], VALUES[int(v)]
    return _sq().derived_truth_at(_document(t), value) is _rl().member(term, value)


def a_found_value_is_placed_by_both_meanings(t: int, u: int) -> bool:
    """Whether a value found inside the document of term `t` and
    outside that of term `u` is placed so by the interpreter on the two
    documents and by `record_language.member` on the two terms."""
    from mathema.koine.interpret import Value
    rt, rl = _rt(), _rl()
    a, b = _document(t), _document(u)
    found = _sq().find_member([a], [b])
    if found.status != "member":
        return True
    x = found.member
    return (rt.interpret(a, [x]) == Value(True) and rt.interpret(b, [x]) == Value(False)
            and rl.member(TERMS[int(t)], x) and not rl.member(TERMS[int(u)], x))


def the_question_agrees_with_the_reference(t: int, u: int) -> bool:
    """Whether the question over the documents of terms `t` and `u`
    has the status `record_language.find_member` gives over the two
    terms, and that status is an answer: a member or none."""
    found = _sq().find_member([_document(t)], [_document(u)])
    reference = _rl().find_member([TERMS[int(t)]], [TERMS[int(u)]])
    return found.status == reference.status and found.status in ("member", "none")


def none_means_no_catalogue_value(t: int, u: int) -> bool:
    """Whether, when the question finds no value inside the document
    of term `t` and outside that of term `u`, no value of the catalogue
    is, by `record_language.member`."""
    rl = _rl()
    if _sq().find_member([_document(t)], [_document(u)]).status != "none":
        return True
    return not any(rl.member(TERMS[int(t)], x) and not rl.member(TERMS[int(u)], x)
                   for x in VALUES)


def several_documents_are_asked_at_once(t: int, u: int, w: int) -> bool:
    """Whether the question with two documents inside and one outside
    has the status the reference gives the same three terms."""
    found = _sq().find_member([_document(t), _document(u)], [_document(w)])
    reference = _rl().find_member([TERMS[int(t)], TERMS[int(u)]], [TERMS[int(w)]])
    return found.status == reference.status


def a_membership_document_has_a_value_everywhere(t: int) -> bool:
    """Whether no JSON value is found at which the membership document
    of term `t` has no value."""
    return _sq().find_point_without_value(_document(t)).status == "none"


def a_document_without_a_value_somewhere_is_not_an_answer(e: int) -> bool:
    """Whether, for expression `e`: a point found where it has no value
    is one where the interpreter gives none or does not run; and when
    such a point exists, the question with the expression's document
    outside gives no answer, with the reason."""
    from mathema.koine.interpret import InterpretError, Value
    rt, sq = _rt(), _sq()
    document = rt.function_of_one_value(_expressions()[int(e)])
    found = sq.find_point_without_value(document)
    if found.status == "none":
        return True
    if found.status != "member":
        return False
    try:
        if isinstance(rt.interpret(document, [found.member]), Value):
            return False
    except InterpretError:
        pass
    asked = sq.find_member([], [document])
    return asked.status == "unknown" and "no value" in asked.reason


def the_child_is_inside_its_parent() -> bool:
    """Whether the nested configuration record is a subset of the wider
    one; the child with `publish` widened is not a subset of the child,
    by a value holding `publish` true that `record_language.member`
    puts in the widened record and outside the child; and the parent is
    not a subset of the child."""
    rr, rl = _rr(), _rl()
    child, parent, widened = (REF._exact(n) for n in (CHILD, PARENT, WIDENED))
    proven = rr.decide("subset", child, parent)
    falsified = rr.decide("subset", widened, child)
    witness = falsified.witness
    return (proven.verdict == "proven" and proven.witness is None
            and falsified.verdict == "falsified" and isinstance(witness, dict)
            and witness.get("publish") is True
            and rl.member(WIDENED, witness) and not rl.member(CHILD, witness)
            and rr.decide("subset", parent, child).verdict == "falsified"
            and rr.decide("not subset", widened, child).verdict == "proven"
            and rr.decide("not subset", child, parent).verdict == "falsified")


def _reference_verdict(word: str, a: dict, b: dict) -> str:
    if word in ("subset", "not subset"):
        verdict = REF.includes(a, b)[0]
    elif word == "disjoint":
        verdict = REF.disjoint(a, b)[0]
    else:
        verdict = REF.equal(a, b)[0]
    if word in ("not subset", "!=") and verdict != "unknown":
        return "falsified" if verdict == "proven" else "proven"
    return verdict


def a_relation_agrees_with_the_reference(t: int, u: int, w: int) -> bool:
    """Whether relation word `w` between the exact definitions of terms
    `t` and `u` has the verdict the reference's inclusion, disjointness
    and equality give, and a witness it carries is placed by
    `record_language.member` as the verdict says."""
    rl, word = _rl(), WORDS[int(w)]
    a, b = TERMS[int(t)], TERMS[int(u)]
    decided = _rr().decide(word, REF._exact(a), REF._exact(b))
    if decided.verdict != _reference_verdict(word, a, b):
        return False
    if decided.witness is None:
        return decided.verdict == ("proven" if word in ("subset", "disjoint", "=")
                                   else "falsified")
    x = decided.witness
    if word == "disjoint":
        return rl.member(a, x) and rl.member(b, x)
    return rl.member(a, x) != rl.member(b, x)


def a_relation_of_two_bounds_is_decided_on_the_right_side(d: int, e: int, w: int) -> bool:
    """Whether, for definitions `d` and `e` that may each be a pair of
    bounds and the universal word `w` (subset, disjoint or =): a proven
    verdict means no catalogue value breaks the relation between the
    at_least bounds, which hold every member; and a falsified one
    carries a value that breaks it between the at_most bounds, which
    hold only members."""
    rl, word = _rl(), ("subset", "disjoint", "=")[int(w)]
    left, right = DEFINITIONS[int(d)], DEFINITIONS[int(e)]

    def breaks(x, bound: str) -> bool:
        a, b = rl.member(left, x, bound=bound), rl.member(right, x, bound=bound)
        if word == "disjoint":
            return a and b
        return (a and not b) if word == "subset" else (a != b)
    decided = _rr().decide(word, left, right)
    if decided.verdict == "proven":
        if word == "subset":
            return not any(rl.member(left, x, bound="at_least")
                           and not rl.member(right, x, bound="at_most") for x in VALUES)
        if word == "disjoint":
            return not any(breaks(x, "at_least") for x in VALUES)
        return not any(rl.member(left, x, bound="at_least")
                       != rl.member(right, x, bound="at_most") for x in VALUES) \
            and not any(rl.member(left, x, bound="at_most")
                        != rl.member(right, x, bound="at_least") for x in VALUES)
    if decided.verdict == "falsified":
        x = decided.witness
        if word == "subset":
            return rl.member(left, x, bound="at_most") \
                and not rl.member(right, x, bound="at_least")
        if word == "disjoint":
            return breaks(x, "at_most")
        return (rl.member(left, x, bound="at_most")
                and not rl.member(right, x, bound="at_least")) \
            or (rl.member(right, x, bound="at_most")
                and not rl.member(left, x, bound="at_least"))
    return decided.verdict == "unknown" and bool(decided.reason)


def generated_questions_agree_with_the_reference(seed: int) -> bool:
    """Whether, for two terms and forty values drawn from `seed`: the
    formula of each membership document has `record_language.member`'s
    truth at each value; the question over the two documents has the
    status the reference gives the two terms; and a value found is
    placed by `record_language.member` as asked."""
    rl, sq, rm = _rl(), _sq(), _rm()
    a, b = REF.generated_term(int(seed)), REF.generated_term(int(seed) + 1000)
    doc_a, doc_b = rm.membership_document(a), rm.membership_document(b)
    for i in range(40):
        value = REF.generated_value(int(seed) * 40 + i)
        if sq.derived_truth_at(doc_a, value) is not rl.member(a, value):
            return False
    found = sq.find_member([doc_a], [doc_b])
    reference = rl.find_member([a], [b])
    if found.status != reference.status:
        return False
    if found.status == "member":
        return rl.member(a, found.member) and not rl.member(b, found.member)
    return found.status == "none"


def _outside_the_reading() -> list:
    """Documents the question has no reading of."""
    from mathema.koine.syntax import Int, Name, Real, Term
    rt = _rt()
    v = Name(rt.PARAMETER)
    p = Term(rt.VALUE_OF_PRESENT, (v,))
    return [
        rt.function_of_one_value(Term("operator::comparison::less", (p, Int(1)))),
        rt.function_of_one_value(Term("operator::comparison::equal", (p, Real("0.5")))),
        rt.function_of_one_value(Term("operator::comparison::equal", (p, p))),
        rt.function_of_one_value(Term("operator::binary::addition", (p, Int(1)))),
        rt.function_of_one_value(p),
        rt.function_of_one_value(Term("operator::logic::not", (p,))),
    ]


OUTSIDE_THE_READING = 6


def a_document_outside_the_reading_is_not_an_answer(i: int) -> bool:
    """Whether the question about a document it has no reading of gives
    no answer and says which term it does not read."""
    document = _outside_the_reading()[int(i)]
    found = _sq().find_member([document], [])
    return found.status == "unknown" and "no solver reading" in found.reason
