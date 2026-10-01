# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library method's parameter that defaults to None is a parameter a
claim can bind.

`pandas.Series.clip(lower=None, upper=None)` and
`polars.Series.clip(lower_bound=None, upper_bound=None)` take their
bounds as parameters with a default. A claim that binds them
(`lower in [-1e6, 1e6]`) samples them and passes them to the call,
rather than skipping the claim because the names are not parameters.
Both libraries clip reversed bounds their own way, so the claims here
state bounds in order.
"""
import pytest

_CLIP = ("((a + {lo} + abs(a - {lo})) / 2 + {hi} - abs((a + {lo} + "
         "abs(a - {lo})) / 2 - {hi})) / 2")


@pytest.mark.parametrize("key, lo, hi", [
    ("pandas.Series.clip", "lower", "upper"),
    ("polars.Series.clip", "lower_bound", "upper_bound"),
])
def test_a_bound_defaulting_to_none_is_sampled_and_passed(key, lo, hi):
    from mathema.conjecture import _resolve_func_ref, check_conjectures, claim
    pytest.importorskip(key.split(".")[0])
    fn = _resolve_func_ref(key)
    statement = (f"for a in R^n \\ {{∅}}, {lo} in [-1e6, 1e6], "
                 f"{hi} in [-1e6, 1e6], assuming {lo} <= {hi}, "
                 f"f(a, {lo}, {hi}) ~= "
                 + _CLIP.format(lo=lo, hi=hi))
    (p,) = check_conjectures(fn, [claim(statement, name="definition")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note)


def test_a_wrong_statement_about_the_bound_is_falsified():
    from mathema.conjecture import _resolve_func_ref, check_conjectures, claim
    pytest.importorskip("pandas")
    fn = _resolve_func_ref("pandas.Series.clip")
    (p,) = check_conjectures(fn, [claim(
        "for a in R^n \\ {∅}, lower in [-1e6, 1e6], upper in [-1e6, 1e6], "
        "f(a, lower, upper) ~= a", name="identity")])
    assert p.verdict == "falsified", (p.verdict, p.note)
