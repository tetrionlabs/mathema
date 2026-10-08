# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A lexicon row with an example function renders and round-trips as
that function completes it: `for n in N` against `n: int` is plain
`N`, since an int holds no hole and the parameter is always passed, so
the canonical form reaches the row's own verdict and the golden shows
`N` with no suffix. A row without an example function still renders
the unannotated default."""
from types import SimpleNamespace

import pytest

import mathema.lexicon as lexicon
from mathema import lexicon_checks
from mathema.languages import (StringLanguage, register_language,
                               unregister_language)
from mathema.lexicon import LexiconSource


def render_count(n: int) -> str:
    """The count as decimal digits."""
    return str(n)


ROWS = {"count_digits": "for n in N, f(n) in L[digit]",
        "count_unannotated": "for n in N, f(n) >= 0"}
DEMO = SimpleNamespace(
    LEXICON=ROWS,
    SECTIONS={"counts": tuple(ROWS)},
    TAGS={},
    EXAMPLE_FUNCTIONS={"render_count": (render_count, ["count_digits"])},
)
#: the row with its example function alone, a lexicon every check passes
SRC = LexiconSource("demo", {"count_digits": ROWS["count_digits"]},
                    {"counts": ("count_digits",)}, {}, DEMO.EXAMPLE_FUNCTIONS)


@pytest.fixture
def digit_language():
    register_language("digit", StringLanguage("digit", char_ok=str.isdigit,
                                              pool="0123456789"))
    try:
        yield
    finally:
        unregister_language("digit")


class _Entry:
    def __init__(self, name, obj):
        self.name, self.value, self._obj = name, f"pkg:{name}", obj

    def load(self):
        return self._obj


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setattr(lexicon, "_entry_points", lambda: (_Entry("demo", DEMO),))
    lexicon._extensions.cache_clear()
    yield
    lexicon._extensions.cache_clear()


def test_the_canonical_form_reaches_the_rows_verdict(digit_language):
    assert lexicon_checks.check_same_verdict(SRC) == []


def test_the_golden_renders_the_parameter_as_the_function_takes_it(
        digit_language, tmp_path):
    rendered = lexicon_checks.rendered(LexiconSource(
        "demo", ROWS, DEMO.SECTIONS, {}, DEMO.EXAMPLE_FUNCTIONS))
    assert rendered["count_digits"]["ascii"] == "for n in N, f(n) in L[digit]"
    assert rendered["count_digits"]["unicode"] == "∀ n ∈ ℕ, f(n) ∈ L[digit]"
    assert rendered["count_unannotated"]["ascii"] == \
        "for n in N|absent|missing, f(n) >= 0"
    golden = str(tmp_path / "golden.json")
    lexicon_checks.write_golden(SRC, golden)
    assert lexicon_checks.lexicon_problems(
        SRC, golden=golden, expected={"count_digits": "holds"}) == {}


def test_render_both_shows_the_row_as_its_example_function_takes_it(
        digit_language, registered):
    text, unicode_form, ascii_form = lexicon.render_both("count_digits")
    assert (text, ascii_form) == (ROWS["count_digits"], "for n in N, f(n) in L[digit]")
    assert unicode_form == "∀ n ∈ ℕ, f(n) ∈ L[digit]"
    *_, plain = lexicon.render_both("count_unannotated")
    assert plain == "for n in N|absent|missing, f(n) >= 0"
