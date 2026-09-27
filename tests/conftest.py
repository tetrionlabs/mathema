# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Suite-wide pytest wiring: the `--extensive` flag that opts into the
extensive-ladder proof corpus, the `needs_full_proof_budget` marker
for tests whose assertion depends on a proof actually finishing, and
isolation from capability providers installed in the environment.

The extensive-ladder tests each run full adjudication twice (fast
path and ladder), so they are skipped by default and run on command:

    python -m pytest --extensive tests/test_extensive_proofs.py

They parallelize cleanly under pytest-xdist (`-n auto`) when it is
installed, since every case is a self-contained adjudication."""
import pytest


@pytest.fixture(autouse=True)
def _no_installed_providers(monkeypatch):
    """Capability providers installed in the environment (a symbology
    package, say) change rendered output, so every test runs against
    mathema's own defaults; a test about providers patches its own in."""
    from mathema import _providers
    discovered, load = _providers._discovered, _providers._load
    monkeypatch.setattr(_providers, "entry_points", lambda **_: [])
    discovered.cache_clear()
    load.cache_clear()
    yield
    discovered.cache_clear()
    load.cache_clear()


@pytest.fixture(autouse=True)
def _no_installed_runtime_type_adapters(monkeypatch):
    """Runtime type adapters installed in the environment change how a
    parameter is realised, so every test runs against the built-ins; a
    test about registered adapters patches its own in."""
    from mathema import runtime_types
    monkeypatch.setattr(runtime_types, "entry_points", lambda **_: [])
    runtime_types._discovered.cache_clear()
    yield
    runtime_types._discovered.cache_clear()


@pytest.fixture(autouse=True)
def _no_project_pseudo_infinity(monkeypatch):
    """A project-level `MATHEMA_PSEUDO_INFINITY` set on this machine
    moves how far every unbounded direction is exercised, so every
    test starts without one; a test about the project level sets its
    own."""
    monkeypatch.delenv("MATHEMA_PSEUDO_INFINITY", raising=False)


@pytest.fixture(autouse=True)
def _library_claims_isolated():
    """Installing library claims (`compendium.install`, which `verify`,
    `write_spec` and `mathema check` do) registers process-wide
    partiality guards and a hazard generator; every test starts and
    ends with the registries as they were, so no verdict depends on
    which test ran earlier in the same process. The baseline is the
    bundled library claims alone, the state every `check()` starts
    from."""
    from mathema import compendium, hazards
    from mathema.symbolic import _partiality
    compendium.ensure_bundled()
    lemmas = {k: list(v) for k, v in _partiality._PARTIALITY_LEMMAS.items()}
    computation = {k: list(v) for k, v in compendium._COMPUTATION.items()}
    generators = dict(hazards._GENERATORS)
    installed = dict(compendium._INSTALLED)
    yield
    _partiality._PARTIALITY_LEMMAS.clear()
    _partiality._PARTIALITY_LEMMAS.update(lemmas)
    compendium._COMPUTATION.clear()
    compendium._COMPUTATION.update(computation)
    hazards._GENERATORS.clear()
    hazards._GENERATORS.update(generators)
    compendium._INSTALLED.clear()
    compendium._INSTALLED.update(installed)


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
    config.addinivalue_line(
        "markers",
        "slow_docs_example: a documentation example that takes more than "
        "a few seconds to run, see tests/test_docs_outputs.py")


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
