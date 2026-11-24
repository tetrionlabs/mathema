# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A key whose processing stops after its record was written gets the
record it had before the run back, whatever stopped it.

An ordinary exception fails the key alone; running out of memory, an
interrupt or the wall-clock alarm ends the sweep. In every case the
record on disk is the one from before the run (or none), and a read of
the verified store later in the same run scope sees what is on disk,
not the record the stopped key wrote.
"""
import pytest

from mathema import _run_scope, _timeout, spec
from mathema import verify as _verify
from tests import test_one_key_crash_does_not_stop_the_sweep as _crash

project = _crash.project
_record = _crash._record
KEY = "crashpkg.boom"

_ADDED = ('      statement: "for n in [0, 10] subset Z, f(n) == n + n + n"\n'
          '    - name: grows\n'
          '      statement: "for n in [0, 10] subset Z, f(n) >= n"\n')


def _edit_claims(root):
    claims = root / "claims" / "demo.claims.yaml"
    text = claims.read_text()
    claims.write_text(text.replace(_ADDED.split("\n")[0] + "\n", _ADDED))


def _stop_after_the_write(monkeypatch, root, exc):
    """`exc` raised for `KEY` once its record is written and the run
    has read the store holding it."""
    real = _verify._carry_recorded_verdicts

    def carry(probes, written, key):
        real(probes, written, key)
        if key == KEY:
            spec.load_verified(str(root))
            raise exc
    monkeypatch.setattr(_verify, "_carry_recorded_verdicts", carry)


def _stop_while_settling(monkeypatch, exc):
    """`exc` raised while `KEY`'s dependencies are settled, after
    every record of the sweep is written."""
    real = _verify._restamp_freshness

    def restamp(target, root):
        out = real(target, root)
        if (target or {}).get("name") == "boom":
            raise exc
        return out
    monkeypatch.setattr(_verify, "_restamp_freshness", restamp)


def _disk_entry(root):
    path = _record(root, KEY)
    if not path.exists():
        return None
    return spec.read_verified_file(str(path))[0].get(KEY)


@pytest.mark.parametrize("first_record", [True, False])
def test_the_run_reads_the_restored_record_from_disk(project, monkeypatch,
                                                     first_record):
    from mathema.verify import verify_project
    if first_record:
        assert not verify_project(root=str(project)).problems
        _edit_claims(project)
    before = (_record(project, KEY).read_bytes()
              if _record(project, KEY).exists() else None)
    with _run_scope.run_scope():
        with monkeypatch.context() as m:
            _stop_after_the_write(m, project, RuntimeError("fell over"))
            out = verify_project(root=str(project))
        kept = spec.load_verified(str(project))
        assert (kept.get(KEY) or {}).get("entry") == _disk_entry(project)
    after = (_record(project, KEY).read_bytes()
             if _record(project, KEY).exists() else None)
    assert after == before
    assert any(KEY in p and "RuntimeError" in p for p in out.problems)


@pytest.mark.parametrize("exc", [MemoryError(), KeyboardInterrupt(),
                                 _timeout._WallClockExpired()])
def test_a_stop_that_ends_the_sweep_puts_the_record_back(project, monkeypatch,
                                                         exc):
    from mathema.verify import verify_project
    assert not verify_project(root=str(project)).problems
    _edit_claims(project)
    before = _record(project, KEY).read_bytes()
    with _run_scope.run_scope():
        with monkeypatch.context() as m:
            _stop_after_the_write(m, project, exc)
            with pytest.raises(type(exc)):
                verify_project(root=str(project))
        kept = spec.load_verified(str(project))
        assert kept[KEY]["entry"] == _disk_entry(project)
    assert _record(project, KEY).read_bytes() == before


@pytest.mark.parametrize("exc", [MemoryError(), KeyboardInterrupt(),
                                 _timeout._WallClockExpired()])
def test_a_first_record_is_removed_whatever_stops_the_sweep(project,
                                                            monkeypatch, exc):
    from mathema.verify import verify_project
    with monkeypatch.context() as m:
        _stop_after_the_write(m, project, exc)
        with pytest.raises(type(exc)):
            verify_project(root=str(project))
    assert not _record(project, KEY).exists()


@pytest.mark.parametrize("exc", [RuntimeError("fell over"), MemoryError(),
                                 KeyboardInterrupt(),
                                 _timeout._WallClockExpired()])
def test_a_stop_while_settling_puts_the_record_back(project, monkeypatch, exc):
    from mathema.verify import verify_project
    assert not verify_project(root=str(project)).problems
    _edit_claims(project)
    before = _record(project, KEY).read_bytes()
    with _run_scope.run_scope():
        with monkeypatch.context() as m:
            _stop_while_settling(m, exc)
            if not isinstance(exc, (MemoryError, KeyboardInterrupt,
                                    _timeout._WallClockExpired)):
                verify_project(root=str(project))
            else:
                with pytest.raises(type(exc)):
                    verify_project(root=str(project))
        kept = spec.load_verified(str(project))
        assert kept[KEY]["entry"] == _disk_entry(project)
    assert _record(project, KEY).read_bytes() == before
