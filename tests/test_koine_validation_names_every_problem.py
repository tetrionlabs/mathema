# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The validator: each signature and each scope rule refuses exactly
the document that breaks it, and says where."""
import pytest
from mathema.koine import Document, validate
from tests._koine_docs import SEQUENCE, at, doc, golden, growth, growth_restated, koi


def problems(body: str, **kw) -> str:
    return "\n".join(validate(doc(body, **kw)))


def test_the_worked_example_is_valid():
    assert validate(growth()) == [] and validate(growth_restated()) == []
    assert validate(golden("growth_py")) == []


def test_not_a_document():
    assert validate("koine(1)") == ["document: not a KOINE document"]


def test_the_envelope():
    text = koi(f"statement::return(x, {at()})").replace('koine("0.0.1")', 'koine("0.0.2")\nkoine("0.0.1")')
    text = text.replace('language: "py"', 'language: "PY"').replace(f'"{"0" * 64}"', '"abc"')
    text += 'manifest(nonvalue::mathematical::singular, as::trap)\nnonsense(1)\nfeature(telepathy)\n'
    found = "\n".join(validate(Document.parse(text)))
    for needle in ("koine: this is KOINE 0.0.1, the document says \"0.0.2\"",
                   "document: koine(...) appears 2 times",
                   "'PY' is not a language tag",
                   "sha256 must be 64 lowercase hex digits",
                   "manifest: nonvalue::mathematical::singular is given twice",
                   "nonsense(1) is not a document term",
                   "unknown feature telepathy"):
        assert needle in found, needle
    bare = Document.parse('koine("0.0.1")\nbody()\n')
    assert "document: lifter(...) is missing" in "\n".join(validate(bare))


def test_parameters():
    params = """parameter(x, kind::scalar, representation::f64)
parameter(x, kind::scalar)
parameter(y, kind::tensor)
parameter(z, kind::scalar, representation::f128)
parameter(cfg, kind::record)"""
    found = problems(f"statement::return(1, {at()})", params=params)
    for needle in ("parameter: x is declared twice", "expected a kind::, got kind::tensor",
                   "expected a representation::, got representation::f128",
                   "record cfg names no fields"):
        assert needle in found, needle


def test_signatures():
    found = problems(f"""
      statement::bind(g, operator::binary::addition(x), {at()}),
      statement::bind(h, function::order::clamp(x, r), {at()}),
      statement::bind(k, operator::binary::division::banker(x, r), {at()}),
      statement::evaluate(x),
      statement::return(g, {at()}, extra: 1),
    """)
    for needle in ("body[0].arg[1]: operator::binary::addition takes 2 positional argument(s), got 1",
                   "body[1].arg[1]: function::order::clamp takes 3 positional argument(s), got 2",
                   "body[2].arg[1]: operator::binary::division::banker(x, r) is not an expression",
                   "body[4]: statement::return takes no argument named extra",
                   "body[3]: statement::evaluate requires at:"):
        assert needle in found, needle


def test_scope():
    found = problems(f"""
      statement::bind(x, 1, {at()}),
      statement::update(acc, operator::binary::addition, 1, {at()}),
      statement::update(r, operator::binary::power, 1, {at()}),
      statement::return(y, {at()}),
    """)
    for needle in ("body[0].arg[0]: parameter x may not be assigned",
                   "body[1].arg[0]: must name a local bound earlier",
                   "body[2].arg[1]: expected an update operator, got operator::binary::power",
                   "body[3].arg[0]: y is not bound here"):
        assert needle in found, needle


def test_nothing_follows_a_return():
    assert problems(f"statement::return(x, {at()}), statement::bind(g, 1, {at()})") == \
        "body[1]: nothing may follow a return or a fail"


def test_a_branch_binds_what_both_arms_bind():
    found = problems(f"""
      statement::branch(operator::comparison::greater(x, 0),
        [statement::bind(a, 1, {at()}), statement::bind(b, 2, {at()})],
        [statement::bind(a, 3, {at()})], {at()}),
      statement::return(operator::binary::addition(a, b), {at()}),
    """)
    assert found == "body[1].arg[0].arg[1]: b is not bound here"


def test_loops():
    good = f"""
      statement::bind(acc, value::index(xs, 0), {at()}),
      statement::loop::each(v, xs, 1, [
        statement::bind(acc, operator::binary::addition(acc, v), {at()}),
      ], {at()}),
      statement::return(acc, {at()}),
    """
    assert problems(good, params=SEQUENCE) == ""
    bad = f"""
      statement::bind(acc, 0, {at()}),
      statement::loop::each(v, alpha, 2, [
        statement::require(operator::comparison::greater(v, 0), failure::raise("E"), {at()}),
      ], {at()}),
      statement::loop::range(i, 0, value::length(xs), 0, [], {at()}),
      statement::return(v, {at()}),
    """
    found = problems(bad, params=SEQUENCE)
    for needle in ("body[1].arg[2]: expected 0 or 1, got 2",
                   "body[1].arg[1]: alpha is not a sequence parameter",
                   "body[1].arg[3][0]: statement::require is not allowed inside a loop",
                   "body[2].arg[3]: expected a positive integer, got 0",
                   "body[3].arg[0]: v is not bound here"):
        assert needle in found, needle


def test_local_functions():
    found = problems(f"""
      statement::define(sq, [t], operator::binary::multiplication(t, t), {at()}),
      statement::return(operator::binary::addition(call::local(sq, x), call::local(sq, x, r)), {at()}),
    """)
    assert found == "body[1].arg[0].arg[1]: sq takes 1 argument(s), got 2"


def test_literals_features_fields_and_membership():
    found = problems(f"""
      statement::bind(a, value::absent, {at()}),
      statement::bind(b, value::field(x, rate), {at()}),
      statement::bind(c, operator::membership::in(x, [1, r]), {at()}),
      statement::bind(d, 1e999, {at()}),
      statement::return(operator::logic::and(true), {at()}),
    """)
    for needle in ("body[0].arg[1]: value::absent needs feature(option_result)",
                   "body[1].arg[1].arg[0]: must name a record parameter",
                   "body[2].arg[1].arg[1][1]: expected a literal, got r",
                   "body[3].arg[1]: 1e999 is not a finite real",
                   "body[4].arg[0]: operator::logic::and takes at least 2 argument(s), got 1"):
        assert needle in found, needle
    assert problems(f"statement::return(value::absent, {at()})",
                    extra="feature(option_result)") == ""


@pytest.mark.parametrize("failure, needle", [
    ('failure::explode("E")', "expected a failure::"),
    ('failure::raise("")', "the failure type is empty"),
    ("failure::raise(E)", "expected a string, got E"),
])
def test_failures(failure, needle):
    assert needle in problems(f"statement::fail({failure}, {at()})")
