# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One declared claim that does not parse is reported on its own, with
the parser's message, while the function's other claims are adjudicated
as usual: by `mathema verify`, by `mathema check`, and by the MCP tools,
which return rows rather than raising over claim text."""
import json

import pytest

from mathema.cli import main
from mathema.interfaces.mcp import tools

_SOURCE = '''def discounted(price, pct):
    """Price after a discount of pct percent, pct in [0, 100]."""
    return price - price * pct / 100
'''
_CLAIMS = """onebadclaim.discounted:
  claims:
    - name: never_above_price
      statement: "for price in [0, 1000], pct in [0, 100], f(price, pct) <= price"
    - name: list_domain
      statement: "for pct in [[0, 10], [50]], f(100, pct) >= 0"
"""
_PARSER_SAYS = "isn't a recognized interval, discrete set, or named set"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "onebadclaim.py").write_text(_SOURCE)
    (tmp_path / "onebadclaim.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _the_bad_claim_line(text):
    lines = [ln for ln in text.splitlines()
             if ln.startswith("FAIL onebadclaim.discounted: claim "
                              "'list_domain'")]
    assert len(lines) == 1, text
    assert _PARSER_SAYS in lines[0]
    assert "onebadclaim.claims.yaml" in lines[0]
    return lines[0]


def test_verify_names_the_bad_claim_and_checks_the_other(project, capsys):
    rc = main(["verify", "--root", str(project)])
    out = capsys.readouterr().out
    assert rc == 2, out
    _the_bad_claim_line(out)
    record = (project / ".mathema" / "verified").glob("*.yaml")
    text = "".join(p.read_text() for p in record)
    assert "never_above_price" in text
    assert "list_domain" not in text


def test_check_prints_the_other_claims_and_names_the_bad_one(project, capsys):
    rc = main(["check", "onebadclaim.discounted", "--root", str(project)])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert rc == 2, captured.out + captured.err
    _the_bad_claim_line(captured.out)
    assert any(ln.startswith("FAIL onebadclaim.discounted: ")
               and "checked (" in ln for ln in captured.out.splitlines()), \
        captured.out


def test_check_json_adjudicates_the_other_claim(project, capsys):
    rc = main(["check", "onebadclaim.discounted", "--root", str(project),
               "--format", "compact"])
    out = capsys.readouterr().out
    assert rc == 2, out
    (fn,) = json.loads(out)
    rows = {r["claim"]: r for r in fn["claims"]}
    assert rows["never_above_price"]["stance"] == "supported"
    assert "list_domain" not in rows
    assert fn["passed"] is False
    assert any("'list_domain'" in p and _PARSER_SAYS in p
               for p in fn["problems"])


def test_the_mcp_tool_returns_rows_with_the_bad_claim_carrying_an_error(
        project):
    out = tools.adjudicate_target("onebadclaim.discounted",
                                  root=str(project))
    rows = {r["claim"]: r for r in out["claims"]}
    assert rows["never_above_price"]["stance"] == "supported"
    assert _PARSER_SAYS in rows["list_domain"]["error"]
    assert out["passed"] is False
    assert any("'list_domain'" in p for p in out["problems"])


def test_the_mcp_batch_tool_adjudicates_the_other_claim(project):
    out = tools.adjudicate_targets(["onebadclaim.discounted"],
                                   root=str(project))
    claims = [row[1] for row in out["rows"]]
    assert "never_above_price" in claims
    assert out["passed"] is False
    assert any("'list_domain'" in p and _PARSER_SAYS in p
               for p in out["problems"])


def test_the_audit_counts_the_function_as_claimed(project):
    out = tools.audit_targets(["onebadclaim"], root=str(project))
    (row,) = out["rows"]
    assert row[out["cols"].index("claims")] == 2


def test_claims_lists_both_declared_claims(project, capsys):
    rc = main(["claims", "onebadclaim.discounted", "--root", str(project)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "2 declared claim(s)" in out
    assert "list_domain" in out


def test_init_writes_no_stub_over_an_authored_claim(project, capsys):
    rc = main(["init", "onebadclaim", "--root", str(project)])
    capsys.readouterr()
    assert rc == 0
    assert not (project / "claims" / "onebadclaim.claims.yaml").exists()
