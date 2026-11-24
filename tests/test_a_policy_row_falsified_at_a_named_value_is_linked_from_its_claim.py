# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One written claim is a group of rows: the mathematics row, over the
printed domain with a named missing value left out, and the policy row
that judges that value. Where the function raises at the named value
and nothing covers it, the mathematics row stays proven over the
restated domain, its note points at the policy row, the policy row is
falsified, and the mathematics row carries a structured link to it."""
from typing import Optional

import pytest

import mathema
from mathema.conjecture import claim

TEXT = "for x in {1, None}, y in [0, 1], f(x, y) == 0"


def scaled(x: Optional[float], y: float) -> float:
    return (x - 1) * y  # type: ignore[operator]


@pytest.mark.needs_smt
@pytest.mark.needs_full_proof_budget
def test_an_uncovered_raise_links_the_claim_to_its_falsified_policy_row():
    rec = mathema.check(scaled, claims=[claim(TEXT, name="c")])
    rows = {p.name: p for p in rec.probes}
    main, policy = rows["c"], rows["absent[x]"]
    assert main.verdict == "proven", (main.verdict, main.note)
    assert main.statement.startswith("for x in {1}, "), main.statement
    assert "judged by the policy row absent[x]" in main.note, main.note
    assert policy.verdict == "falsified", policy.note
    assert main.meta["mathema.claim_group"] == [
        {"row": "absent[x]", "verdict": "falsified", "value": "x = None"}]


_SQUARE = '''
def square(x):
    return x * x
'''


@pytest.mark.parametrize("written", ["for x in {1, None}, f(x) >= 0",
                                     "for x in [0, 1] | {None}, f(x) >= 0"])
def test_a_record_of_a_restated_domain_holds_the_claim_as_written(
        tmp_path, monkeypatch, written):
    """The record's row prints the domain with None left out, and the
    record still holds the claim as written: the next run finds it
    fresh, with no re-authored claim and no rules change."""
    import subprocess
    import sys

    import yaml

    from mathema.verify import verify_project
    for name in [m for m in sys.modules if m == "lopkg" or m.startswith("lopkg.")]:
        sys.modules.pop(name, None)
    (tmp_path / "lopkg").mkdir()
    (tmp_path / "lopkg" / "__init__.py").write_text("")
    (tmp_path / "lopkg" / "mod.py").write_text(_SQUARE)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "s.claims.yaml").write_text(yaml.safe_dump(
        {"lopkg.mod.square": {"claims": [{"name": "c", "statement": written}]}}))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        first = verify_project(root=str(tmp_path))
        record = yaml.safe_load((tmp_path / ".mathema" / "verified"
                                 / "lopkg.mod.square.yaml").read_text())
        row = {r["name"]: r for r in record["lopkg.mod.square"]["claims"]}["c"]
        assert "None" not in row["statement"] and "absent" not in row["statement"], row
        assert [k["why"] for k in first.keys] == ["no baseline record"]
        again = verify_project(root=str(tmp_path))
        assert not any("re-authored" in p for p in again.problems), again.problems
        assert [k["why"] for k in again.keys] == ["fresh"], again.keys
    finally:
        for name in [m for m in sys.modules if m == "lopkg" or m.startswith("lopkg.")]:
            sys.modules.pop(name, None)
