# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The canonical form and `koine_hash`: what they drop, what they
respell, what they keep, and the specification's worked example, whose
canonical spelling and hash are fixed."""
from mathema.koine import Document, canonical_text, koine_hash, nominal_hash, nominal_text
from mathema.koine.canonical import canonical_terms
from tests._koine_docs import NONFINITE, at, doc, golden, growth, growth_restated

WORKED_EXAMPLE_CANONICAL = (
    'koine("0.0.1")\n'
    "parameter(_p0,kind::scalar)\n"
    "parameter(_p1,kind::scalar)\n"
    "body(statement::require(operator::logic::not(operator::comparison::less(_p1,-1)),"
    "failure::raise),statement::bind(_0,operator::binary::addition(1,_p1)),"
    "statement::return(operator::binary::multiplication(_p0,_0)))")

WORKED_EXAMPLE_NOMINAL = (
    'koine("0.0.1")\n'
    "parameter(x,kind::scalar)\n"
    "parameter(r,kind::scalar)\n"
    "body(statement::require(operator::logic::not(operator::comparison::less(r,-1)),"
    "failure::raise),statement::bind(_0,operator::binary::addition(1,r)),"
    "statement::return(operator::binary::multiplication(x,_0)))")


def test_the_worked_example_has_its_fixed_canonical_spelling_and_hash():
    for d in (growth(), golden("growth_py")):
        assert canonical_text(d) == WORKED_EXAMPLE_CANONICAL
        assert koine_hash(d) == "koine-0.0.1:989acc442e1bdcd6"


def test_the_worked_example_has_its_fixed_nominal_spelling_and_hash():
    for d in (growth(), golden("growth_py")):
        assert nominal_text(d) == WORKED_EXAMPLE_NOMINAL
        assert nominal_hash(d) == "koine-0.0.1:bd9102d9efb1342e"


def test_the_worked_example_hashes_alike_under_another_envelope():
    assert koine_hash(growth()) == koine_hash(growth_restated())
    assert koine_hash(growth()).startswith("koine-0.0.1:")
    assert len(koine_hash(growth())) == len("koine-0.0.1:") + 16


def test_what_is_kept():
    d = growth_restated()
    heads = [t.head for t in canonical_terms(d)]
    assert heads == ["koine", "parameter", "parameter", "body"]
    text = canonical_text(d)
    assert "at:" not in text and "RateError" not in text
    assert "failure::raise" in text
    assert "operator::comparison::less(_p1,-1)" in text


def test_canonical_is_deterministic_and_pure():
    d = growth()
    before = d.text()
    assert canonical_text(d) == canonical_text(d)
    assert d.text() == before


def test_locals_renamed_in_binding_order():
    a = doc(f"statement::bind(g, 1, {at()}), statement::bind(h, g, {at()}),"
            f" statement::return(operator::binary::multiplication(x, h), {at()})")
    b = doc(f"statement::bind(first, 1, {at()}), statement::bind(second, first, {at()}),"
            f" statement::return(operator::binary::multiplication(x, second), {at()})")
    assert koine_hash(a) == koine_hash(b)
    assert "statement::bind(_0,1)" in canonical_text(a)


def test_distinct_operations_hash_apart():
    def with_op(op):
        return koine_hash(doc(f"statement::return(operator::binary::{op}(x, r), {at()})"))
    ops = ["remainder::floor", "remainder::truncation", "remainder::euclidean",
           "division::real", "division::floor", "division::truncation", "division::euclidean"]
    assert len({with_op(o) for o in ops}) == len(ops)


def test_derived_functions_are_not_expanded():
    """hypot(a, b) and sqrt(a*a + b*b) agree in the reals and not in
    binary64 (the second overflows first), so they hash apart."""
    a = doc(f"statement::return(function::magnitude::hypotenuse(x, r), {at()})")
    b = doc("statement::return(function::root::square(operator::binary::addition("
            "operator::binary::multiplication(x, x), operator::binary::multiplication(r, r))), "
            f"{at()})")
    assert koine_hash(a) != koine_hash(b)


def test_spellings_that_do_not_move_the_hash():
    pairs = [
        ("operator::unary::negation(3)", "-3"),
        ("operator::unary::negation(1.5)", "-1.5"),
        ("1e-7", "1e-07"),
        ("0.10", "0.1"),
        ("operator::unary::identity(x)", "x"),
    ]
    for left, right in pairs:
        a = doc(f"statement::return(operator::binary::addition({left}, r), {at()})")
        b = doc(f"statement::return(operator::binary::addition({right}, r), {at()})")
        assert koine_hash(a) == koine_hash(b), (left, right)


def test_what_stays_outside_the_hash():
    base = doc(f"statement::return(x, {at()})")
    assert koine_hash(base) == koine_hash(doc(f"statement::return(x, {at(9)})",
                                              manifest=NONFINITE, name="other"))
    assert koine_hash(base) == koine_hash(Document.parse(base.text().replace(
        "returns(kind::scalar, representation::f64)", "returns(kind::unknown)")))
    # the representation is the machine: f32, i64 and f64 compute the
    # same mathematics
    narrower = Document.parse(base.text().replace(
        "parameter(x, kind::scalar, representation::f64)",
        "parameter(x, kind::scalar, representation::f32)"))
    assert koine_hash(base) == koine_hash(narrower)
    # the kind is the mathematics: a real and an integer differ
    integer = Document.parse(base.text().replace(
        "parameter(x, kind::scalar, representation::f64)",
        "parameter(x, kind::int, representation::i64)"))
    assert koine_hash(base) != koine_hash(integer)


def test_a_sequence_elements_representation_stays_outside_the_hash():
    params = "parameter(xs, kind::sequence, representation::f64, element: representation::{})"
    a = doc(f"statement::return(value::length(xs), {at()})", params=params.format("f64"))
    b = doc(f"statement::return(value::length(xs), {at()})", params=params.format("f32"))
    assert koine_hash(a) == koine_hash(b)


def test_an_integral_real_is_its_integer():
    """`1.0 + r` and `1 + r`, `r < -1.0` and `r < -1`: one number, one
    hash."""
    for left, right in [("1.0", "1"), ("-1.0", "-1"), ("operator::unary::negation(1.0)", "-1"),
                        ("2e3", "2000"), ("0.5", "0.5")]:
        a = doc(f"statement::return(operator::binary::addition({left}, r), {at()})")
        b = doc(f"statement::return(operator::binary::addition({right}, r), {at()})")
        assert koine_hash(a) == koine_hash(b), (left, right)
    half = doc(f"statement::return(operator::binary::addition(0.5, r), {at()})")
    one = doc(f"statement::return(operator::binary::addition(1, r), {at()})")
    assert koine_hash(half) != koine_hash(one)


def test_a_failure_kind_is_a_contract_its_type_a_spelling():
    def fail(failure):
        return koine_hash(doc(f"statement::fail({failure}, {at()})"))
    assert fail('failure::raise("A", message: "one")') == fail('failure::raise("B")')
    assert fail('failure::raise("A")') != fail('failure::panic("A")')


def test_the_canonical_spelling_parses():
    c = canonical_text(doc(f"statement::return(operator::unary::negation(1.5), {at()})"))
    assert canonical_text(Document.parse(c)) == c
