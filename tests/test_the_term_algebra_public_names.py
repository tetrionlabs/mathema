# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The public calls of `mathema.regular`'s term algebra and what each
answers: `contains` (whether a text is in a definition's language, or in
a bare node's), `matcher` (the same, prepared for many texts),
`validate`, `atoms`, `shortest_member` and `find_member`. The node-level
readers, the default budget and the z3 lowering are private."""
from mathema import regular

FULL = [[0, 0x10FFFF]]
LETTERS = {"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 122]]}, "min": 1,
           "max": None}
DOCUMENT = {"kind": "regular_language", "version": 1, "alphabet": FULL, "exact": True,
            "language": LETTERS}


def test_contains_reads_a_definition_and_a_bare_node():
    assert regular.contains(DOCUMENT, "abc") and not regular.contains(DOCUMENT, "a1")
    assert regular.contains(LETTERS, "abc") and not regular.contains(LETTERS, "")


def test_matcher_keeps_its_name_and_reads_both():
    assert regular.matcher(DOCUMENT)("ab") and regular.matcher(LETTERS)("ab")


def test_the_public_calls_are_these():
    for name in ("validate", "contains", "matcher", "atoms", "shortest_member",
                 "find_member"):
        assert name in regular.__all__ and callable(getattr(regular, name)), name


def test_the_earlier_draft_names_are_gone():
    for name in ("member", "node_member", "node_matcher", "MATCH_BUDGET", "Lowering"):
        assert not hasattr(regular, name), name
        assert name not in regular.__all__, name
