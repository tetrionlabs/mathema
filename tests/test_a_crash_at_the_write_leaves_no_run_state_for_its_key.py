# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A key whose record write raises leaves nothing in the run's totals.

What the sweep gathered for that key before the write (a release move
it would report, an adjudication it would count) is dropped with the
key, so the run's closing notes and counts describe only the keys
whose records were written.
"""
from mathema import spec as _spec
from mathema import sync as _sync
from tests import test_one_key_crash_does_not_stop_the_sweep as _crash

project = _crash.project


def test_a_failed_write_reports_no_release_move_and_no_count(project, monkeypatch):
    from mathema.verify import verify_project
    real_conflicts = _sync.claim_conflicts
    real_record = _spec.record

    def conflicts(fn, file_entry, verified_entry=None):
        found = real_conflicts(fn, file_entry, verified_entry)
        if getattr(fn, "__name__", "") == "boom":
            found = found + [{"kind": "release-move", "claim": "thrice"}]
        return found

    def record(ex, key=None, *args, **kwargs):
        if key == "crashpkg.boom":
            raise OSError("the store is not writable")
        return real_record(ex, key, *args, **kwargs)

    monkeypatch.setattr(_sync, "claim_conflicts", conflicts)
    monkeypatch.setattr(_spec, "record", record)
    out = verify_project(root=str(project))
    assert any("crashpkg.boom" in p and "OSError" in p for p in out.problems)
    assert not any("re-recorded under the new text" in ln for ln in out.lines), \
        out.lines
    assert out.adjudicated == 2, out.adjudicated
