# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A MemoryError while one key is adjudicated stops the whole sweep.

The per-key guard reports an ordinary exception as that key's failure
and goes on; running out of memory is not a key-local fault, so it
passes through the guard and ends the run, as an interrupt does.
"""
import pytest

from tests import test_one_key_crash_does_not_stop_the_sweep as _crash

project = _crash.project
_raising_check = _crash._raising_check


def test_a_memory_error_is_not_absorbed_by_the_key_guard(project, monkeypatch):
    from mathema.verify import verify_project
    _raising_check(monkeypatch, MemoryError())
    with pytest.raises(MemoryError):
        verify_project(root=str(project))
