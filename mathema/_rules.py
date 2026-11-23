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
2      the raise reading: a `raises` claim is proven only where the
       path to the raise, the building of the exception, the wrappers
       around the function and the arguments of the claim's call are
       each read as unable to do anything else
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
