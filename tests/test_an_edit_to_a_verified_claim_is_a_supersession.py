# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An edit to a verified claim is a supersession, escapes or not.

A verified row is the record: an authored claim that states something
else (another relation, another side, another literal) is a
supersession, adopted only by `mathema accept <key> <claim> --as
superseded`. The release-move routes, which re-record a claim whose
stored text an earlier release wrote, apply only when the row was
written by an earlier release and records the authored claim as that
release wrote it. A row this release wrote, or an authored claim that
differs in anything but how an earlier release spelled or read it, is
a supersession.
"""
import pytest

from mathema.conjecture import claim
from mathema.spec import canonical_claim_text, recorded_claims_fingerprint
from mathema.sync import claim_conflicts


def measure(s: str, body: str = "", t: str = "") -> int:
    """The length of `t`."""
    return len(t)


#: the lineage of a record this release writes; its claims fingerprint
#: is made under the rules in force
_NOW = {"generated_by": "mathema"}


def _kinds(authored: str, row: dict, lineage: "dict | None" = None) -> list:
    """The conflict kinds of an authored claim against a verified row,
    in a record with `lineage` (an earlier release's, stating no
    statement text rules, when None)."""
    entry = {"claims": [{"name": "c", "statement": authored}]}
    verified = {"claims": [{"name": "c", "verdict": "proven",
                            "route": "probe", **row}],
                "lineage": lineage or {"generated_by": "mathema 0.6.6.1"}}
    if lineage is _NOW:
        verified["identity"] = {
            "claims_fingerprint": recorded_claims_fingerprint(verified, measure)}
    return [(x["kind"], x.get("moved")) for x in claim_conflicts(measure, entry, verified)]


#: a row whose domain set holds `"\t"`, read as a backslash and a t:
#: the stored text is the text written, the recorded domain holds the
#: two characters
_OLD_ESCAPES_ROW = {"statement": 'for s in {"\\t"}, f(s) >= 0',
                    "domain": {"s": {"set": ["\\t"]}}}


@pytest.mark.parametrize("edited", [
    'for s in {"\\t"}, f(s) <= 0',
    'for s in {"\\t"}, f(s) = 7',
    'for s in {"\\t", "\\n"}, f(s) >= 0',
    'for s in {"\\t"}, f(s) >= 1',
])
def test_an_edit_to_a_claim_whose_domain_has_an_escape_is_a_supersession(edited):
    assert _kinds(edited, _OLD_ESCAPES_ROW) == [("supersession", None)]


def test_the_same_claim_with_an_escape_in_its_domain_is_unchanged():
    assert _kinds('for s in {"\\t"}, f(s) >= 0', _OLD_ESCAPES_ROW) == []


@pytest.mark.parametrize("written, edited", [
    ("f(s, '}\"\", \"s') = 1", "f(s, '}\"', 's') = 1"),
    ('f(s, "a") = 1', 'f(s, "b") = 1'),
    ('for s in {"a"}, f(s) >= 0', 'for s in {"a"}, f(s) <= 0'),
    ('f(s) == (not (s < 1 and s > 0))', 'f(s) == (not (s < 2 and s > 0))'),
])
def test_an_edit_to_a_claim_this_release_recorded_is_a_supersession(written, edited):
    row = {"statement": canonical_claim_text(claim(written))}
    assert _kinds(edited, row, _NOW) == [("supersession", None)]
