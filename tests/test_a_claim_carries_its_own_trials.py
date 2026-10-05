# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim may carry its own trials (`trials=` on `claim(...)`, a
`trials:` field in a claims file), which can raise its budget beyond the
usual limit; a finite domain whose point count is within it is swept in
full on the computation line. `--trials-downscale` (Python keyword
`trials_downscale`) only shrinks the budget, and the old spelling
`--trials-scale` still works with a deprecation note."""
import math
import os
import subprocess
import sys
import textwrap
import warnings

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.spec import entry_claims

_LAW = ("for periods in [1, 260] subset Z, active in [0, 260] subset Z, "
        "assuming active <= periods, "
        "f(active, periods) == ceil(100*active/periods)/100")


def exposure_formula(active: int, periods: int) -> float:
    return math.ceil(active / periods * 100) / 100


def test_claim_takes_trials():
    cj = claim(_LAW, trials=40000)
    assert cj.trials == 40000


def test_a_claims_file_entry_takes_trials():
    (cj,) = entry_claims({"claims": [{"name": "c", "statement": _LAW,
                                      "trials": 40000}]})
    assert cj.trials == 40000


def test_claim_trials_within_the_domain_sweeps_every_point(monkeypatch):
    from mathema import gates
    # however slow the timing looks, the claim asked for every point
    monkeypatch.setattr(gates, "_SWEEP_SECONDS", 0.0)
    probes = check_conjectures(exposure_formula, [claim(_LAW, trials=40000)],
                               float_companions=True)
    (float_row,) = [p for p in probes if p.name.endswith("[float]")]
    assert float_row.verdict == "falsified"
    assert "every point of the domain in order" in float_row.note, float_row.note


def unsortable(a: float, b: float) -> float:
    vals = [a, b]
    vals.sort()
    return vals[0] + vals[1]


def test_claim_trials_raise_the_probe_budget():
    law = "for a in [-5, 5], b in [-5, 5], f(a, b) == f(b, a)"
    (usual,) = check_conjectures(unsortable, [claim(law, route="probe")])
    (raised,) = check_conjectures(unsortable, [claim(law, route="probe",
                                                     trials=3000)])
    assert usual.verdict == raised.verdict == "holds"
    assert raised.n >= 3000 > usual.n, (usual.n, raised.n)


def test_trials_downscale_is_the_python_keyword():
    def ident(x: float) -> float:
        return x
    rec = mathema.check(ident, claims=["for x in [0, 1], f(x) == x"],
                        trials_downscale=0.5)
    assert rec.probes
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mathema.check(ident, claims=["for x in [0, 1], f(x) == x"],
                      trials_scale=0.5)
    assert any(issubclass(w.category, DeprecationWarning)
               and "trials_scale" in str(w.message) for w in caught)


def test_the_cli_takes_trials_downscale_and_the_old_spelling(tmp_path):
    (tmp_path / "m.py").write_text(textwrap.dedent("""
        def ident(x: float) -> float:
            return x
    """))
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    env.pop("VIRTUAL_ENV", None)

    def run(*args):
        script = ("import sys; from mathema.cli import main; "
                  f"sys.exit(main({list(args)!r}))")
        return subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                              capture_output=True, text=True, env=env)
    new = run("check", "m.py", "--claim", "for x in [0, 1], f(x) == x",
              "--trials-downscale", "0.5")
    assert new.returncode == 0, new.stderr
    old = run("check", "m.py", "--claim", "for x in [0, 1], f(x) == x",
              "--trials-scale", "0.5")
    assert old.returncode == 0, old.stderr
    assert "--trials-scale is deprecated" in old.stderr
    assert "--trials-downscale" in old.stderr
