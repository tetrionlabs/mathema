# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library call's missing-value rows speak for a parameter only when
the parameter reaches the call as it was passed.

`return float(np.mean(xs))` inherits numpy.mean's rows. A body that
first changes `xs` in place (`xs[np.isnan(xs)] = 0.0`, `xs.fillna(0.0,
inplace=True)`), or through another name bound to it, hands the call a
different value, so the call's rows say nothing about `xs`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mathema import analyze
from mathema.policy import composed_policies


def mean_after_zeroing(xs: np.ndarray) -> float:
    xs[np.isnan(xs)] = 0.0
    return float(np.mean(xs))


def mean_after_inplace_fill(xs: pd.Series) -> float:
    xs.fillna(0.0, inplace=True)
    return float(xs.mean())


def mean_through_alias(xs: np.ndarray) -> float:
    ys = xs
    ys[np.isnan(ys)] = 0.0
    return float(np.mean(xs))


def plain_mean(xs: np.ndarray) -> float:
    return float(np.mean(xs))


@pytest.mark.parametrize("fn", [mean_after_zeroing, mean_after_inplace_fill,
                                mean_through_alias])
def test_a_parameter_changed_before_the_call_inherits_no_row(fn):
    assert composed_policies(fn, analyze(fn)) == {}


def test_a_parameter_passed_as_it_is_inherits_the_rows():
    composed = composed_policies(plain_mean, analyze(plain_mean))
    assert composed and composed["xs"][0] == "numpy.mean"
