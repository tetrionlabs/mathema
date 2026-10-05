# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Suite-wide pytest wiring: the `--extensive` flag that opts into the
extensive-ladder proof corpus, the `--third-party-compendiums` flag
that opts into adjudicating the bundled compendium rows against the
installed libraries, the `needs_full_proof_budget` marker for tests whose assertion depends on a proof actually finishing, and
isolation from capability providers installed in the environment.

The extensive-ladder tests each run full adjudication twice (fast
path and ladder), so they are skipped by default and run on command:

    python -m pytest --extensive tests/test_extensive_proofs.py

They parallelize cleanly under pytest-xdist (`-n auto`) when it is
installed, since every case is a self-contained adjudication.

A test marked `third_party_compendiums` checks a library (or
mathema's reading of it) rather than mathema, so it is skipped by
default too:

    python -m pytest -n 4 -q -m third_party_compendiums \
        --third-party-compendiums"""
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
def _len_refinement():
    """mathema registers no refinement key; the suite registers `len`
    (see `tests/_length_refinement.py`) so its length-bounded claims
    resolve, as they do with the mathema-language package installed."""
    from mathema.languages import register_refinement, unregister_refinement
    from tests._length_refinement import length
    register_refinement("len", length)
    yield
    unregister_refinement("len")


@pytest.fixture(autouse=True)
def _no_project_pseudo_infinity(monkeypatch):
    """A project-level `MATHEMA_PSEUDO_INFINITY` set on this machine
    moves how far every unbounded direction is exercised, so every
    test starts without one; a test about the project level sets its
    own."""
    monkeypatch.delenv("MATHEMA_PSEUDO_INFINITY", raising=False)


@pytest.fixture(autouse=True)
def _no_throwaway_modules_left_behind(tmp_path_factory):
    """A test that imports a package it wrote under its temporary
    directory (`spkg.mod`, say) leaves no module behind: every module
    imported during the test from a file under pytest's temporary base
    directory is removed afterwards, so a later test in the same process
    that writes a package of the same name imports its own."""
    import os
    import sys
    base = os.path.realpath(str(tmp_path_factory.getbasetemp())) + os.sep
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        module = sys.modules.get(name)
        path = getattr(module, "__file__", None)
        if path and os.path.realpath(path).startswith(base):
            sys.modules.pop(name, None)


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
    from mathema.runtime_types import _missing
    definitions = dict(_missing._DEFINITIONS)
    yield
    _missing._DEFINITIONS.clear()
    _missing._DEFINITIONS.update(definitions)
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
    parser.addoption("--third-party-compendiums", action="store_true",
                     default=False,
                     help="adjudicate the bundled compendium rows against the "
                          "installed libraries (opt-in)")


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
    config.addinivalue_line(
        "markers",
        "third_party_compendiums: adjudicates bundled compendium rows "
        "against the installed library; skipped unless "
        "--third-party-compendiums is given")


def pytest_collection_modifyitems(config, items):
    opt_in = {"extensive_proofs": ("--extensive", "extensive-ladder corpus: "
                                   "run with --extensive"),
              "third_party_compendiums": (
                  "--third-party-compendiums", "adjudicates library rows "
                  "against the installed library: run with "
                  "--third-party-compendiums")}
    for marker, (option, reason) in opt_in.items():
        if config.getoption(option):
            continue
        skip = pytest.mark.skip(reason=reason)
        for item in items:
            if marker in item.keywords:
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
# the time a finite domain's whole sweep may take, by a timed estimate
# of one call (`gates._SWEEP_SECONDS` for the computation line,
# `_brute_force._SWEEP_SECONDS` for a derive brute-force proof): under
# load the estimate grows and the sweep falls back to part of the domain
_GENEROUS_SWEEP = 600


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
                            ("EXTENSIVE_TIMEOUT_SECONDS", _GENEROUS_EXTENSIVE),
                            ("_SWEEP_SECONDS", _GENEROUS_SWEEP)):
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, value, raising=False)
