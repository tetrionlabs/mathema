# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about texts with surrogates and numbers no
float holds, on the KOINE route, are stated over.

The modules under claim are `mathema.koine.record_membership`,
`mathema.koine.solver_question` and `mathema.koine.canonical`. The
record-language oracle (`tests/_record_language_oracle.py`) is what the
route is compared with: it keeps a surrogate on its own and refuses a
high surrogate followed by a low one, in a choice's texts and in a
field's name.

Each function takes an index into `SURROGATE_DOCUMENTS` or into
`NUMBER_EXPRESSIONS`, and returns the truth of one statement, so a
claim reads `f(i) == True`."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _load("koine_record_reading_support")
REF = R.REF
EMPTY = {"op": "empty"}
HIGH, LOW, PAIR = "\ud800", "\udc00", "😀"
#: texts holding surrogates on their own, a pair, and an astral
#: character written as one code point
TEXTS = [HIGH, LOW, "a" + HIGH, LOW + HIGH, PAIR, "a" + PAIR, "\U0001f600", ""]
#: texts at the edges of the two surrogate ranges: a pair of the first
#: and of the last high and low surrogates, the two mixed edge pairs, a
#: pair at the very start and at the very end of a text, each edge
#: surrogate alone, and the code points just past each range
TEXTS += ["\ud800\udc00", "\udbff\udfff", "\ud800\udfff", "\udbff\udc00",
          "\ud800\udc00ab", "ab\udbff\udfff", "\udbff", "\udfff", "\ud7ff\udc00",
          "\udbff\ue000", "\udc00\ud800", "\ud7ff\ue000"]


def _documents() -> list:
    out = []
    for text in TEXTS:
        out.append(REF._exact(REF.choice(text)))
        out.append(REF._exact(REF.choice(text, "b")))
        out.append(REF._exact(REF.record((text, REF.FLAG, True))))
        out.append(REF._exact(REF.record(("x", REF.choice(text), False))))
    return out


SURROGATE_DOCUMENTS = _documents()
#: values the documents are asked at: each text, and maps holding it
SURROGATE_VALUES = TEXTS + [{t: True} for t in TEXTS] + [{"x": t} for t in TEXTS] \
    + [None, True, "b", {}, {"x": "b"}]


def _rl():
    return REF._load()


def _rm():
    from mathema.koine import record_membership
    return record_membership


def a_text_with_surrogates_is_read_as_the_oracle_reads_it(i: int) -> bool:
    """Whether the route refuses definition `i` exactly when the oracle
    does; when both read it, whether each membership document has, at
    every value, the oracle's truth, its KOINE hash can be taken, and
    the question of a member inside it gives a member the oracle
    places, or none only when no value is one."""
    from mathema.koine import koine_hash, record_terms, solver_question
    from mathema.koine.interpret import Value
    document = SURROGATE_DOCUMENTS[int(i)]
    outcome, documents = R._route(document)
    if not R._reference_reads(document):
        return outcome == "refused"
    if outcome != "documents":
        return False
    at_most = documents[0]
    rl = _rl()
    for value in SURROGATE_VALUES:
        if record_terms.interpret(at_most, [value]) != Value(rl.member(document, value)):
            return False
    koine_hash(at_most)
    found = solver_question.find_member([at_most], [])
    if found.status == "member":
        return rl.member(document, found.member)
    if found.status == "none":
        return not any(rl.member(document, v) for v in SURROGATE_VALUES)
    return False


def _number_expressions() -> list:
    from mathema.koine import record_terms as rt
    from mathema.koine.syntax import Int, Name, Term
    v = Name(rt.PARAMETER)
    present = Term(rt.VALUE_OF_PRESENT, (v,))

    def kind(k):
        return Term(rt.IS_OF_KIND, (v, Term(k)))

    def equal(n):
        return Term("operator::comparison::equal", (present, Int(n)))

    def both(*parts):
        return Term("operator::logic::and", parts)
    out = []
    for n in (10 ** 400, -(10 ** 400), 2 ** 53 + 1, 10 ** 308, 2 ** 1024, 2 ** 1023):
        out += [both(kind("kind::scalar"), equal(n)), both(kind("kind::int"), equal(n)),
                equal(n)]
    return out


NUMBER_EXPRESSIONS = 18


def a_number_no_float_holds_is_never_a_wrong_answer(i: int) -> bool:
    """Whether the question about expression `i`, a number tested by
    kind and by value, asked true and asked false, never raises; a
    member it gives is placed by the interpreter as asked; and it says
    none only when no JSON value is one: no integer, and no float,
    holds the number with the kind asked."""
    from mathema.koine import record_terms as rt
    from mathema.koine import solver_question
    from mathema.koine.interpret import InterpretError, Value
    expression = _number_expressions()[int(i)]
    document = rt.function_of_one_value(expression)
    number = expression.args[1].args[1].value if expression.head != \
        "operator::comparison::equal" else expression.args[1].value
    candidates = [number]
    try:
        if float(number) == number:
            candidates.append(float(number))
    except OverflowError:
        pass

    def truth(value):
        try:
            outcome = rt.interpret(document, [value])
        except InterpretError:
            return None
        return outcome.value if isinstance(outcome, Value) else None
    for inside, wanted in (([document], []), ([], [document])):
        try:
            found = solver_question.find_member(inside, wanted)
        except Exception:
            return False
        asked = bool(inside)
        if found.status == "member" and truth(found.member) is not asked:
            return False
        if found.status == "none" and asked and any(truth(c) is True for c in candidates):
            return False
    return True

