# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `not` over a relation keeps its parentheses in the stored text.

A side that is the negation of a comparison or of a boolean connective
is a truth value inside the claim, and the claim grammar reads it only
in parentheses: `f(x) = not (a < x and x < b)` splits at the inner
relations and does not read, `f(x) = (not (a < x and x < b))` reads as
the claim. The stored text keeps the parentheses, so it reads back. A
record an earlier release wrote without them is the record of the same
claim: the next run checks the claim as written and re-records it.
"""
import os
import subprocess
import sys
import textwrap

import pytest
import yaml

from mathema.conjecture import claim
from mathema.spec import canonical_claim_text

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("statement, stored", [
    ("f(x, lo, hi) == (not (lo < x and x < hi))",
     "f(x, lo, hi) = (not (lo < x and x < hi))"),
    ("f(x, lo) == (not (lo < x))", "f(x, lo) = (not lo < x)"),
    ("f(x, lo) == (not (not (lo < x)))", "f(x, lo) = (not not lo < x)"),
])
def test_a_negated_relation_is_stored_so_it_reads_back(statement, stored):
    text = canonical_claim_text(claim(statement))
    assert text == stored
    assert canonical_claim_text(claim(text)) == text


_MOD = '''
def outside(x: float, lo: float, hi: float) -> bool:
    """Whether x lies outside the open band (lo, hi)."""
    return not (lo < x and x < hi)
'''

_CLAIMS = """
npkg.mod.outside:
  claims:
    - name: outside_band
      statement: "for x in [0,10], lo in [0,3], hi in [7,10], f(x, lo, hi) == (not (lo < x and x < hi))"
"""
KEY = "npkg.mod.outside"


def _run(tmp_path, env, *args, old=False):
    setup = ("from mathema._scan import _LEGACY_NOT_PARENTHESES; "
             "_LEGACY_NOT_PARENTHESES.set(True); ") if old else ""
    return subprocess.run(
        [sys.executable, "-c",
         f"import sys; {setup}from mathema.cli import main; "
         f"sys.exit(main({list(args) + ['--root', str(tmp_path)]!r}))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)


@pytest.mark.needs_full_proof_budget
def test_a_record_written_without_the_parentheses_is_checked_again(tmp_path):
    pkg = tmp_path / "npkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_MOD))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "n.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    old = _run(tmp_path, env, "verify", old=True)
    record = tmp_path / ".mathema" / "verified" / f"{KEY}.yaml"
    rows = {r.get("name"): r for r in yaml.safe_load(record.read_text())[KEY]["claims"]}
    assert rows["outside_band"]["statement"].endswith("= not (lo < x and x < hi)"), \
        old.stdout + old.stderr
    run = _run(tmp_path, env, "verify")
    assert "Traceback" not in run.stderr, run.stderr
    assert "re-authored" not in run.stdout and "could not be read" not in run.stdout, run.stdout
    assert "negated relation" in run.stdout, run.stdout
    rows = {r.get("name"): r for r in yaml.safe_load(record.read_text())[KEY]["claims"]}
    assert rows["outside_band"]["statement"].endswith("= (not (lo < x and x < hi))")
    assert rows["outside_band"]["verdict"] in ("proven", "holds"), rows["outside_band"]
