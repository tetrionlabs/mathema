# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What `mathema accept` prints: a header naming the key, the claim,
the kind of acceptance and the person; the verdict line with its
witness; one line per move; one line for the correction where one
applies; then the prompt and `written.`. Several claims on one key
are accepted in one act, each listed in the same shape, with one
prompt for all of them."""
import subprocess
import sys

import yaml

from tests.test_cli_verify import _env_with_repo_on_path

_KEEP = ("def keep(x: float) -> float:\n"
         "    return abs(x)\n")
_WRONG = ("    - name: wrong\n"
          "      statement: \"for x in [-5, 5], f(x) == x\"\n"
          "      route: probe\n")
_NEGATIVE = ("    - name: negative\n"
             "      statement: \"for x in [-5, 5], f(x) == -x\"\n"
             "      route: probe\n")
_NONNEG = ("    - name: nonneg\n"
           "      statement: \"for x in [-5, 5], f(x) >= 0\"\n"
           "      route: probe\n")


def _main(root, *argv, stdin=None):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(argv) + ['--root', str(root)]!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, input=stdin,
                          env=_env_with_repo_on_path())


def _project(tmp_path, *rows):
    (tmp_path / "funcs.py").write_text(_KEEP)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "funcs.claims.yaml").write_text(
        "funcs.keep:\n  claims:\n" + "".join(rows))
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _main(tmp_path, "verify", "--lenient")
    return tmp_path


def _record(root):
    path = root / ".mathema" / "verified" / "funcs.keep.yaml"
    return yaml.safe_load(path.read_text())["funcs.keep"]


def _witness(root, name):
    entry = _record(root)
    row = next(c for c in entry["claims"] if c["name"] == name)
    return row["counterexample"]


def test_a_discovery_beside_a_holding_claim_reads_in_four_lines(tmp_path):
    root = _project(tmp_path, _WRONG, _NONNEG)
    witness = _witness(root, "wrong")
    r = _main(root, "accept", "funcs.keep", "wrong", "--as", "discovery",
              "--by", "Ada Lovelace", stdin="y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == (
        "accept funcs.keep :: wrong as a discovery, by Ada Lovelace\n"
        f"  falsified at {witness}\n"
        "  the claim moves to discoveries with that witness, out of "
        "claims/funcs.claims.yaml\n"
        "write this acceptance? [y/N] written.\n")


def test_a_discovery_with_nothing_holding_names_the_missing_correction(
        tmp_path):
    root = _project(tmp_path, _WRONG)
    witness = _witness(root, "wrong")
    r = _main(root, "accept", "funcs.keep", "wrong", "--as", "discovery",
              "--by", "Ada Lovelace", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == (
        "accept funcs.keep :: wrong as a discovery, by Ada Lovelace\n"
        f"  falsified at {witness}\n"
        "  the claim moves to discoveries with that witness, out of "
        "claims/funcs.claims.yaml\n"
        "  no corrected claim; pass --corrected \"<law>\" to state what "
        "is true\n"
        "written.\n")


def test_a_stated_correction_is_one_line(tmp_path):
    root = _project(tmp_path, _WRONG)
    r = _main(root, "accept", "funcs.keep", "wrong", "--as", "discovery",
              "--corrected", "for x in [-5, 5], f(x) >= x",
              "--by", "Ada Lovelace", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.splitlines()
    assert lines[2] == ("  the claim moves to discoveries with that "
                        "witness, out of claims/funcs.claims.yaml")
    assert lines[3].startswith(
        "  the corrected claim takes its place: wrong_corrected [probe]: "
        "for x in [-5, 5], f(x) >= x, checked now: holds"), r.stdout
    assert lines[4:] == ["written."], r.stdout


def test_evidence_states_the_verdict_and_the_one_move(tmp_path):
    root = _project(tmp_path, _NONNEG)
    n = next(c for c in _record(root)["claims"] if c["name"] == "nonneg")["n"]
    form = _record(root)["identity"]["form"]
    r = _main(root, "accept", "funcs.keep", "nonneg", "--as", "evidence",
              "--by", "Ada Lovelace", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == (
        "accept funcs.keep :: nonneg as evidence, by Ada Lovelace\n"
        f"  holds over {n} trials\n"
        f"  the claim is accepted as evidence at n={n}, bound to form "
        f"{form}\n"
        "written.\n")


def test_several_claims_are_accepted_under_one_prompt(tmp_path):
    root = _project(tmp_path, _WRONG, _NEGATIVE, _NONNEG)
    wrong, negative = _witness(root, "wrong"), _witness(root, "negative")
    r = _main(root, "accept", "funcs.keep", "wrong", "negative",
              "--as", "discovery", "--by", "Ada Lovelace", stdin="y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    move = ("  the claim moves to discoveries with that witness, out of "
            "claims/funcs.claims.yaml\n")
    assert r.stdout == (
        "accept funcs.keep :: wrong as a discovery, by Ada Lovelace\n"
        f"  falsified at {wrong}\n" + move
        + "accept funcs.keep :: negative as a discovery, by Ada Lovelace\n"
        f"  falsified at {negative}\n" + move
        + "write these 2 acceptances? [y/N] written.\n")
    entry = _record(root)
    assert {d["name"] for d in entry["discoveries"]} == {"wrong", "negative"}
    assert "nonneg" in {c["name"] for c in entry["claims"]}
    declared = yaml.safe_load(
        (root / "claims" / "funcs.claims.yaml").read_text())
    assert [c["name"] for c in declared["funcs.keep"]["claims"]] == [
        "nonneg"]


def test_declining_several_claims_writes_none(tmp_path):
    root = _project(tmp_path, _WRONG, _NEGATIVE)
    before = (root / ".mathema" / "verified" / "funcs.keep.yaml").read_text()
    r = _main(root, "accept", "funcs.keep", "wrong", "negative",
              "--as", "discovery", stdin="n\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout.endswith("nothing written\n"), r.stdout
    after = (root / ".mathema" / "verified" / "funcs.keep.yaml").read_text()
    assert after == before
