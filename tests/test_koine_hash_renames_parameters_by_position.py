# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Parameter names are documentation: the canonical form renames them
positionally, so two bodies that differ only in what they call their
inputs hash alike, while the nominal hash keeps the names for the
cases where the interface itself is the identity."""
from tests._koine_docs import doc
from mathema.koine import canonical_text, koine_hash, nominal_hash, nominal_text

GROWTH = """
  statement::bind(g, operator::binary::addition(1, r)),
  statement::return(operator::binary::multiplication(x, g)),
"""
GROWTH_RENAMED = """
  statement::bind(gain, operator::binary::addition(1, rate)),
  statement::return(operator::binary::multiplication(spot, gain)),
"""
RENAMED_PARAMS = """parameter(spot, kind::scalar, representation::f64)
parameter(rate, kind::scalar, representation::f64)"""
SWAPPED_PARAMS = """parameter(r, kind::scalar, representation::f64)
parameter(x, kind::scalar, representation::f64)"""


def test_bodies_differing_only_in_parameter_names_hash_alike():
    a = doc(GROWTH)
    b = doc(GROWTH_RENAMED, params=RENAMED_PARAMS)
    assert koine_hash(a) == koine_hash(b)
    assert canonical_text(a) == canonical_text(b)
    assert "parameter(_p0,kind::scalar)" in canonical_text(a)
    assert "multiplication(_p0,_0)" in canonical_text(a)


def test_the_nominal_hash_keeps_the_names_apart():
    a = doc(GROWTH)
    b = doc(GROWTH_RENAMED, params=RENAMED_PARAMS)
    assert nominal_hash(a) != nominal_hash(b)
    assert "parameter(x,kind::scalar)" in nominal_text(a)
    assert "multiplication(x,_0)" in nominal_text(a)
    assert nominal_hash(a) == nominal_hash(doc(GROWTH))


def test_parameter_order_is_part_of_the_mathematics():
    """`f(x, r) = x * (1 + r)` and `g(r, x) = x * (1 + r)` are different
    functions of their positional inputs."""
    a = doc(GROWTH)
    b = doc(GROWTH, params=SWAPPED_PARAMS)
    assert koine_hash(a) != koine_hash(b)


def test_record_field_names_stay():
    body = "statement::return(operator::binary::multiplication(x, value::field(cfg, rate)))"
    params = """parameter(cfg, kind::record, fields: [field(rate, kind::scalar, representation::f64)])
parameter(x, kind::scalar, representation::f64)"""
    text = canonical_text(doc(body, params=params))
    assert "field(rate,kind::scalar)" in text
    assert "value::field(_p0,rate)" in text
