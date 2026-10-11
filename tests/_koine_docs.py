# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""KOINE documents for the tests, written as KOINE: `koi(body, ...)`
wraps statements in a valid envelope, and the golden corpus is read
from `tests/data/koine`."""
import importlib.util
import pathlib

import yaml

from mathema.koine import Document

GOLDEN = pathlib.Path(__file__).resolve().parent / "data" / "koine"

SHA = "0" * 64

SCALARS = """parameter(x, kind::scalar, representation::f64)
parameter(r, kind::scalar, representation::f64)"""

SEQUENCE = """parameter(xs, kind::sequence, representation::f64, element: representation::f64)
parameter(alpha, kind::scalar, representation::f64)"""

PY = """manifest(nonvalue::mathematical::singular, as::raise("ZeroDivisionError"))
manifest(nonvalue::mathematical::domain, as::raise("ValueError"))
manifest(nonvalue::machine::overflow, as::raise("OverflowError"))"""

NONFINITE = """manifest(nonvalue::mathematical::singular, as::nonfinite)
manifest(nonvalue::mathematical::domain, as::nonfinite)
manifest(nonvalue::machine::overflow, as::nonfinite)"""


def koi(body: str, *, params: str = SCALARS, manifest: str = PY, name: str = "f",
        extra: str = "", lifter: str = "test") -> str:
    """A KOINE text: the envelope around `body`, a comma-separated run
    of statements."""
    return f"""koine("0.0.1")
{extra}
lifter(language: "py", name: "{lifter}", version: "0")
source(file: "src/{name}.py", line: 1, sha256: "{SHA}")
function(name: "{name}", key: "py:src/{name}.py#{name}")
{params}
returns(kind::scalar, representation::f64)
{manifest}
body({body})
"""


def doc(body: str, **kw) -> Document:
    return Document.parse(koi(body, **kw))


def at(line: int = 1) -> str:
    return f'at: span({line}, {line}, "")'


def golden_text(name: str) -> str:
    return (GOLDEN / f"{name}.koi").read_text()


def golden(name: str) -> Document:
    return Document.parse(golden_text(name))


def koine_fixture():
    """The module `tests/fixtures/koine_py.py`, whose functions the
    golden documents were written from."""
    path = GOLDEN.parent.parent / "fixtures" / "koine_py.py"
    spec = importlib.util.spec_from_file_location("koine_py", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def golden_index() -> dict:
    return yaml.safe_load((GOLDEN / "golden.yaml").read_text())


GROWTH_BODY = f"""
  statement::require(
    operator::logic::not(operator::comparison::less(r, operator::unary::negation(1))),
    failure::raise("ValueError"), {at(2)}),
  statement::bind(g, operator::binary::addition(1, r), {at(3)}),
  statement::return(operator::binary::multiplication(x, g), {at(4)}),
"""


def growth() -> Document:
    """The worked example, `growth`, with the Python manifest."""
    return doc(GROWTH_BODY, name="growth")


def growth_restated() -> Document:
    """The worked example under another envelope: another writer,
    another file, a runtime that shows every non-value as a non-finite
    number, and a refusal of another type."""
    return doc(GROWTH_BODY.replace('"ValueError"', '"RateError"'), manifest=NONFINITE,
               name="growth", lifter="other")


#: locals, a local function, a swap and a call by key
LOCAL_AND_CALLS = f"""
  statement::define(sq, [t], operator::binary::multiplication(t, t), {at(2)}),
  statement::bind_many([a, b], [r, x], {at(3)}),
  statement::bind_many([a, b], [b, a], {at(4)}),
  statement::return(operator::binary::addition(
    operator::binary::addition(call::local(sq, b), call::function("py:src/shapes.py#twice", a)),
    operator::binary::addition(function::root::square(function::magnitude::absolute(a)), 1)),
    {at(5)}),
"""

#: operations with no exact Python operator, and a constant
OPS = f"""
  statement::return(value::tuple(
    operator::binary::remainder::truncation(x, r),
    function::magnitude::hypotenuse(x, r),
    function::rounding::ties_up(x),
    operator::binary::division::truncation(x, r),
    function::magnitude::sign(x),
    constant::pi), {at(2)}),
"""

#: a record parameter read by field
RECORD = """parameter(cfg, kind::record, fields: [field(rate, kind::scalar, representation::f64),
  field(years, kind::scalar, representation::f64)])
parameter(x, kind::scalar, representation::f64)"""

RECORD_BODY = f"""
  statement::return(operator::binary::multiplication(x, operator::binary::power(
    operator::binary::addition(1, value::field(cfg, rate)), value::field(cfg, years))), {at(2)}),
"""
