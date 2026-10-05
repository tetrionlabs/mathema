# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_state_safe sees writes to state the whole process shares, read
from the source: the environment (through os.environ, os.putenv and
an alias of either), the working directory, sys.path, the shared
random generators, warnings and logging configuration. Each write
falsifies with its site as the witness, and none of it runs: the
process is never changed, so it never needs restoring. A function
whose only work is arithmetic is proven."""
import logging
import os
import random
import sys
from os import putenv
from random import random as draw

import pytest

from mathema import check
from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")

pricing_log = logging.getLogger("mathema.t.pricing")


def set_item(x: float) -> float:
    os.environ["MATHEMA_T"] = str(x)
    return x


def put_env(x: float) -> float:
    os.putenv("MATHEMA_T", str(x))
    return x


def bare_put_env(x: float) -> float:
    putenv("MATHEMA_T", str(x))
    return x


def local_put_env(x: float) -> float:
    from os import putenv as set_c_env
    set_c_env("MATHEMA_T", str(x))
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


def self_restoring(x: float) -> float:
    old = os.environ.get("HOME")
    os.environ["HOME"] = "/elsewhere"
    os.environ["HOME"] = old
    return x


def change_dir(x: float) -> float:
    os.chdir(os.path.dirname(os.getcwd()))
    return x


def extend_path(x: float) -> float:
    sys.path.append(f"/nowhere/{x}")
    return x


def rebind_path(x: float) -> float:
    sys.path = sys.path + ["/rebound"]
    return x


def reseed(x: float) -> float:
    random.seed(x)
    return x


def bare_draw(x: float) -> float:
    return x + 0.0 * draw()


def numpy_reseed(x: float) -> float:
    np.random.seed(int(abs(x)) % 1000)
    return x


def local_numpy_seed(x: float) -> float:
    import numpy.random as npr
    npr.seed(3)
    return x


def configure_logging(x: float) -> float:
    logging.getLogger().setLevel(logging.DEBUG if x > 0 else logging.ERROR)
    return x


def quiet_pricing(price: float) -> float:
    pricing_log.setLevel(logging.WARNING)
    return round(price * 1.2, 2)


def silence_logger(x: float) -> float:
    logging.getLogger("mathema.t.quiet").propagate = False
    return x


def ignore_warnings(x: float) -> float:
    import warnings
    warnings.simplefilter("ignore")
    return x


def deeper_recursion(x: float) -> float:
    sys.setrecursionlimit(1500)
    return x


def write_then_raise(x: float) -> float:
    os.environ["MATHEMA_T8"] = "1"
    raise ValueError("after the write")


def pure(x: float) -> float:
    return 2 * x


def local_sort(a: float, b: float) -> float:
    vals = [a, b]
    vals.sort()
    return vals[0]


@pytest.fixture(scope="module", autouse=True)
def _imports_made():
    # a first check imports what the engine needs; an import that sets an
    # environment variable is not the examined function's doing
    check_conjectures(pure, [claim("f(x) >= -1e300")])


def _state_safe(fn):
    (p,) = check_conjectures(fn, [claim("is_state_safe(f)")])
    return p


@pytest.mark.parametrize("fn, named", [
    (set_item, "os.environ"), (update_env, "os.environ"),
    (setdefault_env, "os.environ"), (pop_env, "os.environ"),
    (self_restoring, "os.environ"),
    (put_env, "os.putenv"), (bare_put_env, "os.putenv"),
    (local_put_env, "os.putenv"),
    (change_dir, "os.chdir"), (extend_path, "sys.path"),
    (rebind_path, "sys.path"),
    (reseed, "random.seed"), (bare_draw, "shared random generator"),
    (numpy_reseed, "numpy.random.seed"), (local_numpy_seed, "numpy.random.seed"),
    (configure_logging, "setLevel"), (quiet_pricing, "setLevel"),
    (silence_logger, "propagate"), (ignore_warnings, "simplefilter"),
    (deeper_recursion, "setrecursionlimit"),
    (write_then_raise, "os.environ"),
])
def test_a_process_state_write_falsifies_with_its_site(fn, named):
    env, cwd, path = dict(os.environ), os.getcwd(), list(sys.path)
    p = _state_safe(fn)
    assert (p.verdict, p.route) == ("falsified", "examine"), (
        fn.__name__, p.verdict, p.note)
    assert named in str(p.counterexample), p.counterexample
    assert (dict(os.environ), os.getcwd(), sys.path) == (env, cwd, path)


def test_the_witness_names_the_function_and_the_change():
    p = _state_safe(set_item)
    assert p.counterexample == (
        "set_item changes os.environ (os.environ['MATHEMA_T'] = ...)")


def test_check_states_the_write_under_the_function(monkeypatch):
    # other rows of check() run the function; the write is read from
    # the source, stated under the function, and is_state_safe is not
    # suggested for a function that writes at its defaults
    monkeypatch.setattr(pricing_log, "level", pricing_log.level)
    rec = check(quiet_pricing)
    assert "is_state_safe" not in {p.name for p in rec.probes}
    assert rec.meta["mathema.effects"]["writes"], rec.meta
    assert "  effects: " in repr(rec)


@pytest.mark.parametrize("fn", [pure, local_sort])
def test_a_function_writing_nothing_is_proven(fn):
    p = _state_safe(fn)
    assert (p.verdict, p.route) == ("proven", "examine"), (p.verdict, p.note)


def test_the_record_header_does_not_say_no_side_effects_beside_a_state_write(
        monkeypatch):
    # other rows of check() run the function, which sets the variable
    monkeypatch.setenv("MATHEMA_T", "0")
    header = repr(check(set_item)).splitlines()[0]
    assert "source, side effects" in header, header
    header = repr(check(pure)).splitlines()[0]
    assert "source, no side effects" in header, header


def test_the_check_line_does_not_say_no_side_effects_beside_a_state_write(
        tmp_path, capsys, monkeypatch):
    from mathema.cli import main
    monkeypatch.setenv("MATHEMA_FX", "0")
    (tmp_path / "svc.py").write_text(
        "import os\n\n\ndef remember_rate(rate: float) -> float:\n"
        "    os.environ['MATHEMA_FX'] = str(rate)\n    return rate\n")
    main(["check", str(tmp_path / "svc.py") + ":remember_rate",
          "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "remember_rate: source, side effects;" in out, out
