# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter that bundles many scalars into one (a flat @dataclass, or
a dict accessed only via literal string keys) is liftable by expanding
into one symbol per field/key (see _bind_params/Lifted's docstring in
symbolic.py), rather than lift() refusing the whole function outright
because the parameter itself isn't a bare scalar."""
from dataclasses import dataclass

from mathema.conjecture import claim, check_conjectures
from mathema.inventory import is_pure_enough


@dataclass
class Config:
    a: float
    b: float


def sum_fields(cfg: Config) -> float:
    return cfg.a + cfg.b


def scaled_with_offset(cfg: Config, x: float) -> float:
    return cfg.a * x + cfg.b


def sum_dict(params: dict) -> float:
    return params["a"] + params["b"]


def test_is_pure_enough_true_for_a_flat_dataclass_parameter():
    assert is_pure_enough(sum_fields) is True


def test_is_pure_enough_true_for_a_named_dict_parameter():
    assert is_pure_enough(sum_dict) is True


def test_dataclass_field_access_proves_correctly():
    results = check_conjectures(
        sum_fields, [claim("f(cfg) == cfg.a + cfg.b", route="derive")])
    assert results[0].verdict == "proven"


def test_dataclass_field_access_falsifies_a_wrong_formula():
    results = check_conjectures(
        sum_fields, [claim("f(cfg) == cfg.a - cfg.b", route="derive")])
    assert results[0].verdict == "falsified"


def test_dataclass_parameter_mixes_with_an_ordinary_scalar_parameter():
    results = check_conjectures(
        scaled_with_offset,
        [claim("f(cfg, x) == cfg.a * x + cfg.b", route="derive")])
    assert results[0].verdict == "proven"


def test_named_dict_field_access_proves_correctly():
    results = check_conjectures(
        sum_dict, [claim('f(params) == params["a"] + params["b"]', route="derive")])
    assert results[0].verdict == "proven"


def test_bare_reference_to_a_bundled_parameter_is_a_clear_error():
    # a bare `cfg` (no field access) must not silently become a phantom
    # free/aux variable; it has no single scalar value.
    results = check_conjectures(
        sum_fields, [claim("f(cfg) == cfg", route="derive")])
    # never a phantom free variable: the clear error is kept in the
    # note, and probing then compares the sum against the dataclass
    # itself, which is simply unequal
    assert results[0].verdict == "falsified"
    assert "bundles multiple fields" in results[0].note


def test_f_call_reusing_the_same_bundled_parameter_name_still_works():
    # f(cfg) appearing on both sides is a no-op substitution for cfg's
    # own slot, must not be confused with "substituting a different
    # value", which is the case that's actually unsupported.
    results = check_conjectures(
        sum_fields, [claim("f(cfg) == f(cfg) + 0", route="derive")])
    assert results[0].verdict == "proven"
