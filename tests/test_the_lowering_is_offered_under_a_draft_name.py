# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The lowering of a question's nodes to z3 over one symbol per atom is
offered as `regular.Lowering`, a draft name, and the earlier private
name stays the same object."""
from mathema import regular


def test_the_lowering_is_exported_under_its_draft_name():
    assert "Lowering" in regular.__all__
    assert regular.Lowering is regular._Lowering
