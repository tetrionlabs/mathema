# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bundled definition row is an axiom only from the supported floor
up.

mathema supports numpy from 2.0, pandas from 2.2 and polars from 1.0.
A bundled file may state a wider range (`numpy >=1.24`); between the
file's own start and the floor a row is evidence, so a proof through it
is `holds` and its sketch says the installed library is below the
floor. From the floor up the row is an axiom, and its sketch names the
range from the floor ("numpy 2.0 to 2.x").
"""
from __future__ import annotations

import numpy as np
import pytest

from mathema import compendium, definitions
from mathema.claims import check_conjectures, claim

_SCALE = ("let s = mathema.f.scale_seq, let c be [0.1, 10], "
          "for x in [-1, 1]^n, f(s(x, c)) ~= c * f(x)")


def total(x: np.ndarray) -> float:
    """The sum of the elements."""
    return float(np.sum(x))


def _check():
    compendium.uninstall()
    definitions._LIBRARY_CACHE.clear()
    try:
        (p,) = check_conjectures(total, [claim(_SCALE, route="derive")])
    finally:
        definitions._LIBRARY_CACHE.clear()
        compendium.uninstall()
    return p


def test_the_supported_floors_are_one_table():
    assert compendium.SUPPORTED_FLOORS == {
        "numpy": "2.0", "pandas": "2.2", "polars": "1.0"}


@pytest.mark.needs_full_proof_budget
def test_from_the_floor_up_the_row_is_an_axiom_named_from_the_floor():
    p = _check()
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "(axiom, bundled with mathema, numpy 2.0 to 2.x)" in \
        (p.sketch or ""), p.sketch


@pytest.mark.needs_full_proof_budget
def test_below_the_floor_the_row_is_evidence(monkeypatch):
    real = compendium._installed_version
    monkeypatch.setattr(
        compendium, "_installed_version",
        lambda lib, aliases=(): "1.26.4" if lib == "numpy"
        else real(lib, aliases))
    p = _check()
    assert p.verdict == "holds", (p.verdict, p.sketch)
    used = {u["key"]: u for u in p.meta["mathema.definitions"]}
    assert used["numpy.sum"]["standing"] == "evidence"
    assert "numpy 1.26.4 is below the supported floor 2.0" in \
        (p.sketch or ""), p.sketch
