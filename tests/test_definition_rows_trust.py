# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Which definition rows a proof may rest on: trust by source.

A definition row bundled with mathema feeds the derive route at once
(this test suite verifies each against the installed library). A row
from a project's own claims file, or from a third party, feeds the
derive route only once `mathema verify` has recorded it `holds` or
`proven` here, or it was accepted `--as trusted`; until then it only
guides sampling, and a claim resting on it stays `holds`. A row verify
recorded `falsified` is never used, bundled or not. A record whose
proof could read through different rows now (a row verified,
falsified or added since) is stale, and verify re-adjudicates it.
"""
from __future__ import annotations

import sys
import textwrap

import pandas as pd
import pytest
import yaml

from mathema import compendium
from mathema.claims import check_conjectures, claim
from mathema.definitions import RowBook, row_standing

_SEM_ROW = """\
compendium: pandas
versions: ">=2"

pandas.Series.sem:
  claims:
    - name: definition
      statement: "for a in R^n \\\\ {∅}, assuming dim(a) >= 2, f(a) ~= std(a, ddof=1) / sqrt(len(a))"
"""

_LEVERAGE = ("for returns in [-0.1, 0.1]^n, let s = mathema.f.scale_seq, "
             "let c be [0.1, 10], assuming std(returns, ddof=1) > 1e-6, "
             "f(s(returns, c)) ~= f(returns)")


def sem_ratio(returns: pd.Series):
    return returns.mean() / returns.sem()


def sharpe(returns: pd.Series):
    return returns.mean() / returns.std()


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "claims").mkdir()
    yield tmp_path
    compendium.uninstall()


def _check(root, fn, law=_LEVERAGE):
    compendium.uninstall()
    compendium.install(str(root))
    try:
        (p,) = check_conjectures(fn, [claim(law)])
    finally:
        compendium.uninstall()
    return p


def _verify(root, *files):
    from mathema.verify import verify_project
    compendium.uninstall()
    try:
        return verify_project(str(root), files=[str(f) for f in files]
                              or None)
    finally:
        compendium.uninstall()


def test_a_project_row_feeds_derive_only_after_verify_records_it(project):
    rows = project / "claims" / "pandas.claims.yaml"
    rows.write_text(_SEM_ROW)
    p = _check(project, sem_ratio)
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "pandas.Series.sem has no definition row usable here" in p.note
    assert "feeds sampling only" in p.note, p.note
    _verify(project, rows)
    p = _check(project, sem_ratio)
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    used = {u["key"]: u for u in p.meta["mathema.definitions"]}
    assert used["pandas.Series.sem"]["status"] == "holds"
    assert used["pandas.Series.sem"]["source"] == "claims/pandas.claims.yaml"
    assert used["pandas.Series.mean"]["status"] == "bundled"


def test_a_wrong_definition_row_is_falsified_by_verify_and_never_used(
        project):
    rows = project / "claims" / "pandas.claims.yaml"
    rows.write_text(textwrap.dedent("""\
        compendium: pandas
        versions: ">=2"
        pandas.Series.std:
          claims:
            - name: definition
              statement: "for a in R^n \\\\ {∅}, f(a) ~= std(a, ddof=0)"
        """))
    # the project's row shadows the bundled one: unverified, it is not used
    p = _check(project, sharpe)
    assert p.verdict != "proven", (p.verdict, p.sketch)
    _verify(project, rows)
    record = yaml.safe_load((project / ".mathema" / "verified"
                             / "pandas.Series.std.yaml").read_text())
    (row,) = [c for c in record["pandas.Series.std"]["claims"]
              if c["name"] == "definition"]
    assert row["verdict"] == "falsified"
    p = _check(project, sharpe)
    assert p.verdict != "proven", (p.verdict, p.sketch)
    assert "recorded it falsified" in p.note, p.note


def test_a_bundled_row_verify_falsified_here_is_not_used(project):
    statement = next(
        r["statement"] for r in RowBook(None)._library[
            "pandas.Series.mean"]["entry"]["claims"]
        if r["name"] == "definition")
    verified = project / ".mathema" / "verified"
    verified.mkdir(parents=True)
    (verified / "pandas.Series.mean.yaml").write_text(yaml.safe_dump({
        "pandas.Series.mean": {"claims": [
            {"name": "definition", "statement": statement,
             "verdict": "falsified"}]}}))
    assert row_standing(str(project), "pandas.Series.mean",
                        {"name": "definition", "statement": statement},
                        bundled=True)[0] is None
    p = _check(project, sharpe)
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_a_trusted_acceptance_lets_a_project_row_feed_derive(project):
    rows = project / "claims" / "pandas.claims.yaml"
    rows.write_text(_SEM_ROW)
    statement = yaml.safe_load(_SEM_ROW)["pandas.Series.sem"]["claims"][0][
        "statement"]
    verified = project / ".mathema" / "verified"
    verified.mkdir(parents=True)
    (verified / "pandas.Series.sem.yaml").write_text(yaml.safe_dump({
        "pandas.Series.sem": {"claims": [
            {"name": "definition", "statement": statement,
             "verdict": "holds", "accepted": {"as": "trusted"}}]}}))
    p = _check(project, sem_ratio)
    assert p.verdict == "proven", (p.verdict, p.note)
    used = {u["key"]: u for u in p.meta["mathema.definitions"]}
    assert used["pandas.Series.sem"]["status"] == "trusted"


def test_a_record_is_stale_when_its_definition_rows_change(project,
                                                          monkeypatch):
    package = project / "qpkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "quant.py").write_text(textwrap.dedent('''\
        import pandas as pd


        def sem_ratio(returns: pd.Series):
            """Mean return over its standard error."""
            return returns.mean() / returns.sem()
        '''))
    (project / "claims" / "quant.claims.yaml").write_text(yaml.safe_dump({
        "qpkg.quant.sem_ratio": {"claims": [
            {"name": "leverage_invariant", "statement": _LEVERAGE}]}}))
    monkeypatch.syspath_prepend(str(project))
    sys.modules.pop("qpkg", None)
    sys.modules.pop("qpkg.quant", None)

    def verdict():
        record = yaml.safe_load((project / ".mathema" / "verified"
                                 / "qpkg.quant.sem_ratio.yaml").read_text())
        return {c["name"]: c for c in
                record["qpkg.quant.sem_ratio"]["claims"]}[
            "leverage_invariant"]["verdict"]
    _verify(project)
    assert verdict() == "holds"
    (project / "claims" / "pandas.claims.yaml").write_text(_SEM_ROW)
    result = _verify(project)
    assert not result.problems, result.lines
    assert "ok   qpkg.quant.sem_ratio: definition rows changed" in \
        "\n".join(result.lines), result.lines
    assert verdict() == "proven"
    result = _verify(project)
    assert "ok   qpkg.quant.sem_ratio: fresh" in "\n".join(result.lines), \
        result.lines
