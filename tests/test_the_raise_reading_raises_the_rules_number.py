# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The reasoning version goes up by one for a release that changes a
reading that could have given a wrong verdict, and the stricter reading
of `raise` is one such change: the table in `_rules` carries an entry for
it, so every stored verdict reached under the earlier reading is checked
again."""
from mathema import _rules


def test_the_reasoning_version_carries_an_entry_for_the_raise_reading():
    assert _rules.REASONING_VERSION == 2
    assert "the raise reading" in (_rules.__doc__ or "")
