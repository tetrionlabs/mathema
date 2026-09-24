# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An absolute value in a stored statement parses back to the same claim.

A bar pair wraps a single term (a name, a number, one call, or one
parenthesised group), so an `abs(...)` around anything larger has to
come back out of the renderer as the call, never as bars the grammar
then rejects. Covered in all three renderings (the stored canonical
text and both display modes) and through a real `verify` run twice.
"""
import pytest

from mathema.conjecture import claim
from mathema.spec import canonical_claim_text, render_claim_text

_ABS_SHAPES = [
    "abs(f(xs, y0) - y0) <= sum(abs(v) for v in xs)",
    "abs(f(x) - x) <= abs(x - 1)",
    "abs(abs(f(x)) - 1) <= 2",
    "abs(f(x)**2) <= 1",
    "abs(f(x) + abs(x)) <= 2*abs(x) + 1",
    "abs(f(x)) <= abs(x) + 1",
    "abs(2*f(x)) <= 1",
    "abs(f(x)*g(x)) <= 1",
    "abs(f(x)/(x + 1)) <= 1",
    "abs(sin(f(x))) <= 1",
    "for x in [-3, 3], abs(f(x) - x) <= 1",
]


def _same_claim(a, b):
    """Two parses denote the same claim when their stored spellings agree
    (the stored spelling is rendered from the parsed expression, so
    `abs(2*f(x))` and `2*|f(x)|` are one claim)."""
    return canonical_claim_text(a) == canonical_claim_text(b)


@pytest.mark.parametrize("law", _ABS_SHAPES)
def test_the_stored_statement_reparses_to_the_same_claim(law):
    original = claim(law)
    stored = canonical_claim_text(original)
    restored = claim(stored)
    assert _same_claim(original, restored), stored
    assert canonical_claim_text(restored) == stored


@pytest.mark.parametrize("unicode_mode", [True, False])
@pytest.mark.parametrize("law", _ABS_SHAPES)
def test_the_displayed_statement_reparses_to_the_same_claim(law, unicode_mode):
    original = claim(law)
    shown = render_claim_text(original, unicode=unicode_mode)
    restored = claim(shown)
    assert _same_claim(original, restored), shown
    assert render_claim_text(restored, unicode=unicode_mode) == shown


def test_a_single_term_still_renders_with_bars():
    assert canonical_claim_text(claim("abs(f(x)) <= abs(x) + 1")) == "|f(x)| <= |x| + 1"


def test_a_compound_term_renders_as_the_call():
    assert (canonical_claim_text(claim("abs(f(x) - x) <= abs(x - 1)"))
            == "abs(x - f(x)) <= abs(x - 1)")


_RUNNING_TOTAL = '''\
def running_total(xs, y0):
    total = y0
    for v in xs:
        if v > 0:
            total = total + v
    return total
'''

_RUNNING_TOTAL_CLAIMS = '''\
absround.running_total:
  claims:
  - statement: abs(f(xs, y0) - y0) <= sum(abs(v) for v in xs)
'''


def test_a_second_verify_reads_back_the_record_it_wrote(tmp_path, monkeypatch):
    import importlib
    import sys

    from mathema.verify import verify_project
    sys.modules.pop("absround", None)
    importlib.invalidate_caches()
    (tmp_path / "absround.py").write_text(_RUNNING_TOTAL)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "running_total.claims.yaml").write_text(_RUNNING_TOTAL_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    verify_project(root=str(tmp_path))
    second = verify_project(root=str(tmp_path), all=True)
    assert not any("does not parse" in str(p) for p in second.problems), second.problems
