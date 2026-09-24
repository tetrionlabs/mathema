# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bad argument is exit 2 with a clean one-line message, never a
traceback and never the gate-failure code 1: a malformed `--claim`, a
non-positive `--trials-scale`, a bad `--domain`, an unknown audit
`--exclude`. Also covers the Python API side of a malformed claim
(`claim()` raises `InvalidConjecture`) and how `verify` reports a
malformed claim sitting in a claims file."""
import subprocess
import sys

import pytest

from mathema.conjecture import InvalidConjecture, claim

MALFORMED_CLAIMS = ["f(x) >= 1 +", "f(x) === 1", "f(x) >= ("]


def _run(*argv, cwd):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(argv)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(cwd),
                          capture_output=True, text=True)


def _write_funcs(path):
    path.write_text("def sq(x: float) -> float:\n"
                    "    return x * x + 1\n")


@pytest.mark.parametrize("law", MALFORMED_CLAIMS)
def test_claim_raises_invalid_conjecture_for_an_unreadable_side(law):
    with pytest.raises(InvalidConjecture) as info:
        claim(law)
    assert law in str(info.value)


def test_claim_still_accepts_well_formed_relations():
    assert claim("f(x) >= 1 + x").rhs == "1 + x"
    assert claim("0 <= f(x) <= 1").links


@pytest.mark.parametrize("law", MALFORMED_CLAIMS)
def test_check_with_a_malformed_claim_exits_2_with_one_clean_line(
        tmp_path, law):
    _write_funcs(tmp_path / "funcs.py")
    r = _run("check", "funcs.py", "--claim", law, cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    lines = r.stderr.strip().splitlines()
    assert len(lines) == 1, r.stderr
    assert lines[0].startswith("mathema: ")
    assert law in lines[0]


def test_verify_reports_a_malformed_claims_file_claim_without_a_traceback(
        tmp_path):
    pkg = tmp_path / "vpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    _write_funcs(pkg / "mod.py")
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "vpkg.mod.claims.yaml").write_text(
        "vpkg.mod.sq:\n"
        "  claims:\n"
        "    - name: bad\n"
        '      statement: "f(x) >= 1 +"\n')
    r = _run("verify", "--root", str(tmp_path), cwd=tmp_path)
    assert "Traceback" not in r.stderr, r.stderr
    # the per-key report: a FAIL line naming the key; a claim that does
    # not parse is an authoring error, exit 2, as `check` gives
    assert r.returncode == 2, r.stdout + r.stderr
    assert "FAIL vpkg.mod.sq" in r.stdout
    assert "f(x) >= 1 +" in r.stdout


@pytest.mark.parametrize("bad", ["0", "-0.5"])
def test_check_trials_scale_not_positive_exits_2(tmp_path, bad):
    _write_funcs(tmp_path / "funcs.py")
    r = _run("check", "funcs.py", "--trials-scale", bad, cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    assert "--trials-scale" in r.stderr


def test_verify_trials_scale_not_positive_exits_2(tmp_path):
    r = _run("verify", "--root", str(tmp_path), "--trials-scale", "0",
             cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "--trials-scale" in r.stderr


def test_check_bad_domain_exits_2(tmp_path):
    _write_funcs(tmp_path / "funcs.py")
    r = _run("check", "funcs.py", "--domain", "not-a-domain", cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "bad --domain" in r.stderr


def test_audit_unknown_exclude_exits_2(tmp_path):
    pkg = tmp_path / "apkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    _write_funcs(pkg / "mod.py")
    r = _run("audit", "apkg", "--root", str(tmp_path), "--exclude", "bogus",
             cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "unknown --exclude" in r.stderr
