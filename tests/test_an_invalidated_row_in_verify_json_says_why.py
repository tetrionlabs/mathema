# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`verify --format json` gives an invalidated claim's reason,
evidence and counterexample.

A claim the record held as proven, which a code edit broke, is
invalidated. Its record says why: the note or the derivation sketch,
the verdict it had and the one it fell to, and the counterexample. The
JSON row is what a pipeline reads instead of the record, so it carries
the same explanation, on the run that finds the regression and on
every later run that reads it back from the record."""
import json
import os
import subprocess
import sys
import textwrap

import yaml

from mathema.records import claim_row

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_BEFORE = '''
def double(x: float) -> float:
    """Doubles."""
    return 2.0 * x
'''

_AFTER = '''
def double(x: float) -> float:
    """Doubles."""
    return 2.0 * x + 1.0
'''

_CLAIMS = """
rpkg.mod.double:
  claims:
    - name: doubles
      statement: 'for x in [0,5], f(x) == 2*x'
"""


def _project(tmp_path):
    pkg = tmp_path / "rpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent(_BEFORE))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "r.claims.yaml").write_text(textwrap.dedent(_CLAIMS))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([REPO, str(tmp_path)]))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    return env


def _verify_json(tmp_path, env):
    run = subprocess.run(
        [sys.executable, "-c",
         "import sys; from mathema.cli import main; "
         f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}, "
         "'--format', 'json']))"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    return json.loads(run.stdout)


def _json_row(report, name):
    (key,) = [k for k in report["keys"] if k["key"] == "rpkg.mod.double"]
    (row,) = [c for c in key["claims"] if c["claim"] == name]
    return row


def _record_row(tmp_path, name):
    path = tmp_path / ".mathema" / "verified" / "rpkg.mod.double.yaml"
    entry = yaml.safe_load(path.read_text())["rpkg.mod.double"]
    (row,) = [c for c in entry["claims"] if c.get("name") == name]
    return row


def test_an_invalidated_row_carries_what_the_record_says(tmp_path):
    env = _project(tmp_path)
    assert _verify_json(tmp_path, env)["passed"]
    (tmp_path / "rpkg" / "mod.py").write_text(textwrap.dedent(_AFTER))
    for _ in range(2):
        row = _json_row(_verify_json(tmp_path, env), "doubles")
        stored = _record_row(tmp_path, "doubles")
        assert row["verdict"] == stored["verdict"] == "invalidated"
        assert row["reason"] == (stored.get("note") or stored["sketch"])
        assert row["evidence"]["previous_verdict"] == "proven"
        assert row["evidence"]["regressed_to"] == "falsified"
        assert row["evidence"]["sketch"] == stored["sketch"]
        assert row["counterexample"] == stored["counterexample"]


def test_an_invalidated_row_without_a_counterexample_gives_its_note():
    stored = {
        "name": "gaussian_calibration",
        "statement": "let rho be [0.01, 0.99] : float|missing, "
                     "f(-log(1 - rho^2)/2) = rho",
        "verdict": "invalidated",
        "note": "rho is a constant, and a constant has no hole; to admit "
                "its absence write `|absent`",
        "route": None,
        "meta": {"mathema.previous_verdict": "proven",
                 "mathema.regressed_to": "skipped:misspecified"},
    }
    row = claim_row(stored)
    assert row["reason"] == stored["note"]
    assert row["evidence"] == {"n": None, "previous_verdict": "proven",
                               "regressed_to": "skipped:misspecified"}
    assert row["counterexample"] is None
