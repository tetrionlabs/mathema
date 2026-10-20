# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The KOINE vocabulary, as data.

Every term a document may contain is a row here: its `::` path and its
signature, the sorts of its positional and named arguments. Extending
the language is adding a row; the validator, the interpreter and the
printers read these tables and nothing else about which terms exist.

The tree:

    koine, feature, lifter, source, function, parameter, returns,
    manifest, structure, body            the document envelope
    statement::...                        what a body is made of
    value::..., constant::...             values that are not operations
    operator::unary::...                  negation, identity
    operator::binary::...                 arithmetic, the division and
                                          remainder families, power
    operator::comparison::...             the six relations
    operator::logic::...                  and, or (short-circuit), not
    operator::membership::...             in, not_in a literal set
    function::<family>::...               the closed set of named functions
    call::...                             another function, a library
                                          function, a local function
    call::self, ::hashed, ::ancestor,     how the canonical form respells a
      ::external                          call to another function of the
                                          program; never written by a frontend
    failure::...                          an explicit refusal
    nonvalue::<stratum>::...              why an expression has no value
    as::...                               how a runtime shows a non-value
    kind::..., representation::...        parameter descriptions
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .._representation_words import REPRESENTATION_WORDS

KOINE_VERSION = "0.0.1"

# --- sorts: what an argument position accepts ----------------------------

EXPR = "expression"
NAME = "name"
NAMES = "list of names"
SEQ = "sequence reference"
BLOCK = "block"
EXPRS = "list of expressions"
LITERALS = "list of literals"
INT = "integer"
START = "start (0 or 1)"
POSINT = "positive integer"
STR = "string"
BOOL = "boolean"
FAILURE = "failure"
UPDATE_OP = "update operator"
KIND = "kind"
REPR = "representation"
NONVALUE = "non-value class"
AS = "manifestation"
SPAN = "span"
FIELDS = "list of fields"
FEATURE = "feature name"
STATEMENT = "statement"
LITERAL = "literal"
OPERATION = "operation"


@dataclass(frozen=True)
class Signature:
    positional: tuple = ()
    required: int | None = None        # positional arguments that must be present
    rest: str | None = None            # sort of any further positional arguments
    rest_min: int = 0                  # how many further arguments at least
    named: dict = field(default_factory=dict)   # name -> (sort, required)
    any_named: str | None = None       # sort of free-named arguments
    feature: str | None = None         # the feature the term needs, if any

    @property
    def min_positional(self) -> int:
        return len(self.positional) if self.required is None else self.required


def _sig(*positional, **kw) -> Signature:
    return Signature(tuple(positional), **kw)


_AT = {"at": (SPAN, True)}

# --- envelope ------------------------------------------------------------

ENVELOPE: dict[str, Signature] = {
    "koine": _sig(STR),
    "feature": _sig(FEATURE),
    "lifter": _sig(named={"language": (STR, True), "name": (STR, True),
                          "version": (STR, True)}),
    "source": _sig(named={"file": (STR, True), "line": (POSINT, True),
                          "sha256": (STR, True)}),
    "function": _sig(named={"name": (STR, True), "key": (STR, True)}),
    "parameter": _sig(NAME, KIND, REPR, required=2,
                      named={"element": (REPR, False), "fields": (FIELDS, False)}),
    "returns": _sig(KIND, REPR, required=1),
    "manifest": _sig(NONVALUE, AS, named={"operation": (OPERATION, False)}),
    "structure": _sig(named={"loops": (INT, True), "branches": (INT, True),
                             "recursion": (BOOL, True)}),
    "body": _sig(rest=STATEMENT),
}

#: envelope terms that appear at most once, and the ones that must appear
SINGLE = frozenset({"koine", "lifter", "source", "function", "returns",
                    "structure", "body"})
REQUIRED = ("koine", "lifter", "source", "function", "body")

FIELD = "field"
FIELD_SIG = _sig(NAME, KIND, REPR, required=2)
SPAN_HEAD = "span"
SPAN_SIG = _sig(POSINT, POSINT, STR)

KNOWN_FEATURES = frozenset({"option_result"})

# --- statements ------------------------------------------------------------

STATEMENTS: dict[str, Signature] = {
    "statement::bind": _sig(NAME, EXPR, named=_AT),
    "statement::bind_many": _sig(NAMES, EXPRS, named=_AT),
    "statement::update": _sig(NAME, UPDATE_OP, EXPR, named=_AT),
    "statement::define": _sig(NAME, NAMES, EXPR, named=_AT),
    "statement::branch": _sig(EXPR, BLOCK, BLOCK, named=_AT),
    "statement::loop::range": _sig(NAME, EXPR, EXPR, POSINT, BLOCK, named=_AT),
    "statement::loop::each": _sig(NAME, SEQ, START, BLOCK,
                                  named={**_AT, "index": (NAME, False)}),
    "statement::require": _sig(EXPR, FAILURE, named=_AT),
    "statement::fail": _sig(FAILURE, named=_AT),
    "statement::return": _sig(EXPR, named=_AT),
    "statement::evaluate": _sig(EXPR, named=_AT),
}

TERMINAL = frozenset({"statement::return", "statement::fail"})
NOT_IN_LOOPS = frozenset({"statement::return", "statement::fail", "statement::require"})
LOOPS = frozenset({"statement::loop::range", "statement::loop::each"})

FAILURES: dict[str, Signature] = {
    f"failure::{k}": _sig(STR, named={"message": (STR, False)})
    for k in ("raise", "panic", "trap", "abort")
}

# --- operators -------------------------------------------------------------

UNARY = ("operator::unary::negation", "operator::unary::identity")

ARITHMETIC = (
    "operator::binary::addition",
    "operator::binary::subtraction",
    "operator::binary::multiplication",
    "operator::binary::power",
)

#: real division and the three integer-quotient families (Boute 1992):
#: truncation rounds the quotient toward zero, floor toward minus
#: infinity, euclidean so the remainder is never negative
DIVISION = (
    "operator::binary::division::real",
    "operator::binary::division::truncation",
    "operator::binary::division::floor",
    "operator::binary::division::euclidean",
)
REMAINDER = (
    "operator::binary::remainder::truncation",
    "operator::binary::remainder::floor",
    "operator::binary::remainder::euclidean",
)

COMPARISON = tuple(f"operator::comparison::{r}" for r in
                   ("equal", "not_equal", "less", "less_equal", "greater", "greater_equal"))

#: the operators `statement::update` may name
UPDATE_OPS = frozenset({"operator::binary::addition", "operator::binary::subtraction",
                        "operator::binary::multiplication",
                        "operator::binary::division::real"})

# --- functions -------------------------------------------------------------

_ONE = (1,)
FUNCTIONS: dict[str, tuple | None] = {
    "function::root::square": _ONE,
    "function::root::cube": _ONE,
    "function::exponential::natural": _ONE,
    "function::exponential::natural_minus_one": _ONE,
    "function::logarithm::natural": _ONE,
    "function::logarithm::binary": _ONE,
    "function::logarithm::decimal": _ONE,
    "function::logarithm::natural_one_plus": _ONE,
    "function::trigonometric::sine": _ONE,
    "function::trigonometric::cosine": _ONE,
    "function::trigonometric::tangent": _ONE,
    "function::trigonometric::arcsine": _ONE,
    "function::trigonometric::arccosine": _ONE,
    "function::trigonometric::arctangent": _ONE,
    "function::trigonometric::arctangent2": (2,),
    "function::hyperbolic::sine": _ONE,
    "function::hyperbolic::cosine": _ONE,
    "function::hyperbolic::tangent": _ONE,
    "function::rounding::floor": _ONE,
    "function::rounding::ceiling": _ONE,
    "function::rounding::truncation": _ONE,
    "function::rounding::ties_even": _ONE,
    "function::rounding::ties_away": _ONE,
    "function::rounding::ties_up": _ONE,
    "function::order::minimum": None,
    "function::order::maximum": None,
    "function::order::clamp": (3,),
    "function::magnitude::absolute": _ONE,
    "function::magnitude::sign": _ONE,
    "function::magnitude::hypotenuse": (2,),
    "function::special::gamma": _ONE,
    "function::special::log_gamma": _ONE,
    "function::special::factorial": _ONE,
    "function::special::error": _ONE,
    "function::special::error_complement": _ONE,
    "function::integer::gcd": (2,),
    "function::complex::real_part": _ONE,
    "function::complex::imaginary_part": _ONE,
    "function::complex::conjugate": _ONE,
    "function::complex::argument": _ONE,
}

CONSTANTS = frozenset({"constant::pi", "constant::e", "constant::infinity"})

#: the operations a `manifest` line may single out
OPERATIONS = frozenset(UNARY + ARITHMETIC + DIVISION + REMAINDER) | frozenset(FUNCTIONS)


def _expression_signatures() -> dict[str, Signature]:
    out: dict[str, Signature] = {}
    for head in UNARY:
        out[head] = _sig(EXPR)
    for head in ARITHMETIC + DIVISION + REMAINDER + COMPARISON:
        out[head] = _sig(EXPR, EXPR)
    out["operator::logic::and"] = _sig(rest=EXPR, rest_min=2)
    out["operator::logic::or"] = _sig(rest=EXPR, rest_min=2)
    out["operator::logic::not"] = _sig(EXPR)
    out["operator::membership::in"] = _sig(EXPR, LITERALS)
    out["operator::membership::not_in"] = _sig(EXPR, LITERALS)
    for head, arity in FUNCTIONS.items():
        out[head] = _sig(rest=EXPR, rest_min=1) if arity is None else \
            _sig(*([EXPR] * arity[0]))
    for head in CONSTANTS:
        out[head] = _sig()
    out["value::absent"] = _sig(feature="option_result")
    out["value::field"] = _sig(NAME, rest=NAME, rest_min=1)
    out["value::index"] = _sig(SEQ, EXPR)
    out["value::length"] = _sig(SEQ)
    out["value::tuple"] = _sig(rest=EXPR, rest_min=2)
    out["value::item"] = _sig(EXPR, INT)
    out["value::conditional"] = _sig(EXPR, EXPR, EXPR)
    out["call::function"] = _sig(STR, rest=EXPR)
    out["call::library"] = _sig(STR, rest=EXPR, any_named=LITERAL)
    out["call::local"] = _sig(NAME, rest=EXPR)
    out["call::self"] = _sig(rest=EXPR)
    out["call::hashed"] = _sig(STR, rest=EXPR)
    out["call::ancestor"] = _sig(POSINT, rest=EXPR)
    out["call::external"] = _sig(STR, rest=EXPR)
    return out


EXPRESSIONS: dict[str, Signature] = _expression_signatures()

#: operators and functions with a `nonvalue::mathematical::singular`
#: region: a zero divisor, or zero to a negative power
SINGULAR_AT_ZERO_DIVISOR = frozenset(DIVISION + REMAINDER)

#: functions with a `nonvalue::mathematical::domain` region over the reals
DOMAIN_FUNCTIONS = frozenset({
    "function::root::square", "function::logarithm::natural",
    "function::logarithm::binary", "function::logarithm::decimal",
    "function::logarithm::natural_one_plus", "function::trigonometric::arcsine",
    "function::trigonometric::arccosine", "function::special::factorial",
    "function::special::gamma", "function::special::log_gamma",
})

# --- descriptions ------------------------------------------------------------

KINDS = frozenset(f"kind::{k}" for k in (
    "scalar", "int", "bool", "complex", "string", "sequence", "vec", "mat",
    "table", "dict", "unknown", "record"))
SEQUENCE_KINDS = frozenset({"kind::sequence", "kind::vec", "kind::mat"})

REPRS = frozenset(f"representation::{r}" for r in REPRESENTATION_WORDS)

#: why an expression has no value, by stratum: mathematics (the same
#: whatever runs it), the machine (a property of the representation),
#: the data (an input that is not there)
NONVALUES = frozenset({
    "nonvalue::mathematical::singular",
    "nonvalue::mathematical::domain",
    "nonvalue::machine::overflow",
    "nonvalue::data::absent",
})

#: how a runtime shows a non-value; `as::raise` names the type raised,
#: `as::complex` is a complex result where the reals have none (Python's
#: `**` of a negative base to a fractional power). A `manifest` line may
#: name the `operation:` it applies to; a line without one applies to
#: every operation the runtime has no more specific line for.
MANIFESTATIONS: dict[str, Signature] = {
    "as::raise": _sig(STR),
    "as::nonfinite": _sig(),
    "as::complex": _sig(),
    "as::panic": _sig(),
    "as::trap": _sig(),
    "as::undefined": _sig(),
    "as::absent": _sig(),
}

#: decline categories a body may be refused with: the derive route's
#: own first, then KOINE's
DECLINE_CATEGORIES = frozenset({
    "unsupported-statement", "unsupported-call", "unsupported-syntax",
    "unsupported-attribute", "unsupported-lambda", "unsupported-comprehension",
    "non-numeric-constant", "unbound-name", "tuple-in-expression",
    "missing-return",
    "mutation", "closure", "impure", "bitwise", "loose-equality",
    "truthy-coercion", "optionality", "nan-observation", "nonfinite-literal",
    "untyped-operand", "unsupported-koine-feature", "structure-conflict",
    "invalid-koine",
})

ALL_HEADS = frozenset(ENVELOPE) | frozenset(STATEMENTS) | frozenset(FAILURES) \
    | frozenset(EXPRESSIONS) | frozenset(MANIFESTATIONS) | KINDS | REPRS | NONVALUES \
    | {FIELD, SPAN_HEAD}
