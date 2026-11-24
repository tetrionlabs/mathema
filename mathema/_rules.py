# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema's rules number: one integer, raised when a release fixes
something that could have given a wrong verdict, or changes how claim
text is stored. It is combined with the claims fingerprint in
the value a record stores for freshness (`spec.stored_claims_fingerprint`),
so a record written under an earlier value no longer matches its claims
and is checked again on the next sweep.

=====  ==========================================================
value  what it changed
=====  ==========================================================
0      the fingerprint before the rules number existed
1      canonical statement text: each string literal respelled from
       its value, and a negated relation in its parentheses
2      the missing argument reading: a call that passes `None` or
       nan as written is run at that value, or read exactly, never
       derived as a real number
2      the listed missing value reading: `is_defined` runs f at each
       missing value the domain lists
2      the negation reading: a negated claim is proven only from a
       disproof whose witness was run
2      the contained witness: the call that witnesses a negated
       safety claim is made in a child process
2      the empty input reading: `is_empty_safe` runs every empty
       input the parameter admits
2      the enforced domain reading: `excluded_outside_domain` is
       proven only for mathema's own wrapper, enforcing no more than
       the claim's domain
2      the claim side reading: a failure only the float evaluation
       of the claim's own side makes is no counterexample
2      the weakest row reading: a safety gate is no stronger than
       its weakest row
2      the unreachable code reading: a write is in unreachable code
       only under a constant test, or a test of one parameter that
       nothing binds again against numeric literals
2      the source reading of a write: where no call is run, a
       negated `is_state_safe` is proven from a statement the source
       shows changing state on every call that reaches it; a file
       opened for writing and an environment item assigned are not
       such statements
2      the shown change: a witness is a change shown by comparing
       what two values hold, described by type and size, never shown
2      the number reading: a parameter the claim binds to numbers is
       drawn and derived as a number, whatever marker its annotation
       carries
2      the named point reading: an infinite point the claim names,
       where the function's own guard refuses, falsifies a value
       claim
2      the let argument: a `let`-bound function passed as an
       argument is the function itself
=====  ==========================================================

A release raises the number once. Each fix in that release that could
change a verdict adds its own entry under the release's value.
"""
from __future__ import annotations

RULES = 2


def rules_in_force() -> int:
    """Intent:
        The rules number a fingerprint is made under now: `RULES`, or 0
        while an earlier release's rendering of claim text is
        reproduced (`_scan.uses_legacy_rendering`), so a record written
        that way is the record such a release left.
    """
    from ._scan import uses_legacy_rendering
    return 0 if uses_legacy_rendering() else RULES
