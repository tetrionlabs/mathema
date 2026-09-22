# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""finite_sets.py: OpaqueRegistry and is_opaque_eligible directly,
the derive-route integration tests (tests/test_symbolic.py's own
"finite sets" section) exercise this through real claims; these test
the module's own contract in isolation."""
from enum import Enum

from mathema.finite_sets import OpaqueRegistry, is_opaque_eligible


class Scale(Enum):
    INFO = "info"
    CHANCE = "chance"


def test_is_opaque_eligible_accepts_str_none_enum():
    assert is_opaque_eligible("hello")
    assert is_opaque_eligible(None)
    assert is_opaque_eligible(Scale.INFO)


def test_is_opaque_eligible_rejects_bool_and_arbitrary_objects():
    assert not is_opaque_eligible(True)
    assert not is_opaque_eligible(False)
    assert not is_opaque_eligible(3.14)
    assert not is_opaque_eligible(b"bytes")
    assert not is_opaque_eligible(object())


def test_is_opaque_eligible_tuple_only_if_every_element_is():
    # capability kept in the module for future use even though nothing
    # currently wires it into the derive route, see the derive-route
    # docs for why (a real conflict with the existing tuple-return/
    # elementwise-comparison semantics, not yet resolved).
    assert is_opaque_eligible(("info", "chance"))
    assert is_opaque_eligible(("info", None))
    assert not is_opaque_eligible(("info", 3.14))
    assert not is_opaque_eligible(("info", object()))


def test_registry_same_value_returns_same_symbol():
    reg = OpaqueRegistry()
    a = reg.register("foo")
    b = reg.register("foo")
    assert a == b


def test_registry_different_values_return_different_symbols():
    reg = OpaqueRegistry()
    a = reg.register("foo")
    b = reg.register("bar")
    assert a != b


def test_registry_none_is_pre_registered_and_stable():
    reg = OpaqueRegistry()
    assert reg.register(None) == reg.none_symbol
    assert reg.value_of(reg.none_symbol) is None


def test_registry_value_of_round_trips():
    reg = OpaqueRegistry()
    sym = reg.register("positive")
    assert reg.value_of(sym) == "positive"


def test_registry_value_of_unknown_symbol_is_none():
    reg = OpaqueRegistry()
    other = OpaqueRegistry().register("only in the other registry")
    assert reg.value_of(other) is None


def test_registry_is_opaque_symbol():
    reg = OpaqueRegistry()
    sym = reg.register("x")
    assert reg.is_opaque_symbol(sym)
    other_reg = OpaqueRegistry()
    other_sym = other_reg.register("x")
    # same *value* registered in a different registry, a different
    # symbol object/name, correctly not recognized as this registry's own.
    assert not reg.is_opaque_symbol(other_sym)


def test_registry_two_distinct_registries_never_share_symbols():
    # each OpaqueRegistry is scoped to one lift, two different
    # registries registering the identical *value* must still get
    # different symbols, since nothing threads them together unless a
    # caller explicitly shares one (see try_prove()'s own Lifted.opaque
    # wiring in symbolic.py).
    a = OpaqueRegistry().register("shared value")
    b = OpaqueRegistry().register("shared value")
    assert a != b
