# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When every witness of a falsified value claim lies at a length below
some k (a sample statistic of one element, an index past the end of a
short list), the record says so and offers the split as a command: the
claim with `assuming len(r) >= k`, and the region row `is_defined:
len(r) >= k` on f. Run, the command writes both rows, and the project
then verifies: what was a falsification becomes a held fact and a
region the function has a value on.
"""
from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import textwrap  # noqa: E402

import mathema  # noqa: E402

_MODULE = textwrap.dedent('''
    import numpy as np


    def sstd(r: np.ndarray) -> float:
        return float(np.std(r, ddof=1))


    def first_move(xs: list) -> float:
        return xs[1] - xs[0]
''')


def _module(tmp_path):
    (tmp_path / "split_mod.py").write_text(_MODULE)
    sys.path.insert(0, str(tmp_path))
    try:
        import importlib
        sys.modules.pop("split_mod", None)
        return importlib.import_module("split_mod")
    finally:
        sys.path.remove(str(tmp_path))


def _claim_probe(rec, name_part):
    return next(p for p in rec.probes if p.statement and name_part in p.statement
                and not (p.meta or {}).get("mathema.companion_of"))


def test_a_sample_statistic_of_one_element_offers_the_split_at_two(tmp_path):
    mod = _module(tmp_path)
    rec = mathema.check(mod.sstd, claims=["for r in [-1e6, 1e6]^n, f(r) >= 0"])
    p = _claim_probe(rec, "f(r) >= 0")
    assert p.verdict == "falsified"
    assert p.meta["mathema.split"] == {"param": "r", "at": 2}
    shown = repr(rec)
    assert ('possible fixes: (i) to split at the shared cause, run: '
            'mathema claims split_mod.sstd --split '
            '"for r in [-1e6, 1e6]^n, f(r) >= 0" --at "len(r) >= 2"') in shown, shown


def test_a_witness_at_the_empty_input_searches_no_split(tmp_path, monkeypatch):
    # the empty container is the empty-input line's fact (is_empty_safe,
    # which offers its own fixes); it says nothing about the lengths the
    # claim's own numbers run over, so no narrowed claim is checked
    from mathema import claims as claims_mod
    from mathema._split import split_offer
    from mathema.analysis import analyze_source
    from mathema.conjecture import claim
    from mathema.records import Probe
    mod = _module(tmp_path)
    calls = []
    real = claims_mod.check_conjectures
    monkeypatch.setattr(claims_mod, "check_conjectures",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    text = "for xs in [-1e6, 1e6]^n, f(xs) == xs[1] - xs[0]"
    cj = claim(text)
    probe = Probe(cj.name, text, "falsified", route="probe",
                  counterexample="xs = []: f raised IndexError")
    assert split_offer(mod.first_move, analyze_source(mod.first_move),
                       cj, probe, text) is None
    assert calls == []


def test_an_index_past_the_end_offers_the_split_at_two(tmp_path):
    # a bounded interval: over R^n the computation is also drawn at the
    # float-limit corners, where xs[1] - xs[0] overflows to -inf (no value
    # from finite inputs), a second failure the split would not mend
    mod = _module(tmp_path)
    rec = mathema.check(mod.first_move,
                        claims=["for xs in [-1e6, 1e6]^n, f(xs) == xs[1] - xs[0]"])
    p = _claim_probe(rec, "xs[1]")
    assert p.meta["mathema.split"] == {"param": "xs", "at": 2}


def test_a_claim_false_at_every_length_offers_no_split(tmp_path):
    mod = _module(tmp_path)
    rec = mathema.check(mod.sstd, claims=["for r in R^n, f(r) <= -1"])
    p = _claim_probe(rec, "f(r) <= -1")
    assert p.verdict == "falsified"
    assert "mathema.split" not in (p.meta or {})


def _cli(*argv, cwd):
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(argv)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(cwd),
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(cwd)})


def test_the_offered_command_writes_both_rows_and_verify_passes(tmp_path):
    (tmp_path / "split_mod.py").write_text(_MODULE)
    r = _cli("claims", "split_mod.sstd", "--split", "for r in [-1e6, 1e6]^n, f(r) >= 0",
             "--at", "len(r) >= 2", "--root", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    import yaml
    doc = yaml.safe_load((tmp_path / "claims" / "adopted.claims.yaml")
                         .read_text())
    rows = doc["split_mod.sstd"]["claims"]
    assert [(c["name"], c["statement"]) for c in rows] == [
        ("f_r_ge_0", "assuming len(r) >= 2, for r in [-1e6, 1e6]^n, f(r) >= 0"),
        ("is_defined", "len(r) >= 2")]
    v = _cli("verify", "--root", str(tmp_path), cwd=tmp_path)
    assert v.returncode == 0, v.stdout + v.stderr
    assert "ok   split_mod.sstd" in v.stdout, v.stdout
