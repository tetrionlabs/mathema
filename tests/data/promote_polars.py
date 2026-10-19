# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Unannotated parameters in a module that imports polars only, each
used in a way a polars DataFrame or Series supports and a list does
not."""
import polars as pl


def groups_per_row(df):
    """How many distinct k groups the frame has, per row."""
    return df.group_by("k").len().height / df.height


def scaled(df, c):
    """The returns column scaled by c."""
    assert "returns" in df.columns
    return df["returns"] * c


def spread(xs):
    """The largest value less the smallest."""
    return xs.max() - xs.min()


def scaled_annotated(df: pl.DataFrame, c):
    """The returns column scaled by c, the frame's type annotated."""
    assert "returns" in df.columns
    return df["returns"] * c
