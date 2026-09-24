# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The two strata: verdict about the artifact, stratum about the layer.

A falsified claim's verdict never moves; the stratum, present only
where evidence exists, says which layer the falsification indicts. The
tests here hold the three invariants that make the field honest: it
never softens a verdict, it is absent without evidence, and the
evidence classes that write it are the ones that genuinely support the
classification (an exact-arithmetic proof coexisting with an executed
break; a machine-failure raise; nudged inputs evaluating cleanly).
"""
import importlib
import sys
import textwrap

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.records import Probe, claim_row, stance
from mathema.spec import to_spec
from mathema.verify import gate


@pytest.fixture
def modfile(tmp_path, monkeypatch):
    def load(name, src):
        (tmp_path / f"{name}.py").write_text(textwrap.dedent(src))
        monkeypatch.syspath_prepend(str(tmp_path))
        sys.modules.pop(name, None)
        importlib.invalidate_caches()
        return importlib.import_module(name)

    return load


def _one(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, **kw)])
    return p


# --- never softens ----------------------------------------------------------

def test_a_stratum_never_softens_the_verdict():
    p = Probe("k", "s", "falsified", counterexample="x: raised",
              meta={"mathema.claim_source": "user"},
              stratum={"mathematics": "sound", "blame": "implementation",
                       "cause": "implementation:overflow"})
    assert p.verdict == "falsified"
    assert stance(p.verdict) == "refuted"
    report = gate([p], strict=False)
    assert report.refuted == 1 and report.problems


# --- absent without evidence ------------------------------------------------

def test_an_ordinary_probe_mismatch_carries_no_stratum(modfile):
    mod = modfile("plainmod", '''
        def off_by_one(x: float) -> float:
            """x plus one."""
            return x + 1.0
    ''')
    p = _one(mod.off_by_one, "for x in [0, 10], f(x) == x", route="probe")
    assert p.verdict == "falsified"
    assert p.stratum is None
    row = claim_row(p)
    assert "refuted_by" not in row and row["reason"] is None


def test_a_corroborated_symbolic_disproof_indicts_the_mathematics(modfile):
    """The derive route on the same claim: symbolically disproven AND
    reproduced against the real function, which is the evidence bar
    for saying the mathematics itself is unsound."""
    mod = modfile("plainmod2", '''
        def off_by_one(x: float) -> float:
            """x plus one."""
            return x + 1.0
    ''')
    p = _one(mod.off_by_one, "for x in [0, 10], f(x) == x", route="derive")
    assert p.verdict == "falsified"
    assert p.stratum is not None
    assert p.stratum["mathematics"] == "unsound"
    assert p.stratum["blame"] == "claim"
    assert claim_row(p)["refuted_by"] == "claim"


def test_a_mathematical_partiality_raise_carries_no_stratum(modfile):
    # log(-1) raising is the mathematics (or the claim's domain)
    # talking, never implementation blame
    mod = modfile("logmod", '''
        import math

        def safe_log(x: float) -> float:
            """Natural log."""
            return math.log(x)
    ''')
    p = _one(mod.safe_log, "for x in [-1, 1], f(x) <= 1", route="probe")
    assert p.verdict == "falsified"
    assert "raised" in (p.counterexample or "")
    assert p.stratum is None


# --- the evidence classes that write it -------------------------------------

def test_an_overflow_raise_pins_implementation_blame(modfile):
    mod = modfile("ovfmod", '''
        import math

        def explode(x: float) -> float:
            """Exponential of a square."""
            return math.exp(x * x)
    ''')
    p = _one(mod.explode, "for x in [0, 1e6], f(x) >= 1", route="probe")
    assert p.verdict == "falsified"
    assert p.stratum is not None
    assert p.stratum["blame"] == "implementation"
    assert p.stratum["cause"] == "implementation:overflow"
    # a machine failure alone says nothing about the mathematics
    assert "mathematics" not in p.stratum
    row = claim_row(p)
    assert row["refuted_by"] == "implementation:overflow"
    assert row["reason"] == "implementation:overflow"


def test_the_float_companion_states_mathematics_sound(modfile):
    mod = modfile("fragmod", '''
        def plus_one_minus(x: float) -> float:
            """One, computed the long way round."""
            return (x + 1.0) - x
    ''')
    probes = {p.name: p for p in check_conjectures(
        mod.plus_one_minus,
        [claim("let |inf| be 1e17, for x in [0, oo], f(x) == 1",
               name="one", route="derive")],
        float_companions=True)}
    assert probes["one"].verdict == "proven"
    assert probes["one"].stratum is None
    companion = probes["one[float]"]
    assert companion.verdict == "falsified"
    assert companion.stratum["mathematics"] == "sound"
    assert companion.stratum["blame"] == "implementation"
    assert companion.stratum["cause"] == "implementation:numerical-instability"


# --- persistence ------------------------------------------------------------

def test_the_stratum_round_trips_through_the_record(modfile):
    mod = modfile("rtmod", '''
        import math

        def explode(x: float) -> float:
            """Exponential of a square."""
            return math.exp(x * x)
    ''')
    rec = mathema.check(mod.explode, claims=[
        claim("for x in [0, 1e6], f(x) >= 1", route="probe")])
    spec = to_spec(rec)
    (row,) = [c for c in spec["claims"] if c["verdict"] == "falsified"]
    stored = row["meta"]["mathema.stratum"]
    assert stored["cause"] == "implementation:overflow"
    # the stored dict reconstructs the same agent-facing row
    live = claim_row([p for p in rec.probes
                      if p.verdict == "falsified"][0])
    reloaded = claim_row(row)
    assert live["refuted_by"] == reloaded["refuted_by"]
    assert live["reason"] == reloaded["reason"]


def test_repr_renders_the_stratum_without_touching_the_verdict(modfile):
    mod = modfile("reprmod", '''
        import math

        def explode(x: float) -> float:
            """Exponential of a square."""
            return math.exp(x * x)
    ''')
    rec = mathema.check(mod.explode, claims=[
        claim("for x in [0, 1e6], f(x) >= 1", route="probe")])
    text = repr(rec)
    assert "FALSIFY" in text
    assert "implementation:overflow" in text
