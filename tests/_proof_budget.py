# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The full proof budget: every wall-clock budget mathema reads while
deciding a verdict, raised so far that the verdict reflects the
mathematics rather than how busy the machine is.

Two kinds of budget are involved:

* the proof caps, `FAST_TIMEOUT_SECONDS` and `EXTENSIVE_TIMEOUT_SECONDS`
  (`mathema._timeout`), which several engine modules copy at import
  time (`from .._timeout import FAST_TIMEOUT_SECONDS`), so each copy is
  raised too;
* the sweep budgets, `_SWEEP_SECONDS` in `mathema.gates` (the
  computation line) and `mathema._brute_force` (a derive brute-force
  proof): a finite domain is swept whole only when a timed estimate of
  a few calls says the sweep fits, so under load the estimate grows and
  the sweep falls back to part of the domain.

`tests/conftest.py` applies it to a test marked
`needs_full_proof_budget`; the docs harness (`tests/test_docs_outputs.py`)
applies it to every documented example, in the driver process and in
the `mathema` command an example runs."""
import os
import sys

GENEROUS = {"FAST_TIMEOUT_SECONDS": 60,
            "EXTENSIVE_TIMEOUT_SECONDS": 120,
            "_SWEEP_SECONDS": 600}

#: the environment variables `mathema._timeout` seeds its caps from, read
#: by a subprocess (a CLI run) when it imports mathema
ENVIRONMENT = {"MATHEMA_FAST_TIMEOUT": str(GENEROUS["FAST_TIMEOUT_SECONDS"]),
               "MATHEMA_EXTENSIVE_TIMEOUT":
                   str(GENEROUS["EXTENSIVE_TIMEOUT_SECONDS"])}

#: the modules that hold a budget, imported before raising so that a
#: copy is never taken afterwards from an unraised original
_HOLDERS = ("mathema._timeout", "mathema.gates", "mathema._brute_force",
            "mathema.symbolic._proof_support", "mathema.symbolic._extensive",
            "mathema.symbolic._strategies", "mathema.symbolic._recurrence",
            "mathema.symbolic._coupled", "mathema.symbolic._matrix",
            "mathema.symbolic._smt")


def raise_budget(setattr_=setattr, budget=None):
    """Set every budget in `budget` (default `GENEROUS`) on every loaded
    mathema module that holds one, through `setattr_(module, name,
    value)` (a pytest `monkeypatch.setattr`, to have it undone after the
    test)."""
    import importlib
    budget = GENEROUS if budget is None else budget
    for name in _HOLDERS:
        try:
            importlib.import_module(name)
        except ImportError:
            pass
    for name, mod in list(sys.modules.items()):
        if mod is None or not (name == "mathema" or name.startswith("mathema.")):
            continue
        for attr, value in budget.items():
            if attr in vars(mod):
                setattr_(mod, attr, value)


def raise_environment(env=None):
    """Put the generous caps in `env` (default `os.environ`) for any
    mathema process started from it."""
    env = os.environ if env is None else env
    env.update(ENVIRONMENT)
    return env
