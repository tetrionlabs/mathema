# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Machine carriers: what a mathematical set is represented AS.

A claim quantifies over a mathematical set (`Z`, `R`); an
implementation computes over a carrier (`bigint`, `f64`, an `i64`).
The two agree on most points and part company exactly where
implementation-level falsifications live: an overflow threshold, a
denormal band, an integer that wraps. This module names carriers and
the facts that differ between them, so evidence about the machine can
say which machine.

Two profiles exist today, Python's own. The vocabulary is the point:
a hazard ladder is a property of a CARRIER (an IEEE-754 double is the
same carrier in every language), not of a language, so a future
target declares its carriers and inherits their hazards, and only the
native-type-to-carrier mapping is per-language. The `let Z be i64`
claim-level declaration and carrier-driven hazard generation build on
this vocabulary; neither is wired yet.

Overflow semantics vocabulary: `arbitrary` (the carrier grows,
overflow cannot happen), `inf` (IEEE saturation to an infinity),
`wrap` (two's-complement wraparound, a WRONG VALUE and no failure at
the call boundary), `trap` (a raise/panic at the point of overflow),
`ub` (undefined behaviour: anything, including silence). A wrapped or
undefined result is only detectable against exact arithmetic, which
is why implementation blame under those semantics needs the
mathematical stratum alongside.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .claim_families import _ACCIDENTAL_CRASHES
from .hazards import _REPRESENTATION_LADDER

__all__ = ["PY_FLOAT64", "PY_INT", "PYTHON_PROFILES", "Representation",
           "machine_failure_types"]


@dataclass(frozen=True)
class Representation:
    """One carrier: its tag, how it overflows, the hazard ladder worth
    probing on it, and the exception types that signal the MACHINE
    failing (as opposed to a value-level rejection like ValueError,
    which is the mathematics or the contract talking)."""
    tag: str
    overflow: str                       # arbitrary | inf | wrap | trap | ub
    ladder: tuple = ()
    machine_failures: tuple = field(default=())


#: Python's float: an IEEE-754 double. Overflow raises OverflowError
#: from some operations (math.exp) and saturates to inf from others
#: (multiplication), so both spellings appear in evidence; the ladder
#: is the float64 one hazards.py already probes.
PY_FLOAT64 = Representation(
    tag="f64",
    overflow="inf",
    ladder=tuple(_REPRESENTATION_LADDER),
    machine_failures=(OverflowError, MemoryError, RecursionError),
)

#: Python's int: arbitrary precision. Overflow cannot happen; the
#: machine failures it can still exhibit are resource exhaustion.
PY_INT = Representation(
    tag="bigint",
    overflow="arbitrary",
    machine_failures=(MemoryError, RecursionError),
)

#: The profiles the Python runtime supplies, by the param kinds the
#: analysis vocabulary uses.
PYTHON_PROFILES: dict[str, Representation] = {
    "scalar": PY_FLOAT64,
    "int": PY_INT,
}


def machine_failure_types() -> tuple:
    """Intent:
        Every exception type that signals the MACHINE failing under
        Python's profiles, for the falsification classifier: a raise
        of one of these pins implementation blame; any other raise
        says nothing about the stratum on its own.

    Notes:
        Deliberately narrower than `_ACCIDENTAL_CRASHES` (the fuzz
        family's crash-versus-rejection taxonomy, which includes
        TypeError/KeyError/IndexError): a TypeError is a contract
        violation, not the machine running out of anything. The two
        vocabularies share members (RecursionError, OverflowError)
        and answer different questions; both are referenced here so
        the relationship is stated once.
    """
    kinds: list = []
    for profile in PYTHON_PROFILES.values():
        for exc in profile.machine_failures:
            if exc not in kinds:
                kinds.append(exc)
    assert set(kinds) <= set(_ACCIDENTAL_CRASHES) | {MemoryError}
    return tuple(kinds)
