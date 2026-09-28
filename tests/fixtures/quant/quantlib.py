# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Quant functions in the shape of a returns-analytics library.

Written for mathema's own tests: each is the kind of one-line pandas
or numpy statistic such libraries are made of (a mean, a Sharpe ratio,
volatility, the maximum drawdown of a price path, a weighted return),
so the claims about them are claims a user of such a library writes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def mean_pd(xs: pd.Series) -> float:
    return float(xs.mean())


def mean_np(xs: np.ndarray) -> float:
    return float(np.mean(xs))


def sharpe(returns: pd.Series) -> float:
    return float(returns.mean() / returns.std(ddof=1) * np.sqrt(252))


def volatility(returns: pd.Series) -> float:
    return float(returns.std(ddof=1) * np.sqrt(252))


def max_drawdown(prices: pd.Series) -> float:
    return float((prices / prices.cummax() - 1.0).min())


def weighted_return(df: pd.DataFrame) -> float:
    return float((df.w * df.r).sum())
