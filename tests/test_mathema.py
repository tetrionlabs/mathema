# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
import math

import pytest

import mathema
from mathema.analysis import analyze_source, get_tree
from mathema.identity import form_hash


# ---- example functions under test -----------------------------------------

def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def total(xs: list) -> float:
    t = 0.0
    for v in xs:
        t += v
    return t


def normalize_positive(xs: list) -> list:
    return [v for v in xs if v > 0]


def doubled(xs: list) -> list:
    return [2 * v for v in xs]


def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def chatty(x: float) -> float:
    print("computing", x)
    return x * 2


def add(a: float, b: float) -> float:
    return a + b


def clamp01(x: float) -> float:
    return min(max(x, 0.0), 1.0)


# ---- identity ----------------------------------------------------------

def test_form_hash_ignores_names():
    def f1(x, alpha):
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    def f2(prices, decay):
        """Docstrings differ too."""
        level = prices[0]
        for price in prices[1:]:
            level = decay * price + (1 - decay) * level
        return level

    _, t1 = get_tree(f1)
    _, t2 = get_tree(f2)
    assert form_hash(t1) == form_hash(t2)

    def f3(prices, decay):  # genuinely different op
        level = prices[0]
        for price in prices[1:]:
            level = decay * price - (1 - decay) * level
        return level

    _, t3 = get_tree(f3)
    assert form_hash(t1) != form_hash(t3)


def test_form_hash_ignores_except_handler_names():
    def f1(x):
        try:
            return 1 / x
        except ZeroDivisionError as exc:
            raise ValueError("x must be nonzero") from exc

    def f2(x):
        try:
            return 1 / x
        except ZeroDivisionError as err:
            raise ValueError("x must be nonzero") from err

    _, t1 = get_tree(f1)
    _, t2 = get_tree(f2)
    assert form_hash(t1) == form_hash(t2)


# ---- analysis ------------------------------------------------------------

def test_fold_detected():
    facts = analyze_source(ema)
    folds = [loop for loop in facts.loops if loop.kind == "fold"]
    assert len(folds) == 1
    assert folds[0].acc == "y"
    assert facts.is_pure
    assert facts.param_kinds["x"] == "sequence"
    assert facts.param_kinds["alpha"] == "scalar"


def test_comprehensions_detected():
    f = analyze_source(normalize_positive)
    assert "filter" in f.comprehensions
    m = analyze_source(doubled)
    assert "map" in m.comprehensions


def test_recursion_and_effects():
    assert analyze_source(factorial).recursion
    c = analyze_source(chatty)
    assert not c.is_pure
    assert any("print" in e for e in c.effects)


def test_analyze_sets_tier_from_purity():
    assert mathema.analyze(ema).tier == 2
    assert mathema.analyze(chatty).tier == 3


# ---- probing (built-in algebraic laws) ------------------------------------

def test_add_probes():
    # add is trivially liftable, so commutative/associative/is_reproducible
    # are now proof-strength evidence (route="derive") rather than
    # probed, suggest_claims()'s route="best" claims prefer a proof
    # whenever one is available.
    r = mathema.check(add)
    probes = {p.name: p for p in r.probes}
    assert probes["commutative"].verdict == "proven"
    assert probes["commutative"].route == "derive"
    assert probes["associative"].verdict == "proven"
    assert probes["associative"].route == "derive"
    assert probes["is_deterministic"].verdict == "proven"
    # a safety-family verdict reports the examine route: the fact was
    # established structurally (the body lifts)
    assert probes["is_deterministic"].route == "examine"


def test_clamp_idempotent_monotone():
    # "monotone" no longer exists as its own claim, superseded by
    # suggest_claims()'s own monotonic_increasing[x]/monotonic_decreasing[x]
    # (derivative-sign based, strictly more precise than the retired
    # two-random-points check). clamp01 lifts trivially, so idempotent
    # proves rather than merely holds.
    r = mathema.check(clamp01)
    probes = {p.name: p for p in r.probes}
    assert probes["idempotent"].verdict == "proven"
    assert probes["idempotent"].route == "derive"


def test_clamp_monotone_falls_back_to_probing_when_derive_cant_settle_it():
    # clamp01 is genuinely non-decreasing everywhere (slope 0 or 1) but
    # not non-increasing (slope 1 in the unclamped middle). Derive
    # can't settle either (a Heaviside-gated Min/Max sympy can't decide
    # the sign of), so route="best" falls back to the registered
    # monotonic_increasing/monotonic_decreasing families' own
    # probe:algorithmic (pairwise-sampling) technique, a real
    # empirical fallback, not a skip.
    r = mathema.check(clamp01)
    probes = {p.name: p for p in r.probes}
    assert probes["monotonic_increasing[x]"].verdict == "holds"
    assert probes["monotonic_increasing[x]"].route == "probe:algorithmic"
    assert probes["monotonic_decreasing[x]"].verdict == "falsified"
    assert probes["monotonic_decreasing[x]"].route == "probe:algorithmic"
    assert probes["monotonic_decreasing[x]"].counterexample is not None


def test_ema_order_sensitivity_falsified():
    r = mathema.check(ema)
    perm = next(p for p in r.probes if p.name == "permutation_invariant")
    assert perm.verdict == "falsified"
    assert perm.counterexample is not None


def test_total_seq_probes_hold():
    # "bounded" split into bounded_lower/bounded_upper (one relation per
    # claim, since Conjecture.relation is a single relation, not a
    # chain). Both are falsified for a plain sum: a sum of several
    # positive values exceeds max(x), and a sum with enough negative
    # values falls below min(x), real, not the same failure twice.
    r = mathema.check(total)
    verdicts = {p.name: p.verdict for p in r.probes}
    assert verdicts["permutation_invariant"] == "holds"
    # proven, not holds: the elementwise transform composes through
    # the fold's closed form on the derive route now
    assert verdicts["scale_equivariant"] == "proven"
    assert verdicts["bounded_lower"] == "falsified"
    assert verdicts["bounded_upper"] == "falsified"


def test_effectful_tier3_probing_skipped():
    r = mathema.check(chatty)
    assert r.facts.tier == 3
    assert any(p.verdict == "skipped" for p in r.probes)


def test_parity_probes():
    # both trivially lift, so even/odd are proven/derive, not
    # holds/falsified via probing.
    def sq(x: float) -> float:
        return x * x

    def cube(x: float) -> float:
        return x * x * x

    # a falsified derive verdict is now corroborated against the real
    # function, seeded by derive's own witness, so its route is
    # probe:semi_analytical (a probe reproduction guided by the
    # analytical result), while a proof stays plain derive.
    ps = {p.name: p for p in mathema.check(sq).probes}
    assert ps["even"].verdict == "proven" and ps["even"].route == "derive"
    assert ps["odd"].verdict == "falsified"
    assert ps["odd"].route == "probe:semi_analytical"
    pc = {p.name: p for p in mathema.check(cube).probes}
    assert pc["odd"].verdict == "proven" and pc["odd"].route == "derive"
    assert pc["even"].verdict == "falsified"
    assert pc["even"].route == "probe:semi_analytical"


def test_trials_budget_is_configurable():
    def double(x: float) -> float:
        return 2 * x

    r = mathema.check(double, trials=10)
    # a falsification stops at its first witness, so its n counts the
    # trials run up to it, never more than the budget
    assert all(p.n == 10 for p in r.probes
               if p.n and p.verdict != "falsified")
    assert all(p.n <= 10 for p in r.probes if p.n)


def test_pole_detected_empirically():
    # is_numerically_stable is now a claim (mathema.f.finite_no_error,
    # boolean-as-int over the claim grammar's own equality check), not
    # its own hardcoded message builder; the counterexample is the
    # generic "args: lv vs rv" shape ("(1): 0 vs 1", not the old prose
    # "x=1.0 (division by zero)"), a real but minor loss of message
    # detail traded for going through the same adjudication path as
    # every other claim. route is "probe:semi_analytical": the pole at
    # x=1 is analytically discovered and guaranteed-sampled, not found
    # by chance.
    def reciprocal_gap(x: float) -> float:
        return 1 / (1 - x)

    r = mathema.check(reciprocal_gap)
    st = next(p for p in r.probes if p.name == "is_numerically_stable")
    assert st.verdict == "falsified"
    assert st.route == "probe:semi_analytical"
    assert "0 vs 1" in st.counterexample


def test_domain_boundary_sampling_hits_edge_poles():
    # route="probe" pinned explicitly (not suggest_claims()'s own
    # route="best" default) so this keeps testing critical-point-
    # informed *sampling* reaching an edge pole specifically,
    # unaffected by is_numerically_stable's own registered derive route
    # (which now also correctly proves this domain unsafe; see
    # test_domain_boundary_edge_pole_provably_unsafe_via_derive below).
    from mathema.conjecture import check_conjectures, claim

    def edge_pole(x: float) -> float:
        return 1 / x

    results = check_conjectures(
        edge_pole, [claim("g(f, x) == 1", name="is_numerically_stable", route="probe",
                          funcs={"g": "mathema.f.finite_no_error"})],
        domain={"x": (0.0, 2.0)})  # pole at the edge
    st = results[0]
    assert st.verdict == "falsified"
    assert st.route == "probe:semi_analytical"


def test_domain_boundary_edge_pole_provably_unsafe_via_derive():
    def edge_pole(x: float) -> float:
        return 1 / x

    r = mathema.check(edge_pole, domain={"x": (0.0, 2.0)})  # pole at the edge
    st = next(p for p in r.probes if p.name == "is_numerically_stable")
    assert st.verdict == "falsified"
    assert st.route == "examine"


# ---- declared domain vs enforced domain ------------------------------------

def test_domain_restricts_probes_and_reports_enforcement():
    def ema2(x: list, alpha: float) -> float:
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    r = mathema.check(ema2, domain={"alpha": (0.0, 1.0)})
    vs = {p.name: p.verdict for p in r.probes}
    # the convex-combination certificate proves the bound outright
    # (the fold's weights are nonnegative and sum to 1 here); before
    # it, in-domain sampling could only reach holds
    assert vs["bounded_lower"] == "proven"
    assert vs["bounded_upper"] == "proven"
    # enforcement is not synthesized behind a mode any more: undeclared
    # means unreported; DECLARING excluded_outside_domain makes the
    # unenforced exclusion a real falsification with the witness
    assert not any(n.startswith("domain_enforced") for n in vs)
    declared = mathema.check(ema2, domain={"alpha": (0.0, 1.0)},
                             claims=["excluded_outside_domain(alpha)"])
    vs2 = {p.name: p for p in declared.probes}
    enf = vs2["excluded_outside_domain[alpha]"]
    assert enf.verdict == "falsified"
    assert "asserted, not enforced" in enf.counterexample


def test_domain_enforced_probe_extends_to_a_sequence_parameters_elements():
    # A sequence-typed parameter's declared element domain used
    # to be entirely unenforced (both by enforce_domain and by this
    # prober, which skipped every sequence-typed parameter outright);
    # this is the real, end-to-end confirmation that closing that gap
    # actually surfaces a violation for an unguarded function and
    # reports `holds` for a guarded one.
    from mathema.grammar import normalize, split_quantifier

    dom, _ = split_quantifier(normalize("for x in [0, 100] \\subset Z, True"))
    strict_domain = dom["x"]

    def unguarded_sum(xs: list) -> float:
        return sum(xs)

    r = mathema.check(unguarded_sum, domain={"xs": strict_domain},
                      claims=["excluded_outside_domain(xs)"])
    enf = next(p for p in r.probes
               if p.name == "excluded_outside_domain[xs]")
    assert enf.verdict == "falsified"

    def guarded_sum(xs: list) -> float:
        for v in xs:
            if v != v or not (isinstance(v, int) and 0 <= v <= 100):
                raise ValueError("out of domain")
        return sum(xs)

    r2 = mathema.check(guarded_sum, domain={"xs": strict_domain},
                       claims=["excluded_outside_domain(xs)"])
    enf2 = next(p for p in r2.probes
                if p.name == "excluded_outside_domain[xs]")
    assert enf2.verdict == "holds"


def test_guarded_function_holds_the_declared_exclusion():
    def ema_guarded(x: list, alpha: float) -> float:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha out of (0, 1]")
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    r = mathema.check(ema_guarded, domain={"alpha": (0.0, 1.0)},
                      claims=["excluded_outside_domain(alpha)"])
    enf = next(p for p in r.probes
               if p.name == "excluded_outside_domain[alpha]")
    assert enf.verdict == "holds"
    assert r.facts.guards["alpha"] == "raise"


def test_enforce_domain_auto_declares_the_exclusion_claim():
    # the decorator that MAKES out-of-domain rejection true also
    # DECLARES it: an @enforce_domain function carries the
    # excluded_outside_domain claim, proven structurally (rejection
    # by construction); there is no mode, no marker-driven default
    @mathema.enforce_domain({"alpha": (0.0, 1.0)})
    def ema2(x: list, alpha: float) -> float:
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    r = mathema.check(ema2, domain={"alpha": (0.0, 1.0)})
    enf = next(p for p in r.probes
               if p.name == "excluded_outside_domain[alpha]")
    assert enf.verdict == "proven"
    assert enf.route == "examine"
    assert "rejection by construction" in enf.sketch


# ---- documented intent, doc-only records for compiled callables -----------

def test_docstring_intent_and_references():
    def smooth(x: list, alpha: float) -> float:
        """Exponentially weighted smoothing of a series.

        Blends each new value with the running mean.

        References
        ----------
        .. [1] Wikipedia, "Exponential smoothing",
               https://en.wikipedia.org/wiki/Exponential_smoothing
        """
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    r = mathema.check(smooth)
    assert "Exponentially weighted smoothing" in r.facts.doc_intent
    assert any("wikipedia.org/wiki/Exponential_smoothing" in (u or "")
               for _, u, _via in r.facts.doc_refs)


def test_docstring_notes_block_and_intent_boundary():
    # regression: Intent:/Domain:/Notes: weren't recognized as summary
    # boundaries by intent.py's own header regex (only Claims:/Types:
    # were), so a docstring using the strict mathema schema without a
    # separate leading prose paragraph had its Notes: block text bleed
    # straight into doc_intent (and therefore into to_spec()'s own
    # written `intent` field).
    def half(x: float) -> float:
        """Halves x.

        Notes:
            Only tested for finite inputs. NaN handling is unspecified.
        """
        return x / 2

    facts = mathema.analyze(half)
    assert facts.doc_intent == "Halves x."
    assert facts.doc_notes == ("Only tested for finite inputs. "
                               "NaN handling is unspecified.")


def test_docstring_no_notes_block_is_none():
    def half(x: float) -> float:
        """Halves x."""
        return x / 2

    assert mathema.analyze(half).doc_notes is None


def test_doc_only_record_for_builtins():
    # a doc-only Facts (no real source, math.atan is a C builtin) has no
    # AST for suggest_claims() to read guard/param-kind information off
    # of, so its omitted-claims default is now an empty list rather
    # than probe()'s old hardcoded battery, which needed no source at
    # all since it called the live function directly. A real, known
    # trade-off: check() on a doc-only function reports nothing by
    # default today, not the previously-automatic odd/monotone coverage.
    r = mathema.check(math.atan)
    assert r.facts.tier == 0
    assert "arc tangent" in (r.facts.doc_intent or "")
    assert r.probes == []


# ---- @track_claims registry & the layered spec store -----------------------

def test_track_claims_no_wrapper_and_registered():
    def plain(x: float) -> float:
        return x + 1

    tagged_fn = mathema.track_claims(plain)
    assert tagged_fn is plain                      # no wrapper, same object
    key = f"{plain.__module__}.{plain.__qualname__}"
    assert plain.__mathema__["key"] == key
    assert mathema.tagged()[key] is plain


def test_spec_store_many_files_nearest_human_wins(tmp_path):
    def ema5(x: list, alpha: float) -> float:
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    from mathema.spec import load_specs, record

    root = str(tmp_path)
    # machine layer: one file per function
    record(mathema.check(ema5), key="pricing.ema5", root=root)
    record(mathema.check(ema5), key="risk.ema5", root=root)
    assert (tmp_path / ".mathema" / "verified" / "pricing.ema5.yaml").exists()
    assert (tmp_path / ".mathema" / "verified" / "risk.ema5.yaml").exists()

    specs = load_specs(root)
    assert specs["pricing.ema5"]["layer"] == "machine"
    assert specs["pricing.ema5"]["entry"]["identity"]["form"]

    # human layer at project root overrides the machine record
    (tmp_path / "claimspec.yaml").write_text(
        'pricing.ema5:\n  intent: "root-level intent"\n')
    # a deeper human file overrides the root one (nearest wins)
    (tmp_path / "pricing").mkdir()
    (tmp_path / "pricing" / "claimspec.yaml").write_text(
        'pricing.ema5:\n  intent: "nearest intent wins"\n')

    specs = load_specs(root)
    assert specs["pricing.ema5"]["layer"] == "human"
    assert specs["pricing.ema5"]["entry"]["intent"] == "nearest intent wins"
    assert specs["risk.ema5"]["layer"] == "machine"   # untouched key keeps machine record


def test_status_reports_fresh_and_stale(tmp_path):
    @mathema.track_claims
    def tracked(x: float) -> float:
        return 2 * x

    root = str(tmp_path)
    key = f"{tracked.__module__}.{tracked.__qualname__}"
    from mathema.spec import record
    record(mathema.check(tracked), key=key, root=root)
    assert "fresh" in mathema.status(root)

    # simulate the code changing after the spec was recorded
    p = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    p.write_text(p.read_text().replace(mathema.analyze(tracked).form, "deadbeef0000"))
    assert "STALE" in mathema.status(root)


def test_note_writes_spec_and_returns_record(tmp_path):
    r = mathema.write_spec(ema, root=str(tmp_path))
    assert r.spec_path and "ema" in r.spec_path


def test_note_writes_notes_block_into_meta(tmp_path):
    def half(x: float) -> float:
        """Halves x.

        Notes:
            Only tested for finite inputs. NaN handling is unspecified.
        """
        return x / 2

    r = mathema.write_spec(half, root=str(tmp_path))
    spec = r.to_spec()
    assert spec["meta"]["notes"] == ("Only tested for finite inputs. "
                                     "NaN handling is unspecified.")


def test_note_omits_meta_when_no_notes_block(tmp_path):
    r = mathema.write_spec(ema, root=str(tmp_path))
    # concepts now legitimately populate meta (ema's fold shape tags
    # summation); the pin narrows to what it always meant, no NOTES
    # key without a Notes: block
    assert "notes" not in (r.to_spec().get("meta") or {})


def test_record_meta_is_included_in_to_spec(tmp_path):
    r = mathema.write_spec(ema, root=str(tmp_path))
    r.meta["mathema.diagnostic_report"] = {"liftable": True}
    spec = r.to_spec()
    assert spec["meta"]["mathema.diagnostic_report"] == {"liftable": True}


def test_record_meta_and_docstring_notes_both_appear_without_clobbering(tmp_path):
    def half(x: float) -> float:
        """Halves x.

        Notes:
            Only tested for finite inputs.
        """
        return x / 2

    r = mathema.write_spec(half, root=str(tmp_path))
    r.meta["mathema.diagnostic_report"] = {"liftable": True}
    spec = r.to_spec()
    assert spec["meta"]["notes"] == "Only tested for finite inputs."
    assert spec["meta"]["mathema.diagnostic_report"] == {"liftable": True}


def test_probe_claim_carries_its_sampling_meta(tmp_path):
    # route="probe" pinned explicitly, not left to suggest_claims()'s
    # own route="best" default: ema lifts (it's fold-shaped), so an
    # unpinned "deterministic" claim would prove via derive today and
    # carry no sampling meta at all, an assertion that would silently
    # start failing the moment derive's own capability grows rather
    # than testing what this test actually means to test, the shape
    # of a probe-route claim's own record.
    cj = mathema.claim("f(x, alpha) == f(x, alpha)", name="deterministic", route="probe")
    r = mathema.write_spec(ema, claims=[cj], root=str(tmp_path))
    spec = r.to_spec()
    det = next(c for c in spec["claims"] if c["name"] == "deterministic")
    assert det["route"] == "probe"
    # a probe row carries its real probe data, the sampling meta; the
    # empty/derivable fields (note, sketch, and condition, which rides the
    # statement/domain on a probe row) are omitted rather than written as
    # placeholders
    assert det["meta"] and "mathema.sampling" in det["meta"]
    assert "note" not in det and "sketch" not in det and "condition" not in det
    assert (tmp_path / ".mathema" / "verified").exists()


def test_ipython_cell_magic(tmp_path, monkeypatch):
    pytest.importorskip("IPython")
    monkeypatch.chdir(tmp_path)
    from IPython.core.interactiveshell import InteractiveShell
    ip = InteractiveShell.instance()
    import mathema as _m
    _m.load_ipython_extension(ip)
    ip.run_cell_magic("mathema", "", "def cube(x: float) -> float:\n    return x*x*x\n")
    specs = list((tmp_path / ".mathema" / "verified").glob("*.yaml"))
    assert specs and "cube" in specs[0].name


# ---- the decoupled spec: reasoning chain, YAML shape -----------------------

def test_spec_decoupled_with_reasoning_chain(tmp_path):
    def ema4(x: list, alpha: float) -> float:
        """Exponentially weighted moving average."""
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    r = mathema.check(ema4)
    spec = r.to_spec()
    steps = [row["step"] for row in spec["reasoning"]]
    assert steps.index("intent") < steps.index("structure")
    assert "evidence" in steps and "refutation" in steps
    assert spec["math"] is None   # reserved, empty in v0.1
    # concepts populate now: ema4's fold shape tags summation
    assert "summation" in spec["concepts"]
    assert spec["lineage"]["CDD_spec_version"] == mathema.SPEC_VERSION
    p = r.save_spec(str(tmp_path / "ema4.yaml"))
    text = open(p).read()
    assert r.facts.form in text and "reasoning" in text and "ema4" in text


# ---- the conjecture pipeline -----------------------------------------------

def test_conjecture_pipeline_core():
    def cube(x: float) -> float:
        return x * x * x

    from mathema import Conjecture, check_conjectures
    results = check_conjectures(cube, [
        Conjecture("odd", "f(-x)", "-f(x)"),
        Conjecture("nonnegative", "f(x)", "0", relation=">="),
        Conjecture("shift_aux", "f(x + c)", "f(x) + c"),
        Conjecture("evil", "__import__('os')", "0"),
        Conjecture("attr", "f.__code__", "0"),
    ])
    by = {p.name: p for p in results}
    # default route is now "best": the cubic lifts, so oddness proves
    assert by["odd"].verdict == "proven"
    assert by["nonnegative"].verdict == "falsified" and by["nonnegative"].counterexample
    assert by["shift_aux"].verdict == "falsified"     # aux var sampled and reported
    assert "c=" in by["shift_aux"].counterexample
    assert by["evil"].verdict == "skipped" and "disallowed" in by["evil"].note
    assert "funcs=" not in by["evil"].note   # never suggest binding a dunder
    assert by["attr"].verdict == "skipped"
    # provenance rides meta, never note prose
    assert all((p.meta or {}).get("mathema.surface")
               for p in results if p.verdict != "skipped")


def test_conjecture_derive_route_proves_symbolically():
    def cube(x: float) -> float:
        return x * x * x

    from mathema import Conjecture, check_conjectures
    results = check_conjectures(cube, [Conjecture("odd", "f(-x)", "-f(x)", route="derive")])
    assert results[0].verdict == "proven"
    assert results[0].sketch is not None


def test_conjecture_derive_route_unliftable_is_skipped():
    # total = total * v is multiplicative in the accumulator (coeff_acc
    # depends on v, never identically 1), neither lift_fold() (needs
    # affine in item AND acc) nor lift_sum() (needs the update to be
    # exactly `acc + <anything>`, i.e. purely additive) recognize it, so
    # this stays a genuine, unrecognized-shape unliftable case.
    def looped(xs: list) -> float:
        total = 1.0
        for v in xs:
            total = total * v
        return total

    from mathema import Conjecture, check_conjectures
    results = check_conjectures(
        looped, [Conjecture("scale", "f(xs) * 2", "f(xs) * 2", route="derive")])
    # the loop stays unliftable (named in the note); the tautology then
    # holds empirically via the probe fallback
    assert results[0].verdict == "holds"
    assert "not derivable" in results[0].note


def test_claim_helper_strings():
    from mathema.claims import claim
    c = claim("f(-x) == -f(x)")
    assert c.lhs == "f(-x)" and c.rhs == "-f(x)" and c.relation == "=="
    c2 = claim("min(x) <= f(x, alpha)", name="lower")
    assert c2.name == "lower" and c2.relation == "<="

    def cube2(x: float) -> float:
        return x ** 3

    results = mathema.claims.check(cube2, ["f(-x) == -f(x)", "f(x) >= 0"])
    by = {p.name: p.verdict for p in results}
    assert by["f_x_f_x"] == "proven"           # auto-named; best-route proof
    assert list(by.values()).count("falsified") == 1


def test_check_accepts_claims_alongside_built_in_probes():
    # explicit claims= bypasses suggest_claims() entirely (unioned only
    # with declared_from_function(fn)), and probe()'s own remaining
    # unconditional battery is just domain_enforced[...] now, which
    # only appears when a domain is actually declared. Declaring one
    # here is what makes "alongside a built-in probe" true at all;
    # without it, cube's own claims=[...] call would report nothing
    # but the explicit claim.
    def cube(x: float) -> float:
        return x * x * x

    r = mathema.check(cube, claims=["f(x) >= 0",
                                    "excluded_outside_domain(x)"],
                      domain={"x": (0.0, 10.0)})
    by = {p.name: p.verdict for p in r.probes}
    # enforcement rides along only because it was DECLARED (cube never
    # guards, so the exclusion is asserted-not-enforced: falsified)
    assert by["excluded_outside_domain[x]"] == "falsified"
    assert by["f_x_0"] == "proven"   # x**3 >= 0 over [0, 10], best-route proof


# ---- claims file loader (authoring shape) ----------------------------------

def test_load_claims_parses_authoring_shape_and_skips_derive_route(tmp_path):
    from mathema.spec import load_claims

    f = tmp_path / "claims.yaml"
    f.write_text(
        "geo.dist:\n"
        "  intent: distance between two points\n"
        "  claims:\n"
        "    - name: symmetric\n"
        "      family: symmetry\n"
        "      law: \"d(p, q) == d(q, p)\"\n"
        "      route: derive\n"
        "    - name: nonneg\n"
        "      family: order\n"
        "      law: \"d(p, q) >= 0\"\n")

    loaded = load_claims(str(f))
    cs = {c.name: c for c in loaded["geo.dist"]}
    assert cs["symmetric"].route == "derive"
    assert cs["nonneg"].route == "best"        # default


# ---- CLI --------------------------------------------------------------------

def test_cli_check_ci_gate(tmp_path, capsys):
    f = tmp_path / "m.py"
    f.write_text(
        "def ema(x: list, alpha: float) -> float:\n"
        "    y = x[0]\n"
        "    for v in x[1:]:\n"
        "        y = alpha * v + (1 - alpha) * y\n"
        "    return y\n")
    from mathema.cli import main
    assert main(["check", str(f)]) == 0                       # lenient: passes
    out = capsys.readouterr().out
    assert "claims" in out and "falsified" in out
    # a DECLARED exclusion the code never guards -> a falsified claim
    # -> CI failure (no mode involved)
    assert main(["check", str(f), "--domain", "alpha=0:1",
                 "--claim", "excluded_outside_domain(alpha)"]) == 1
    out2 = capsys.readouterr().out
    assert "FAIL" in out2 and "falsified" in out2


def test_check_formats(tmp_path, capsys):
    f = tmp_path / "m.py"
    f.write_text(
        "def ema(x: list, alpha: float) -> float:\n"
        "    y = x[0]\n"
        "    for v in x[1:]:\n"
        "        y = alpha * v + (1 - alpha) * y\n"
        "    return y\n")
    from mathema.cli import main
    import json as _json

    rpt = tmp_path / "claims.json"
    # suggestions no longer count as claims: declare one explicitly so
    # the report has adopted content to verify
    assert main(["check", str(f), "--format", "json",
                 "--claim", "f(x, 1.0) == x[-1]",
                 "--output", str(rpt)]) == 0
    data = _json.loads(rpt.read_text())
    assert data["tool"] == "mathema" and data["CDD_spec_version"]
    assert data["functions"][0]["claims"] and data["totals"]["verified"] > 0

    assert main(["check", str(f), "--format", "junit"]) == 0
    out = capsys.readouterr().out
    assert "<testsuite" in out and 'failures="0"' in out
    import xml.dom.minidom
    xml.dom.minidom.parseString(out[out.index("<?xml"):])

    assert main(["check", str(f), "--format", "github",
                 "--domain", "alpha=0:1",
                 "--claim", "excluded_outside_domain(alpha)"]) == 1
    out = capsys.readouterr().out
    assert "::error title=mathema claim check::" in out

    assert main(["check", str(f), "--format", "md"]) == 0
    assert "| function |" in capsys.readouterr().out


def test_cli_status(tmp_path, capsys):
    f = tmp_path / "m.py"
    f.write_text(
        "import mathema\n\n"
        "@mathema.track_claims\n"
        "def double(x: float) -> float:\n"
        "    return 2 * x\n")
    from mathema.cli import main
    assert main(["verify", "--status", str(f), "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "no verified record" in out
