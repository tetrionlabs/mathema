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

import mathema
from mathema.conjecture import claim
from mathema.domain import MissingDefaults, complete, parse_binding, render_domain
from mathema.lexicon import LEXICON, get
from mathema.spec import read_claims_file, render_claim_text

np = pytest.importorskip("numpy")


def both(text: str, defaults=None) -> tuple:
    """The ASCII and unicode renderings of a written domain, completed
    from `defaults` (a parameter's annotation) when given."""
    bound = parse_binding(f"x in {text}")[1]
    if defaults is not None:
        bound = complete(bound, defaults)
    return (render_domain(bound, ascii_mode=True, defaults=defaults),
            render_domain(bound, ascii_mode=False, defaults=defaults))


FLOAT = MissingDefaults(False, ("nan",), "float")
OPTIONAL = MissingDefaults(True, ("nan",), "float")
INT = MissingDefaults(False, (), "int")
ARRAY = MissingDefaults(False, ("nan",), "numpy.ndarray")
OPTIONAL_ARRAY = MissingDefaults(True, ("nan",), "numpy.ndarray")

#: annotation, written, ASCII canonical, unicode (sections 2 and 3 of the
#: model, with D4: an exclusion renders where it narrows the annotation)
TABLE = [
    (FLOAT, "[0, 1]", "[0.0, 1.0] : float|missing", "[0.0, 1.0] ⊂ ℝ ∪ {∅}"),
    (FLOAT, "[0, 1] : float", "[0.0, 1.0] \\ {missing} : float", "[0.0, 1.0] \\ {∅} ⊂ ℝ"),
    (OPTIONAL, "[0, 1]", "[0.0, 1.0] : float|absent|missing", "[0.0, 1.0] ⊂ ℝ ∪ {absent, ∅}"),
    (OPTIONAL, "[0, 1] : float|None", "[0.0, 1.0] \\ {missing} : float|absent",
     "[0.0, 1.0] \\ {∅} ⊂ ℝ ∪ {absent}"),
    (FLOAT, "[0, 1] : float|nan", "[0.0, 1.0] : float|nan", "[0.0, 1.0] ⊂ ℝ ∪ {nan}"),
    (OPTIONAL, "[0, 1] : float", "[0.0, 1.0] \\ {absent, missing} : float",
     "[0.0, 1.0] \\ {absent, ∅} ⊂ ℝ"),
    (FLOAT, "[0, 1] | {5}", "[0.0, 1.0] | {5} : float|missing", "[0.0, 1.0] ∪ {5} ⊂ ℝ ∪ {∅}"),
    (FLOAT, "R", "R|missing", "ℝ ∪ {∅}"),
    (OPTIONAL, "R", "R|absent|missing", "ℝ ∪ {absent, ∅}"),
    (INT, "[0, 1] subset Z", "[0, 1] : int", "[0, 1] ⊂ ℤ"),
    (INT, "N|None", "N|absent", "ℕ ∪ {absent}"),
    (INT, "Z", "Z", "ℤ"),
    (FLOAT, "{0.25, None}", "{0.25, absent}", "{0.25, absent}"),
    (FLOAT, "{0.25, nan}", "{0.25, nan}", "{0.25, nan}"),
    (FLOAT, "{missing}", "{missing}", "{∅}"),
    (FLOAT, "{None}", "{absent}", "{absent}"),
    (ARRAY, "[0, 1]^n", "([0.0, 1.0] | {missing})^n : float", "([0.0, 1.0] ∪ {∅})ⁿ ⊂ ℝ"),
    (ARRAY, "[0, 1]^n \\ {missing}", "[0.0, 1.0]^n \\ {missing} : float",
     "[0.0, 1.0]ⁿ \\ {∅} ⊂ ℝ"),
    (ARRAY, "([0, 1] | {nan})^n", "([0.0, 1.0] | {nan})^n : float", "([0.0, 1.0] ∪ {nan})ⁿ ⊂ ℝ"),
    (ARRAY, "([0, 1] | {None})^n", "([0.0, 1.0] | {null})^n : float",
     "([0.0, 1.0] ∪ {null})ⁿ ⊂ ℝ"),
    (OPTIONAL_ARRAY, "[0, 1]^n", "([0.0, 1.0] | {missing})^n : float|absent",
     "([0.0, 1.0] ∪ {∅})ⁿ ⊂ ℝ ∪ {absent}"),
    (ARRAY, "R^(n,n)", "(R | {missing})^(n,n)", "(ℝ ∪ {∅})ⁿˣⁿ"),
    (ARRAY, "R^(n,n) \\ {missing}", "R^(n,n) \\ {missing}", "ℝⁿˣⁿ \\ {∅}"),
]

#: written, ASCII, unicode with no function: the default of no annotation
UNANNOTATED = [
    ("[0, 1]", "[0.0, 1.0] : float|absent|missing", "[0.0, 1.0] ⊂ ℝ ∪ {absent, ∅}"),
    ("[0, 1] : float", "[0.0, 1.0] \\ {absent, missing} : float", "[0.0, 1.0] \\ {absent, ∅} ⊂ ℝ"),
    ("R", "R|absent|missing", "ℝ ∪ {absent, ∅}"),
    ("R^n", "(R | {missing})^n|absent", "(ℝ ∪ {∅})ⁿ ∪ {absent}"),
    ("[1, 5] subset Z", "[1, 5] \\ {absent, missing} : int", "[1, 5] \\ {absent, ∅} ⊂ ℤ"),
]


@pytest.mark.parametrize("defaults, written, ascii_text, unicode_text", TABLE)
def test_the_rendering_states_what_the_domain_admits(defaults, written, ascii_text,
                                                    unicode_text):
    assert both(written, defaults) == (ascii_text, unicode_text)


@pytest.mark.parametrize("defaults, written, ascii_text, unicode_text", TABLE)
def test_each_rendering_parses_back_to_itself_given_the_same_function(
        defaults, written, ascii_text, unicode_text):
    assert both(ascii_text, defaults) == (ascii_text, unicode_text)
    assert both(unicode_text, defaults) == (ascii_text, unicode_text)


@pytest.mark.parametrize("written, ascii_text, unicode_text", UNANNOTATED)
def test_without_a_function_the_default_of_no_annotation_applies(
        written, ascii_text, unicode_text):
    assert both(written) == (ascii_text, unicode_text)
    assert both(ascii_text) == (ascii_text, unicode_text)
    assert both(unicode_text) == (ascii_text, unicode_text)


def gram_trace(A: "np.ndarray") -> float:
    return float(np.trace(A @ A.T))


@pytest.mark.parametrize("written, statement", [
    ("R^(n,n)", "for A in (R | {missing})^(n,n), f(A) >= 0"),
    ("R^(n,n) \\ {missing}", "for A in R^(n,n) \\ {missing}, f(A) >= 0"),
])
def test_a_named_space_on_an_ndarray_is_completed_and_reads_back(written, statement):
    first = _record(gram_trace, f"for A in {written}, f(A) >= 0")
    assert first == statement
    assert _record(gram_trace, first) == statement


def _record(fn, text: str) -> str:
    report = mathema.check(fn, claims=[claim(text, name="c", route="derive:math_only")])
    return next(p for p in report.probes if p.name == "c").statement


def test_a_language_spells_the_words_in_both_modes():
    assert both("L[unicode]|None") == ("L[unicode]|None", "L[unicode]|None")
    assert both("L[unicode]") == ("L[unicode]", "L[unicode]")


def test_an_excluded_sentinel_renders_only_where_it_narrows_the_annotation():
    assert both("[-1, 1] \\ {1, missing} : float|absent", OPTIONAL) == (
        "[-1.0, 1.0] \\ {1, missing} : float|absent",
        "[-1.0, 1.0] \\ {1, ∅} ⊂ ℝ ∪ {absent}")
    assert both("[-1, 1] \\ {1, missing} : float|absent", OptionalInt) == (
        "[-1.0, 1.0] \\ {1} : float|absent", "[-1.0, 1.0] \\ {1} ⊂ ℝ ∪ {absent}")


OptionalInt = MissingDefaults(True, (), "int")


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


@pytest.mark.parametrize("defaults, written, ascii_text, unicode_text", TABLE)
def test_every_table_row_is_a_fixed_point_as_a_claim(defaults, written, ascii_text,
                                                    unicode_text):
    _fixed_point(f"for x in {written}, f(x) >= 0")


def test_a_bundled_definition_row_states_nothing_missing_without_an_exclusion():
    statements = [s for _key, s in _bundled_statements()]
    assert statements
    assert not any("{∅}" in s or "\\ {missing}" in s for s in statements)
