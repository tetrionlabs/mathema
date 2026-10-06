# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A trusted acceptance is tied to the row as written.

`mathema accept KEY ROW --as trusted` stores the row's `statement:`
exactly as the claims file writes it, and the file's `versions:`
range. When `mathema verify` carries the acceptance forward, a changed
statement makes it stale, and so does a wider versions range; a
narrower range, or an edit to the row's note, keeps it. A stale row is
evidence, so a proof through it is capped at `holds` and its sketch
names the command that re-accepts it. An acceptance recorded before
the statement was stored is stale on its first carry, and is accepted
again once.
"""
from __future__ import annotations
import pytest

pytest.importorskip("pandas")

import textwrap  # noqa: E402

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from mathema import compendium  # noqa: E402
from mathema.acceptance import carry_acceptance  # noqa: E402
from mathema.claims import check_conjectures, claim  # noqa: E402

_KEY = "pandas.Series.multiply"
_STATEMENT = ("for a in R^n \\ {∅}, other in [-1e6, 1e6], "
              "f(a, other) == a * other")


def _rows_file(statement=_STATEMENT, versions=">=2", note="the product"):
    return textwrap.dedent(f"""\
        compendium: pandas
        versions: "{versions}"

        {_KEY}:
          claims:
            - name: definition
              statement: "{statement.replace(chr(92), chr(92) * 2)}"
              note: "{note}"
        """)


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "claims").mkdir()
    (tmp_path / ".mathema" / "verified").mkdir(parents=True)
    yield tmp_path
    compendium.uninstall()


def _record(project, accepted):
    path = project / ".mathema" / "verified" / f"{_KEY}.yaml"
    path.write_text(yaml.safe_dump({_KEY: {"claims": [
        {"name": "definition", "statement": _STATEMENT, "verdict": "holds",
         "accepted": accepted, "acceptance_history": []}]}}))
    return path


def _accepted(**extra):
    return {"as": "trusted", "at": "2026-10-05", "level": "holds",
            "statement": _STATEMENT, "versions": ">=2", **extra}


def _carry(project, path):
    compendium.uninstall()
    spec = {"identity": {"form": None}, "claims": [
        {"name": "definition", "statement": _STATEMENT, "verdict": "unknown"}]}
    carry_acceptance(spec, _KEY, str(path))
    (row,) = spec["claims"]
    return row


def test_an_edited_statement_makes_the_acceptance_stale(project):
    path = _record(project, _accepted())
    (project / "claims" / "pandas.claims.yaml").write_text(_rows_file(
        statement=_STATEMENT.replace("[-1e6, 1e6]", "[-1e7, 1e7]")))
    row = _carry(project, path)
    assert row["accepted"].get("stale") is True, row
    assert "statement" in row["acceptance_history"][-1]["reason"]


def test_an_edited_note_keeps_the_acceptance(project):
    path = _record(project, _accepted())
    (project / "claims" / "pandas.claims.yaml").write_text(
        _rows_file(note="the elementwise product"))
    row = _carry(project, path)
    assert not row["accepted"].get("stale"), row


def test_a_wider_versions_range_makes_the_acceptance_stale(project):
    path = _record(project, _accepted(versions=">=2.2,<3"))
    (project / "claims" / "pandas.claims.yaml").write_text(
        _rows_file(versions=">=2"))
    row = _carry(project, path)
    assert row["accepted"].get("stale") is True, row
    assert "versions" in row["acceptance_history"][-1]["reason"]


def test_a_narrower_versions_range_keeps_the_acceptance(project):
    path = _record(project, _accepted(versions=">=2"))
    (project / "claims" / "pandas.claims.yaml").write_text(
        _rows_file(versions=">=2.2,<4"))
    row = _carry(project, path)
    assert not row["accepted"].get("stale"), row


def test_an_acceptance_without_a_stored_statement_is_stale_once(project):
    legacy = _accepted()
    del legacy["statement"], legacy["versions"]
    path = _record(project, legacy)
    (project / "claims" / "pandas.claims.yaml").write_text(_rows_file())
    row = _carry(project, path)
    assert row["accepted"].get("stale") is True, row
    assert "mathema accept pandas.Series.multiply definition --as trusted" \
        in row["acceptance_history"][-1]["reason"]


def doubled_mean(x: pd.Series) -> float:
    """Twice the mean, through Series.multiply."""
    return x.multiply(2.0).mean()


@pytest.mark.needs_full_proof_budget
def test_a_proof_through_a_row_respelled_after_acceptance_holds(project):
    _record(project, _accepted())
    (project / "claims" / "pandas.claims.yaml").write_text(_rows_file(
        statement=_STATEMENT.replace("a * other", "a*other")))
    compendium.uninstall()
    compendium.install(str(project))
    try:
        (p,) = check_conjectures(doubled_mean, [claim(
            "let s = mathema.f.scale_seq, let c be [0.1, 10], "
            "for x in [-1, 1]^n, f(s(x, c)) ~= c * f(x)", route="derive")])
    finally:
        compendium.uninstall()
    assert p.verdict == "holds", (p.verdict, p.sketch, p.note)
    assert "mathema accept pandas.Series.multiply definition --as trusted" \
        in (p.sketch or "") + (p.note or ""), (p.sketch, p.note)
