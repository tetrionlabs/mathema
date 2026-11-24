# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The reasoning version is `_rules.REASONING_VERSION`; `RULES` and
`rules_in_force` read as the same objects, and the claims fingerprint
a record stores is the one made under that version."""
import hashlib

from mathema import _rules
from mathema.spec import claims_fingerprint, stored_claims_fingerprint

_CLAIMS = [{"name": "doubles", "statement": "for n in [0, 10] subset Z, f(n) == n + n"}]


def test_old_names_are_aliases():
    assert _rules.RULES == _rules.REASONING_VERSION == 2
    assert _rules.rules_in_force is _rules.reasoning_version_in_force
    assert _rules.reasoning_version_in_force() == _rules.REASONING_VERSION


def test_stored_fingerprint_is_unchanged_by_the_rename():
    pure = claims_fingerprint(_CLAIMS)
    expected = hashlib.sha256(f"{pure}|rules=2".encode()).hexdigest()[:12]
    assert stored_claims_fingerprint(_CLAIMS) == expected
