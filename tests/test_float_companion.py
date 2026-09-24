# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A derive `proven` is the mathematics; the `[float]` companion is the
implementation.

Every claim the derive route proves spawns `<name>[float]`, its own
claim with its own verdict: the relation executed against the real
code in float, at the domain's corners and at sampled interior points,
unbounded directions reaching the claim's `|inf|` when one is declared
and a large magnitude otherwise. A raise, a NaN, or an inf or a loss of
precision where the relation fails falsifies the companion with that
point as its witness, and it gates `verify` like any claim.
`route="derive:math_only"` states the mathematics alone and spawns
nothing.
"""
import mathema
from mathema.conjecture import claim, check_conjectures
from mathema.spec import claims_fingerprint, to_spec
from mathema.verify import _union_verified_membership, gate


def _check(fn, law, **kw):
    kw.setdefault("route", "derive")
    rec = mathema.check(fn, claims=[claim(law, name="law", **kw)])
    return {p.name: p for p in rec.probes}, rec


def plus_one_minus(x: float) -> float:
    return (x + 1.0) - x


def doubled(x: float) -> float:
    return 2.0 * x


def all_nan(x: float) -> float:
    return float("nan") * x


def count_up(n: float) -> float:
    total = 0.0
    for _ in range(n):
        total += 1.0
    return total


def test_a_derive_proof_spawns_a_float_companion_that_holds():
    probes, _ = _check(doubled, "for x in [-10, 10], f(x) == 2*x")
    assert probes["law"].verdict == "proven"
    comp = probes["law[float]"]
    assert comp.verdict == "holds"
    assert comp.route == "probe"
    assert comp.statement == probes["law"].statement
    assert comp.n > 0
    assert comp.meta["mathema.companion_of"] == "law"
    assert probes["law"].meta["mathema.float_companion"] == "law[float]"


def test_precision_loss_falsifies_the_companion_not_the_proof():
    probes, _ = _check(plus_one_minus, "for x in [0, 1e300], f(x) == 1")
    assert probes["law"].verdict == "proven"
    comp = probes["law[float]"]
    assert comp.verdict == "falsified"
    assert comp.counterexample
    assert comp.stratum["mathematics"] == "sound"
    assert comp.stratum["blame"] == "implementation"


def test_nan_everywhere_falsifies_the_companion_over_an_unbounded_domain():
    probes, _ = _check(all_nan, "f(x) == f(x)")
    assert probes["law"].verdict == "proven"
    comp = probes["law[float]"]
    assert comp.verdict == "falsified"
    assert "NaN" in comp.sketch


def test_unbounded_direction_without_pseudo_infinity_reaches_a_large_magnitude():
    # (x + 1) - x collapses to 0 past 2^53, far beyond any moderate draw
    probes, _ = _check(plus_one_minus, "f(x) == 1")
    assert probes["law"].verdict == "proven"
    comp = probes["law[float]"]
    assert comp.verdict == "falsified"
    assert "1e+308" in comp.note


def test_a_declared_pseudo_infinity_bounds_the_companion():
    probes, _ = _check(plus_one_minus, "f(x) == 1", pseudo_infinity=100.0)
    assert probes["law[float]"].verdict == "holds"
    assert "|inf|" in probes["law[float]"].statement
    probes, _ = _check(plus_one_minus, "f(x) == 1", pseudo_infinity=1e17)
    assert probes["law[float]"].verdict == "falsified"


def test_math_only_opts_out_and_says_so():
    probes, rec = _check(plus_one_minus, "f(x) == 1",
                         route="derive:math_only")
    assert probes["law"].verdict == "proven"
    assert "law[float]" not in probes
    assert probes["law"].meta["mathema.float_companion"] == \
        "none (derive:math_only)"
    spec = to_spec(rec)
    row = next(r for r in spec["claims"] if r["name"] == "law")
    assert row["meta"]["mathema.float_companion"] == "none (derive:math_only)"


def test_a_probe_claim_spawns_no_companion():
    probes, _ = _check(doubled, "for x in [-10, 10], f(x) == 2*x",
                       route="probe")
    assert "law[float]" not in probes


def test_an_integer_domain_reaches_the_code_as_an_int():
    # range(n) raises TypeError on a float; the domain says n is an
    # integer, so every executed point, corners included, is an int
    probes, _ = _check(count_up, "for n in {2, 3, 4}, f(n) == n")
    assert probes["law"].verdict == "proven"
    assert probes["law[float]"].verdict == "holds", probes["law[float]"].sketch
    probes, _ = _check(count_up, "for n in [2, 10] ⊂ Z, f(n) == n")
    assert probes["law[float]"].verdict == "holds", probes["law[float]"].sketch


def test_the_integer_corners_are_ints():
    from mathema.gates import _point_evaluator
    from mathema.analysis import analyze_source
    for law in ("for n in {2, 3, 4}, f(n) == n",
                "for n in [2, 10] ⊂ Z, f(n) == n"):
        cj = claim(law)
        deps = _point_evaluator(cj, count_up, analyze_source(count_up), cj.domain,
                                {})
        for corner in deps["corners"]:
            assert type(corner["n"]) is int, (law, corner)


def test_a_falsified_companion_fails_the_gate():
    probes, _ = _check(plus_one_minus, "for x in [0, 1e300], f(x) == 1")
    report = gate(list(probes.values()), strict=False)
    assert report.falsified >= 1
    assert report.problems


def test_the_companion_is_recorded_but_never_membership():
    probes, rec = _check(plus_one_minus, "for x in [0, 1e300], f(x) == 1")
    spec = to_spec(rec)
    rows = {r["name"]: r for r in spec["claims"]}
    assert rows["law[float]"]["meta"]["mathema.companion_of"] == "law"
    assert rows["law[float]"]["verdict"] == "falsified"
    declared = [{"name": "law",
                 "statement": "for x in [0, 1e300], f(x) == 1",
                 "route": "derive"}]
    widened = _union_verified_membership(declared, spec)
    assert [c["name"] for c in widened] == ["law"]
    # the declared layer, and so the fingerprint, is the parent alone
    assert claims_fingerprint(widened) == claims_fingerprint(declared)


def test_check_conjectures_keeps_one_probe_per_claim_by_default():
    (p,) = check_conjectures(doubled, [claim("for x in [-10, 10], f(x) == 2*x",
                                             route="derive")])
    assert p.verdict == "proven"
    both = check_conjectures(doubled, [claim("for x in [-10, 10], f(x) == 2*x",
                                             name="law", route="derive")],
                             float_companions=True)
    assert [p.name for p in both] == ["law", "law[float]"]


def overflow_scale(x: float) -> float:
    return x * 1e300


def test_an_infinite_result_that_fails_the_relation_corroborates_a_disproof(
        monkeypatch):
    # every executed value on [1e9, 1e10] overflows to inf, which fails
    # `<= 1e308`: under the overflow rule that is a counterexample, not
    # an inconclusive point
    from mathema.symbolic import _proof_support as ps

    def disproof(lhs, rhs, diff, relation, domain, bound_context, params,
                 tolerance=1e-9):
        return ps.ProofResult("disproven", sketch="f(x) exceeds 1e308",
                              witness={"x": 1e10}, disproof_hint=None)

    monkeypatch.setitem(ps._RELATION_DECIDERS, "<=", disproof)
    (p,) = check_conjectures(overflow_scale, [claim(
        "for x in [1e9, 1e10], f(x) <= 1e308", route="derive")])
    assert p.verdict == "falsified"
    assert p.meta.get("mathema.corroboration") == "reproduced"
    assert (p.route or "").startswith(("derive", "probe:semi_analytical"))


def test_an_infinity_only_the_law_produces_stays_inconclusive():
    from mathema.analysis import analyze_source
    from mathema.gates import _point_evaluator
    cj = claim("for x in [1, 2], f(x) <= x * 1e308 * 10")
    deps = _point_evaluator(cj, doubled, analyze_source(doubled), cj.domain, {})
    assert deps["evaluate"]({"x": 1.5}) is None
    cj = claim("for x in [1e9, 1e10], f(x) <= 1e308")
    deps = _point_evaluator(cj, overflow_scale,
                            analyze_source(overflow_scale), cj.domain, {})
    assert deps["evaluate"]({"x": 1e10}) is False


def test_a_chain_proof_spawns_one_companion_folded_from_its_links():
    probes, _ = _check(plus_one_minus, "for x in [0, 1e300], 0.5 <= f(x) <= 1")
    assert probes["law"].verdict == "proven"
    comp = probes["law[float]"]
    assert comp.verdict == "falsified"
    assert comp.meta["mathema.companion_of"] == "law"
    assert comp.stratum["blame"] == "implementation"
    assert not any("link" in name for name in probes)
    probes, _ = _check(doubled, "for x in [0, 1], 0 <= f(x) <= 2")
    assert probes["law[float]"].verdict == "holds"


_STORE_FIXTURE = '''\
def plus_one_minus(x: float) -> float:
    """One, computed the long way round.

    Claims:
        one [derive]: for x in [0, 1e300], f(x) == 1
    """
    return (x + 1.0) - x
'''


def test_the_companion_round_trips_through_the_store_and_retires(
        tmp_path, monkeypatch):
    import yaml

    from mathema.acceptance import apply_acceptance, plan_acceptance
    from mathema.verify import verify_project
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "floatfix.py").write_text(_STORE_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = __import__("floatfix")
    mathema.write_spec(mod.plus_one_minus, root=str(tmp_path))
    path = tmp_path / ".mathema" / "verified" / "floatfix.plus_one_minus.yaml"

    def names():
        entry = yaml.safe_load(path.open())["floatfix.plus_one_minus"]
        return [c["name"] for c in entry["claims"]]

    assert names().count("one[float]") == 1
    from mathema.docstring import render_docstring
    rendered = render_docstring(mod.plus_one_minus, root=str(tmp_path))
    assert "one [derive]:" in rendered and "[float]" not in rendered
    first = verify_project(root=str(tmp_path), all=True)
    assert any("falsified" in p for p in first.problems)
    assert names().count("one[float]") == 1
    plan = plan_acceptance(str(tmp_path), "floatfix.plus_one_minus",
                           "one[float]", "discovery", by="turing")
    assert any("float companion of 'one'" in a for a in plan["actions"])
    apply_acceptance(plan)
    after = verify_project(root=str(tmp_path), all=True)
    assert after.problems == []
    assert not any("one[float]" in line for line in after.lines
                   if line.startswith("note"))
    assert "one" in names() and "one[float]" not in names()


def test_a_docstring_claim_can_opt_out_with_math_only():
    from mathema.authoring import parse_docstring_claims
    (row,) = parse_docstring_claims(
        "Claims:\n    exact [derive:math_only]: f(x) == 1\n")
    assert row["route"] == "derive:math_only"


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def test_a_family_claim_spawns_no_float_companion():
    from mathema import families
    rec = mathema.check(ema)
    probes = {p.name: p for p in rec.probes}
    registered = set(families.families())
    spawned = [n for n in probes if n.endswith("[float]")
               and n[:-len("[float]")].split("[", 1)[0] in registered]
    assert not spawned, spawned
    assert probes["is_deterministic"].meta["mathema.float_companion"] == \
        "none (a claim family adjudicates this claim)"
    for law in ("scale_equivariant", "translation_equivariant"):
        assert probes[law].verdict == "proven"
        assert probes[f"{law}[float]"].verdict == "falsified", law
