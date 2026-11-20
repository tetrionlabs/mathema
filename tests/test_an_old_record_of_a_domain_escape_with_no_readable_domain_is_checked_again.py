# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An earlier release's record of a domain escape is checked again.

Releases up to 0.6.6.1 read `{"\\t"}` in a domain set as a backslash
and a t; this release reads a tab. The stored text is the same bytes
under both readings: what tells the two apart is the rules number the
record's claims fingerprint was made under (`spec.written_under_earlier_rules`)
and the values its row's `domain` records. A row of an earlier release's record whose `domain`
is missing, or does not read, is checked again like one that records
the old values; it never keeps its verdict.
"""
import os
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema.spec import (recorded_claims_fingerprint, save_verified_entry,
                          written_under_earlier_rules)
from mathema.sync import claim_conflicts


def width(s: str) -> int:
    """The number of characters in s."""
    return len(s)


_STATEMENT = 'for s in {"\\t"}, f(s) == 1'


def _kinds(row_domain, lineage) -> list:
    entry = {"claims": [{"name": "c", "statement": _STATEMENT}]}
    row = {"name": "c", "verdict": "falsified", "route": "probe",
           "statement": 'for s in {"\\t"}, f(s) = 1'}
    if row_domain is not None:
        row["domain"] = row_domain
    verified = {"claims": [row], "lineage": lineage}
    if lineage is _NOW:
        verified["identity"] = {
            "claims_fingerprint": recorded_claims_fingerprint(verified, width)}
    return [(x["kind"], x.get("moved"))
            for x in claim_conflicts(width, entry, verified)]


_EARLIER = {"generated_by": "mathema 0.6.6.1"}
#: the lineage of a record this release writes; its claims fingerprint
#: is made under the rules in force
_NOW = {"generated_by": "mathema"}


@pytest.mark.parametrize("row_domain", [
    None,
    {"s": {"set": 5}},
    {"s": "not a domain {"},
    "not a mapping",
])
def test_a_row_with_no_readable_domain_is_a_release_move(row_domain):
    assert _kinds(row_domain, _EARLIER) == [("release-move", ("domain-escapes",))]


def test_a_row_this_release_wrote_is_not_moved():
    assert _kinds({"s": {"set": ["\t"]}}, _NOW) == []


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "wpkg.mod.width"

_MOD = '''
def width(s: str) -> int:
    """The number of characters in s."""
    return len(s)
'''

_CLAIMS = r"""
wpkg.mod.width:
  claims:
    - name: one_character
      statement: 'for s in {"\t"}, f(s) == 1'
"""


def _run(tmp_path, env, *args, old=False):
    setup = ("from mathema._scan import _LEGACY_DOMAIN_ESCAPES; "
             "_LEGACY_DOMAIN_ESCAPES.set(True); ") if old else ""
    return subprocess.run(
        [sys.executable, "-c",
         f"import sys; {setup}from mathema.cli import main; "
         f"sys.exit(main({list(args) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


def test_an_old_row_with_its_domain_removed_is_checked_again(tmp_path):
    pkg = tmp_path / "wpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "w.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    old = _run(tmp_path, env, "verify", old=True)
    record = tmp_path / ".mathema" / "verified" / f"{KEY}.yaml"
    entry = yaml.safe_load(record.read_text())[KEY]
    assert written_under_earlier_rules(entry)
    rows = {r["name"]: r for r in entry["claims"]}
    assert rows["one_character"]["verdict"] == "falsified", old.stdout
    del rows["one_character"]["domain"]
    save_verified_entry(KEY, entry, root=str(tmp_path))
    run = _run(tmp_path, env, "verify")
    assert "backslash escape" in run.stdout, run.stdout
    entry = yaml.safe_load(record.read_text())[KEY]
    rows = {r["name"]: r for r in entry["claims"]}
    assert rows["one_character"]["verdict"] in ("proven", "holds"), rows
    assert not written_under_earlier_rules(entry)
