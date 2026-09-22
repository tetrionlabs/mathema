# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Set-notation domains: membership/exclusion/union/subset spellings all
canonicalize to one `Domain`, missing is included by default regardless
of whether a type is stated (only an explicit exclusion clause excludes
it, for either an implicit or an explicit type), rendering always states
the resolved policy explicitly, and a malformed domain binding raises
`InvalidDomain` with an actionable reason rather than being silently
discarded."""

import pytest

from mathema.grammar import (Domain, Interval, InvalidDomain, MISSING,
                             is_missing, domain_contains, normalize,
                             render_domain, split_quantifier)


def _dom(text: str):
    domain, _ = split_quantifier(normalize(text))
    return domain["x"]


# ---- membership spellings collapse to the same canonical domain -----------

@pytest.mark.parametrize("op", ["in", "\\in", "\\elem", "∈"])
def test_membership_spellings_parse_to_the_same_domain(op):
    assert _dom(f"for x {op} [0, 1], True") == Interval(0.0, 1.0)


# ---- exclusion: backslash-set-minus and the exclude= keyword form ---------

def test_backslash_exclusion_removes_a_point_from_an_interval():
    dom = _dom("for x in [-1, 1] \\ {0}, True")
    assert isinstance(dom, Domain)
    # no type stated, only the explicitly excluded point is excluded,
    # missing stays allowed (the implicit-type default from below).
    assert dom.excluded == frozenset({0.0})
    assert not domain_contains(0.0, dom)
    assert domain_contains(0.5, dom)
    assert domain_contains(float("nan"), dom)


def test_exclude_keyword_form_is_equivalent_to_backslash():
    inline = _dom("for x in [-1, 1] \\ {0}, True")
    keyword = _dom("for x in [-1, 1], exclude={0}, True")
    assert inline == keyword


# ---- union: '|' and '∪' -----------------------------------------------

@pytest.mark.parametrize("op", ["|", "∪"])
def test_union_spellings_parse_to_the_same_pieces(op):
    dom = _dom(f"for x in [-10, -1) {op} (1, 10], True")
    assert isinstance(dom, Domain)
    assert len(dom.pieces) == 2
    assert domain_contains(-5.0, dom)
    assert domain_contains(5.0, dom)
    assert not domain_contains(0.0, dom)


def test_union_with_exclusion_removes_the_point_from_the_whole_union():
    dom = _dom("for x in [-10, -1) | (1, 10] \\ {5}, True")
    assert domain_contains(4.0, dom)
    assert not domain_contains(5.0, dom)


# ---- subset/type-refinement: glyph and text spellings ---------------------

@pytest.mark.parametrize("op", ["\\subset", "\\sub", "⊂"])
def test_subset_spellings_parse_to_the_same_base_type(op):
    dom = _dom(f"for x in [0, 10] {op} Z, True")
    assert isinstance(dom, Domain)
    assert dom.base_type == "Z"
    assert domain_contains(3, dom)
    assert not domain_contains(3.5, dom)


def test_bare_named_set_is_a_stated_type_choice_not_just_a_shorthand():
    # a bare "x in Z" produces a Domain, not the raw string "Z", stating
    # a type at all, even this way, is a deliberate choice
    # (`explicit_type=True`), even though it no longer changes the
    # missing-value default (see the corner tests below).
    dom = _dom("for x in Z, True")
    assert dom == Domain(base_type="Z", explicit_type=True)


def test_omitted_type_defaults_to_real_unrestricted():
    dom = _dom("for x in [0, 1], True")
    assert dom == Interval(0.0, 1.0)   # collapses to the old raw shape


# ---- missing-value sentinel spellings --------------------------------------

@pytest.mark.parametrize("token", ["∅", "missing", "NA", "nan"])
def test_missing_sentinel_spellings_all_exclude_the_same_way(token):
    dom = _dom(f"for x in [0, 1] \\ {{{token}}}, True")
    assert MISSING in dom.excluded
    assert not domain_contains(float("nan"), dom)
    assert not domain_contains(None, dom)


# ---- missing is included by default, regardless of type; only an ---------
# ---- explicit exclusion clause ever excludes it, for either type ---------

def test_corner_a_implicit_type_missing_allowed_by_default():
    dom = _dom("for x in [0, 100], True")
    assert domain_contains(float("nan"), dom)
    assert domain_contains(None, dom)


def test_corner_b_explicit_type_missing_also_allowed_by_default():
    # stating a type never excludes missing as a side effect, the
    # default is the same, wider, unverified-safe one either way.
    dom = _dom("for x in [0, 100] \\subset Z, True")
    assert domain_contains(float("nan"), dom)
    assert domain_contains(None, dom)


def test_corner_c_implicit_type_explicitly_excluded_missing():
    dom = _dom("for x in [0, 100] \\ {missing}, True")
    assert not domain_contains(float("nan"), dom)


def test_corner_d_explicit_type_explicitly_excluded_missing():
    dom = _dom("for x in [0, 100] \\subset Z \\ {missing}, True")
    assert not domain_contains(float("nan"), dom)
    assert domain_contains(50, dom)


# ---- extensible, dependency-free missing-value detection -------------------

def test_is_missing_detects_none_and_python_nan_with_no_imports():
    assert is_missing(None)
    assert is_missing(float("nan"))
    assert not is_missing(0.0)
    assert not is_missing("nan-shaped-string-is-not-missing")


def test_is_missing_detects_numpy_nan_without_importing_numpy_itself():
    numpy = pytest.importorskip("numpy")
    assert is_missing(numpy.float64("nan"))
    assert not is_missing(numpy.float64(1.0))


# ---- explicit-output rendering: the policy is never left for a
# ---- reader to infer from what's absent, in the same glyph
# ---- vocabulary as input -------------------------------------------

def test_rendering_distinguishes_all_four_corners_via_glyph_notation():
    a = _dom("for x in [0, 100], True")
    b = _dom("for x in [0, 100] \\subset Z, True")
    c = _dom("for x in [0, 100] \\ {missing}, True")
    d = _dom("for x in [0, 100] \\subset Z \\ {missing}, True")
    ra, rb, rc, rd = (render_domain(x, show_missing=True) for x in (a, b, c, d))
    assert ra != rb   # differ by type glyph (ℝ vs ℤ), not missing-status
    assert ra.endswith("∪ {∅}") and rb.endswith("∪ {∅}")
    assert rc.endswith("\\ {∅}") and rd.endswith("\\ {∅}")
    for r in (ra, rb, rc, rd):
        assert "∅" in r   # glyph notation, never an English phrase


def test_render_domain_never_uses_a_natural_language_phrase():
    dom = _dom("for x in [-10, -1) | (1, 10] \\ {5} \\subset R, True")
    text = render_domain(dom, show_missing=True)
    for banned in ("missing", "included", "excluded", "allowed"):
        assert banned not in text.lower()


# ---- InvalidDomain: a malformed binding is diagnosable, not silently ------
# ---- discarded once "for ... :" has already matched -----------------------

def test_malformed_binding_raises_invalid_domain_with_a_specific_reason():
    with pytest.raises(InvalidDomain, match="no recognized membership operator"):
        split_quantifier(normalize("for x: f(x) >= 0"))


def test_unrecognized_domain_shape_raises_invalid_domain():
    with pytest.raises(InvalidDomain, match="isn't a recognized"):
        split_quantifier(normalize("for x in ???, f(x) >= 0"))


def test_no_quantifier_at_all_is_not_an_error():
    domain, law = split_quantifier(normalize("f(x) >= 0"))
    assert domain == {}
    assert law == "f(x) >= 0"
