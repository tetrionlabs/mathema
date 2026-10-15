# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim whose own row is proven and whose computation line is
falsified is accepted whole as a discovery, as an `f =:= g` claim is:
the claim's row and its computation row move to discoveries under one
acceptance, the computation's witness kept, and the claim no longer
counts as proven. A proven claim with no failing computation line is
still refused, a proof being its own acceptance. A computation line
the conditioning does not show to be inherent is refused alone, and
its refusal names this way out beside fixing the code and narrowing
the domain knowingly."""
import shlex
import sys

import pytest
import yaml

from mathema.acceptance import (AcceptanceError, apply_acceptance,
                                describe_acceptance, plan_acceptance)
from mathema.cli import main

_ONE = ("def plus_one_minus(x: float) -> float:\n"
        "    return (x + 1.0) - x\n")
_ONE_CLAIMS = ("stepmod.plus_one_minus:\n  claims:\n    - name: one\n"
               "      statement: \"for x in [0, 1e300], f(x) == 1\"\n")

_TOTAL = ("def running_total(xs: list, y0: float) -> float:\n"
          "    total = y0\n    for v in xs:\n        total = v + total\n"
          "    return total\n")
_TOTAL_CLAIMS = ("ledger.running_total:\n  claims:\n    - name: shift\n"
                 "      statement: \"for xs in [-1e16, 1e16]^2 \\\\ {missing}, "
                 "y0 in {1}, f(xs, y0) == f(xs, 0) + y0\"\n")

_DOUBLE = ("def double(x: float) -> float:\n"
           "    return 2 * x\n")
_DOUBLE_CLAIMS = ("dbl.double:\n  claims:\n    - name: twice\n"
                  "      statement: \"for x in [0, 10], f(x) == x + x\"\n")


def _project(tmp_path, monkeypatch, module, source, claims):
    (tmp_path / f"{module}.py").write_text(source)
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / f"{module}.claims.yaml").write_text(claims)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    sys.modules.pop(module, None)


def _record(tmp_path, key):
    path = tmp_path / ".mathema" / "verified" / f"{key}.yaml"
    return (yaml.safe_load(path.read_text()) or {})[key]


def _rows(entry, section):
    return {c["name"]: c for c in entry.get(section) or []}


def test_a_proven_claim_retires_whole_with_its_failing_computation(
        tmp_path, monkeypatch, capsys):
    _project(tmp_path, monkeypatch, "stepmod", _ONE, _ONE_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    before = _record(tmp_path, "stepmod.plus_one_minus")
    claims = _rows(before, "claims")
    assert claims["one"]["verdict"] == "proven"
    assert claims["one[float]"]["verdict"] == "falsified"
    witness = claims["one[float]"]["counterexample"]
    plan = plan_acceptance(str(tmp_path), "stepmod.plus_one_minus", "one",
                           "discovery", by="lovelace")
    assert plan["witness"] == witness
    assert [r["name"] for r in plan["moves_with"]] == ["one[float]"]
    # an inverse of a proven law cannot hold, so none is offered
    assert "corrected_statement" not in plan
    shown = "\n".join(describe_acceptance(plan))
    assert f"one[float] falsified at {witness}" in shown, shown
    assert "with its computation line one[float]" in shown, shown
    apply_acceptance(plan)
    after = _record(tmp_path, "stepmod.plus_one_minus")
    retired = _rows(after, "discoveries")
    assert set(retired) == {"one", "one[float]"}
    assert retired["one[float]"]["counterexample"] == witness
    for row in retired.values():
        assert row["accepted"]["as"] == "discovery"
        assert row["accepted"]["by"] == "lovelace"
        assert len(row["acceptance_history"]) == 1
    assert retired["one"]["accepted"] == retired["one[float]"]["accepted"]
    assert not any(n.startswith("one") for n in _rows(after, "claims"))
    # the claims file no longer states the retired law
    assert "name: one" not in (tmp_path / "claims"
                               / "stepmod.claims.yaml").read_text()
    capsys.readouterr()
    assert main(["verify", "--root", str(tmp_path)]) == 0, \
        capsys.readouterr().out


def test_an_inherent_loss_can_also_retire_the_whole_claim(
        tmp_path, monkeypatch, capsys):
    pytest.importorskip("numpy")
    _project(tmp_path, monkeypatch, "ledger", _TOTAL, _TOTAL_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    plan = plan_acceptance(str(tmp_path), "ledger.running_total", "shift",
                           "discovery")
    assert [r["name"] for r in plan["moves_with"]] == ["shift[float]"]
    apply_acceptance(plan)
    assert set(_rows(_record(tmp_path, "ledger.running_total"),
                     "discoveries")) == {"shift", "shift[float]"}
    capsys.readouterr()
    assert main(["verify", "--root", str(tmp_path)]) == 0, \
        capsys.readouterr().out


def test_a_proven_claim_whose_computation_holds_is_still_refused(
        tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch, "dbl", _DOUBLE, _DOUBLE_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 0
    claims = _rows(_record(tmp_path, "dbl.double"), "claims")
    assert claims["twice"]["verdict"] == "proven"
    with pytest.raises(AcceptanceError, match="proof is its own acceptance"):
        plan_acceptance(str(tmp_path), "dbl.double", "twice", "discovery")


def test_the_refusal_of_the_line_alone_names_accepting_the_whole_claim(
        tmp_path, monkeypatch, capsys):
    _project(tmp_path, monkeypatch, "stepmod", _ONE, _ONE_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    with pytest.raises(AcceptanceError) as refused:
        plan_acceptance(str(tmp_path), "stepmod.plus_one_minus",
                        "one[float]", "discovery")
    text = str(refused.value)
    whole = ("accept the whole claim as a discovery, keeping both lines, "
             "run: mathema accept stepmod.plus_one_minus one --as discovery")
    assert whole in text, text
    assert "fix the code" in text, text
    assert "--as superseded" in text, text
    # verify's note offers the same three ways out
    assert whole in printed, printed
    # the way out it names runs, and leaves verify clean
    command = next(line.split("run: ", 1)[1] for line in printed.splitlines()
                   if line.rstrip().endswith("one --as discovery"))
    argv = shlex.split(command)
    assert main(argv[1:] + ["--yes", "--root", str(tmp_path)]) == 0, argv
    assert set(_rows(_record(tmp_path, "stepmod.plus_one_minus"),
                     "discoveries")) == {"one", "one[float]"}
    capsys.readouterr()
    assert main(["verify", "--root", str(tmp_path)]) == 0, \
        capsys.readouterr().out
