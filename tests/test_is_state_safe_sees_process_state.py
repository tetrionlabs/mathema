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
    monkeypatch.delenv("MATHEMA_T", raising=False)
    _state_safe(pure)   # imports made by a first check are not the trial's
    root = logging.getLogger()
    env, cwd, path = dict(os.environ), os.getcwd(), list(sys.path)
    state, np_state = random.getstate(), np.random.get_state()
    level, handlers = root.level, list(root.handlers)
    disabled = logging.root.manager.disable
    for fn in (set_item, update_env, pop_env, change_dir, extend_path,
               configure_logging, put_env, bare_put_env, reseed, bare_draw,
               numpy_reseed, write_then_raise, chdir_then_raise,
               delete_own_cwd, rebind_path):
        _state_safe(fn)
    assert dict(os.environ) == env
    assert os.getcwd() == cwd
    assert sys.path == path
    assert random.getstate() == state
    after = np.random.get_state()
    assert after[0] == np_state[0] and (after[1] == np_state[1]).all()
    assert tuple(after[2:]) == tuple(np_state[2:])
    assert (root.level, list(root.handlers)) == (level, handlers)
    assert logging.root.manager.disable == disabled
    assert "MATHEMA_T=" not in _child_environ()


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
    with pytest.warns(UserWarning, match="could not restore the global state"):
        p = _state_safe(draw_and_configure)
    assert p.verdict == "falsified"
    assert "the global state of random" in str(
        p.meta.get("mathema.restore_failed")), p.meta
    assert "restart it before trusting later results" in (p.note or "")
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


# --- the structural half declines every watched write ------------------------

from logging import getLogger  # noqa: E402
from sys import setrecursionlimit  # noqa: E402
from warnings import simplefilter  # noqa: E402

from numpy.random import seed as numpy_seed  # noqa: E402
from numpy.random import set_state as numpy_set_state  # noqa: E402


def bare_numpy_seed(x: float) -> float:
    numpy_seed(3)
    return x


def bare_numpy_set_state(x: float) -> float:
    numpy_set_state(np.random.get_state())
    return x


def root_level_by_call(x: float) -> float:
    getLogger().setLevel(10)
    return x


def named_logger_handler(x: float) -> float:
    logging.getLogger("mathema.t").addHandler(logging.NullHandler())
    return x


def ignore_warnings(x: float) -> float:
    simplefilter("ignore")
    return x


def deeper_recursion(x: float) -> float:
    setrecursionlimit(1500)
    return x


def local_sort(a: float, b: float) -> float:
    vals = [a, b]
    vals.sort()
    return vals[0]


@pytest.fixture
def warnings_and_recursion_kept():
    import warnings
    limit, filters = sys.getrecursionlimit(), list(warnings.filters)
    yield
    sys.setrecursionlimit(limit)
    warnings.filters[:] = filters


@pytest.mark.parametrize("fn, verdict", [
    (bare_numpy_seed, "falsified"), (bare_numpy_set_state, "holds"),
    (root_level_by_call, "falsified"),
    # outside the watched state: the structure declines a proof and the
    # trials, which do not read warnings filters or the recursion limit,
    # hold; a module-level bound method (`draw`, imported from random)
    # is not data and is not reported as mutated
    (ignore_warnings, "holds"), (deeper_recursion, "holds"),
])
def test_a_watched_write_through_a_bare_name_or_a_call_result_is_not_proven(
        fn, verdict, warnings_and_recursion_kept):
    p = _state_safe(fn)
    assert p.verdict == verdict, (fn.__name__, p.route, p.counterexample)


def test_a_method_call_on_a_local_is_still_proven():
    p = _state_safe(local_sort)
    assert (p.verdict, p.route) == ("proven", "examine")


# --- a write undone before returning is no change -----------------------------

def self_restoring(x: float) -> float:
    old = os.environ.get("HOME")
    os.environ["HOME"] = "/elsewhere"
    os.environ["HOME"] = old
    return x


def checks_another_function(x: float) -> float:
    def inner(y: float) -> float:
        os.environ["MATHEMA_T7"] = "1"
        return y
    check_conjectures(inner, [claim("is_state_safe(f)")])
    return x


def test_a_self_restoring_environment_write_holds():
    p = _state_safe(self_restoring)
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_a_check_run_inside_the_function_is_no_change():
    p = _state_safe(checks_another_function)
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_a_c_environment_write_names_the_variable_as_text():
    p = _state_safe(put_env)
    assert "'MATHEMA_T'" in p.counterexample and "b'" not in p.counterexample


# --- every logger, and a write before a raise -----------------------------------

def named_logger_level(x: float) -> float:
    logging.getLogger("mathema.t.level").setLevel(5)
    return x


def child_logger_handler(x: float) -> float:
    logging.getLogger("mathema.t.child").addHandler(logging.NullHandler())
    return x


def silence_logger(x: float) -> float:
    logging.getLogger("mathema.t.quiet").propagate = False
    return x


def write_then_raise(x: float) -> float:
    os.environ["MATHEMA_T8"] = "1"
    raise ValueError("after the write")


def chdir_then_raise(x: float) -> float:
    os.chdir("/")
    raise ValueError("after the move")


@pytest.mark.parametrize("fn, logger", [
    (named_logger_level, "mathema.t.level"),
    (child_logger_handler, "mathema.t.child"),
    (silence_logger, "mathema.t.quiet"),
])
def test_a_named_logger_configuration_falsifies_and_is_restored(fn, logger):
    target = logging.getLogger(logger)
    kept = (target.level, list(target.handlers), target.propagate)
    p = _state_safe(fn)
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    assert logger in str(p.counterexample), p.counterexample
    assert (target.level, list(target.handlers), target.propagate) == kept


@pytest.mark.parametrize("fn, named", [
    (write_then_raise, "os.environ"), (chdir_then_raise, "working directory")])
def test_a_write_before_a_raise_falsifies(fn, named):
    cwd, env = os.getcwd(), dict(os.environ)
    p = _state_safe(fn)
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    assert named in str(p.counterexample)
    assert "ValueError" in str(p.counterexample)
    assert os.getcwd() == cwd and dict(os.environ) == env


# --- what the rows say ---------------------------------------------------------

def test_a_state_witness_names_the_function_its_input_and_the_change():
    p = _state_safe(set_item)
    assert p.counterexample.startswith("calling set_item with x = "), \
        p.counterexample
    assert "changed os.environ (MATHEMA_T set to '" in p.counterexample


def test_a_c_environment_witness_says_where_the_write_went():
    p = _state_safe(put_env)
    assert p.counterexample.startswith("calling put_env with x = ")
    assert "ran os.putenv('MATHEMA_T')" in p.counterexample
    assert "passes to its subprocesses, where os.environ cannot see it" \
        in p.counterexample


def test_the_record_header_does_not_say_no_side_effects_beside_a_state_write():
    import mathema
    header = repr(mathema.check(set_item)).splitlines()[0]
    assert "source, side effects" in header, header
    header = repr(mathema.check(pure)).splitlines()[0]
    assert "source, no side effects" in header, header


def test_the_check_line_does_not_say_no_side_effects_beside_a_state_write(
        tmp_path, capsys):
    from mathema.cli import main
    (tmp_path / "svc.py").write_text(
        "import os\n\n\ndef remember_rate(rate: float) -> float:\n"
        "    os.environ['MATHEMA_FX'] = str(rate)\n    return rate\n")
    main(["check", str(tmp_path / "svc.py") + ":remember_rate",
          "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "remember_rate: source, side effects;" in out, out


def local_put_env(x: float) -> float:
    from os import putenv as set_c_env
    set_c_env("MATHEMA_T", str(x))
    return x


def local_numpy_seed(x: float) -> float:
    import numpy.random as npr
    npr.seed(3)
    return x


def test_a_writer_imported_inside_the_body_is_a_write_site(monkeypatch):
    monkeypatch.delenv("MATHEMA_T", raising=False)
    from mathema._process_state import writer_calls
    from mathema.analysis import analyze_source
    assert writer_calls(local_put_env, analyze_source(local_put_env))
    p = _state_safe(local_put_env)
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    p = _state_safe(local_numpy_seed)
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)


# --- through check(), where other rows call f first -----------------------------

pricing_log = logging.getLogger("mathema.t.pricing")


def quiet_pricing(price: float) -> float:
    pricing_log.setLevel(logging.WARNING)
    return round(price * 1.2, 2)


def set_pricing_mode(price: float) -> float:
    os.environ["MATHEMA_PRICING_MODE"] = "fast"
    return price * 2.0


def add_pricing_path(price: float) -> float:
    if "/opt/mathema-pricing" not in sys.path:
        sys.path.append("/opt/mathema-pricing")
    return price * 2.0


@pytest.mark.parametrize("fn", [quiet_pricing, set_pricing_mode,
                                add_pricing_path])
def test_an_idempotent_write_is_falsified_through_check_and_does_not_leak(fn):
    import mathema
    level = pricing_log.level
    rows = {p.name: p for p in mathema.check(fn).probes}
    assert rows["is_state_safe"].verdict == "falsified", (
        fn.__name__, rows["is_state_safe"].verdict, rows["is_state_safe"].note)
    assert pricing_log.level == level
    assert "MATHEMA_PRICING_MODE" not in os.environ
    assert "/opt/mathema-pricing" not in sys.path


# --- the trial's own ending is interruption proof -------------------------------

def test_an_alarm_during_the_after_reading_still_restores_the_process(
        monkeypatch):
    import threading
    stop = threading.Event()
    idle = threading.Thread(target=stop.wait, daemon=True)
    idle.start()
    state, env = random.getstate(), dict(os.environ)
    real = _process_state.snapshot
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 2:          # the reading after the call
            raise _WallClockExpired("cap")
        return real()
    monkeypatch.setattr(_process_state, "snapshot", flaky)
    try:
        with pytest.raises(_WallClockExpired):
            with _process_state.isolated(draw_and_configure):
                draw_and_configure(1.0)
    finally:
        stop.set()
    assert random.getstate() == state
    assert dict(os.environ) == env


def test_a_step_interrupted_twice_is_recorded_and_warned(monkeypatch):
    real = random.setstate

    def refuses(saved):
        raise KeyboardInterrupt

    monkeypatch.setattr(random, "setstate", refuses)
    trial = None
    with pytest.warns(UserWarning, match="global state of random"):
        with pytest.raises(KeyboardInterrupt):
            with _process_state.isolated(draw_and_configure) as trial:
                draw_and_configure(1.0)
    monkeypatch.setattr(random, "setstate", real)
    assert any(f.startswith("the global state of random")
               for f in trial.restore_failed), trial.restore_failed


class ClosingHandler(logging.Handler):
    """A handler that remembers being closed."""

    closed = False

    def emit(self, record):
        pass

    def close(self):
        ClosingHandler.closed = True
        super().close()


def adds_a_handler(x: float) -> float:
    logging.getLogger("mathema.t.closing").addHandler(ClosingHandler())
    return x


def test_a_handler_the_function_added_is_closed():
    ClosingHandler.closed = False
    _state_safe(adds_a_handler)
    assert ClosingHandler.closed
    assert not logging.getLogger("mathema.t.closing").handlers
