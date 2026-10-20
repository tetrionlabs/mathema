# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A computation line under a proven claim is accepted alone, as a
discovery, only where its conditioning says the loss is inherent: no
float64 computation could do better at the witness. Where the code
loses more than the conditioning explains, or whether the loss is
inherent was not decided, the acceptance is refused with the cause and
the ways out: fix the code, or narrow the claim's domain knowingly and
supersede it. Each way out the refusal names is run here."""
import shlex

import pytest

from mathema.acceptance import AcceptanceError, plan_acceptance
from mathema.cli import main

_ONE = ("def plus_one_minus(x: float) -> float:\n"
        "    return (x + 1.0) - x\n")
_ONE_FIXED = ("def plus_one_minus(x: float) -> float:\n"
              "    gap = x - x\n"
              "    return gap + 1.0\n")
_ONE_CLAIMS = ("stepmod.plus_one_minus:\n  claims:\n    - name: one\n"
               "      statement: \"for x in [0, 1e300], f(x) == 1\"\n")

_SQUARED = ("def squared(x: float) -> float:\n"
            "    return x * x\n")
_SQUARED_CLAIMS = ("sqmod.squared:\n  claims:\n    - name: nonneg\n"
                   "      statement: \"for x in [1e200, 1e300], f(x) >= 0\"\n")

_SHARPE = ("import numpy as np\nimport pandas as pd\n\n"
           "def sharpe(returns: pd.Series) -> float:\n"
           "    return returns.mean() / returns.std(ddof=1) * np.sqrt(252)\n")
_SHARPE_CLAIMS = (
    "sharpemod.sharpe:\n  claims:\n    - name: leverage_invariant\n"
    "      statement: \"for returns in [-0.1, 0.1]^n \\\\ {missing}, "
    "let s = mathema.f.scale_seq, let c be [0.1, 10], "
    "assuming std(returns, ddof=1) > 0, f(s(returns, c)) ~= f(returns)\"\n")


def _project(tmp_path, monkeypatch, module, source, claims):
    (tmp_path / f"{module}.py").write_text(source)
    (tmp_path / "claims").mkdir(exist_ok=True)
    (tmp_path / "claims" / f"{module}.claims.yaml").write_text(claims)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _refusal(tmp_path, key, row) -> str:
    with pytest.raises(AcceptanceError) as refused:
        plan_acceptance(str(tmp_path), key, row, "discovery")
    return str(refused.value)


def test_a_loss_that_is_the_codes_is_refused_with_the_ways_out(
        tmp_path, monkeypatch, capsys):
    _project(tmp_path, monkeypatch, "stepmod", _ONE, _ONE_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    text = _refusal(tmp_path, "stepmod.plus_one_minus", "one[float]")
    assert "f loses more than the conditioning explains" in text, text
    assert "accepted alone only where its loss is inherent" in text, text
    assert "fix the code" in text, text
    assert ("edit one, then run: mathema accept stepmod.plus_one_minus one "
            "--as superseded") in text, text
    # verify's note offers the same ways out, and no acceptance of the
    # line alone
    assert "one[float] initially falsified" in printed, printed
    assert '"one[float]" --as discovery' not in printed, printed
    assert "fix the code" in printed, printed
    assert ("edit one, then run: mathema accept stepmod.plus_one_minus one "
            "--as superseded") in printed, printed


def test_fixing_the_code_settles_the_line(tmp_path, monkeypatch, capsys):
    _project(tmp_path, monkeypatch, "stepmod", _ONE, _ONE_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    (tmp_path / "stepmod.py").write_text(_ONE_FIXED)
    import sys
    sys.modules.pop("stepmod", None)
    assert main(["verify", "--root", str(tmp_path)]) == 0, \
        capsys.readouterr().out


def test_narrowing_the_domain_knowingly_settles_the_line(
        tmp_path, monkeypatch, capsys):
    _project(tmp_path, monkeypatch, "stepmod", _ONE, _ONE_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    command = next(line.split("run: ", 1)[1] for line in printed.splitlines()
                   if "--as superseded" in line)
    (tmp_path / "claims" / "stepmod.claims.yaml").write_text(
        _ONE_CLAIMS.replace("1e300", "1e15"))
    argv = shlex.split(command)
    assert main(argv[1:] + ["--yes", "--root", str(tmp_path)]) == 0, argv
    assert main(["verify", "--root", str(tmp_path)]) == 0, \
        capsys.readouterr().out


def test_a_line_with_no_conditioning_read_is_undecided_and_refused(
        tmp_path, monkeypatch):
    # x*x overflows to inf: the line fails without a relation miss, so
    # no conditioning is read at its witness
    _project(tmp_path, monkeypatch, "sqmod", _SQUARED, _SQUARED_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    text = _refusal(tmp_path, "sqmod.squared", "nonneg[float]")
    assert "whether the loss is inherent is not decided" in text, text
    assert "fix the code" in text, text


def test_an_undecided_conditioning_is_refused(tmp_path, monkeypatch, capsys):
    pytest.importorskip("pandas")
    _project(tmp_path, monkeypatch, "sharpemod", _SHARPE, _SHARPE_CLAIMS)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    rows = [line for line in printed.splitlines() if "initially falsified" in line]
    assert any("conditioning unknown here" in line for line in rows), printed
    row = next(line.split(": ", 1)[1].split(" initially")[0] for line in rows
               if "conditioning unknown here" in line)
    assert row.startswith("leverage_invariant["), row
    text = _refusal(tmp_path, "sharpemod.sharpe", row)
    assert "conditioning unknown here" in text, text
    assert "not known to be inherent" in text, text


def test_an_inherent_loss_is_accepted_alone(tmp_path, monkeypatch):
    numpy = pytest.importorskip("numpy")
    assert numpy
    source = ("def running_total(xs: list, y0: float) -> float:\n"
              "    total = y0\n    for v in xs:\n        total = v + total\n"
              "    return total\n")
    claims = ("ledger.running_total:\n  claims:\n    - name: shift\n"
              "      statement: \"for xs in [-1e16, 1e16]^2 \\\\ {missing}, "
              "y0 in {1}, f(xs, y0) == f(xs, 0) + y0\"\n")
    _project(tmp_path, monkeypatch, "ledger", source, claims)
    assert main(["verify", "--root", str(tmp_path)]) == 1
    plan = plan_acceptance(str(tmp_path), "ledger.running_total",
                           "shift[float]", "discovery")
    assert plan["companion_of"] == "shift"
