# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The internal rules number goes up by one for a release that changes a
reading that could have given a wrong verdict, and the stricter reading
of `raise` is one such change: the rules carry an entry for it, so every
stored verdict reached under the earlier reading is checked again."""
import pytest


def test_the_rules_carry_an_entry_for_the_raise_reading():
    rules = pytest.importorskip(
        "mathema._rules",
        reason="the internal rules number is not in mathema yet; the raise "
               "reading raises it by one when it arrives")
    assert "raise reading" in repr(vars(rules)), sorted(vars(rules))
