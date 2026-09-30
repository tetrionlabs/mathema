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
