# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The renderer: a KOINE body written as the liftable Python subset
computes what the interpreter says, agrees with the Python function the
document was written from, and proves through the derive route the
claims that function proves."""
import ast
import inspect
import math

import pytest

import mathema
from mathema.koine import Document, interpret
from mathema.koine._render import (
    RenderError,
    exception_class,
    materialise,
    namespace,
    render,
)
from mathema.koine.interpret import Value
from tests._koine_docs import (
    GROWTH_BODY,
    LOCAL_AND_CALLS,
    OPS,
    SEQUENCE,
    at,
    doc,
    golden,
    growth,
    koine_fixture,
)

koine_py = koine_fixture()

GOLDEN_FUNCTIONS = {"growth_py": "growth", "ema_first_py": "ema", "piecewise_py": "tax",
                    "dot_py": "dot", "mean_py": "mean", "quotient_py": "quotient",
                    "remainders_py": "remainders"}


def spelled(fragment):
    """The fragment as this Python's `ast.unparse` spells it, the
    spelling the renderer writes: a compound-statement header such as
    `for i, v in enumerate(xs):` is parsed with a `pass` body and only
    its header line kept, so `for (i, v) in ...` on 3.10 and
    `for i, v in ...` on later versions both match."""
    header = fragment.endswith(":")
    tree = ast.parse(fragment + " pass" if header else fragment)
    text = ast.unparse(tree)
    return text.splitlines()[0] if header else text


def verdicts(rec):
    """Named claims only, without the `[float]` companion and the
    default policy rows."""
    return {p.name: (p.verdict, p.route) for p in rec.probes
            if not p.name.endswith("[float]") and p.name != "purity"
            and (p.meta or {}).get("mathema.surface") != "mathema"}


def test_growth_renders_to_the_liftable_subset():
    r = render(growth())
    assert r.source.startswith("def growth(x: float, r: float) -> float:")
    assert spelled("if r < -1:") in r.source and spelled("raise ValueError") in r.source
    assert r.exceptions == {"ValueError"}
    assert r.line_map == {2: 2, 4: 3, 5: 4}


def test_the_materialised_function():
    fn = materialise(render(growth()), key="py:src/growth.py#growth")
    assert fn(2.0, 0.5) == interpret(growth(), [2.0, 0.5]).value
    with pytest.raises(ValueError) as caught:
        fn(2.0, -2.0)
    assert type(caught.value) is ValueError
    assert "def growth" in inspect.getsource(fn)
    assert fn.__mathema_key__ == "py:src/growth.py#growth"


def test_a_qualified_failure_type_is_raised_under_its_last_segment():
    d = doc(GROWTH_BODY.replace('"ValueError"', '"pkg.errors.RateError"'), name="growth")
    r = render(d)
    assert r.exceptions == {"pkg.errors.RateError"}
    assert spelled("raise RateError()") in r.source
    with pytest.raises(Exception) as caught:
        materialise(r)(2.0, -2.0)
    assert type(caught.value).__name__ == "pkg.errors.RateError"


def test_a_builtin_failure_type_is_the_builtin_itself():
    assert exception_class("ValueError", "m") is ValueError
    made = exception_class("pkg.ValueError", "m")
    assert made is not ValueError and issubclass(made, ValueError)
    assert issubclass(exception_class("RateError", "m"), Exception)
    scope = namespace(render(growth()))
    assert scope["ValueError"] is ValueError and scope["math"] is math
    assert scope["div_trunc"].__koine__ == "operator::binary::division::truncation"


@pytest.mark.parametrize("name", sorted(GOLDEN_FUNCTIONS))
def test_every_golden_document_renders_and_materialises(name):
    fn = materialise(render(golden(name)))
    assert fn.__name__ == GOLDEN_FUNCTIONS[name]


def test_the_rendered_growth_proves_through_derive():
    fn = materialise(render(golden("growth_py")))
    rec = mathema.check(fn, claims=[
        "for r in [-1, 5], for x in [-10, 10], f(x, r) == x * (1 + r)",
        "for r in [-5, -1.5], raises(f(x, r), ValueError)",
    ])
    assert set(verdicts(rec).values()) == {("proven", "derive")}, verdicts(rec)


def test_the_rendering_and_the_original_prove_alike():
    claim = "for r in [-1, 5], for x in [-10, 10], f(x, r) == x * (1 + r)"
    rendered = materialise(render(golden("growth_py")))
    assert verdicts(mathema.check(rendered, claims=[claim])) == \
        verdicts(mathema.check(koine_py.growth, claims=[claim]))


def test_the_fold_renders_over_the_tail():
    r = render(golden("ema_first_py"))
    assert spelled("for v in xs[1:]:") in r.source
    assert materialise(r)([1.0, 2.0, 3.0], 0.5) == 2.25


def test_operations_without_a_python_spelling_use_the_helpers():
    r = render(doc(OPS))
    for spelling in ("math.fmod(x, r)", "math.hypot(x, r)", "round_ties_up(x)",
                     "div_trunc(x, r)", "sign(x)", "math.pi"):
        assert spelled(spelling) in r.source, spelling
    fn = materialise(r)
    assert fn(-7.5, 2.0)[:4] == (-1.5, pytest.approx(7.762087348130012), -7, -3.0)


def test_locals_and_externals():
    r = render(doc(LOCAL_AND_CALLS))
    assert spelled("sq = lambda t: t * t") in r.source
    assert r.externals == {"twice": "py:src/shapes.py#twice"}
    with pytest.raises(NameError, match="no binding for external 'twice'"):
        materialise(r)
    assert materialise(r, bindings={"twice": lambda v: 2 * v})(4.0, 3.0) == pytest.approx(20.0)


def test_loop_forms():
    each = doc(f"""
      statement::bind(acc, 0, {at()}),
      statement::loop::each(v, xs, 0, [
        statement::update(acc, operator::binary::addition,
                          operator::binary::multiplication(i, v), {at()}),
      ], {at()}, index: i),
      statement::return(acc, {at()}),
    """, params=SEQUENCE)
    assert spelled("for i, v in enumerate(xs):") in render(each).source
    assert materialise(render(each))([1.0, 2.0, 3.0], 0.0) == 8.0
    bad = Document.parse(each.text().replace("statement::loop::each(\n    v,\n    xs,\n    0,",
                                             "statement::loop::each(\n    v,\n    xs,\n    1,"))
    assert bad != each
    with pytest.raises(RenderError):
        render(bad)


POINTS = {
    "growth_py": [[2.0, 0.5], [-3.0, 1.0]],
    "ema_first_py": [[[1.0, 2.0, 3.0], 0.5], [[4.0], 0.25]],
    "piecewise_py": [[-1.0, 2.0], [0.25, 2.0], [3.0, 2.0]],
    "dot_py": [[[1.0, 2.0], [3.0, 4.0]]],
    "mean_py": [[[1.0, 2.0, 6.0]], [[0.5]]],
    "quotient_py": [[-7, 2], [7, -2], [9, 3]],
    "remainders_py": [[-7.5, 2.0], [7.5, -2.0], [2.5, 1.0]],
}


@pytest.mark.parametrize("name", sorted(POINTS))
def test_rendering_interpretation_and_the_original_agree(name):
    d = golden(name)
    fn = materialise(render(d))
    original = getattr(koine_py, GOLDEN_FUNCTIONS[name])
    for pt in POINTS[name]:
        expected = interpret(d, pt)
        assert isinstance(expected, Value), (name, pt, expected)
        assert fn(*pt) == expected.value == original(*pt), (name, pt)


def test_rendering_and_interpretation_agree_on_the_helpers():
    d = doc(OPS)
    fn = materialise(render(d))
    for pt in ([-7.5, 2.0], [7.5, -2.0], [2.5, 1.0]):
        assert fn(*pt) == interpret(d, pt).value
