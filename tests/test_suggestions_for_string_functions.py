# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What core suggests for a function over strings, with no language
package: the arbitrary-input family for each string parameter and the
purity claims, never numeric stability, which reads a finite number
where a string function has none."""
import textwrap

import pytest

from mathema import suggest_claims


@pytest.fixture
def mod(tmp_path):
    import importlib.util
    import sys
    p = tmp_path / "string_suggestion_fns.py"
    p.write_text(textwrap.dedent('''
        def label(s: str) -> str:
            """Upper case, stripped."""
            return s.strip().upper()

        def width(s: str) -> int:
            """The length of the stripped text."""
            return len(s.strip())

        def scale(x: float) -> float:
            """Twice."""
            return 2 * x
    '''))
    spec = importlib.util.spec_from_file_location("string_suggestion_fns", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules["string_suggestion_fns"] = m
    spec.loader.exec_module(m)
    return m


def _names(fn):
    return {c.name for c in suggest_claims(fn)}


def test_a_string_function_is_offered_the_arbitrary_input_family(mod):
    names = _names(mod.label)
    assert "is_language_defined[s]" in names
    assert {"is_deterministic", "is_state_safe"} <= names


def test_numeric_stability_is_not_offered_where_nothing_is_numeric(mod):
    assert "is_numerically_stable" not in _names(mod.label)


def test_numeric_stability_stays_where_the_function_returns_a_number(mod):
    assert "is_numerically_stable" in _names(mod.width)
    assert "is_numerically_stable" in _names(mod.scale)
