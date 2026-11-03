# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The shared test-slot pool that bounds how many test workers run at once.

`scripts/test_slots.py` is a development tool, not shipped, so it is
loaded by path. Its lock files are the same ones other repositories on
the machine use, so the protocol (one file per slot, an exclusive flock,
all requested slots or none) is what these tests pin.
"""
import importlib.util
import pathlib
import sys

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "test_slots.py"


def _load():
    spec = importlib.util.spec_from_file_location("test_slots_script", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


slots = _load()


def test_a_request_takes_all_its_slots_or_none(tmp_path):
    pool = slots.SlotPool(tmp_path, 4)
    first = pool.try_take(3, "first")
    assert first is not None and len(first) == 3
    assert pool.try_take(2, "second") is None
    second = pool.try_take(1, "second")
    assert second is not None and len(second) == 1
    pool.release(first)
    pool.release(second)


def test_released_slots_are_free_again_and_holders_are_named(tmp_path):
    pool = slots.SlotPool(tmp_path, 2)
    taken = pool.try_take(2, "lead suite")
    assert pool.holders() == ["lead suite", "lead suite"]
    pool.release(taken)
    assert pool.holders() == []
    again = pool.try_take(2, "agent")
    assert again is not None
    pool.release(again)


def test_a_request_larger_than_the_pool_takes_the_whole_pool(tmp_path):
    pool = slots.SlotPool(tmp_path, 3)
    taken = pool.try_take(8, "everything")
    assert taken is not None and len(taken) == 3
    pool.release(taken)


def test_the_worker_count_is_read_from_either_spelling_of_n():
    assert slots.split_workers(["-n", "4", "tests/a.py"]) == (4, ["tests/a.py"])
    assert slots.split_workers(["-n2", "-x"]) == (2, ["-x"])
    assert slots.split_workers(["tests/a.py"]) == (1, ["tests/a.py"])
