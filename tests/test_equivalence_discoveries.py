# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Accepting a falsified `f =:= g` as a discovery. The whole claim
retires with both its lines: the claim's row and its computation row
`NAME[float]`. The computation row alone is never accepted, since the
computation is what runs. Where the mathematics line is falsified and
the computation holds, the correction offered is `f(x) ~= g(x)` at the
tolerance the computation used, adjudicated first and written only when
it holds or is proven."""
import os
import subprocess
import sys

import pytest
import yaml

from mathema.acceptance import (AcceptanceError, apply_acceptance,
                                plan_acceptance)
from mathema.spec import classify_verdict

FUNCS = '''import math


def keep(x: float) -> float:
    return math.sqrt(x)


def nudged(x: float) -> float:
    return math.sqrt(x) + 1e-12


def cancelling(x: float) -> float:
    return (x + 1e20) - 1e20


def identity(x: float) -> float:
    return x


def big_plus(x: float) -> float:
    return x + 1e-3
'''


def _env():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"]
                                if env.get("PYTHONPATH") else "")
    return env


def _run(root, script):
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=_env())


def _project(tmp_path, key, claims_yaml):
    (tmp_path / "funcs.py").write_text(FUNCS)
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / "claims.yaml").write_text(claims_yaml)
    name = key.split(".", 1)[1]
    r = _run(tmp_path, f"import sys\nsys.path.insert(0, {str(tmp_path)!r})\n"
                       f"import mathema, funcs\n"
                       f"mathema.write_spec(funcs.{name}, root={str(tmp_path)!r})")
    assert r.returncode == 0, r.stderr
    _run(tmp_path, "import sys; from mathema.cli import main; "
                   f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}, "
                   f"'--lenient']))")
    return _record(tmp_path, key)


def _verify_all(root):
    return _run(root, "import sys; from mathema.cli import main; "
                      f"sys.exit(main(['verify', '--root', {str(root)!r}, "
                      f"'--all']))")


def _record(root, key):
    with open(os.path.join(str(root), ".mathema", "verified",
                           f"{key}.yaml")) as fh:
        return (yaml.safe_load(fh) or {})[key]


def _row(entry, name, section="claims"):
    return next(c for c in entry.get(section) or [] if c.get("name") == name)


def test_a_mathematics_falsification_offers_the_approximate_claim(tmp_path):
    entry = _project(tmp_path, "funcs.keep", (
        "funcs.keep:\n  claims:\n    - name: same_root\n"
        "      statement: \"let g = funcs.nudged, for x in [0, 4], "
        "f =:= g\"\n"))
    assert _row(entry, "same_root")["verdict"] == "falsified"
    assert _row(entry, "same_root[float]")["verdict"] == "holds"
    plan = plan_acceptance(str(tmp_path), "funcs.keep", "same_root",
                           "discovery", by="lovelace")
    assert plan["corrected_statement"].startswith("let g = funcs.nudged, ")
    assert plan["corrected_statement"].endswith(", f(x) ~= g(x)")
    # the computation compared under the default allowance, 1e-9 absolute
    assert plan["corrected_tolerance"] == 1e-9
    assert classify_verdict(plan["corrected_verdict"]) in ("proven", "holds")
    apply_acceptance(plan)
    entry = _record(tmp_path, "funcs.keep")
    retired = {c["name"] for c in entry["discoveries"]}
    assert retired == {"same_root", "same_root[float]"}
    assert all(not c["name"].startswith("same_root[")
               for c in entry["claims"])
    corrected = _row(entry, "same_root_corrected")
    assert corrected["tolerance"] == 1e-9
    assert corrected["statement"] == plan["corrected_statement"]
    # both retired rows carry the acceptance, so the record verifies
    again = _verify_all(tmp_path)
    assert again.returncode == 0, again.stdout + again.stderr


def test_the_correction_carries_a_declared_tolerance(tmp_path):
    _project(tmp_path, "funcs.big_plus", (
        "funcs.big_plus:\n  claims:\n    - name: shifted\n"
        "      statement: \"let g = funcs.identity, for x in [1e7, 1e8], "
        "f =:= g\"\n      tolerance: 1e-2\n"))
    plan = plan_acceptance(str(tmp_path), "funcs.big_plus", "shifted",
                           "discovery")
    assert plan["corrected_tolerance"] == 1e-2
    assert classify_verdict(plan["corrected_verdict"]) in ("proven", "holds")


def test_a_tolerance_kind_offers_no_approximate_claim(tmp_path):
    _project(tmp_path, "funcs.big_plus", (
        "funcs.big_plus:\n  claims:\n    - name: shifted\n"
        "      statement: \"let g = funcs.identity, for x in [1e7, 1e8], "
        "f =:= g\"\n      tolerance: {rel: 1e-9}\n"))
    plan = plan_acceptance(str(tmp_path), "funcs.big_plus", "shifted",
                           "discovery")
    assert "corrected_statement" not in plan
    assert any("rel" in a and "~=" in a for a in plan["actions"]), \
        plan["actions"]


def test_the_computation_line_alone_is_never_accepted(tmp_path):
    entry = _project(tmp_path, "funcs.cancelling", (
        "funcs.cancelling:\n  claims:\n    - name: same\n"
        "      statement: \"let g = funcs.identity, for x in [0, 1], "
        "f =:= g\"\n"))
    assert _row(entry, "same")["verdict"] == "proven"
    assert _row(entry, "same[float]")["verdict"] == "falsified"
    with pytest.raises(AcceptanceError, match="computation is what runs"):
        plan_acceptance(str(tmp_path), "funcs.cancelling", "same[float]",
                        "discovery")


def test_the_whole_claim_retires_with_both_lines(tmp_path):
    _project(tmp_path, "funcs.cancelling", (
        "funcs.cancelling:\n  claims:\n    - name: same\n"
        "      statement: \"let g = funcs.identity, for x in [0, 1], "
        "f =:= g\"\n"))
    plan = plan_acceptance(str(tmp_path), "funcs.cancelling", "same",
                           "discovery")
    # the computation falsifies, so no approximate claim at its tolerance
    # can hold: the replacement is the author's to state
    assert "corrected_statement" not in plan
    assert plan["witness"]
    apply_acceptance(plan)
    entry = _record(tmp_path, "funcs.cancelling")
    by_name = {c["name"]: c for c in entry["discoveries"]}
    assert set(by_name) == {"same", "same[float]"}
    assert by_name["same"]["verdict"] == "proven"
    assert by_name["same[float]"]["verdict"] == "falsified"
    assert all(not c["name"].startswith("same") for c in entry["claims"])
    again = _verify_all(tmp_path)
    assert "FAIL funcs.cancelling" not in again.stdout, again.stdout


def test_a_proven_equivalence_whose_computation_holds_needs_no_acceptance(
        tmp_path):
    _project(tmp_path, "funcs.identity", (
        "funcs.identity:\n  claims:\n    - name: same\n"
        "      statement: \"let g = funcs.identity, for x in [0, 1], "
        "f =:= g\"\n"))
    with pytest.raises(AcceptanceError, match="proof is its own acceptance"):
        plan_acceptance(str(tmp_path), "funcs.identity", "same", "discovery")
