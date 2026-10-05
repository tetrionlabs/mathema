# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An acceptance of risk is a sign-off on one form of a function. Once
the body changes, the first `verify` after the change marks the
acceptance stale and fails on the claim it covered, under `--lenient`
too, rather than counting it as accepted risk once more."""
import os
import subprocess
import sys

import yaml

from mathema.acceptance import apply_acceptance, plan_acceptance


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = _repo_root() + (os.pathsep + env["PYTHONPATH"]
                                        if env.get("PYTHONPATH") else "")
    env.pop("VIRTUAL_ENV", None)
    return env


def _verify(root):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main(['verify', '--root', {str(root)!r}, "
              "'--lenient']))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=_env())


# the examine route cannot follow a function looked up by name at run
# time, so whether the function is deterministic is genuinely unknown
_BODY = ("import math\n\n\n"
         "def keep(x: float) -> float:\n"
         "    fn = getattr(math, 'fa' + 'bs')\n"
         "    return fn(x)\n")

_CLAIMS = ("funcs.keep:\n  claims:\n"
           "    - name: mystery\n"
           "      statement: \"is_deterministic(f)\"\n")


def _record(root):
    with open(os.path.join(str(root), ".mathema", "verified",
                           "funcs.keep.yaml")) as fh:
        return (yaml.safe_load(fh) or {})["funcs.keep"]


def test_the_first_verify_after_a_body_change_fails_the_stale_risk(tmp_path):
    funcs = tmp_path / "funcs.py"
    funcs.write_text(_BODY)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "keep.claims.yaml").write_text(_CLAIMS)
    first = _verify(tmp_path)
    row = next(c for c in _record(tmp_path)["claims"]
               if c["name"] == "mystery")
    assert row["verdict"] == "unknown", first.stdout + first.stderr
    assert not (row.get("meta") or {}).get("mathema.invalid_conjecture"), row
    apply_acceptance(plan_acceptance(str(tmp_path), "funcs.keep", "mystery",
                                     "risk", by="lovelace"))
    accepted = _verify(tmp_path)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    funcs.write_text(_BODY.replace("'fa' + 'bs'", "'f' + 'abs'"))
    changed = _verify(tmp_path)
    out = changed.stdout + changed.stderr
    assert changed.returncode != 0, out
    assert "accepted risk" not in out.split("funcs.keep", 1)[1].split(
        "\n", 1)[0], out
    row = next(c for c in _record(tmp_path)["claims"]
               if c["name"] == "mystery")
    assert row["accepted"]["stale"] is True
    again = _verify(tmp_path)
    assert again.returncode != 0, again.stdout + again.stderr
