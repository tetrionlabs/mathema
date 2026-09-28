# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A rendered domain states what it admits and never what it excludes:
the absence of the object as `None`, a hole in a slot as `missing` (`∅`
in unicode) or a member word, in the order `None`, `missing`, members.
ASCII fuses them onto the type clause, unicode writes a union; a space
puts its slot's holes in brackets before the power. Every claim text is
a fixed point: rendering, parsing and rendering again gives the same
bytes, in both modes."""
import os

import pytest

from mathema.conjecture import claim
from mathema.domain import parse_binding, render_domain
from mathema.lexicon import LEXICON, get
from mathema.spec import read_claims_file, render_claim_text


def both(text: str) -> tuple:
    bound = parse_binding(f"x in {text}")[1]
    return render_domain(bound, ascii_mode=True), render_domain(bound, ascii_mode=False)


#: written, ASCII canonical, unicode (section 2 of the model)
SCALAR_TABLE = [
    ("[0, 1] : float", "[0.0, 1.0] : float", "[0.0, 1.0] ⊂ ℝ"),
    ("[0, 1] : float|None", "[0.0, 1.0] : float|None", "[0.0, 1.0] ⊂ ℝ ∪ {None}"),
    ("[0, 1] : float|missing", "[0.0, 1.0] : float|missing", "[0.0, 1.0] ⊂ ℝ ∪ {∅}"),
    ("[0, 1] : float|nan", "[0.0, 1.0] : float|nan", "[0.0, 1.0] ⊂ ℝ ∪ {nan}"),
    ("[0, 1] : float|None|missing", "[0.0, 1.0] : float|None|missing",
     "[0.0, 1.0] ⊂ ℝ ∪ {None, ∅}"),
    ("[0, 1] | {5} : float|missing", "[0.0, 1.0] | {5} : float|missing",
     "[0.0, 1.0] ∪ {5} ⊂ ℝ ∪ {∅}"),
    ("R", "R", "ℝ"),
    ("R|None|missing", "R|None|missing", "ℝ ∪ {None, ∅}"),
    ("N|None", "N|None", "ℕ ∪ {None}"),
    ("{0.25, None}", "{0.25, None}", "{0.25, None}"),
    ("{0.25, nan}", "{0.25, nan}", "{0.25, nan}"),
    ("{missing}", "{missing}", "{∅}"),
    ("{None}", "{None}", "{None}"),
]

#: written, ASCII canonical, unicode (section 3 of the model)
SPACE_TABLE = [
    ("([0, 1] | {missing})^n : float", "([0.0, 1.0] | {missing})^n : float",
     "([0.0, 1.0] ∪ {∅})ⁿ ⊂ ℝ"),
    ("[0, 1]^n : float", "[0.0, 1.0]^n : float", "[0.0, 1.0]ⁿ ⊂ ℝ"),
    ("([0, 1] | {nan})^n : float", "([0.0, 1.0] | {nan})^n : float",
     "([0.0, 1.0] ∪ {nan})ⁿ ⊂ ℝ"),
    ("([0, 1] | {None})^n : float", "([0.0, 1.0] | {null})^n : float",
     "([0.0, 1.0] ∪ {null})ⁿ ⊂ ℝ"),
    ("([0, 1] | {missing})^n : float|None", "([0.0, 1.0] | {missing})^n : float|None",
     "([0.0, 1.0] ∪ {∅})ⁿ ⊂ ℝ ∪ {None}"),
    ("(R | {missing})^(n,n)", "(R | {missing})^(n,n)", "(ℝ ∪ {∅})ⁿˣⁿ"),
    ("R^(n,n)", "R^(n,n)", "ℝⁿˣⁿ"),
    ("R^n \\ {missing}", "R^n", "ℝⁿ"),
]


@pytest.mark.parametrize("written, ascii_text, unicode_text", SCALAR_TABLE + SPACE_TABLE)
def test_the_rendering_states_what_the_domain_admits(written, ascii_text, unicode_text):
    assert both(written) == (ascii_text, unicode_text)


@pytest.mark.parametrize("written, ascii_text, unicode_text", SCALAR_TABLE + SPACE_TABLE)
def test_each_rendering_parses_back_to_itself(written, ascii_text, unicode_text):
    assert both(ascii_text) == (ascii_text, unicode_text)
    assert both(unicode_text) == (ascii_text, unicode_text)


def test_an_unstated_binding_renders_the_default_of_no_annotation():
    assert both("[0, 1]") == ("[0.0, 1.0] : float|None|missing",
                              "[0.0, 1.0] ⊂ ℝ ∪ {None, ∅}")


def test_a_language_spells_the_words_in_both_modes():
    assert both("L[unicode]|None") == ("L[unicode]|None", "L[unicode]|None")
    assert both("L[unicode]") == ("L[unicode]", "L[unicode]")


def test_an_excluded_value_renders_and_an_excluded_sentinel_does_not():
    assert both("[-1, 1] \\ {1, missing} : float|None") == (
        "[-1.0, 1.0] \\ {1} : float|None", "[-1.0, 1.0] \\ {1} ⊂ ℝ ∪ {None}")


def test_the_raises_exception_is_never_read_as_a_parameter():
    cj = claim("for x in {missing}, raises(f(x), ValueError)")
    assert render_claim_text(cj, unicode=True) == "∀ x ∈ {∅}, raises(f(x), ValueError)"
    assert render_claim_text(cj, unicode=False) == \
        "for x in {missing}, raises(f(x), ValueError)"


def _fixed_point(text: str) -> None:
    for unicode in (False, True):
        once = render_claim_text(claim(text), unicode=unicode)
        assert render_claim_text(claim(once), unicode=unicode) == once, (text, once)


@pytest.mark.parametrize("key", list(LEXICON))
def test_every_lexicon_entry_is_a_fixed_point(key):
    _fixed_point(get(key))


def _bundled_statements() -> list:
    root = os.path.join(os.path.dirname(__file__), "..", "mathema", "compendium")
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith(".claims.yaml"):
                continue
            path = os.path.join(dirpath, name)
            data = read_claims_file(path, name) or {}
            for key, entry in data.items():
                if isinstance(entry, dict):
                    out += [(key, c["statement"]) for c in entry.get("claims") or []]
    return out


@pytest.mark.parametrize("key, statement", _bundled_statements())
def test_every_bundled_row_is_a_fixed_point(key, statement):
    _fixed_point(statement)


@pytest.mark.parametrize("written, ascii_text, unicode_text", SCALAR_TABLE + SPACE_TABLE)
def test_every_table_row_is_a_fixed_point_as_a_claim(written, ascii_text, unicode_text):
    _fixed_point(f"for x in {written}, f(x) >= 0")


def test_a_bundled_definition_row_states_nothing_missing_without_an_exclusion():
    statements = [s for _key, s in _bundled_statements()]
    assert statements
    assert not any("{∅}" in s or "\\ {missing}" in s for s in statements)
