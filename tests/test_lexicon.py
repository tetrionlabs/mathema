# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Coverage over `mathema.lexicon`: every entry parses and renders
without raising, both rendered forms match a golden snapshot
(`data/lexicon_golden.json`), and every row with an example function
lands on its pinned verdict (`PINNED`). The snapshot is a
characterization net; it pins current behavior so refactors can't shift
rendered output unnoticed, not a sign-off of the spellings, which are
still under review; a deliberate rendering change regenerates it (see
`test_rendered_output_matches_golden_snapshot`) with the diff reviewed
as part of that change. The verdict table is the same kind of net for
adjudication: a row whose verdict moves is a change to review."""
import importlib.util

import pytest

from mathema import lexicon_checks
from mathema.conjecture import claim
from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON, get, render_both, show, sources
from mathema.spec import render_claim_text

#: mathema's own lexicon, never a registered package's
CORE = sources(extensions=False)[0]

#: the rows over a language, adjudicated only with `mathema-language`
#: installed; without it each is skipped with the reason
_LANGUAGE_ROWS = (
    "containment_absent", "language_alphabet", "language_closure",
    "language_contraction", "language_excluding_empty",
    "language_length_bound", "language_membership_symbol",
    "language_missing_excluded", "language_section",
)

#: the verdict every row with an example function lands on, or
#: `(verdict, text the witness contains)`
PINNED: dict = {
    "abs_bars": "falsified",
    "abs_bars_compound": "proven",
    "assuming_inequality": "proven",
    "assuming_is_defined": "proven",
    "assuming_is_defined_pinned": "proven",
    "assuming_is_defined_postfix": "proven",
    "assuming_named_claim": "skipped",
    "bound_function_nested_in_f": "proven",
    "certificate_convex_lower": "proven",
    "certificate_convex_upper": "proven",
    "ceil_div_lower_bound": "proven",
    "certificate_quadratic": "proven",
    "chained_comparison": "proven",
    "descent_converges": "proven",
    "dim_premise_pins_length": "proven",
    "dim_premise_rectangular_matrix": "holds",
    "dim_premise_square_matrix": "holds",
    "dim_premise_ties_two_lengths": "holds",
    "dim_premise_vector_bound": "holds",
    "domain_blackboard_reals": "proven",
    "domain_closed_interval": "proven",
    "domain_open_interval": "proven",
    "domain_subset_integer": "skipped",
    "domain_subset_symbol": "skipped",
    "finite_domain_discrete_set": "proven",
    "finite_domain_pinned": "proven",
    "finite_domain_small_range": "proven",
    "floor_brackets_unicode": "holds",
    "floor_div_evaluable": "proven",
    "forall_symbol": "proven",
    "greek_delta_lower": "proven",
    "greek_delta_upper": "proven",
    "inferred_literal_domain": "proven",
    "infinity_symbol": "proven",
    # two functions demonstrate the same row to opposite ends: numpy.clip
    # never leaks a nan, numpy.arcsin does past 1
    "is_compendium_safe": {"clipped_ratio": "holds",
                           "unguarded_arcsin": ("falsified", "output nan")},
    "is_compendium_safe_scoped": "holds",
    "latex_command_forall": "proven",
    "latex_equiv": "proven",
    "latex_geqslant": "proven",
    "latex_left_right_bars": "proven",
    "latex_leqslant": "proven",
    "latex_varepsilon": "proven",
    "latex_varphi": "proven",
    "let_alias": "proven",
    "let_alias_for_under_test": "proven",
    "let_free_var_closed": "skipped",
    "let_free_var_typed": "skipped",
    "matrix_determinant_bars_compound": "proven",
    "membership_interval_reduces_to_chain": "proven",
    "multiply_dot": "proven",
    "named_under_test": "proven",
    "odd_function": "proven",
    "parity_identity": "proven",
    "power_caret": "proven",
    "power_superscript": "proven",
    "power_superscript_negative": "proven",
    "premise_relates_two_params": "proven",
    "raises_typed": "skipped:misspecified",
    "real_domain_is_not_finite": "holds",
    "recurrence_identity": "proven",
    "relation_approx_unicode": "proven",
    "relation_eq": "falsified",
    "relation_le_unicode": "falsified",
    "sigmoid_bounded_above": "proven",
    "sigmoid_bounded_below": "proven",
    "sigmoid_density_integrates": "proven",
    "sigmoid_derivative": "proven",
    "sigmoid_limit_lower": "proven",
    "sigmoid_limit_upper": "proven",
    "sigmoid_symmetry": "proven",
    "sqrt_bare_radical": "proven",
    "sqrt_symbol": "proven",
    "stress_gauge_invariance": "proven",
    "table_column_attribute": "holds",
    "table_column_item": "holds",
    "table_columns_dot": "proven",
    "tolerance_eps_ascii": "proven",
    "tolerance_epsilon": "proven",
    "tolerance_epsilon_latex": "proven",
    "tolerance_epsilon_word": "proven",
    "vector_between_least_and_greatest": "proven",
    "vector_drawdown_bounds": "proven",
    "vector_running_maximum": "proven",
    # the space rows: a fixed size in a binding, the output's space, the
    # exclusion over a space, a premise against a fixed length
    "space_vector_real": "proven",
    "space_matrix": "proven",
    "space_vector_fixed": "holds",
    "space_vector_fixed_trap": "falsified",
    "space_vector_fixed_sketch": "proven",
    "space_matrix_fixed": "proven",
    "space_matrix_mixed": "holds",
    "space_output_wrong_shape": "falsified",
    "space_output_named": "holds",
    "space_excluded_fixed": ("falsified", "A of shape (31, 15)"),
    "space_excluded_by_construction": "proven",
    "dim_premise_against_fixed": "skipped",
    "let_scale_seq_sharpe_premise": "proven",
    "let_scale_seq_sharpe_trap": ("falsified", "returns=[0.0]"),
    "let_shift_seq_range": "holds",
    "let_shift_seq_mean_moves": "falsified",
    "assuming_spread_positive": "proven",
    "dim_call_premise": "holds",
}
if importlib.util.find_spec("mathema_language") is None:
    PINNED.update({key: "skipped" for key in _LANGUAGE_ROWS})


@pytest.mark.parametrize("key", list(LEXICON))
def test_every_entry_parses(key):
    claim(get(key))


@pytest.mark.parametrize("key", list(LEXICON))
def test_every_entry_renders_in_both_forms(key):
    cj = claim(get(key))
    render_claim_text(cj, unicode=True)
    render_claim_text(cj, unicode=False)


def test_get_accepts_name_or_index():
    assert get("relation_eq") == get(0)


def test_render_both_returns_input_and_both_rendered_forms():
    text, unicode_form, ascii_form = render_both("relation_eq")
    assert text == LEXICON["relation_eq"]
    assert isinstance(unicode_form, str) and isinstance(ascii_form, str)


def test_render_both_include_internal_adds_conjecture_fields():
    *_, internal = render_both("let_free_var_typed", include_internal=True)
    assert set(internal) == {"lhs", "relation", "rhs", "domain", "funcs", "free_vars"}
    assert internal["free_vars"] == frozenset({"c"})


def test_show_does_not_raise(capsys):
    show("relation_eq")
    show("let_free_var_typed", include_internal=True)
    assert "input:" in capsys.readouterr().out


@pytest.mark.parametrize("key", list(LEXICON))
def test_rendered_output_matches_golden_snapshot(key):
    """Characterization net for refactoring, not a sign-off of the
    spellings: both rendered forms of every entry must match
    `tests/data/lexicon_golden.json` exactly, so any change to the
    parse/render pipeline that shifts output is caught deliberately.
    When a rendering choice changes on purpose, regenerate the snapshot:

        python -c "import json; from mathema.lexicon import LEXICON, \\
            render_both; json.dump({k: dict(zip(('input', 'unicode', \\
            'ascii'), render_both(k))) for k in LEXICON}, \\
            open('tests/data/lexicon_golden.json', 'w'), \\
            ensure_ascii=False, indent=1)"

    and review the diff as part of the change."""
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "data", "lexicon_golden.json")
    with open(path) as fh:
        golden = json.load(fh)
    text, unicode_form, ascii_form = render_both(key)
    assert text == golden[key]["input"]
    assert unicode_form == golden[key]["unicode"]
    assert ascii_form == golden[key]["ascii"]


def test_example_functions_are_checkable_against_their_own_lexicon_keys():
    assert lexicon_checks.check_examples(CORE, every_row=False) == []


def test_every_spelling_is_a_render_parse_render_fixed_point():
    """The rendered claim is the canonical form, so rendering it,
    reparsing it and rendering again must land on the same text, in
    both modes. Without this a record drifts every time it passes
    through the store, and a statement stops denoting its claim.

    Three spellings failed this when it was written: a domain with an
    excluded point would not reparse at all, and the bare `N`/`C`
    domains gained a spurious `⊂ ℝ` on the second pass (false for ℂ
    besides). All three were one cause, the trailing `∪ {∅}`
    missing-value clause being absorbed by whatever preceded it.

    A fixed point alone is not enough: a display that reparses to a
    different claim can still render back to itself. So the reparsed
    display must also have the original's canonical text, the claim's
    identity.
    """
    drifted = lexicon_checks.check_fixed_point(CORE)
    assert not drifted, "rendered claims drift on reparse:\n" + "\n".join(drifted)


def test_a_rendered_domain_always_states_its_missing_policy():
    """Terse input, explicit output: nothing has to say anything about
    missing values, and a rendered domain always does."""
    from mathema.conjecture import claim
    from mathema.spec import render_claim_text

    allowed = claim("for x in [0,10], f(x) >= 0")
    assert "∪ {∅}" in render_claim_text(allowed, unicode=True)
    assert "|missing" in render_claim_text(allowed, unicode=False)

    excluded = claim("for x in [0,10] \\ {missing}, f(x) >= 0")
    assert "\\ {∅}" in render_claim_text(excluded, unicode=True)
    assert "|missing" not in render_claim_text(excluded, unicode=False)
    assert "\\ {missing}" in render_claim_text(excluded, unicode=False)

    from mathema.spec import canonical_claim_text
    for conjecture in (allowed, excluded):
        for unicode_mode in (True, False):
            shown = render_claim_text(conjecture, unicode=unicode_mode)
            assert canonical_claim_text(claim(shown)) == \
                canonical_claim_text(conjecture)
    assert lexicon_checks.check_missing_policy(CORE) == []


def test_every_spelling_survives_the_declared_store():
    """The render round trip is not enough on its own: a claim also
    goes out to `claims.yaml` through `declare()` and comes back
    through `entry_claims()`, and that path lost four different things
    before anyone noticed; an `assuming` premise, a `let g = <path>`
    binding, a `let c be [...]` free variable, and the second half of a
    chained comparison. Each loss made the store hold a weaker claim
    than the one written, and two of them made `adjudicate_target` and
    `verify_project` disagree about the same function.

    Every spelling the lexicon documents is checked here, so a section
    added to the grammar later cannot quietly skip the store."""
    lost = lexicon_checks.check_declared_store(CORE)
    assert not lost, "the declared store loses part of the claim:\n" + "\n".join(lost)


def test_the_renderer_is_total_by_verbatim_preservation():
    """A subtree with no sympy model (a subscript, a string literal, an
    unknown call) renders as its exact source spelling and re-parses to
    itself, in both output modes; the renderer's job is spelling,
    never validation, so no claim that parses is refused a rendering."""
    from mathema.conjecture import claim
    from mathema.spec import render_claim_text

    for law in ("f(x, 1.0) == x[-1]",
                'f(r, "linear") == 1 - r',
                "for xs in [1, 5], f(xs) >= xs[-1]"):
        cj = claim(law)
        for unicode in (False, True):
            text = render_claim_text(cj, unicode=unicode)
            again = render_claim_text(claim(text), unicode=unicode)
            assert text == again, (law, unicode, text, again)


def test_a_malformed_outcome_arrow_errors_instead_of_joining_the_rhs():
    """`f(x) > 0 => f(2*x) > 0` is not outcome grammar (that takes
    `=> self.<claim>`), and before this check the arrow and everything
    after it silently became part of `rhs`, a different claim than
    the author wrote, discovered only as a SyntaxError at render or
    adjudication time."""
    import pytest

    from mathema.conjecture import InvalidConjecture, claim

    for law in ("f(x) > 0 => f(2*x) > 0", "f(x) > 0 --> f(2*x) > 0"):
        with pytest.raises(InvalidConjecture, match="outcome clause"):
            claim(law)
    # the two legitimate arrow shapes are untouched
    assert claim("f(x) > 0 => self.ok").outcome == "self.ok"
    assert claim(
        "assuming f is defined --> b != 0, f(a, b) * b == a"
    ).assuming.startswith("assuming")


def test_sections_partition_the_lexicon():
    """`SECTIONS` is the lexicon's exact table of contents: every key
    in exactly one section, no key invented, so `entries("domains")`
    can never silently under-cover the grammar it names."""
    from mathema.lexicon import LEXICON, entries

    assert lexicon_checks.check_sections(CORE) == []
    assert entries(extensions=False) == dict(LEXICON)
    import pytest as _pytest
    with _pytest.raises(KeyError, match="unknown lexicon section"):
        entries("no-such-section")


@pytest.mark.needs_full_proof_budget
def test_every_paired_spelling_survives_the_verified_record():
    """The verified-layer half of the store round trip: adjudicate,
    take exactly what the record row would carry (canonical statement
    plus the structured fields), reconstruct a declared claim from it
    the way `verify` repopulates one, and re-adjudicate. The verdict
    must not move. The absence of this invariant is how a committed
    store could contradict itself on the second run: the record held a
    weaker claim than the one adjudicated, and nothing noticed until a
    field run did."""
    _ROW_STILL_DRIFTS = {"bound_function_nested_in_f"}
    drift = lexicon_checks.check_verified_record(CORE, skip=_ROW_STILL_DRIFTS)
    for key, (_before, after, p2, _statement) in \
            lexicon_checks.verified_record_verdicts(CORE).items():
        if key not in _ROW_STILL_DRIFTS:
            continue
        # the one known, tracked drift. Its BINDING half is now closed:
        # canonical text keeps real function names, so a scope-bound
        # second function rebinds from f's module on reconstruction
        # rather than arriving as an orphan short name that resolves to
        # nothing. What is left is narrower and is not a lost reference:
        # the reconstructed expression is a harder one for the derive
        # route, which returns `undecided` where the original proved.
        # Pinned exactly, not tolerated.
        assert after == "unknown", (
            f"{key} now reaches {after!r}; the tracked drift changed, "
            f"re-examine it rather than editing this pin")
        assert p2.meta.get("mathema.derive_status") == "undecided", (
            f"{key} is unknown for a NEW reason ({p2.meta}); an "
            f"uncorroborated disproof here would be a different and more "
            f"serious problem")
    assert not drift, ("a record row adjudicates differently than the "
                       "claim it recorded:\n" + "\n".join(drift))


# --- finding an example without knowing its key -----------------------------

def test_tags_only_name_real_entries():
    """A tag on a key that no longer exists is a silent dead end in the
    search index, so the table is pinned as a subset of the lexicon."""
    unknown = lexicon_checks.check_tags(CORE)
    assert not unknown, f"TAGS names entries that do not exist: {unknown}"


def test_search_finds_an_entry_by_a_word_it_does_not_contain():
    """The point of the tags: a reader searches for the spoken name of a
    symbol or an everyday synonym, not the key."""
    from mathema.lexicon import search
    cases = {
        "modulo": "remainder_below_modulus",
        "round down": "floor_below_argument",
        "divide by zero": "is_pole_safe",
        "same length": "dim_premise_ties_two_lengths",
        "brute force": "finite_domain_pinned",
        "absolute value": "abs_bars",
        "fibonacci": "recurrence_identity",
    }
    for query, expected in cases.items():
        hits = [key for key, _law in search(query, limit=5)]
        assert expected in hits, (query, expected, hits)


def test_search_tolerates_a_typo():
    from mathema.lexicon import search
    assert "recurrence_identity" in [k for k, _ in search("fibonaci")]
    assert any(k.startswith("finite_domain")
               for k, _ in search("evry point"))


def test_search_returns_laws_that_are_really_in_the_lexicon():
    from mathema.lexicon import LEXICON, search
    for key, law in search("domain", limit=20):
        assert LEXICON[key] == law, key


def test_search_is_empty_for_a_query_that_matches_nothing():
    from mathema.lexicon import search
    assert search("") == []
    assert search("   ") == []
    assert search("zzzzqqqqxxxx") == []


def test_search_respects_its_limit():
    from mathema.lexicon import search
    assert len(search("domain", limit=3)) <= 3


def test_find_prints_the_hits(capsys):
    from mathema.lexicon import find
    find("modulo")
    out = capsys.readouterr().out
    assert "remainder_below_modulus" in out
    find("zzzzqqqqxxxx")
    assert "no lexicon entry matches" in capsys.readouterr().out


def test_every_spelling_has_a_stable_canonical_form():
    """The canonical rendering is a THIRD mode, distinct from the two
    display renderings, and it is the one that matters most: a record
    stores it and `claims_fingerprint` hashes it. If it is not a fixed
    point then a claim's identity changes merely by passing through the
    store, which reads as an edited claim and forces re-adjudication.

    The display-mode fixed-point test above does not cover this mode,
    which is how two lossy canonicalisations reached the store: `min(x)`
    collapsing to `x` (a strictly different, usually false assertion)
    and `∂σ` degrading into an ordinary quotient (a proven claim coming
    back unknown)."""
    drifted = lexicon_checks.check_stable_canonical(CORE)
    assert not drifted, ("canonical claim text drifts on reparse:\n"
                         + "\n".join(drifted))


def test_the_canonical_form_reaches_the_same_verdict_everywhere():
    """Text fidelity is necessary but not sufficient. A canonicalisation
    can be perfectly stable and still mean something else: `min(x) <=
    f(x)` collapsed to `x <= f(x)`, which re-rendered to itself forever
    while asserting something stronger and false.

    So for every spelling that has a function to be checked against,
    adjudicate the original and its canonical form and require the same
    verdict. This is the guard that catches a meaning-changing
    canonicalisation, which the fixed-point tests cannot see."""
    diverged = lexicon_checks.check_same_verdict(CORE)
    assert not diverged, ("a canonical form changed the verdict:\n"
                          + "\n".join(diverged))


def test_every_row_with_a_function_has_a_pinned_verdict():
    with_function = {key for _fn, keys in EXAMPLE_FUNCTIONS.values() for key in keys}
    unpinned = sorted(key for key in with_function
                      if key not in PINNED and key not in _LANGUAGE_ROWS)
    assert not unpinned, unpinned
    assert not sorted(set(PINNED) - set(LEXICON)), sorted(set(PINNED) - set(LEXICON))


@pytest.mark.needs_full_proof_budget
def test_every_row_lands_on_its_pinned_verdict():
    """The verdict table over the whole lexicon: a row with no example
    function is unpinned (None), one over a language is pinned only
    without `mathema-language`, every other row must land where the
    table says."""
    pytest.importorskip("numpy")
    expected = {**{key: None for key in LEXICON}, **PINNED}
    assert lexicon_checks.check_verdicts(CORE, expected) == []

