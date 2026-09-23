# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where a function raises, declared so that claims about its CALLERS
can reason about it.

`register_raises_when(target, condition, exc_name)` states the region
in which `target` raises, written against its arguments as sympy
expressions. A claim about any function that CALLS `target` then
treats that region exactly as it would an explicit `raise` guard
written in the caller: a value claim quantifying over the region is
falsified with a witness, or the region is proven excluded and the
proof proceeds through it.

    import sympy, mathema.partiality

    def stable_kernel(u, tol):
        ...   # raises for u <= tol

    mathema.partiality.register_raises_when(
        stable_kernel, lambda u, tol: sympy.Le(u, tol), "ValueError")

This is a DECLARATION, not a result. mathema does not establish the
region and does not check it against the target's body; it takes the
statement on trust and reasons from it, the way a proof takes an
axiom. That is the whole point: the target is usually third-party or
builtin code whose body mathema cannot lift, and declaring its
partiality is what lets a caller's claim be adjudicated at all. A
wrong declaration produces a wrong verdict, so it is a statement to
make deliberately.

The `math` module's own partiality (sqrt, log, asin, ...) ships
registered out of the box, so an ordinary caller of those needs no
declaration.

Not to be confused with a LEMMA in the claim sense, which is a named
claim another claim rests on through an `assuming` premise (see
docs/lemmas.md). A lemma is established by adjudication; a partiality
declaration is asserted.
"""
from .symbolic._partiality import (   # noqa: F401
    qualified_name as qualified_name,
    register_raises_when as register_raises_when,
)
