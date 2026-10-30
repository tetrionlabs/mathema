# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Number representations: what a mathematical set is represented AS.

A claim quantifies over a mathematical set (`Z`, `R`); an implementation
computes over a number representation (`bigint`, `f64`, an `i64`). The two
agree on most points and part company exactly where implementation-level
falsifications live: an overflow threshold, a denormal band, an integer
that wraps. This module names number representations and the facts that
differ between them, so evidence about the machine can say which machine.

`PROFILES` holds one profile per representation word the claim grammar
reserves (`i8` to `i128`, `u8` to `u128`, `f16`, `f32`, `f64`, `bigint`,
`f64int`), and `profile(tag)` returns one. A hazard ladder is a property
of a NUMBER REPRESENTATION (an IEEE-754 double is the same number
representation in every language), not of a language, so a target
declares its number representations and inherits their hazards, and
only the native-type-to-representation mapping is per-language. A KOINE
parameter line names its representation (`representation::i64`), and
the extreme hazard points of that parameter come from the named
profile's ladder (`hazards._extreme_hazard_points`).

A profile's `overflow` is the representation's own arithmetic at
overflow (an `i64` wraps modulo 2**64). How a particular function shows
an overflow is a property of the runtime and its build mode, stated by
the body's `manifest` line for `nonvalue::machine::overflow` and read
by `overflow_semantics`.

Overflow semantics vocabulary: `arbitrary` (the number representation
grows, overflow cannot happen), `inf` (IEEE saturation to an infinity),
`wrap` (wraparound modulo 2**bits, a WRONG VALUE and no failure at
the call boundary), `trap` (a raise/panic at the point of overflow),
`ub` (undefined behaviour: anything, including silence). A wrapped or
undefined result is only detectable against exact arithmetic, which
is why implementation blame under those semantics needs the
mathematical stratum alongside.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

from ._representation_words import NUMBER_REPRESENTATIONS
from .claim_families import _ACCIDENTAL_CRASHES
from .hazards import _REPRESENTATION_LADDER

__all__ = ["PROFILES", "PY_COMPLEX128", "PY_FLOAT64", "PY_INT", "PYTHON_PROFILES",
           "Representation", "machine_failure_types", "overflow_semantics",
           "parameter_profile", "profile"]


@dataclass(frozen=True)
class Representation:
    """One number representation: its tag, how its arithmetic overflows,
    the hazard ladder worth probing on it, the exception types that
    signal the MACHINE failing (as opposed to a value-level rejection
    like ValueError, which is the mathematics or the contract talking),
    and the largest finite magnitude it represents (None for a number
    representation that grows without bound). The maximum is how far a
    computation over the number representation can reach along an
    unbounded direction.

    `ladder` is the signed input values where the representation's
    behaviour changes character; a probe along an unbounded positive
    direction visits its non-negative rungs, along an unbounded negative
    direction its non-positive ones. `min_value` and `max_value` are the
    most negative and most positive finite values (None when unbounded),
    `integral` says the representation holds integers only, and
    `unit_roundoff` is the relative rounding error of one operation
    (2**-53 for float64, 0 for exact integers, None when not stated)."""
    tag: str
    overflow: str                       # arbitrary | inf | wrap | trap | ub
    ladder: tuple = ()
    machine_failures: tuple = field(default=())
    max_magnitude: "float | None" = None
    min_value: "float | None" = None
    max_value: "float | None" = None
    integral: bool = False
    unit_roundoff: "float | None" = None


def _mirrored(magnitudes: tuple) -> tuple:
    """The rungs `magnitudes` on both sides of zero, positive first."""
    return tuple(magnitudes) + tuple(-v for v in magnitudes)


#: Python's float: an IEEE-754 double. Overflow raises OverflowError
#: from some operations (math.exp) and saturates to inf from others
#: (multiplication), so both spellings appear in evidence; the ladder
#: is the float64 one hazards.py already probes, on both signs.
PY_FLOAT64 = Representation(
    tag="f64",
    overflow="inf",
    ladder=_mirrored(_REPRESENTATION_LADDER),
    machine_failures=(OverflowError, MemoryError, RecursionError),
    max_magnitude=sys.float_info.max,
    min_value=-sys.float_info.max,
    max_value=sys.float_info.max,
    unit_roundoff=2.0**-53,
)

#: Python's complex (numpy's complex128): a pair of IEEE-754 doubles,
#: the real and the imaginary part. Each part overflows as a float64
#: does, so the largest finite magnitude is float64's, per component.
PY_COMPLEX128 = Representation(
    tag="c128",
    overflow="inf",
    ladder=_mirrored(_REPRESENTATION_LADDER),
    machine_failures=(OverflowError, MemoryError, RecursionError),
    max_magnitude=sys.float_info.max,
    unit_roundoff=2.0**-53,
)

#: Python's int: arbitrary precision. Overflow cannot happen; the
#: machine failures it can still exhibit are resource exhaustion.
PY_INT = Representation(
    tag="bigint",
    overflow="arbitrary",
    machine_failures=(MemoryError, RecursionError),
    max_magnitude=None,
    integral=True,
    unit_roundoff=0.0,
)

#: The profiles the Python runtime supplies, by the param kinds the
#: analysis vocabulary uses.
PYTHON_PROFILES: dict[str, Representation] = {
    "scalar": PY_FLOAT64,
    "complex": PY_COMPLEX128,
    "int": PY_INT,
}


def _fixed_width(tag: str, bits: int, signed: bool) -> Representation:
    """Intent:
        The profile of a fixed-width integer of `bits` bits: its range
        ends, and a ladder of those ends with -1 (when signed), 0 and 1.
        Its arithmetic wraps modulo 2**bits at overflow.
    """
    lo = -2**(bits - 1) if signed else 0
    hi = 2**(bits - 1) - 1 if signed else 2**bits - 1
    ladder = (hi, 1, 0, -1, lo) if signed else (hi, 1, 0)
    return Representation(tag=tag, overflow="wrap", ladder=ladder,
                          max_magnitude=max(abs(lo), hi), min_value=lo, max_value=hi,
                          integral=True, unit_roundoff=0.0)


def _binary_float(tag: str, largest: float, square_root: float, exp_overflow: float,
                  below_normal: float, smallest: float, unit_roundoff: float) -> Representation:
    """Intent:
        The profile of an IEEE-754 binary format whose largest finite
        value is `largest`: a ladder of that maximum, a magnitude whose
        square overflows (`square_root`), the smallest whole number whose
        exponential overflows (`exp_overflow`), a magnitude in the
        subnormal band (`below_normal`) and the smallest subnormal, on
        both signs. Its arithmetic saturates to an infinity at overflow.
    """
    return Representation(
        tag=tag, overflow="inf",
        ladder=_mirrored((largest, square_root, exp_overflow, below_normal, smallest)),
        max_magnitude=largest, min_value=-largest, max_value=largest,
        unit_roundoff=unit_roundoff)


#: The largest integer a float64 holds with every smaller integer also
#: held exactly; 2**53 + 1 is the first integer it cannot hold.
_F64_EXACT = 2**53

#: Integers carried in a float64 (a JavaScript number used as an
#: integer): exact up to 2**53, rounding past it, an infinity past
#: float64's maximum. The ladder is the exactness cliff on both signs,
#: float64's maximum, and -1, 0, 1.
F64INT = Representation(
    tag="f64int",
    overflow="inf",
    ladder=(int(sys.float_info.max), _F64_EXACT, _F64_EXACT - 1, 1, 0, -1,
            -(_F64_EXACT - 1), -_F64_EXACT, -int(sys.float_info.max)),
    max_magnitude=sys.float_info.max,
    min_value=-int(sys.float_info.max),
    max_value=int(sys.float_info.max),
    integral=True,
)

#: The profiles of the reserved words that are not fixed-width integers.
_NAMED_PROFILES: dict[str, Representation] = {
    "f16": _binary_float("f16", 65504.0, 256.0, 12.0, 1e-5, 2.0**-24, 2.0**-11),
    "f32": _binary_float("f32", 3.4028234663852886e38, 2.0**64, 89.0, 1e-38, 2.0**-149,
                         2.0**-24),
    "f64": PY_FLOAT64,
    "bigint": PY_INT,
    "f64int": F64INT,
}


def _reserved_profile(tag: str) -> Representation:
    """Intent:
        The profile of the reserved representation word `tag`: a
        fixed-width integer for `i<bits>` and `u<bits>`, else the
        named profile.

    Raises:
        KeyError: `tag` is neither a fixed-width integer word nor named.
    """
    if tag[:1] in ("i", "u") and tag[1:].isdigit():
        return _fixed_width(tag, int(tag[1:]), signed=tag[0] == "i")
    return _NAMED_PROFILES[tag]


#: One profile per representation word the claim grammar reserves,
#: by tag, read from the one table of representation words.
PROFILES: dict[str, Representation] = {
    tag: _reserved_profile(tag) for tag in NUMBER_REPRESENTATIONS}


def profile(tag: str) -> Representation:
    """Intent:
        The profile of the number representation named `tag` (`i64`,
        `f32`, `bigint`, any word of `PROFILES`).

    Raises:
        KeyError: `tag` names no profile; the message lists the words
            that do.
    """
    try:
        return PROFILES[tag]
    except KeyError:
        raise KeyError(f"no number representation is named {tag!r}; the "
                       f"representations are {', '.join(sorted(PROFILES))}") from None


def parameter_profile(document, param: str) -> "Representation | None":
    """Intent:
        The profile of the number representation KOINE `document`'s
        parameter line for `param` names (`representation::i64` gives
        `profile("i64")`); None when there is no such line, it names no
        representation, or the representation has no profile.
    """
    from .koine.syntax import Name, Term
    for line in document.parameters:
        if line.args and isinstance(line.args[0], Name) and line.args[0].id == param:
            named = line.args[2] if len(line.args) > 2 else None
            if isinstance(named, Term) and named.head.startswith("representation::"):
                return PROFILES.get(named.head.rpartition("::")[2])
            return None
    return None


#: the module's overflow word for each way a manifest says a runtime
#: shows an overflow
_MANIFESTED_OVERFLOW = {
    "as::raise": "trap",
    "as::panic": "trap",
    "as::trap": "trap",
    "as::undefined": "ub",
    "as::nonfinite": "inf",
}


def overflow_semantics(document, param: str, operation: "str | None" = None) -> "str | None":
    """Intent:
        How an overflow of `param`'s representation shows in the
        function KOINE `document` describes, in this module's overflow
        vocabulary: `arbitrary` when the parameter's representation
        cannot overflow; otherwise the word for the document's
        `manifest` line for `nonvalue::machine::overflow` (the line
        naming `operation` when there is one, else the class line):
        `trap` for `as::raise`, `as::panic` and `as::trap`, `ub` for
        `as::undefined`, `inf` for `as::nonfinite`. None when the
        document does not say, or says it some other way.

    Notes:
        A manifest line has no spelling for a wrapped value, so `wrap`
        is never returned.
    """
    from .koine.interpret import OVERFLOW
    named = parameter_profile(document, param)
    if named is not None and named.overflow == "arbitrary":
        return "arbitrary"
    shown = document.manifestation(OVERFLOW, operation)
    return _MANIFESTED_OVERFLOW.get(shown.head) if shown is not None else None


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
    for rep in PYTHON_PROFILES.values():
        for exc in rep.machine_failures:
            if exc not in kinds:
                kinds.append(exc)
    assert set(kinds) <= set(_ACCIDENTAL_CRASHES) | {MemoryError}
    return tuple(kinds)
