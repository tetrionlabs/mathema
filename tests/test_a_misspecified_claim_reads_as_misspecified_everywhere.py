# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that cannot be adjudicated as stated reads `skipped:misspecified`
in the record, and the same word on the printed record, on the `verify` line
and in its count. A record whose value claims are all misspecified carries no
policy rows: their floors would be drawn over a domain that has no points."""
import subprocess
from typing import Annotated

import pytest

import mathema
from mathema.cli import _format_check
from mathema.types import Shape
from mathema.verify import gate, summary_counts
from tests.test_cli_verify import _run


def two(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("n")]) -> float:
    return sum(a) + sum(b)


def square(A: Annotated[list, Shape("n", "n")]) -> float:
    return sum(sum(r) for r in A)


def aliased(a: Annotated[list, Shape("n")], b: Annotated[list, Shape("k")],
            c: Annotated[list, Shape("k")]) -> float:
    return sum(a) + sum(b) + sum(c)


def plain(x: float) -> float:
    return x + 1.0


TWO_SIZES = "for a in [0, 1]^2, b in [0, 1]^3, f(a, b) == f(a, b)"


def _policy_rows(rec) -> list:
    return [p.name for p in rec.probes if (p.meta or {}).get("mathema.policy")]


@pytest.mark.parametrize("fn,text", [
    (two, TWO_SIZES),
    (square, "for A in [0, 1]^(2,3), f(A) >= 0"),
    (aliased, "for a in [0, 1]^2, b in [0, 1]^3, c in [0, 1]^n, f(a, b, c) >= 0"),
    (plain, "for x in [0, 1], f(x) >= not_a_name"),
])
def test_a_misspecified_claim_carries_no_policy_rows(fn, text):
    rec = mathema.check(fn, claims=[text])
    assert [p.verdict for p in rec.probes] == ["skipped:misspecified"], [
        (p.name, p.verdict) for p in rec.probes]
    assert _policy_rows(rec) == []


def test_a_valid_claim_beside_a_misspecified_one_keeps_the_policy_rows():
    rec = mathema.check(two, claims=[TWO_SIZES, "for a in [0, 1]^2, b in [0, 1]^2, f(a, b) >= 0"])
    assert "skipped:misspecified" in [p.verdict for p in rec.probes]
    assert _policy_rows(rec)


def test_a_valid_claim_alone_keeps_the_policy_rows():
    rec = mathema.check(two, claims=["for a in [0, 1]^2, b in [0, 1]^2, f(a, b) >= 0"])
    assert _policy_rows(rec)


def test_a_stated_policy_row_stays_beside_a_misspecified_claim():
    rec = mathema.check(two, claims=[TWO_SIZES, "missing(f, a) raises"])
    assert "skipped:misspecified" in [p.verdict for p in rec.probes]
    sources = [(p.meta or {}).get("mathema.policy", {}).get("source") for p in rec.probes
               if (p.meta or {}).get("mathema.policy")]
    assert sources == ["stated"], sources


def test_the_printed_record_says_misspecified():
    text = repr(mathema.check(two, claims=[TWO_SIZES]))
    assert "misspecified" in text, text
    assert "is fixed to two sizes" in text, text
    assert "unknown" not in text, text
    assert "falsified" not in text, text


def test_the_gate_names_and_counts_a_misspecified_claim():
    rec = mathema.check(two, claims=[TWO_SIZES])
    report = gate(rec.probes, strict=True, accepted_risk=set(), unresolved=[], key="two")
    assert report.skipped == 1
    assert report.misspecified == 1
    assert report.unknown == 0
    line = "; ".join(report.problems)
    assert "misspecified: n is fixed to two sizes" in line, line
    assert "unknown" not in line, line
    assert summary_counts(report) == "0 proven, 0 holds, 0 falsified, 1 misspecified"


def test_a_lenient_gate_still_passes_a_misspecified_claim():
    rec = mathema.check(two, claims=[TWO_SIZES])
    report = gate(rec.probes, strict=False, accepted_risk=set(), unresolved=[], key="two")
    assert report.problems == []
    assert report.misspecified == 1


def test_a_claim_skipped_for_another_reason_still_counts_unknown():
    report = gate([mathema.records.Probe("c", "s", "skipped", note="no evaluable inputs")],
                  strict=True, accepted_risk=set(), unresolved=[], key="k")
    assert report.misspecified == 0
    assert "c unknown: no evaluable inputs" in "; ".join(report.problems)
    assert summary_counts(report) == "0 proven, 0 holds, 0 falsified, 1 unknown"


def test_a_count_splits_misspecified_from_the_other_skipped():
    counts = {"proven": 0, "holds": 0, "falsified": 0, "unknown": 1, "skipped": 3,
              "misspecified": 2, "accepted_risk": 0}
    assert summary_counts(counts) == "0 proven, 0 holds, 0 falsified, 2 unknown, 2 misspecified"


def _row(**kw) -> dict:
    return {"name": "m.f", "tier": "source", "effects": None, "proven": 0, "holds": 0,
            "refuted": 0, "falsified": 0, "invalidated": 0, "unknown": 0, "skipped": 0,
            "misspecified": 0, "accepted_risk": 0, "coverage": "0/1", "problems": [], **kw}


def test_the_check_table_splits_misspecified_from_unknown():
    table = _format_check([_row(unknown=1, skipped=3, misspecified=2)], "md")
    header, _rule, row, *_rest = table.splitlines()
    cells = [c.strip() for c in row.split("|")]
    names = [c.strip() for c in header.split("|")]
    assert cells[names.index("unknown")] == "2", table
    assert cells[names.index("misspecified")] == "2", table


_FUNCS = ("from typing import Annotated\n"
          "from mathema.types import Shape\n\n\n"
          "def two(a: Annotated[list, Shape('n')], b: Annotated[list, Shape('n')]) -> float:\n"
          "    return sum(a) + sum(b)\n")
_CLAIMS = """funcs.two:
  claims:
    - name: conflict
      statement: "for a in [0, 1]^2, b in [0, 1]^3, f(a, b) == f(a, b)"
"""


def test_verify_prints_a_misspecified_claim_as_misspecified(tmp_path):
    (tmp_path / "funcs.py").write_text(_FUNCS)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "demo.claims.yaml").write_text(_CLAIMS)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    run = _run(tmp_path)
    assert run.returncode == 1, run.stdout + run.stderr
    stored = (tmp_path / ".mathema" / "verified" / "funcs.two.yaml").read_text()
    assert 'verdict: "skipped:misspecified"' in stored, stored
    (row,) = [ln for ln in run.stdout.splitlines() if " funcs.two:" in ln[:60]]
    assert "1 misspecified" in row, run.stdout
    assert "conflict misspecified: n is fixed to two sizes" in run.stdout, run.stdout
    assert "conflict unknown" not in run.stdout, run.stdout
    assert " unknown" not in row, row
    assert "policy" not in run.stdout, run.stdout
