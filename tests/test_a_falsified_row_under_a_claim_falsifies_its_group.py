# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One written claim is a group of rows: the mathematics row over the
domain with a named missing value left out, and the policy row that
judges that value, a default row or one the author stated. A falsified
row in the group falsifies the claim in its headline and in the
counts, and every row a note names is a row of the record."""
import re
from typing import Optional

import pytest

import mathema
from mathema.conjecture import claim
from mathema.verify import gate


def type_error_at_none(x: Optional[float]) -> float:
    return x * 1.0  # type: ignore[operator]


STATED = "absent(f, x) raises(ValueError)"


def _record(text, *more):
    claims = [claim(text, name="c")] + [claim(t, name=f"c{i + 1}")
                                       for i, t in enumerate(more)]
    return mathema.check(type_error_at_none, claims=claims)


def _headline(rec, name="c"):
    return next(line for line in str(rec).splitlines()
                if line.startswith(f"  {name}  "))


@pytest.mark.parametrize("domain", ["{0.5, None}", "[0, 1] | {None}"])
def test_a_falsified_stated_row_falsifies_the_claim_headline(domain):
    rec = _record(f"for x in {domain}, f(x) >= 0", STATED)
    rows = {p.name: p for p in rec.probes}
    assert rows["c1"].verdict == "falsified", rows["c1"].note
    assert "falsified" in _headline(rec), _headline(rec)


@pytest.mark.parametrize("more", [(), (STATED,)])
def test_every_row_a_note_names_exists(more):
    rec = _record("for x in {0.5, None}, f(x) >= 0", *more)
    rows = {p.name: p for p in rec.probes}
    for row in rows.values():
        for named in re.findall(r"policy row ([\w\[\]]+)", row.note or ""):
            assert named in rows, (named, row.note, sorted(rows))
        for entry in (row.meta or {}).get("mathema.claim_group") or []:
            assert entry["row"] in rows, (entry, sorted(rows))


@pytest.mark.parametrize("more", [(), (STATED,)])
def test_the_counts_read_the_group_as_falsified(more):
    rec = _record("for x in {0.5, None}, f(x) >= 0", *more)
    report = gate(rec.probes, strict=False)
    c = next(p for p in rec.probes if p.name == "c")
    assert c.verdict == "proven", c.verdict
    falsified_rows = sum(1 for p in rec.probes if p.verdict == "falsified")
    assert report.falsified == falsified_rows + 1, (report.falsified, report.proven)
