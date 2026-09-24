# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Coverage over `mathema.lexicon`: every entry parses and renders
without raising, and both rendered forms match a golden snapshot
(`data/lexicon_golden.json`). The snapshot is a characterization net;
it pins current behavior so refactors can't shift rendered output
unnoticed, not a sign-off of the spellings, which are still under
review; a deliberate rendering change regenerates it (see
`test_rendered_output_matches_golden_snapshot`) with the diff reviewed
as part of that change."""
import pytest

from mathema.conjecture import claim
from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON, get, render_both, show
from mathema.spec import render_claim_text


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
    from mathema.conjecture import check_conjectures

    for fn, keys in EXAMPLE_FUNCTIONS.values():
        for key in keys:
            cj = claim(get(key), route="probe")
            check_conjectures(fn, [cj], extensive=False)


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
    """
    from mathema.conjecture import claim
    from mathema.lexicon import LEXICON
    from mathema.spec import render_claim_text

    drifted = []
    for name, law in LEXICON.items():
        try:
            conjecture = claim(law)
        except Exception:
            continue          # a spelling the grammar declines by design
        for unicode_mode in (True, False):
            once = render_claim_text(conjecture, unicode=unicode_mode)
            try:
                twice = render_claim_text(claim(once), unicode=unicode_mode)
            except Exception as exc:
                drifted.append(f"{name}: rendered text will not reparse "
                               f"({type(exc).__name__}): {once}")
                continue
            if once != twice:
                drifted.append(f"{name}:\n    {once}\n    {twice}")
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
    from mathema.conjecture import claim
    from mathema.lexicon import LEXICON
    from mathema.spec import canonical_claim_text, declare, entry_claims

    lost = []
    for name, law in LEXICON.items():
        original = claim(law)
        try:
            restored = entry_claims({"claims": [declare(original)]})[0]
        except Exception as exc:
            lost.append(f"{name}: will not reparse ({type(exc).__name__}: {exc})")
            continue
        for what, before, after in (
            ("statement", (original.lhs, original.relation, original.rhs),
                          (restored.lhs, restored.relation, restored.rhs)),
            ("links", original.links, restored.links),
            ("free_vars", set(original.free_vars), set(restored.free_vars)),
            ("funcs", set(original.funcs), set(restored.funcs)),
            ("assuming", original.assuming, restored.assuming),
            ("tolerance", original.tolerance, restored.tolerance),
            ("canonical text", canonical_claim_text(original),
                               canonical_claim_text(restored)),
        ):
            if before != after:
                lost.append(f"{name}: {what} {before!r} -> {after!r}")
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
    from mathema.lexicon import LEXICON, SECTIONS, entries

    seen: list[str] = []
    for keys in SECTIONS.values():
        seen.extend(keys)
    assert sorted(seen) == sorted(set(seen)), "a key appears twice"
    assert set(seen) == set(LEXICON)
    assert entries() == dict(LEXICON)
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
    from mathema.conjecture import check_conjectures, claim
    from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON
    from mathema.spec import entry_claims

    _ROW_STILL_DRIFTS = {"bound_function_nested_in_f"}
    drift = []
    for fname, (fn, keys) in EXAMPLE_FUNCTIONS.items():
        laws = [claim(LEXICON[k], name=k) for k in keys]
        probes = check_conjectures(fn, laws)
        for p in probes:
            row = {"name": p.name, "statement": p.statement,
                   "route": (p.route or "best").split(":", 1)[0]}
            if row["route"] not in ("derive", "probe"):
                row["route"] = "best"
            for field_name in ("domain", "grammar", "tolerance"):
                if getattr(p, field_name, None) is not None:
                    row[field_name] = getattr(p, field_name)
            try:
                (rebuilt,) = entry_claims({"claims": [row]})
            except Exception as exc:
                drift.append(f"{fname}/{p.name}: row will not reconstruct "
                             f"({type(exc).__name__}: {exc})")
                continue
            (p2,) = check_conjectures(fn, [rebuilt])
            if p.name in _ROW_STILL_DRIFTS:
                # the one known, tracked drift. Its BINDING half is
                # now closed: canonical text keeps real function names,
                # so a scope-bound second function rebinds from f's
                # module on reconstruction rather than arriving as an
                # orphan short name that resolves to nothing. What is
                # left is narrower and is not a lost reference: the
                # reconstructed expression is a harder one for the
                # derive route, which returns `undecided` where the
                # original proved. Pinned exactly, not tolerated.
                assert p2.verdict == "unknown", (
                    f"{p.name} now reaches {p2.verdict!r}; the tracked "
                    f"drift changed, re-examine it rather than editing "
                    f"this pin")
                assert p2.meta.get("mathema.derive_status") == "undecided", (
                    f"{p.name} is unknown for a NEW reason ({p2.meta}); "
                    f"an uncorroborated disproof here would be a "
                    f"different and more serious problem")
                continue
            if p2.verdict != p.verdict:
                drift.append(f"{fname}/{p.name}: {p.verdict} -> {p2.verdict}"
                             f" (statement {p.statement!r})")
    assert not drift, ("a record row adjudicates differently than the "
                       "claim it recorded:\n" + "\n".join(drift))


# --- finding an example without knowing its key -----------------------------

def test_tags_only_name_real_entries():
    """A tag on a key that no longer exists is a silent dead end in the
    search index, so the table is pinned as a subset of the lexicon."""
    from mathema.lexicon import LEXICON, TAGS
    unknown = sorted(set(TAGS) - set(LEXICON))
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
    from mathema.conjecture import claim
    from mathema.lexicon import LEXICON
    from mathema.spec import canonical_claim_text

    drifted = []
    for name, law in LEXICON.items():
        try:
            once = canonical_claim_text(claim(law))
        except Exception:
            continue          # a spelling the grammar declines by design
        try:
            twice = canonical_claim_text(claim(once))
        except Exception as exc:
            drifted.append(f"{name}: canonical text will not reparse "
                           f"({type(exc).__name__}): {once}")
            continue
        if once != twice:
            drifted.append(f"{name}:\n    {once}\n    {twice}")
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
    from mathema.conjecture import check_conjectures, claim
    from mathema.lexicon import EXAMPLE_FUNCTIONS, get
    from mathema.spec import canonical_claim_text

    diverged = []
    for fn, keys in EXAMPLE_FUNCTIONS.values():
        for key in keys:
            law = get(key)
            try:
                original = claim(law, route="probe")
                restored = claim(canonical_claim_text(original), route="probe")
            except Exception as exc:
                diverged.append(f"{key}: canonical form will not reparse "
                                f"({type(exc).__name__})")
                continue
            (before,) = check_conjectures(fn, [original], extensive=False)
            (after,) = check_conjectures(fn, [restored], extensive=False)
            if before.verdict != after.verdict:
                diverged.append(f"{key}: {before.verdict} -> {after.verdict}"
                                f"\n    {law}"
                                f"\n    {canonical_claim_text(original)}")
    assert not diverged, ("a canonical form changed the verdict:\n"
                          + "\n".join(diverged))
