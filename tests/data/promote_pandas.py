# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Unannotated parameters in a module that imports pandas only, each
used in a way a pandas DataFrame or Series supports and a list does
not."""
import pandas as pd


def first_row_share(df):
    """The first row's v as a share of its group's total."""
    totals = df.groupby("k")["v"].sum()
    first = df.iloc[0]
    return first["v"] / totals[first["k"]]


def scaled(df, c):
    """The returns column scaled by c."""
    assert "returns" in df.columns
    return df["returns"] * c


def spread(xs):
    """The largest value less the smallest."""
    return xs.max() - xs.min()


def scaled_annotated(df: pd.DataFrame, c):
    """The returns column scaled by c, the frame's type annotated."""
    assert "returns" in df.columns
    return df["returns"] * c


def total_and_weight(xs):
    """The total times a weight read off the same object: a Series has
    no `.weight`."""
    return xs.sum() * xs.weight
