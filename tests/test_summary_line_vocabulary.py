# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The one-line summaries `mathema check` and `mathema verify` print
name every count by the verdict it counts: `proven`, `holds`,
`falsified`, `unknown`, `skipped`, never a word from a different
vocabulary (`hold`, `refuted`, `unverifiable`). `invalidated` names a
function that changed since its record, never a claim count."""
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
    # a claim mathema could not run reads unknown: 1 + 3; the function
    # flag `invalidated` is not a claim count
    assert ("0 proven, 2 holds, 1 falsified, 4 unknown, "
            "1 accepted risk") in line
    assert "invalidated" not in line
    assert not _FOREIGN.search(line)


def test_the_markdown_table_uses_verdict_words():
    table = _format_check([_row(proven=1)], "md")
    header = table.splitlines()[0]
    assert "| holds |" in header and "| falsified |" in header
    assert not _FOREIGN.search(table)


def test_a_regression_an_old_record_stored_as_invalidated_reads_as_what_it_fell_to():
    # a record written before 0.6.5 stored a regression as the verdict
    # `invalidated`; it reads as the verdict it fell to, the move open
    report = gate([Probe("c", "f(x) >= 0", "invalidated",
                         meta={"mathema.previous_verdict": "proven",
                               "mathema.regressed_to": "falsified"})],
                  strict=False)
    assert report.falsified == 1 and report.invalidated == 0
    assert report.transitions == 1
    assert report.problems == [
        "c regressed proven to falsified (recorded before 0.6.5); to "
        "acknowledge it, run: mathema accept KEY c --transition",
        "1 falsified claim(s)"]


def test_strict_names_skipped_and_accepted_risk_separately():
    report = gate([Probe("a", "s", "skipped"), Probe("b", "s", "unknown")],
                  strict=True, accepted_risk=frozenset({"b"}))
    assert report.problems == ["a unknown", "1 accepted-risk claim(s)"]


def test_verify_and_check_share_one_summary():
    report = gate([Probe("a", "s", "proven"), Probe("b", "s", "falsified")],
                  strict=False)
    assert summary_counts(report) == "1 proven, 0 holds, 1 falsified"
