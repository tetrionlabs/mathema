# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A key whose processing crashed after its record was written is
checked again on the next run.

The record a crashed key leaves on disk is the one it had before the
run (or none), never the half-settled record of the crashed run, so a
later run with unchanged code still finds the change that made it
re-check, and adjudicates the key in full.
"""
from mathema import verify as _verify
from tests import test_one_key_crash_does_not_stop_the_sweep as _crash

project = _crash.project
_record = _crash._record

_ADDED = ('      statement: "for n in [0, 10] subset Z, f(n) == n + n + n"\n'
          '    - name: grows\n'
          '      statement: "for n in [0, 10] subset Z, f(n) >= n"\n')


def _crash_after_the_write(monkeypatch):
    real = _verify._carry_recorded_verdicts

    def carry(probes, written, key):
        if key == "crashpkg.boom":
            raise RuntimeError("fell over after the write")
        return real(probes, written, key)
    monkeypatch.setattr(_verify, "_carry_recorded_verdicts", carry)


def _why(out, key):
    return {row["key"]: row for row in out.keys}[key]["why"]


def test_the_crashed_key_is_adjudicated_on_the_next_run(project, monkeypatch):
    from mathema.verify import verify_project
    first = verify_project(root=str(project))
    assert not first.problems, first.problems
    before = _record(project, "crashpkg.boom").read_bytes()
    claims = project / "claims" / "demo.claims.yaml"
    text = claims.read_text()
    claims.write_text(text.replace(_ADDED.split("\n")[0] + "\n", _ADDED))
    assert "grows" in claims.read_text()
    with monkeypatch.context() as m:
        _crash_after_the_write(m)
        crashed = verify_project(root=str(project))
    assert any("crashpkg.boom" in p and "RuntimeError" in p
               for p in crashed.problems), crashed.problems
    assert _record(project, "crashpkg.boom").read_bytes() == before
    again = verify_project(root=str(project))
    assert not again.problems, again.problems
    assert _why(again, "crashpkg.boom") != "fresh", again.keys
    assert _why(again, "crashpkg.alpha") == "fresh", again.keys


def test_a_crashed_first_record_is_not_left_on_disk(project, monkeypatch):
    from mathema.verify import verify_project
    with monkeypatch.context() as m:
        _crash_after_the_write(m)
        verify_project(root=str(project))
    assert not _record(project, "crashpkg.boom").exists()
    again = verify_project(root=str(project))
    assert not again.problems, again.problems
    assert _record(project, "crashpkg.boom").exists()
