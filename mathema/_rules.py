# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema's reasoning version: one integer, raised when a release fixes
something that could have given a wrong verdict, or changes how claim
text is stored. It is combined with the claims fingerprint in
the value a record stores for freshness (`spec.stored_claims_fingerprint`),
so a record written under an earlier value no longer matches its claims
and is checked again on the next sweep.

=====  ==========================================================
value  what it changed
=====  ==========================================================
0      the fingerprint before the reasoning version existed
1      canonical statement text: each string literal respelled from
       its value, and a negated relation in its parentheses
2      the named missing value reading: a None or nan the claim
       names, in any spelling, is judged at that point; where the
       function returns None or nan there its return annotation
       judges it, and a listed value is run at every value of the
       other parameters
2      the canonical text reading: a missing value named beside an
       interval or a named type stays in the canonical text
=====  ==========================================================

A release raises the number once. Each fix in that release that could
change a verdict adds its own entry under the release's value.
"""
from __future__ import annotations

# :draft the wording of the two value-2 rows of the table above
REASONING_VERSION = 2
RULES = REASONING_VERSION  # :draft alias, kept for one release: the old name of REASONING_VERSION


def reasoning_version_in_force() -> int:
    """Intent:
        The reasoning version a fingerprint is made under now: `REASONING_VERSION`, or 0
        while an earlier release's rendering of claim text is
        reproduced (`_scan.uses_legacy_rendering`), so a record written
        that way is the record such a release left.
    """
    from ._scan import uses_legacy_rendering
    return 0 if uses_legacy_rendering() else REASONING_VERSION


rules_in_force = reasoning_version_in_force  # :draft alias, kept for one release: the old name of reasoning_version_in_force
