# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_state_safe sees the state a function can change for the whole
process, not only its own module's globals: the environment (through
os.environ and through os.putenv, which changes the C environment
only), the working directory, sys.path, the global state of `random`
and `numpy.random`, and logging's root configuration. Each write
falsifies with the state named; a call that writes none still proves
by structure, and checking leaves the process as it found it."""
import logging
import os
import random
import sys
from os import putenv
from random import random as draw

import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")


def set_item(x: float) -> float:
    os.environ["MATHEMA_T"] = str(x)
    return x


def put_env(x: float) -> float:
    os.putenv("MATHEMA_T", str(x))
    return x


def bare_put_env(x: float) -> float:
    putenv("MATHEMA_T", str(x))
    return x


def update_env(x: float) -> float:
    os.environ.update({"MATHEMA_T": str(x)})
    return x


def setdefault_env(x: float) -> float:
    os.environ.setdefault("MATHEMA_T2", str(x))
    return x


def pop_env(x: float) -> float:
    os.environ.pop("MATHEMA_T3", None)
    return x


def change_dir(x: float) -> float:
    os.chdir(os.path.dirname(os.getcwd()))
    return x


def extend_path(x: float) -> float:
    sys.path.append(f"/nowhere/{x}")
    return x


def reseed(x: float) -> float:
    random.seed(x)
    return x


def bare_draw(x: float) -> float:
    return x + 0.0 * draw()


def numpy_reseed(x: float) -> float:
    np.random.seed(int(abs(x)) % 1000)
    return x


def configure_logging(x: float) -> float:
    logging.getLogger().setLevel(logging.DEBUG if x > 0 else logging.ERROR)
    return x


def pure(x: float) -> float:
    return 2 * x


def _state_safe(fn):
    (p,) = check_conjectures(fn, [claim("is_state_safe(f)")])
    return p


@pytest.mark.parametrize("fn, named", [
    (set_item, "os.environ"), (update_env, "os.environ"),
    (setdefault_env, "os.environ"), (pop_env, "os.environ"),
    (put_env, "os.putenv"), (bare_put_env, "os.putenv"),
    (change_dir, "working directory"), (extend_path, "sys.path"),
    (reseed, "random"), (bare_draw, "random"),
    (numpy_reseed, "numpy.random"), (configure_logging, "logging"),
])
def test_a_process_state_write_falsifies_with_the_state_named(
        fn, named, monkeypatch):
    monkeypatch.setenv("MATHEMA_T3", "present")
    p = _state_safe(fn)
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    assert named in str(p.counterexample), p.counterexample


def test_checking_leaves_the_process_as_it_found_it(monkeypatch):
    monkeypatch.setenv("MATHEMA_T3", "present")
    env, cwd, path = dict(os.environ), os.getcwd(), list(sys.path)
    level = logging.getLogger().level
    for fn in (set_item, update_env, pop_env, change_dir, extend_path,
               configure_logging):
        _state_safe(fn)
    assert dict(os.environ) == env
    assert os.getcwd() == cwd
    assert sys.path == path
    assert logging.getLogger().level == level


def test_a_bare_writer_call_is_a_write_site_for_the_structural_half():
    p = _state_safe(bare_put_env)
    assert p.route != "examine"


def test_a_function_writing_nothing_still_proves_by_structure():
    p = _state_safe(pure)
    assert (p.verdict, p.route) == ("proven", "examine")


# --- the trial always puts the process back --------------------------------

import subprocess  # noqa: E402
import tempfile  # noqa: E402

from mathema import _process_state  # noqa: E402
from mathema._timeout import _WallClockExpired  # noqa: E402


def _child_environ() -> str:
    return subprocess.run(["/usr/bin/env"], capture_output=True, text=True,
                          cwd="/").stdout


def delete_own_cwd(x: float) -> float:
    d = tempfile.mkdtemp()
    os.chdir(d)
    os.rmdir(d)
    return x


def unset_existing(x: float) -> float:
    os.unsetenv("MATHEMA_T4")
    return x


def rebind_path(x: float) -> float:
    sys.path = sys.path + ["/rebound"]
    return x


def draw_and_configure(x: float) -> float:
    random.random()
    logging.getLogger().setLevel(1)
    os.environ["MATHEMA_T5"] = "1"
    return x


def test_a_deleted_working_directory_is_reported_and_the_process_recovers():
    cwd = os.getcwd()
    p = _state_safe(delete_own_cwd)
    assert p.verdict == "falsified"
    assert "the working directory (deleted)" in str(p.counterexample)
    assert os.getcwd() == cwd
    assert _state_safe(set_item).verdict == "falsified"   # the next check runs


def test_a_c_environment_write_is_undone(monkeypatch):
    monkeypatch.delenv("MATHEMA_T", raising=False)
    _state_safe(put_env)
    _state_safe(bare_put_env)
    assert "MATHEMA_T=" not in _child_environ()


def test_a_c_environment_unset_is_undone(monkeypatch):
    monkeypatch.setenv("MATHEMA_T4", "kept")
    _state_safe(unset_existing)
    assert "MATHEMA_T4=kept" in _child_environ()


def test_a_rebound_sys_path_is_the_same_list_again():
    original = sys.path
    _state_safe(rebind_path)
    assert sys.path is original
    assert "/rebound" not in sys.path


def test_the_environment_is_restored_without_emptying_it(monkeypatch):
    # restoring never clears the environment, so a thread reading it
    # meanwhile never sees it empty
    def refuse():
        raise AssertionError("os.environ was cleared")
    monkeypatch.setattr(os.environ, "clear", refuse)
    _state_safe(set_item)
    assert "MATHEMA_T" not in os.environ or os.environ["MATHEMA_T"] != ""


def test_an_alarm_during_the_restore_waits_until_the_restore_is_done(
        monkeypatch):
    # a real SIGALRM armed inside the restore is held back until every
    # step has run, or, when another thread takes it, the interrupted
    # step runs again; either way it is delivered and nothing is left
    # half restored
    import signal
    import time
    level, state = logging.getLogger().level, random.getstate()
    env = dict(os.environ)
    real = random.setstate

    armed = []

    def slow_setstate(saved):
        if not armed:
            armed.append(True)
            signal.setitimer(signal.ITIMER_REAL, 0.001)
            time.sleep(0.05)
        return real(saved)

    def handler(signum, frame):
        raise _WallClockExpired("cap")
    previous = signal.signal(signal.SIGALRM, handler)
    monkeypatch.setattr(random, "setstate", slow_setstate)
    try:
        with pytest.raises(_WallClockExpired):
            with _process_state.isolated(draw_and_configure):
                draw_and_configure(1.0)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        monkeypatch.setattr(random, "setstate", real)
    assert random.getstate() == state
    assert logging.getLogger().level == level
    assert dict(os.environ) == env


def test_a_restore_step_that_fails_is_recorded_on_the_row(monkeypatch):
    def broken(saved):
        raise RuntimeError("no")
    _state_safe(pure)   # imports made by a first check are not the trial's
    level, env = logging.getLogger().level, dict(os.environ)
    monkeypatch.setattr(random, "setstate", broken)
    with pytest.warns(UserWarning, match="could not put the process back"):
        p = _state_safe(draw_and_configure)
    assert p.verdict == "falsified"
    assert "the global state of random" in str(
        p.meta.get("mathema.restore_failed")), p.meta
    assert "could not put the process back" in (p.note or "")
    # every other part was still put back
    assert logging.getLogger().level == level
    assert dict(os.environ) == env


def test_a_part_that_cannot_be_read_does_not_crash_the_check(monkeypatch):
    calls = {"n": 0}
    real = np.random.get_state

    def flaky():
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("unreadable")
        return real()
    _state_safe(pure)   # imports made by a first check are not the trial's
    monkeypatch.setattr(np.random, "get_state", flaky)
    env = dict(os.environ)
    p = _state_safe(set_item)
    assert p.verdict == "falsified"
    assert dict(os.environ) == env


def test_restore_reports_a_failed_step_and_runs_the_rest():
    before = _process_state.snapshot()
    os.environ["MATHEMA_T6"] = "1"
    before_bad = dict(before, **{"the working directory": "/no/such/dir"})
    failed = _process_state.restore(before_bad)
    assert any(f.startswith("the working directory") for f in failed)
    assert "MATHEMA_T6" not in os.environ
