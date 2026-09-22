# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Suite-wide pytest wiring: the `--extensive` flag that opts into the
extensive-ladder proof corpus, and the `needs_full_proof_budget`
marker for tests whose assertion depends on a proof actually
finishing.

The extensive-ladder tests each run full adjudication twice (fast
path and ladder), so they are skipped by default and run on command:

    python -m pytest --extensive tests/test_extensive_proofs.py

They parallelize cleanly under pytest-xdist (`-n auto`) when it is
installed, since every case is a self-contained adjudication."""
import pytest


def pytest_addoption(parser):
    parser.addoption("--extensive", action="store_true", default=False,
                     help="run the extensive-ladder proof corpus (slower, opt-in)")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "extensive_proofs: contrast cases for the extensive strategy ladder; "
        "skipped unless --extensive is given")
    config.addinivalue_line(
        "markers",
        "needs_full_proof_budget: the assertion depends on a proof "
        "finishing, so the wall-clock cap is raised, see the note above "
        "the fixture in this file")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--extensive"):
        return
    skip = pytest.mark.skip(reason="extensive-ladder corpus: run with --extensive")
    for item in items:
        if "extensive_proofs" in item.keywords:
            item.add_marker(skip)

# --- the proof budget, and why a test may need it raised ---------------
#
# mathema caps proof attempts on the WALL CLOCK (SIGALRM). That makes
# "is this claim provable" partly a function of how fast the machine is
# right now: the same claim on the same code degrades `proven` ->
# `holds` (the empirical fallback is doing its job) whenever the search
# does not finish in time.
#
# Two things routinely slow it enough to matter, and neither is a bug
# in the code under test:
#
#   * coverage line tracing, which `--testmon-forceselect` turns on for
#     every test; measured at roughly 4x on sympy-heavy work, so a
#     0.9s proof becomes 3.5s and blows the 3s fast cap;
#   * ordinary machine load, including a second test run in another
#     terminal.
#
# A test that asserts a VERDICT is asking "is this provable", not "is
# this provable within three seconds on this laptop". Mark it, and it
# gets a budget generous enough that the answer is about the
# mathematics.
#
# Patching is not a one-liner: several engine modules bind the caps at
# IMPORT time (`from .._timeout import FAST_TIMEOUT_SECONDS` at module
# level in _proof_support, _extensive, _strategies, _recurrence,
# _coupled, _smt), so setting the attribute on `mathema._timeout`
# alone leaves those holding the original value. The fixture patches
# every module that captured a copy, which also means a new module
# doing the same import is covered without editing this file.

_GENEROUS_FAST = 60
_GENEROUS_EXTENSIVE = 120


@pytest.fixture(autouse=True)
def full_proof_budget(request, monkeypatch):
    """A wall-clock budget large enough that a verdict reflects the
    mathematics rather than the machine, for any test marked
    `needs_full_proof_budget`. Every other test is left alone, so the
    caps keep being exercised at their real values."""
    if request.node.get_closest_marker("needs_full_proof_budget") is None:
        return
    import sys

    from mathema import _timeout
    targets = [_timeout] + [m for name, m in list(sys.modules.items())
                            if name.startswith("mathema.") and m is not None]
    for mod in targets:
        for attr, value in (("FAST_TIMEOUT_SECONDS", _GENEROUS_FAST),
                            ("EXTENSIVE_TIMEOUT_SECONDS", _GENEROUS_EXTENSIVE)):
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, value, raising=False)
