# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `let p be v` naming a parameter of f pins it for every call, and the
claim is written with the pin in the call: `let alpha be 2, for x in R^n,
f(x) == 2 * x[0]` reads `for x in R^n, f(x, alpha=2) == 2 * x[0]`. The let
form is still read as input. A claim renders, parses and renders to the
same text in both spellings."""
import os

import pytest
import yaml

import mathema
from mathema.compendium import _bundled_dir
from mathema.conjecture import claim
from mathema.lexicon import LEXICON
from mathema.spec import render_claim_text


def scaled_head(x: list, alpha: float = 1.0) -> float:
    return alpha * x[0]


def _fixed_point(text: str, unicode: bool) -> None:
    once = render_claim_text(claim(text), unicode=unicode, canonical=True)
    twice = render_claim_text(claim(once), unicode=unicode, canonical=True)
    assert twice == once, (text, once, twice)


@pytest.mark.parametrize("unicode", [False, True])
def test_a_keyword_in_a_call_round_trips(unicode):
    _fixed_point("for x in R^n, f(x, alpha=2) == 2 * x[0]", unicode)


def test_the_let_pin_is_written_into_the_call():
    rec = mathema.check(scaled_head, claims=[claim(
        "let alpha be 2, for x in R^3, f(x) == 2 * x[0]", name="pinned")])
    (row,) = [p for p in rec.probes if p.name == "pinned"]
    assert "f(x, alpha=2)" in row.statement, row.statement
    assert "let alpha" not in row.statement, row.statement
    (same,) = [p for p in mathema.check(scaled_head, claims=[claim(
        "for x in R^3, f(x, alpha=2) == 2 * x[0]", name="pinned")]).probes
        if p.name == "pinned"]
    assert same.statement == row.statement
    assert same.verdict == row.verdict, (row.verdict, same.verdict, same.note)


def _bundled_rows() -> list:
    out = []
    for dirpath, _dirs, files in os.walk(_bundled_dir()):
        for name in sorted(files):
            if name.endswith(".claims.yaml"):
                with open(os.path.join(dirpath, name)) as fh:
                    data = yaml.safe_load(fh) or {}
                for key, entry in data.items():
                    if isinstance(entry, dict):
                        out += [(key, c["name"], c["statement"])
                                for c in entry.get("claims") or []]
    return out


_PINNED = [r for r in _bundled_rows() if "@" in r[1]]


@pytest.mark.parametrize("key, name, statement", _PINNED,
                         ids=[f"{k}:{n}" for k, n, _s in _PINNED])
def test_a_bundled_pinned_row_writes_its_pin_in_the_call(key, name, statement):
    for pin in name.split("@", 1)[1].split(","):
        param = pin.split("=", 1)[0]
        assert f"let {param} be" not in statement, statement


@pytest.mark.parametrize("unicode", [False, True])
@pytest.mark.parametrize("text", [s for _k, _n, s in _PINNED] + list(LEXICON.values()))
def test_every_pinned_row_and_lexicon_row_is_a_fixed_point(text, unicode):
    _fixed_point(text, unicode)
