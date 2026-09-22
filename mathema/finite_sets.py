# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Finite sets for non-numeric values in the derive route.

A branch/ternary/fold that resolves down to picking one of several
literal, non-numeric values (a string, `None`, an enum member) has
nowhere to go once resolved: sympy is a numeric-algebra system, and
`_expr_to_sympy`'s own `ast.Constant` case refuses any non-numeric
constant outright. This module gives such a value somewhere to go,
not by teaching sympy about strings, but by treating each *distinct*
value as an opaque member of a small, implicit finite set: a stable,
untyped sympy Symbol stands in for it structurally (equal to itself,
unrelated to any other value's symbol, never orderable, since it
carries none of sympy's numeric assumptions), and a hashmap-backed
registry keeps the real value recoverable afterward, so a proof's
sketch or a disproof's counterexample can render in terms of the
actual value rather than a meaningless symbol name.

This is deliberately not a general vector/set-algebra facility, just
enough structure to let equality-only reasoning about a small, known,
non-numeric value flow through the existing derive-route machinery.
Two distinct registered values are never provably *unequal* by this
alone (`_prove_relation()` isn't touched here, a claim comparing two
different known values stays honestly `undecided`, not falsely
`disproven`, until that's built); ordering (`<=`/`>=`) is never
meaningful for an opaque value and isn't attempted. Real set algebra,
union/intersection/membership over an actual Python `set`/`frozenset`
value, provable inequality, ordering, is deliberately out of scope
for this module."""
from __future__ import annotations

from enum import Enum

import sympy


def is_opaque_eligible(value) -> bool:
    """Is `value` one of the non-numeric shapes this module registers?
    `str`, `None`, and `Enum` members directly; a `tuple` only if every
    one of its own elements is (recursively) eligible too, a fixed
    categorical row (`("info", "chance")`), not an arbitrary tuple of
    computed values (those are `_expr_to_sympy`'s own existing multi-
    return-value shape, untouched by this module; see
    OpaqueRegistry's own docstring and the derive-route docs for how
    the two are told apart). `bool` is deliberately excluded: a bare
    `True`/`False` constant is refused by `_expr_to_sympy`'s own
    `ast.Constant` case already, for reasons unrelated to and predating
    this module, not something registering it here would fix, since
    that refusal happens before this function is ever consulted."""
    if value is None or isinstance(value, str) or isinstance(value, Enum):
        return True
    if isinstance(value, tuple):
        return all(is_opaque_eligible(v) for v in value)
    return False


class OpaqueRegistry:
    """A value <-> `sympy.Symbol` bijection, one per lift (one per
    top-level `lift()`/`lift_fold()`/`lift_dot()`/`lift_sum()` call,
    shared across a callee-inlining chain within `lift()` itself since
    an opaque value's meaning doesn't depend on which function produced
    it, see the derive-route docs). Every distinct value (by `==`,
    real dict-key equality) gets exactly one stable symbol, created on
    first registration and reused after, so the same string appearing
    twice in one function's body, or once in the body and once in a
    claim's own law text, resolves to the identical symbol both times,
    which is what makes an equality claim about it provable at all.

    `None` is pre-registered at construction (`self.none_symbol`),
    not registered lazily like everything else, purely so every
    registry's own "empty" slot exists unconditionally from the start;
    the symbol itself is still only meaningful *within this one
    registry* (two different `OpaqueRegistry` instances never compare
    equal just because they both know about `None`).

    Uses `sympy.Dummy`, not `sympy.Symbol`, specifically because two
    independent registries must never collide: a plain `Symbol`
    compares equal purely by *name*, and two unrelated registries can
    easily reach the same internal counter value for their own second,
    third, ... registration, `Symbol('__opaque2__') ==
    Symbol('__opaque2__')` is `True` regardless of which registry
    produced either one, a real (if narrow) correctness risk found
    live while building this. `Dummy` compares by a hidden internal
    index instead of its display name, so two `Dummy`s are never equal
    just because they happen to share a name, exactly what "opaque
    value from *this* registry, not some other one" needs."""

    def __init__(self):
        self._by_value: dict = {}
        self._by_symbol: dict = {}
        self._next = 0
        self.none_symbol = self.register(None)

    def register(self, value) -> sympy.Dummy:
        if value in self._by_value:
            return self._by_value[value]
        self._next += 1
        sym = sympy.Dummy(f"__opaque{self._next}__")
        self._by_value[value] = sym
        self._by_symbol[sym] = value
        return sym

    def value_of(self, symbol: sympy.Dummy):
        """The real value a registered symbol stands for, or `None` if
        `symbol` was never registered through this instance, used to
        render a proof's sketch or a disproof's counterexample in terms
        of the actual value, not the symbol's own opaque name."""
        return self._by_symbol.get(symbol)

    def is_opaque_symbol(self, symbol) -> bool:
        """Was `symbol` produced by this registry? Equality/inequality
        (`==`/`!=`) are meaningful for an opaque value, two symbols
        are either the same registered value or provably different
        ones, both well-defined, but ordering (`<=`/`>=`) never is:
        a string or `None` has no inherent order. Callers use this to
        refuse an ordering claim outright the moment either side
        touches a registered opaque value, rather than letting the
        generic numeric sign-decidability machinery accidentally
        "prove" one via the degenerate same-value/same-symbol case
        (`x <= x` is trivially true by reflexivity even though
        ordering was never a meaningful thing to ask about `x` in the
        first place)."""
        return symbol in self._by_symbol
