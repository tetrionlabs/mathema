# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The solver formula a KOINE function of one JSON value is read as,
and the one question asked of such formulas.

Draft, not part of the public interface. A document is read when it has
one parameter and a body that returns one expression written in:
`true` and `false`; `operator::logic::not`, `and`, `or`;
`operator::comparison::equal` and `not_equal` between a value and a
constant that is a truth value, a whole number or a text; and the terms
of `record_terms`. Each term has one rule here, and the formula of a
document is built from the document by those rules and from nothing
else.

The value is held as solver variables: its kind (null, or one of the
tested kinds); the truth value, the number or the text it is when of
that kind; and, when a map, for each key some document names at that
place, whether the key is set and the value under it, and whether it
holds any key no document names there. No term tells apart two values
that agree on those, so the question over these variables has the
answer of the question over every JSON value. A number is a whole part
and whether it is whole; a number that is not whole is equal to no
constant a document may write. A list is its kind alone.

An expression has a value under a condition, read with it: a
`value::map::` term where its operand is a map, `in_language` where it
is a text, `value::value_of_present` where it is not absent, and a
later part of an `and` or an `or` only where the earlier parts do not
settle it. Equality follows the interpreter, in which a truth value
equals the number 1 or 0.

`find_member` asks for a value at which every document of one list
returns true and every document of another returns false. `none` is a
proof that no JSON value is such a value. A value the solver gives is
returned only when `record_terms.interpret` returns those truths at it.
A value at which a document has no value is neither, and the answer is
then `unknown`. The `z3` dependency is the optional `mathema[smt]`
extra.
"""
from __future__ import annotations

from .. import regular
from ..regular import Found
from . import language_terms, record_terms as T
from .document import Document
from .interpret import InterpretError, Value
from .syntax import Bool, Int, List, Name, Str, Term

#: the kinds of a value, null first and then the tested kinds
_KINDS = ("null", *T.TESTED_KINDS)
_NUMBERS = ("kind::int", "kind::scalar")
NOT, AND, OR = "operator::logic::not", "operator::logic::and", "operator::logic::or"
EQUAL, NOT_EQUAL = "operator::comparison::equal", "operator::comparison::not_equal"
_EVERY_CODE_POINT = [[0, regular.MAX_CODE_POINT]]


class NoReading(ValueError):
    """A document outside what this module reads; the message names the
    term or the shape."""


class _Place:
    """One value of the question as solver variables, and the places
    under the keys the documents name there."""

    def __init__(self, z3, path: str) -> None:
        self.z3, self.path = z3, path
        self.kind = z3.Int(f"{path} kind")
        self.boolean = z3.Bool(f"{path} boolean")
        self.number = z3.Int(f"{path} number")
        self.whole = z3.Bool(f"{path} whole")
        self.text = z3.String(f"{path} text")
        self.other_key = z3.Bool(f"{path} other key")
        self.keys: dict = {}

    def is_(self, kind: str):
        return self.kind == _KINDS.index(kind)

    def a_number(self):
        return self.z3.Or(self.is_("kind::int"), self.is_("kind::scalar"))

    def key(self, name: str) -> tuple:
        """`(is set, place)` of the key `name`, made on first use."""
        if name not in self.keys:
            self.keys[name] = (self.z3.Bool(f"{self.path}.{name!r} set"),
                               _Place(self.z3, f"{self.path}.{name!r}"))
        return self.keys[name]

    def every(self):
        """This place and every place under it."""
        yield self
        for _, inner in self.keys.values():
            yield from inner.every()


class _Operand:
    """What an expression that is no truth value is read as: a place,
    the condition under which it is unset (no key), and the condition
    under which the expression has a value. `present` says the
    expression is a `value::value_of_present`, never absent where it
    has a value."""

    def __init__(self, place: _Place, unset, defined, present: bool = False) -> None:
        self.place, self.unset, self.defined, self.present = place, unset, defined, present


class _Truth:
    """What an expression that is a truth value is read as: the formula
    of its truth and the condition under which it has a value."""

    def __init__(self, formula, defined) -> None:
        self.formula, self.defined = formula, defined


def _body_expression(document: Document):
    """The one expression a readable document returns.

    Raises:
        NoReading: the document has another shape.
    """
    if not isinstance(document, Document) or len(document.parameter_names) != 1:
        raise NoReading("a function of one value is read, and this is not one")
    body = document.body
    if not (len(body) == 1 and isinstance(body[0], Term)
            and body[0].head == "statement::return" and len(body[0].args) == 1):
        raise NoReading("a body that returns one expression is read, and this is not one")
    return document.parameter_names[0], body[0].args[0]


def _texts_of(node, into: list) -> None:
    """Every regular-language node an expression reads a text by: the
    language of each `in_language` term and the literal of each string
    it writes."""
    if isinstance(node, Str):
        into.append(_literal(node.value))
    elif isinstance(node, Term):
        if node.head == T.IN_LANGUAGE and len(node.args) == 2:
            _texts_of(node.args[0], into)
            try:
                into.append(regular.canonical(language_terms.node_of_exact(node.args[1])))
            except (language_terms.InvalidLanguageTerm, regular.InvalidTerm) as e:
                raise NoReading(str(e)) from e
            return
        for a in node.args:
            _texts_of(a, into)
    elif isinstance(node, List):
        for x in node.items:
            _texts_of(x, into)


#: the texts holding a high surrogate followed by a low one
_PAIR = {"op": "concat", "args": [
    {"op": "repeat", "arg": {"op": "chars", "ranges": [[0, regular.MAX_CODE_POINT]]},
     "min": 0, "max": None},
    {"op": "chars", "ranges": [[0xD800, 0xDBFF]]}, {"op": "chars", "ranges": [[0xDC00, 0xDFFF]]},
    {"op": "repeat", "arg": {"op": "chars", "ranges": [[0, regular.MAX_CODE_POINT]]},
     "min": 0, "max": None}]}
#: what a member holding a surrogate pair is returned with when the
#: search for a member holding none gets no answer
NO_PAIR_FREE_ANSWER = ("the member holds a surrogate pair, and no member without a surrogate "
                       "pair was found")
#: what a member holding a surrogate pair is returned with
ONLY_PAIRS = ("every value the question has holds a surrogate pair, which JSON text reads back "
              "as the one character beyond the basic plane it encodes")


def _holds_a_pair(value) -> bool:
    """Whether a JSON value holds a text with a high surrogate followed
    by a low one, in a key or a value, at any depth."""
    if isinstance(value, str):
        return any("\ud800" <= a <= "\udbff" and "\udc00" <= b <= "\udfff"
                   for a, b in zip(value, value[1:]))
    if isinstance(value, dict):
        return any(_holds_a_pair(k) or _holds_a_pair(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_holds_a_pair(v) for v in value)
    return False


def _literal(text: str) -> dict:
    return regular.canonical({"op": "literal", "codes": [ord(c) for c in text]})


def _texts_in(value, into: list) -> None:
    """The literal of every text inside a JSON value, keys included."""
    if isinstance(value, str):
        into.append(_literal(value))
    elif isinstance(value, dict):
        for key, inner in value.items():
            _texts_in(key, into)
            _texts_in(inner, into)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            _texts_in(inner, into)


class _Reading:
    """Several documents read as formulas over one value.

    "No key other than these" denies every other key any document
    names at that place, whichever document names it, and the keys are
    all known only once every document is read. So each such term is
    read as a truth variable of its own, and `shape` states what the
    variable is equal to over the keys known by then."""

    def __init__(self, z3, documents: list, values: "list | tuple" = ()) -> None:
        self.z3 = z3
        bodies = [_body_expression(d) for d in documents]
        texts: list = []
        for _, expression in bodies:
            _texts_of(expression, texts)
        for value in values:
            _texts_in(value, texts)
        # the surrogate ranges are always told apart, so that a text
        # holding a pair can be asked about
        self.texts = regular.lower_into([*texts, _PAIR], z3, _EVERY_CODE_POINT)
        self.root = _Place(z3, "value")
        #: each "no key other than" read: its variable, place and names
        self._closed: list = []
        #: what each term object was read as, kept with the term, so
        #: that a term standing in several places is read once
        self._seen: dict = {}
        self.truths = [self._truth(expression, parameter)
                       for parameter, expression in bodies]

    def no_pair(self):
        """That no text the variables stand for holds a surrogate pair."""
        z3 = self.z3
        pair = self.texts.regex(regular.canonical(_PAIR))
        return z3.And(*[z3.Implies(place.is_("kind::string"), z3.Not(z3.InRe(place.text, pair)))
                        for place in self.root.every()])

    def shape(self) -> list:
        """What every variable must satisfy to stand for a value: a
        kind that is one of the kinds, a text over the question's
        symbols, and an integer that is whole."""
        z3, out = self.z3, []
        for place in self.root.every():
            out.append(z3.And(place.kind >= 0, place.kind < len(_KINDS)))
            out.append(z3.InRe(place.text, self.texts.everything))
            out.append(z3.Implies(place.is_("kind::int"), place.whole))
        for variable, place, listed in self._closed:
            others = [z3.Not(is_set) for name, (is_set, _) in sorted(place.keys.items())
                      if name not in listed]
            out.append(variable == z3.And(z3.Not(place.other_key), *others))
        return out

    # ---- one rule for each term ---------------------------------------

    def _read(self, node, parameter: str):
        seen = self._seen.get(id(node))
        if seen is not None and seen[0] is node and seen[1] == parameter:
            return seen[2]
        read = self._read_once(node, parameter)
        self._seen[id(node)] = (node, parameter, read)
        return read

    def _read_once(self, node, parameter: str):
        z3 = self.z3
        if isinstance(node, Bool):
            return _Truth(z3.BoolVal(node.value), z3.BoolVal(True))
        if isinstance(node, Name):
            if node.id != parameter:
                raise NoReading(f"the name {node.id} is not the parameter")
            return _Operand(self.root, z3.BoolVal(False), z3.BoolVal(True))
        if not isinstance(node, Term):
            raise NoReading(f"{node!r} is read only as the constant of an equality")
        head, args = node.head, node.args
        if head in T.EXPRESSIONS and T.shape_problem(node) is not None:
            raise NoReading(f"{head}: {T.shape_problem(node)}")
        if head == NOT and len(args) == 1:
            inner = self._truth(args[0], parameter)
            return _Truth(z3.Not(inner.formula), inner.defined)
        if head in (AND, OR) and len(args) >= 2:
            return self._joined(head, [self._truth(a, parameter) for a in args])
        if head in (EQUAL, NOT_EQUAL) and len(args) == 2:
            return self._equality(head, args, parameter)
        if head == T.IS_ABSENT:
            e = self._operand(args[0], parameter)
            return _Truth(self._absent(e), e.defined)
        if head == T.VALUE_OF_PRESENT:
            e = self._operand(args[0], parameter)
            return _Operand(e.place, z3.BoolVal(False),
                            z3.And(e.defined, z3.Not(self._absent(e))), present=True)
        if head == T.IS_OF_KIND:
            e = self._operand(args[0], parameter)
            return _Truth(z3.And(z3.Not(e.unset), e.place.is_(args[1].head)), e.defined)
        if head in (T.HAS_KEY, T.VALUE_AT_KEY, T.HAS_NO_KEY_OTHER_THAN):
            m = self._operand(args[0], parameter)
            defined = z3.And(m.defined, z3.Not(m.unset), m.place.is_("kind::dict"))
            if head == T.HAS_NO_KEY_OTHER_THAN:
                listed = frozenset(x.value for x in args[1].items)
                for name in sorted(listed):
                    m.place.key(name)
                variable = z3.Bool(f"{m.place.path} no key other than {len(self._closed)}")
                self._closed.append((variable, m.place, listed))
                return _Truth(variable, defined)
            is_set, inner = m.place.key(args[1].value)
            if head == T.HAS_KEY:
                return _Truth(is_set, defined)
            return _Operand(inner, z3.Not(is_set), defined)
        if head == T.IN_LANGUAGE:
            e = self._operand(args[0], parameter)
            node_ = regular.canonical(language_terms.node_of_exact(args[1]))
            return _Truth(z3.InRe(e.place.text, self.texts.regex(node_)),
                          z3.And(e.defined, z3.Not(e.unset), e.place.is_("kind::string")))
        raise NoReading(f"{head} has no solver reading")

    def _truth(self, node, parameter: str) -> _Truth:
        read = self._read(node, parameter)
        if not isinstance(read, _Truth):
            raise NoReading("a value stands where a truth value is read, with no solver "
                            "reading")
        return read

    def _operand(self, node, parameter: str) -> _Operand:
        read = self._read(node, parameter)
        if not isinstance(read, _Operand):
            raise NoReading("a truth value stands where a value is read, with no solver "
                            "reading")
        return read

    def _absent(self, e: _Operand):
        """Whether an operand is absent: unset, or null."""
        return self.z3.Or(e.unset, e.place.is_("null"))

    def _joined(self, head: str, parts: list) -> _Truth:
        """A conjunction or disjunction evaluated in order: a part has
        to have a value only where no earlier part settles the whole."""
        z3 = self.z3
        defined, unsettled = [], z3.BoolVal(True)
        for part in parts:
            defined.append(z3.Implies(unsettled, part.defined))
            carries_on = part.formula if head == AND else z3.Not(part.formula)
            unsettled = z3.And(unsettled, carries_on)
        formula = (z3.And if head == AND else z3.Or)(*[p.formula for p in parts])
        return _Truth(formula, z3.And(*defined))

    def _equality(self, head: str, args: tuple, parameter: str) -> _Truth:
        z3 = self.z3
        constants = [a for a in args if isinstance(a, (Bool, Int, Str))]
        others = [a for a in args if not isinstance(a, (Bool, Int, Str))]
        if len(constants) != 1 or len(others) != 1:
            raise NoReading(f"{head} between a value and one constant that is a truth "
                            f"value, a whole number or a text is read; this one has no "
                            f"solver reading")
        e, constant = self._operand(others[0], parameter), constants[0]
        place = e.place
        if isinstance(constant, Str):
            same = z3.And(place.is_("kind::string"),
                          z3.InRe(place.text, self.texts.regex(_literal(constant.value))))
        else:
            # a truth value equals the number 1 or 0, as in the interpreter
            number = int(constant.value)
            same = z3.And(place.a_number(), place.whole, place.number == number)
            if number in (0, 1):
                same = z3.Or(same, z3.And(place.is_("kind::bool"),
                                          place.boolean == bool(number)))
        same = z3.And(z3.Not(e.unset), same)
        return _Truth(same if head == EQUAL else z3.Not(same), e.defined)

    # ---- a value written into, and read out of, the variables ----------

    def at(self, value, place: "_Place | None" = None) -> list:
        """The constraints that make the variables stand for the JSON
        value `value`.

        Raises:
            NoReading: the value is no JSON value.
        """
        z3 = self.z3
        place = self.root if place is None else place
        kind = "null" if value is None else T.kind_of(value)
        if kind is None:
            raise NoReading(f"{value!r} is no JSON value")
        out = [place.is_(kind)]
        if kind == "kind::bool":
            out.append(place.boolean == value)
        elif kind == "kind::int":
            out += [place.number == value, place.whole]
        elif kind == "kind::scalar":
            if value != value or value in (float("inf"), float("-inf")):
                raise NoReading(f"{value!r} is no JSON value")
            whole = float(value).is_integer()
            out.append(place.whole == whole)
            if whole:
                out.append(place.number == int(value))
        elif kind == "kind::string":
            out.append(z3.InRe(place.text, self.texts.regex(_literal(value))))
        elif kind == "kind::dict":
            out.append(place.other_key == any(k not in place.keys for k in value))
            for name, (is_set, inner) in sorted(place.keys.items()):
                out.append(is_set == (name in value))
                if name in value:
                    out += self.at(value[name], inner)
        return out

    def read(self, model, place: "_Place | None" = None):
        """The JSON value a model gives the variables: a number that is
        not whole as its whole part and a half, a number of the float
        kind past every float as the integer, a list as the list of
        nothing, a map as its named keys that are set and, when it
        holds another key, one key no document names, holding null."""
        place = self.root if place is None else place

        def of(term):
            return model.eval(term, model_completion=True)
        kind = _KINDS[of(place.kind).as_long()]
        if kind == "null":
            return None
        if kind == "kind::bool":
            return bool(of(place.boolean))
        if kind == "kind::int":
            return of(place.number).as_long()
        if kind == "kind::scalar":
            number = of(place.number).as_long()
            try:
                return float(number) if bool(of(place.whole)) else number + 0.5
            except OverflowError:
                # no float holds the number; the interpreter judges the
                # integer read in its place
                return number
        if kind == "kind::string":
            return self.texts.decode(of(place.text).as_string())
        if kind == "kind::sequence":
            return []
        out = {}
        for name, (is_set, inner) in sorted(place.keys.items()):
            if bool(of(is_set)):
                out[name] = self.read(model, inner)
        if bool(of(place.other_key)):
            other = "\x00"
            while other in place.keys:
                other += "\x00"
            out[other] = None
        return out


def _checked(z3, solver, timeout_ms: int):
    """The solver's answer, with the wall clock interrupting it one
    second past its own timeout."""
    import threading
    solver.set("timeout", int(timeout_ms))
    watchdog = threading.Timer(timeout_ms / 1000.0 + 1.0, solver.ctx.interrupt)
    watchdog.daemon = True
    watchdog.start()
    try:
        return solver.check()
    finally:
        watchdog.cancel()


def _no_z3() -> Found:
    return Found("unknown", reason="z3 is not installed (the mathema[smt] extra)")


def _unanswered(z3, solver, timeout_ms: int) -> Found:
    return Found("unknown", reason=f"z3 gave no answer within {timeout_ms} ms "
                                   f"({solver.reason_unknown()})")


def _outcome(document: Document, value):
    """The truth `record_terms.interpret` gives `document` at `value`,
    or None where it gives no truth value or does not run."""
    try:
        outcome = T.interpret(document, [value])
    except InterpretError:
        return None
    if isinstance(outcome, Value) and isinstance(outcome.value, bool):
        return outcome.value
    return None


def find_member(inside, outside, *, valued_only: bool = False,
                timeout_ms: int = 5000) -> Found:
    """Intent:
        A JSON value at which every document in `inside` returns true
        and every document in `outside` returns false: `member` with
        the value, `none` when no such value exists, or `unknown` with
        the reason.

    Notes:
        `none` is a proof, and also says every document has a value at
        every JSON value. With `valued_only` the question is asked only
        of the points where every document has a value, and `none` then
        says nothing of the other points. A value is returned only when
        `record_terms.interpret` gives those truths at it. `unknown`
        when a document has no solver reading, when a document has no
        value at the point the solver gives, when the interpreter does
        not place the solver's value as asked, or when the solver gives
        no answer in time or is not installed. A member holding no
        surrogate pair is given where one exists; a member holding one is
        given with `ONLY_PAIRS` as its reason when every member does, and
        with `NO_PAIR_FREE_ANSWER` when the search for one with no pair
        gets no answer.
    """
    inside, outside = list(inside), list(outside)
    try:
        import z3
    except ImportError:
        return _no_z3()
    try:
        reading = _Reading(z3, inside + outside)
    except NoReading as e:
        return Found("unknown", reason=f"a document has no solver reading: {e}")
    truths = reading.truths
    asked = z3.And(*[t.formula for t in truths[:len(inside)]],
                   *[z3.Not(t.formula) for t in truths[len(inside):]])
    valueless = z3.Or(*[z3.Not(t.defined) for t in truths])
    solver = z3.Solver()
    solver.add(*reading.shape())
    solver.add(z3.And(z3.Not(valueless), asked) if valued_only else z3.Or(valueless, asked))
    outcome = _checked(z3, solver, timeout_ms)
    if outcome == z3.unsat:
        return Found("none")
    if outcome != z3.sat:
        return _unanswered(z3, solver, timeout_ms)
    value = reading.read(solver.model())
    note = ""
    if _holds_a_pair(value):
        solver.add(reading.no_pair())
        again = _checked(z3, solver, timeout_ms)
        if again == z3.sat:
            value = reading.read(solver.model())
        elif again == z3.unsat:
            note = ONLY_PAIRS
        else:
            note = (f"{NO_PAIR_FREE_ANSWER} within {timeout_ms} ms "
                    f"({solver.reason_unknown()})")
    got = [_outcome(d, value) for d in inside + outside]
    if None in got:
        return Found("unknown", reason=f"a document has no value at {value!r}, so it is "
                                       f"neither true nor false there")
    if all(got[:len(inside)]) and not any(got[len(inside):]):
        return Found("member", member=value, reason=note)
    return Found("unknown", reason=f"the solver's value {value!r} is not placed by the "
                                   f"interpreter as asked")


def find_point_without_value(document, *, timeout_ms: int = 5000) -> Found:
    """Intent:
        A JSON value at which `document` has no value: `member` with
        the value, `none` when it has a value at every JSON value, or
        `unknown` with the reason.

    Notes:
        A value is returned only when `record_terms.interpret` gives no
        truth value at it.
    """
    try:
        import z3
    except ImportError:
        return _no_z3()
    try:
        reading = _Reading(z3, [document])
    except NoReading as e:
        return Found("unknown", reason=f"a document has no solver reading: {e}")
    solver = z3.Solver()
    solver.add(*reading.shape())
    solver.add(z3.Not(reading.truths[0].defined))
    outcome = _checked(z3, solver, timeout_ms)
    if outcome == z3.unsat:
        return Found("none")
    if outcome != z3.sat:
        return _unanswered(z3, solver, timeout_ms)
    value = reading.read(solver.model())
    if _outcome(document, value) is None:
        return Found("member", member=value)
    return Found("unknown", reason=f"the interpreter gives a value at the solver's point "
                                   f"{value!r}")


def derived_truth_at(document, value, *, timeout_ms: int = 5000) -> "bool | None":
    """Intent:
        The truth the formula of `document` has at the JSON value
        `value`, or None where the formula has no value there. The
        interpreter is not asked: this is the solver's reading alone,
        for comparing the two.

    Raises:
        NoReading: the document or the value has no solver reading.
        RuntimeError: z3 is not installed, or gives no answer, or the
            variables written for the value leave the truth open.
    """
    try:
        import z3
    except ImportError as e:
        raise RuntimeError("z3 is not installed (the mathema[smt] extra)") from e
    reading = _Reading(z3, [document], [value])
    truth = reading.truths[0]

    def possible(wanted) -> bool:
        solver = z3.Solver()
        solver.add(*reading.shape(), *reading.at(value), wanted)
        outcome = _checked(z3, solver, timeout_ms)
        if outcome not in (z3.sat, z3.unsat):
            raise RuntimeError(f"z3 gave no answer within {timeout_ms} ms")
        return outcome == z3.sat
    if possible(z3.Not(truth.defined)):
        return None
    true, false = possible(truth.formula), possible(z3.Not(truth.formula))
    if true == false:
        raise RuntimeError(f"the formula does not settle its truth at {value!r}")
    return true


__all__ = ["Found", "NO_PAIR_FREE_ANSWER", "NoReading", "ONLY_PAIRS", "derived_truth_at",
           "find_member",
           "find_point_without_value"]
