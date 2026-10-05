# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim with lines under it prints as a block: the claim and its
overall verdict on one line, then one line per aspect of what is known
about it (the mathematics over the numbers, the computation in float,
and the policy at each value that is not a number: f(nan), f(None),
f([])), each with its verdict first. The claim is falsified when any of
its lines is, and a falsified absence or missing line says the possible
fixes."""
import math
from typing import Optional

import mathema
import pandas as pd


def root_opt(x: Optional[float]) -> float:
    return math.sqrt(x)


def first(xs: list) -> float:
    return xs[0]


def _lines(rec) -> list:
    return repr(rec).splitlines()


def test_a_claim_with_lines_prints_as_a_block():
    rec = mathema.check(root_opt, claims=[mathema.claim(
        "for x in [0, 4], f(x) >= 0", name="nonneg")])
    lines = _lines(rec)
    start = next(i for i, line in enumerate(lines) if line.startswith("  nonneg  "))
    head, *block = lines[start:start + 9]
    assert head.endswith("falsified at x = None"), head
    assert block[0].split() [:2] == ["proven", "mathematics"], block[0]
    assert "for x in [0.0, 4.0] ⊂ ℝ, f(x) >= 0" in block[0], block[0]
    assert block[1].split()[:2] == ["holds", "computation"], block[1]
    assert "for x in [0.0, 4.0] : float, f(x) >= 0" in block[1], block[1]
    assert block[1].rstrip().endswith("draws"), block[1]
    assert block[2].split()[:3] == ["proven", "policy", "f(nan)"], block[2]
    assert block[3].split()[:3] == ["falsified", "policy", "f(None)"], block[3]
    assert "no absent policy stated; raises TypeError" in block[3], block[3]
    assert [line.strip() for line in block[4:8]] == [
        "possible fixes:",
        "(i) if the raise is intended, run: mathema accept "
        "test_a_claim_reads_as_its_lines.root_opt absent[x] --as discovery --corrected "
        "\"absent(f, x) raises(TypeError)\"",
        "(ii) exclude None",
        "(iii) handle None at entry"], block[4:8]


def test_the_verdict_words_are_spelled_out():
    rec = mathema.check(root_opt, claims=[mathema.claim(
        "for x in [0, 4], f(x) >= 0", name="nonneg")])
    assert "FALSIFY" not in repr(rec)


def test_the_empty_input_line_sits_in_the_block():
    rec = mathema.check(first, claims=[mathema.claim(
        "for xs in [0, 1]^n, f(xs) >= 0", name="lead")])
    lines = _lines(rec)
    start = next(i for i, line in enumerate(lines) if line.startswith("  lead  "))
    assert lines[start].endswith("falsified at xs = []"), lines[start]
    empty = next(line for line in lines[start + 1:] if "f([])" in line)
    assert empty.split()[:3] == ["falsified", "policy", "f([])"], empty


def test_the_mathematics_line_keeps_its_own_verdict_under_an_empty_input_witness():
    # min(xs, "a") has no value at any drawn xs, so the mathematics is
    # undecided; f([]) raises, which falsifies the claim, and the
    # mathematics line still says unknown
    rec = mathema.check(first, claims=[mathema.claim(
        'for xs in [0, 1]^n, f(xs) >= min(xs, "a")', name="lead")])
    (row,) = [p for p in rec.probes if p.name == "lead"]
    assert row.verdict == "falsified"
    assert row.meta["mathema.mathematics"]["verdict"] == "unknown", row.meta
    lines = _lines(rec)
    start = next(i for i, line in enumerate(lines) if line.startswith("  lead  "))
    # the probe's draws all leave the claim's own side without a value,
    # so the probe decides nothing and derive's unknown stands as the
    # mathematics line, with the probe's reason carried (ruling of
    # 2026-10-01: an undecided point never counts toward holds)
    assert lines[start + 1].split()[:2] == ["unknown", "mathematics"], lines[start + 1]
    assert "the claim's own side could not be evaluated" in lines[start + 1]


def line_of(x: float) -> float:
    return 2.0 * x + 1.0


def test_the_headline_is_the_weakest_line_when_none_is_falsified():
    # the mathematics is proven, the computation and the policy hold
    rec = mathema.check(line_of, claims=[mathema.claim(
        "for x in R, f(x) == 2*x + 1", name="line")])
    lines = _lines(rec)
    head = next(line for line in lines if line.startswith("  line  "))
    assert head.endswith("   holds"), head


def square_in_int32(x: float) -> float:
    import numpy as np
    return float(np.int32(x) * np.int32(x))


def test_a_verdict_from_running_the_code_is_on_the_computation_line():
    # the square is never negative; int32 overflows past 46340
    rec = mathema.check(square_in_int32, claims=[mathema.claim(
        "for x in [0, 100000], f(x) >= 0", name="sq")])
    lines = _lines(rec)
    start = next(i for i, line in enumerate(lines) if line.startswith("  sq  "))
    block = [ln for ln in lines[start + 1:] if ln.startswith("    ")]
    assert not any(ln.split()[1:2] == ["mathematics"] and ln.split()[0] == "falsified"
                   for ln in block), block
    assert block[0].split()[:2] == ["falsified", "computation"], block[0]
    assert "counterexample x = " in block[0], block[0]


_MOD = ("import math\nfrom typing import Optional\n\n"
        "def clamp(x: float) -> float:\n    return max(0.0, min(1.0, x))\n\n"
        "def root_opt(x: Optional[float]) -> float:\n    return math.sqrt(x)\n")
_CLAIMS = ("fixmod.clamp:\n  claims:\n    - name: unit\n"
           "      statement: \"for x in [0, 1], 0 <= f(x) <= 1\"\n"
           "fixmod.root_opt:\n  claims:\n    - name: nonneg\n"
           "      statement: \"for x in [0, 4], f(x) >= 0\"\n")


def test_the_first_possible_fix_is_a_command_that_settles_the_line(tmp_path, monkeypatch):
    import shlex

    from mathema.cli import main
    (tmp_path / "fixmod.py").write_text(_MOD)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "fix.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    import fixmod
    assert main(["verify", "--root", str(tmp_path)]) == 1
    for fn, text in ((fixmod.clamp, "for x in [0, 1], 0 <= f(x) <= 1"),
                     (fixmod.root_opt, "for x in [0, 4], f(x) >= 0")):
        rec = mathema.check(fn, claims=[mathema.claim(text, name="c")])
        lines = _lines(rec)
        at = next(i for i, line in enumerate(lines) if "possible fixes:" in line)
        # the command is the last thing on its line
        command = lines[at + 1].split(", run: ", 1)[1]
        argv = shlex.split(command)
        assert argv[:2] == ["mathema", "accept"], command
        assert main(argv[1:] + ["--yes", "--root", str(tmp_path)]) == 0, command
    assert main(["verify", "--root", str(tmp_path)]) == 0


def average_return(returns: pd.Series) -> float:
    return float(returns.mean())


def test_a_chained_claim_on_a_series_keeps_its_computation_line():
    rec = mathema.check(average_return, claims=[
        "for returns in [-0.1, 0.1]^n \\ {missing}, "
        "min(returns) <= f(returns) <= max(returns)"])
    names = [p.name for p in rec.probes]
    assert "min_returns_le_f_returns_le_max_returns[float, pandas.Series]" in names, names
    lines = _lines(rec)
    assert any(line.split()[:2] == ["holds", "computation"] for line in lines), lines
    assert any("f([])" in line for line in lines), lines


def mean_return(xs: pd.Series) -> float:
    return float(xs.mean())


def test_two_policy_lines_for_one_parameter_say_which_case_each_is():
    rec = mathema.check(mean_return, claims=[mathema.claim(
        "for xs in [-1, 1]^n, -1 <= f(xs) <= 1", name="bounded")])
    policy = [line for line in _lines(rec) if line.split()[1:2] == ["policy"]
              and "f([])" not in line]
    labels = [line.split("policy", 1)[1].strip().split("   ")[0] for line in policy]
    assert len(labels) == len(set(labels)), policy
    assert labels == ["f([..., missing, ...]) assuming count(xs) >= 1",
                      "f([..., missing, ...]) assuming count(xs) == 0"], labels


def test_a_falsified_case_says_what_f_did_and_offers_no_partial_command():
    rec = mathema.check(mean_return, claims=[mathema.claim(
        "for xs in [-1, 1]^n, -1 <= f(xs) <= 1", name="bounded")])
    lines = _lines(rec)
    at = next(i for i, line in enumerate(lines)
              if "assuming count(xs) == 0" in line and line.split()[0] == "falsified")
    assert "raises TypeError, where the word is propagates" in lines[at], lines[at]
    # one claim per member settles it, so no single command is offered
    assert [line.strip() for line in lines[at + 1:at + 4]] == [
        "possible fixes:", "(i) exclude missing", "(ii) handle missing at entry"], \
        lines[at + 1:at + 4]


def a_hair_over_one(x: float) -> float:
    return min(1.0, x) + 1e-12


def test_a_line_that_passed_within_the_tolerance_prints_the_gap():
    rec = mathema.check(a_hair_over_one, claims=[mathema.claim(
        "for x in [0.5, 2], 0 <= f(x) <= 1", name="unit", route="probe")])
    line = next(ln for ln in _lines(rec)
                if ln.split()[:2] == ["holds", "computation"])
    assert "fails by 1e-12 at x = 2, within the default tolerance (1e-09)" in line, line
