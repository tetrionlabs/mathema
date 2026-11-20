# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""docsync's diagnostics say where the problem is.

The index it could not write is named under the project root given
with `--root`. A claim it cannot read is reported as a diagnostic: a
summary line, the title, the claims file and line with the claim and
function named, the quoted line, and one sentence with the fix.
"""
import os

from mathema.cli import main
from tests import test_docsync_reports_a_claim_it_cannot_read_and_goes_on as _unread
from tests import test_docsync_says_when_the_index_is_not_written as _index

project = _index.project


def test_the_index_error_names_the_index_under_the_root(project, capsys):
    main(["docsync", "--root", str(project), "--yes"])
    err = capsys.readouterr().err
    where = os.path.join(str(project), ".mathema", "index.yaml")
    assert f"  on {where}\n" in err, err
    assert f"make {where} writable" in err, err


def test_an_unreadable_claim_is_a_diagnostic(tmp_path):
    env = _unread._project(tmp_path)
    first = _unread._run(tmp_path, env, "verify")
    assert first.returncode == 0, first.stdout + first.stderr
    line = _unread._reauthor_unreadably(tmp_path, "dpkg.mod.one")
    run = _unread._run(tmp_path, env, "docsync", "dpkg.mod")
    out = run.stdout.splitlines()
    at = next(i for i, ln in enumerate(out) if ln.startswith("UNREADABLE"))
    where = os.path.join("claims", "d.claims.yaml")
    text = "statement: 'for x in [0, 1], f(x) <= <= x'"
    assert out[at + 1:at + 7] == [
        "", "Error: a claim does not read", "",
        f"  on {where} line {line}, claim above of dpkg.mod.one:",
        f"  {line}:   {text}", ""], run.stdout
    fix = out[at + 7]
    assert "this function was not synced" in fix, fix
    assert fix.endswith("correct the claim there and run mathema docsync "
                        "again."), fix
