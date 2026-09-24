# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The one-line summaries `mathema check` and `mathema verify` print
name every count by the verdict it counts: `proven`, `holds`,
`falsified`, `invalidated`, `unknown`, `skipped`, never a word from a
different vocabulary (`hold`, `refuted`, `unverifiable`)."""
import re

from mathema.cli import _format_check
from mathema.records import Probe
from mathema.verify import gate, summary_counts

_FOREIGN = re.compile(r"\b(hold|refuted|unverifiable)\b")


def _row(**counts):
    base = {"name": "m.f", "tier": 1, "proven": 0, "holds": 0,
            "falsified": 0, "invalidated": 0, "unknown": 0, "skipped": 0,
            "accepted_risk": 0, "coverage": "1/1", "problems": []}
    base.update(counts)
    return base


def test_a_proven_claim_is_summarised_in_verdict_words():
    line = _format_check([_row(proven=1)], "text")
    assert "(1 proven, 0 holds, 0 falsified)" in line
    assert not _FOREIGN.search(line)


def test_every_nonzero_state_is_named_by_its_verdict():
    line = _format_check([_row(holds=2, falsified=1, invalidated=1,
                               unknown=1, skipped=3, accepted_risk=1)],
                         "text")
    assert ("0 proven, 2 holds, 1 falsified, 1 invalidated, 1 unknown, "
            "3 skipped, 1 accepted risk") in line
    assert not _FOREIGN.search(line)


def test_the_markdown_table_uses_verdict_words():
    table = _format_check([_row(proven=1)], "md")
    header = table.splitlines()[0]
    assert "| holds |" in header and "| falsified |" in header
    assert not _FOREIGN.search(table)


def test_an_invalidated_claim_is_not_reported_as_falsified():
    report = gate([Probe("c", "f(x) >= 0", "invalidated")], strict=False)
    assert report.invalidated == 1 and report.falsified == 0
    assert report.problems == ["1 invalidated claim(s)"]


def test_strict_names_skipped_and_accepted_risk_separately():
    report = gate([Probe("a", "s", "skipped"), Probe("b", "s", "unknown")],
                  strict=True, accepted_risk=frozenset({"b"}))
    assert report.problems == ["1 skipped claim(s)",
                               "1 accepted-risk claim(s)"]


def test_verify_and_check_share_one_summary():
    report = gate([Probe("a", "s", "proven"), Probe("b", "s", "falsified")],
                  strict=False)
    assert summary_counts(report) == "1 proven, 0 holds, 1 falsified"
