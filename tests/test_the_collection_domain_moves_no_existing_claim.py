# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Reading a named collection as a domain moves no claim that names
none: thirty ordinary claims of varied shapes keep the verdict, route,
canonical text and fingerprint they had on the tree the collection
domain was built on, and every lexicon row keeps its canonical text and
fingerprint. The table in `tests/data/collection_base_against_head.json`
was written by `tests/_base_against_head_claims.py` run against that
tree; the lexicon rows' verdicts are pinned by `tests/test_lexicon.py`."""
import json
from pathlib import Path

import pytest

from tests import _base_against_head_claims as table

_BASE = json.loads((Path(__file__).parent / "data" /
                    "collection_base_against_head.json").read_text())


def test_the_table_states_thirty_claims_and_every_lexicon_row():
    from mathema.lexicon import LEXICON
    assert len(_BASE["claims"]) == len(table.CLAIMS) == 30
    assert [r["claim"] for r in _BASE["claims"]] == [text for _fn, text in table.CLAIMS]
    assert {r["key"] for r in _BASE["lexicon"]} == set(LEXICON)


@pytest.mark.needs_full_proof_budget
def test_every_ordinary_claim_keeps_its_verdict_route_text_and_fingerprint():
    moved = [(was, now) for was, now in zip(_BASE["claims"], table.rows()) if was != now]
    assert not moved, moved


def test_every_lexicon_row_keeps_its_canonical_text_and_fingerprint():
    moved = [(was, now) for was, now in zip(_BASE["lexicon"], table.lexicon_texts())
             if was != now]
    assert not moved, moved
