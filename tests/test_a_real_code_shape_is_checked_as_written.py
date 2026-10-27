# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Shapes ordinary code takes, each checked as written: a module global
with no equality, an array return compared elementwise, a chained
comparison and a bounded free variable kept through the store, a
claim's inline quantifier as the derive context, an absolute value
whose sign the domain fixes, a conjunction over a finite set, a claims
file row passed at the call site, and domain variants of one law.
"""
import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from mathema import check  # noqa: E402
from mathema.claims import check_conjectures, claim  # noqa: E402


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
    no `__eq__`, so a deep copy of it never compares equal to the
    original. is_state_safe does not read that as a write.

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
    """`0 <= f(x) < 1` is stored with both links, so what verify reads
    back from the record is the claim that was checked."""
    from mathema.spec import declare, entry_claims

    original = claim("for mi in [0,100], 0 <= f(mi) < 1")
    stored = declare(original)
    assert "< 1" in stored["statement"], stored["statement"]
    assert entry_claims({"claims": [stored]})[0].links == original.links


def test_a_free_variable_keeps_its_bound_through_the_store():
    """`let c be [a,b]` keeps its bound in the record, so a claim read
    back draws c from [a, b] only."""
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
    [0, 100], f(theta) >= 0`, the spelling the grammar teaches. That
    inline quantifier is the context, so a branchy function whose
    claims prove reads derivable."""
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
    """A step claim on a lag-overlap function leaves
    `Abs(lag) - Abs(lag + 1) + 1` to decide. It is nonzero somewhere on
    the real line but zero for every `lag >= 0`, where both absolute
    values take the sign the domain fixes: |lag + 1| = |lag| + 1. The
    absolute values are resolved on the formed difference, so the
    identity is proven over that domain."""
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
    """`for r in [0,1], scale in {"info","linear"}, d(f(r, scale), r) <= 0`
    is true on each scale (-1 and -2r), so the conjunction proves piece
    by piece. `falsified` requires an executed witness; an
    uncorroborated symbolic disproof is unknown. On the derive route the
    true conjunction proves piecewise, a false claim's falsification
    names its witness (and its sub-domain), and a variant derive cannot
    decide gives no refutation without a witness."""
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
    """`check(claims=[{"name", "statement", "route"}])` takes a dict as a
    claims.yaml row: it is built the way a claims file row is
    (spec._declared_conjecture), side `domain` field included, and gates
    like any call-site claim."""
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
    # four domain-variants of one law auto-name alike (f_mi_ge_0,
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
        # spawns its `[float]` companion row, and the record carries
        # the policy row mathema writes for the parameter
        return [p for p in rec.probes
                if "mathema.companion_of" not in (p.meta or {})
                and "mathema.policy" not in (p.meta or {})]

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
