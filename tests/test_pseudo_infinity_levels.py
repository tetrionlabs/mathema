# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Pseudo-infinity at three levels (P6, P7, P8).

The operational infinity resolves claim (`let |inf| be`) > function (a
claims-file entry's `pseudo_infinity:` field, `check(fn,
pseudo_infinity=)`) > project (`MATHEMA_PSEUDO_INFINITY`) > the
carrier's maximum. It bounds only the computation, never a claim's
identity, and it is rendered, with its source, only where it bounds an
unbounded direction of the claim's effective domain."""
import math
import os
import subprocess
import sys
import textwrap

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.grammar import InvalidDomain


def sq(x):
    return x * x


def logistic(x):
    return 1 / (1 + math.exp(-x))


def _rows(fn, law, **kw):
    return {p.name: p for p in mathema.check(fn, claims=[law], **kw).probes}


def _proof_and_companion(fn, law, **kw):
    rows = _rows(fn, law, **kw)
    (comp,) = [p for p in rows.values()
               if (p.meta or {}).get("mathema.companion_of")]
    return rows[comp.meta["mathema.companion_of"]], comp


# --- the resolver ----------------------------------------------------------

def test_nothing_set_resolves_to_none_the_carrier_maximum():
    from mathema.records import resolve_pseudo_infinity
    assert resolve_pseudo_infinity(None, None) is None


def test_precedence_claim_over_function_over_environment(monkeypatch):
    from mathema.records import PseudoInfinity, resolve_pseudo_infinity
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e100")
    assert resolve_pseudo_infinity(None, None) == PseudoInfinity(
        1e100, "environment")
    assert resolve_pseudo_infinity(None, 1e50) == PseudoInfinity(
        1e50, "function")
    assert resolve_pseudo_infinity(30.0, 1e50) == PseudoInfinity(
        30.0, "claim")


def test_the_environment_is_read_at_call_time(monkeypatch):
    from mathema.records import resolve_pseudo_infinity
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e100")
    assert resolve_pseudo_infinity(None, None).value == 1e100
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e50")
    assert resolve_pseudo_infinity(None, None).value == 1e50


def test_an_invalid_environment_value_refuses_like_a_bad_let(monkeypatch):
    from mathema.records import resolve_pseudo_infinity
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "lots")
    with pytest.raises(InvalidDomain, match="expects a positive magnitude"):
        resolve_pseudo_infinity(None, None)
    with pytest.raises(InvalidDomain, match="expects a positive magnitude"):
        check_conjectures(sq, [claim("for x in R, f(x) >= 0")])
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "-5")
    with pytest.raises(InvalidDomain, match="finite positive magnitude"):
        resolve_pseudo_infinity(None, None)


def test_an_invalid_function_value_refuses():
    with pytest.raises(InvalidDomain, match="finite positive magnitude"):
        mathema.check(sq, claims=["for x in R, f(x) >= 0"],
                      pseudo_infinity=0)


def test_an_invalid_entry_field_is_refused_by_the_claims_file_check():
    from mathema.spec import ClaimsFileError, validate_claims_file
    with pytest.raises(ClaimsFileError, match="pseudo_infinity"):
        validate_claims_file({"m.sq": {"pseudo_infinity": "lots",
                                       "claims": []}}, "m.claims.yaml")
    validate_claims_file({"m.sq": {"pseudo_infinity": 1e100, "claims": []}},
                         "m.claims.yaml")


def test_operational_range_reads_the_resolved_value_first():
    from dataclasses import replace

    from mathema.records import PseudoInfinity, operational_range
    cj = claim("f(x) >= 0")
    assert operational_range(cj) is None
    resolved = replace(cj, resolved_pseudo_infinity=PseudoInfinity(
        1e100, "environment"))
    assert operational_range(resolved) == (-1e100, 1e100)
    assert operational_range(claim("let |inf| be 30, f(x) >= 0")) == (
        -30.0, 30.0)


# --- identity never depends on the environment (P7) ------------------------

def test_identity_is_the_same_with_and_without_a_resolved_value(monkeypatch):
    from dataclasses import replace

    from mathema.records import PseudoInfinity
    from mathema.spec import (canonical_claim_text, claims_fingerprint,
                              declare)
    law = "for x in R, f(x) >= 0"
    cj = claim(law, name="nonneg")
    text, decl = canonical_claim_text(cj), declare(cj)
    fp = claims_fingerprint([decl])
    resolved = replace(cj, resolved_pseudo_infinity=PseudoInfinity(
        1e100, "environment"))
    assert resolved == cj
    assert canonical_claim_text(resolved) == text
    assert declare(resolved) == decl
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e100")
    assert canonical_claim_text(claim(law, name="nonneg")) == text
    assert claims_fingerprint([declare(claim(law, name="nonneg"))]) == fp
    proof, companion = _proof_and_companion(sq, law)
    assert "inf|" not in proof.statement
    assert "inf|" not in companion.statement


# --- rendering: only what bounds something (P8) -----------------------------

def test_an_inert_binding_on_a_bounded_claim_is_dropped():
    from mathema.spec import canonical_claim_text, declare
    cj = claim("let |inf| be 30, for x in [0, 1], f(x) >= 0")
    assert "|inf|" not in canonical_claim_text(cj)
    assert "pseudo_infinity" not in declare(cj)
    assert "|inf|" not in declare(cj)["statement"]


def test_a_binding_that_bounds_a_direction_is_kept():
    from mathema.spec import canonical_claim_text, declare
    for law in ("let |inf| be 30, f(x) > 0",
                "let |inf| be 30, for x in [0, oo), f(x) > 0",
                "let |inf| be 30, for x in R, f(x) > 0"):
        cj = claim(law)
        assert "let |inf| be 30" in canonical_claim_text(cj), law
        assert declare(cj)["pseudo_infinity"] == 30.0, law


def test_nothing_about_infinity_when_every_direction_is_bounded(monkeypatch):
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e100")
    for route in ("best", "probe"):
        rows = {p.name: p for p in mathema.check(
            sq, claims=[claim("for x in [0, 1], f(x) >= 0", route=route)]
        ).probes}
        for p in rows.values():
            if p.name.startswith("f_x_ge_0") or "[float]" in p.name:
                assert "mathema.pseudo_infinity" not in (p.meta or {}), p
                assert "MATHEMA_PSEUDO_INFINITY" not in (p.note or ""), p
                assert "|inf|" not in (p.note or ""), p


# --- the sq demo: carrier, environment, function level ---------------------

@pytest.mark.needs_full_proof_budget
def test_sq_companion_falls_at_the_carrier_corner_with_no_setting():
    proof, companion = _proof_and_companion(sq, "for x in R, f(x) >= 0")
    assert proof.verdict == "proven"
    assert companion.verdict == "falsified", companion.note
    assert "e+308" in companion.counterexample, companion.counterexample
    assert "mathema.pseudo_infinity" not in (companion.meta or {})


@pytest.mark.needs_full_proof_budget
def test_sq_companion_holds_under_the_environment_value(monkeypatch):
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e100")
    proof, companion = _proof_and_companion(sq, "for x in R, f(x) >= 0")
    assert proof.verdict == "proven"
    assert companion.verdict == "holds", companion.note
    assert companion.meta["mathema.pseudo_infinity"] == {
        "value": 1e100, "source": "environment"}
    assert "let |inf| be 1e+100 (MATHEMA_PSEUDO_INFINITY)" in companion.note
    assert "inf|" not in companion.statement


@pytest.mark.needs_full_proof_budget
def test_sq_companion_holds_under_the_function_level_value():
    proof, companion = _proof_and_companion(
        sq, "for x in R, f(x) >= 0", pseudo_infinity=1e100)
    assert companion.verdict == "holds", companion.note
    assert companion.meta["mathema.pseudo_infinity"] == {
        "value": 1e100, "source": "function"}
    assert "let |inf| be 1e+100 (function level)" in companion.note


@pytest.mark.needs_full_proof_budget
def test_sq_companion_holds_under_the_declared_entry_field():
    declared = {"claims": [{"name": "nonneg",
                            "statement": "for x in R, f(x) >= 0"}],
                "pseudo_infinity": 1e100}
    rows = {p.name: p for p in mathema.check(sq, claims=[],
                                             declared=declared).probes}
    companion = rows["nonneg[float]"]
    assert companion.verdict == "holds", companion.note
    assert companion.meta["mathema.pseudo_infinity"] == {
        "value": 1e100, "source": "function"}


@pytest.mark.needs_full_proof_budget
def test_the_claim_level_value_renders_with_its_source():
    _proof, companion = _proof_and_companion(
        sq, "let |inf| be 1e100, for x in R, f(x) >= 0")
    assert companion.verdict == "holds", companion.note
    assert companion.meta["mathema.pseudo_infinity"] == {
        "value": 1e100, "source": "claim"}
    assert "let |inf| be 1e+100 (claim)" in companion.note


def test_the_probe_note_names_the_value_and_its_source(monkeypatch):
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e6")
    (probed,) = check_conjectures(
        sq, [claim("for x in [0, oo), f(x) >= 0", route="probe")])
    assert probed.verdict == "holds", probed.note
    assert ("the computation approximates infinity as 1e+06 "
            "(MATHEMA_PSEUDO_INFINITY); the mathematics keeps the "
            "declared oo") in probed.note, probed.note
    assert probed.meta["mathema.pseudo_infinity"] == {
        "value": 1e6, "source": "environment"}


# --- the probe route reaches finite values only (P1 corollary) -------------

def test_the_sampler_never_draws_an_infinity_for_an_infinite_endpoint():
    import random

    from mathema._sampling import _synth_scalar
    from mathema.domain import Interval
    rng = random.Random(7)
    for bounds in (Interval(0.0, math.inf, False, True),
                   Interval(-math.inf, 5.0), Interval(-math.inf, math.inf)):
        draws = [_synth_scalar(rng, bounds) for _ in range(2000)]
        assert all(math.isfinite(v) for v in draws), bounds
        far = [v for v in draws if abs(v) > 1e100]
        assert far, f"{bounds}: the far decades are never exercised"


def test_a_bare_domain_samples_up_to_the_declared_reach():
    law = "let |inf| be 30, for x in R, f(x) > 0"
    (probed,) = check_conjectures(logistic, [claim(law, route="probe")])
    assert probed.verdict == "holds", (probed.note, probed.counterexample)
    assert (probed.route or "").startswith("probe")
    (bare,) = check_conjectures(
        logistic, [claim("let |inf| be 30, f(x) > 0", route="probe")])
    assert bare.verdict == "holds", (bare.note, bare.counterexample)


def test_without_a_reach_the_bare_domain_falls_at_a_far_corner():
    (probed,) = check_conjectures(
        logistic, [claim("for x in R, f(x) > 0", route="probe")])
    assert probed.verdict == "falsified"
    import re
    x = float(re.search(r"-?[\d.]+e[+-]\d+|-?[\d.]+",
                        probed.counterexample).group())
    assert abs(x) > 700, probed.counterexample


def test_the_extreme_ladder_keeps_its_rungs_below_the_reach():
    from mathema.hazards import _extreme_candidates
    capped = _extreme_candidates((0.0, math.inf),
                                 pseudo_infinity=(-1e200, 1e200))
    assert 1e200 in capped and 1e154 in capped and 710.0 in capped
    assert sys.float_info.max not in capped
    small = _extreme_candidates(None, pseudo_infinity=(-30.0, 30.0))
    assert set(small) >= {30.0, -30.0, 1e-308, -1e-308}
    assert 710.0 not in small


# --- the function level reaches verify, and freshness sees a change -------

def _project(tmp_path, entry_field=""):
    (tmp_path / "pimod.py").write_text(textwrap.dedent('''
        def sq(x: float) -> float:
            """The square."""
            return x * x
    '''))
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "pimod.claims.yaml").write_text(textwrap.dedent(f"""
        pimod.sq:
          {entry_field}
          claims:
            - name: nonneg
              statement: 'for x in R, f(x) >= 0'
    """))


def _verified_rows(result):
    return {entry["key"]: entry for entry in result.keys}


@pytest.mark.needs_full_proof_budget
def test_verify_honours_the_entry_field(tmp_path, monkeypatch):
    from mathema.spec import load_verified
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    _project(tmp_path, "pseudo_infinity: 1e100")
    verify_project(str(tmp_path))
    entry = load_verified(str(tmp_path))["pimod.sq"]["entry"]
    rows = {c["name"]: c for c in entry["claims"]}
    assert rows["nonneg[float]"]["verdict"] == "holds", rows["nonneg[float]"]
    assert rows["nonneg[float]"]["meta"]["mathema.pseudo_infinity"] == {
        "value": 1e100, "source": "function"}


@pytest.mark.needs_full_proof_budget
def test_a_changed_environment_value_makes_the_record_stale(tmp_path,
                                                            monkeypatch):
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    _project(tmp_path)
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e100")
    verify_project(str(tmp_path))
    again = _verified_rows(verify_project(str(tmp_path)))
    assert again["pimod.sq"]["why"] == "fresh"
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e50")
    moved = _verified_rows(verify_project(str(tmp_path)))
    assert moved["pimod.sq"]["why"] == "pseudo-infinity changed"
    monkeypatch.delenv("MATHEMA_PSEUDO_INFINITY")
    unset = _verified_rows(verify_project(str(tmp_path)))
    assert unset["pimod.sq"]["why"] == "pseudo-infinity changed"


# --- the loud warning --------------------------------------------------------

def _cli(tmp_path, *args, pseudo_infinity):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = repo + (os.pathsep + env["PYTHONPATH"]
                                if env.get("PYTHONPATH") else "")
    env.pop("MATHEMA_PSEUDO_INFINITY", None)
    if pseudo_infinity is not None:
        env["MATHEMA_PSEUDO_INFINITY"] = pseudo_infinity
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(args)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                          capture_output=True, text=True, env=env)


_WARNING = ("MATHEMA_PSEUDO_INFINITY=1e6 is below 1e100: a leftover? "
            "overflow beyond it is not exercised")


def test_verify_and_check_warn_loudly_on_a_small_project_value(tmp_path):
    _project(tmp_path)
    for args in (("verify", "--root", str(tmp_path)),
                 ("check", str(tmp_path / "pimod.py"))):
        r = _cli(tmp_path, *args, pseudo_infinity="1e6")
        assert r.stderr.count(_WARNING) == 1, (args, r.stderr)
        quiet = _cli(tmp_path, *args, pseudo_infinity="1e100")
        assert "a leftover?" not in quiet.stderr, (args, quiet.stderr)
        unset = _cli(tmp_path, *args, pseudo_infinity=None)
        assert "a leftover?" not in unset.stderr, (args, unset.stderr)
