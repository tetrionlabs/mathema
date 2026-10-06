# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Emitting a log record is not a state change for is_state_safe
(debug, info, warning, error, exception, critical, log on a module-level
logger or one obtained by name), so a function whose only effect is
logging is proven state safe by structure. Changing logging's
configuration (basicConfig, setLevel, addHandler, disable) stays a
state change and is falsified with the state named."""

import pytest

pytest.importorskip("numpy")

import logging  # noqa: E402
import os  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402

log = logging.getLogger(__name__)


def price_with_audit_log(x: float) -> float:
    log.info("pricing %s", x)
    return 2 * x


def price_with_named_logger(x: float) -> float:
    logging.getLogger("svc.pricing").warning("pricing %s", x)
    return 2 * x


def price_logging_every_level(x: float) -> float:
    log.debug("d %s", x)
    log.error("e %s", x)
    log.critical("c %s", x)
    log.log(logging.INFO, "l %s", x)
    return 2 * x


def price_and_configure(x: float) -> float:
    logging.basicConfig(level=logging.DEBUG)
    return 2 * x


def _state_safe(fn):
    (p,) = check_conjectures(fn, [claim("is_state_safe(f)")])
    return p


def _in_a_fresh_process(names):
    # a test runner attaches its own capturing handlers to every logger,
    # and a handler that is not the standard library's is user code the
    # emission runs: the proof is judged in a process without one
    import subprocess
    import sys
    script = ("import sys, os\n"
              f"sys.path.insert(0, {os.path.dirname(__file__)!r})\n"
              "import test_is_state_safe_logging_is_benign as t\n"
              "from mathema.conjecture import check_conjectures, claim\n"
              f"for name in {list(names)!r}:\n"
              "    (p,) = check_conjectures(getattr(t, name),"
              " [claim('is_state_safe(f)')])\n"
              "    print(name, p.verdict, p.route)\n")
    r = subprocess.run([sys.executable, "-c", script], capture_output=True,
                       text=True, timeout=300)
    return dict((line.split()[0], tuple(line.split()[1:]))
                for line in r.stdout.splitlines() if line.strip()), r.stderr


def test_a_function_that_only_logs_is_proven_state_safe():
    found, err = _in_a_fresh_process(["price_with_audit_log",
                                      "price_logging_every_level"])
    for name in ("price_with_audit_log", "price_logging_every_level"):
        assert found.get(name) == ("proven", "examine"), (name, found, err)


def test_a_logger_obtained_by_name_is_recognised():
    found, err = _in_a_fresh_process(["price_with_named_logger"])
    assert found.get("price_with_named_logger") == ("proven", "examine"), (
        found, err)


def test_a_handler_the_standard_library_does_not_define_is_named():
    # this test runner's own capturing handlers are such handlers
    p = _state_safe(price_with_audit_log)
    assert p.verdict == "unknown", (p.verdict, p.route)
    assert "LogCaptureHandler.emit, which mathema cannot read" in p.note


def test_configuring_logging_is_falsified_with_the_state_named():
    p = _state_safe(price_and_configure)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "logging.basicConfig" in p.counterexample


# --- only the standard library's own emission is benign ------------------------

import numpy as np  # noqa: E402


class EnvAdapter(logging.LoggerAdapter):
    """An adapter whose `process` writes the environment."""

    def process(self, msg, kwargs):
        os.environ["MATHEMA_LB_ADAPTER"] = "1"
        return msg, kwargs


class SeedingLogger(logging.Logger):
    """A logger whose `info` reseeds numpy's global generator."""

    def info(self, msg, *args, **kwargs):
        np.random.seed(0)
        super().info(msg, *args, **kwargs)


class SeedingHandler(logging.Handler):
    """A handler whose `emit` reseeds numpy's global generator."""

    def emit(self, record):
        np.random.seed(3)


_adapted = logging.getLogger("mathema.t.lb")
_adapted.setLevel(logging.INFO)
_adapted.propagate = False
env_adapter = EnvAdapter(_adapted, {})
seeding_logger = SeedingLogger("mathema.t.lb.custom")
seeded = logging.getLogger("mathema.t.lb.seeded")
seeded.addHandler(SeedingHandler())
seeded.setLevel(logging.INFO)
seeded.propagate = False


def price_through_env_adapter(x: float) -> float:
    env_adapter.info("x=%s", x)
    return 2 * x


def price_through_seeding_logger(x: float) -> float:
    seeding_logger.info("x")
    return 2 * x


def price_through_seeding_handler(x: float) -> float:
    seeded.info("x")
    return 2 * x


def test_user_logging_code_that_writes_state_is_not_proven_and_falsifies():
    for fn in (price_through_env_adapter, price_through_seeding_logger,
               price_through_seeding_handler):
        p = _state_safe(fn)
        assert p.verdict == "falsified", (fn.__name__, p.verdict, p.route,
                                          p.note)
