# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A norm written with double bars, the order as a subscript.

`||x||` is `norm(x)` and `||x||_k` is `norm(x, k)` for `k` one of `1`,
`2`, an integer `p >= 1` and `inf` (also `oo` and `∞`); the two
spellings lower to the same text and reach the same verdict on the
same route. The order is never a superscript, so `||x||^2` is the
square of the norm. A written `||x||` renders back as written, `||x||`
in ascii and `‖x‖` in unicode with the order a subscript glyph, and a
written `norm(x)` stays the call. The record's note names the norm a
bare `||x||` or `norm(x)` resolves to, in the spelling written:
Euclidean for a vector, Frobenius for a matrix. Any other order is
refused with the accepted orders named.
"""
from __future__ import annotations

import numpy as np
import pytest

from mathema._linalg_eval import _norm
from mathema.claims import check_conjectures, claim
from mathema.compendium import _installed_version, _version_in_range
from mathema.conjecture import InvalidConjecture
from mathema.grammar import normalize
from mathema.spec import canonical_claim_text, render_claim_text
from tests.test_claim_text_soundness import assert_round_trips


# `numpy.dot`'s definition row applies from numpy 2.4, so below it a
# squared length computed with `np.dot` has no derivation and is sampled
_NUMPY_DOT_ROW = _version_in_range(_installed_version("numpy") or "0", ">=2.4")
_SQUARED = ("proven", "derive") if _NUMPY_DOT_ROW else ("holds", "probe")


def _spaceless(text: str) -> str:
    return text.replace(" ", "")


# --- the grammar ----------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("||x||", "norm(x)"),
    ("||x||_1", "norm(x, 1)"),
    ("||x||_2", "norm(x, 2)"),
    ("||x||_12", "norm(x, 12)"),
    ("||x||_inf", "norm(x, inf)"),
    ("||x||_oo", "norm(x, inf)"),
    ("||x||_∞", "norm(x, inf)"),
    ("||x - y||", "norm(x - y)"),
    ("||x - y||_2", "norm(x - y, 2)"),
    ("||f(x)||_1", "norm(f(x), 1)"),
    ("||x||^2", "norm(x)**2"),
    ("||x||_2^2", "norm(x, 2)**2"),
    ("||x||_2 + ||y||_2", "norm(x, 2) + norm(y, 2)"),
    ("2 * ||x|| / ||y||_inf", "2 * norm(x) / norm(y, inf)"),
    ("||a| - |b||", "abs(abs(a) - abs(b))"),
    ("‖x‖", "norm(x)"),
    ("‖x‖₂", "norm(x, 2)"),
    ("‖x‖₁₂", "norm(x, 12)"),
    ("‖x‖∞", "norm(x, inf)"),
    ("‖x - y‖", "norm(x - y)"),
    ("‖x‖^2", "norm(x)**2"),
    ("‖x‖²", "norm(x)**2"),
])
def test_double_bars_lower_to_the_norm_call(text, expected):
    assert _spaceless(normalize(text)) == _spaceless(expected)


@pytest.mark.parametrize("sugar, words", [
    ("for x in R^n, ||x|| >= 0", "for x in R^n, norm(x) >= 0"),
    ("for x in R^n, ||x||_1 >= ||x||_2", "for x in R^n, norm(x, 1) >= norm(x, 2)"),
    ("for x in R^n, ||x||_inf <= ||x||_1", "for x in R^n, norm(x, inf) <= norm(x, 1)"),
    ("for x in R^n, ||x||_oo <= ||x||_1", "for x in R^n, norm(x, inf) <= norm(x, 1)"),
    ("for x in R^n, ||x||^2 == dot(x, x)", "for x in R^n, norm(x)**2 == dot(x, x)"),
    ("for A in R^(n,n), ||A|| >= 0", "for A in R^(n,n), norm(A) >= 0"),
    ("for A in R^(n,n), ||A||_2 <= ||A||", "for A in R^(n,n), norm(A, 2) <= norm(A)"),
])
def test_the_sugar_parses_to_the_same_sides_as_the_words(sugar, words):
    a, b = claim(sugar), claim(words)
    assert (a.lhs, a.relation, a.rhs, a.domain) == (b.lhs, b.relation, b.rhs, b.domain)


def test_double_bars_around_a_matrix_are_its_norm_not_its_determinant():
    cj = claim("for A in R^(n,n), ||A|| >= |A|")
    assert (cj.lhs, cj.rhs) == ("norm(A)", "det(A)")


@pytest.mark.parametrize("bad", [
    "for x in R^n, ||x||_0 >= 0",
    "for x in R^n, ||x||_0.5 >= 0",
    "for x in R^n, ||x||_p >= 0",
    "for x in R^n, ||x||_-1 >= 0",
])
def test_an_order_the_bars_do_not_read_is_refused_naming_the_accepted_ones(bad):
    with pytest.raises(InvalidConjecture,
                       match=r"Write _1, _2, a whole number such as _3, or _inf"):
        claim(bad)


@pytest.mark.parametrize("bad", [
    "for x in R^n, ||x| >= 0",
    "for x in R^n, ||x||_2 + |y >= 0",
])
def test_bars_that_do_not_pair_are_still_refused(bad):
    with pytest.raises(InvalidConjecture, match="do not pair up"):
        claim(bad)


# --- rendering ------------------------------------------------------------

@pytest.mark.parametrize("law, ascii_form, unicode_form", [
    ("for x in R^n, ||x|| >= 0",
     "for x in (R | {missing})^n|absent, ||x|| >= 0",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖ ≥ 0"),
    ("for x in R^n, ||x||_1 >= ||x||_2",
     "for x in (R | {missing})^n|absent, ||x||_1 >= ||x||_2",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖₁ ≥ ‖x‖₂"),
    ("for x in R^n, ||x||_inf <= ||x||_1",
     "for x in (R | {missing})^n|absent, ||x||_inf <= ||x||_1",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖∞ ≤ ‖x‖₁"),
    ("for x in R^n, ||x||_oo <= ||x||_1",
     "for x in (R | {missing})^n|absent, ||x||_inf <= ||x||_1",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖∞ ≤ ‖x‖₁"),
    ("for x in R^n, ||x||_∞ <= ||x||_1",
     "for x in (R | {missing})^n|absent, ||x||_inf <= ||x||_1",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖∞ ≤ ‖x‖₁"),
    ("for x in R^n, ||x||_12 <= ||x||_1",
     "for x in (R | {missing})^n|absent, ||x||_12 <= ||x||_1",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖₁₂ ≤ ‖x‖₁"),
    ("for x in R^n, ||x||^2 == dot(x, x)",
     "for x in (R | {missing})^n|absent, ||x||^2 = dot(x, x)",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖^2 = dot(x, x)"),
    ("for x in R^n, y in R^n, ||x - y|| <= ||x|| + ||y||",
     "for x in (R | {missing})^n|absent, y in (R | {missing})^n|absent, ||x - y|| <= ||x|| + ||y||",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, y ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x - y‖ ≤ ‖x‖ + ‖y‖"),
    ("for A in R^(n,n), ||A||_2 <= ||A||",
     "for A in (R | {missing})^(n,n)|absent, ||A||_2 <= ||A||",
     "∀ A ∈ (ℝ ∪ {∅})ⁿˣⁿ ∪ {absent}, ‖A‖₂ ≤ ‖A‖"),
    ("∀ x ∈ ℝⁿ, ‖x‖₂ ≤ ‖x‖₁",
     "for x in (R | {missing})^n|absent, ||x||_2 <= ||x||_1",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖₂ ≤ ‖x‖₁"),
    # the words stay the words
    ("for x in R^n, norm(x) >= 0",
     "for x in (R | {missing})^n|absent, norm(x) >= 0",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, norm(x) ≥ 0"),
    ("for x in R^n, norm(x, 2) <= norm(x, 1)",
     "for x in (R | {missing})^n|absent, norm(x, 2) <= norm(x, 1)",
     "∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, norm(x, 2) ≤ norm(x, 1)"),
])
def test_a_norm_renders_as_the_author_spelled_it(law, ascii_form, unicode_form):
    cj = claim(law)
    assert render_claim_text(cj, unicode=False) == ascii_form
    assert render_claim_text(cj, unicode=True) == unicode_form
    # the canonical text, the claim's identity, keeps the call in every
    # case, and the display reparses to it
    canonical = canonical_claim_text(cj)
    assert "||" not in canonical and "‖" not in canonical, canonical
    assert canonical_claim_text(claim(ascii_form)) == canonical


def test_the_canonical_text_writes_every_infinity_spelling_as_inf():
    texts = {canonical_claim_text(claim(f"for x in R^n, ||x||_{spelling} <= ||x||_1"))
             for spelling in ("inf", "oo", "∞")}
    assert texts == {"for x in (R | {missing})^n|absent, norm(x, inf) <= norm(x, 1)"}


def test_a_norm_of_a_bar_term_keeps_the_call_spelling():
    cj = claim("for x in R^n, ||abs(x)|| == ||x||")
    assert render_claim_text(cj, unicode=False) == \
        "for x in (R | {missing})^n|absent, norm(|x|) = ||x||"


@pytest.mark.parametrize("law", [
    "for x in R^n, ||x|| >= 0",
    "for x in R^n, ||x||_1 >= ||x||_2",
    "for x in R^n, ||x||_oo <= ||x||_1",
    "for x in R^n, ||x||^2 == dot(x, x)",
    "for x in R^n, y in R^n, ||x - y|| <= ||x|| + ||y||",
    "for A in R^(m,n), ||A|| >= 0",
    "for A in R^(n,n), ||A||_2 <= ||A||",
    "for x in R^n, ||abs(x)|| == ||x||",
    "assuming ||x|| > 0, for x in R^n, ||x||_inf > 0",
])
def test_render_parse_render_is_a_fixed_point_in_both_modes(law):
    assert_round_trips(law)
    cj = claim(law)
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        assert render_claim_text(claim(shown), unicode=unicode) == shown


def test_the_two_spellings_are_one_claim_with_one_fingerprint():
    from mathema.spec import fingerprint_text
    bars = claim("for x in R^n, ||x||_2 <= 1")
    words = claim("for x in R^n, norm(x, 2) <= 1")
    assert (bars.lhs, bars.rhs) == (words.lhs, words.rhs)
    assert canonical_claim_text(bars) == canonical_claim_text(words) \
        == "for x in (R | {missing})^n|absent, norm(x, 2) <= 1"
    assert fingerprint_text(bars) == fingerprint_text(words)
    # the display keeps each author's spelling
    assert render_claim_text(bars, unicode=False).endswith("||x||_2 <= 1")
    assert render_claim_text(words, unicode=False).endswith("norm(x, 2) <= 1")


@pytest.mark.parametrize("bad, shown", [
    ("for x in R^n, |||x||| >= 0", "|||x|||"),
    ("for x in R^n, ||||x|||| >= 0", "||||x||||"),
    ("for x in R^n, ‖‖x‖‖ >= 0", "‖‖x‖‖"),
])
def test_three_bars_are_refused_not_read(bad, shown):
    with pytest.raises(InvalidConjecture, match="more bars than a norm reads") as e:
        claim(bad)
    assert f"`{shown}`" in str(e.value), str(e.value)


def test_an_order_glyph_on_the_opening_bars_is_refused():
    with pytest.raises(InvalidConjecture) as e:
        claim("for x in R^n, ‖₂x‖ >= 0")
    assert str(e.value).startswith(
        "`₂` after the opening bars is not read; the order goes after the "
        "closing bars, ‖x‖₂"), str(e.value)


@pytest.mark.parametrize("bad, written", [
    ("for x in R^n, ||x||_0 >= 0", "`_0`"),
    ("for x in R^n, ||x||_02 >= 0", "`_02`"),
    ("for x in R^n, ||x||_0.5 >= 0", "`_0.5`"),
    ("for x in R^n, ||x||_p >= 0", "`_p`"),
    ("for x in R^n, ‖x‖∞∞ >= 0", "`∞∞`"),
    ("for x in R^n, ‖x‖₂∞ >= 0", "`₂∞`"),
    ("for x in R^n, ||x||_∞∞ >= 0", "`∞∞`"),
])
def test_the_refusal_names_what_was_written_and_the_claim(bad, written):
    with pytest.raises(InvalidConjecture) as e:
        claim(bad)
    said = str(e.value)
    assert said.startswith(written + " after the closing bars is not an order"), said
    assert "Write _1, _2, a whole number such as _3, or _inf (also _oo or _∞)" in said
    assert "norm(x, 0.5)" in said and "let p be 3, then write norm(x, p)" in said
    assert bad in said, said


def test_the_premise_spellings_are_one_fingerprint():
    from mathema.spec import fingerprint_text
    bars = claim("assuming ||x|| > 0, for x in R^n, ||x||_2 > 0")
    words = claim("assuming norm(x) > 0, for x in R^n, norm(x, 2) > 0")
    assert bars.assuming == words.assuming == "assuming norm(x) > 0"
    assert fingerprint_text(bars) == fingerprint_text(words)
    # the display keeps the author's spelling in the premise too, in the
    # mode of the statement
    assert render_claim_text(bars, unicode=False).startswith("assuming ||x|| > 0, ")
    assert render_claim_text(bars, unicode=True).startswith("assuming ‖x‖ > 0, ")
    assert render_claim_text(words, unicode=True).startswith("assuming norm(x) > 0, ")
    # the same fold takes an absolute value in a premise
    assert fingerprint_text(claim("assuming |x| > 0, for x in [-1, 1], f(x) >= 0")) \
        == fingerprint_text(claim("assuming abs(x) > 0, for x in [-1, 1], f(x) >= 0"))


def test_a_bad_order_on_a_decorated_function_names_the_function():
    from mathema import claims_decorator

    with pytest.raises(InvalidConjecture, match="declared on") as e:
        @claims_decorator("for x in R^n, f(x) ~= ||x||_0")
        def badly_claimed(x: np.ndarray) -> float:
            return float(np.linalg.norm(x))
    assert "badly_claimed" in str(e.value) and "`_0` after the closing bars" in str(e.value)


# --- an infinite order in the call form ------------------------------------

@pytest.mark.parametrize("spelling", ["oo", "infinity", "∞", "inf", "\\infty"])
def test_every_infinite_order_in_the_call_form_lowers_to_inf(spelling):
    cj = claim(f"for x in R^n, norm(x, {spelling}) <= norm(x, 1)")
    assert cj.lhs == "norm(x, inf)"
    assert canonical_claim_text(cj) == \
        "for x in (R | {missing})^n|absent, norm(x, inf) <= norm(x, 1)"


def test_a_nested_norm_order_is_lowered_too():
    assert normalize("norm(norm(x, oo) * y, oo)") == "norm(norm(x, inf) * y, inf)"


@pytest.mark.needs_full_proof_budget
def test_the_call_form_with_oo_reaches_the_verdict_of_inf():
    # the control is the old failure: `oo` was unbound in the probe's
    # namespace and sampled as a free variable, so numpy computed a
    # random-order norm and the claim was falsified
    with_oo = _adjudicate(largest_magnitude, "for x in R^n, f(x) ~= norm(x, oo)")
    with_inf = _adjudicate(largest_magnitude, "for x in R^n, f(x) ~= norm(x, inf)")
    assert (with_oo.verdict, with_oo.route) == (with_inf.verdict, with_inf.route) \
        == ("proven", "derive"), (with_oo.note, with_inf.note)
    assert "oo" not in claim("for x in R^n, f(x) ~= norm(x, oo)").lhs
    assert _norm(_V, 2.7) != _norm(_V, np.inf)
    # a norm's order is not a bare infinity in the law, so no note says
    # it reads as the constant
    for p in (with_oo, with_inf):
        assert "reads as the mathematical constant" not in (p.note or ""), p.note


_DECORATED = '''\
import numpy as np
from mathema import claims_decorator


@claims_decorator("for x in R^n, f(x) ~= {law}")
def largest_magnitude(x: np.ndarray) -> float:
    return float(np.max(np.abs(x)))
'''


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("law, expected", [
    ("||x||_inf", "proven"),
    ("‖x‖∞", "proven"),
    ("norm(x, oo)", "proven"),
    # the control: the wrong order is caught on the same path, at a
    # vector with entries
    ("||x||_1", "falsified"),
])
def test_the_cli_reads_the_infinite_order_on_the_decorator_path(
        tmp_path, monkeypatch, capsys, law, expected):
    # at e9172e8 `mathema check` on this module printed a probe record
    # falsified with the witness `inf=-1.13166e+162`: the decorator path
    # never bound `inf`, which was sampled as a free variable
    import json

    from mathema.cli import main
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "normdeco.py").write_text(_DECORATED.format(law=law))
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    main(["check", "normdeco.py", "--format", "compact"])
    out = capsys.readouterr().out
    assert "inf=" not in out, out
    (record,) = json.loads(out)
    rows = [r for r in record["claims"] if r["source"] == "decorator"]
    headline = next(r for r in rows if r["claim"].startswith("f_x_approx")
                    and "[" not in r["claim"])
    if expected == "proven":
        companion = next(r for r in rows if "[float" in r["claim"])
        # np.max raises on the empty vector, which the claim's
        # empty-input line reports: that is the claim's only witness,
        # and every non-empty vector agrees with the infinite order
        assert headline["counterexample"] == "x = []", headline
        assert companion["verdict"] == "holds", companion
    else:
        assert headline["verdict"] == "falsified", headline
        assert headline["counterexample"] != "x = []", headline


# --- the evaluation path: numpy's norm, both ranks, the matrix orders ------

_V = np.array([3.0, -4.0, 12.0])
_M = np.array([[1.0, -2.0], [3.0, 4.0]])
_RANK_ONE = np.array([[1.0, 2.0], [2.0, 4.0]])


@pytest.mark.parametrize("value, order, expected", [
    # the dispatch on rank: a number is its magnitude whatever the
    # order, a vector its Euclidean length, a matrix its Frobenius norm
    (-2.5, None, 2.5),
    (-2.5, 1, 2.5),
    (_V, None, 13.0),
    (_M, None, np.sqrt(30.0)),
    # the matrix orders as numpy reads `ord`: the largest column sum,
    # the largest singular value, the largest row sum
    (_M, 1, 6.0),
    (_M, 2, np.linalg.svd(_M, compute_uv=False)[0]),
    (_M, np.inf, 7.0),
    # the scale-out branch at a zero largest magnitude
    (np.zeros(3), None, 0.0),
    (np.zeros(3), np.inf, 0.0),
    (np.zeros((2, 2)), 1, 0.0),
    # the boundaries: a vector of one entry, a 1 by 1 matrix (which is
    # not a matrix to the lift, and still a matrix to numpy's `ord`)
    (np.array([-3.0]), np.inf, 3.0),
    (np.array([[-2.0]]), 1, 2.0),
    # rank one: the Frobenius norm equals the spectral norm
    (_RANK_ONE, None, 5.0),
    (_RANK_ONE, 2, 5.0),
])
def test_the_norm_dispatches_on_rank_and_order(value, order, expected):
    got = _norm(value) if order is None else _norm(value, order)
    assert got == pytest.approx(expected)


def test_the_norm_scales_out_entries_near_the_float_maximum():
    # the square of an entry near the float maximum overflows; the norm
    # itself does not, since every norm is homogeneous
    big = np.array([1e308, 1e308])
    assert _norm(big) == pytest.approx(1e308 * np.sqrt(2.0))
    assert _norm(big, np.inf) == 1e308


def test_the_matrix_orders_are_three_different_numbers():
    # a control on the parametrisation above: on this matrix the column
    # sums, the singular values and the row sums do not coincide
    values = {_norm(_M, 1), _norm(_M, 2), _norm(_M, np.inf), _norm(_M)}
    assert len(values) == 4, values


@pytest.mark.parametrize("text, written", [
    ("for x in R^n, ||x|| >= 0", True),
    ("for x in (R | {missing})^n|absent, ||x||_2 <= ||x||_1", True),
    ("∀ x ∈ (ℝ ∪ {∅})ⁿ ∪ {absent}, ‖x‖₂ ≤ ‖x‖₁", True),
    ("assuming ||x|| > 0, for x in R^n, f(x) >= 0", True),
    ("for x in R^n, norm(x) >= 0", False),
    ("for x in [0, 1], |x| <= 1", False),
    ("for a in [0, 1], b in [0, 1], ||a| - |b|| <= 1", False),
    ("for A in R^(n,n), |A| >= 0", False),
    ('f(s) == "||x||"', False),
])
def test_the_renderer_reads_the_bar_spelling_from_the_author_text(text, written):
    from mathema.grammar import norm_bars_written
    assert norm_bars_written(text) is written


# --- the same verdict on the same route as the words ---------------------

def euclidean_length(x: np.ndarray) -> float:
    return float(np.linalg.norm(x))


def manhattan_length(x: np.ndarray) -> float:
    return float(np.sum(np.abs(x)))


def largest_magnitude(x: np.ndarray) -> float:
    return float(np.max(np.abs(x)))


def squared_length(x: np.ndarray) -> float:
    return float(np.dot(x, x))


def distance(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.linalg.norm(x - y))


def frobenius(A: np.ndarray) -> float:
    return float(np.sqrt(np.sum(A * A)))


def largest_singular_value(A: np.ndarray) -> float:
    return float(np.linalg.svd(A, compute_uv=False)[0])


def max_column_sum(A: np.ndarray) -> float:
    return float(np.max(np.sum(np.abs(A), axis=0)))


def max_row_sum(A: np.ndarray) -> float:
    return float(np.max(np.sum(np.abs(A), axis=1)))


def _adjudicate(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn, sugar, words, verdict, route", [
    # a norm over a vector is lowered on the derive route, so these
    # prove for every length through the numpy definition rows
    (euclidean_length, "for x in R^n, f(x) ~= ||x||",
     "for x in R^n, f(x) ~= norm(x)", "proven", "derive"),
    (euclidean_length, "for x in R^n, f(x) ~= ||x||_2",
     "for x in R^n, f(x) ~= norm(x, 2)", "proven", "derive"),
    (manhattan_length, "for x in R^n, f(x) ~= ||x||_1",
     "for x in R^n, f(x) ~= norm(x, 1)", "proven", "derive"),
    (largest_magnitude, "for x in R^n, f(x) ~= ||x||_inf",
     "for x in R^n, f(x) ~= norm(x, inf)", "proven", "derive"),
    (largest_magnitude, "for x in R^n, f(x) ~= ||x||_oo",
     "for x in R^n, f(x) ~= norm(x, inf)", "proven", "derive"),
    (squared_length, "for x in [-1e6, 1e6]^n, f(x) ~= ||x||^2",
     "for x in [-1e6, 1e6]^n, f(x) ~= norm(x)**2", *_SQUARED),
    (distance, "for x in R^n, y in R^n, f(x, y) ~= ||x - y||",
     "for x in R^n, y in R^n, f(x, y) ~= norm(x - y)", "proven", "derive"),
    # a sum over every entry of a matrix, a singular value decomposition
    # and the matrix orders have no lowering, so these stay sampled
    (frobenius, "for A in R^(m,n), f(A) ~= ||A||",
     "for A in R^(m,n), f(A) ~= norm(A)", "holds", "probe"),
    (largest_singular_value, "for A in R^(n,n), f(A) ~= ||A||_2",
     "for A in R^(n,n), f(A) ~= norm(A, 2)", "holds", "probe"),
    (max_column_sum, "for A in R^(m,n), f(A) ~= ||A||_1",
     "for A in R^(m,n), f(A) ~= norm(A, 1)", "holds", "probe"),
    (max_row_sum, "for A in R^(m,n), f(A) ~= ||A||_inf",
     "for A in R^(m,n), f(A) ~= norm(A, inf)", "holds", "probe"),
    # a false sibling falsifies in either spelling, with a witness
    (manhattan_length, "for x in R^n, f(x) ~= ||x||_2",
     "for x in R^n, f(x) ~= norm(x, 2)", "falsified", "probe"),
    (max_column_sum, "for A in R^(m,n), f(A) ~= ||A||_inf",
     "for A in R^(m,n), f(A) ~= norm(A, inf)", "falsified", "probe"),
])
@pytest.mark.needs_full_proof_budget
def test_the_sugar_reaches_the_verdict_of_the_words(fn, sugar, words, verdict, route):
    a, b = _adjudicate(fn, sugar), _adjudicate(fn, words)
    assert (a.verdict, a.route) == (b.verdict, b.route) == (verdict, route), \
        (a.verdict, a.note, b.verdict, b.note)
    if verdict == "falsified":
        assert a.counterexample and b.counterexample
    if route == "derive":
        assert "every length" in (a.sketch or ""), a.sketch



def test_the_squared_length_overflows_at_the_magnitude_corner_on_every_numpy():
    """Over all of `R^n`, `float(np.dot(x, x))` overflows to inf at a
    vector of entries near the float maximum, where the exact squared
    norm is finite: the record's headline is falsified there through
    the computation line, whether or not the mathematics is proven (it
    is from numpy 2.4, through `numpy.dot`'s definition row)."""
    import mathema
    law = "for x in R^n, f(x) ~= norm(x)**2"
    record = mathema.check(squared_length, claims=[law])
    headline = str(record).splitlines()[1]
    assert "falsified at x = " in headline, headline
    (computation,) = [p for p in record.probes
                      if p.name.startswith("f_x_approx_norm_x_2")
                      and p.verdict == "falsified"]
    import re
    entries = [float(v) for v in re.findall(r"-?\d[\d.e+-]*",
                                           computation.counterexample)]
    assert max(abs(v) for v in entries) >= 1e300, computation.counterexample

# --- the derive route: what the lowering proves and what it refuses -------

@pytest.mark.parametrize("fn, law", [
    (euclidean_length, "for x in R^n, f(x) ~= ||x||_1"),
    (largest_magnitude, "for x in R^n, f(x) ~= ||x||_2"),
    (manhattan_length, "for x in R^n, f(x) ~= ||x||_inf"),
    (squared_length, "for x in R^n, ||x||^2 == 2 * dot(x, x)"),
    (distance, "for x in R^n, y in R^n, f(x, y) ~= ||x|| - ||y||"),
])
def test_a_false_norm_identity_is_not_proven_and_is_falsified(fn, law):
    # the control for the lowering: the derive route proves none of
    # these, and sampling finds the witness
    p = _adjudicate(fn, law)
    assert (p.verdict, p.route) == ("falsified", "probe"), (p.verdict, p.note)
    assert p.counterexample, p.note
    # the derive route was attempted and did not prove it
    assert ("derive could not decide it" in (p.note or "")
            or "could not show the relation" in (p.note or "")), p.note


def test_an_order_outside_the_lowering_is_named_and_left_to_the_probe():
    p = _adjudicate(euclidean_length, "for x in R^n, f(x) ~= norm(x, 3)")
    assert (p.verdict, p.route) == ("falsified", "probe"), (p.verdict, p.note)
    assert "the derive route reads the orders 1, 2 and inf, so order 3 is left " \
           "to sampling" in (p.note or ""), p.note


@pytest.mark.parametrize("law", [
    "for x in R^0, f(x) ~= ||x||_inf",
    "for x in R^n, assuming len(x) == 0, f(x) ~= ||x||_inf",
])
def test_the_largest_magnitude_of_the_empty_vector_is_left_to_the_probe(law):
    # `largest_magnitude([])` raises; a proof over a domain that admits
    # the empty vector would be wrong, so the derive route declines and
    # says so, and the probe decides
    p = _adjudicate(largest_magnitude, law)
    assert p.verdict != "proven", (p.verdict, p.note)
    assert "holds for every length of at least one, and the empty vector is " \
           "left to the probe" in (p.note or ""), p.note


@pytest.mark.parametrize("law", [
    "for pred in R^0, actual in R^0, f(pred, actual) ~= ||pred - actual|| / sqrt(len(pred))",
    "for pred in R^n, actual in R^n, assuming len(pred) == 0, "
    "f(pred, actual) ~= ||pred - actual|| / sqrt(len(pred))",
])
def test_the_root_mean_square_error_of_the_empty_vector_is_left_to_the_probe(law):
    # `rmse([], [])` is nan (a division by the length); at 7dcd05c the
    # sequence route proved this over the explicit empty domain
    from mathema._lexicon_numpy import rmse
    p = _adjudicate(rmse, law)
    assert p.verdict != "proven", (p.verdict, p.note)
    assert "the empty vector is left to the probe" in (p.note or ""), p.note


def test_the_empty_vector_falsifies_the_largest_magnitude_with_a_witness():
    p = _adjudicate(largest_magnitude, "for x in R^0, f(x) ~= ||x||_inf")
    assert (p.verdict, p.route) == ("falsified", "probe"), (p.verdict, p.note)
    assert "x = []" in str(p.counterexample), p.counterexample


@pytest.mark.parametrize("fn, law", [
    (euclidean_length, "for x in R^0, f(x) ~= ||x||"),
    (manhattan_length, "for x in R^0, f(x) ~= ||x||_1"),
])
def test_the_euclidean_and_manhattan_lengths_of_the_empty_vector_are_zero(fn, law):
    # numpy's norm and sum of an empty vector are 0, as the sums say
    p = _adjudicate(fn, law)
    assert p.verdict != "falsified", (p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
def test_a_proof_through_a_largest_magnitude_says_at_least_one():
    p = _adjudicate(largest_magnitude, "for x in R^n, f(x) ~= ||x||_inf")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    assert "for every length of at least one" in (p.sketch or ""), p.sketch
    q = _adjudicate(euclidean_length, "for x in R^n, f(x) ~= ||x||")
    assert "of at least one" not in (q.sketch or ""), q.sketch


@pytest.mark.needs_full_proof_budget
def test_a_matrix_frobenius_identity_proves_through_the_trace():
    from mathema._lexicon_numpy import frobenius_norm, gram_trace
    for fn, law in [(frobenius_norm, "for A in R^(m,n), ||A|| ~= sqrt(trace(A.T @ A))"),
                    (gram_trace, "for A in R^(m,n), ||A||^2 ~= trace(A @ A.T)"),
                    (gram_trace, "for A in R^(m,n), ||A|| ~= sqrt(f(A))")]:
        p = _adjudicate(fn, law)
        assert (p.verdict, p.route) == ("proven", "derive"), (law, p.verdict, p.note)
    p = _adjudicate(gram_trace, "for A in R^(m,n), ||A||^2 ~= 2 * f(A)")
    assert (p.verdict, p.route) == ("falsified", "probe"), (p.verdict, p.note)


# --- the note names the resolved norm -------------------------------------

def test_a_bare_norm_of_a_vector_is_noted_as_euclidean():
    p = _adjudicate(euclidean_length, "for x in R^n, f(x) ~= ||x||")
    assert "||x|| is the Euclidean norm of x" in (p.note or ""), p.note


def test_a_bare_norm_of_a_matrix_is_noted_as_frobenius():
    p = _adjudicate(frobenius, "for A in R^(m,n), f(A) ~= ||A||")
    assert "||A|| is the Frobenius norm of A" in (p.note or ""), p.note


def test_a_bare_norm_of_a_difference_is_noted_from_its_operands():
    p = _adjudicate(distance, "for x in R^n, y in R^n, f(x, y) ~= ||x - y||")
    assert "||x - y|| is the Euclidean norm of x - y" in (p.note or ""), p.note


def test_a_bare_norm_of_a_call_is_noted_for_either_rank():
    # the rank of f(x) cannot be read from the claim, so the note says
    # what the bars mean for a vector and for a matrix
    from mathema._lexicon_numpy import unit_vector
    p = _adjudicate(unit_vector, "assuming ||x|| > 0, for x in R^n, ||f(x)|| ~= 1")
    assert ("||f(x)|| is the Euclidean norm if f(x) is a vector and the "
            "Frobenius norm if it is a matrix") in (p.note or ""), p.note


def test_a_one_column_matrix_is_noted_as_frobenius():
    from mathema._lexicon_numpy import frobenius_norm
    p = _adjudicate(frobenius_norm, "for A in R^(n,1), f(A) ~= ||A||")
    assert "||A|| is the Frobenius norm of A" in (p.note or ""), p.note


def test_a_written_order_needs_no_note():
    p = _adjudicate(manhattan_length, "for x in R^n, f(x) ~= ||x||_1")
    assert "norm of" not in (p.note or ""), p.note


def test_the_call_spelling_gets_the_same_note_in_its_own_spelling():
    p = _adjudicate(euclidean_length, "for x in R^n, f(x) ~= norm(x)")
    assert "norm(x) is the Euclidean norm of x" in (p.note or ""), p.note
    assert "||x||" not in (p.note or ""), p.note
    p = _adjudicate(frobenius, "for A in R^(m,n), f(A) ~= norm(A)")
    assert "norm(A) is the Frobenius norm of A" in (p.note or ""), p.note


def test_the_call_with_an_order_written_needs_no_note():
    p = _adjudicate(manhattan_length, "for x in R^n, f(x) ~= norm(x, 1)")
    assert "norm of" not in (p.note or ""), p.note


# --- the lexicon rows -----------------------------------------------------

#: every row of the sugar, with the verdict and route it reaches
#: against its example function; the trap row falsifies with a witness
_LEXICON_ROWS = {
    "norm_bars_euclidean": ("proven", "derive"),
    "norm_bars_two": ("proven", "derive"),
    "norm_bars_one": ("proven", "derive"),
    "norm_bars_inf": ("proven", "derive"),
    # a whole-number order other than 1 and 2 has no lowering
    "norm_bars_integer_order": ("holds", "probe"),
    # a chain of orders and the triangle inequality need Cauchy-Schwarz
    # or a bound on a root of a sum of squares, which no lemma states
    "norm_bars_chain": ("holds", "probe"),
    "norm_bars_homogeneous": ("proven", "derive"),
    "norm_bars_homogeneous_sign_trap": ("falsified", "probe"),
    "norm_bars_unit_vector": ("proven", "derive"),
    "norm_bars_direction": ("proven", "derive"),
    "norm_bars_distance": ("proven", "derive"),
    "norm_bars_distance_symmetric": ("proven", "derive"),
    "norm_bars_triangle": ("holds", "probe"),
    # a boolean equality: the derive route does not read a comparison
    # inside a body
    "norm_bars_stopping_criterion": ("holds", "probe"),
    "norm_bars_nearest_distance": ("holds", "probe"),
    "norm_bars_nearest_distance_trap": ("falsified", "probe"),
    "norm_bars_series_tracking_error": ("proven", "derive"),
    "norm_bars_rmse": ("proven", "derive"),
    "norm_bars_portfolio_weights": ("proven", "derive"),
    # proven from numpy 2.4, where `numpy.dot` has a definition row
    "norm_bars_squared": _SQUARED,
    "norm_bars_squared_trap": ("falsified", "probe"),
    "norm_bars_order_trap": ("falsified", "probe"),
    "matrix_norm_bars_frobenius": ("proven", "derive"),
    "matrix_norm_bars_gram_trace": ("proven", "derive"),
    # the matrix orders stay with the probe, and a singular value
    # decomposition has no definition row
    "matrix_norm_bars_one": ("holds", "probe"),
    "matrix_norm_bars_inf": ("holds", "probe"),
    "matrix_norm_bars_order_trap": ("falsified", "probe"),
    "matrix_norm_bars_spectral": ("holds", "probe"),
    "matrix_norm_bars_spectral_below_frobenius": ("holds", "probe"),
}


def test_every_sugar_row_of_the_lexicon_is_pinned_here():
    from mathema.lexicon import LEXICON
    sugar_rows = {key for key in LEXICON if "norm_bars" in key}
    assert sugar_rows == set(_LEXICON_ROWS)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("key, verdict, route", sorted(
    (key, *want) for key, want in _LEXICON_ROWS.items()))
def test_each_lexicon_row_reaches_its_pinned_verdict(key, verdict, route):
    from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON, SECTIONS, TAGS
    (fn,) = [fn for fn, keys in EXAMPLE_FUNCTIONS.values() if key in keys]
    assert key in SECTIONS["linear_algebra"]
    assert "norm" in TAGS[key]
    p = _adjudicate(fn, LEXICON[key])
    assert (p.verdict, p.route) == (verdict, route), (p.verdict, p.note)
    if verdict == "falsified":
        assert p.counterexample, p.note
    assert_round_trips(LEXICON[key], fn)


def test_the_trap_row_names_the_two_numbers_that_differ():
    from mathema.lexicon import LEXICON
    p = _adjudicate(manhattan_length, LEXICON["norm_bars_order_trap"])
    assert p.verdict == "falsified"
    assert " vs " in str(p.counterexample), p.counterexample


def test_the_triangle_inequality_fails_with_the_wrong_norms():
    # the control for the triangle row: the same distance is not bounded
    # by the sum of the largest magnitudes, and a witness says so
    from mathema._lexicon_numpy import distance as lexicon_distance
    p = _adjudicate(lexicon_distance,
                    "for x in R^n, y in R^n, f(x, y) <= ||x||_inf + ||y||_inf")
    assert p.verdict == "falsified" and p.counterexample, (p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
def test_the_unit_vector_row_needs_its_premise_for_the_zero_vector():
    # without the premise the zero vector divides by zero; the probe
    # over R^n does not draw that one point, so the row states the
    # premise rather than leaning on the draw
    from mathema._lexicon_numpy import unit_vector
    from mathema.lexicon import LEXICON
    law = LEXICON["norm_bars_unit_vector"]
    assert law.startswith("assuming ||x|| > 0, ")
    p = _adjudicate(unit_vector, law)
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    with pytest.raises(FloatingPointError):
        with np.errstate(all="raise"):
            unit_vector(np.zeros(3))


def test_the_lexicon_rows_carry_the_documented_tags():
    from mathema.lexicon import TAGS
    assert "euclidean" in TAGS["norm_bars_euclidean"]
    assert "frobenius" in TAGS["matrix_norm_bars_frobenius"]
    assert "subscript" in TAGS["norm_bars_one"]
