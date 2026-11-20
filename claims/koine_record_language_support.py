# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about membership of a record language, stated
in KOINE, are stated over.

The modules under claim are `mathema.koine.language_terms` (a regular
language as `language::` terms), `mathema.koine.record_terms` (the
terms a function of one JSON value is written in: a test of a value's
kind, absence, and the keys of a map) and
`mathema.koine.record_membership` (the membership function of a
record-language node, as a KOINE document).

Each function takes whole numbers a claim can quantify: indices into
`TERMS` and `VALUES` (the catalogues of
`claims/record_language_support.py`, with a few more values), into
`REGULAR` (regular-language nodes, one of each operation), `TEXTS`,
`NAMESETS`, `DEFINITIONS` and the lists of malformed terms. Each
returns the truth of one statement, so a claim reads `f(t, v) == True`.

`mathema.record_language.member` is the statement of membership the
KOINE documents are compared with."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _reference_support():
    spec = importlib.util.spec_from_file_location(
        "record_language_support", _HERE / "record_language_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REF = _reference_support()
TERMS = REF.TERMS
#: the reference catalogue, then values it lacks: two keys holding
#: null, a nested record alone, numbers written as floats, a lone
#: surrogate, the empty key, and a key no term names
VALUES = REF.VALUES + [
    {"x": None, "y": None}, {"git": "status"}, {"x": 1.0}, -0.0, 2.0, "\ud800", {"": True},
    {"x": True, "\x00": None}, {"x": "a", "y": "a"}, {"shell": {"git": "status"}},
]
DEFINITIONS = REF.DOCUMENTS


def _lit(text: str) -> dict:
    return {"op": "literal", "codes": [ord(c) for c in text]}


_DIGIT = {"op": "chars", "ranges": [[48, 57]]}
#: regular-language nodes: one of each operation, then the catalogue's
REGULAR = [
    {"op": "empty"}, {"op": "epsilon"}, _lit("a"), _lit("/wt"), _DIGIT,
    {"op": "chars", "ranges": [[97, 122], [48, 57], [45, 45]]},
    {"op": "concat", "args": [_lit("a"), _DIGIT]},
    {"op": "union", "args": [_lit("a"), _lit("b"), {"op": "epsilon"}]},
    {"op": "inter", "args": [{"op": "repeat", "arg": _DIGIT, "min": 0, "max": None}, _lit("1")]},
    {"op": "complement", "arg": _lit("a")},
    {"op": "repeat", "arg": _DIGIT, "min": 1, "max": 3},
    {"op": "repeat", "arg": _DIGIT, "min": 2, "max": None},
    {"op": "concat", "args": []}, {"op": "union", "args": []},
    REF.SHALLOW, REF.DEEP, REF.DOLLAR,
]
#: the ruled head each operation of a regular-language node is written as
_HEAD_OF = {"empty": "language::empty", "epsilon": "language::epsilon",
            "literal": "language::literal", "chars": "language::characters",
            "concat": "language::concatenation", "union": "language::union",
            "inter": "language::intersection", "complement": "language::complement"}
TEXTS = ["", "a", "b", "a\n", "1", "12", "123", "1234", "a1", "-", "/wt", "/wt/task-7",
         "/wt/task-7/src", "/wt/other", "/etc", "\ud800", "\x00", "\U0010ffff"]
NAMESETS = [[], ["x"], ["x", "y"], ["y"], ["edit", "publish", "root"],
            ["edit", "publish", "root", "shell"], [""], ["w", "x"]]
KEYS = ["x", "y", "z", "w", "", "edit", "shell"]
KINDS = ["kind::bool", "kind::int", "kind::scalar", "kind::string", "kind::sequence",
         "kind::dict"]


def _lt():
    from mathema.koine import language_terms
    return language_terms


def _rt():
    from mathema.koine import record_terms
    return record_terms


def _rm():
    from mathema.koine import record_membership
    return record_membership


def _rl():
    from mathema import record_language
    return record_language


def _syntax():
    from mathema.koine import syntax
    return syntax


def _at(expression, value):
    """What `record_terms.interpret` gives the function of one value
    returning `expression`, at `value`."""
    rt = _rt()
    return rt.interpret(rt.function_of_one_value(expression), [value])


def _operand():
    return _syntax().Name(_rt().PARAMETER)


def _present():
    s = _syntax()
    return s.Term(_rt().VALUE_OF_PRESENT, (_operand(),))


def _value(outcome):
    """The value of an outcome that is one, else the outcome itself."""
    from mathema.koine.interpret import Value
    return outcome.value if isinstance(outcome, Value) else outcome


def _expected_kind(value) -> "str | None":
    """The tested kind of a JSON value, written out: a truth value is
    `kind::bool` and never a number; a whole number carried as an
    integer is `kind::int`; a number carried in floating point is
    `kind::scalar`, whole or not; null is of no tested kind."""
    if value is None:
        return None
    if value is True or value is False:
        return "kind::bool"
    if type(value) is int:
        return "kind::int"
    if type(value) is float:
        return "kind::scalar"
    if type(value) is str:
        return "kind::string"
    if type(value) is list:
        return "kind::sequence"
    if type(value) is dict:
        return "kind::dict"
    raise AssertionError(f"not a JSON value: {value!r}")


# ---- a regular language as language:: terms ------------------------------

def a_language_term_reads_back(i: int) -> bool:
    """Whether the term of regular-language node `i` reads back to that
    node, argument for argument."""
    lt, node = _lt(), REGULAR[int(i)]
    return lt.to_node(lt.from_node(node)) == node


def a_language_term_is_written_with_the_ruled_head(i: int) -> bool:
    """Whether node `i` is written with the head ruled for its
    operation, a repetition with the bounded head when it has an upper
    end and the unbounded one when it has none, and the exact wrapper
    names the alphabet of code points."""
    lt, node = _lt(), REGULAR[int(i)]
    term = lt.from_node(node)
    if node["op"] == "repeat":
        want = ("language::repetition::unbounded" if node["max"] is None
                else "language::repetition::bounded")
    else:
        want = _HEAD_OF[node["op"]]
    wrapped = lt.exact(term)
    return (term.head == want and wrapped.head == "language::regular::exact"
            and wrapped.args[0] == term and wrapped.args[1].head == "alphabet::codepoints"
            and lt.node_of_exact(wrapped) == node)


def _malformed_language_terms() -> list:
    s = _syntax()
    T, N, L = s.Term, s.Int, s.List
    a = T("language::literal", (L((N(97),)),))
    return [
        s.Name("x"), N(1), T("language::regex", (s.Str("a"),)), T("language::empty", (a,)),
        T("language::literal", (N(97),)), T("language::literal", (L((s.Str("a"),)),)),
        T("language::literal", (L((s.Bool(True),)),)),
        T("language::characters", (L((N(1), N(2))),)),
        T("language::characters", (L((L((N(1),)),)),)),
        T("language::complement", ()), T("language::complement", (a, a)),
        T("language::repetition::bounded", (a, N(1))),
        T("language::repetition::unbounded", (a, N(1), N(2))),
        T("language::repetition::bounded", (a, s.Str("1"), N(2))),
        T("language::union", (a, N(1))),
        T("language::union", (a,), (("alphabet", a),)),
        T("language::regular::exact", (a,)),
        T("language::regular::exact", (a, T("alphabet::bytes"))),
    ]


MALFORMED_LANGUAGE_TERMS = 18


def a_malformed_language_term_is_refused(i: int) -> bool:
    """Whether the malformed term `i` is refused: `to_node` for a node
    term, `node_of_exact` for a wrapper."""
    lt = _lt()
    term = _malformed_language_terms()[int(i)]
    read = lt.node_of_exact if getattr(term, "head", "") == "language::regular::exact" \
        else lt.to_node
    try:
        read(term)
    except lt.InvalidLanguageTerm:
        return True
    return False


# ---- the terms of a function of one JSON value ----------------------------

def a_value_is_of_one_tested_kind_or_none(v: int) -> bool:
    """Whether the kind tests that are true of value `v` are exactly the
    one kind written out for it, and none for null."""
    s, rt, value = _syntax(), _rt(), VALUES[int(v)]
    true_of = [k for k in KINDS
               if _value(_at(s.Term(rt.IS_OF_KIND, (_operand(), s.Term(k))), value)) is True]
    false_of = [k for k in KINDS
                if _value(_at(s.Term(rt.IS_OF_KIND, (_operand(), s.Term(k))), value)) is False]
    want = _expected_kind(value)
    return true_of == ([want] if want else []) and len(true_of) + len(false_of) == len(KINDS)


def absent_is_null_at_the_top(v: int) -> bool:
    """Whether `value::is_absent` of value `v` is true exactly when the
    value is null, and `value::value_of_present` gives the value where
    it is not null and no value, of the class of absent data, where it
    is."""
    from mathema.koine.interpret import NoValue, Value
    s, rt, value = _syntax(), _rt(), VALUES[int(v)]
    absent = _at(s.Term(rt.IS_ABSENT, (_operand(),)), value)
    read = _at(_present(), value)
    if value is None:
        return absent == Value(True) and isinstance(read, NoValue) \
            and read.cls == "nonvalue::data::absent"
    return absent == Value(False) and isinstance(read, Value) and read.value is value


def a_key_is_set_unset_or_null(v: int, k: int) -> bool:
    """Whether, for a map `v` and key `k`: `has_key` is true exactly
    when the map holds the key; the value at the key is absent exactly
    when the key is unset or holds null; and where the key holds a
    value that is not null, the value at the key is that value. For a
    value that is no map, whether the three terms are not runnable."""
    from mathema.koine.interpret import InterpretError, Value
    s, rt, value, key = _syntax(), _rt(), VALUES[int(v)], KEYS[int(k)]
    has = s.Term(rt.HAS_KEY, (_present(), s.Str(key)))
    at = s.Term(rt.VALUE_AT_KEY, (_present(), s.Str(key)))
    absent = s.Term(rt.IS_ABSENT, (at,))
    read = s.Term(rt.VALUE_OF_PRESENT, (at,))
    if type(value) is not dict:
        if value is None:
            return True
        for expression in (has, at):
            try:
                _at(expression, value)
            except InterpretError:
                continue
            return False
        return True
    if _at(has, value) != Value(key in value):
        return False
    if _at(absent, value) != Value(key not in value or value[key] is None):
        return False
    if key in value and value[key] is not None:
        got = _at(read, value)
        return isinstance(got, Value) and got.value is value[key]
    return True


def no_other_key_reads_every_key(v: int, n: int) -> bool:
    """Whether, for a map `v`, `has_no_key_other_than` over name set `n`
    is true exactly when every key the map holds is one of the names."""
    from mathema.koine.interpret import Value
    s, rt, value, names = _syntax(), _rt(), VALUES[int(v)], NAMESETS[int(n)]
    if type(value) is not dict:
        return True
    term = s.Term(rt.HAS_NO_KEY_OTHER_THAN,
                  (_present(), s.List(tuple(s.Str(x) for x in names))))
    return _at(term, value) == Value(set(value) <= set(names))


def a_text_is_in_its_language(i: int, t: int) -> bool:
    """Whether `in_language` of text `t` in the exact term of node `i`
    is what the regular-language matcher says of the node and the
    text."""
    from mathema import regular
    from mathema.koine.interpret import Value
    lt, s = _lt(), _syntax()
    node, text = REGULAR[int(i)], TEXTS[int(t)]
    term = s.Term(lt.IN_LANGUAGE, (_present(), lt.exact(lt.from_node(node))))
    return _at(term, text) == Value(regular.node_member(node, text))


def _malformed_expressions() -> list:
    s, rt, lt = _syntax(), _rt(), _lt()
    T, v = s.Term, _operand()
    exact = lt.exact(lt.from_node(_lit("a")))
    return [
        T(rt.IS_OF_KIND, (v,)), T(rt.IS_OF_KIND, (v, T("kind::record"))),
        T(rt.IS_OF_KIND, (v, s.Str("kind::bool"))), T(rt.IS_OF_KIND, (v, T("kind::bool"), v)),
        T(rt.IS_OF_KIND, (v, T("kind::bool", (v,)))),
        T(rt.IS_ABSENT, ()), T(rt.IS_ABSENT, (v, v)), T(rt.VALUE_OF_PRESENT, ()),
        T(rt.HAS_KEY, (v,)), T(rt.HAS_KEY, (v, s.Name("x"))), T(rt.HAS_KEY, (v, s.Int(1))),
        T(rt.VALUE_AT_KEY, (v, s.Str("x"), s.Str("y"))),
        T(rt.HAS_NO_KEY_OTHER_THAN, (v,)),
        T(rt.HAS_NO_KEY_OTHER_THAN, (v, s.Str("x"))),
        T(rt.HAS_NO_KEY_OTHER_THAN, (v, s.List((s.Int(1),)))),
        T(rt.HAS_NO_KEY_OTHER_THAN, (v, s.List((s.Str("x"), s.Str("x"))))),
        T(lt.IN_LANGUAGE, (v,)), T(lt.IN_LANGUAGE, (v, s.Str("a"))),
        T(lt.IN_LANGUAGE, (v, T("language::literal", (s.Int(1),)))),
        T(lt.IN_LANGUAGE, (v, exact.args[0])),
        T(rt.IS_ABSENT, (s.Name("unbound"),)),
        T(rt.HAS_KEY, (s.Name("unbound"), s.Str("x"))),
        T("value::is_of_type", (v, T("kind::bool"))),
    ]


MALFORMED_EXPRESSIONS = 23


def a_malformed_term_is_refused(i: int) -> bool:
    """Whether the validator reports a problem for the function
    returning malformed expression `i`."""
    rt = _rt()
    return bool(rt.validate(rt.function_of_one_value(_malformed_expressions()[int(i)])))


def _wellformed_expressions() -> list:
    s, rt, lt = _syntax(), _rt(), _lt()
    T, v, p = s.Term, _operand(), _present()
    return [
        T(rt.IS_OF_KIND, (v, T(k))) for k in KINDS
    ] + [
        T(rt.IS_ABSENT, (v,)), T(rt.HAS_KEY, (p, s.Str("x"))),
        T(rt.IS_ABSENT, (T(rt.VALUE_AT_KEY, (p, s.Str(""))),)),
        T(rt.HAS_NO_KEY_OTHER_THAN, (p, s.List(()))),
        T(rt.HAS_NO_KEY_OTHER_THAN, (p, s.List((s.Str("x"), s.Str("y"))))),
        T(lt.IN_LANGUAGE, (p, lt.exact(lt.from_node(REF.SHALLOW)))),
    ]


WELLFORMED_EXPRESSIONS = 12


def a_wellformed_term_is_accepted(i: int) -> bool:
    """Whether the validator reports nothing for the function returning
    well-formed expression `i`."""
    rt = _rt()
    return rt.validate(rt.function_of_one_value(_wellformed_expressions()[int(i)])) == []


# ---- the membership function of a record-language node --------------------

def membership_agrees_with_the_reference(t: int, v: int) -> bool:
    """Whether the membership document of term `t`, interpreted at
    value `v`, has the value `record_language.member` gives."""
    from mathema.koine.interpret import Value
    rt, term, value = _rt(), TERMS[int(t)], VALUES[int(v)]
    document = _rm().membership_document(term)
    return rt.interpret(document, [value]) == Value(_rl().member(term, value))


def a_membership_document_is_valid(t: int) -> bool:
    """Whether the membership document of term `t` is valid, and built
    twice has one hash."""
    from mathema.koine import koine_hash
    rt, rm, term = _rt(), _rm(), TERMS[int(t)]
    document = rm.membership_document(term)
    return rt.validate(document) == [] \
        and koine_hash(document) == koine_hash(rm.membership_document(term))


def a_record_states_each_notion_once(t: int) -> bool:
    """Whether, for a record term `t` of n fields, the membership
    expression is one conjunction of n + 2 parts: the value is a map;
    it has no key other than the n names, in the order written; then
    one part for each field, a conjunction that starts with `has_key`
    for a required field and a disjunction that starts with the
    negation of `has_key` for an optional one."""
    s, rt, rm, term = _syntax(), _rt(), _rm(), TERMS[int(t)]
    if term.get("op") != "record":
        return True
    expression = rm.membership_expression(term, _operand())
    names = [name for name, _, _ in term["fields"]]
    if not (isinstance(expression, s.Term) and expression.head == "operator::logic::and"
            and len(expression.args) == len(names) + 2):
        return False
    is_map, closed, *parts = expression.args
    if is_map != s.Term(rt.IS_OF_KIND, (_operand(), s.Term("kind::dict"))):
        return False
    if closed != s.Term(rt.HAS_NO_KEY_OTHER_THAN,
                        (_present(), s.List(tuple(s.Str(n) for n in names)))):
        return False
    for (name, _, required), part in zip(term["fields"], parts):
        has = s.Term(rt.HAS_KEY, (_present(), s.Str(name)))
        if required:
            if not (part.head == "operator::logic::and" and part.args[0] == has):
                return False
        elif not (part.head == "operator::logic::or"
                  and part.args[0] == s.Term("operator::logic::not", (has,))):
            return False
    return True


def _list_terms() -> list:
    flag = REF.FLAG
    a_list = {"op": "list", "item": flag, "min": 0, "max": None}
    return [a_list, REF.record(("x", a_list, True)), REF.union(flag, a_list),
            REF.complement(a_list)]


LIST_TERMS = 4


def a_list_is_declined_by_name(i: int) -> bool:
    """Whether a term holding a list node has no membership document,
    and the refusal names the list."""
    rm = _rm()
    try:
        rm.membership_document(_list_terms()[int(i)])
    except rm.Declined as e:
        return "list" in str(e)
    return False


def each_bound_has_its_document(d: int, v: int) -> bool:
    """Whether the two membership documents of definition `d`, its
    at_most and its at_least, interpreted at value `v`, have the values
    `record_language.member` gives under each bound."""
    from mathema.koine.interpret import Value
    rt, rl, definition, value = _rt(), _rl(), DEFINITIONS[int(d)], VALUES[int(v)]
    at_most, at_least = _rm().membership_documents(definition)
    return (rt.interpret(at_most, [value]) == Value(rl.member(definition, value, bound="at_most"))
            and rt.interpret(at_least, [value])
            == Value(rl.member(definition, value, bound="at_least")))


def generated_membership_agrees_with_the_reference(seed: int) -> bool:
    """Whether, for a term and forty values drawn from `seed`, the
    membership document interpreted at each value has the value
    `record_language.member` gives, and the document is valid."""
    from mathema.koine.interpret import Value
    rt, rl = _rt(), _rl()
    term = REF.generated_term(int(seed))
    document = _rm().membership_document(term)
    if rt.validate(document):
        return False
    return all(rt.interpret(document, [value]) == Value(rl.member(term, value))
               for value in (REF.generated_value(int(seed) * 40 + i) for i in range(40)))
