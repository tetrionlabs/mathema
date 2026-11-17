# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Waiting runs are served in the order they arrived."""
import importlib.util
import pathlib
import sys

_SPEC = importlib.util.spec_from_file_location(
    "test_slots", pathlib.Path(__file__).parent.parent / "scripts" / "test_slots.py")
test_slots = importlib.util.module_from_spec(_SPEC)
sys.modules["test_slots"] = test_slots
_SPEC.loader.exec_module(test_slots)


def test_a_later_request_waits_for_every_earlier_one(tmp_path):
    pool = test_slots.SlotPool(tmp_path, 4)
    first = pool.enqueue("whole pool")
    second = pool.enqueue("one slot")
    assert not pool.ahead_of(first)
    assert pool.ahead_of(second)
    pool.leave(first)
    assert not pool.ahead_of(second)
    pool.leave(second)


def test_a_waiter_whose_process_died_is_not_waited_for(tmp_path):
    pool = test_slots.SlotPool(tmp_path, 1)
    pool.queue.mkdir(parents=True)
    (pool.queue / "00000000000000000001-1-1").write_text("gone")
    with pool.held(1, "me", say=lambda text: None):
        assert pool.holders() == ["me"]
    assert list(pool.queue.iterdir()) == []
