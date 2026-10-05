# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What f does with an empty input is strict by default: a nan or a
None returned for `[]` is no value, so a value claim's empty-input line
is falsified unless the author states what the empty input means. The
author states it with the claim forms that already exist, read by the
line as its policy:

- `f([]) in {missing}`: no value is the intended answer;
- `raises(f([]), E)`: the empty input is refused with E;
- `f([]) == 0`: the empty input has that value.

The line holds where f does what the policy says and is falsified with
the witness where it does not. A guard in the code (a raise for an
empty input, `enforce_dimensions` with n >= 1) counts as deliberate.
A falsified line offers its fixes with the condition first and the
claim last, after a colon.
"""
from __future__ import annotations

import statistics

import pandas as pd
import pytest

from mathema.claims import check_conjectures, claim


def mean_ret(r: pd.Series) -> float:
    return float(r.mean())


def stat_mean(xs: list) -> float:
    return statistics.mean(xs)


def total(xs: list) -> float:
    s = 0.0
    for v in xs:
        s += v
    return s


def guarded_mean(xs: list) -> float:
    if not xs:
        raise ValueError("no data")
    return sum(xs) / len(xs)


_LAW = "for r in R^n, f(r) <= max(r)"


def _line(fn, laws, param):
    probes = check_conjectures(fn, [claim(t) for t in laws],
                               float_companions=True)
    line = next(p for p in probes if p.name == f"is_empty_safe[{param}]")
    return probes[0], line


def test_a_nan_for_no_data_is_no_value_by_default():
    head, line = _line(mean_ret, [_LAW], "r")
    assert line.verdict == "falsified", (line.verdict, line.note)
    assert line.counterexample == "r = []", line.counterexample
    assert head.verdict == "falsified"


def test_a_stated_missing_answer_is_the_policy():
    head, line = _line(mean_ret, [_LAW, "f([]) in {missing}"], "r")
    assert line.verdict == "holds", (line.verdict, line.note)


def test_a_stated_raise_is_the_policy():
    law = "for xs in R^n, f(xs) <= max(xs)"
    _head, line = _line(stat_mean, [law, "raises(f([]), StatisticsError)"],
                        "xs")
    assert line.verdict == "holds", (line.verdict, line.note)
    _head, line = _line(stat_mean, [law, "raises(f([]), TypeError)"], "xs")
    assert line.verdict == "falsified", (line.verdict, line.note)


def test_a_stated_value_is_the_policy():
    law = "for xs in R^n, f(xs) == sum(xs)"
    _head, line = _line(total, [law, "f([]) == 0"], "xs")
    assert line.verdict == "holds", (line.verdict, line.note)
    _head, line = _line(total, [law, "f([]) == 1"], "xs")
    assert line.verdict == "falsified", (line.verdict, line.note)
    assert line.counterexample == "xs = []"


def test_a_guard_in_the_code_is_deliberate():
    _head, line = _line(guarded_mean, ["for xs in R^n, f(xs) <= max(xs)"],
                        "xs")
    assert line.verdict == "holds", (line.verdict, line.note)


def test_the_fixes_put_the_claim_last_after_a_colon():
    import mathema
    rec = mathema.check(mean_ret, claims=[_LAW])
    shown = repr(rec)
    assert ("(i) if nan for no data is intended, state: "
            "mean_ret([]) in {missing}") in shown, shown
    assert "(ii) guard the empty input at entry" in shown, shown


@pytest.mark.third_party_compendiums
def test_the_bundled_statistics_row_states_the_empty_refusal():
    import os

    import yaml

    from mathema.compendium import _bundled_dir
    with open(os.path.join(_bundled_dir(), "statistics.claims.yaml")) as fh:
        rows = yaml.safe_load(fh)["statistics.mean"]["claims"]
    (row,) = rows
    assert row["statement"] == "raises(f([]), StatisticsError)"
    (p,) = check_conjectures(statistics.mean, [claim(row["statement"])])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note)
