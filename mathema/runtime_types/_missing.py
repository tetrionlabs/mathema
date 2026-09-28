# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Which missing values a slot type has: the members the hole class
stands for, and the spellings of the object's absence.

`missing` in claim text always names the class; the class is resolved
per slot type. A Python scalar slot takes its members from the scalar
runtime's table (`float` holds `nan`, a datetime `NaT`, an `int`, a
`bool` or a `str` nothing); a runtime type takes the spellings its
adapter draws by default (`list`: `null`, `nan`; `numpy.ndarray`:
`nan`; `pandas.Series`: `nan`, `null`, `NA`; `polars.Series`: `null`,
`nan`). A definition row in a claims file then extends or overrides a
key's members, read in layers: the bundled compendium files, a
project's compendium files, then a project's ordinary claims files, a
later layer applying after an earlier one.

A definition row is `<word> := {<members>}`, with the word `missing`
(the hole class) or `None` (the object's absence). A plain set replaces
what the key had; the word itself inside the set extends it
(`missing := {missing, NaT}` adds `NaT`).
"""
from __future__ import annotations

from dataclasses import dataclass

#: the hole members of each Python scalar slot type
SCALAR_MEMBERS = {
    "float": ("nan",),
    "complex": ("nan",),
    "datetime": ("NaT",),
    "int": (),
    "bool": (),
    "str": (),
    "object": (),
}

#: the definition layers, in the order they apply
LAYERS = ("bundled", "compendium", "claims")


@dataclass(frozen=True)
class Definition:
    """One definition row: the key it is stated under, its word
    (`missing` or `None`), the members its set names (the word itself
    left out), whether the set extends what the key had (the word
    appears inside it), the text as written, and where it came from."""
    key: str
    word: str
    members: tuple
    extends: bool
    text: str
    source: str


_DEFINITIONS: dict = {layer: () for layer in LAYERS}


def set_definitions(layer: str, rows) -> None:
    """Replace the definitions of `layer` with `rows`, and register each
    member spelling a row's adapter realises so claim text reads it and
    the sampler can build its value."""
    if layer not in LAYERS:
        raise ValueError(f"unknown definition layer {layer!r}; one of {LAYERS}")
    _DEFINITIONS[layer] = tuple(rows)
    from ..domain import register_absence_spelling, register_spelling
    from . import adapter as _adapter
    for row in rows:
        found = _adapter(row.key)
        table = spellings(found) if found is not None else {}
        for word in row.members:
            realise = table.get(word, (None, None))[0]
            if realise is None:
                continue
            if row.word == "None":
                register_absence_spelling(word, realise)
            else:
                register_spelling(word, realise)


def definitions(layers: tuple = LAYERS) -> tuple:
    """Every definition row in force in `layers`, layer by layer."""
    return tuple(row for layer in LAYERS if layer in layers
                 for row in _DEFINITIONS[layer])


def spellings(found) -> dict:
    """An adapter's spellings, `{word: (realise, detect)}`: the values it
    can hold a missing value as, and how each is recognised."""
    return dict(getattr(found, "SPELLINGS", None) or {})


def _built_in(slot_type: str, word: str) -> tuple:
    if slot_type in SCALAR_MEMBERS:
        return ("None",) if word == "None" else SCALAR_MEMBERS[slot_type]
    from . import adapter as _adapter
    found = _adapter(slot_type)
    if found is None:
        return ()
    attribute = "ABSENCE" if word == "None" else "MISSING_MEMBERS"
    return tuple(getattr(found, attribute, ()) or ())


def members(slot_type: str, word: str = "missing") -> tuple:
    """Intent:
        The spellings `word` stands for on a slot of `slot_type`: for
        `missing` the hole members, for `None` the absence spellings.
        The built-ins first (the scalar runtime's table, else the
        adapter's default spellings), then each definition row keyed
        `slot_type`, a plain set replacing and a set holding the word
        extending.
    """
    out = list(_built_in(slot_type, word))
    for row in definitions():
        if row.key != slot_type or row.word != word:
            continue
        out = (out + [m for m in row.members if m not in out]
               if row.extends else list(row.members))
    seen: list = []
    for m in out:
        if m not in seen:
            seen.append(m)
    return tuple(seen)


def resolve_missing(slot_type: str) -> tuple:
    """The members the hole class stands for on a slot of `slot_type`
    (`("nan",)` for `float`, `()` for `str`)."""
    return members(slot_type, "missing")


def resolve_absence(slot_type: str) -> tuple:
    """The spellings of absence a slot of `slot_type` has by definition
    row (`("Option::None",)`), the built-in `None` for a Python scalar,
    else none."""
    return members(slot_type, "None")


def absence_defined(slot_type: str) -> bool:
    """Whether a definition row states an absence for `slot_type`, which
    makes the absence of an object of that type admitted by default."""
    return any(row.key == slot_type and row.word == "None"
               for row in definitions())
