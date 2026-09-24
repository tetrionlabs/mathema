# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Bugs found running mathema over a real repository.

Each test here is a report from the field, kept in its own file so the
provenance stays obvious: these are not shapes anyone designed, they
are what real code did.
"""
import numpy as np
import pytest

from mathema import check
from mathema.claims import check_conjectures, claim


def scaled(mi):
    """A fraction strictly below one."""
    return mi / (mi + 1.0)


def association_matrix(xs: list):
    """Outer product of a sequence with itself."""
    a = np.asarray(xs, dtype=float)
    if a.size == 0:
        raise ValueError("empty sequence")
    return np.outer(a, a)


def test_state_safety_ignores_a_global_that_cannot_compare_to_its_copy():
    """A module with `from __future__ import annotations` carries an
    `annotations` global bound to a `__future__._Feature`, which defines
    no `__eq__`. The check deep-copies module globals and compares, so
    the copy could never equal the original and every such module was
    reported as mutating it, with a witness whose before and after
    printed identically.

    This module has that import (numpy's namespace does too), so the
    check is live here."""
    probe = next(p for p in check(association_matrix, claims=["stateless"]).probes
                 if p.name == "is_state_safe")
    assert probe.verdict != "falsified", probe.counterexample


def test_an_elementwise_comparison_adjudicates_across_the_matrix():
    """An ndarray return makes `f(xs) >= 0` an array of comparisons;
    it is adjudicated ELEMENTWISE (the relation holds iff it holds at
    every element), not skipped as unanswerable. The outer product of
    values in [1, 10] is positive everywhere, so the claim holds."""
    probe = check_conjectures(
        association_matrix,
        [claim("for xs in [1,10], f(xs) >= 0", route="probe")])[0]
    assert probe.verdict == "holds"
    assert probe.route == "probe"


def test_a_chained_comparison_survives_the_store():
    """`0 <= f(x) < 1` was persisted as `0 <= f(x)`, so `adjudicate_target`
    falsified the claim while `verify_project`, reading the record,
    proved the weaker one that was stored."""
    from mathema.spec import declare, entry_claims

    original = claim("for mi in [0,100], 0 <= f(mi) < 1")
    stored = declare(original)
    assert "< 1" in stored["statement"], stored["statement"]
    assert entry_claims({"claims": [stored]})[0].links == original.links


def test_a_free_variable_keeps_its_bound_through_the_store():
    """`let c be [a,b]` lost its bound in the record, so the probe route
    sampled from +-1e6 and falsified with an out-of-domain error."""
    from mathema.spec import declare, entry_claims

    restored = entry_claims({"claims": [declare(
        claim("let c be [-5,5], for x in [0,10], f(x) + c >= 0"))]})[0]
    from mathema.domain import domain_contains

    assert set(restored.free_vars) == {"c"}
    bound = restored.domain["c"]
    assert domain_contains(-5.0, bound) and domain_contains(5.0, bound)
    assert not domain_contains(6.0, bound), "the bound was widened or lost"


@pytest.mark.parametrize("law", [
    "for mi in [0,100], 0 <= f(mi) < 1",
    "for mi in [1,100], 0 < f(mi) <= 1",
])
def test_both_halves_of_a_chain_are_adjudicated(law):
    """The point of keeping the chain: the second link has to be able to
    fail the claim."""
    probe = check_conjectures(scaled, [claim(law)])[0]
    assert probe.verdict in ("proven", "holds"), probe.counterexample


def test_a_claim_quantifier_supplies_the_derive_context(tmp_path, monkeypatch):
    """`derivable` asks what the derive route can do given the declared
    domain, and a claim declares its domain inline, `for theta in
    [0, 100], f(theta) >= 0`, which is the spelling the grammar
    teaches and every example uses. The context was being read off the
    claim dict's `domain` key instead, which only a claim mathema
    itself wrote ever has, so the common case supplied no context at
    all and a branchy function read underivable while its claims
    proved."""
    from mathema.audit import _claim_domain, audit_rows

    pkg = tmp_path / "geopkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "spiral.py").write_text(
        "def spiral_radius(theta, a):\n"
        '    """Archimedean spiral radius; negative angles mirror."""\n'
        "    if theta < 0:\n"
        "        return a * (-theta)\n"
        "    return a * theta\n")
    (tmp_path / "s.claims.yaml").write_text(
        "geopkg.spiral.spiral_radius:\n"
        "  claims:\n"
        "    - name: nonneg\n"
        '      statement: "for theta in [0, 100], a in [1, 2], f(theta, a) >= 0"\n')

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    from mathema.spec import load_declared
    entry = (load_declared(".").get("geopkg.spiral.spiral_radius") or {}).get("entry") or {}
    assert set(_claim_domain(entry)) == {"theta", "a"}, "inline quantifier not read"

    row = audit_rows(["geopkg"], root=".")[0]
    assert row["derivable"] is True, "a declared domain makes this derivable"
    assert row["unconditional"] is False, "the body still does not lift bare"


def test_a_docstring_claim_quantifier_supplies_the_derive_context(
        tmp_path, monkeypatch):
    """A `Claims:` block in the docstring is an authoring surface like a
    claims file: its quantifier is the context `mathema check` proves
    the claim with, so `derivable` reads it too."""
    from mathema.audit import audit_rows

    pkg = tmp_path / "geodoc"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "spiral.py").write_text(
        "def spiral_radius(theta, a):\n"
        '    """Archimedean spiral radius; negative angles mirror.\n'
        "\n"
        "    Claims:\n"
        "        nonneg: for theta in [0, 100], a in [1, 2], f(theta, a) >= 0\n"
        '    """\n'
        "    if theta < 0:\n"
        "        return a * (-theta)\n"
        "    return a * theta\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    row = audit_rows(["geodoc"], root=".")[0]
    assert row["derivable"] is True, "the docstring's domain makes this derivable"
    assert row["unconditional"] is False, "the body still does not lift bare"


def _lag_overlap(n, lag):
    """Overlapping sample count at a given lag."""
    return n - abs(lag)


def test_an_absolute_value_takes_the_sign_the_domain_fixes():
    """Reported as the one engine defect in a real run: a step claim on
    a lag-overlap function left `Abs(lag) - Abs(lag + 1) + 1` for the
    decider, sympy's `.equals()` answered "nonzero" (right for the whole
    real line, wrong for `lag >= 0`), a seeded numeric check contradicted
    it, and the corroboration guard correctly refused the disproof,
    leaving a real identity undecided.

    Two guards were working against each other: a transformed call
    argument (`f(n, lag + 1)`) turns the sign bake off, because
    pre-collapsing the body under it produces false disproofs, and the
    sign then never reached `Abs`. Resolving the absolute values on the
    already-formed difference is safe for the same reason baking is
    not, and closes the identity."""
    proven = check_conjectures(_lag_overlap, [claim(
        "for n in [1,100], lag in [0,10], f(n, lag+1) == f(n, lag) - 1",
        route="derive")])[0]
    assert proven.verdict == "proven", proven.note
    assert proven.route == "derive"


def test_the_same_claim_over_a_signed_domain_still_falsifies():
    """The identity genuinely fails below zero, so widening the domain
    must bring back a refutation, with a witness, not a symbolic
    assertion."""
    refuted = check_conjectures(_lag_overlap, [claim(
        "for n in [1,100], lag in [-10,10], f(n, lag+1) == f(n, lag) - 1",
        route="derive")])[0]
    assert refuted.verdict == "falsified"
    assert refuted.counterexample


def test_a_conjunction_over_a_finite_set_never_falsifies_without_a_witness(tmp_path):
    """Field report L3: `for r in [0,1], scale in {"info","linear"},
    d(f(r, scale), r) <= 0` came back refuted with no counterexample,
    while both single-scale restrictions proved and the property is
    numerically true. The rule stands: `falsified` requires an
    executed witness; an uncorroborated symbolic disproof downgrades
    to unknown. This pins the whole shape family on the derive route:
    the true conjunction proves piecewise, a false claim's
    falsification names its witness (and its sub-domain), and the
    undecidable variant says unknown rather than inventing a refutation."""
    import textwrap

    mod = tmp_path / "l3mod.py"
    mod.write_text(textwrap.dedent('''
        def distance_from_strength(r, scale):
            """Distance implied by a strength on a named scale."""
            if scale == "linear":
                return 1.0 - r
            return 1.0 - r * r
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("l3mod", mod)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    fn = m.distance_from_strength

    from mathema.conjecture import check_conjectures, claim

    (true_conj,) = check_conjectures(fn, [claim(
        'for r in [0, 1], scale in {"info", "linear"}, '
        'd(f(r, scale), r) <= 0', route="derive")])
    assert true_conj.verdict == "proven", (true_conj.verdict, true_conj.note)
    assert "each piece proven" in (true_conj.sketch or "")

    (false_conj,) = check_conjectures(fn, [claim(
        'for r in [0, 1], scale in {"info", "linear"}, '
        'f(r, scale) == 1 - r', route="derive")])
    assert false_conj.verdict == "falsified"
    assert false_conj.counterexample, "falsified requires an executed witness"
    assert "info" in str(false_conj.counterexample)

    for law in (
        'for r in [0, 1], scale in {"info", "linear"}, f(r, scale) >= 1',
        'for r in [0, 1], scale in {"info", "linear"}, '
        'd(f(r, scale), r) >= 0',
    ):
        (p,) = check_conjectures(fn, [claim(law, route="derive")])
        if p.verdict in ("falsified", "refuted"):
            assert p.counterexample, (law, p.verdict, p.note)
        else:
            assert p.verdict in ("unknown", "holds", "skipped"), (law, p.verdict)


def test_call_site_claims_accept_the_claims_file_row_shape():
    """Field report L9: `check(claims=[{"name", "statement", "route"}])`
    died with `AttributeError: 'dict' object has no attribute 'links'`
    from inside spec.declare. A dict now goes through the same
    construction a claims.yaml row does (spec._declared_conjecture),
    side `domain` field included, and gates like any call-site claim."""
    import mathema

    def halve(x: float) -> float:
        """Half of x."""
        return x / 2.0

    rec = mathema.check(halve, claims=[
        {"name": "shrinks", "statement": "for x in [0, 8], f(x) <= x",
         "route": "derive"},
        {"name": "bounded", "statement": "abs(f(x)) <= 4",
         "domain": {"x": [0.0, 8.0]}},
        "f(2.0) == 1.0",
    ])
    by_name = {p.name: p for p in rec.probes}
    assert by_name["shrinks"].verdict == "proven"
    assert by_name["bounded"].verdict in ("proven", "holds")
    # the side-field domain reached the claim: the canonical statement
    # states it inline
    assert "for x in [0.0, 8.0]" in by_name["bounded"].statement


def test_domain_variants_of_one_law_keep_distinct_rows(tmp_path):
    # L5: four domain-variants of one law auto-name alike (f_mi_ge_0,
    # the name is built from the domain-stripped statement); they must
    # not collapse to one row under the name-keyed merge, so unnamed
    # they are refused, and named they are four rows.
    import importlib.util
    import textwrap

    import mathema

    p = tmp_path / "ramp.py"
    p.write_text(textwrap.dedent('''
        def f(mi: float) -> float:
            """A clamp to [0, 1]."""
            return max(0.0, min(1.0, mi))
    '''))
    spec = importlib.util.spec_from_file_location("ramp", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    variants = [
        "for mi in [0,1], f(mi) >= 0",
        "for mi in [1,2], f(mi) >= 0",
        "for mi in [-1,0], f(mi) >= 0",
        "for mi in [2,3], f(mi) >= 0",
    ]
    def declared(rec):
        # the rows the claims themselves produce; each proof also
        # spawns its `[float]` companion row
        return [p for p in rec.probes
                if "mathema.companion_of" not in (p.meta or {})]

    # identical auto-names are refused, asking for explicit names
    from mathema.conjecture import InvalidConjecture, claim
    with pytest.raises(InvalidConjecture, match="explicit name"):
        mathema.check(mod.f, claims=variants)
    named = [claim(v, name=f"v{i}") for i, v in enumerate(variants)]
    rows = declared(mathema.check(mod.f, claims=named))
    assert len(rows) == 4                          # four distinct rows kept
    assert len({p.name for p in rows}) == 4        # each with its own name

    # exact duplicates (same statement AND domain) still collapse to one
    assert len(declared(mathema.check(
        mod.f, claims=["f(mi) >= 0", "f(mi) >= 0"]))) == 1
    # a single domain claim keeps its plain auto-name (no suffix)
    (only,) = declared(mathema.check(
        mod.f, claims=["for mi in [0,1], f(mi) >= 0"]))
    assert only.name == "f_mi_ge_0"
