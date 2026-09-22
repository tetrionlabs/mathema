# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Lemmas about functions, consumable during claim adjudication.

The first lemma kind is partiality: `register_raises_when(target,
condition, exc_name)` states the region where `target` raises, given
its lifted arguments as sympy expressions. Claims about any function
that CALLS the target then treat that region exactly like an explicit
raise guard; a value claim quantifying over it is falsified with a
witness, or the region is proven excluded and the proof proceeds.

    import sympy, mathema.lemmas

    def stable_kernel(u, tol):
        ...   # raises for u <= tol

    mathema.lemmas.register_raises_when(
        stable_kernel, lambda u, tol: sympy.Le(u, tol), "ValueError")

The math module's own partiality (sqrt, log, asin, ...) ships
registered out of the box.
"""
from .symbolic._partiality import (   # noqa: F401
    qualified_name as qualified_name,
    register_raises_when as register_raises_when,
)
