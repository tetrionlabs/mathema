# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Emitting a log record is not a state change for is_state_safe
(debug, info, warning, error, exception, critical, log on a module-level
logger or one obtained by name), so a function whose only effect is
logging is proven state safe by structure. Changing logging's
configuration (basicConfig, setLevel, addHandler, disable) stays a
state change and is falsified with the state named."""
import logging

from mathema.conjecture import check_conjectures, claim

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
    # force: the root logger already has handlers under a test runner,
    # and basicConfig without it would change nothing
    logging.basicConfig(level=logging.DEBUG, force=True)
    return 2 * x


def _state_safe(fn):
    (p,) = check_conjectures(fn, [claim("is_state_safe(f)")])
    return p


def test_a_function_that_only_logs_is_proven_state_safe():
    for fn in (price_with_audit_log, price_logging_every_level):
        p = _state_safe(fn)
        assert (p.verdict, p.route) == ("proven", "examine"), (
            fn.__name__, p.verdict, p.route, p.note)


def test_a_logger_obtained_by_name_is_recognised():
    p = _state_safe(price_with_named_logger)
    assert (p.verdict, p.route) == ("proven", "examine"), (p.verdict, p.note)


def test_configuring_logging_is_falsified_with_the_state_named():
    p = _state_safe(price_and_configure)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "logging's root configuration" in p.counterexample
