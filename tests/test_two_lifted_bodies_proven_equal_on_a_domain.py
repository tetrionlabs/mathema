# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`prove_bodies_equal(left, right, domain)` on the extension surface:
two lifted bodies, as the KOINE documents a frontend wrote, compared on
a domain by core's derive rungs. Equal bodies are proven with the rung
named; bodies that differ are falsified only at a point executed on
both; refusal names are compared only when both bodies come from one
runtime."""
import math

import pytest

from mathema.interfaces.extension import BodyEquivalence, prove_bodies_equal

SHA = "0" * 64

X = "parameter(x, kind::scalar, representation::f64)"

AT = 'at: span(1, 1, "")'


def body(statements: str, *, language: str = "py", name: str = "f",
         params: str = X) -> str:
    """KOINE text for one function of one parameter `x`, written by a
    frontend for `language`."""
    return f"""koine("0.0.1")
lifter(language: "{language}", name: "t", version: "0")
source(file: "src/{name}", line: 1, sha256: "{SHA}")
function(name: "{name}", key: "{language}:src/{name}#{name}")
{params}
returns(kind::scalar, representation::f64)
body({statements})
"""


def returns(expression: str) -> str:
    return f"statement::return({expression}, {AT})"


TWICE = returns("operator::binary::multiplication(2, x)")
SUM_WITH_ITSELF = returns("operator::binary::addition(x, x)")
SQUARE = returns("operator::binary::multiplication(x, x)")


def guarded_root(failure: str, admits: str = "operator::logic::not("
                 "operator::comparison::less(x, 0))") -> str:
    return f"""statement::require(
    {admits},
    failure::raise("{failure}"), {AT}),
  {returns("function::root::square(x)")}"""


def test_the_same_body_from_two_frontends_is_proven_on_the_form_rung():
    left = body(TWICE, name="double")
    right = body(TWICE, language="ext", name="twice")
    answer = prove_bodies_equal(left, right, {"x": [-4.0, 4.0]})
    assert isinstance(answer, BodyEquivalence)
    assert answer.verdict == "proven", answer
    assert answer.rung == "form"
    assert answer.witness is None


def test_two_spellings_of_one_function_are_proven_on_the_symbolic_rung():
    answer = prove_bodies_equal(body(TWICE), body(SUM_WITH_ITSELF, language="ext"),
                                {"x": [-4.0, 4.0]})
    assert answer.verdict == "proven", answer
    assert answer.rung == "symbolic"
    assert answer.witness is None
    assert answer.sketch


def test_two_bodies_that_differ_are_falsified_at_an_executed_point():
    answer = prove_bodies_equal(body(TWICE), body(SQUARE, language="ext"),
                                {"x": [-4.0, 4.0]})
    assert answer.verdict == "falsified", answer
    assert answer.rung == "symbolic"
    assert answer.point is not None and set(answer.point) == {"x"}
    x = answer.point["x"]
    assert 2 * x != x * x
    assert answer.witness and "x" in answer.witness
    assert answer.meta["mathema.corroboration"] == "reproduced"


def test_bodies_equal_on_the_domain_but_not_beyond_it_are_proven_there():
    left = body(returns("function::magnitude::absolute(x)"))
    answer = prove_bodies_equal(left, body(returns("x"), language="ext"),
                                {"x": [0.0, 4.0]})
    assert answer.verdict == "proven", answer
    outside = prove_bodies_equal(left, body(returns("x"), language="ext"),
                                 {"x": [-4.0, 4.0]})
    assert outside.verdict == "falsified", outside
    assert outside.point["x"] < 0


def test_a_refusal_against_a_value_is_falsified_at_the_executed_point():
    refusing = body(guarded_root("ValueError"))
    answer = prove_bodies_equal(
        refusing, body(returns("function::root::square("
                               "function::magnitude::absolute(x))"), language="ext"),
        {"x": [-4.0, 4.0]})
    assert answer.verdict == "falsified", answer
    assert answer.point["x"] < 0
    assert "raised" in answer.witness


def test_differently_named_refusals_across_runtimes_are_not_compared():
    answer = prove_bodies_equal(
        body(guarded_root("ValueError")),
        body(guarded_root("DomainError", "operator::comparison::greater_equal(x, 0)"),
             language="ext"),
        {"x": [-4.0, 4.0]})
    assert answer.verdict == "proven", answer
    assert answer.rung == "symbolic"
    assert "ValueError" in answer.sketch and "DomainError" in answer.sketch


def test_one_body_refusing_under_two_names_across_runtimes_has_one_form():
    answer = prove_bodies_equal(body(guarded_root("ValueError")),
                                body(guarded_root("DomainError"), language="ext"),
                                {"x": [-4.0, 4.0]})
    assert answer.verdict == "proven", answer
    assert answer.rung == "form"


def test_refusals_on_different_regions_across_runtimes_are_falsified():
    answer = prove_bodies_equal(
        body(guarded_root("ValueError")),
        body(guarded_root("DomainError", "operator::comparison::greater_equal(x, 1)"),
             language="ext"),
        {"x": [-4.0, 4.0]})
    assert answer.verdict == "falsified", answer
    assert 0 <= answer.point["x"] < 1


def test_differently_named_refusals_in_one_runtime_are_falsified():
    answer = prove_bodies_equal(body(guarded_root("ValueError")),
                                body(guarded_root("ArithmeticError")),
                                {"x": [-4.0, 4.0]})
    assert answer.rung != "form"
    assert answer.verdict == "falsified", answer
    assert answer.point["x"] < 0
    assert "ValueError" in answer.witness and "ArithmeticError" in answer.witness


def test_the_domain_names_the_left_body_parameters_and_aligns_by_position():
    right = body(SUM_WITH_ITSELF.replace("x", "y"), language="ext",
                 params="parameter(y, kind::scalar, representation::f64)")
    answer = prove_bodies_equal(body(TWICE), right, {"x": [-4.0, 4.0]})
    assert answer.verdict == "proven", answer


def test_bodies_of_different_arity_are_not_compared():
    two = body(returns("operator::binary::addition(x, r)"),
               params=X + "\nparameter(r, kind::scalar, representation::f64)")
    answer = prove_bodies_equal(body(TWICE), two, {"x": [-4.0, 4.0]})
    assert answer.verdict == "unknown"
    assert answer.rung is None
    assert "arity" in answer.note


def test_a_document_the_engine_declines_is_an_error():
    import pytest
    with pytest.raises(ValueError):
        prove_bodies_equal("not koine", body(TWICE), {"x": [-4.0, 4.0]})


def test_two_bodies_calling_a_sibling_are_compared_through_it():
    helper_key = "py:src/scaled#scaled"
    helper = body(returns("operator::binary::multiplication(3, x)"), name="scaled")
    calling = body(returns(f'operator::binary::addition(call::function("{helper_key}", x), 1)'))
    inlined = body(returns("operator::binary::addition("
                           "operator::binary::multiplication(3, x), 1)"), language="ext")
    unbound = prove_bodies_equal(calling, inlined, {"x": [-4.0, 4.0]})
    assert unbound.verdict != "proven", unbound
    answer = prove_bodies_equal(calling, inlined, {"x": [-4.0, 4.0]},
                                siblings={helper_key: helper})
    assert answer.verdict == "proven", answer


def test_a_domain_name_the_left_body_does_not_have_is_an_error():
    import pytest
    with pytest.raises(ValueError, match="not a parameter"):
        prove_bodies_equal(body(TWICE), body(SUM_WITH_ITSELF), {"y": [0.0, 1.0]})


def test_a_bound_given_as_text_is_read_and_stated():
    answer = prove_bodies_equal(body(returns("function::magnitude::absolute(x)")),
                                body(returns("x"), language="ext"), {"x": "(0, inf)"})
    assert answer.verdict == "proven", answer
    assert answer.meta["mathema.domain"]["x"].startswith("(0")


# --- two bodies refusing on one region are compared where both return ---

ROOT = "function::root::square(x)"
SQUARED = "operator::binary::multiplication(x, x)"
TWICE_ROOT = "operator::binary::multiplication(2, function::root::square(x))"
ROOT_NUDGED = "operator::binary::addition(function::root::square(x), 1e-12)"
NOT_NEGATIVE = "operator::comparison::greater_equal(x, 0)"


def guarded(expression: str, failure: str = "ValueError",
            admits: str = "operator::logic::not("
                          "operator::comparison::less(x, 0))") -> str:
    """A body that refuses where `admits` fails and returns
    `expression` elsewhere."""
    return f"""statement::require(
    {admits},
    failure::raise("{failure}"), {AT}),
  {returns(expression)}"""


#: (right body's expression, its refusal name, its language)
GUARDED_PAIRS = [
    (SQUARED, "ValueError", "py"),
    (SQUARED, "DomainError", "ext"),
    (TWICE_ROOT, "ValueError", "py"),
    (TWICE_ROOT, "DomainError", "ext"),
    (ROOT_NUDGED, "ValueError", "py"),
    (ROOT, "ValueError", "py"),
]


@pytest.mark.parametrize("expression, failure, language", GUARDED_PAIRS)
def test_bodies_refusing_alike_answer_as_they_do_where_both_return(
        expression, failure, language):
    both_refusing = prove_bodies_equal(
        body(guarded(ROOT)),
        body(guarded(expression, failure, admits=NOT_NEGATIVE),
             language=language),
        {"x": [-4.0, 4.0]})
    where_both_return = prove_bodies_equal(
        body(returns(ROOT)), body(returns(expression), language="ext"),
        {"x": [0.0, 4.0]})
    assert both_refusing.verdict == where_both_return.verdict, (
        both_refusing, where_both_return)
    assert (both_refusing.meta.get("mathema.corroboration")
            == where_both_return.meta.get("mathema.corroboration"))


@pytest.mark.parametrize("language", ["py", "ext"])
def test_bodies_refusing_alike_but_differing_elsewhere_are_falsified(language):
    answer = prove_bodies_equal(
        body(guarded(ROOT)),
        body(guarded(SQUARED, "ValueError" if language == "py"
                     else "DomainError"), language=language),
        {"x": [-4.0, 4.0]})
    assert answer.verdict == "falsified", answer
    assert answer.rung == "symbolic"
    x = answer.point["x"]
    assert 0 <= x <= 4 and math.sqrt(x) != x * x, answer
    assert "f returned" in answer.witness and "g returned" in answer.witness
    assert answer.meta["mathema.corroboration"] == "reproduced"


def test_bodies_refusing_alike_and_agreeing_elsewhere_are_proven():
    answer = prove_bodies_equal(
        body(guarded(ROOT)), body(guarded(ROOT, admits=NOT_NEGATIVE)),
        {"x": [-4.0, 4.0]})
    assert answer.verdict == "proven", answer
    assert answer.rung == "symbolic"


def test_a_difference_below_any_float_tolerance_is_falsified_exactly():
    answer = prove_bodies_equal(
        body(guarded(ROOT)), body(guarded(ROOT_NUDGED, admits=NOT_NEGATIVE)),
        {"x": [-4.0, 4.0]})
    assert answer.verdict == "falsified", answer
    assert answer.meta["mathema.corroboration"] == "reproduced"
    assert 0 <= answer.point["x"] <= 4
